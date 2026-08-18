#!/usr/bin/env python3
"""Final-rules re-evaluation
=============================
Scores every distilled paper with the FINAL accumulated rule set (the last
snapshot) AND the no-rules baseline (step_00), against the silver gold — so all
papers are compared on the SAME rule set, unlike iteration_log's post_f1 (which
uses cumulative-so-far rules, different per paper).

For each paper reports per-type F1 plus two overall means:
  all9     = macro mean over all 9 types (absent types count as 0; matches the
             iteration_log convention)
  present  = macro mean over only types with gold (no absent-type deflation)

No LLM calls — pure regex parse + matching.

Usage:
    python scripts/final_eval.py \
        --eval-dir src/LLMVersion/merged_eval_silver_001_011 \
        --tex-dir /Users/yaronot/Datasets/Authomathics_data/alignment/papers \
        --match-metric containment
"""

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import silver_distillation_sequential as seq
import silver_distillation_merged as merged
from silver_distillation_merged import (FNAME_MAP, parse_buckets, metrics,
                                        load_gold_texts)


def overall(per_type: dict):
    """Return (all9_macro, present_macro) from {type: metrics-dict}."""
    f1s = [m['f1'] for m in per_type.values()]
    present = [m['f1'] for m in per_type.values() if m['n_gold'] > 0]
    all9 = sum(f1s) / len(f1s) if f1s else 0.0
    pres = sum(present) / len(present) if present else 0.0
    return all9, pres


def _f1_from(c: dict) -> dict:
    """Rebuild a metrics-shaped dict from recorded integer counts.

    Recomputed rather than read back as a float: the stored floats are rounded
    on write, and a derived number that differs from the parsed one in the
    third decimal is worse than useless — neither can then check the other.
    """
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    tpr = c.get("tp_recall", tp)
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tpr / (tpr + fn) if (tpr + fn) else 0.0
    return {"tp": tp, "tp_recall": tpr, "fp": fp, "fn": fn,
            "n_gold": c.get("n_gold", 0), "precision": p, "recall": r,
            "f1": 2 * p * r / (p + r) if (p + r) else 0.0}


def load_recorded(eval_dir: Path, papers, types, metric, threshold):
    """{state: {paper: {type: counts}}} from trajectory/scores.jsonl, m1 only.

    Returns None unless the file covers every state and paper this script
    needs, under the same scoring parameters. final_eval scores in m1 with no
    cross-type support, so only m1 rows are eligible; cover is irrelevant to m1
    and deliberately not checked.

    The states map onto the run like this:
      base      -> the no-rules baseline (step_00)
      after i   -> the rules in effect AFTER the i-th paper, which is also the
                   state in effect JUST BEFORE paper i+1 was distilled
    so 'rules so far' for papers[i] is 'base' when i == 0 and 'after i'
    otherwise, and FINAL is 'after len(papers)'.
    """
    path = eval_dir / "trajectory" / "scores.jsonl"
    if not path.exists():
        return None
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("mode") != "m1" or not r.get("per_type"):
                continue
            if r.get("metric") != metric or r.get("threshold") != threshold:
                continue
            out.setdefault(r["state"], {})[r["paper_id"]] = r["per_type"]
    need = ["base"] + [f"after {i}" for i in range(1, len(papers) + 1)]
    for st in need:
        if st not in out:
            return None
        for pid in papers:
            row = out[st].get(pid)
            if not row or any(t not in row for t in types):
                return None
    return out


