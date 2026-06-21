#!/usr/bin/env python3
"""Consolidated distillation results report (read-only).
Pulls iteration_log.json + final_eval.csv + per-group cumulative_analyze.csv +
distilled_rules.py into a single <eval_dir>/REPORT.md. No LLM, no parsing.

Usage:
    python scripts/make_distill_report.py --eval-dir <dir>
"""
import argparse
import csv
import glob
import json
import os
import re
from collections import Counter
from pathlib import Path


def build_report(eval_dir):
    eval_dir = Path(eval_dir)
    out = eval_dir / "REPORT.md"
    L = []
    def w(s=""):
        L.append(s)

    log = json.load(open(eval_dir / "iteration_log.json", encoding="utf-8"))
    w("# Silver Merged Distillation — Results Report")
    w(f"\n_eval-dir: `{eval_dir}` · papers: {len(log)} · "
      f"generated read-only from existing artifacts_\n")
    tot_calls = sum(e.get("total_llm_calls", 0) for e in log)
    tot_cost = sum(e.get("total_cost_usd", 0) for e in log)
    w("## 1. Run summary\n")
    w(f"- Papers: {', '.join(e['paper_id'] for e in log)}")
    w(f"- Total LLM calls: {tot_calls}  ·  Total cost: ${tot_cost:.4f}  ·  "
      f"Avg ${tot_cost/len(log):.4f}/paper" if log else "- (no papers)")
    w("- LLM steps per group: 2 (analyze + aggregate); "
      "identify-dark-knowledge & prune are deterministic\n")
    w("| paper | total FNs | new FNs | cum. rules | calls (a+agg) | cost | "
      "F1 base | F1 post |")
    w("|---|---|---|---|---|---|---|---|")
    for e in log:
        w(f"| {e['paper_id']} | {e.get('total_fns','?')} | "
          f"{e.get('new_fns_to_distill','?')} | {e.get('cumulative_rules','?')} | "
          f"{e.get('total_llm_calls','?')} "
          f"({e.get('analyze_llm_calls','?')}+{e.get('aggregate_llm_calls','?')}) | "
          f"${e.get('total_cost_usd',0):.4f} | {e.get('baseline_f1',0):.3f} | "
          f"{e.get('post_f1',0):.3f} |")

    w("\n## 2. Final per-type F1 (containment matching)\n")
    fe = eval_dir / "final_eval.csv"
    if fe.exists():
        rows = list(csv.DictReader(open(fe, encoding="utf-8")))
        cols = list(rows[0].keys()) if rows else []
        w("| " + " | ".join(cols) + " |")
        w("|" + "---|" * len(cols))
        for r in rows:
            w("| " + " | ".join(str(r[c]) for c in cols) + " |")
    else:
        w("_final_eval.csv not found (run scripts/final_eval.py)_")

    # Adjusted precision from the FP-judge, if present.
    fj = eval_dir / "fp_judge.csv"
    if fj.exists():
        jr = list(csv.DictReader(open(fj, encoding="utf-8")))
        by = Counter((r["type"], r["verdict"]) for r in jr)
        w("\n## 2b. LLM-judge FP adjustment\n")
        w("| type | judged FP | GENUINE (rescued) | real FP |")
        w("|---|---|---|---|")
        for t in sorted({r["type"] for r in jr}):
            g = by[(t, "GENUINE")]; real = sum(v for (tt, vv), v in by.items()
                                               if tt == t and vv != "GENUINE")
            w(f"| {t} | {g+real} | {g} | {real} |")

    w("\n## 3. Per-group breakdown\n")
    for g in sorted(glob.glob(str(eval_dir / "groups" / "*"))):
        gk = os.path.basename(g)
        rules_py = Path(g) / "distilled_rules.py"
        analyze = Path(g) / "cumulative_analyze.csv"
        src = rules_py.read_text(encoding="utf-8") if rules_py.exists() else ""
        active = re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*re\.compile\(", src, re.M)
        pruned = re.findall(r"#\s*PRUNED — (.+)", src)
        arows = list(csv.DictReader(open(analyze, encoding="utf-8"))) if analyze.exists() else []
        bytype = Counter(r.get("structure_type", "") for r in arows)
        w(f"### {gk}")
        w(f"- active patterns: {len(active)}  ·  pruned: {len(pruned)}  ·  "
          f"FNs analyzed: {len(arows)} {dict(bytype)}")
        if pruned:
            w("- PRUNED rules:")
            for pr in pruned:
                w(f"  - {pr}")
        w("")

    w("\n## 4. FN-level detail (what each group learned from)\n")
    for g in sorted(glob.glob(str(eval_dir / "groups" / "*"))):
        gk = os.path.basename(g)
        analyze = Path(g) / "cumulative_analyze.csv"
        if not analyze.exists():
            continue
        arows = list(csv.DictReader(open(analyze, encoding="utf-8")))
        if not arows:
            continue
        w(f"### {gk} ({len(arows)} items)\n")
        for r in arows:
            gt = (r.get("gold_text", "") or "").strip().replace("\n", " ")[:160]
            rs = (r.get("llm_reasoning", "") or "").strip().replace("\n", " ")[:220]
            rule = (r.get("llm_suggested_rule", "") or "").strip().replace("\n", " ")[:160]
            w(f"- **{r.get('paper_id','?')} / {r.get('structure_type','?')}** — `{gt}`")
            if rs:
                w(f"  - why missed: {rs}")
            if rule:
                w(f"  - suggested: `{rule}`")
        w("")

    out.write_text("\n".join(L), encoding="utf-8")
    return out


def main():
    p = argparse.ArgumentParser(description="Consolidated distillation report")
    p.add_argument("--eval-dir", required=True)
    args = p.parse_args()
    out = build_report(args.eval_dir)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
