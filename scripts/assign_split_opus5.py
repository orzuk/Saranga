#!/usr/bin/env python3
"""Draw the train/test split over the opus-5 v5.1 silver corpus.

The split was deliberately deferred while the corpus was being extracted
(`corpus/silver/CONTINUE_HERE.md`: "the pool CSV has no split column, so it can
be drawn at any time"). This draws it, and freezes the result in

    corpus/silver/split_opus5.csv        # arxiv_id,category,split

which is the SOURCE OF TRUTH for the split. metadata.csv is regenerated from
the corpus, so the split cannot live only there.

Design
------
* **Stratified** by arXiv category. The corpus is exactly balanced (10 papers x
  20 categories at 200 papers), so a per-category quota is exact.
* **Deterministic** by `sha256(arxiv_id)` — a paper's rank depends only on its
  own id, never on the draw order or on how many other papers exist.
* **Sticky.** Any assignment already present in split_opus5.csv is preserved
  verbatim; only unassigned papers are drawn. So when the remaining 800 target
  papers are extracted, re-running this fills them in WITHOUT moving any paper
  already assigned. A test paper can never silently drift into train.

Category comes from `extraction_targets_opus5.csv`, not from the JSON metadata
(37 of the 200 JSONs carry no `category` field).

Usage:
    python scripts/assign_split_opus5.py            # draw / top up
    python scripts/assign_split_opus5.py --dry-run
    python scripts/assign_split_opus5.py --train-per-cat 3
"""
import argparse
import csv
import glob
import hashlib
import os
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(REPO, "corpus/silver/opus-5__v5.1")
TARGETS = os.path.join(REPO, "corpus/silver/extraction_targets_opus5.csv")
SPLIT_CSV = os.path.join(REPO, "corpus/silver/split_opus5.csv")
COLS = ["arxiv_id", "category", "split"]


def rank_key(aid):
    """Stable per-paper rank in [0,1). Depends on the id alone."""
    h = hashlib.sha256(aid.encode("utf-8")).hexdigest()
    return int(h, 16) / float(1 << 256)


def load_existing(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["arxiv_id"]: r["split"] for r in csv.DictReader(f)
                if r.get("arxiv_id") and r.get("split")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-per-cat", type=int, default=3,
                    help="train papers per category (default 3 -> 3/7 of a "
                         "10-paper category = 60/140 over 200 papers)")
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--out", default=SPLIT_CSV)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(TARGETS):
        sys.exit("missing %s" % TARGETS)
    cat = {r["arxiv_id"]: r["category"] for r in
           csv.DictReader(open(TARGETS, encoding="utf-8"))}

    ids = sorted(os.path.basename(p)[:-5]
                 for p in glob.glob(os.path.join(args.corpus, "*.json")))
    if not ids:
        sys.exit("no extracted JSONs under %s" % args.corpus)
    unknown = [i for i in ids if i not in cat]
    if unknown:
        sys.exit("%d extracted id(s) absent from the target pool, refusing to "
                 "guess a category: %s" % (len(unknown), ", ".join(unknown[:5])))

    existing = load_existing(args.out)
    kept = sum(1 for i in ids if i in existing)

    bycat = defaultdict(list)
    for i in ids:
        bycat[cat[i]].append(i)

    out = {}
    for c, members in sorted(bycat.items()):
        # honour prior assignments, then fill the train quota with the
        # lowest-hash unassigned papers.
        for i in members:
            if i in existing:
                out[i] = existing[i]
        need = args.train_per_cat - sum(1 for i in members if out.get(i) == "train")
        free = sorted((i for i in members if i not in out), key=rank_key)
        for i in free[:max(need, 0)]:
            out[i] = "train"
        for i in members:
            out.setdefault(i, "test")

    counts = Counter(out.values())
    percat = {c: Counter(out[i] for i in m) for c, m in sorted(bycat.items())}
    print("opus-5 v5.1 split over %d papers in %d categories" % (len(ids), len(bycat)))
    print("  preserved from existing split file: %d" % kept)
    print("  train=%d  test=%d" % (counts["train"], counts["test"]))
    off = [c for c, k in percat.items() if k["train"] != args.train_per_cat]
    if off:
        print("  NOTE categories not at quota (fewer papers extracted): %s"
              % ", ".join("%s(%d)" % (c, percat[c]["train"]) for c in off))

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for i in ids:
            w.writerow({"arxiv_id": i, "category": cat[i], "split": out[i]})
    print("\nwrote %s" % os.path.relpath(args.out, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
