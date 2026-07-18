"""T-OPEN corpus sweep — real (unplanted) open-problem → resolution candidates.

Unlike run_open_demo.py (which plants twins to *measure* O1), this runs O1 over
the WHOLE corpus and emits a ranked triage CSV of real problem->theorem pairs for
human/LLM-judge (O4) review. Cross-category by construction: it streams every
paper under --root regardless of category, so a problem in cs.CC can match a
theorem in math.CO.

    python discovery_suite/open_problems/sweep_open.py \
        --root /path/to/parsed_100k_v4 \
        --out  discovery_suite/open_problems/runs/open_sweep_100k.csv

MEMORY: streams the corpus (stream_papers) and keeps ONLY the token-sets of
problem/theorem nodes — never a full list of Paper objects. Equations, proofs,
edges and raw LaTeX (~7M of ~8M nodes at 100k) are parsed and immediately
discarded, so peak RAM is well under 1GB instead of ~15GB.

SCALE: matching is O(#problems x #theorems). We default the query set to
{open_problem, conjecture} (the genuine target) and EXCLUDE the generic `problem`
type (~20k noisy nodes at 100k). Pass --include-problem to widen it.
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

from shared.corpus import stream_papers, node_norm_text  # noqa: E402
from o1_retrieve import THEOREM_TYPES, _jaccard  # noqa: E402


def _extract(root, ptypes, min_words, on_progress):
    """Stream the corpus once; return (problems, theorems) as lean records.

    Each record: {key, pid, year, cat, type, toks(frozenset), snip}. Full Paper
    objects are dropped after each iteration (generator + no retention)."""
    keep = ptypes | THEOREM_TYPES
    problems, theorems = [], []
    for p in stream_papers(root=root, on_progress=on_progress):
        for n in p.nodes:
            t = (n.get("type") or "").lower()
            if t not in keep:
                continue
            txt = node_norm_text(n) or ""
            toks = frozenset(txt.split())
            if len(toks) < min_words:
                continue
            rec = {
                "key": f"{p.paper_id}::{n.get('id')}",
                "pid": p.paper_id, "year": p.year, "cat": p.category,
                "type": t, "toks": toks,
                "snip": txt[:160].replace("\n", " "),
            }
            (problems if t in ptypes else theorems).append(rec)
    return problems, theorems


def _rank(problems, theorems, top_k, min_score, on_progress):
    """All-pairs temporal-directed Jaccard; return ranked (prob_rec, thm_rec, s)."""
    out = []
    total = len(problems)
    for i, pr in enumerate(problems):
        if on_progress is not None and i and i % 100 == 0:
            on_progress(i, total)
        scored = []
        for th in theorems:
            if th["pid"] == pr["pid"] or th["year"] < pr["year"]:
                continue
            s = _jaccard(pr["toks"], th["toks"])
            if s >= min_score:
                scored.append((th, s))
        scored.sort(key=lambda x: -x[1])
        for th, s in scored[:top_k]:
            out.append((pr, th, s))
    out.sort(key=lambda x: -x[2])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="parsed corpus root (streams all categories)")
    ap.add_argument("--out", required=True, help="output triage CSV path")
    ap.add_argument("--top-k", type=int, default=20, help="candidates kept per problem")
    ap.add_argument("--min-score", type=float, default=0.10, help="min Jaccard to keep")
    ap.add_argument("--min-words", type=int, default=6)
    ap.add_argument("--include-problem", action="store_true",
                    help="also treat generic `problem` nodes as queries (slower, noisier)")
    args = ap.parse_args()

    ptypes = {"open_problem", "conjecture"}
    if args.include_problem:
        ptypes = ptypes | {"problem"}

    t0 = time.time()

    def _load_progress(scanned):
        print(f"[sweep] load: scanned {scanned} files ({time.time()-t0:.0f}s)", flush=True)

    problems, theorems = _extract(args.root, ptypes, args.min_words, _load_progress)
    print(f"[sweep] streamed corpus in {time.time()-t0:.0f}s; "
          f"{len(problems)} query nodes ({'+'.join(sorted(ptypes))}), "
          f"{len(theorems)} theorem nodes", flush=True)

    t1 = time.time()

    def _rank_progress(done, total):
        print(f"[sweep] rank: {done}/{total} query nodes scored ({time.time()-t1:.0f}s)", flush=True)

    ranked = _rank(problems, theorems, args.top_k, args.min_score, _rank_progress)
    print(f"[sweep] rank -> {len(ranked)} candidate pairs in {time.time()-t1:.0f}s", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["score", "problem_key", "problem_cat", "problem_type",
                    "theorem_key", "theorem_cat", "cross_category",
                    "problem_snippet", "theorem_snippet"])
        for pr, th, s in ranked:
            cross = int(bool(pr["cat"] and th["cat"] and pr["cat"] != th["cat"]))
            w.writerow([f"{s:.3f}", pr["key"], pr["cat"], pr["type"],
                        th["key"], th["cat"], cross, pr["snip"], th["snip"]])
    print(f"[sweep] wrote {len(ranked)} rows -> {out}", flush=True)


if __name__ == "__main__":
    main()
