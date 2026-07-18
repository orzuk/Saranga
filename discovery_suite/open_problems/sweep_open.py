"""T-OPEN corpus sweep — real (unplanted) open-problem → resolution candidates.

Unlike run_open_demo.py (which plants twins to *measure* O1), this runs O1 over
the WHOLE corpus and emits a ranked triage CSV of real problem->theorem pairs for
human/LLM-judge (O4) review. Cross-category by construction: it loads every paper
under --root regardless of category, so a problem in cs.CC can match a theorem in
math.CO.

    python discovery_suite/open_problems/sweep_open.py \
        --root /path/to/parsed_100k_v4 \
        --out  discovery_suite/open_problems/runs/open_sweep_100k.csv

Scale note: retrieve() is ~O(#problems x #theorems). We default the problem set
to {open_problem, conjecture} (the genuine target, ~hundreds-to-thousands of
nodes) and EXCLUDE the generic `problem` type (~20k nodes at 100k, mostly
exercise/problem-statement noise). Pass --include-problem to widen it.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _SUITE / "open_problems"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import load_papers, node_norm_text  # noqa: E402
import o1_retrieve  # noqa: E402
from o1_retrieve import retrieve  # noqa: E402


def _node_index(papers) -> dict:
    """key 'pid::nodeid' -> (category, type, name/snippet) for CSV enrichment."""
    idx = {}
    for i, p in enumerate(papers):
        if i and i % 20000 == 0:
            print(f"[sweep] index {i}/{len(papers)} papers …", flush=True)
        for n in p.nodes:
            key = f"{p.paper_id}::{n.get('id')}"
            snippet = (node_norm_text(n) or "")[:160].replace("\n", " ")
            idx[key] = (p.category, (n.get("type") or "").lower(), snippet)
    return idx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="parsed corpus root (walks all categories)")
    ap.add_argument("--out", required=True, help="output triage CSV path")
    ap.add_argument("--limit", type=int, default=None, help="cap papers (smoke test)")
    ap.add_argument("--top-k", type=int, default=20, help="candidates kept per problem")
    ap.add_argument("--min-score", type=float, default=0.10, help="min Jaccard to keep")
    ap.add_argument("--min-words", type=int, default=6)
    ap.add_argument("--include-problem", action="store_true",
                    help="also treat generic `problem` nodes as queries (much slower, noisier)")
    args = ap.parse_args()

    ptypes = {"open_problem", "conjecture"}
    if args.include_problem:
        ptypes = ptypes | {"problem"}
    o1_retrieve.PROBLEM_TYPES = ptypes  # retrieve() reads this global at call time

    t0 = time.time()

    def _load_progress(scanned, kept):
        print(f"[sweep] load: scanned {scanned} files, kept {kept} papers "
              f"({time.time()-t0:.0f}s)", flush=True)

    papers = load_papers(root=args.root, limit=args.limit, on_progress=_load_progress)
    n_prob = sum(1 for p in papers for n in p.nodes
                 if (n.get("type") or "").lower() in ptypes)
    print(f"[sweep] loaded {len(papers)} papers in {time.time()-t0:.1f}s; "
          f"{n_prob} query nodes ({'+'.join(sorted(ptypes))})", flush=True)

    idx = _node_index(papers)

    t1 = time.time()

    def _retr_progress(done, total):
        print(f"[sweep] retrieve: {done}/{total} query nodes scored "
              f"({time.time()-t1:.0f}s)", flush=True)

    pairs = retrieve(papers, top_k=args.top_k, min_score=args.min_score,
                     min_words=args.min_words, on_progress=_retr_progress)
    print(f"[sweep] retrieve -> {len(pairs)} candidate pairs in {time.time()-t1:.1f}s", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["score", "problem_key", "problem_cat", "problem_type",
                    "theorem_key", "theorem_cat", "cross_category",
                    "problem_snippet", "theorem_snippet"])
        for pk, tk, s in pairs:
            pcat, ptype, psnip = idx.get(pk, ("", "", ""))
            tcat, _ttype, tsnip = idx.get(tk, ("", "", ""))
            w.writerow([f"{s:.3f}", pk, pcat, ptype, tk, tcat,
                        int(bool(pcat and tcat and pcat != tcat)), psnip, tsnip])
    print(f"[sweep] wrote {len(pairs)} rows -> {out}", flush=True)


if __name__ == "__main__":
    main()
