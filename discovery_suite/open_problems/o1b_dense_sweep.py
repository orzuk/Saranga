"""T-OPEN O1b — DENSE (semantic) problem->theorem candidate generation.

The semantic counterpart of ``sweep_open.py``. Same task, same population, same
temporal/self-paper rules, same output schema — a different similarity. Run both
and the difference is attributable to the matching function alone, which is the
comparison the paper needs.

    # everything in one process (local / small corpora)
    python discovery_suite/open_problems/o1b_dense_sweep.py all \
        --vectors $VECS --model qwen3-0.6b --view node --canon raw \
        --out runs/open_dense_qwen_node_raw.csv

    # cluster: map over doc shards, then reduce
    ... map --shard-id $SLURM_ARRAY_TASK_ID --partials $P
    ... reduce --partials $P --out runs/....csv

OUTPUT CONTRACT: the first nine columns are byte-identical to sweep_open.py's, so
``triage_open.py`` -> author gate -> ``batch_o4.py`` -> S2 citation gate all
consume dense output with no changes at all. Extra columns (method/model/view/
canon/rank) are appended; triage reads by name and ignores them.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from embed import encode as ENC  # noqa: E402
from embed import index as IDX  # noqa: E402
from embed.progress import Heartbeat, banner  # noqa: E402

#: sweep_open.py's header, verbatim. Do not reorder — downstream consumers and
#: the lexical/dense comparison both depend on these being the same nine columns.
SWEEP_COLUMNS = ["score", "problem_key", "problem_cat", "problem_type",
                 "theorem_key", "theorem_cat", "cross_category",
                 "problem_snippet", "theorem_snippet"]
EXTRA_COLUMNS = ["method", "model", "view", "canon", "rank"]


def _apply_view(vecs: np.ndarray, metas, view: str, alpha: float) -> np.ndarray:
    """ctx-late is assembled here from the cached node vectors; every other view
    was already materialized at encode time."""
    if view == "ctx-late":
        return IDX.build_ctx_late(vecs, metas, alpha=alpha)
    return vecs


def load_queries(vdir: Path, view: str, alpha: float,
                 *, roles=("query",)) -> IDX.QuerySide:
    """Concatenate the query vectors from every shard.

    Tiny by construction — 15k x 1024 fp16 is ~30MB — which is the whole reason
    the map step can be sharded over documents rather than queries.
    """
    keep = set(roles)
    vecs, metas = [], []
    for sid in ENC.list_vec_shards(vdir):
        m = ENC.read_meta(vdir, sid)
        if not m:
            continue
        v = np.asarray(ENC.read_vectors(vdir, sid, mmap=True))
        v = _apply_view(v, m, view, alpha)
        sel = [i for i, mm in enumerate(m) if mm.get("role") in keep]
        if sel:
            vecs.append(np.asarray(v)[sel])
            metas.extend(m[i] for i in sel)
    if not metas:
        raise SystemExit(f"[dense] no query nodes in {vdir} — check --roles and "
                         f"that the text store contains open_problem/conjecture nodes")
    return IDX.QuerySide(np.concatenate(vecs, axis=0), metas)


def map_shards(vdir: Path, q: IDX.QuerySide, shard_ids, *, k: int, view: str,
               alpha: float, backend: str, min_score: float, temporal: bool,
               doc_roles, partial_dir: Optional[Path], status_dir: Optional[Path],
               merger: Optional[IDX.TopKMerger] = None) -> IDX.TopKMerger:
    keep = set(doc_roles)
    merger = merger or IDX.TopKMerger(len(q), k)
    for sid in shard_ids:
        metas = ENC.read_meta(vdir, sid)
        if not metas:
            continue
        vecs = np.asarray(ENC.read_vectors(vdir, sid, mmap=True))
        vecs = _apply_view(vecs, metas, view, alpha)
        sel = [i for i, m in enumerate(metas) if m.get("role") in keep]
        if not sel:
            continue
        d_metas = [metas[i] for i in sel]
        d_vecs = np.asarray(vecs)[sel]
        hb = Heartbeat(f"dense.map.s{sid}", total=len(q), unit="queries",
                       status_dir=status_dir, every=4096,
                       extra={"shard": sid, "docs": len(d_metas)})
        doc_idx, scores = IDX.search_shard(
            q, d_vecs, d_metas, k=k, backend=backend, temporal=temporal,
            min_score=min_score, on_block=lambda n: hb.tick(n))
        hb.close(docs=len(d_metas))
        # search_shard indexes the ROLE-FILTERED doc list; everything downstream
        # (partials on disk, the reduce, write_csv) resolves against the full
        # shard meta. Remap here, once, so the two can never drift apart —
        # without this a theorem index silently resolves to whatever node sits
        # at that position in the unfiltered shard, e.g. a definition.
        lut = np.asarray(sel, dtype=np.int32)
        doc_idx = np.where(doc_idx >= 0, lut[np.clip(doc_idx, 0, None)], -1
                           ).astype(np.int32)
        if partial_dir is not None:
            IDX.save_partial(Path(partial_dir) / f"partial_{sid:05d}.npz",
                             sid, doc_idx, scores)
        merger.add(sid, doc_idx, scores)
    return merger


def write_csv(out: Path, vdir: Path, q: IDX.QuerySide, merger: IDX.TopKMerger,
              *, model: str, view: str, canon: str, method: str,
              min_score: float) -> int:
    """Resolve (shard, doc_idx) hits back to node keys and emit the triage CSV."""
    meta_cache: dict[int, list] = {}

    def dmeta(shard_id: int, doc_idx: int):
        if shard_id not in meta_cache:
            meta_cache[shard_id] = ENC.read_meta(vdir, shard_id)
        rows = meta_cache[shard_id]
        return rows[doc_idx] if 0 <= doc_idx < len(rows) else None

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(SWEEP_COLUMNS + EXTRA_COLUMNS)
        for qi, hits in merger.results():
            qm = q.metas[qi]
            for rank, (sid, di, score) in enumerate(hits, 1):
                if score < min_score:
                    continue
                dm = dmeta(sid, di)
                if dm is None:
                    continue
                qcat, dcat = qm.get("category") or "", dm.get("category") or ""
                cross = int(bool(qcat and dcat and qcat != dcat))
                w.writerow([
                    f"{score:.4f}", qm["key"], qcat, qm.get("ntype") or "",
                    dm["key"], dcat, cross,
                    (qm.get("snippet") or "")[:160],
                    (dm.get("snippet") or "")[:160],
                    method, model, view, canon, rank,
                ])
                rows_written += 1
    return rows_written


def _sorted_csv(path: Path) -> None:
    """Re-sort the CSV by descending score.

    sweep_open.py emits globally score-sorted rows and triage_open.py's
    --per-problem / top-N logic assumes that ordering, so the dense arm has to
    match it rather than emitting query-major order.
    """
    import pandas as pd
    df = pd.read_csv(path)
    if df.empty:
        return
    df = df.sort_values(["score", "problem_key", "theorem_key"],
                        ascending=[False, True, True], kind="mergesort")
    df.to_csv(path, index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("all", "map", "reduce"))
    ap.add_argument("--vectors", required=True, help="vector store root (encode.py --out)")
    ap.add_argument("--model", default="minilm")
    ap.add_argument("--view", default="node",
                    help="node | ctx-concat | concepts-only | ctx-late")
    ap.add_argument("--canon", choices=("raw", "canon"), default="raw")
    ap.add_argument("--alpha", type=float, default=0.7,
                    help="ctx-late mixing weight: 1.0 = pure node vector, "
                         "0.0 = pure neighbourhood. Swept post-hoc, no re-encoding")
    ap.add_argument("--top-k", type=int, default=50)
    ap.add_argument("--min-score", type=float, default=0.0,
                    help="cosine cutoff. Cosines are not comparable across "
                         "models, so leave at 0 and cut in triage instead")
    ap.add_argument("--backend", choices=("auto", "torch", "numpy"), default="auto")
    ap.add_argument("--no-temporal", action="store_true",
                    help="disable the 'solution cannot predate the problem' filter "
                         "(diagnostics only — it is a correctness rule, not a heuristic)")
    ap.add_argument("--doc-roles", default="doc")
    ap.add_argument("--query-roles", default="query")
    ap.add_argument("--shard-id", type=int, default=None)
    ap.add_argument("--shard-stride", type=int, default=1)
    ap.add_argument("--partials", default=None, help="dir for map-stage partials")
    ap.add_argument("--out", default=None, help="output CSV (all/reduce)")
    ap.add_argument("--status-dir", default=None)
    args = ap.parse_args()

    # ctx-late reuses the 'node' vectors, so it reads the node variant directory.
    enc_view = "node" if args.view in ("ctx-late",) else args.view
    vdir = ENC.variant_dir(Path(args.vectors), args.model, enc_view, args.canon)
    if not vdir.exists():
        sys.exit(f"[dense] no vectors at {vdir} — run embed.encode for "
                 f"model={args.model} view={enc_view} canon={args.canon} first")

    shards = ENC.list_vec_shards(vdir)
    if not shards:
        sys.exit(f"[dense] {vdir} has no shards")

    status_dir = Path(args.status_dir) if args.status_dir else vdir / "status"
    partial_dir = Path(args.partials) if args.partials else None
    t0 = time.time()

    q = load_queries(vdir, args.view, args.alpha,
                     roles=tuple(r.strip() for r in args.query_roles.split(",")))
    doc_roles = tuple(r.strip() for r in args.doc_roles.split(","))

    # Which shards THIS invocation touches. Counting docs over all shards from
    # every array task would mean N tasks each scanning every meta file — the
    # shared-metadata hammering that killed the download jobs. Map tasks count
    # only their own slice.
    if args.cmd == "map":
        start = args.shard_id if args.shard_id is not None else 0
        mine = [s for s in shards if s >= start and (s - start) % args.shard_stride == 0]
    else:
        mine = shards
    n_docs = sum(sum(1 for m in ENC.read_meta(vdir, s) if m.get("role") in set(doc_roles))
                 for s in mine)
    banner("dense", queries=len(q), docs=n_docs, shards=len(mine),
           shards_total=len(shards), pairs_to_score=len(q) * n_docs,
           top_k=args.top_k, model=args.model, view=args.view, canon=args.canon,
           backend=args.backend)

    if args.cmd == "map":
        if partial_dir is None:
            sys.exit("[dense] map requires --partials")
        map_shards(vdir, q, mine, k=args.top_k, view=args.view, alpha=args.alpha,
                   backend=args.backend, min_score=args.min_score,
                   temporal=not args.no_temporal, doc_roles=doc_roles,
                   partial_dir=partial_dir, status_dir=status_dir)
        print(f"[dense] mapped {len(mine)} shard(s) in {time.time()-t0:.0f}s "
              f"-> {partial_dir}", file=sys.stderr, flush=True)
        return

    if args.cmd == "reduce":
        if partial_dir is None or args.out is None:
            sys.exit("[dense] reduce requires --partials and --out")
        merger = IDX.TopKMerger(len(q), args.top_k)
        files = sorted(Path(partial_dir).glob("partial_*.npz"))
        if not files:
            sys.exit(f"[dense] no partials in {partial_dir}")
        hb = Heartbeat("dense.reduce", total=len(files), unit="partials",
                       status_dir=status_dir, every=1)
        for p in files:
            sid, doc_idx, scores = IDX.load_partial(p)
            merger.add(sid, doc_idx, scores)
            hb.tick()
        hb.close()
    else:  # all
        merger = map_shards(vdir, q, shards, k=args.top_k, view=args.view,
                            alpha=args.alpha, backend=args.backend,
                            min_score=args.min_score, temporal=not args.no_temporal,
                            doc_roles=doc_roles, partial_dir=partial_dir,
                            status_dir=status_dir)

    if args.out is None:
        sys.exit("[dense] --out is required")
    n = write_csv(Path(args.out), vdir, q, merger, model=args.model, view=args.view,
                  canon=args.canon, method="dense", min_score=args.min_score)
    _sorted_csv(Path(args.out))
    dt = time.time() - t0
    print(f"[dense] wrote {n:,} candidate pairs -> {args.out} in {dt:.0f}s "
          f"({len(q)*n_docs/max(dt,1e-9):,.0f} pairs/s scored)",
          file=sys.stderr, flush=True)
    side = Path(args.out).with_suffix(".meta.json")
    side.write_text(json.dumps({
        "model": args.model, "view": args.view, "canon": args.canon,
        "alpha": args.alpha, "top_k": args.top_k, "backend": args.backend,
        "queries": len(q), "docs": n_docs, "rows": n, "seconds": round(dt, 1),
        "vectors": str(vdir), "encoder": ENC.read_vec_manifest(vdir),
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
