#!/usr/bin/env python3
"""
Silver Standard Sequential Distillation
========================================
Process tier-2 (opus) papers one by one through the NtRED distillation
pipeline, accumulating rules after each paper.  Tracks:

  - cost ($) per paper   — LLM token usage during analyze + aggregate
  - sub-linearity        — new rules needed diminishes over papers
  - wall-clock time      — per paper
  - P/R/F1               — baseline vs post-distillation, per type

Usage:
    python scripts/silver_distillation_sequential.py \
        --structure-type definition \
        --pilot-papers paper001,paper009,paper050,paper100,paper200 \
        --t2-dir portal/data/tier2 \
        --tex-dir /path/to/alignment/papers \
        --eval-dir src/LLMVersion/definition_eval_silver \
        --model claude-sonnet-4-6
"""

import argparse
import contextlib
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

# Add src/LLMVersion to path for imports
REPO = Path(__file__).resolve().parent.parent
LLM_DIR = REPO / "src" / "LLMVersion"
sys.path.insert(0, str(LLM_DIR))
sys.path.insert(0, str(REPO / "src"))

import distillation_analysis as _da
from distillation_analysis import (
    _gold_for_paper,
    _load_gold_csv,
    _load_extractions,
    analyze_patterns,
    aggregate_rules,
    identify_dark_knowledge,
    prune_rules,
)
from latex_clean import clean_latex_to_text
from node_similarity import get_match_metric


# Match metric — set by --match-metric flag. "jaccard" preserves prior behavior;
# "containment" uses |A ∩ B| / min(|A|,|B|) which is forgiving on span asymmetry
# (rules fragments inside opus paragraphs match cleanly).
def set_match_metric(metric: str) -> str:
    """Set the run-wide match metric. THE way to configure matching.

    Both similarity wrappers (this module's SILVER-profile one and
    distillation_analysis's DISTILLATION-profile one) read a single variable in
    node_similarity, so they cannot end up on different metrics. Assigning a
    module global here does nothing — call this instead.
    """
    import node_similarity as _ns
    return _ns.set_match_metric(metric)


def jaccard_similarity(text1, text2):
    """Silver-profile match score; metric read from node_similarity.

    Implementation lives in src/node_similarity.py (Profile.SILVER): the same
    macro-collapsing cleanup as before, with "jaccard" and "containment"
    selectable. Kept as a module-level function because the monkey-patch below
    relies on rebinding this name.
    """
    import node_similarity as _ns
    from node_similarity import Profile, text_sim
    return text_sim(text1, text2, profile=Profile.SILVER,
                    metric=_ns.MATCH_METRIC)


# Monkey-patch so identify_dark_knowledge / validate_rules / etc. inside
# distillation_analysis pick up the cleaned matcher transparently.
_da.jaccard_similarity = jaccard_similarity

def _estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """USD estimate from token counts (the shared pricing table)."""
    return _da.estimate_cost({'input_tokens': input_tokens, 'output_tokens': output_tokens}, model)


# ---------------------------------------------------------------------------
# T2 JSON → Gold CSV conversion
# ---------------------------------------------------------------------------

FNAME_MAP = {
    "definition":  "Gold_Standard_Definitions.csv",
    "theorem":     "Gold_Standard_Theorems.csv",
    "lemma":       "Gold_Standard_Lemmas.csv",
    "proof":       "Gold_Standard_Proofs.csv",
    "proposition": "Gold_Standard_Propositions.csv",
    "corollary":   "Gold_Standard_Corollaries.csv",
    "claim":       "Gold_Standard_Claims.csv",
    "conjecture":  "Gold_Standard_Conjectures.csv",
    "problem":     "Gold_Standard_Problems.csv",
    "remark":      "Gold_Standard_Remarks.csv",
    "algorithm":   "Gold_Standard_Algorithms.csv",
    "example":     "Gold_Standard_Examples.csv",
    "assumption":  "Gold_Standard_Assumptions.csv",
    "open_problem":"Gold_Standard_OpenProblems.csv",
}


