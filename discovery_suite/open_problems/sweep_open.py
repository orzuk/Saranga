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
import os
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _SUITE / "open_problems"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import node_norm_text, _lazy_walk, _build_paper  # noqa: E402
from o1_retrieve import THEOREM_TYPES, _jaccard  # noqa: E402


# --- parallel file reading -------------------------------------------------
# Each worker reads ONE file, keeps only its problem/theorem nodes, and returns
# those tiny records. The full paper never leaves the worker (it's GC'd there),
# so 4 workers reading at once still use almost no memory. Config is handed to
# each worker once via the pool initializer (globals below), not per file.
_WROOT = None
_WPTYPES: set = set()
_WMINWORDS = 6


def _winit(root, ptypes, min_words):
    global _WROOT, _WPTYPES, _WMINWORDS
    _WROOT = Path(root)
    _WPTYPES = ptypes
    _WMINWORDS = min_words


def _extract_one(path_str):
    """Read one file -> (problems, theorems) lean records for just that paper."""
    p = _build_paper(Path(path_str), _WROOT)
    if p is None:
        return [], []
    keep = _WPTYPES | THEOREM_TYPES
    problems, theorems = [], []
    for n in p.nodes:
        t = (n.get("type") or "").lower()
        if t not in keep:
            continue
        txt = node_norm_text(n) or ""
        toks = frozenset(txt.split())
        if len(toks) < _WMINWORDS:
            continue
        rec = {
            "key": f"{p.paper_id}::{n.get('id')}",
            "pid": p.paper_id, "year": p.year, "cat": p.category,
            "type": t, "toks": toks,
            "snip": txt[:160].replace("\n", " "),
        }
        (problems if t in _WPTYPES else theorems).append(rec)
    return problems, theorems


def _default_workers():
    """How many files to READ at once. Reading is network-I/O-bound (each worker
    mostly waits on the disk), so we want MANY concurrent readers to hide latency
    — NOT the CPU count. SLURM's cgroup still caps our real CPU share to the
    allocated cores no matter how many reader processes we start, so a high count
    is safe and much faster (128 readers read 100k files in ~170s; 4 took ~13min).
    Capped at 64 to stay reasonable; override with --workers."""
    return min(64, os.cpu_count() or 8)


def _extract(root, ptypes, min_words, on_progress, workers):
    """Read the whole corpus (files in parallel); return (problems, theorems).

    Only the small node records are collected in the main process; each paper is
    read and discarded inside a worker, so peak memory stays ~1GB."""
    paths = [str(pp) for pp in _lazy_walk(Path(root))]
    problems, theorems = [], []
    done = 0
    with Pool(workers, initializer=_winit,
              initargs=(root, ptypes, min_words)) as pool:
        for probs, thms in pool.imap_unordered(_extract_one, paths, chunksize=64):
            done += 1
            if on_progress is not None and done % 5000 == 0:
                on_progress(done, len(paths))
            problems.extend(probs)
            theorems.extend(thms)
    return problems, theorems


def _rank(problems, theorems, top_k, min_score, on_progress, df_frac=0.02):
    """Temporal-directed Jaccard, but only over theorems that share a SELECTIVE
    word with each problem (via an inverted index) instead of all-pairs. On 100k
    this turns ~24 billion comparisons into a few hundred million. Return ranked
    (prob_rec, thm_rec, score).

    Two separate roles for words:
      * candidate GENERATION uses only *selective* words — those in <= df_frac of
        theorems. Common words (the 'math' placeholder, stopwords, and mid-common
        words like 'graph'/'set' that each sit in hundreds of thousands of
        theorems) are skipped here: iterating their huge posting lists is what
        made rank hang, and a pair whose ONLY overlap is such generic words is a
        weak match anyway.
      * SCORING is the exact full-word Jaccard (unchanged) — so every candidate's
        score is identical to the brute-force value; we only narrow *which*
        theorems get scored."""
    # inverted index: word -> theorem row-numbers containing it
    posting = defaultdict(list)
    for ti, th in enumerate(theorems):
        for tok in th["toks"]:
            posting[tok].append(ti)
    max_df = max(1, int(len(theorems) * df_frac))
    common = {tok for tok, lst in posting.items() if len(lst) > max_df}
    print(f"[sweep] index: {len(posting)} words, {len(common)} skipped for candidate "
          f"generation as too common (>{max_df} theorems)", flush=True)

    out = []
    total = len(problems)
    for i, pr in enumerate(problems):
        if on_progress is not None and i and i % 500 == 0:
            on_progress(i, total)
        # candidate theorems = those sharing >=1 selective word with the problem
        cand = set()
        for tok in pr["toks"]:
            if tok not in common:
                cand.update(posting.get(tok, ()))
        ptoks, ppid, pyear = pr["toks"], pr["pid"], pr["year"]
        scored = []
        for ti in cand:
            th = theorems[ti]
            if th["pid"] == ppid or th["year"] < pyear:
                continue
            s = _jaccard(ptoks, th["toks"])
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
    ap.add_argument("--workers", type=int, default=None,
                    help="concurrent file readers (default = min(64, node cores); reads "
                         "are I/O-bound so more readers = faster, CPU stays cgroup-capped)")
    ap.add_argument("--df-frac", type=float, default=0.02,
                    help="for candidate generation, use only words in <= this fraction "
                         "of theorems (skips common words whose huge posting lists make "
                         "rank hang; scoring still uses full word-sets). 1.0 = all words")
    args = ap.parse_args()

    ptypes = {"open_problem", "conjecture"}
    if args.include_problem:
        ptypes = ptypes | {"problem"}

    workers = args.workers or _default_workers()
    t0 = time.time()
    print(f"[sweep] reading corpus with {workers} parallel workers …", flush=True)

    def _load_progress(done, total):
        print(f"[sweep] load: read {done}/{total} files ({time.time()-t0:.0f}s)", flush=True)

    problems, theorems = _extract(args.root, ptypes, args.min_words,
                                  _load_progress, workers)
    print(f"[sweep] streamed corpus in {time.time()-t0:.0f}s; "
          f"{len(problems)} query nodes ({'+'.join(sorted(ptypes))}), "
          f"{len(theorems)} theorem nodes", flush=True)

    t1 = time.time()

    def _rank_progress(done, total):
        print(f"[sweep] rank: {done}/{total} query nodes scored ({time.time()-t1:.0f}s)", flush=True)

    ranked = _rank(problems, theorems, args.top_k, args.min_score, _rank_progress,
                   df_frac=args.df_frac)
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
