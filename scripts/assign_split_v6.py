#!/usr/bin/env python3
"""Draw the train / val / test split of the 200-paper silver corpus for the
distiller comparison, and freeze it in

    corpus/silver/split_v6_<train>-<val>-<test>.csv    # arxiv_id,category,split,split_v51

Design
------
* Per category (20 categories x 10 papers): --train / --val / --test papers,
  6 / 2 / 2 by default = 120 / 40 / 40. The sizes are parameters; each choice
  gets its own file, so several splits can be compared.
* The 3 training papers of the v5.1 split (corpus/silver/split_opus5.csv) stay
  in training (needs --train >= 3). So the v5.1 distilled rules, which were
  written from them, have never seen a val or test paper of this split, and can
  be scored on it. --no-keep-v51 drops that constraint (and that comparison).
* The other papers are ranked by sha256(arxiv_id) within the category
  (assign_split_opus5.rank_key): the lowest-ranked fill the rest of the training
  quota, the next ones validation, the rest test.
* Deterministic, and the file is the source of truth: re-running it rewrites the
  same split.

Usage:
    python scripts/assign_split_v6.py [--train 6 --val 2 --test 2] [--dry-run]
"""
import argparse
import csv
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assign_split_opus5 import REPO, SPLIT_CSV as V51_SPLIT, rank_key   # noqa: E402


def split_path(train: int, val: int, test: int) -> str:
    return os.path.join(REPO, f"corpus/silver/split_v6_{train}-{val}-{test}.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=6)
    ap.add_argument("--val", type=int, default=2)
    ap.add_argument("--test", type=int, default=2)
    ap.add_argument("--no-keep-v51", action="store_true",
                    help="rank every paper, ignoring which were v5.1 training papers")
    ap.add_argument("--out", default=None, help="default corpus/silver/split_v6_<train>-<val>-<test>.csv")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(V51_SPLIT, encoding="utf-8")))
    bycat = defaultdict(list)
    for r in rows:
        bycat[r["category"]].append(r)
    out = {}
    for cat, members in sorted(bycat.items()):
        if len(members) != args.train + args.val + args.test:
            sys.exit(f"category {cat} has {len(members)} papers, quotas sum to "
                     f"{args.train + args.val + args.test}")
        old_train = [] if args.no_keep_v51 else \
            [r["arxiv_id"] for r in members if r["split"] == "train"]
        if len(old_train) > args.train:
            sys.exit(f"category {cat}: {len(old_train)} v5.1 training papers > --train "
                     f"(use --no-keep-v51)")
        rest = sorted((r["arxiv_id"] for r in members if r["arxiv_id"] not in old_train),
                      key=rank_key)
        need = args.train - len(old_train)
        for a in old_train + rest[:need]:
            out[a] = "train"
        for a in rest[need:need + args.val]:
            out[a] = "val"
        for a in rest[need + args.val:]:
            out[a] = "test"

    counts = Counter(out.values())
    print(f"split over {len(out)} papers in {len(bycat)} categories: "
          + "  ".join(f"{k}={counts[k]}" for k in ("train", "val", "test")))
    if args.dry_run:
        return 0
    args.out = args.out or split_path(args.train, args.val, args.test)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["arxiv_id", "category", "split", "split_v51"])
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["category"], r["arxiv_id"])):
            w.writerow({"arxiv_id": r["arxiv_id"], "category": r["category"],
                        "split": out[r["arxiv_id"]], "split_v51": r["split"]})
    print(f"wrote {os.path.relpath(args.out, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