def convert_t2_to_gold_csv(t2_json_path: Path, structure_type: str,
                           out_dir: Path,
                           origin_filter: str | None = None) -> tuple[Path, int]:
    """Convert a single T2 JSON file into gold-CSV rows for `structure_type`.

    Appends to the CSV if it already exists.
    If `origin_filter` is set (e.g. "paper"), only nodes whose `origin` field
    matches are included. Returns (csv_path, n_items_added).
    """
    d = json.load(open(t2_json_path, encoding='utf-8'))
    # Use the filename stem as paper_id (e.g. "paper001") to stay consistent
    # with how pilot_papers are specified and how evaluate_single_paper looks up gold.
    pid = t2_json_path.stem

    rows = []
    for n in d.get("nodes", []):
        if n.get("type") != structure_type:
            continue
        # origin filter: match `origin_filter`, or accept nodes with no origin
        # tag (older v4 parses don't emit the field on every node).
        if origin_filter is not None:
            o = n.get("origin")
            if o is not None and o != origin_filter:
                continue
        raw = n.get("statement_latex") or n.get("statement") or n.get("raw_latex") or ""
        clean = n.get("statement_clean") or n.get("clean_text") or ""
        if raw.strip():
            rows.append({
                "paper_id": pid,
                "Gold_Standard_raw_latex": raw,
                "Gold_Standard_clean_text": clean,
            })

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / FNAME_MAP[structure_type]
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "Gold_Standard_raw_latex",
                                          "Gold_Standard_clean_text"])
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)

    return csv_path, len(rows)


# ---------------------------------------------------------------------------
# Build detailed_matches.csv for a single paper
# ---------------------------------------------------------------------------

def build_detailed_matches(paper_id: str, t2_json_path: Path,
                           tex_dir: Path, structure_type: str,
                           eval_dir: Path,
                           origin_filter: str | None = None) -> Path:
    """Parse one paper with rules, combine with opus, write detailed_matches.csv.

    Uses provider names 'manual' (for rules) and 'anthropic' (for opus)
    so that identify_dark_knowledge works unchanged.
    """
    from math_paper_parser import PaperParser

    rows = []

    # --- Rules side, with the silver distilled rules installed ---
    src_dir = tex_dir / paper_id / "source"
    main_tex = _find_main_tex(src_dir)
    with silver_rules_installed(eval_dir, structure_type):
        if main_tex:
            try:
                parser = PaperParser(
                    paper_id=paper_id,
                    extraction_mode='rules',
                    structure_types=[structure_type],
                )
                graph = parser.parse_file(str(main_tex))
                graph_dict = graph.to_dict()
                for obj_id, obj in graph_dict.get('objects', {}).items():
                    if obj.get('kind') != structure_type:
                        continue
                    raw = obj.get('raw_latex', '') or obj.get('statement', '')
                    if raw.strip():
                        rows.append({"paper_id": paper_id, "provider": "manual",
                                     "definition_text": raw})
            except Exception as e:
                print(f"  [warn] Rules parse failed for {paper_id}: {e}")

    # --- Opus side ---
    d = json.load(open(t2_json_path, encoding='utf-8'))
    for n in d.get("nodes", []):
        if n.get("type") != structure_type:
            continue
        if origin_filter is not None:
            o = n.get("origin")
            if o is not None and o != origin_filter:
                continue
        raw = n.get("statement_latex") or n.get("statement") or n.get("raw_latex") or ""
        if raw.strip():
            rows.append({"paper_id": paper_id, "provider": "anthropic",
                         "definition_text": raw})

    # Write
    eval_dir.mkdir(parents=True, exist_ok=True)
    out = eval_dir / "detailed_matches.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "provider", "definition_text"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    return out


