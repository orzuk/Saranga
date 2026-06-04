#!/usr/bin/env python3
"""
Silver Distillation Report
===========================
Reads iteration_log.json produced by silver_distillation_sequential.py
and generates summary tables + matplotlib plots for:

  1. Sub-linearity (new FNs per paper, cumulative rules)
  2. Cost breakdown
  3. Time breakdown
  4. P/R/F1 progression (baseline → post-distillation)
  5. Already-covered ratio

Usage:
    python scripts/silver_distillation_report.py \
        --log src/LLMVersion/definition_eval_silver/iteration_log.json
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# Allow importing the pipeline's helpers for the (opt-in) FP re-derivation.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(_REPO / "src"))

try:
    import matplotlib
    matplotlib.use('Agg')  # non-interactive backend
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def load_log(path: str) -> list[dict]:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def print_summary_table(log: list[dict]):
    print(f"\n{'='*80}")
    print("SILVER DISTILLATION — SUMMARY TABLE")
    print(f"{'='*80}")
    print(f"{'#':<3} {'Paper':<12} {'FNs':>4} {'Covered':>8} {'New':>4} "
          f"{'Rules':>6} {'Cost($)':>8} {'Time(s)':>8} {'F1-pre':>7} {'F1-post':>8}")
    print("-" * 80)
    for e in log:
        print(f"{e['paper_idx']:<3} {e['paper_id']:<12} "
              f"{e['total_fns']:>4} {e['already_covered']:>8} "
              f"{e['new_fns_to_distill']:>4} {e['new_rules_in_file']:>6} "
              f"{e['total_cost_usd']:>8.4f} {e['wall_time_seconds']:>8.1f} "
              f"{e['baseline_f1']:>7.3f} {e['post_f1']:>8.3f}")

    total_cost = sum(e['total_cost_usd'] for e in log)
    avg_time = sum(e['wall_time_seconds'] for e in log) / len(log)
    print("-" * 80)
    print(f"{'':3} {'TOTAL/AVG':<12} "
          f"{sum(e['total_fns'] for e in log):>4} "
          f"{sum(e['already_covered'] for e in log):>8} "
          f"{sum(e['new_fns_to_distill'] for e in log):>4} "
          f"{log[-1]['cumulative_rules'] if log else 0:>6} "
          f"{total_cost:>8.4f} {avg_time:>8.1f} "
          f"{sum(e['baseline_f1'] for e in log)/len(log):>7.3f} "
          f"{sum(e['post_f1'] for e in log)/len(log):>8.3f}")


def print_cost_table(log: list[dict]):
    print(f"\n{'='*80}")
    print("COST BREAKDOWN")
    print(f"{'='*80}")
    print(f"{'#':<3} {'Paper':<12} {'Analyze$':>10} {'Aggr$':>10} "
          f"{'Total$':>10} {'Cumul$':>10} {'LLM Calls':>10}")
    print("-" * 70)
    for e in log:
        print(f"{e['paper_idx']:<3} {e['paper_id']:<12} "
              f"{e['analyze_cost_usd']:>10.4f} {e['aggregate_cost_usd']:>10.4f} "
              f"{e['total_cost_usd']:>10.4f} {e['cumulative_cost_usd']:>10.4f} "
              f"{e['analyze_llm_calls']:>10}")


def print_sublinearity(log: list[dict]):
    print(f"\n{'='*80}")
    print("SUB-LINEARITY ANALYSIS")
    print(f"{'='*80}")
    fns = [e['new_fns_to_distill'] for e in log]
    covered = [e['already_covered'] for e in log]
    for i, e in enumerate(log):
        cover_pct = (e['already_covered'] / (e['total_fns'] + e['already_covered']) * 100
                     if (e['total_fns'] + e['already_covered']) > 0 else 0)
        bar = '#' * e['new_fns_to_distill'] + '.' * e['already_covered']
        print(f"  Paper {e['paper_idx']}: new={e['new_fns_to_distill']:>3}  "
              f"covered={e['already_covered']:>3}  "
              f"coverage={cover_pct:>5.1f}%  |{bar}")

    if len(fns) >= 2:
        mid = len(fns) // 2
        first_half = sum(fns[:mid])
        second_half = sum(fns[mid:])
        ratio = second_half / first_half if first_half > 0 else float('inf')
        print(f"\n  First half sum:  {first_half}")
        print(f"  Second half sum: {second_half}")
        print(f"  Ratio: {ratio:.2f} {'(sub-linear)' if ratio < 1 else '(not sub-linear)'}")


def plot_all(log: list[dict], out_dir: Path):
    if not HAS_MPL:
        print("\n  [skip] matplotlib not available — no plots generated")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    papers = [e['paper_id'] for e in log]
    idxs = [e['paper_idx'] for e in log]

    # --- Plot 1: Sub-linearity (new FNs + already covered, stacked bar) ---
    fig, ax = plt.subplots(figsize=(10, 5))
    new_fns = [e['new_fns_to_distill'] for e in log]
    covered = [e['already_covered'] for e in log]
    ax.bar(idxs, new_fns, label='New FNs to distill', color='#e74c3c')
    ax.bar(idxs, covered, bottom=new_fns, label='Already covered', color='#2ecc71')
    ax.set_xlabel('Paper Index')
    ax.set_ylabel('Count')
    ax.set_title('Sub-linearity: New FNs vs Already Covered')
    ax.set_xticks(idxs)
    ax.set_xticklabels(papers, rotation=45, ha='right')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / 'sublinearity_bars.png', dpi=150)
    plt.close(fig)

    # --- Plot 2: Cumulative rules (should be concave for sub-linearity) ---
    fig, ax = plt.subplots(figsize=(8, 5))
    cum_rules = [e['cumulative_rules'] for e in log]
    ax.plot(idxs, cum_rules, 'o-', color='#3498db', linewidth=2)
    ax.set_xlabel('Paper Index')
    ax.set_ylabel('Cumulative Compiled Patterns')
    ax.set_title('Cumulative Rules Growth')
    ax.set_xticks(idxs)
    ax.set_xticklabels(papers, rotation=45, ha='right')
    fig.tight_layout()
    fig.savefig(out_dir / 'cumulative_rules.png', dpi=150)
    plt.close(fig)

    # --- Plot 3: Cost per paper ---
    fig, ax = plt.subplots(figsize=(8, 5))
    analyze_cost = [e['analyze_cost_usd'] for e in log]
    agg_cost = [e['aggregate_cost_usd'] for e in log]
    ax.bar(idxs, analyze_cost, label='Analyze', color='#f39c12')
    ax.bar(idxs, agg_cost, bottom=analyze_cost, label='Aggregate', color='#9b59b6')
    ax.set_xlabel('Paper Index')
    ax.set_ylabel('Cost (USD)')
    ax.set_title('LLM Cost per Paper')
    ax.set_xticks(idxs)
    ax.set_xticklabels(papers, rotation=45, ha='right')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / 'cost_per_paper.png', dpi=150)
    plt.close(fig)

    # --- Plot 4: F1 progression ---
    fig, ax = plt.subplots(figsize=(10, 5))
    baseline_f1 = [e['baseline_f1'] for e in log]
    post_f1 = [e['post_f1'] for e in log]
    x = range(len(papers))
    width = 0.35
    ax.bar([i - width/2 for i in x], baseline_f1, width, label='Baseline F1',
           color='#bdc3c7')
    ax.bar([i + width/2 for i in x], post_f1, width, label='Post-distill F1',
           color='#2ecc71')
    ax.set_xlabel('Paper')
    ax.set_ylabel('F1 Score')
    ax.set_title('F1 Before vs After Distillation')
    ax.set_xticks(list(x))
    ax.set_xticklabels(papers, rotation=45, ha='right')
    ax.legend()
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    fig.savefig(out_dir / 'f1_progression.png', dpi=150)
    plt.close(fig)

    # --- Plot 5: Time per paper ---
    fig, ax = plt.subplots(figsize=(8, 5))
    times = [e['wall_time_seconds'] for e in log]
    ax.bar(idxs, times, color='#1abc9c')
    ax.set_xlabel('Paper Index')
    ax.set_ylabel('Wall-clock time (s)')
    ax.set_title('Time per Paper')
    ax.set_xticks(idxs)
    ax.set_xticklabels(papers, rotation=45, ha='right')
    fig.tight_layout()
    fig.savefig(out_dir / 'time_per_paper.png', dpi=150)
    plt.close(fig)

    print(f"\n  Plots saved to {out_dir}/")


# ---------------------------------------------------------------------------
# Verbose digest — read-only consumer of artifacts the pipeline already writes
# (cumulative_analyze.csv, distilled_rules.py, iteration_log.json). No LLM, no
# re-running of rules; purely renders what is already on disk.
# ---------------------------------------------------------------------------

def _trunc(s: str, n: int = 400) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")


def load_analyze_rows(eval_dir: Path) -> list[dict]:
    """Load cumulative_analyze.csv (one row per missed/dark-knowledge item)."""
    path = eval_dir / "cumulative_analyze.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_distilled_rules(eval_dir: Path) -> tuple[list[str], list[tuple]]:
    """Return (active_pattern_names, pruned[(var, marker_text)]) from the file.

    Reads the `# PRUNED — FP on ...` markers the prune step already wrote, so we
    surface which rules were dropped (and why) without re-running anything.
    """
    path = eval_dir / "distilled_rules.py"
    if not path.exists():
        return [], []
    lines = path.read_text(encoding="utf-8").splitlines()
    active, pruned = [], []
    for i, line in enumerate(lines):
        s = line.strip()
        m = re.match(r"^([A-Za-z_]\w*)\s*=\s*re\.compile\(", s)
        if m:
            active.append(m.group(1))
        if s.startswith("# PRUNED"):
            marker = s.lstrip("# ").strip()
            var = None
            for j in range(i + 1, min(i + 5, len(lines))):
                mm = re.match(r"^#\s*([A-Za-z_]\w*)\s*=\s*re\.compile\(",
                              lines[j].strip())
                if mm:
                    var = mm.group(1)
                    break
            pruned.append((var, marker))
    return active, pruned


def build_digest(eval_dir: Path, log: list[dict], out_path: Path,
                 extra: str = ""):
    """Write a human-readable markdown digest from existing run artifacts."""
    rows = load_analyze_rows(eval_dir)
    by_paper: dict[str, list[dict]] = {}
    for r in rows:
        by_paper.setdefault(r.get("paper_id", "?"), []).append(r)

    active, pruned = parse_distilled_rules(eval_dir)
    f1_by_paper = {e["paper_id"]: e for e in log}

    out = ["# Silver Distillation Digest (from outputs)\n",
           f"_Generated read-only from `{eval_dir.name}/` "
           f"(cumulative_analyze.csv, distilled_rules.py, iteration_log.json)._\n"]

    # Order papers by the iteration log, then any extras seen in the CSV.
    ordered = [e["paper_id"] for e in log] + [
        p for p in by_paper if p not in {e["paper_id"] for e in log}]
    for pid in ordered:
        e = f1_by_paper.get(pid, {})
        hdr = f"\n## {pid}"
        if e:
            hdr += (f"  (F1 {e.get('baseline_f1', '?')} → {e.get('post_f1', '?')}, "
                    f"new FNs {e.get('new_fns_to_distill', '?')}, "
                    f"cost ${e.get('total_cost_usd', 0):.4f})")
        out.append(hdr + "\n")

        items = by_paper.get(pid, [])
        out.append(f"\n### Dark-knowledge FNs ({len(items)}) — gold the rules "
                   f"missed but opus caught\n")
        if not items:
            out.append("_No analyze rows recorded for this paper._\n")
        for r in items:
            gi = r.get("gold_index", "?")
            ptype = r.get("pattern_type", "")
            out.append(f"\n**Gold[{gi}]**"
                       f"{f' ({ptype})' if ptype else ''}: "
                       f"{_trunc(r.get('gold_text'))}\n")
            reasoning = (r.get("llm_reasoning") or "").strip()
            rule = (r.get("llm_suggested_rule") or "").strip()
            if reasoning:
                out.append(f"  - _Why missed / approach:_ {_trunc(reasoning, 600)}\n")
            if rule:
                out.append(f"  - _Suggested rule:_\n\n```python\n{rule[:900]}\n```\n")
            else:
                out.append("  - _No rule suggested (e.g. tex_not_found)._\n")

    # Rules section — global (the distilled file is shared across papers).
    out.append(f"\n## Distilled rules in `distilled_rules.py`\n")
    out.append(f"\n- **Compiled patterns defined ({len(active)}):** "
               f"{', '.join(f'`{a}`' for a in active) if active else '_none_'}\n")
    out.append(f"\n- **Pruned patterns ({len(pruned)})** "
               f"(from `# PRUNED` markers — rule, then why):\n")
    if not pruned:
        out.append("  _No `# PRUNED` markers found. NOTE: absence of markers does "
                   "NOT guarantee nothing was pruned — the prune step only writes a "
                   "marker when the compiled variable name matches the result's "
                   "`rule_name`. FP details and prune decisions are printed to the "
                   "console at run time and are not persisted in this file._\n")
    for var, marker in pruned:
        out.append(f"  - `{var or '?'}` — {marker}\n")

    if extra:
        out.append(extra)

    out_path.write_text("".join(out), encoding="utf-8")
    print(f"\n  Verbose digest: {out_path}")


# ---------------------------------------------------------------------------
# Opt-in FP re-derivation — runs the ALREADY-GENERATED distilled_rules.py
# against the gold (deterministic, no LLM, no change to generation). Recovers
# the FP snippets + prune decisions that the run only printed to the console.
# ---------------------------------------------------------------------------

def _silver_matcher(metric: str):
    """Replicate the pipeline's clean+token matcher (containment for silver)."""
    from latex_clean import clean_latex_to_text
    import distillation_analysis as da

    def sim(a: str, b: str) -> float:
        t1 = da.tokenize_latex(clean_latex_to_text(a or "").lower())
        t2 = da.tokenize_latex(clean_latex_to_text(b or "").lower())
        if not t1 or not t2:
            return 0.0
        inter = len(t1 & t2)
        if metric == "containment":
            return inter / min(len(t1), len(t2))
        return inter / len(t1 | t2)
    return sim


