"""Stage 1 — corpus JSONs -> sharded text store (raw + canonical, node + context).

This is the CPU half of the pipeline, and it exists so the GPU half never has to
touch the corpus. Canonicalization runs at ~240 nodes/s/core (measured on real
tier3 nodes) — doing it inline in the encode job would leave the GPU idle ~90% of
the time. Here it is parallel, cached and done once for every downstream
experiment.

    # once, cheap: enumerate the corpus so N array tasks don't each walk it
    python -m embed.textstore plan --root $ROOT --out $STORE

    # per array task
    python -m embed.textstore build --root $ROOT --out $STORE \
        --shards 64 --shard-id $SLURM_ARRAY_TASK_ID

Output ``<out>/shard_%05d.jsonl.gz`` + a ``.done`` marker per shard (resume =
skip anything already marked done), plus ``manifest.json`` recording the exact
view configuration the vectors were built under. gzipped JSONL rather than
parquet: no pyarrow dependency, streams one shard at a time, and the store is
written once but read many times by cheap sequential scans.
"""
from __future__ import annotations

import argparse
import gzip
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
from typing import Iterator, Optional, Sequence

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import _lazy_walk, _build_paper  # noqa: E402
from embed.progress import Heartbeat, banner, task_id  # noqa: E402
from embed import views as V  # noqa: E402

SHARD_FMT = "shard_%05d.jsonl.gz"
FILES_NAME = "files.txt"
MANIFEST = "manifest.json"


# ── shard io (imported by encode.py — one definition of the on-disk format) ───

def shard_path(out_dir: Path, shard_id: int) -> Path:
    return Path(out_dir) / (SHARD_FMT % shard_id)


def done_path(out_dir: Path, shard_id: int) -> Path:
    return shard_path(out_dir, shard_id).with_suffix(".done")


def write_shard(out_dir: Path, shard_id: int, rows: Sequence[dict]) -> Path:
    """Write atomically: full temp file, then rename. A killed job therefore
    leaves either a complete shard or nothing — never a truncated one that a
    later resume would happily treat as finished."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    final = shard_path(out_dir, shard_id)
    tmp = final.with_suffix(".gz.tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, final)
    done_path(out_dir, shard_id).write_text(
        json.dumps({"rows": len(rows), "ts": time.time()}), encoding="utf-8")
    return final


def read_shard(out_dir: Path, shard_id: int) -> Iterator[dict]:
    p = shard_path(out_dir, shard_id)
    if not p.exists():
        return
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def list_shards(out_dir: Path) -> list[int]:
    out_dir = Path(out_dir)
    ids = []
    for p in sorted(out_dir.glob("shard_*.jsonl.gz")):
        try:
            ids.append(int(p.name.split("_")[1].split(".")[0]))
        except (IndexError, ValueError):
            continue
    return ids


def read_manifest(out_dir: Path) -> dict:
    p = Path(out_dir) / MANIFEST
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# ── file planning ────────────────────────────────────────────────────────────

def plan_files(root: Path, out_dir: Path, *, limit: Optional[int] = None,
               categories: Optional[Sequence[str]] = None) -> list[str]:
    """Enumerate corpus files ONCE and persist the list.

    Every array task needs the same deterministic file ordering to slice
    ``files[k::N]``. Having 64 tasks each os.walk a 100k-file networked tree is
    exactly the shared-metadata hammering that killed the download jobs — so the
    walk happens once, here, and the tasks read a text file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cat_filter = set(categories) if categories else None
    files: list[str] = []
    t0 = time.time()
    for p in _lazy_walk(Path(root)):
        if cat_filter is not None:
            try:
                if p.relative_to(root).parts[0] not in cat_filter:
                    continue
            except (ValueError, IndexError):
                continue
        files.append(str(p))
        # Report often: this walk crosses ~100k files on a networked FS and a
        # sparse heartbeat is indistinguishable from a hang (it got killed once
        # for exactly that reason).
        if len(files) % 2000 == 0:
            el = time.time() - t0
            print(f"[plan] {len(files):,} files  {len(files)/max(el,1e-9):,.0f}/s  "
                  f"{el:.0f}s elapsed", file=sys.stderr, flush=True)
        if limit is not None and len(files) >= limit:
            break
    target = out_dir / FILES_NAME
    tmp = target.with_suffix(".txt.tmp")
    tmp.write_text("\n".join(files), encoding="utf-8")
    os.replace(tmp, target)
    print(f"[plan] {len(files):,} files -> {target} ({time.time()-t0:.0f}s)",
          file=sys.stderr, flush=True)
    return files


