#!/usr/bin/env python3
"""Audit what the BASE parser's false positives actually are (no LLM, no distillation).

Step 1-3 of the "repair the corpus" plan: every span the base regex parser
extracts that the silver gold does not credit is a candidate silver gap. This
classifies each one so we know how much of the problem is mechanical
(reconcilable without a model) versus a real judging job.

Buckets, per FP:
  cross_type     the silver HAS this statement, filed under a different type
                 -> mechanical: a type-reconciliation / cross-type matcher fix
  boundary       best overlap in [partial_lo, threshold), same type
                 -> mechanical: span-boundary convention, matcher fix
  boundary_xtype best overlap in [partial_lo, threshold), different type
                 -> both problems at once
  dup_span       same-type gold already consumed by another extraction
                 -> dedup bug, not a labelling issue
  real_gap       nothing in the silver resembles it
                 -> the only bucket that actually needs an LLM judge

Usage:
    python scripts/silver_gap_audit.py \
        --cache <buckets_cache.json> --examples 6
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

import silver_distillation_sequential as seq
import distillation_analysis as da
from silver_distillation_sequential import FNAME_MAP
from silver_distillation_merged import load_gold_texts
from latex_clean import clean_latex_to_text

TYPES = list(FNAME_MAP.keys())


def _tok(s):
    return da.tokenize_latex(clean_latex_to_text(s or "").lower())


def greedy_matched(extracted, gold, threshold):
    pairs = []
    for i, e in enumerate(extracted):
        for j, g in enumerate(gold):
            s = seq.jaccard_similarity(e, g)
            if s >= threshold:
                pairs.append((s, i, j))
    pairs.sort(reverse=True)
    me, mg = set(), set()
    for s, i, j in pairs:
        if i in me or j in mg:
            continue
        me.add(i); mg.add(j)
    return me


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--gold-dir", default=None)
    ap.add_argument("--eval-dir", default="src/LLMVersion/merged_eval_silver_001_011_v3")
    ap.add_argument("--which", default="base", choices=["base", "final"])
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--partial-lo", type=float, default=0.4)
    ap.add_argument("--nest-ratio", type=float, default=3.0,
                    help="gold/extraction token ratio above which a containment "
                         "match is nesting (granularity), not type confusion")
    ap.add_argument("--match-metric", default="containment")
    ap.add_argument("--examples", type=int, default=6)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    seq.set_match_metric(args.match_metric)
    cache = json.load(open(args.cache, encoding="utf-8"))
    gold_dir = Path(args.gold_dir) if args.gold_dir else \
        (REPO / args.eval_dir).resolve() / "_split_eval" / "gold"
    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in TYPES}

    meta = {r["paper_id"]: r for r in
            csv.DictReader(open(REPO / "corpus/silver/metadata.csv", encoding="utf-8"))
            if r["prompt_version"] == "v4.1"}

    buckets = Counter()
    confusion = Counter()          # (rules_type, silver_type) -> n
    nesting = Counter()            # (rules_type, enclosing_gold_type) -> n
    by_group = defaultdict(Counter)
    gaps = []
    rows = []

    for pid, entry in cache.items():
        m = meta.get(pid)
        if not m:
            continue
        grp = "train" if m["split"] == "train" else f"test-{m['tier']}"
        all_gold = [(t, g) for t in TYPES for g in gold[t].get(pid, [])]

        for t in TYPES:
            texts = entry[args.which][t]
            g_own = gold[t].get(pid, [])
            matched = greedy_matched(texts, g_own, args.threshold)
            for i, ext in enumerate(texts):
                if i in matched:
                    continue
                # best overlap against gold of every type
                best_s, best_t, best_g = 0.0, None, ""
                best_same = 0.0
                for gt, g in all_gold:
                    s = seq.jaccard_similarity(ext, g)
                    if s > best_s:
                        best_s, best_t, best_g = s, gt, g
                    if gt == t and s > best_same:
                        best_same = s
                # Length ratio guards against the containment min() artifact: a
                # short span nested in a long gold node scores 1.0 by
                # construction, which is a GRANULARITY disagreement, not a type
                # disagreement. Only comparable-length spans are real type
                # confusion.
                n_ext = len(_tok(ext))
                n_gold = len(_tok(best_g))
                ratio = (n_gold / n_ext) if n_ext else 0.0
                nested = ratio >= args.nest_ratio
                if best_same >= args.threshold:
                    kind = "dup_span"
                elif best_s >= args.threshold:
                    if nested:
                        kind = "nested_in_" + ("same" if best_t == t else "other")
                        nesting[(t, best_t)] += 1
                    else:
                        kind = "cross_type"
                        confusion[(t, best_t)] += 1
                elif best_s >= args.partial_lo:
                    kind = "boundary" if best_t == t else "boundary_xtype"
                    if best_t != t:
                        confusion[(t, best_t)] += 1
                else:
                    kind = "real_gap"
                    if len(gaps) < args.examples:
                        gaps.append((pid, t, ext[:170].replace("\n", " ")))
                buckets[kind] += 1
                by_group[grp][kind] += 1
                rows.append({"paper_id": pid, "group": grp, "rules_type": t,
                             "kind": kind, "best_sim": round(best_s, 3),
                             "silver_type": best_t or "",
                             "snippet": ext[:300].replace("\n", " ")})

    total = sum(buckets.values())
    order = ["nested_in_other", "nested_in_same", "cross_type",
             "boundary_xtype", "boundary", "dup_span", "real_gap"]
    print(f"BASE-parser false positives ({args.which} rules), {len(cache)} papers")
    print(f"metric={args.match_metric} threshold={args.threshold} partial_lo={args.partial_lo}\n")
    print(f"{'bucket':<16} {'n':>5} {'share':>7}   fix")
    fixes = {"nested_in_other": "GRANULARITY - sub-span of a bigger gold node",
             "nested_in_same": "GRANULARITY - sub-span, same type",
             "cross_type": "mechanical - type reconciliation",
             "boundary_xtype": "mechanical - both type + span",
             "boundary": "mechanical - span-boundary convention",
             "dup_span": "code bug - dedup",
             "real_gap": "NEEDS LLM JUDGE"}
    for k in order:
        print(f"{k:<16} {buckets[k]:>5} {buckets[k]/total*100:>6.1f}%   {fixes[k]}")
    print(f"{'TOTAL':<16} {total:>5}")
    mech = buckets["cross_type"] + buckets["boundary"] + \
        buckets["boundary_xtype"] + buckets["dup_span"]
    gran = buckets["nested_in_other"] + buckets["nested_in_same"]
    print(f"\nmechanical (matcher/dedup fix)   : {mech}/{total} = {mech/total*100:.1f}%")
    print(f"granularity policy call (nested) : {gran}/{total} = {gran/total*100:.1f}%")
    print(f"real gap, needs a judge          : {buckets['real_gap']}/{total} = "
          f"{buckets['real_gap']/total*100:.1f}%")

    print(f"\nBy split")
    for grp in ["train", "test-B_math_shift", "test-A_matched_ML"]:
        d = by_group.get(grp)
        if not d:
            continue
        tot = sum(d.values())
        print(f"  {grp:<20} {tot:>5}  " +
              "  ".join(f"{k}={d[k]}" for k in order if d[k]))

    print(f"\nNESTING — rules extracted a sub-span of a larger gold node (top 10)")
    print(f"  {'rules_type':<14} {'enclosing gold':<14} {'n':>5}")
    for (rt, st), n in nesting.most_common(10):
        print(f"  {rt:<14} {st:<14} {n:>5}")

    print(f"\nType confusion — comparable-length spans, rules say X / silver Y (top 10)")
    print(f"  {'rules_type':<14} {'silver_type':<14} {'n':>5}")
    for (rt, st), n in confusion.most_common(10):
        print(f"  {rt:<14} {st:<14} {n:>5}")

    if gaps:
        print(f"\nExamples of real gaps (silver has nothing like this)")
        for pid, t, s in gaps:
            print(f"  [{pid} {t}] {s}")

    out = Path(args.out) if args.out else \
        (REPO / args.eval_dir).resolve() / f"silver_gap_audit_{args.which}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\nWrote {out}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
