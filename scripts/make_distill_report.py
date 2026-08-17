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


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def pooled_stages(eval_dir, log):
    """Pooled (node-level) TP/FP/FN + P/R/F1 for the three stages that matter:
    base (no distilled rules), post-distillation (final rule set), and
    post-LLM-judge (spurious FPs the judge ruled were silver under-labeling are
    removed; recall is unchanged because the judge only inspects FPs).

    Sources: base + post from pooled_stages.json (clean step_00 vs final rule
    set, written by final_eval.py — exact integer counts, not contaminated by
    prior rules as iteration_log baselines are on a resume); judge from
    fp_judge.csv (GENUINE = rescued FP). Returns list of (label, tp, fp, fn).
    """
    btp = bfp = bfn = 0
    ptp = pfp = pfn = None

    pj = eval_dir / "pooled_stages.json"
    if pj.exists():
        ps = json.load(open(pj, encoding="utf-8"))
        b, p = ps["base"], ps["final"]
        btp, bfp, bfn = b["tp"], b["fp"], b["fn"]
        ptp, pfp, pfn = p["tp"], p["fp"], p["fn"]
    else:
        # Fallback (older runs without pooled_stages.json): iteration_log
        # baseline + final_eval.csv f1-inversion. NOTE: base is contaminated on
        # resume runs — rerun scripts/final_eval.py to get the clean headline.
        for e in log:
            for d in e.get("per_type", {}).values():
                bb = d.get("baseline", {})
                btp += bb.get("tp", 0); bfp += bb.get("fp", 0); bfn += bb.get("fn", 0)
        fe = eval_dir / "final_eval.csv"
        if fe.exists():
            rows = list(csv.DictReader(open(fe, encoding="utf-8")))
            types = [c[len("final_f1_"):] for c in (rows[0] if rows else {})
                     if c.startswith("final_f1_")]
            ptp = 0; pfp = 0; total_gold = 0
            for r in rows:
                for t in types:
                    f1 = float(r[f"final_f1_{t}"]); gold = int(r[f"final_gold_{t}"])
                    fp = int(r[f"final_fp_{t}"])
                    total_gold += gold; pfp += fp
                    ptp += round(f1 * (fp + gold) / (2 - f1)) if f1 > 0 else 0
            pfn = total_gold - ptp

    # --- judge: remove rescued (GENUINE) FPs; TP/FN unchanged ---
    jtp = jfp = jfn = None
    fj = eval_dir / "fp_judge.csv"
    if fj.exists() and ptp is not None:
        jr = list(csv.DictReader(open(fj, encoding="utf-8")))
        rescued = sum(1 for x in jr if x.get("verdict") == "GENUINE")
        jtp, jfp, jfn = ptp, max(pfp - rescued, 0), pfn

    stages = [("Base (no distilled rules)", btp, bfp, bfn)]
    if ptp is not None:
        stages.append(("Post-distillation (final rules)", ptp, pfp, pfn))
    if jtp is not None:
        stages.append(("Post-LLM-judge (spurious FPs removed)", jtp, jfp, jfn))
    return stages


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

    # ---- Headline: pooled (node-level) P/R/F1 across the three stages ----
    w("## 0. Headline — pooled P/R/F1 (base → distillation → LLM-judge)\n")
    w("_Pooled over every node in all papers (not a per-type macro), so it is "
      "not deflated by sparse/absent types. The judge corrects precision only "
      "(rescues FPs that were silver under-labeling); it cannot change recall._\n")
    w("| stage | TP | FP | FN | precision | recall | F1 |")
    w("|---|---|---|---|---|---|---|")
    for label, tp, fp, fn in pooled_stages(eval_dir, log):
        p, r, f = _prf(tp, fp, fn)
        w(f"| {label} | {tp} | {fp} | {fn} | {p:.3f} | {r:.3f} | {f:.3f} |")
    w("")

    # ---- Metric ladder, if the finalize step produced one ----
    # Written by eval_metric_ladder.py --markdown. Absent when --skip-ladder was
    # used or the ladder failed; the report stays valid either way.
    ladder = eval_dir / "metric_ladder.md"
    if ladder.is_file():
        w(ladder.read_text(encoding="utf-8").rstrip())
        w("")

    tot_calls = sum(e.get("total_llm_calls", 0) for e in log)
    tot_cost = sum(e.get("total_cost_usd", 0) for e in log)
    w("## 1. Run summary\n")
    w(f"- Papers: {', '.join(e['paper_id'] for e in log)}")
    w(f"- Total LLM calls: {tot_calls}  ·  Total cost: ${tot_cost:.4f}  ·  "
      f"Avg ${tot_cost/len(log):.4f}/paper" if log else "- (no papers)")
    w("- LLM steps per group: 2 (analyze + aggregate); "
      "identify-dark-knowledge & prune are deterministic\n")
    # FN gap per paper: with ZERO rules vs with the rules accumulated BEFORE this
    # paper was distilled (both from final_eval.csv, same matcher). Shows
    # dark-knowledge transfer — for later papers, prior rules already shrink the
    # gap before we learn anything new (paper 1 has no prior rules, so equal).
    # F1 base/post columns dropped: they were a macro over ALL types (absent
    # counted 0), deflated and misleading — read §0 for the real P/R/F1.
    fe_fn = {}
    fe = eval_dir / "final_eval.csv"
    if fe.exists():
        for r in csv.DictReader(open(fe, encoding="utf-8")):
            if "fn_base" in r and "fn_sofar" in r:
                fe_fn[r["paper_id"]] = (r["fn_base"], r["fn_sofar"])
    w("| paper | FN (no rules) | FN (rules so far) | cum. rules | calls (a+agg) | cost |")
    w("|---|---|---|---|---|---|")
    for e in log:
        fnb, fns = fe_fn.get(e['paper_id'], (e.get('total_fns', '?'), e.get('total_fns', '?')))
        w(f"| {e['paper_id']} | {fnb} | {fns} | {e.get('cumulative_rules','?')} | "
          f"{e.get('total_llm_calls','?')} "
          f"({e.get('analyze_llm_calls','?')}+{e.get('aggregate_llm_calls','?')}) | "
          f"${e.get('total_cost_usd',0):.4f} |")

    w("\n## 2. Final per-type F1 (containment matching)\n")
    w("_Per-paper diagnostic detail. `present` = macro over only the types that "
      "appear in that paper; `all9` counts absent types as 0 (deflated — ignore "
      "for quality). Use this table to spot which specific types are weak, not "
      "for the headline number (that's §0)._\n")
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