def _find_main_tex(src_dir: Path):
    if not src_dir.exists():
        return None
    tex_files = sorted(src_dir.glob("*.tex"))
    if not tex_files:
        return None
    for tf in tex_files:
        try:
            if r"\documentclass" in tf.read_text(encoding="utf-8", errors="replace")[:8000]:
                return tf
        except OSError:
            continue
    return tex_files[0]


def rederive_fp_section(eval_dir: Path, tex_dir: Path, structure_type: str,
                        threshold: float, alpha: float, metric: str) -> str:
    """Return a markdown section attributing FPs/TPs to each distilled rule.

    Read-only: imports and runs the existing distilled_rules.py; classifies its
    output against the silver gold exactly like the prune step does, but without
    modifying anything.
    """
    import importlib.util
    from collections import defaultdict
    from distillation_analysis import _load_gold_csv

    rules_path = eval_dir / "distilled_rules.py"
    if not rules_path.exists():
        return "\n## FP re-derivation\n_No distilled_rules.py found._\n"
    gold_files = list((eval_dir / "silver_gold").glob("Gold_Standard_*.csv"))
    if not gold_files:
        return "\n## FP re-derivation\n_No silver_gold CSV found._\n"
    gold_data = _load_gold_csv(str(gold_files[0]))

    # Import the distilled module defensively (bad LLM codegen shouldn't crash us).
    spec = importlib.util.spec_from_file_location("distilled_rederive", rules_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        return (f"\n## FP re-derivation\n_distilled_rules.py failed to import "
                f"({type(e).__name__}: {e})._\n")
    extract_fn = getattr(mod, f"extract_distilled_{structure_type}", None)
    if extract_fn is None:
        return "\n## FP re-derivation\n_extract function not found in module._\n"

    sim = _silver_matcher(metric)
    fp_by_rule: dict[str, list[dict]] = defaultdict(list)
    tp_by_rule: dict[str, list[str]] = defaultdict(list)

    for pid in sorted(gold_data.keys()):
        main_tex = _find_main_tex(tex_dir / pid / "source")
        if main_tex is None:
            continue
        text = main_tex.read_text(encoding="utf-8", errors="replace")
        try:
            results = extract_fn(text)
        except Exception as e:
            return (f"\n## FP re-derivation\n_distilled extract raised on {pid} "
                    f"({type(e).__name__}: {e})._\n")
        extracted = [r.get("raw_latex", "") for r in results]
        gold_texts = [g["raw_latex"] or g["clean_text"]
                      for g in gold_data.get(pid, [])
                      if (g.get("raw_latex") or g.get("clean_text", "")).strip()]

        pairs = []
        for ei, e in enumerate(extracted):
            for gi, g in enumerate(gold_texts):
                if sim(e, g) >= threshold:
                    pairs.append((sim(e, g), ei, gi))
        pairs.sort(reverse=True)
        matched_ext, matched_gold = set(), set()
        for s, ei, gi in pairs:
            if ei not in matched_ext and gi not in matched_gold:
                matched_ext.add(ei)
                matched_gold.add(gi)
        for ei, r in enumerate(results):
            rule = r.get("rule_name", "?")
            if ei in matched_ext:
                tp_by_rule[rule].append(pid)
            else:
                snip = (r.get("raw_latex", "") or "").strip().replace("\n", " ")
                fp_by_rule[rule].append({"paper_id": pid, "text": snip[:200]})

    out = [f"\n## FP re-derivation (alpha={alpha:.2f}, metric={metric})\n",
           "_Computed by re-running the existing distilled rules against gold "
           "(no LLM). A rule would be pruned when FP/(FP+TP) > alpha._\n"]
    all_rules = sorted(set(fp_by_rule) | set(tp_by_rule))
    touched = [r for r in all_rules if fp_by_rule.get(r)]
    out.append(f"\n**Rules producing FPs: {len(touched)} of {len(all_rules)} "
               f"that fired.**\n")
    for rule in all_rules:
        fps = fp_by_rule.get(rule, [])
        tpc = len(tp_by_rule.get(rule, []))
        fpc = len(fps)
        if fpc == 0:
            continue
        fdr = fpc / (fpc + tpc)
        status = "🔴 would PRUNE" if fdr > alpha else "🟢 would keep"
        out.append(f"\n- `{rule}` — FDR {fdr:.2f} ({fpc} FP / {tpc} TP) — {status}\n")
        for ex in fps[:3]:
            out.append(f"    - FP @ {ex['paper_id']}: {ex['text']}\n")
    clean_rules = [r for r in all_rules if not fp_by_rule.get(r)]
    if clean_rules:
        out.append(f"\n**Clean rules (TP only, no FPs):** "
                   f"{', '.join(f'`{r}`' for r in clean_rules)}\n")
    return "".join(out)


def main():
    p = argparse.ArgumentParser(description="Silver Distillation Report")
    p.add_argument("--log", required=True,
                   help="Path to iteration_log.json")
    p.add_argument("--out-dir", default=None,
                   help="Output dir for plots (default: same dir as log)")
    p.add_argument("--digest-out", default=None,
                   help="Path for the verbose markdown digest "
                        "(default: distill_digest.md beside the log)")
    p.add_argument("--rederive-fps", action="store_true",
                   help="Also re-run the existing distilled_rules.py against the "
                        "gold (deterministic, no LLM) to recover FP snippets + "
                        "prune decisions that were only printed at run time. "
                        "Requires --tex-dir.")
    p.add_argument("--tex-dir", default=None,
                   help="paper*/source/*.tex root (needed for --rederive-fps)")
    p.add_argument("--structure-type", default="definition",
                   help="Structure type (for --rederive-fps; default definition)")
    p.add_argument("--threshold", type=float, default=0.7,
                   help="Match threshold for --rederive-fps (default 0.7)")
    p.add_argument("--prune-alpha", type=float, default=0.5,
                   help="FDR alpha to show would-prune decisions (default 0.5)")
    p.add_argument("--match-metric", default="containment",
                   choices=["jaccard", "containment"],
                   help="Matcher for --rederive-fps (default containment)")
    args = p.parse_args()

    log = load_log(args.log)
    if not log:
        print("Empty log — nothing to report.")
        sys.exit(0)

    out_dir = Path(args.out_dir) if args.out_dir else Path(args.log).parent / "silver_report"

    print_summary_table(log)
    print_cost_table(log)
    print_sublinearity(log)
    plot_all(log, out_dir)

    # Verbose digest from existing artifacts (no LLM, no re-running rules).
    eval_dir = Path(args.log).parent
    digest_path = Path(args.digest_out) if args.digest_out else eval_dir / "distill_digest.md"

    extra = ""
    if args.rederive_fps:
        if not args.tex_dir:
            print("  [skip] --rederive-fps needs --tex-dir")
        else:
            extra = rederive_fp_section(
                eval_dir, Path(args.tex_dir), args.structure_type,
                args.threshold, args.prune_alpha, args.match_metric)
    build_digest(eval_dir, log, digest_path, extra=extra)


if __name__ == "__main__":
    main()
