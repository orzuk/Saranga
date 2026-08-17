#!/usr/bin/env python3
"""Characterize the FPs that distillation ADDS, without any LLM call.

Reads the bucket cache written by eval_base_vs_distilled_split.py and, for every
extraction present under the FINAL rules but absent under the BASE rules that
does not match gold of its own type, asks what it actually overlaps:

  cross_type      matches gold of a DIFFERENT type at >= threshold
                  -> real content, wrong type bucket (not a hallucinated span)
  dup_span        matches a same-type gold item that was already consumed by
                  another extraction -> double-counted span, one node of content
  partial         best overlap in [partial_lo, threshold) -> span-boundary
                  disagreement with the silver, not invented text
  spurious        best overlap < partial_lo -> text the silver has no node for
                  (either a genuine FP or a silver miss; only an LLM can split)

Usage:
    python scripts/analyze_distill_fps.py \
        --cache src/LLMVersion/merged_eval_silver_001_011_v3/_split_eval/buckets_cache.json
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

import silver_distillation_sequential as seq
from silver_distillation_sequential import FNAME_MAP
from silver_distillation_merged import load_gold_texts

TYPES = list(FNAME_MAP.keys())


def greedy_match(extracted, gold, threshold):
    """Same greedy matcher as merged.metrics; returns (matched_ext_idx, matched_gold_idx)."""
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
        me.add(i)
        mg.add(j)
    return me, mg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--eval-dir", default="src/LLMVersion/merged_eval_silver_001_011_v3")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--partial-lo", type=float, default=0.4)
    ap.add_argument("--match-metric", default="containment")
    ap.add_argument("--examples", type=int, default=0,
                    help="print N example spurious FPs per group")
    args = ap.parse_args()

    seq.set_match_metric(args.match_metric)
    cache = json.load(open(args.cache, encoding="utf-8"))
    gold_dir = (REPO / args.eval_dir).resolve() / "_split_eval" / "gold"
    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in TYPES}

    meta = {r["paper_id"]: r for r in
            csv.DictReader(open(REPO / "corpus/silver/metadata.csv", encoding="utf-8"))
            if r["prompt_version"] == "v4.1"}

    buckets = defaultdict(lambda: defaultdict(int))
    by_type = defaultdict(lambda: defaultdict(int))
    samples = defaultdict(list)

    for pid, entry in cache.items():
        m = meta.get(pid)
        if not m:
            continue
        grp = "train" if m["split"] == "train" else f"test-{m['tier']}"
        all_gold = [(t, g) for t in TYPES for g in gold[t].get(pid, [])]

        for t in TYPES:
            g_own = gold[t].get(pid, [])
            for tag in ("base", "final"):
                texts = entry[tag][t]
                me, _ = greedy_match(texts, g_own, args.threshold)
                for i, ext in enumerate(texts):
                    if i in me:
                        continue                 # it's a TP
                    # --- an FP under this rule set: what does it overlap? ---
                    best_same, best_cross = 0.0, 0.0
                    for gt, g in all_gold:
                        s = seq.jaccard_similarity(ext, g)
                        if gt == t:
                            best_same = max(best_same, s)
                        else:
                            best_cross = max(best_cross, s)
                    if best_same >= args.threshold:
                        kind = "dup_span"
                    elif best_cross >= args.threshold:
                        kind = "cross_type"
                    elif max(best_same, best_cross) >= args.partial_lo:
                        kind = "partial"
                    else:
                        kind = "spurious"
                    buckets[(grp, tag)][kind] += 1
                    buckets[(grp, tag)]["total"] += 1
                    by_type[(t, tag)][kind] += 1
                    by_type[(t, tag)]["total"] += 1
                    if (tag == "final" and kind == "spurious"
                            and len(samples[grp]) < args.examples):
                        samples[grp].append((pid, t, ext[:200].replace("\n", " ")))

    kinds = ["cross_type", "dup_span", "partial", "spurious"]
    print("What every FALSE POSITIVE actually is, base vs final rules")
    print("  cross_type = real content, wrong type bucket   dup_span = double-counted span")
    print("  partial    = span-boundary disagreement        spurious = silver has no such node")
    print(f"threshold={args.threshold} partial_lo={args.partial_lo} metric={args.match_metric}\n")
    hdr = f"{'group':<22} {'rules':<6} {'FP':>5} " + " ".join(f"{k:>11}" for k in kinds)
    print(hdr)
    for grp in ["train", "test-B_math_shift", "test-A_matched_ML"]:
        for tag in ("base", "final"):
            d = buckets.get((grp, tag))
            if not d:
                continue
            tot = d["total"]
            cells = " ".join(f"{d[k]:>5} {d[k]/tot*100:>4.0f}%" for k in kinds)
            print(f"{grp:<22} {tag:<6} {tot:>5} {cells}")
        b, f = buckets[(grp, "base")], buckets[(grp, "final")]
        delta = " ".join(f"{f[k]-b[k]:>+5}      " for k in kinds)
        print(f"{'':<22} {'DELTA':<6} {f['total']-b['total']:>+5} {delta}")
        print()

    print(f"By type — DELTA in FPs (final − base)\n{'type':<14} {'dFP':>5} "
          + " ".join(f"{k:>9}" for k in kinds))
    for t in TYPES:
        b, f = by_type.get((t, "base"), {}), by_type.get((t, "final"), {})
        if not (b or f):
            continue
        d_tot = f.get("total", 0) - b.get("total", 0)
        if d_tot == 0 and not any(f.get(k, 0) - b.get(k, 0) for k in kinds):
            continue
        cells = " ".join(f"{f.get(k,0)-b.get(k,0):>+9}" for k in kinds)
        print(f"{t:<14} {d_tot:>+5} {cells}")

    for grp, ex in samples.items():
        print(f"\n--- example spurious FPs: {grp} ---")
        for pid, t, s in ex:
            print(f"  [{pid} {t}] {s}")


if __name__ == "__main__":
    main()