def load_files(out_dir: Path) -> list[str]:
    p = Path(out_dir) / FILES_NAME
    if not p.exists():
        raise FileNotFoundError(
            f"{p} not found — run `textstore.py plan --root ... --out {out_dir}` "
            f"once before launching the build array")
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ── workers ──────────────────────────────────────────────────────────────────

_CFG: dict = {}


def _winit(root: str, cfg: dict) -> None:
    global _CFG
    _CFG = dict(cfg)
    _CFG["root"] = Path(root)


def _extract_one(path_str: str) -> list[dict]:
    """One file -> its text-store rows. The Paper object never leaves the worker."""
    paper = _build_paper(Path(path_str), _CFG["root"])
    if paper is None:
        return []
    try:
        recs = V.paper_records(
            paper,
            query_types=_CFG["query_types"],
            canon_scope=_CFG["canon_scope"],
            ctx_canon_scope=_CFG["ctx_canon_scope"],
            with_canon=_CFG["with_canon"],
            ctx_depth=_CFG["ctx_depth"],
            max_neighbours=_CFG["max_neighbours"],
            max_ctx_chars=_CFG["max_ctx_chars"],
            min_words=_CFG["min_words"],
            keep_ctx_nodes=_CFG["keep_ctx_nodes"],
        )
    except Exception as exc:  # one malformed paper must not kill a whole shard
        print(f"[textstore] SKIP {path_str}: {type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)
        return []
    return [r.as_row() for r in recs]


def _default_workers() -> int:
    """CPU-bound here (canonicalization dominates), unlike the I/O-bound reads in
    sweep_open.py — so use the cores SLURM actually gave us, not a high count."""
    n = os.environ.get("SLURM_CPUS_PER_TASK")
    if n:
        return max(1, int(n))
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:
        return os.cpu_count() or 4


# ── build ────────────────────────────────────────────────────────────────────

def build_shard(root: Path, out_dir: Path, files: Sequence[str], shard_id: int,
                n_shards: int, cfg: dict, *, workers: int,
                status_dir: Optional[Path] = None, log_every: int = 500,
                force: bool = False) -> int:
    if done_path(out_dir, shard_id).exists() and not force:
        print(f"[textstore] shard {shard_id} already done — skipping "
              f"(--force to rebuild)", file=sys.stderr, flush=True)
        return 0
    mine = list(files[shard_id::n_shards])
    banner(f"textstore.s{shard_id}", files=len(mine), shard=shard_id,
           shards=n_shards, workers=workers)
    hb = Heartbeat(f"textstore.s{shard_id}", total=len(mine), unit="files",
                   status_dir=status_dir, every=log_every,
                   extra={"shard": shard_id, "rows": 0})
    rows: list[dict] = []
    if workers <= 1:
        _winit(str(root), cfg)
        for fp in mine:
            rows.extend(_extract_one(fp))
            hb.tick(rows=len(rows))
    else:
        ctx = mp.get_context("fork")
        with ctx.Pool(workers, initializer=_winit,
                      initargs=(str(root), cfg)) as pool:
            for got in pool.imap_unordered(_extract_one, mine, chunksize=8):
                rows.extend(got)
                hb.tick(rows=len(rows))
    # Deterministic order regardless of which worker finished first, so a
    # rebuilt shard is byte-identical and vectors stay reproducible.
    rows.sort(key=lambda r: r["key"])
    write_shard(out_dir, shard_id, rows)
    hb.close(rows=len(rows))
    return len(rows)


def _cfg_from_args(args) -> dict:
    qt = sorted(V.QUERY_TYPES_WIDE if args.include_problem else V.QUERY_TYPES)
    return {
        "query_types": qt,
        "canon_scope": args.canon_scope,
        "ctx_canon_scope": args.ctx_canon_scope,
        "with_canon": not args.no_canon,
        "ctx_depth": args.ctx_depth,
        "max_neighbours": args.max_neighbours,
        "max_ctx_chars": args.max_ctx_chars,
        "min_words": args.min_words,
        "keep_ctx_nodes": not args.no_ctx_nodes,
    }


def _write_manifest(out_dir: Path, cfg: dict, root: Path, n_shards: int,
                    n_files: int) -> None:
    """Record exactly how the text was built.

    A vector is only comparable to another vector built from the same view
    configuration. When a benchmark row says 'ctx-concat, canon, depth 2', this
    file is what proves the store actually was that.
    """
    p = Path(out_dir) / MANIFEST
    payload = {"root": str(root), "shards": n_shards, "files": n_files,
               "columns": V.ROW_COLUMNS, "views": list(V.ALL_VIEWS),
               "built_ts": time.time(), **cfg}
    if p.exists():
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
            drift = {k: (old.get(k), payload.get(k)) for k in cfg
                     if k in old and old.get(k) != payload.get(k)}
            if drift:
                print(f"[textstore] WARNING: config differs from the existing "
                      f"store at {out_dir}: {drift}. Shards built under both "
                      f"configs are NOT comparable — use a fresh --out or --force.",
                      file=sys.stderr, flush=True)
        except (OSError, json.JSONDecodeError):
            # A concurrent replace by another array task shows up as a stale NFS
            # handle here. The drift check is advisory; never fail the job for it.
            pass

    # PER-TASK temp name. Every array task writes this manifest at startup, and a
    # shared "manifest.json.tmp" makes them race: one task's os.replace removes
    # the file another is about to rename, and that one dies with FileNotFoundError
    # BEFORE doing any work. That is what lost 47 of 64 shards on the first 100k
    # run. The payload is identical across tasks, so last-writer-wins is correct.
    tmp = p.with_suffix(f".json.{task_id()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    except OSError as exc:
        print(f"[textstore] note: manifest not written ({exc}); shard work "
              f"continues — the manifest is metadata, not an input.",
              file=sys.stderr, flush=True)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> None:
    try:
        mp.set_start_method("fork")
    except (RuntimeError, ValueError):
        pass  # already set, or unavailable

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("plan", help="enumerate corpus files once")
    pp.add_argument("--root", default=None)
    pp.add_argument("--out", required=True)
    pp.add_argument("--limit", type=int, default=None)
    pp.add_argument("--categories", default=None, help="comma-separated filter")

    bp = sub.add_parser("build", help="build one shard (or a range)")
    bp.add_argument("--root", default=None)
    bp.add_argument("--out", required=True)
    bp.add_argument("--shards", type=int, default=1)
    bp.add_argument("--shard-id", type=int, default=None,
                    help="default: $SLURM_ARRAY_TASK_ID, else all shards in sequence")
    bp.add_argument("--workers", type=int, default=None)
    bp.add_argument("--limit", type=int, default=None,
                    help="cap files (walks the tree if no files.txt exists)")
    bp.add_argument("--categories", default=None)
    bp.add_argument("--include-problem", action="store_true",
                    help="also treat generic `problem` nodes as queries")
    bp.add_argument("--canon-scope", choices=("local", "paper", "none"), default="local")
    bp.add_argument("--ctx-canon-scope", choices=("local", "paper", "none"), default="paper")
    bp.add_argument("--no-canon", action="store_true",
                    help="skip canonical views entirely (~20x faster; raw arm only)")
    bp.add_argument("--ctx-depth", type=int, default=1)
    bp.add_argument("--max-neighbours", type=int, default=4)
    bp.add_argument("--max-ctx-chars", type=int, default=600)
    bp.add_argument("--min-words", type=int, default=6)
    bp.add_argument("--no-ctx-nodes", action="store_true",
                    help="don't emit definition/assumption records (disables ctx-late)")
    bp.add_argument("--status-dir", default=None)
    bp.add_argument("--log-every", type=int, default=500)
    bp.add_argument("--force", action="store_true", help="rebuild finished shards")

    args = ap.parse_args()
    root = Path(args.root) if args.root else None
    if root is None:
        from shared.corpus import DEFAULT_ROOT
        root = DEFAULT_ROOT
    out_dir = Path(args.out)

    if args.cmd == "plan":
        cats = args.categories.split(",") if args.categories else None
        plan_files(root, out_dir, limit=args.limit, categories=cats)
        return

    try:
        files = load_files(out_dir)
    except FileNotFoundError:
        cats = args.categories.split(",") if args.categories else None
        print("[textstore] no files.txt — planning inline (fine locally, "
              "run `plan` separately on the cluster)", file=sys.stderr, flush=True)
        files = plan_files(root, out_dir, limit=args.limit, categories=cats)

    cfg = _cfg_from_args(args)
    _write_manifest(out_dir, cfg, root, args.shards, len(files))
    workers = args.workers or _default_workers()
    status_dir = Path(args.status_dir) if args.status_dir else out_dir / "status"

    env_task = os.environ.get("SLURM_ARRAY_TASK_ID")
    if args.shard_id is not None:
        shard_ids = [args.shard_id]
    elif env_task is not None:
        shard_ids = [int(env_task)]
    else:
        shard_ids = list(range(args.shards))

    total = 0
    for sid in shard_ids:
        total += build_shard(root, out_dir, files, sid, args.shards, cfg,
                             workers=workers, status_dir=status_dir,
                             log_every=args.log_every, force=args.force)
    print(f"[textstore] {total:,} rows written across {len(shard_ids)} shard(s) "
          f"-> {out_dir}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
