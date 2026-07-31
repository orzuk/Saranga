#!/usr/bin/env python3
"""Assign a train/test (optionally val) split to the extraction pool — a SEPARATE,
re-runnable step so the split is never baked into the sample.

Reads the pool CSV from sample_extraction_targets.py and writes a copy with a
`split` column added, stratified by category so every split covers all 20
categories. Change --test-frac / --val-frac / --seed freely to get a different
(reproducible) split at any time; the underlying 1000-paper pool never changes.

Usage:
    python scripts/assign_split.py \
        [--pool corpus/silver/extraction_targets_opus5.csv] \
        [--test-frac 0.30] [--val-frac 0.0] [--seed 1] \
        [--out <pool basename>_split.csv]
"""
import argparse
import csv
import os
import random
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=os.path.join(
        REPO, "corpus/silver/extraction_targets_opus5.csv"))
    ap.add_argument("--test-frac", type=float, default=0.30)
    ap.add_argument("--val-frac", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    rows = list(csv.DictReader(open(args.pool, encoding="utf-8")))
    if "split" in (rows[0].keys() if rows else []):
        rows = [{k: v for k, v in r.items() if k != "split"} for r in rows]

    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r.get("category", "?")].append(r)

    for cat, items in by_cat.items():
        items = sorted(items, key=lambda r: r["arxiv_id"])   # deterministic
        rng.shuffle(items)
        n = len(items)
        n_test = round(n * args.test_frac)
        n_val = round(n * args.val_frac)
        for i, r in enumerate(items):
            if i < n_test:
                r["split"] = "test"
            elif i < n_test + n_val:
                r["split"] = "val"
            else:
                r["split"] = "train"

    fields = list(rows[0].keys())
    if "split" not in fields:
        fields.append("split")
    out = args.out or args.pool.replace(".csv", "_split.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    c = Counter(r["split"] for r in rows)
    print("split (seed=%d test=%.2f val=%.2f): %s"
          % (args.seed, args.test_frac, args.val_frac, dict(c)))
    print("wrote", os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
