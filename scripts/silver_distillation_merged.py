#!/usr/bin/env python3
"""
Silver Standard MERGED Distillation (single pass, all structure types)
======================================================================
A cost-reduced sibling of ``silver_distillation_sequential.py``.  Instead of
re-running the whole pipeline once per structure type, this distills *all*
requested types in ONE pass per paper.  Two levers cut LLM calls and tokens:

  1. Types are grouped by the base parser method they share, so the 7
     theorem-like types (theorem/lemma/proposition/corollary/claim/conjecture/
     problem) collapse to ONE "theoremlike" track.  Aggregate calls drop from
     up to 9/paper to 3/paper, and the shared base-method context is sent once
     per group, not once per type.
  2. The analyze step batches B missed structures per LLM call (not 1) and marks
     the static base-method source with ``cache_control`` so it bills at the
     cache-read rate on every batch + the aggregate within a paper.

Each base-method group keeps its OWN self-contained ``distilled_rules.py`` under
``<eval_dir>/groups/<group>/`` (so the existing per-group prune works unchanged).
A thin, hand-authored importer ``<eval_dir>/distilled_rules.py`` re-exports a
per-type ``extract_distilled_<type>`` for every type plus ``extract_distilled_all``
so the parser dispatch (``_apply_distilled_rules``) is untouched.

Usage:
    python scripts/silver_distillation_merged.py \
        --structure-types definition,theorem,lemma,proof \
        --pilot-papers paper001,paper005 \
        --t2-dir portal/data/tier2 \
        --tex-dir /path/to/alignment/papers \
        --eval-dir src/LLMVersion/merged_eval_silver \
        --model claude-sonnet-4-6 \
        --batch-size 8
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

# Add src/LLMVersion to path for imports
REPO = Path(__file__).resolve().parent.parent
LLM_DIR = REPO / "src" / "LLMVersion"
sys.path.insert(0, str(LLM_DIR))
sys.path.insert(0, str(REPO / "src"))

import distillation_analysis as _da
from distillation_analysis import (
    base_method_groups,
    identify_dark_knowledge,
    analyze_patterns_batched,
    aggregate_rules_merged,
    prune_rules,
)

# Reuse the proven helpers + the cleaned matcher from the per-type pipeline.
import silver_distillation_sequential as seq
from silver_distillation_sequential import (
    FNAME_MAP,
    convert_t2_to_gold_csv,
    _find_main_tex,
    count_compiled_patterns,
    jaccard_similarity,
)

ALL_SILVER_TYPES = list(FNAME_MAP.keys())

# Pricing (USD per million tokens). Mirrors the per-type script.
PRICING = {
    'claude-opus':   (15.0, 75.0),
    'claude-sonnet': (3.0,  15.0),
    'claude-haiku':  (0.25, 1.25),
}


def _rates(model: str):
    for prefix, (i, o) in PRICING.items():
        if prefix in model:
            return i, o
    return 3.0, 15.0


def estimate_cost(usage: dict, model: str) -> float:
    """Cache-aware USD estimate.

    Anthropic reports non-cached input in ``input_tokens`` and bills cache reads
    at ~0.1x and cache writes at ~1.25x the input rate.
    """
    i_rate, o_rate = _rates(model)
    inp = usage.get('input_tokens', 0) or 0
    cr = usage.get('cache_read_input_tokens', 0) or 0
    cw = usage.get('cache_creation_input_tokens', 0) or 0
    out = usage.get('output_tokens', 0) or 0
    return (inp * i_rate + cr * i_rate * 0.1 + cw * i_rate * 1.25
            + out * o_rate) / 1_000_000


# ---------------------------------------------------------------------------
# Combined importer (hand-authored — no codegen risk)
# ---------------------------------------------------------------------------

def write_combined_importer(eval_dir: Path, groups: dict) -> Path:
    """Write <eval_dir>/distilled_rules.py re-exporting per-type entry points.

    `groups` maps group_key -> [types]. The importer loads each group's
    self-contained module by ABSOLUTE path (so it resolves no matter which
    {type}_eval/ dir it gets symlinked into) and exposes, for every type, an
    extract_distilled_<type>(text) that filters the group's output by
    structure_type. Missing group files degrade gracefully to [].
    """
    group_files = {
        gkey: str((eval_dir / "groups" / gkey / "distilled_rules.py").resolve())
        for gkey in groups
    }
    type_to_group = {t: gkey for gkey, types in groups.items() for t in types}

    lines = [
        "# AUTO-GENERATED combined distilled-rules importer (silver merged",
        "# distillation). Re-exports per-type entry points from per-group rule",
        "# modules so the parser dispatch (_apply_distilled_rules ->",
        "# extract_distilled_<type>) works unchanged. This file holds NO patterns,",
        "# so the prune step (which edits the per-group files) never touches it.",
        "import importlib.util as _ilu",
        "import os as _os",
        "",
        f"_GROUP_FILES = {json.dumps(group_files, indent=4)}",
        "",
        f"_TYPE_TO_GROUP = {json.dumps(type_to_group, indent=4)}",
        "",
        "",
        "def _load_group(gkey):",
        "    path = _GROUP_FILES.get(gkey)",
        "    if not path or not _os.path.isfile(path):",
        "        return None",
        "    try:",
        "        spec = _ilu.spec_from_file_location('distilled_group_' + gkey, path)",
        "        m = _ilu.module_from_spec(spec)",
        "        spec.loader.exec_module(m)",
        "        return m",
        "    except Exception:",
        "        return None",
        "",
        "",
        "def _extract_group(gkey, text):",
        "    m = _load_group(gkey)",
        "    if m is None:",
        "        return []",
        "    fn = getattr(m, 'extract_distilled_' + gkey, None)",
        "    if fn is None:",
        "        return []",
        "    try:",
        "        return fn(text) or []",
        "    except Exception:",
        "        return []",
        "",
        "",
        "def extract_distilled_all(text):",
        "    out = []",
        "    for gkey in _GROUP_FILES:",
        "        out.extend(_extract_group(gkey, text))",
        "    return out",
        "",
    ]

    # Per-type entry points.
    for t, gkey in type_to_group.items():
        if len([x for x in type_to_group.values() if x == gkey]) == 1:
            # Single-type group: the group function IS this type; re-export whole.
            lines += [
                "",
                f"def extract_distilled_{t}(text):",
                f"    return _extract_group({gkey!r}, text)",
            ]
        else:
            # Multi-type (theoremlike): filter by structure_type.
            lines += [
                "",
                f"def extract_distilled_{t}(text):",
                f"    return [d for d in _extract_group({gkey!r}, text)",
                f"            if d.get('structure_type') == {t!r}]",
            ]
    lines.append("")

    eval_dir.mkdir(parents=True, exist_ok=True)
    out = eval_dir / "distilled_rules.py"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Install / uninstall the combined importer across all involved type dirs
# ---------------------------------------------------------------------------

def install_importer(eval_dir: Path, types) -> dict:
    """Symlink <eval_dir>/distilled_rules.py into every {type}_eval/ dir.

    Returns {type: backup_path_or_None} for restoration. Reuses the per-type
    installer so sys.modules cache invalidation stays consistent.
    """
    backups = {}
    for t in types:
        _, backup = seq._install_silver_rules(eval_dir, t)
        backups[t] = backup
    return backups


def uninstall_importer(types, backups: dict) -> None:
    for t in types:
        seq._uninstall_silver_rules(t, backups.get(t))


# ---------------------------------------------------------------------------
# Combined parse: one parser run, bucket extracted raw_latex by kind
# ---------------------------------------------------------------------------

def parse_buckets(pid: str, tex_dir: Path, types, eval_dir: Path | None) -> dict:
    """Parse one paper ONCE with rules; return {type: [raw_latex, ...]}.

    If eval_dir is given, the combined importer is installed across all type
    dirs so distilled rules are applied; otherwise the parser runs as-is
    (baseline = whatever is committed, matching the per-type script).
    """
    from math_paper_parser import PaperParser

    backups = {}
    if eval_dir is not None:
        backups = install_importer(eval_dir, types)

    buckets = {t: [] for t in types}
    src_dir = tex_dir / pid / "source"
    main_tex = _find_main_tex(src_dir)
    if main_tex:
        try:
            parser = PaperParser(paper_id=pid, extraction_mode='rules',
                                 structure_types=list(types))
            graph = parser.parse_file(str(main_tex))
            for _oid, obj in graph.to_dict().get('objects', {}).items():
                kind = obj.get('kind')
                if kind in buckets:
                    raw = obj.get('raw_latex', '') or obj.get('statement', '')
                    if raw.strip():
                        buckets[kind].append(raw)
        except Exception as e:
            print(f"  [warn] parse failed for {pid}: {e}")

    if eval_dir is not None:
        uninstall_importer(types, backups)

    return buckets


def opus_buckets(t2_path: Path, types, origin_filter) -> dict:
    """Bucket opus (tier2) nodes by type from a tier2 JSON."""
    d = json.load(open(t2_path, encoding='utf-8'))
    buckets = {t: [] for t in types}
    for n in d.get("nodes", []):
        t = n.get("type")
        if t not in buckets:
            continue
        if origin_filter is not None:
            o = n.get("origin")
            if o is not None and o != origin_filter:
                continue
        raw = (n.get("statement_latex") or n.get("statement")
               or n.get("raw_latex") or "")
        if raw.strip():
            buckets[t].append(raw)
    return buckets


def write_detailed_matches(eval_dir: Path, pid: str, t: str,
                           manual_texts, opus_texts) -> Path:
    """Write <eval_dir>/_dm/<type>/detailed_matches.csv for identify_dark_knowledge."""
    out_dir = eval_dir / "_dm" / t
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "detailed_matches.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "provider", "definition_text"])
        w.writeheader()
        for raw in manual_texts:
            w.writerow({"paper_id": pid, "provider": "manual", "definition_text": raw})
        for raw in opus_texts:
            w.writerow({"paper_id": pid, "provider": "anthropic", "definition_text": raw})
    return out


# ---------------------------------------------------------------------------
# Per-type P/R/F1 from extracted vs gold (same greedy match as the per-type
# script's evaluate_single_paper).
# ---------------------------------------------------------------------------

def metrics(extracted_texts, gold_texts, threshold) -> dict:
    pairs = []
    for i, ext in enumerate(extracted_texts):
        for j, gold in enumerate(gold_texts):
            sim = jaccard_similarity(ext, gold)
            if sim >= threshold:
                pairs.append((sim, i, j))
    pairs.sort(reverse=True)
    matched_ext, matched_gold = set(), set()
    tp = 0
    for sim, i, j in pairs:
        if i in matched_ext or j in matched_gold:
            continue
        matched_ext.add(i)
        matched_gold.add(j)
        tp += 1
    fp = len(extracted_texts) - tp
    fn = len(gold_texts) - tp
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': p, 'recall': r, 'f1': f1,
            'n_extracted': len(extracted_texts), 'n_gold': len(gold_texts)}


def load_gold_texts(gold_csv: Path) -> dict:
    """Return {paper_id: [raw_latex, ...]} for one type's gold CSV."""
    out = {}
    if not gold_csv.exists():
        return out
    with open(gold_csv, encoding='utf-8-sig', errors='replace') as f:
        for row in csv.DictReader(f):
            pid = (row.get('paper_id') or '').strip()
            raw = (row.get('Gold_Standard_raw_latex') or '').strip()
            if pid and raw:
                out.setdefault(pid, []).append(raw)
    return out


