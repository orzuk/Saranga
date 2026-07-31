#!/usr/bin/env python3
"""Reconcile the extraction pool against what has actually been written.

Filesystem is the source of truth: a paper counts as done iff
corpus/silver/opus-5__v5/<arxiv_id>.json exists and parses with >0 nodes.
Prints per-batch/per-category status and the list of ids still to do, so a
batch runner never depends on remembering which launches succeeded.

Usage:
    python scripts/extraction_status.py [--batches 5] [--per-cat 1] [--todo-only]
"""
import argparse
import csv
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(REPO, "corpus/silver/extraction_targets_opus5.csv")
OUT = os.path.join(REPO, "corpus/silver/opus-5__v5.1")   # default; override with --dir
TEX = os.path.join(REPO, "corpus/silver/tex_pool")


def status(aid):
    """A paper is only 'done' if it has BOTH nodes and edges.

    An agent killed mid-write (API error) can leave a file with nodes but no
    edges — a useless graph that must be re-extracted, not counted as done.
    """
    p = os.path.join(OUT, aid + ".json")
    if not os.path.isfile(p):
        return "missing", 0
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return "corrupt", 0
    n, e = len(d.get("nodes", [])), len(d.get("edges", []))
    if n == 0:
        return "empty", 0
    if e == 0:
        return "no-edges", n          # truncated / incomplete write
    return "done", n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=int, default=5)
    ap.add_argument("--per-cat", type=int, default=1)
    ap.add_argument("--todo-only", action="store_true")
    ap.add_argument("--dir", default=None,
                    help="extraction dir to reconcile against (default corpus/silver/opus-5__v5.1)")
    args = ap.parse_args()
    if args.dir:
        global OUT
        OUT = args.dir

    rows = list(csv.DictReader(open(POOL, encoding="utf-8")))
    bycat = {}
    for r in rows:
        bycat.setdefault(r["category"], []).append(r)

    todo, done_n, tot_nodes = [], 0, 0
    lines = []
    for b in range(args.batches):
        lo, hi = b * args.per_cat, (b + 1) * args.per_cat
        for cat in sorted(bycat):
            for r in bycat[cat][lo:hi]:
                aid = r["arxiv_id"]
                st, n = status(aid)
                has_tex = os.path.isfile(os.path.join(TEX, aid.replace("/", "_") + ".tex"))
                if st == "done":
                    done_n += 1
                    tot_nodes += n
                else:
                    todo.append((b + 1, cat, aid, st, has_tex))
                lines.append((b + 1, cat, aid, st, n, has_tex))

    if not args.todo_only:
        print("%-6s %-11s %-16s %-8s %6s %s" % ("batch", "category", "arxiv_id", "status", "nodes", "tex"))
        for b, cat, aid, st, n, tx in lines:
            print("%-6d %-11s %-16s %-8s %6s %s" % (b, cat, aid, st, n or "", "y" if tx else "NO"))

    total = len(lines)
    print("\nDONE %d/%d   nodes so far: %d   mean %.1f nodes/paper"
          % (done_n, total, tot_nodes, tot_nodes / done_n if done_n else 0))
    if todo:
        print("\nTODO (%d):" % len(todo))
        for b, cat, aid, st, tx in todo:
            print("  batch%-2d %-11s %-16s (%s%s)" % (b, cat, aid, st, "" if tx else ", NO TEX"))
        print("\nids: " + ",".join(t[2] for t in todo))


if __name__ == "__main__":
    main()