def _find_main_tex(src_dir: Path) -> Path | None:
    """Find the main .tex file in a source directory."""
    if not src_dir.exists():
        return None
    tex_files = sorted(src_dir.glob("*.tex"))
    if not tex_files:
        return None
    for tf in tex_files:
        try:
            with open(tf, encoding="utf-8", errors="replace") as f:
                head = f.read(8000)
            if r"\documentclass" in head:
                return tf
        except OSError:
            continue
    return tex_files[0]


# ---------------------------------------------------------------------------
# Compute P/R/F1 for a single paper against its silver gold
# ---------------------------------------------------------------------------

def _install_silver_rules(eval_dir: Path, structure_type: str) -> tuple[Path, Path | None]:
    """Symlink silver distilled_rules.py into where PaperParser expects it.

    Returns (target_dir, backup_path_or_None) so caller can restore.
    """
    silver_rules = eval_dir / "distilled_rules.py"
    parser_dir = Path(LLM_DIR)
    target_dir = parser_dir / f"{structure_type}_eval"
    target_file = target_dir / "distilled_rules.py"

    backup = None
    if target_file.exists() or target_file.is_symlink():
        backup = target_file.with_suffix('.py.silver_bak')
        if backup.exists() or backup.is_symlink():
            # an earlier install was never undone: renaming over the backup would
            # destroy the production rules it holds
            raise RuntimeError(f"{backup} already exists: a previous silver install was "
                               f"not restored. Restore it by hand before continuing.")
        target_file.rename(backup)

    if silver_rules.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file.symlink_to(silver_rules.resolve())

    return target_dir, backup


@contextlib.contextmanager
def silver_rules_installed(eval_dir: Path | None, structure_type: str):
    """Install eval_dir's rules for one type for the duration of the block, and
    restore the original even if the block is interrupted."""
    backup = None
    if eval_dir is not None:
        _, backup = _install_silver_rules(eval_dir, structure_type)
    try:
        yield
    finally:
        if eval_dir is not None:
            _uninstall_silver_rules(structure_type, backup)


def _uninstall_silver_rules(structure_type: str, backup: Path | None):
    """Restore original distilled_rules.py after silver evaluation."""
    parser_dir = Path(LLM_DIR)
    target_file = parser_dir / f"{structure_type}_eval" / "distilled_rules.py"

    if target_file.is_symlink():
        target_file.unlink()

    if backup and backup.exists():
        backup.rename(target_file)


def evaluate_single_paper(paper_id: str, tex_dir: Path, structure_type: str,
                          gold_csv: Path, threshold: float = 0.7,
                          eval_dir: Path = None) -> dict:
    """Parse paper with rules and compute P/R/F1 against silver gold CSV.

    If eval_dir is provided, temporarily installs its distilled_rules.py
    so the parser picks them up.
    """
    from math_paper_parser import PaperParser

    # Load gold for this paper (versioned ids and '_' vs '.' tolerated)
    gold_data = _load_gold_csv(str(gold_csv))
    gold_items = _gold_for_paper(gold_data, paper_id)
    gold_texts = [g['raw_latex'] for g in gold_items if g['raw_latex'].strip()]

    # Parse, with eval_dir's rules installed if given
    src_dir = tex_dir / paper_id / "source"
    main_tex = _find_main_tex(src_dir)
    extracted_texts = []
    with silver_rules_installed(eval_dir, structure_type):
        if main_tex:
            try:
                parser = PaperParser(
                    paper_id=paper_id,
                    extraction_mode='rules',
                    structure_types=[structure_type],
                )
                graph = parser.parse_file(str(main_tex))
                graph_dict = graph.to_dict()
                for obj_id, obj in graph_dict.get('objects', {}).items():
                    if obj.get('kind') != structure_type:
                        continue
                    raw = obj.get('raw_latex', '') or obj.get('statement', '')
                    if raw.strip():
                        extracted_texts.append(raw)
            except Exception as e:
                print(f"  [warn] Parse failed for {paper_id}: {e}")

    # Greedy matching (same logic as distillation_analysis.validate_rules)
    matched_gold = set()
    matched_ext = set()
    pairs = []
    for i, ext in enumerate(extracted_texts):
        for j, gold in enumerate(gold_texts):
            sim = jaccard_similarity(ext, gold)
            if sim >= threshold:
                pairs.append((sim, i, j))
    pairs.sort(reverse=True)
    tp = 0
    for sim, i, j in pairs:
        if i in matched_ext or j in matched_gold:
            continue
        matched_ext.add(i)
        matched_gold.add(j)
        tp += 1

    fp = len(extracted_texts) - tp
    fn = len(gold_texts) - tp
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        'tp': tp, 'fp': fp, 'fn': fn,
        'precision': precision, 'recall': recall, 'f1': f1,
        'n_extracted': len(extracted_texts), 'n_gold': len(gold_texts),
    }


