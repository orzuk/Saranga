#!/usr/bin/env python3
"""Training data for alg3: the silver papers as sentences, silver prose nodes and
the base parser's counts, built with the unit algorithm's own loader
(scripts/distill_units.py: load_paper / _prep_one), so that sentences, silver
alignment and the scoring baseline are exactly those Or's comparison uses.

    python3 alg3/data.py --splits train,val --out alg3/cache/papers.pkl

Test papers are refused unless --allow-test (they are only ever scored through
scripts/compare_distillers.py).
"""
from __future__ import annotations

import argparse
import csv
import multiprocessing as mp
import pickle
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import distill_units as DU                                   # noqa: E402

SPLIT_FILE = REPO / "corpus/silver/split_v6_6-2-2.csv"
SILVER = REPO / "corpus/silver/opus-5.5__v6"


def split_ids(splits) -> dict:
    out = {}
    for r in csv.DictReader(open(SPLIT_FILE, encoding="utf-8")):
        pid = r.get("arxiv_id") or r["paper_id"]
        if r["split"] in splits:
            out[pid] = r["split"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="train,val")
    ap.add_argument("--tex-dir", required=True, help="staged tex: <pid>/source/<pid>.tex")
    ap.add_argument("--out", default=str(REPO / "alg3/cache/papers.pkl"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--allow-test", action="store_true")
    a = ap.parse_args()
    splits = [s.strip() for s in a.splits.split(",")]
    if "test" in splits and not a.allow_test:
        raise SystemExit("test papers are scored only through compare_distillers.py")
    ids = split_ids(splits)
    empty = REPO / "alg3/cache/_empty_rules"
    empty.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    papers = {}
    with mp.Pool(a.workers, initializer=DU._prep_init,
                 initargs=(a.tex_dir, str(SILVER), 0.7, str(empty), "m1g")) as pool:
        for k, (pid, p) in enumerate(pool.imap_unordered(DU._prep_one, sorted(ids)), 1):
            if p is not None:
                p._sig = []
                papers[pid] = (ids[pid], p)
            if k % 20 == 0:
                print(f"  {k}/{len(ids)} papers ({time.time() - t0:.0f}s)", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "wb") as fh:
        pickle.dump(papers, fh)
    n_nodes = sum(len(p.nodes) for _, p in papers.values())
    print(f"saved {len(papers)} papers, {n_nodes} silver prose nodes -> {a.out} "
          f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
