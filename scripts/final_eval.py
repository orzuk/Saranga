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


def main():
    p = argparse.ArgumentParser(description="Final-rules re-evaluation")
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--match-metric", default="containment",
                   choices=["jaccard", "containment"])
    p.add_argument("--final-snapshot", default=None,
                   help="Snapshot dir name to treat as FINAL (default: highest step_NN)")
    args = p.parse_args()

    eval_dir = Path(args.eval_dir).resolve()
    tex_dir = Path(args.tex_dir).resolve()
    gold_dir = eval_dir / "silver_gold"
    seq._MATCH_METRIC = args.match_metric

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
    print(f"\n{'Paper':<10} | {'baseline all9/present':<22} | {'FINAL all9/present':<20} | per-type FINAL f1 (gold>0)")
    print("-" * 110)
    for pid in papers:
        base_b = parse_buckets(pid, tex_dir, types, eval_dir=step00)
        fin_b = parse_buckets(pid, tex_dir, types, eval_dir=final)
        base_m = {t: metrics(base_b[t], gold[t].get(pid, []), args.threshold) for t in types}
        fin_m = {t: metrics(fin_b[t], gold[t].get(pid, []), args.threshold) for t in types}
        b9, bp = overall(base_m)
        f9, fp = overall(fin_m)
        present_str = "  ".join(f"{t[:3]}={fin_m[t]['f1']:.2f}"
                                for t in types if fin_m[t]['n_gold'] > 0)
        print(f"{pid:<10} | {b9:.3f} / {bp:.3f}{'':<8} | {f9:.3f} / {fp:.3f}{'':<6} | {present_str}")
        rows.append({'paper_id': pid,
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


if __name__ == "__main__":
    main()
