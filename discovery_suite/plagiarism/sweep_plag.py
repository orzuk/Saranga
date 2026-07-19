"""T-PLAG P1 corpus sweep — cross-paper lexical reuse candidates over the whole
parsed corpus.

Sibling of open_problems/sweep_open.py, for the plagiarism task. It streams every
paper under --root, MinHashes each node's normalized text, LSH-buckets the
signatures, and emits ranked cross-paper matches for human / P4-LLM review:

  * a NODE-pair evidence CSV (each reused statement pair + est. Jaccard), and
  * an aggregated PAPER-pair triage CSV (the thing a reviewer actually scans):
    per (source, target) papers — n shared nodes, max & summed node Jaccard,
    the single strongest node pair, and cross-category / same-year flags.

Directionality: "B reuses A" with A older, so within each pair the OLDER paper is
labelled the source. We do NOT temporally *exclude* anything (unlike the open
sweep) — both same-year and reverse pairs are legitimate reuse; we only orient
them. Same-author self-reuse is deliberately NOT filtered here: the roadmap wants
that done via the S2 author graph (a later step), not brittle name-string
matching, so this sweep stays name-agnostic and leaves that gate to P4/S2.

    python discovery_suite/plagiarism/sweep_plag.py \
        --root /path/to/parsed_100k_v4 \
        --out  discovery_suite/plagiarism/runs/plag_sweep_100k.csv

MEMORY: the MinHash signature (num_perm * uint64 = 1KB at defaults) is computed
INSIDE each reader worker and only the tiny per-node record (key, ids, 160-char
snippet, signature bytes) crosses back. Signatures are streamed straight into the
LSH index as they arrive — the full paper (equations, proofs, raw LaTeX) is GC'd
in the worker — so peak RAM tracks #kept-nodes, not the ~15GB full corpus.

SCALE: candidate generation is LSH banding (near-linear), not the O(#a x #b) of
the open sweep. The `max_bucket` guard in shared/shingle drops boilerplate buckets
that would otherwise blow up O(bucket^2).
"""
from __future__ import annotations

import argparse
import csv
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _SUITE / "plagiarism"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import node_norm_text, _lazy_walk, _build_paper, DEFAULT_ROOT  # noqa: E402
from shared.shingle import LSHIndex, MinHasher, k_shingles  # noqa: E402


# --- parallel file reading -------------------------------------------------
# Each worker reads ONE file, keeps only nodes long enough to fingerprint, and
# MinHashes them locally (the hasher is deterministic + seeded, so every worker
# produces identical signatures). Only the tiny records return; the full paper is
# GC'd in the worker. Config is handed to each worker once via the pool
# initializer (globals below), not per file.
_WROOT = None
_WHASHER: MinHasher | None = None
_WK = 5
_WMINWORDS = 8


def _winit(root, k, min_words, num_perm, seed):
    global _WROOT, _WHASHER, _WK, _WMINWORDS
    _WROOT = Path(root)
    _WK = k
    _WMINWORDS = min_words
    _WHASHER = MinHasher(num_perm=num_perm, seed=seed)


def _extract_one(path_str):
    """Read one file -> list of lean fingerprint records for that paper."""
    p = _build_paper(Path(path_str), _WROOT)
    if p is None:
        return []
    out = []
    for n in p.nodes:
        txt = node_norm_text(n) or ""
        if len(txt.split()) < _WMINWORDS:
            continue
        sig = _WHASHER.signature(k_shingles(txt, k=_WK))
        out.append({
            "key": f"{p.paper_id}::{n.get('id')}",
            "pid": p.paper_id, "year": p.year, "cat": p.category,
            "type": (n.get("type") or "").lower(),
            "sig": sig.tobytes(),
            "snip": txt[:160].replace("\n", " "),
        })
    return out


