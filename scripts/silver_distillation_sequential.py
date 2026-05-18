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
        --model claude-sonnet-4-5-20250514
"""

import argparse
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

from distillation_analysis import (
    _load_gold_csv,
    _load_extractions,
    analyze_patterns,
    aggregate_rules,
    identify_dark_knowledge,
    jaccard_similarity,
    validate_rules,
)

# ---------------------------------------------------------------------------
# Pricing (USD per million tokens) — update as needed
# ---------------------------------------------------------------------------
PRICING = {
    # model-prefix -> (input_per_M, output_per_M)
    'claude-opus':   (15.0, 75.0),
    'claude-sonnet': (3.0,  15.0),
    'claude-haiku':  (0.25, 1.25),
}


def _estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate USD cost from token counts and model name."""
    for prefix, (inp_rate, out_rate) in PRICING.items():
        if prefix in model:
            return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000
    # Fallback: assume Sonnet pricing
    return (input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000


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
}


def convert_t2_to_gold_csv(t2_json_path: Path, structure_type: str,
                           out_dir: Path) -> tuple[Path, int]:
    """Convert a single T2 JSON file into gold-CSV rows for `structure_type`.

    Appends to the CSV if it already exists.
    Returns (csv_path, n_items_added).
    """
    d = json.load(open(t2_json_path, encoding='utf-8'))
    pid_num = d.get("metadata", {}).get("paper_num")
    if pid_num is None:
        pid_num = t2_json_path.stem.replace("paper", "").lstrip("0") or "1"
    pid = f"paper{int(pid_num)}"

    rows = []
    for n in d.get("nodes", []):
        if n.get("type") != structure_type:
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
                           eval_dir: Path) -> Path:
    """Parse one paper with rules, combine with opus, write detailed_matches.csv.

    Uses provider names 'manual' (for rules) and 'anthropic' (for opus)
    so that identify_dark_knowledge works unchanged.
    """
    from math_paper_parser import PaperParser

    rows = []

    # --- Rules side ---
    src_dir = tex_dir / paper_id / "source"
    main_tex = _find_main_tex(src_dir)
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
                                 "raw_latex": raw})
        except Exception as e:
            print(f"  [warn] Rules parse failed for {paper_id}: {e}")

    # --- Opus side ---
    d = json.load(open(t2_json_path, encoding='utf-8'))
    for n in d.get("nodes", []):
        if n.get("type") != structure_type:
            continue
        raw = n.get("statement_latex") or n.get("statement") or n.get("raw_latex") or ""
        if raw.strip():
            rows.append({"paper_id": paper_id, "provider": "anthropic",
                         "raw_latex": raw})

    # Write
    eval_dir.mkdir(parents=True, exist_ok=True)
    out = eval_dir / "detailed_matches.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "provider", "raw_latex"])
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

def evaluate_single_paper(paper_id: str, tex_dir: Path, structure_type: str,
                          gold_csv: Path, threshold: float = 0.7) -> dict:
    """Parse paper with rules and compute P/R/F1 against silver gold CSV."""
    from math_paper_parser import PaperParser

    # Load gold for this paper
    gold_data = _load_gold_csv(str(gold_csv))
    gold_items = gold_data.get(paper_id, [])
    gold_texts = [g['raw_latex'] for g in gold_items if g['raw_latex'].strip()]

    # Parse
    src_dir = tex_dir / paper_id / "source"
    main_tex = _find_main_tex(src_dir)
    extracted_texts = []
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
    print(f"Silver Sequential Distillation")
    print(f"  structure_type: {structure_type}")
    print(f"  model: {model}")
    print(f"  pilot papers: {pilot_papers}")
    print(f"  eval_dir: {eval_dir}")
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

    # Clean slate for eval dir
    eval_dir.mkdir(parents=True, exist_ok=True)
    # Remove old gold CSV if exists (we append per paper)
    gold_csv_path = gold_dir / FNAME_MAP[structure_type]
    if gold_csv_path.exists():
        gold_csv_path.unlink()

    iteration_log = []
    cumulative_cost = 0.0
    cumulative_rules = 0
    all_analyze_rows = []  # accumulated across papers

    print("=" * 70)
    print("PHASE 1: Convert all pilot T2 JSONs -> silver gold CSV")
    print("=" * 70)
    total_gold_items = 0
    for pid in pilot_papers:
        t2_path = t2_dir / f"{pid}.json"
        _, n_items = convert_t2_to_gold_csv(t2_path, structure_type, gold_dir)
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

    for paper_idx, pid in enumerate(pilot_papers, 1):
        t0 = time.time()
        t2_path = t2_dir / f"{pid}.json"
        print(f"\n{'─'*60}")
        print(f"Paper {paper_idx}/{len(pilot_papers)}: {pid}")
        print(f"{'─'*60}")

        # 3a: Build detailed_matches.csv for this paper
        #     (with current distilled rules already loaded by the parser)
        print(f"  [1] Parsing with rules + current distilled rules...")
        dm_path = build_detailed_matches(
            pid, t2_path, tex_dir, structure_type, eval_dir)

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
            cumulative_csv = eval_dir / "cumulative_analyze.csv"
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

        # 3f: Post-distillation evaluation
        print(f"  [5] Post-distillation evaluation...")
        post_metrics = evaluate_single_paper(
            pid, tex_dir, structure_type, gold_csv_path, threshold)
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
        if second_half < first_half:
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
    p.add_argument("--model", default="claude-sonnet-4-5-20250514",
                   help="Anthropic model for LLM calls")
    p.add_argument("--threshold", type=float, default=0.7,
                   help="Jaccard similarity threshold (default: 0.7)")
    args = p.parse_args()
    run_sequential(args)


if __name__ == "__main__":
    main()
