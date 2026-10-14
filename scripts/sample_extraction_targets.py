#!/usr/bin/env python3
"""Draw a stratified, reproducible POOL of papers to (re-)extract with Opus-5.

Design (settled 2026-07): 50 papers per category × the 20 CORPUS_CATEGORIES =
1000 targets, sampled uniformly at random within each category from the local
tier3_v2 corpus (~5k/category). Excludes papers already in corpus/silver/.

This produces only the POOL — it does NOT assign train/test. The split is a
separate, later decision; run `scripts/assign_split_v6.py` on this file whenever
you want a (re-derivable) split, so you can change the ratio/seed freely.

VALIDITY FILTER: each candidate's tier3 `_rules.json` must have at least
`--min-nodes` extracted nodes. The rule-extractor produced ~0 nodes for papers
with no usable/mathy LaTeX (scanned, exotic macros, non-theorem papers); this
drops those so we don't waste Opus-5 calls on papers with nothing to extract.
It's a lower-bound proxy for "has valid, math-bearing LaTeX", not a guarantee —
the actual .tex is re-fetched and read fresh at extraction time.

Sampling frame: $SARANGA_DATA_ROOT/tier3_v2/<category>/json/<arxivid>_rules.json
(rule-extracted tier3 outputs; we use their IDs+category+node-count only).

Deterministic: fixed seed → same 1000 every run. Makes NO network calls.

Usage:
    python scripts/sample_extraction_targets.py \
        [--per-cat 50] [--min-nodes 3] [--seed 20260730] \
        [--out corpus/silver/extraction_targets_opus5.csv]
"""
import argparse
import csv
import os
import random
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.environ.get("SARANGA_DATA_ROOT", "/mnt/c/Datasets/Saranga_data")
FRAME = os.path.join(DATASET, "tier3_v2")
SILVER_META = os.path.join(REPO, "corpus/silver/metadata.csv")

sys.path.insert(0, os.path.join(REPO, "src"))
try:
    from config import CORPUS_CATEGORIES, ARXIV_FORM  # 20-cat list + fs→arxiv map
except Exception as e:  # pragma: no cover
    print("could not import CORPUS_CATEGORIES from src/config.py: %s" % e, file=sys.stderr)
    raise

COLS = ["idx", "arxiv_id", "category", "category_arxiv", "year",
        "n_rule_nodes", "source_rules_json"]


def arxiv_id_from_file(fn):
    """'1001.0207v2_rules.json' -> '1001.0207v2'."""
    return re.sub(r"_rules\.json$", "", os.path.basename(fn))


def year_of(arxiv_id):
    """New style YYMM.xxxxx or old style archive/YYMMxxx -> 20YY."""
    m = re.match(r"(?:[a-z\-]+/)?(\d{2})(\d{2})", arxiv_id)
    return 2000 + int(m.group(1)) if m else None


def node_count(path):
    """Number of extracted nodes in a tier3 _rules.json (validity proxy)."""
    try:
        import json
        d = json.load(open(path, encoding="utf-8"))
        return len(d.get("nodes", d.get("objects", [])))
    except Exception:
        return 0


def already_extracted():
    """arxiv_ids already present in corpus/silver (to exclude)."""
    ids = set()
    if os.path.isfile(SILVER_META):
        for r in csv.DictReader(open(SILVER_META, encoding="utf-8")):
            if r.get("arxiv_id"):
                ids.add(r["arxiv_id"].strip())
                ids.add(re.sub(r"v\d+$", "", r["arxiv_id"].strip()))  # version-agnostic
    return ids


def frame_ids(cat):
    d = os.path.join(FRAME, cat, "json")
    if not os.path.isdir(d):
        print("  WARN no frame dir for %s (%s)" % (cat, d), file=sys.stderr)
        return []
    return [os.path.join(d, fn) for fn in os.listdir(d) if fn.endswith("_rules.json")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cat", type=int, default=50)
    ap.add_argument("--min-nodes", type=int, default=3,
                    help="require this many rule-extracted nodes (validity proxy)")
    ap.add_argument("--seed", type=int, default=20260730)
    ap.add_argument("--out", default=os.path.join(
        REPO, "corpus/silver/extraction_targets_opus5.csv"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    exclude = already_extracted()

    rows = []
    idx = 0
    print("category           avail  scanned  skipped(<%d nodes)  sampled" % args.min_nodes)
    for cat in CORPUS_CATEGORIES:
        files = frame_ids(cat)
        # exclude already-extracted (version-agnostic) and dedup by base id
        cands, seen = [], set()
        for f in files:
            aid = arxiv_id_from_file(f)
            base = re.sub(r"v\d+$", "", aid)
            if aid in exclude or base in exclude or base in seen:
                continue
            seen.add(base)
            cands.append((aid, f))
        cands.sort(key=lambda t: t[0])          # deterministic order before shuffle
        rng.shuffle(cands)
        # walk the shuffled candidates, reading node counts, until per_cat pass
        picked, scanned, skipped = [], 0, 0
        for aid, f in cands:
            if len(picked) >= args.per_cat:
                break
            scanned += 1
            nn = node_count(f)
            if nn < args.min_nodes:
                skipped += 1
                continue
            picked.append((aid, f, nn))
        for aid, f, nn in picked:
            idx += 1
            rows.append({
                "idx": idx, "arxiv_id": aid, "category": cat,
                "category_arxiv": ARXIV_FORM.get(cat, cat),
                "year": year_of(aid) or "", "n_rule_nodes": nn,
                "source_rules_json": os.path.relpath(f, DATASET),
            })
        print("  %-16s %5d  %6d  %14d  %5d"
              % (cat, len(cands), scanned, skipped, len(picked)))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)

    print("\ntotal pool: %d papers  excluded-already: %d" % (len(rows), len(exclude)))
    print("wrote", os.path.relpath(args.out, REPO))
    print("(no split assigned — run scripts/assign_split_v6.py when you decide the ratio)")


if __name__ == "__main__":
    main()
