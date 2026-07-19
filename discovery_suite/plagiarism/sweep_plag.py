"""T-PLAG P1 corpus sweep — EXTERNAL (disk-based) MinHash-LSH.

The whole point: never hold a global fingerprint index in RAM. The earlier
in-memory version OOM-killed at ~25k/100k papers (33GB). This version keeps peak
RAM bounded *regardless of corpus size* (100k or 3M papers) by writing signatures
to disk and only ever looking at one bucket / one partition at a time.

Four streaming passes over a scratch --work-dir:

  1. FINGERPRINT (parallel, O(1) RAM/worker). Each reader worker streams papers,
     MinHashes each node, and APPENDS to its own on-disk files — never a shared
     index:
       sig_{w}.bin    flat num_perm*uint64 per node (node `li` at li*permbytes)
       meta_{w}.tsv   node_key, pid, year, cat, snippet (line li = node li)
       bands_{w}.bin  one fixed-size record per (node, band):
                      (band_idx, band_bytes, w, li, paper_uid, year)
     A worker holds one paper at a time; nothing accumulates in memory.

  2. PARTITION (serial). Stream every bands_{w}.bin and route each record to one
     of K partition files by hash(band_idx, band_bytes) % K, so every LSH bucket
     lands wholly inside one partition.

  3. BUCKET & PAIR (serial, one partition at a time). Load a partition, sort by
     (band_idx, band_bytes) so identical band-signatures are adjacent = a bucket.
     For each bucket (<= max_bucket) enumerate node pairs, verify with the exact
     MinHash Jaccard (signatures read by seek from sig_{w}.bin), and append
     surviving cross-paper pairs — oriented older-paper-as-source — to pairs.tsv.

  4. DEDUP + AGGREGATE (streaming). External-`sort` pairs.tsv so the same node
     pair (it can surface in several bands/partitions) is adjacent; keep the max
     score per pair; aggregate to paper pairs; resolve node metadata with one
     sequential read of the meta files; write the two CSVs.

Peak RAM tracks the largest partition + the output size, NOT the corpus. Raise
--partitions for bigger corpora (a partition must fit comfortably in RAM);
signatures live on disk (num_perm*8 bytes/node — the disk knob is --num-perm).

    python discovery_suite/plagiarism/sweep_plag.py \
        --root /path/to/parsed_100k_v4 \
        --out  discovery_suite/plagiarism/runs/plag_sweep_100k.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import multiprocessing as mp
import os
import struct
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _SUITE / "plagiarism"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import node_norm_text, _lazy_walk, _build_paper, DEFAULT_ROOT  # noqa: E402
from shared.shingle import MinHasher, k_shingles  # noqa: E402


def _paper_uid(pid: str) -> int:
    """Stable 64-bit id for a paper, so pass 3 can do same-paper / orientation
    checks from the compact band record without touching the metadata files."""
    return int.from_bytes(hashlib.blake2b(pid.encode("utf-8"), digest_size=8).digest(), "little")


def _clean(s: str) -> str:
    return s.replace("\t", " ").replace("\n", " ").replace("\r", " ")


# ── Pass 1: fingerprint & emit (parallel workers) ─────────────────────────────
# Config + per-worker file handles live in module globals, set once in the pool
# initializer (fork gives each worker its own copy). Each worker owns a small,
# stable id (_WID) via a shared counter, so its files never clash.
_WROOT = None
_WHASHER: MinHasher | None = None
_WK = 5
_WMINWORDS = 8
_WNUMPERM = 128
_WBANDS = 32
_WROWBYTES = 0
_WROW: struct.Struct | None = None
_WID = -1
_WN = 0
_WSIG = None
_WMETA = None
_WBANDF = None
_COUNTER = None


def _winit(root, k, min_words, num_perm, bands, seed, work_dir, counter):
    global _WROOT, _WHASHER, _WK, _WMINWORDS, _WNUMPERM, _WBANDS, _WROWBYTES, _WROW
    global _WID, _WN, _WSIG, _WMETA, _WBANDF, _COUNTER
    _WROOT = Path(root)
    _WK = k
    _WMINWORDS = min_words
    _WNUMPERM = num_perm
    _WBANDS = bands
    _WROWBYTES = (num_perm // bands) * 8
    # record: band_idx(H) band_bytes(Ns) w(H) li(I) paper_uid(Q) year(H)
    _WROW = struct.Struct(f"<H{_WROWBYTES}sHIQH")
    _WHASHER = MinHasher(num_perm=num_perm, seed=seed)
    with counter.get_lock():
        _WID = counter.value
        counter.value += 1
    _WN = 0
    wd = Path(work_dir)
    _WSIG = open(wd / f"sig_{_WID}.bin", "wb", buffering=1 << 20)
    _WMETA = open(wd / f"meta_{_WID}.tsv", "w", encoding="utf-8", buffering=1 << 20)
    _WBANDF = open(wd / f"bands_{_WID}.bin", "wb", buffering=1 << 20)


def _fingerprint_one(path_str):
    """Read one paper; append its nodes' signatures/meta/band-rows to this
    worker's files. Returns nothing but the paper is GC'd here immediately."""
    global _WN
    p = _build_paper(Path(path_str), _WROOT)
    if p is None:
        return 0
    puid = _paper_uid(p.paper_id)
    year = int(p.year) & 0xFFFF
    kept = 0
    for n in p.nodes:
        txt = node_norm_text(n) or ""
        if len(txt.split()) < _WMINWORDS:
            continue
        sig = _WHASHER.signature(k_shingles(txt, k=_WK))  # uint64[num_perm]
        li = _WN
        _WSIG.write(sig.tobytes())
        _WMETA.write(f"{p.paper_id}::{n.get('id')}\t{p.paper_id}\t{p.year}\t"
                     f"{p.category}\t{_clean(txt[:160])}\n")
        sig_bytes = sig.tobytes()
        for b in range(_WBANDS):
            band = sig_bytes[b * _WROWBYTES:(b + 1) * _WROWBYTES]
            _WBANDF.write(_WROW.pack(b, band, _WID, li, puid, year))
        _WN += 1
        kept += 1
    return kept


def _wclose(_ignored):
    """Flush this worker's buffers. Mapped over `workers` sentinel tasks so every
    worker runs it exactly once before the pool tears down."""
    for fh in (_WSIG, _WMETA, _WBANDF):
        if fh is not None:
            fh.flush()
            os.fsync(fh.fileno())
    return _WID


def _default_workers():
    # Fewer than the read sweep's 64: each worker holds 3 open write buffers and
    # spawns a numpy process, so 16 balances I/O parallelism against memory/fds.
    return min(16, os.cpu_count() or 8)


def _pass1_fingerprint(root, args, work_dir, on_progress):
    paths = [str(pp) for pp in _lazy_walk(Path(root))]
    workers = args.workers or _default_workers()
    counter = mp.Value("i", 0)
    ctx = mp.get_context("fork")  # Linux default; avoids macOS broken spawn
    done = 0
    with ctx.Pool(workers, initializer=_winit,
                  initargs=(root, args.k, args.min_words, args.num_perm, args.bands,
                            args.seed, str(work_dir), counter)) as pool:
        for _ in pool.imap_unordered(_fingerprint_one, paths, chunksize=64):
            done += 1
            if on_progress is not None and done % 5000 == 0:
                on_progress(done, len(paths))
        # one flush task per worker (fed enough sentinels that each runs it)
        list(pool.imap_unordered(_wclose, range(workers * 4), chunksize=1))
    return len(paths)


# ── Pass 2: partition band rows so each LSH bucket lands in one file ───────────
def _pass2_partition(work_dir, num_perm, bands, partitions):
    rowbytes = (num_perm // bands) * 8
    row = struct.Struct(f"<H{rowbytes}sHIQH")
    rsz = row.size
    outs = [open(work_dir / f"part_{p}.bin", "wb", buffering=1 << 20)
            for p in range(partitions)]
    try:
        for bf in sorted(glob.glob(str(work_dir / "bands_*.bin"))):
            with open(bf, "rb") as fh:
                while True:
                    chunk = fh.read(rsz * 4096)
                    if not chunk:
                        break
                    for i in range(0, len(chunk), rsz):
                        rec = chunk[i:i + rsz]
                        band_idx, band = row.unpack(rec)[:2]
                        h = hash((band_idx, band)) % partitions
                        outs[h].write(rec)
    finally:
        for o in outs:
            o.close()


# ── Pass 3: bucket each partition, verify pairs, emit oriented pairs ───────────
class _SigReader:
    """Random-access reader for the per-worker signature files (seek by node li)."""

    def __init__(self, work_dir, num_perm):
        self._bytes = num_perm * 8
        self._num_perm = num_perm
        self._fh: dict[int, object] = {}
        self._dir = Path(work_dir)

    def sig(self, w: int, li: int) -> np.ndarray:
        fh = self._fh.get(w)
        if fh is None:
            fh = open(self._dir / f"sig_{w}.bin", "rb")
            self._fh[w] = fh
        fh.seek(li * self._bytes)
        return np.frombuffer(fh.read(self._bytes), dtype=np.uint64)

    def close(self):
        for fh in self._fh.values():
            fh.close()


def _pass3_pairs(work_dir, num_perm, bands, partitions, min_jaccard, max_bucket, on_progress):
    rowbytes = (num_perm // bands) * 8
    row = struct.Struct(f"<H{rowbytes}sHIQH")
    rsz = row.size
    sigs = _SigReader(work_dir, num_perm)
    n_pairs = 0
    out = open(work_dir / "pairs.tsv", "w", encoding="utf-8", buffering=1 << 20)
    try:
        for p in range(partitions):
            recs = []
            with open(work_dir / f"part_{p}.bin", "rb") as fh:
                data = fh.read()
            for i in range(0, len(data), rsz):
                recs.append(row.unpack(data[i:i + rsz]))
            # sort so identical (band_idx, band_bytes) rows are adjacent = a bucket
            recs.sort(key=lambda r: (r[0], r[1]))
            i, m = 0, len(recs)
            while i < m:
                j = i + 1
                while j < m and recs[j][0] == recs[i][0] and recs[j][1] == recs[i][1]:
                    j += 1
                bucket = recs[i:j]
                i = j
                if len(bucket) < 2 or (max_bucket and len(bucket) > max_bucket):
                    continue
                for a in range(len(bucket)):
                    _, _, wa, lia, pua, ya = bucket[a]
                    sa = sigs.sig(wa, lia)
                    for b in range(a + 1, len(bucket)):
                        _, _, wb, lib, pub, yb = bucket[b]
                        if pua == pub:            # same paper — not reuse
                            continue
                        sb = sigs.sig(wb, lib)
                        s = float(np.mean(sa == sb))
                        if s < min_jaccard:
                            continue
                        # orient: older paper is the source (tie -> smaller uid,
                        # then smaller (w,li)) so the pair's key is canonical
                        A = (ya, pua, wa, lia)
                        B = (yb, pub, wb, lib)
                        (sy, spu, sw, sl), (ty, tpu, tw, tl) = (
                            (A, B) if A <= B else (B, A))
                        out.write(f"{sw}\t{sl}\t{tw}\t{tl}\t{s:.4f}\t"
                                  f"{spu}\t{tpu}\t{sy}\t{ty}\n")
                        n_pairs += 1
            if on_progress is not None:
                on_progress(p + 1, partitions)
    finally:
        out.close()
        sigs.close()
    return n_pairs


# ── Pass 4: dedup (external sort), aggregate, resolve meta, write CSVs ─────────
def _external_sort(src: Path, dst: Path, work_dir: Path):
    """Sort pairs by node-pair key, highest score first within each pair, so the
    first row of each (sw,sl,tw,tl) group is the max — dedup is then a linear scan."""
    env = dict(os.environ, LC_ALL="C")
    with open(dst, "w") as out:
        subprocess.run(
            ["sort", "-t", "\t", "-k1,1n", "-k2,2n", "-k3,3n", "-k4,4n", "-k5,5nr",
             "-T", str(work_dir), str(src)],
            check=True, stdout=out, env=env)


def _resolve_meta(work_dir: Path, needed: dict[int, set[int]]) -> dict[tuple[int, int], tuple]:
    """One sequential read of each meta_{w}.tsv, picking only the needed lines.
    Returns (w, li) -> (node_key, pid, cat, snip)."""
    res: dict[tuple[int, int], tuple] = {}
    for w, lis in needed.items():
        if not lis:
            continue
        with open(work_dir / f"meta_{w}.tsv", encoding="utf-8") as fh:
            for li, line in enumerate(fh):
                if li in lis:
                    parts = line.rstrip("\n").split("\t")
                    node_key, pid, _yr, cat, snip = (parts + ["", "", "", "", ""])[:5]
                    res[(w, li)] = (node_key, pid, cat, snip)
    return res


def _pass4_finalize(work_dir, out_path, min_jaccard):
    pairs = work_dir / "pairs.tsv"
    ssorted = work_dir / "pairs_sorted.tsv"
    _external_sort(pairs, ssorted, work_dir)

    uniq = work_dir / "uniq.tsv"          # one row per node pair (max score)
    needed: dict[int, set[int]] = defaultdict(set)
    # agg[(src_uid, tgt_uid)] = [n, sum, max, (sw,sl,tw,tl,score), sy, ty]
    agg: dict[tuple[int, int], list] = {}
    n_uniq = 0

    with open(ssorted, encoding="utf-8") as fh, open(uniq, "w", encoding="utf-8") as uo:
        prev_key = None
        for line in fh:
            sw, sl, tw, tl, sc, spu, tpu, sy, ty = line.rstrip("\n").split("\t")
            key = (sw, sl, tw, tl)
            if key == prev_key:
                continue                  # dup of same pair (lower score) — skip
            prev_key = key
            sw, sl, tw, tl = int(sw), int(sl), int(tw), int(tl)
            score = float(sc)
            spu, tpu, sy, ty = int(spu), int(tpu), int(sy), int(ty)
            uo.write(f"{sw}\t{sl}\t{tw}\t{tl}\t{score:.4f}\t{sy}\t{ty}\n")
            needed[sw].add(sl)
            needed[tw].add(tl)
            n_uniq += 1
            a = agg.get((spu, tpu))
            if a is None:
                agg[(spu, tpu)] = [1, score, score, (sw, sl, tw, tl, score), sy, ty]
            else:
                a[0] += 1
                a[1] += score
                if score > a[2]:
                    a[2] = score
                    a[3] = (sw, sl, tw, tl, score)

    meta = _resolve_meta(work_dir, needed)

    def m(w, li):
        return meta.get((w, li), ("", "", "", ""))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nodes_out = out_path.with_name(out_path.stem + "_nodes" + out_path.suffix)

    # node-pair evidence CSV (stream uniq.tsv, now with resolved metadata)
    with open(uniq, encoding="utf-8") as fh, \
         nodes_out.open("w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["est_jaccard", "source_key", "target_key", "source_paper",
                    "target_paper", "source_year", "target_year", "cross_category",
                    "same_year", "source_snippet", "target_snippet"])
        rows = []
        for line in fh:
            sw, sl, tw, tl, sc, sy, ty = line.rstrip("\n").split("\t")
            sk, spid, scat, ssnip = m(int(sw), int(sl))
            tk, tpid, tcat, tsnip = m(int(tw), int(tl))
            cross = int(bool(scat and tcat and scat != tcat))
            rows.append((float(sc), sk, tk, spid, tpid, int(sy), int(ty),
                         cross, int(sy == ty), ssnip, tsnip))
        rows.sort(key=lambda r: (-r[0], r[1], r[2]))
        for r in rows:
            w.writerow([f"{r[0]:.3f}", *r[1:]])

    # paper-pair triage CSV
    paper_rows = []
    for (spu, tpu), (n, ssum, smax, best, sy, ty) in agg.items():
        bsw, bsl, btw, btl, _ = best
        sk, spid, scat, ssnip = m(bsw, bsl)
        tk, tpid, tcat, tsnip = m(btw, btl)
        cross = int(bool(scat and tcat and scat != tcat))
        paper_rows.append((smax, ssum, n, spid, sy, scat, tpid, ty, tcat,
                           cross, int(sy == ty), sk, tk, ssnip, tsnip))
    paper_rows.sort(key=lambda r: (-r[0], -r[2], r[3], r[6]))

    with out_path.open("w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["score_max", "score_sum", "n_shared_nodes",
                    "source_paper", "source_year", "source_cat",
                    "target_paper", "target_year", "target_cat",
                    "cross_category", "same_year",
                    "best_source_key", "best_target_key",
                    "best_source_snippet", "best_target_snippet"])
        for r in paper_rows:
            w.writerow([f"{r[0]:.3f}", f"{r[1]:.3f}", *r[2:]])

    return n_uniq, len(paper_rows), nodes_out


def main() -> None:
    try:
        mp.set_start_method("fork")
    except (RuntimeError, ValueError):
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="parsed corpus root (streams all categories)")
    ap.add_argument("--out", required=True,
                    help="paper-pair triage CSV; node evidence written alongside as "
                         "<out stem>_nodes.csv")
    ap.add_argument("--work-dir", default=None,
                    help="scratch dir for on-disk passes (default: <out>_work). Needs "
                         "space for signatures (~num_perm*8 B/node) + band rows.")
    ap.add_argument("--k", type=int, default=5, help="word-shingle size")
    ap.add_argument("--num-perm", type=int, default=128, help="MinHash permutations (disk knob)")
    ap.add_argument("--bands", type=int, default=32, help="LSH bands (must divide num-perm)")
    ap.add_argument("--partitions", type=int, default=64,
                    help="on-disk band partitions; each must fit in RAM at pass 3. "
                         "Raise for bigger corpora (3M: try 512+).")
    ap.add_argument("--min-jaccard", type=float, default=0.2, help="min est. Jaccard to keep a node pair")
    ap.add_argument("--min-words", type=int, default=8)
    ap.add_argument("--max-bucket", type=int, default=400,
                    help="skip LSH buckets larger than this (boilerplate); 0 = no cap")
    ap.add_argument("--seed", type=int, default=1, help="MinHash permutation seed")
    ap.add_argument("--workers", type=int, default=None,
                    help="parallel fingerprint workers (default = min(16, cores))")
    ap.add_argument("--keep-work", action="store_true", help="don't delete the scratch dir")
    args = ap.parse_args()

    if args.num_perm % args.bands:
        ap.error("--bands must divide --num-perm")

    root = args.root or DEFAULT_ROOT
    out_path = Path(args.out)
    work_dir = Path(args.work_dir) if args.work_dir else out_path.with_name(out_path.stem + "_work")
    work_dir.mkdir(parents=True, exist_ok=True)
    max_bucket = None if args.max_bucket <= 0 else args.max_bucket

    t0 = time.time()
    print(f"[plag] work-dir={work_dir}", flush=True)
    print(f"[plag] pass 1/4: fingerprint (workers={args.workers or _default_workers()}) …", flush=True)
    n_files = _pass1_fingerprint(
        root, args, work_dir,
        lambda d, t: print(f"[plag] fingerprint: {d}/{t} files ({time.time()-t0:.0f}s)", flush=True))
    print(f"[plag] pass 1 done: {n_files} files in {time.time()-t0:.0f}s", flush=True)

    t1 = time.time()
    print(f"[plag] pass 2/4: partition band rows into {args.partitions} shards …", flush=True)
    _pass2_partition(work_dir, args.num_perm, args.bands, args.partitions)
    print(f"[plag] pass 2 done in {time.time()-t1:.0f}s", flush=True)

    t2 = time.time()
    print(f"[plag] pass 3/4: bucket + verify pairs (min_jaccard={args.min_jaccard}) …", flush=True)
    n_pairs = _pass3_pairs(
        work_dir, args.num_perm, args.bands, args.partitions, args.min_jaccard, max_bucket,
        lambda d, t: (print(f"[plag] pair: {d}/{t} partitions ({time.time()-t2:.0f}s)", flush=True)
                      if d % 8 == 0 or d == t else None))
    print(f"[plag] pass 3 done: {n_pairs} raw pairs in {time.time()-t2:.0f}s", flush=True)

    t3 = time.time()
    print("[plag] pass 4/4: dedup + aggregate + write CSVs …", flush=True)
    n_uniq, n_paper, nodes_out = _pass4_finalize(work_dir, out_path, args.min_jaccard)
    print(f"[plag] pass 4 done: {n_uniq} unique node pairs, {n_paper} paper pairs "
          f"in {time.time()-t3:.0f}s", flush=True)
    print(f"[plag] wrote {out_path} (+ {nodes_out.name})", flush=True)

    if not args.keep_work:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
        print(f"[plag] removed scratch {work_dir} (use --keep-work to retain)", flush=True)
    print("[next] filter cross_category / high score_max rows; adjudicate the strongest "
          "node pairs with the P4 LLM judge (common/llm_judge.py) and gate self-reuse "
          "via the S2 author graph.", flush=True)


if __name__ == "__main__":
    main()