def main():
    p = argparse.ArgumentParser(description="Final-rules re-evaluation")
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--match-metric", default="containment",
                   choices=["jaccard", "containment"])
    p.add_argument("--final-snapshot", default=None,
                   help="Snapshot dir name to treat as FINAL (default: highest step_NN)")
    p.add_argument("--no-cache", action="store_true",
                   help="ignore trajectory/scores.jsonl and re-parse every "
                        "paper. Slower, and the two paths are verified to "
                        "agree — use it to re-verify that, or when the "
                        "snapshots have changed under a stale scores file.")
    args = p.parse_args()

    eval_dir = Path(args.eval_dir).resolve()
    tex_dir = Path(args.tex_dir).resolve()
    gold_dir = eval_dir / "silver_gold"
    seq.set_match_metric(args.match_metric)

    types = list(FNAME_MAP.keys())
    snaps = sorted((eval_dir / "snapshots").glob("step_*"))
    if not snaps:
        print(f"ERROR: no snapshots under {eval_dir/'snapshots'}")
        sys.exit(1)
    step00 = next((s for s in snaps if s.name.startswith("step_00")), None)
    final = (eval_dir / "snapshots" / args.final_snapshot) if args.final_snapshot \
        else snaps[-1]
    print(f"Baseline snapshot: {step00.name if step00 else '(none)'}")
    print(f"Final snapshot:    {final.name}")

    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}
    # Papers = those that appear in the iteration log (the distilled set).
    log = json.load(open(eval_dir / "iteration_log.json", encoding="utf-8"))
    papers = [e['paper_id'] for e in log]

    rows = []
    # Pooled (node-level) TP/FP/FN for the clean step_00 baseline vs final rules,
    # so the report's headline P/R/F1 isn't a deflated per-type macro and isn't
    # contaminated by prior rules (as iteration_log baselines are on a resume).
    pooled = {'base': {'tp': 0, 'fp': 0, 'fn': 0},
              'final': {'tp': 0, 'fp': 0, 'fn': 0}}
    # Snapshots in processing order: snaps[0]=step_00 (no rules), snaps[i+1]=after
    # the i-th distilled paper. So the rules in effect JUST BEFORE papers[i] was
    # distilled live in snaps[i] — used for the "FN with rules so far" column.
    print(f"\n{'Paper':<10} | {'baseline all9/present':<22} | {'FINAL all9/present':<20} | per-type FINAL f1 (gold>0)")
    print("-" * 110)
    # The run records these scores itself (--score-every), and this script's
    # three parses per paper are then pure recomputation: 'base' and the
    # per-paper 'rules so far' state were both already parsed during the run
    # and thrown away. Derive when we can; parse only when we must.
    rec = None if args.no_cache else load_recorded(
        eval_dir, papers, types, args.match_metric, args.threshold)
    if rec is not None:
        print(f"Source: trajectory/scores.jsonl (recorded by the run, no reparse)")
    else:
        print("Source: re-parsing (no usable recorded scores)")

    for i, pid in enumerate(papers):
        if rec is not None:
            sofar_state = "base" if i == 0 else f"after {i}"
            base_m = {t: _f1_from(rec["base"][pid][t]) for t in types}
            sofar_m = {t: _f1_from(rec[sofar_state][pid][t]) for t in types}
            fin_m = {t: _f1_from(rec[f"after {len(papers)}"][pid][t])
                     for t in types}
        else:
            pre_snap = snaps[i] if i < len(snaps) else step00
            base_b = parse_buckets(pid, tex_dir, types, eval_dir=step00)
            sofar_b = parse_buckets(pid, tex_dir, types, eval_dir=pre_snap)
            fin_b = parse_buckets(pid, tex_dir, types, eval_dir=final)
            base_m = {t: metrics(base_b[t], gold[t].get(pid, []), args.threshold) for t in types}
            sofar_m = {t: metrics(sofar_b[t], gold[t].get(pid, []), args.threshold) for t in types}
            fin_m = {t: metrics(fin_b[t], gold[t].get(pid, []), args.threshold) for t in types}
        for t in types:
            for k in ('tp', 'fp', 'fn'):
                pooled['base'][k] += base_m[t][k]
                pooled['final'][k] += fin_m[t][k]
        # FN gap (gold missed), summed over types: no rules vs rules-accumulated-
        # before-this-paper. Same metrics() method, so paper 1 (no prior rules)
        # has fn_base == fn_sofar by construction.
        fn_base = sum(base_m[t]['fn'] for t in types)
        fn_sofar = sum(sofar_m[t]['fn'] for t in types)
        b9, bp = overall(base_m)
        f9, fp = overall(fin_m)
        present_str = "  ".join(f"{t[:3]}={fin_m[t]['f1']:.2f}"
                                for t in types if fin_m[t]['n_gold'] > 0)
        print(f"{pid:<10} | {b9:.3f} / {bp:.3f}{'':<8} | {f9:.3f} / {fp:.3f}{'':<6} | {present_str}")
        rows.append({'paper_id': pid,
                     'fn_base': fn_base, 'fn_sofar': fn_sofar,
                     'baseline_all9': round(b9, 4), 'baseline_present': round(bp, 4),
                     'final_all9': round(f9, 4), 'final_present': round(fp, 4),
                     **{f'final_f1_{t}': round(fin_m[t]['f1'], 4) for t in types},
                     **{f'final_gold_{t}': fin_m[t]['n_gold'] for t in types},
                     **{f'final_fp_{t}': fin_m[t]['fp'] for t in types}})

    # Corpus means.
    def col(k):
        return sum(r[k] for r in rows) / len(rows) if rows else 0.0
    print("-" * 110)
    print(f"{'MEAN':<10} | {col('baseline_all9'):.3f} / {col('baseline_present'):.3f}"
          f"{'':<8} | {col('final_all9'):.3f} / {col('final_present'):.3f}")

    out = eval_dir / "final_eval.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out}")

    # Pooled clean base vs final counts for the report's headline table.
    pjson = eval_dir / "pooled_stages.json"
    json.dump(pooled, open(pjson, "w", encoding="utf-8"), indent=2)
    print(f"Wrote {pjson}")


if __name__ == "__main__":
    main()