# ---------------------------------------------------------------------------
# Count rules in distilled_rules.py
# ---------------------------------------------------------------------------

def count_compiled_patterns(rules_path: Path) -> int:
    """Count compiled regex patterns in a distilled_rules.py file."""
    if not rules_path.exists():
        return 0
    text = rules_path.read_text(encoding='utf-8')
    # Count re.compile() calls that are not commented out
    count = 0
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if 're.compile(' in stripped:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Main sequential loop
# ---------------------------------------------------------------------------

def run_sequential(args):
    t2_dir = Path(args.t2_dir).resolve()
    tex_dir = Path(args.tex_dir).resolve()
    eval_dir = Path(args.eval_dir).resolve()
    gold_dir = eval_dir / "silver_gold"
    structure_type = args.structure_type
    model = args.model
    threshold = args.threshold

    pilot_papers = [p.strip() for p in args.pilot_papers.split(',')]
    origin_filter = args.origin_filter or None
    # One setter, one variable — this configures both similarity wrappers at
    # once (see set_match_metric / node_similarity.MATCH_METRIC). They used to
    # be separate module globals, which is how the prune gate ended up scoring
    # on jaccard while the reported metrics used --match-metric.
    set_match_metric(args.match_metric)
    print(f"Silver Sequential Distillation")
    print(f"  structure_type: {structure_type}")
    print(f"  model: {model}")
    print(f"  pilot papers: {pilot_papers}")
    print(f"  eval_dir: {eval_dir}")
    print(f"  origin_filter: {origin_filter}")
    print(f"  match_metric: {get_match_metric()} (clean_latex_to_text + tokens)")
    print(f"  prune_alpha: {args.prune_alpha} (prune when FP/(FP+TP) > alpha)")
    print(f"  resume: {args.resume}")
    print()

    # Validate prerequisites
    for pid in pilot_papers:
        t2_path = t2_dir / f"{pid}.json"
        if not t2_path.exists():
            print(f"ERROR: T2 JSON not found: {t2_path}")
            sys.exit(1)
        src_dir = tex_dir / pid / "source"
        main_tex = _find_main_tex(src_dir)
        if main_tex is None:
            print(f"WARNING: No .tex source for {pid} at {src_dir}")

    eval_dir.mkdir(parents=True, exist_ok=True)
    gold_csv_path = gold_dir / FNAME_MAP[structure_type]
    cumulative_csv = eval_dir / "cumulative_analyze.csv"
    log_path = eval_dir / "iteration_log.json"

    iteration_log = []
    cumulative_cost = 0.0
    cumulative_rules = 0
    all_analyze_rows = []   # accumulated across papers (and prior invocations)
    prior_papers = []       # papers processed in earlier invocations (resume)
    start_idx = 0           # paper_idx offset for resume

    if args.resume:
        # Load prior state; keep gold CSV / distilled_rules.py on disk.
        if log_path.exists():
            with open(log_path, encoding='utf-8') as f:
                iteration_log = json.load(f)
            prior_papers = [e['paper_id'] for e in iteration_log]
            start_idx = len(iteration_log)
            if iteration_log:
                cumulative_cost = iteration_log[-1].get('cumulative_cost_usd', 0.0)
        if cumulative_csv.exists():
            with open(cumulative_csv, encoding='utf-8') as f:
                all_analyze_rows = list(csv.DictReader(f))
        print(f"  RESUME: {len(prior_papers)} prior paper(s), "
              f"{len(all_analyze_rows)} cumulative analyze row(s), "
              f"cumulative cost ${cumulative_cost:.4f}")
        print(f"          prior papers: {prior_papers}")
        print()
    else:
        # Clean slate: drop per-run accumulators so a fresh run starts empty.
        for stale in (gold_csv_path, cumulative_csv):
            if stale.exists():
                stale.unlink()

    print("=" * 70)
    print("PHASE 1: Convert all pilot T2 JSONs -> silver gold CSV")
    print("=" * 70)
    existing_gold_pids = set()
    if gold_csv_path.exists():
        with open(gold_csv_path, encoding='utf-8') as f:
            existing_gold_pids = {r['paper_id'] for r in csv.DictReader(f)}
    total_gold_items = 0
    for pid in pilot_papers:
        if pid in existing_gold_pids:
            print(f"  {pid}: already in gold CSV — skipping conversion")
            continue
        t2_path = t2_dir / f"{pid}.json"
        _, n_items = convert_t2_to_gold_csv(t2_path, structure_type, gold_dir,
                                            origin_filter=origin_filter)
        total_gold_items += n_items
        print(f"  {pid}: {n_items} {structure_type}(s)")
    print(f"  Total: {total_gold_items} gold items across {len(pilot_papers)} papers")
    print()

    print("=" * 70)
    print("PHASE 2: Baseline evaluation (before distillation)")
    print("=" * 70)
    baselines = {}
    for pid in pilot_papers:
        metrics = evaluate_single_paper(pid, tex_dir, structure_type,
                                        gold_csv_path, threshold)
        baselines[pid] = metrics
        print(f"  {pid}: P={metrics['precision']:.3f} R={metrics['recall']:.3f} "
              f"F1={metrics['f1']:.3f} (TP={metrics['tp']} FP={metrics['fp']} "
              f"FN={metrics['fn']})")

    avg_f1 = sum(m['f1'] for m in baselines.values()) / len(baselines) if baselines else 0
    print(f"  Average baseline F1: {avg_f1:.3f}")
    print()

    print("=" * 70)
    print("PHASE 3: Sequential distillation")
    print("=" * 70)

    for offset, pid in enumerate(pilot_papers):
        paper_idx = start_idx + offset + 1
        t0 = time.time()
        t2_path = t2_dir / f"{pid}.json"
        print(f"\n{'─'*60}")
        print(f"Paper {paper_idx} ({offset+1}/{len(pilot_papers)} this run): {pid}")
        print(f"{'─'*60}")

        # 3a: Build detailed_matches.csv for this paper
        #     (with current distilled rules already loaded by the parser)
        print(f"  [1] Parsing with rules + current distilled rules...")
        dm_path = build_detailed_matches(
            pid, t2_path, tex_dir, structure_type, eval_dir,
            origin_filter=origin_filter)

        # 3b: Identify dark knowledge for this paper
        print(f"  [2] Identifying dark knowledge...")
        dk_items = identify_dark_knowledge(
            str(eval_dir), str(gold_csv_path), structure_type, threshold)
        # Filter to this paper only
        dk_items = [d for d in dk_items if d['paper_id'] == pid]
        total_fns = len(dk_items)
        print(f"      {total_fns} dark-knowledge items for {pid}")

        # 3c: Count how many would have been caught by prior distilled rules
        #     (If paper_idx==1, this is always 0)
        already_covered = baselines[pid]['fn'] - total_fns if baselines[pid]['fn'] >= total_fns else 0
        new_fns = total_fns
        print(f"      Already covered by prior rules: {already_covered}")
        print(f"      New FNs to distill: {new_fns}")

        analyze_cost = 0.0
        aggregate_cost = 0.0
        analyze_usage = {'input_tokens': 0, 'output_tokens': 0, 'llm_calls': 0}
        agg_usage = {'input_tokens': 0, 'output_tokens': 0}
        new_rules_count = 0

        if dk_items:
            # 3d: Analyze patterns (LLM calls, one per FN item)
            print(f"  [3] Analyzing patterns ({len(dk_items)} items)...")
            search_dirs = [str(tex_dir / pid / "source")]
            ret = analyze_patterns(
                dk_items, str(tex_dir),
                structure_type=structure_type, model=model,
                search_dirs=search_dirs)
            if isinstance(ret, tuple):
                analyze_results, analyze_usage = ret
            else:
                analyze_results = ret
                analyze_usage = {'input_tokens': 0, 'output_tokens': 0, 'llm_calls': 0}

            analyze_cost = _estimate_cost(
                analyze_usage['input_tokens'],
                analyze_usage['output_tokens'], model)
            print(f"      Analyze: {analyze_usage['llm_calls']} LLM calls, "
                  f"${analyze_cost:.4f}")

            # Save this paper's analyze results and accumulate
            all_analyze_rows.extend(analyze_results)

            # Write cumulative CSV for aggregate step
            if all_analyze_rows:
                fieldnames = list(all_analyze_rows[0].keys())
                with open(cumulative_csv, 'w', newline='', encoding='utf-8') as f:
                    w = csv.DictWriter(f, fieldnames=fieldnames)
                    w.writeheader()
                    for r in all_analyze_rows:
                        w.writerow(r)

            # 3e: Aggregate ALL accumulated rules
            has_suggestions = any(
                r.get('llm_suggested_rule', '').strip() for r in all_analyze_rows)
            if has_suggestions:
                print(f"  [4] Aggregating {len(all_analyze_rows)} cumulative rules...")
                agg_ret = aggregate_rules(
                    str(cumulative_csv), structure_type, str(eval_dir), model)
                if isinstance(agg_ret, tuple):
                    rules_path_str, agg_usage = agg_ret
                else:
                    rules_path_str = agg_ret
                    agg_usage = {'input_tokens': 0, 'output_tokens': 0}

                aggregate_cost = _estimate_cost(
                    agg_usage['input_tokens'],
                    agg_usage['output_tokens'], model)
                print(f"      Aggregate: ${aggregate_cost:.4f}")

                new_rules_count = count_compiled_patterns(
                    Path(eval_dir / "distilled_rules.py"))
            else:
                print(f"  [4] No LLM suggestions to aggregate (all tex_not_found?)")
        else:
            print(f"  [3-4] Skipping analyze/aggregate (no dark knowledge)")

        # 3e.5: Prune FP-causing rules (only if FP > TP for that rule).
        # Uses ALL papers seen so far so a rule that's a net win on later
        # papers isn't pruned for a single earlier FP. The tex search dir
        # is needed because the silver pilot lives outside FULL_PAPERS_DIR.
        papers_so_far = prior_papers + pilot_papers[:offset + 1]
        rules_file = eval_dir / "distilled_rules.py"
        if rules_file.exists():
            tex_search_dirs = [str(tex_dir / p / "source") for p in papers_so_far]
            print(f"  [4b] Pruning rules (alpha={args.prune_alpha:.2f}) over "
                  f"{len(papers_so_far)} paper(s)...")
            n_pruned = prune_rules(
                paper_ids=papers_so_far,
                structure_type=structure_type,
                gold_csv=str(gold_csv_path),
                eval_dir=str(eval_dir),
                threshold=threshold,
                max_fdr=args.prune_alpha,
                tex_search_dirs=tex_search_dirs,
            )
            print(f"      Pruned {n_pruned} rule(s) with FDR > {args.prune_alpha:.2f}")

        # 3f: Post-distillation evaluation
        print(f"  [5] Post-distillation evaluation...")
        post_metrics = evaluate_single_paper(
            pid, tex_dir, structure_type, gold_csv_path, threshold,
            eval_dir=eval_dir)
        print(f"      P={post_metrics['precision']:.3f} "
              f"R={post_metrics['recall']:.3f} "
              f"F1={post_metrics['f1']:.3f} "
              f"(was F1={baselines[pid]['f1']:.3f})")

        wall_time = time.time() - t0
        total_cost = analyze_cost + aggregate_cost
        cumulative_cost += total_cost
        cumulative_rules = new_rules_count  # total rules in file (not delta)

        entry = {
            'paper_idx': paper_idx,
            'paper_id': pid,
            'total_fns': total_fns,
            'already_covered': already_covered,
            'new_fns_to_distill': new_fns,
            'new_rules_in_file': new_rules_count,
            'cumulative_rules': cumulative_rules,
            'analyze_llm_calls': analyze_usage.get('llm_calls', 0),
            'analyze_input_tokens': analyze_usage.get('input_tokens', 0),
            'analyze_output_tokens': analyze_usage.get('output_tokens', 0),
            'analyze_cost_usd': round(analyze_cost, 6),
            'aggregate_input_tokens': agg_usage.get('input_tokens', 0),
            'aggregate_output_tokens': agg_usage.get('output_tokens', 0),
            'aggregate_cost_usd': round(aggregate_cost, 6),
            'total_cost_usd': round(total_cost, 6),
            'cumulative_cost_usd': round(cumulative_cost, 6),
            'wall_time_seconds': round(wall_time, 1),
            'baseline_f1': round(baselines[pid]['f1'], 4),
            'baseline_precision': round(baselines[pid]['precision'], 4),
            'baseline_recall': round(baselines[pid]['recall'], 4),
            'post_f1': round(post_metrics['f1'], 4),
            'post_precision': round(post_metrics['precision'], 4),
            'post_recall': round(post_metrics['recall'], 4),
            'n_gold': baselines[pid]['n_gold'],
            'n_extracted_baseline': baselines[pid]['n_extracted'],
            'n_extracted_post': post_metrics['n_extracted'],
        }
        iteration_log.append(entry)

        # Print summary line
        print(f"\n  Summary: +{new_fns} FNs → {new_rules_count} rules total | "
              f"${total_cost:.4f} (cumul ${cumulative_cost:.4f}) | "
              f"{wall_time:.1f}s")

    # ---------------------------------------------------------------------------
    # PHASE 4: Final report
    # ---------------------------------------------------------------------------
    print(f"\n\n{'='*70}")
    print("SILVER DISTILLATION SUMMARY")
    print(f"{'='*70}")

    # Save log
    log_path = eval_dir / "iteration_log.json"
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(iteration_log, f, indent=2)
    print(f"\nIteration log: {log_path}")

    # Summary table
    print(f"\n{'Paper':<12} {'FNs':>4} {'Covered':>8} {'New':>4} {'Rules':>6} "
          f"{'Cost':>8} {'Time':>6} {'F1 pre':>7} {'F1 post':>8}")
    print("-" * 75)
    for e in iteration_log:
        print(f"{e['paper_id']:<12} {e['total_fns']:>4} {e['already_covered']:>8} "
              f"{e['new_fns_to_distill']:>4} {e['new_rules_in_file']:>6} "
              f"${e['total_cost_usd']:>7.4f} {e['wall_time_seconds']:>5.1f}s "
              f"{e['baseline_f1']:>7.3f} {e['post_f1']:>8.3f}")

    print(f"\n  Total cost: ${cumulative_cost:.4f}")
    avg_time = sum(e['wall_time_seconds'] for e in iteration_log) / len(iteration_log)
    print(f"  Avg time/paper: {avg_time:.1f}s")
    avg_cost = cumulative_cost / len(iteration_log)
    print(f"  Avg cost/paper: ${avg_cost:.4f}")

    # Sub-linearity check
    fns_per_paper = [e['new_fns_to_distill'] for e in iteration_log]
    if len(fns_per_paper) >= 2:
        first_half = sum(fns_per_paper[:len(fns_per_paper)//2])
        second_half = sum(fns_per_paper[len(fns_per_paper)//2:])
        print(f"\n  Sub-linearity: first-half FNs={first_half}, second-half FNs={second_half}")
        if first_half == 0:
            print(f"  (no FNs in first half — sub-linearity not measurable)")
        elif second_half < first_half:
            print(f"  ✓ Diminishing returns confirmed (ratio: {second_half/first_half:.2f})")
        else:
            print(f"  ✗ No diminishing returns observed (ratio: {second_half/first_half:.2f})")

    print(f"\n  Generated rules: {eval_dir}/distilled_rules.py")
    print(f"  Run report:  python scripts/silver_distillation_report.py "
          f"--log {log_path}")


def main():
    p = argparse.ArgumentParser(description="Silver Standard Sequential Distillation")
    p.add_argument("--structure-type", required=True,
                   choices=list(FNAME_MAP.keys()),
                   help="Structure type to distill (e.g. definition, theorem)")
    p.add_argument("--pilot-papers", required=True,
                   help="Comma-separated list of paper IDs (e.g. paper001,paper009)")
    p.add_argument("--t2-dir", default="portal/data/tier2",
                   help="Directory of tier2 opus JSONs")
    p.add_argument("--tex-dir", required=True,
                   help="Directory with paper*/source/*.tex files")
    p.add_argument("--eval-dir", required=True,
                   help="Output directory for eval artifacts")
    # "claude-sonnet-4-5-20250514" was not a real model id — it pairs Sonnet
    # 4.5's name with Sonnet 4's date (4.5 is -20250929), so it 404s. Matches
    # silver_distillation_merged.py, which has always used a valid default.
    p.add_argument("--model", default="claude-sonnet-4-6",
                   help="Anthropic model for LLM calls")
    p.add_argument("--threshold", type=float, default=0.7,
                   help="Jaccard similarity threshold (default: 0.7)")
    p.add_argument("--origin-filter", default=None,
                   help="Only include nodes whose `origin` matches (e.g. 'paper'). "
                        "Use to exclude externally-cited definitions from v4 opus JSONs.")
    p.add_argument("--match-metric", default="jaccard",
                   choices=["jaccard", "containment"],
                   help="Token-set match metric. 'jaccard' = |∩|/|∪| (default, "
                        "strict). 'containment' = |∩|/min(|A|,|B|) (forgiving on "
                        "span asymmetry — recommended when rules extract fragments "
                        "of opus's bundled narrative definitions).")
    p.add_argument("--prune-alpha", type=float, default=0.5,
                   help="Per-rule false-discovery tolerance for pruning. A "
                        "distilled rule is pruned when FP/(FP+TP) > alpha across "
                        "papers seen so far. Default 0.5 = prune FP-majority "
                        "rules (legacy behavior); 0.0 = prune any rule with a "
                        "single FP; higher = more permissive.")
    p.add_argument("--resume", action="store_true",
                   help="Continue a prior run in --eval-dir instead of starting "
                        "fresh: load iteration_log.json + cumulative_analyze.csv, "
                        "keep the existing gold CSV / distilled_rules.py, and only "
                        "process pilot papers not already recorded. Lets each "
                        "paper be its own invocation.")
    args = p.parse_args()
    run_sequential(args)


if __name__ == "__main__":
    main()
