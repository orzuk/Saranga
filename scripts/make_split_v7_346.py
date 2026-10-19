#!/usr/bin/env python3
"""Split file for the v7 silver pool of 346 papers: the 200 silver papers keep their split from
split_v6_6-2-2.csv unchanged; the 146 gold-evaluation papers (v7 extractions of paper_nodiag.tex) are
split 90 train / 28 val / 28 test, stratified by arXiv archive (math, cs, stat, other) with a fixed hash
order, so the result is reproducible.

    python3 scripts/make_split_v7_346.py   ->  corpus/silver/split_v7_346.csv
"""
import csv
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QUOTA = {"train": 90, "val": 28, "test": 28}


def main():
    rows = [dict(r, source="silver") for r in csv.DictReader(open(REPO / "corpus/silver/split_v6_6-2-2.csv"))]
    cat = {x["id"]: x.get("category") or "" for x in json.load(open(REPO / "corpus/gold_candidates/index.json"))}
    ids = [l.split()[0] for l in open(REPO / "corpus/gold_candidates/eval_subset.txt") if l.strip() and not l.startswith("#")]
    group = lambda i: next((g for g in ("math", "cs", "stat") if cat.get(i, "").startswith(g)), "other")
    order = sorted(ids, key=lambda i: (group(i), hashlib.sha256(i.encode()).hexdigest()))
    pattern = [("train", "train", "train", "val", "test")[k % 5] if k < 140 else ("train", "train", "train", "train", "val", "test")[k - 140]
               for k in range(146)]
    left = dict(QUOTA)
    out = []
    for k, i in enumerate(order):                                  # round-robin keeps each group 60/20/20
        s = pattern[k]
        if left[s] == 0:
            s = next(t for t in ("train", "val", "test") if left[t])
        left[s] -= 1
        out.append({"arxiv_id": i, "category": cat.get(i, ""), "split": s, "split_v51": "", "source": "gold_author"})
    with open(REPO / "corpus/silver/split_v7_346.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["arxiv_id", "category", "split", "split_v51", "source"])
        w.writeheader()
        w.writerows(rows + out)
    from collections import Counter
    print(Counter((r["source"], r["split"]) for r in rows + out))
    print(Counter((group(r["arxiv_id"]), r["split"]) for r in out))


if __name__ == "__main__":
    main()