def _default_workers():
    """Concurrent file READERS. Reading is network-I/O-bound (each worker mostly
    waits on the FS), so we want many readers to hide latency, not the CPU count;
    SLURM's cgroup still caps real CPU share to the allocated cores. Capped at 64;
    override with --workers. Mirrors open_problems/sweep_open._default_workers."""
    return min(64, os.cpu_count() or 8)


def _stream_index(root, k, min_words, num_perm, bands, seed, workers, on_progress):
    """Read the whole corpus in parallel and build the LSH index as records
    arrive. Returns (index, meta) where meta[key] = (pid, year, cat, snip).

    Signatures are added to the index (and the raw bytes dropped) one record at a
    time, so we never hold a second full copy of every signature in a Python list."""
    paths = [str(pp) for pp in _lazy_walk(Path(root))]
    index = LSHIndex(num_perm=num_perm, bands=bands)
    meta: dict[str, tuple] = {}
    done = 0

    def _absorb(recs):
        for r in recs:
            sig = np.frombuffer(r["sig"], dtype=np.uint64)
            index.add(r["key"], r["pid"], sig)
            meta[r["key"]] = (r["pid"], r["year"], r["cat"], r["snip"])

    if workers <= 1:
        # No Pool: in-process, deterministic, and dodges macOS framework-build
        # fork breakage. Use --workers 1 for local smoke tests.
        _winit(root, k, min_words, num_perm, seed)
        for pth in paths:
            done += 1
            if on_progress is not None and done % 5000 == 0:
                on_progress(done, len(paths))
            _absorb(_extract_one(pth))
        return index, meta

    # Explicit fork context: Linux default on the cluster, and on macOS avoids the
    # framework build's broken spawn ("posix_spawn: Undefined error").
    ctx = mp.get_context("fork")
    with ctx.Pool(workers, initializer=_winit,
                  initargs=(root, k, min_words, num_perm, seed)) as pool:
        for recs in pool.imap_unordered(_extract_one, paths, chunksize=64):
            done += 1
            if on_progress is not None and done % 5000 == 0:
                on_progress(done, len(paths))
            _absorb(recs)
    return index, meta


def _orient(ka, kb, meta):
    """Return (source_key, target_key): the OLDER paper is the source. Ties (same
    year) break by paper_id so orientation is deterministic; caller flags same_year."""
    ya, yb = meta[ka][1], meta[kb][1]
    if ya < yb:
        return ka, kb
    if yb < ya:
        return kb, ka
    return (ka, kb) if meta[ka][0] <= meta[kb][0] else (kb, ka)