def build_group_gold(gold_dir: Path, group_key: str, types_in_group) -> Path:
    """Concatenate the subtype gold CSVs into one group gold CSV for pruning."""
    out = gold_dir / f"_group_{group_key}.csv"
    cols = ["paper_id", "Gold_Standard_raw_latex", "Gold_Standard_clean_text"]
    with open(out, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=cols)
        w.writeheader()
        for t in types_in_group:
            src = gold_dir / FNAME_MAP[t]
            if not src.exists():
                continue
            with open(src, encoding='utf-8-sig', errors='replace') as fi:
                for row in csv.DictReader(fi):
                    w.writerow({c: row.get(c, "") for c in cols})
    return out


# ---------------------------------------------------------------------------
# Main merged loop
# ---------------------------------------------------------------------------

def run(args):
    t2_dir = Path(args.t2_dir).resolve()
    tex_dir = Path(args.tex_dir).resolve()
    eval_dir = Path(args.eval_dir).resolve()
    gold_dir = eval_dir / "silver_gold"
    groups_dir = eval_dir / "groups"
    model = args.model
    threshold = args.threshold
    batch_size = args.batch_size
    origin_filter = args.origin_filter or None

    types = [t.strip() for t in args.structure_types.split(',') if t.strip()]
    bad = [t for t in types if t not in FNAME_MAP]
    if bad:
        print(f"ERROR: unknown structure type(s): {bad}; valid: {ALL_SILVER_TYPES}")
        sys.exit(1)
    pilot_papers = [p.strip() for p in args.pilot_papers.split(',') if p.strip()]

    groups = base_method_groups(types)
    seq._MATCH_METRIC = args.match_metric  # drives jaccard_similarity (+ _da copy)

    print("Silver MERGED Distillation")
    print(f"  types: {types}")
    print(f"  groups: { {g: ts for g, ts in groups.items()} }")
    print(f"  model: {model}  batch_size: {batch_size}")
    print(f"  pilot papers: {pilot_papers}")
    print(f"  eval_dir: {eval_dir}")
    print(f"  match_metric: {args.match_metric}  prune_alpha: {args.prune_alpha}"
          f"  resume: {args.resume}")
    print()

    for pid in pilot_papers:
        if not (t2_dir / f"{pid}.json").exists():
            print(f"ERROR: T2 JSON not found: {t2_dir / (pid + '.json')}")
            sys.exit(1)
        if _find_main_tex(tex_dir / pid / "source") is None:
            print(f"WARNING: no .tex source for {pid}")

    eval_dir.mkdir(parents=True, exist_ok=True)
    groups_dir.mkdir(parents=True, exist_ok=True)
    log_path = eval_dir / "iteration_log.json"

    # Write the combined importer up front (groups may not exist yet -> [] until
    # a group's distilled_rules.py is generated).
    write_combined_importer(eval_dir, groups)

    iteration_log = []
    cumulative_cost = 0.0
    prior_papers = []
    start_idx = 0
    # Per-group cumulative analyze rows (accumulate across papers for sub-linearity)
    group_cum_rows = {g: [] for g in groups}
    group_cum_csv = {g: groups_dir / g / "cumulative_analyze.csv" for g in groups}

    if args.resume:
        if log_path.exists():
            iteration_log = json.load(open(log_path, encoding='utf-8'))
            prior_papers = [e['paper_id'] for e in iteration_log]
            start_idx = len(iteration_log)
            if iteration_log:
                cumulative_cost = iteration_log[-1].get('cumulative_cost_usd', 0.0)
        for g in groups:
            if group_cum_csv[g].exists():
                group_cum_rows[g] = list(csv.DictReader(open(group_cum_csv[g], encoding='utf-8')))
        print(f"  RESUME: {len(prior_papers)} prior paper(s), cumulative ${cumulative_cost:.4f}")
        print(f"          prior: {prior_papers}\n")
    else:
        # Clean slate: drop gold + per-group caches so a fresh run starts empty.
        for t in types:
            gp = gold_dir / FNAME_MAP[t]
            if gp.exists():
                gp.unlink()
        for g in groups:
            gd = groups_dir / g
            for stale in ("distilled_rules.py", "cumulative_analyze.csv"):
                if (gd / stale).exists():
                    (gd / stale).unlink()
        for g in groups:
            (groups_dir / g).mkdir(parents=True, exist_ok=True)

    # ---- Phase 1: gold CSVs (no LLM) ----
    print("=" * 70)
    print("PHASE 1: tier2 opus JSON -> per-type silver gold CSV")
    print("=" * 70)
    for pid in pilot_papers:
        for t in types:
            existing = load_gold_texts(gold_dir / FNAME_MAP[t])
            if pid in existing:
                continue
            _, n = convert_t2_to_gold_csv(t2_dir / f"{pid}.json", t, gold_dir,
                                          origin_filter=origin_filter)
            if n:
                print(f"  {pid} [{t}]: {n}")
    gold_texts_by_type = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}
    print()

    # ---- Phase 2: baseline (one parse per paper, no distilled rules) ----
    print("=" * 70)
    print("PHASE 2: baseline (single combined parse per paper)")
    print("=" * 70)
    baselines = {}  # pid -> {type -> metrics}
    for pid in pilot_papers:
        b = parse_buckets(pid, tex_dir, types, eval_dir=None)
        baselines[pid] = {t: metrics(b[t], gold_texts_by_type[t].get(pid, []), threshold)
                          for t in types}
        avg = sum(m['f1'] for m in baselines[pid].values()) / len(types)
        print(f"  {pid}: avg baseline F1={avg:.3f}  "
              + " ".join(f"{t[:3]}={baselines[pid][t]['f1']:.2f}" for t in types))
    print()

    # ---- Phase 3: sequential merged distillation ----
    print("=" * 70)
    print("PHASE 3: merged distillation")
    print("=" * 70)

    for offset, pid in enumerate(pilot_papers):
        paper_idx = start_idx + offset + 1
        t0 = time.time()
        t2_path = t2_dir / f"{pid}.json"
        print(f"\n{'─'*60}\nPaper {paper_idx} ({offset+1}/{len(pilot_papers)} this run): {pid}\n{'─'*60}")

        # 3a: ONE combined parse with current distilled rules + opus buckets ->
        #     per-type detailed_matches for dark-knowledge.
        print("  [1] Combined parse (rules + current distilled) ...")
        manual = parse_buckets(pid, tex_dir, types, eval_dir=eval_dir)
        opus = opus_buckets(t2_path, types, origin_filter)
        for t in types:
            write_detailed_matches(eval_dir, pid, t, manual[t], opus[t])

        # 3b: dark knowledge per type (no LLM), tagged + filtered to this paper.
        fn_items_by_group = {g: [] for g in groups}
        total_fns = 0
        per_type_fns = {}
        for t in types:
            dk = identify_dark_knowledge(str(eval_dir / "_dm" / t),
                                         str(gold_dir / FNAME_MAP[t]), t, threshold)
            dk = [d for d in dk if d['paper_id'] == pid]
            for d in dk:
                d['structure_type'] = t
            per_type_fns[t] = len(dk)
            total_fns += len(dk)
            gkey = next(g for g, ts in groups.items() if t in ts)
            fn_items_by_group[gkey].extend(dk)
        print(f"  [2] Dark knowledge: {total_fns} FN(s) "
              + " ".join(f"{t[:3]}={per_type_fns[t]}" for t in types if per_type_fns[t]))

        # 3c+3d: batched analyze + grouped aggregate, per group.
        analyze_usage_tot = _da._empty_usage()
        agg_usage_tot = _da._empty_usage()
        search_dirs = [str(tex_dir / pid / "source")]
        per_group = {}
        for gkey, items in fn_items_by_group.items():
            gdir = groups_dir / gkey
            gdir.mkdir(parents=True, exist_ok=True)
            if items:
                print(f"  [3:{gkey}] analyze {len(items)} item(s) (batch={batch_size}) ...")
                rows, ausage = analyze_patterns_batched(
                    items, str(tex_dir), group_key=gkey,
                    types_in_group=groups[gkey], model=model,
                    search_dirs=search_dirs, batch_size=batch_size)
                for k in analyze_usage_tot:
                    analyze_usage_tot[k] += ausage.get(k, 0)
                group_cum_rows[gkey].extend(rows)
                # rewrite cumulative CSV for this group
                if group_cum_rows[gkey]:
                    fns_cols = list(group_cum_rows[gkey][0].keys())
                    with open(group_cum_csv[gkey], 'w', newline='', encoding='utf-8') as f:
                        w = csv.DictWriter(f, fieldnames=fns_cols)
                        w.writeheader()
                        w.writerows(group_cum_rows[gkey])

            # aggregate if this group has any accumulated suggestion
            has_sugg = any((r.get('llm_suggested_rule') or '').strip()
                           for r in group_cum_rows[gkey])
            if has_sugg:
                print(f"  [4:{gkey}] aggregate {len(group_cum_rows[gkey])} cumulative rule(s) ...")
                _path, gusage = aggregate_rules_merged(
                    str(group_cum_csv[gkey]), gkey, groups[gkey], str(gdir), model)
                for k in agg_usage_tot:
                    agg_usage_tot[k] += gusage.get(k, 0)
            per_group[gkey] = {
                'fns': len(items),
                'rules': count_compiled_patterns(gdir / "distilled_rules.py"),
            }

        # Re-write the importer (in case a group dir was created this paper).
        write_combined_importer(eval_dir, groups)

        # 3e: prune per group (group-level gold so a pattern that's good for one
        #     subtype isn't pruned over another subtype's FP).
        papers_so_far = prior_papers + pilot_papers[:offset + 1]
        tex_search_dirs = [str(tex_dir / p / "source") for p in papers_so_far]
        for gkey in groups:
            gfile = groups_dir / gkey / "distilled_rules.py"
            if not gfile.exists():
                continue
            group_gold = build_group_gold(gold_dir, gkey, groups[gkey])
            print(f"  [5:{gkey}] prune (alpha={args.prune_alpha:.2f}) over "
                  f"{len(papers_so_far)} paper(s) ...")
            n_pruned = prune_rules(
                paper_ids=papers_so_far, structure_type=gkey,
                gold_csv=str(group_gold), eval_dir=str(groups_dir / gkey),
                threshold=threshold, max_fdr=args.prune_alpha,
                tex_search_dirs=tex_search_dirs)
            if n_pruned:
                print(f"      pruned {n_pruned} rule(s)")

        # 3f: post-eval (one combined parse with installed importer).
        post = parse_buckets(pid, tex_dir, types, eval_dir=eval_dir)
        post_metrics = {t: metrics(post[t], gold_texts_by_type[t].get(pid, []), threshold)
                        for t in types}

        # ---- cost + log ----
        analyze_cost = estimate_cost(analyze_usage_tot, model)
        aggregate_cost = estimate_cost(agg_usage_tot, model)
        total_cost = analyze_cost + aggregate_cost
        cumulative_cost += total_cost
        wall = time.time() - t0
        total_rules = sum(count_compiled_patterns(groups_dir / g / "distilled_rules.py")
                          for g in groups)
        llm_calls = analyze_usage_tot['llm_calls']  # batched analyze calls
        # plus one aggregate call per group that had suggestions:
        agg_calls = sum(1 for g in groups
                        if any((r.get('llm_suggested_rule') or '').strip()
                               for r in group_cum_rows[g]))

        def _mean(key, d):
            return round(sum(d[t][key] for t in types) / len(types), 4)

        new_fns_total = total_fns
        entry = {
            'paper_idx': paper_idx,
            'paper_id': pid,
            'total_fns': total_fns,
            'already_covered': 0,
            'new_fns_to_distill': new_fns_total,
            'new_rules_in_file': total_rules,
            'cumulative_rules': total_rules,
            'analyze_llm_calls': llm_calls,
            'aggregate_llm_calls': agg_calls,
            'total_llm_calls': llm_calls + agg_calls,
            'analyze_input_tokens': analyze_usage_tot['input_tokens'],
            'analyze_output_tokens': analyze_usage_tot['output_tokens'],
            'analyze_cache_read_tokens': analyze_usage_tot['cache_read_input_tokens'],
            'analyze_cost_usd': round(analyze_cost, 6),
            'aggregate_input_tokens': agg_usage_tot['input_tokens'],
            'aggregate_output_tokens': agg_usage_tot['output_tokens'],
            'aggregate_cache_read_tokens': agg_usage_tot['cache_read_input_tokens'],
            'aggregate_cost_usd': round(aggregate_cost, 6),
            'total_cost_usd': round(total_cost, 6),
            'cumulative_cost_usd': round(cumulative_cost, 6),
            'wall_time_seconds': round(wall, 1),
            # cross-type means keep silver_distillation_report.py working:
            'baseline_f1': _mean('f1', baselines[pid]),
            'baseline_precision': _mean('precision', baselines[pid]),
            'baseline_recall': _mean('recall', baselines[pid]),
            'post_f1': _mean('f1', post_metrics),
            'post_precision': _mean('precision', post_metrics),
            'post_recall': _mean('recall', post_metrics),
            'per_type': {t: {
                'fns': per_type_fns[t],
                'baseline': {k: round(baselines[pid][t][k], 4)
                             for k in ('precision', 'recall', 'f1', 'tp', 'fp', 'fn',
                                       'n_gold', 'n_extracted')},
                'post': {k: round(post_metrics[t][k], 4)
                         for k in ('precision', 'recall', 'f1', 'tp', 'fp', 'fn',
                                   'n_gold', 'n_extracted')},
            } for t in types},
            'per_group': per_group,
        }
        iteration_log.append(entry)
        json.dump(iteration_log, open(log_path, 'w', encoding='utf-8'), indent=2)

        print(f"\n  Summary: {total_fns} FNs → {total_rules} rules | "
              f"{llm_calls + agg_calls} LLM calls "
              f"({llm_calls} analyze + {agg_calls} aggregate) | "
              f"${total_cost:.4f} (cumul ${cumulative_cost:.4f}) | {wall:.1f}s")
        print("           avg F1 "
              f"{entry['baseline_f1']:.3f} → {entry['post_f1']:.3f}")

    # ---- Final report ----
    print(f"\n\n{'='*70}\nSILVER MERGED SUMMARY\n{'='*70}")
    print(f"\nIteration log: {log_path}")
    print(f"\n{'Paper':<12} {'FNs':>4} {'Rules':>6} {'Calls':>6} "
          f"{'Cost':>9} {'F1 pre':>7} {'F1 post':>8}")
    print("-" * 60)
    for e in iteration_log:
        print(f"{e['paper_id']:<12} {e['total_fns']:>4} {e['new_rules_in_file']:>6} "
              f"{e['total_llm_calls']:>6} ${e['total_cost_usd']:>8.4f} "
              f"{e['baseline_f1']:>7.3f} {e['post_f1']:>8.3f}")
    total_calls = sum(e['total_llm_calls'] for e in iteration_log)
    print(f"\n  Total LLM calls: {total_calls}")
    print(f"  Total cost: ${cumulative_cost:.4f}")
    if iteration_log:
        print(f"  Avg cost/paper: ${cumulative_cost/len(iteration_log):.4f}")
    print(f"\n  Combined importer: {eval_dir}/distilled_rules.py")
    print(f"  Per-group rules:   {groups_dir}/<group>/distilled_rules.py")


def main():
    p = argparse.ArgumentParser(description="Silver Standard MERGED Distillation")
    p.add_argument("--structure-types", default=",".join(ALL_SILVER_TYPES),
                   help="Comma list of types (default: all 9 silver types)")
    p.add_argument("--pilot-papers", required=True,
                   help="Comma-separated paper IDs (e.g. paper001,paper005)")
    p.add_argument("--t2-dir", default="portal/data/tier2")
    p.add_argument("--tex-dir", required=True,
                   help="Directory with paper*/source/*.tex files")
    p.add_argument("--eval-dir", required=True, help="Output dir for artifacts")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--batch-size", type=int, default=8,
                   help="Missed structures per analyze LLM call (default 8)")
    p.add_argument("--origin-filter", default=None,
                   help="Only include opus nodes whose `origin` matches (e.g. 'paper')")
    p.add_argument("--match-metric", default="jaccard",
                   choices=["jaccard", "containment"])
    p.add_argument("--prune-alpha", type=float, default=0.5,
                   help="Per-rule FDR tolerance: prune when FP/(FP+TP) > alpha")
    p.add_argument("--resume", action="store_true",
                   help="Continue a prior run in --eval-dir (per-paper invocation)")
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