def main() -> None:
    # fork everywhere: Linux default on the cluster, and on macOS avoids the
    # framework build's broken spawn. Mirrors sweep_open.
    try:
        mp.set_start_method("fork")
    except (RuntimeError, ValueError):
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="parsed corpus root (streams all categories)")
    ap.add_argument("--out", required=True,
                    help="paper-pair triage CSV path; node evidence written alongside "
                         "as <out stem>_nodes.csv")
    ap.add_argument("--k", type=int, default=5, help="word-shingle size")
    ap.add_argument("--num-perm", type=int, default=128, help="MinHash permutations")
    ap.add_argument("--bands", type=int, default=32,
                    help="LSH bands (must divide num-perm; more bands = looser recall)")
    ap.add_argument("--min-jaccard", type=float, default=0.2, help="min est. Jaccard to keep a node pair")
    ap.add_argument("--min-words", type=int, default=8)
    ap.add_argument("--max-bucket", type=int, default=400,
                    help="skip LSH buckets larger than this (boilerplate collisions "
                         "that would blow up O(bucket^2)); 0 = no cap")
    ap.add_argument("--seed", type=int, default=1, help="MinHash permutation seed")
    ap.add_argument("--workers", type=int, default=None,
                    help="concurrent file readers (default = min(64, cores); I/O-bound)")
    args = ap.parse_args()

    root = args.root or DEFAULT_ROOT
    workers = args.workers or _default_workers()
    max_bucket = None if args.max_bucket <= 0 else args.max_bucket
    t0 = time.time()
    print(f"[plag] reading corpus with {workers} parallel workers …", flush=True)

    def _load_progress(done, total):
        print(f"[plag] load: read {done}/{total} files ({time.time()-t0:.0f}s)", flush=True)

    index, meta = _stream_index(root, args.k, args.min_words, args.num_perm,
                                args.bands, args.seed, workers, _load_progress)
    print(f"[plag] indexed {len(meta)} fingerprintable nodes in {time.time()-t0:.0f}s", flush=True)

    t1 = time.time()
    pairs = index.scored_pairs(cross_paper_only=True, min_jaccard=args.min_jaccard,
                               max_bucket=max_bucket)
    print(f"[plag] LSH -> {len(pairs)} cross-paper node pairs "
          f"(>= {args.min_jaccard} est. Jaccard) in {time.time()-t1:.0f}s", flush=True)

    # ── orient + aggregate node pairs into paper pairs ────────────────────────
    # agg[(src_pid, tgt_pid)] = {n, sum, max, best=(score, src_key, tgt_key)}
    node_rows = []
    agg: dict[tuple[str, str], dict] = {}
    for ka, kb, s in pairs:
        sk, tk = _orient(ka, kb, meta)
        spid, syr, scat, ssnip = meta[sk]
        tpid, tyr, tcat, tsnip = meta[tk]
        cross = int(bool(scat and tcat and scat != tcat))
        same_year = int(syr == tyr)
        node_rows.append((s, sk, tk, spid, tpid, syr, tyr, cross, same_year, ssnip, tsnip))
        a = agg.setdefault((spid, tpid), {"n": 0, "sum": 0.0, "max": -1.0, "best": None,
                                          "syr": syr, "tyr": tyr, "scat": scat, "tcat": tcat})
        a["n"] += 1
        a["sum"] += s
        if s > a["max"]:
            a["max"] = s
            a["best"] = (s, sk, tk, ssnip, tsnip)

    node_rows.sort(key=lambda r: (-r[0], r[1], r[2]))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    nodes_out = out.with_name(out.stem + "_nodes" + out.suffix)
    with nodes_out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["est_jaccard", "source_key", "target_key", "source_paper",
                    "target_paper", "source_year", "target_year", "cross_category",
                    "same_year", "source_snippet", "target_snippet"])
        for r in node_rows:
            w.writerow([f"{r[0]:.3f}", *r[1:9], r[9], r[10]])
    print(f"[plag] wrote {len(node_rows)} node-pair rows -> {nodes_out}", flush=True)

    # paper triage: strongest reuse first (max node Jaccard, then breadth)
    paper_rows = []
    for (spid, tpid), a in agg.items():
        _, bsk, btk, bss, bts = a["best"]
        cross = int(bool(a["scat"] and a["tcat"] and a["scat"] != a["tcat"]))
        paper_rows.append((a["max"], a["sum"], a["n"], spid, a["syr"], a["scat"],
                           tpid, a["tyr"], a["tcat"], cross, int(a["syr"] == a["tyr"]),
                           bsk, btk, bss, bts))
    paper_rows.sort(key=lambda r: (-r[0], -r[2], r[3], r[6]))

    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["score_max", "score_sum", "n_shared_nodes",
                    "source_paper", "source_year", "source_cat",
                    "target_paper", "target_year", "target_cat",
                    "cross_category", "same_year",
                    "best_source_key", "best_target_key",
                    "best_source_snippet", "best_target_snippet"])
        for r in paper_rows:
            w.writerow([f"{r[0]:.3f}", f"{r[1]:.3f}", *r[2:]])
    print(f"[plag] wrote {len(paper_rows)} paper-pair rows -> {out}", flush=True)
    print("[next] review top rows; adjudicate strong pairs with the P4 LLM judge "
          "(reuse common/llm_judge.py) and gate self-reuse via the S2 author graph.",
          flush=True)


if __name__ == "__main__":
    main()
