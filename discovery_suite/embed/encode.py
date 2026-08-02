"""Stage 2 — text-store shard -> fp16 L2-normalized vectors.

    python -m embed.encode --store $STORE --out $VECS \
        --model qwen3-0.6b --view node --canon raw \
        --shard-id $SLURM_ARRAY_TASK_ID

One vector file per (model, view, canon, shard). Resume = skip shards that
already have a ``.done`` marker, so a job array that hits the wall clock can be
resubmitted unchanged.

Queries and documents are encoded SEPARATELY even though they land in the same
file, because instruction-tuned encoders are asymmetric: an open problem is
wrapped in "Instruct: …\\nQuery: " and a theorem is not. Getting this backwards
silently costs several points of recall, so role comes from the text store rather
than from a flag.

Layout:
    <out>/<model>/<view>__<canon>/shard_%05d.f16.npy    (n, dim) float16, unit norm
                                 /shard_%05d.meta.jsonl.gz   key/paper/yymm/role/…
                                 /shard_%05d.done
                                 /manifest.json
The meta file carries everything search needs (paper_id, yymm, category, role,
ctx_keys), so the retrieval stage never has to reopen the text store.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator, Optional, Sequence

import numpy as np

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from embed import textstore as TS  # noqa: E402
from embed import views as V  # noqa: E402
from embed.models import EMBEDDERS, Embedder, get_card, pick_device  # noqa: E402
from embed.progress import Heartbeat, banner  # noqa: E402

#: Metadata carried alongside every vector — the minimum search needs.
META_FIELDS = ("key", "paper_id", "year", "yymm", "category", "ntype", "role",
               "n_words", "ctx_keys", "ctx_weights")


# ── vector store layout ──────────────────────────────────────────────────────

def variant_dir(out_root: Path, model: str, view: str, canon: str) -> Path:
    """One directory per experimental arm; the name IS the arm's identity."""
    return Path(out_root) / model / f"{view}__{canon}"


def vec_path(vdir: Path, shard_id: int) -> Path:
    return Path(vdir) / f"shard_{shard_id:05d}.f16.npy"


def meta_path(vdir: Path, shard_id: int) -> Path:
    return Path(vdir) / f"shard_{shard_id:05d}.meta.jsonl.gz"


def vdone_path(vdir: Path, shard_id: int) -> Path:
    return Path(vdir) / f"shard_{shard_id:05d}.done"


def write_vectors(vdir: Path, shard_id: int, vecs: np.ndarray,
                  metas: Sequence[dict]) -> None:
    """Atomic: temp files then rename, so a killed job never leaves a half
    array that a resume would mistake for finished work."""
    vdir = Path(vdir)
    vdir.mkdir(parents=True, exist_ok=True)
    vp, mp_ = vec_path(vdir, shard_id), meta_path(vdir, shard_id)
    vtmp, mtmp = vp.with_name(vp.name + ".tmp"), mp_.with_name(mp_.name + ".tmp")
    # Explicit handle: np.save appends '.npy' to any path not already ending in
    # it, so saving to a '*.tmp' name would land in '*.tmp.npy' and the rename
    # below would fail on a file that isn't there.
    with open(vtmp, "wb") as fh:
        np.save(fh, vecs.astype(np.float16, copy=False))
    with gzip.open(mtmp, "wt", encoding="utf-8") as fh:
        for m in metas:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    os.replace(vtmp, vp)
    os.replace(mtmp, mp_)
    vdone_path(vdir, shard_id).write_text(
        json.dumps({"rows": int(vecs.shape[0]), "dim": int(vecs.shape[1]),
                    "ts": time.time()}), encoding="utf-8")


def read_vectors(vdir: Path, shard_id: int, *, mmap: bool = True) -> np.ndarray:
    """Load a vector shard. mmap by default — the search stage streams shards and
    should never pull a whole corpus of vectors into RAM at once."""
    return np.load(vec_path(vdir, shard_id), mmap_mode="r" if mmap else None)


def read_meta(vdir: Path, shard_id: int) -> list[dict]:
    p = meta_path(vdir, shard_id)
    if not p.exists():
        return []
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def list_vec_shards(vdir: Path) -> list[int]:
    out = []
    for p in sorted(Path(vdir).glob("shard_*.f16.npy")):
        try:
            out.append(int(p.name.split("_")[1].split(".")[0]))
        except (IndexError, ValueError):
            continue
    return out


def read_vec_manifest(vdir: Path) -> dict:
    p = Path(vdir) / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# ── encoding one shard ───────────────────────────────────────────────────────

def encode_shard(
    store: Path,
    vdir: Path,
    shard_id: int,
    embedder: Embedder,
    *,
    view: str,
    canon: str,
    roles: Sequence[str] = ("query", "doc", "ctx"),
    status_dir: Optional[Path] = None,
    log_every: int = 2000,
    force: bool = False,
) -> int:
    if vdone_path(vdir, shard_id).exists() and not force:
        print(f"[encode] shard {shard_id} already done — skipping", file=sys.stderr, flush=True)
        return 0

    column = V.column_for(view, canon == "canon")
    keep = set(roles)
    rows = [r for r in TS.read_shard(store, shard_id) if r.get("role") in keep]
    if not rows:
        write_vectors(vdir, shard_id, np.zeros((0, embedder.dim or 1), np.float16), [])
        return 0

    # Fall back to the plain node text when a view's column is empty for a row
    # (a ctx-only node has no ctx-concat string, concepts may be absent). An
    # empty string would otherwise become a meaningless near-constant vector
    # that matches everything.
    texts, metas = [], []
    n_fallback = 0
    for r in rows:
        t = (r.get(column) or "").strip()
        if not t:
            t = (r.get("text_canon") if canon == "canon" else "") or r.get("text_raw") or ""
            n_fallback += 1
        texts.append(t)
        meta = {k: r.get(k) for k in META_FIELDS}
        # Carry a snippet of the text ACTUALLY embedded. It makes the output CSV
        # self-describing (you can see what the model saw, per view) and spares
        # the reduce stage a second full pass over the text store.
        meta["snippet"] = " ".join(t.split())[:180]
        metas.append(meta)

    banner(f"encode.s{shard_id}", texts=len(texts), model=embedder.card.key,
           view=view, canon=canon, fallback=n_fallback, device=embedder.device)
    hb = Heartbeat(f"encode.s{shard_id}", total=len(texts), unit="texts",
                   status_dir=status_dir, every=log_every,
                   extra={"model": embedder.card.key, "view": view,
                          "canon": canon, "shard": shard_id})

    # Split by role so asymmetric models get the right instruction wrapper.
    q_idx = [i for i, m in enumerate(metas) if m["role"] == "query"]
    d_idx = [i for i, m in enumerate(metas) if m["role"] != "query"]
    out: Optional[np.ndarray] = None
    for idx, role in ((q_idx, "query"), (d_idx, "doc")):
        if not idx:
            continue
        vecs = embedder.encode([texts[i] for i in idx], role=role,
                               on_batch=lambda n: hb.tick(n))
        if out is None:
            out = np.zeros((len(texts), vecs.shape[1]), dtype=np.float16)
        out[idx] = vecs
    write_vectors(vdir, shard_id, out, metas)
    hb.close(rows=int(out.shape[0]), dim=int(out.shape[1]))
    return int(out.shape[0])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", required=True, help="text-store dir from textstore.py")
    ap.add_argument("--out", required=True, help="vector store root")
    ap.add_argument("--model", default="minilm", choices=sorted(EMBEDDERS))
    ap.add_argument("--view", default="node", choices=sorted(V.TEXT_VIEWS) + list(V.VECTOR_VIEWS),
                    help="ctx-late needs no encoding of its own — it reuses the "
                         "'node' vectors and is assembled at search time")
    ap.add_argument("--canon", choices=("raw", "canon"), default="raw")
    ap.add_argument("--roles", default=None,
                    help="node roles to encode. Default is view-aware: 'query,doc,ctx' "
                         "for the node view (ctx vectors are what ctx-late mixes in), "
                         "'query,doc' otherwise — a definition has no ctx-concat text "
                         "of its own, so encoding it there just duplicates its node "
                         "vector at ~25%% of the arm's GPU budget")
    ap.add_argument("--shard-id", type=int, default=None,
                    help="default: $SLURM_ARRAY_TASK_ID, else every shard in sequence")
    ap.add_argument("--shard-stride", type=int, default=1,
                    help="with --shard-id S, also do S+stride, S+2*stride, … "
                         "(fewer array tasks than shards)")
    ap.add_argument("--device", default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--dtype", default="auto")
    ap.add_argument("--status-dir", default=None)
    ap.add_argument("--log-every", type=int, default=2000)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    store = Path(args.store)
    view = args.view
    if view in V.VECTOR_VIEWS:
        print(f"[encode] '{view}' is a vector view — encoding the 'node' texts it "
              f"is built from instead (no extra GPU pass needed)", file=sys.stderr)
        view = "node"

    roles = tuple(r.strip() for r in args.roles.split(",")) if args.roles else (
        ("query", "doc", "ctx") if view == "node" else ("query", "doc"))

    vdir = variant_dir(Path(args.out), args.model, view, args.canon)
    vdir.mkdir(parents=True, exist_ok=True)

    shards = TS.list_shards(store)
    if not shards:
        sys.exit(f"[encode] no shards found in {store} — run textstore.py build first")

    env_task = os.environ.get("SLURM_ARRAY_TASK_ID")
    start = args.shard_id if args.shard_id is not None else (
        int(env_task) if env_task is not None else None)
    todo = shards if start is None else [s for s in shards
                                         if s >= start and (s - start) % args.shard_stride == 0]

    card = get_card(args.model)
    embedder = Embedder(card, device=args.device, dtype=args.dtype,
                        batch_size=args.batch_size, max_tokens=args.max_tokens)
    status_dir = Path(args.status_dir) if args.status_dir else vdir / "status"

    print(f"[encode] {args.model} view={args.view} canon={args.canon} "
          f"roles={','.join(roles)} device={pick_device(args.device)} "
          f"shards={todo}", file=sys.stderr, flush=True)

    t0, total = time.time(), 0
    for sid in todo:
        total += encode_shard(store, vdir, sid, embedder, view=view, canon=args.canon,
                              roles=roles, status_dir=status_dir,
                              log_every=args.log_every, force=args.force)

    manifest = {"model": args.model, "hf_id": card.hf_id, "view": args.view,
                "encoded_view": view, "canon": args.canon, "dim": embedder.dim,
                "max_tokens": embedder.max_tokens,
                "query_instruction": card.query_instruction,
                "store": str(store), "store_manifest": TS.read_manifest(store),
                "ts": time.time()}
    (vdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    dt = time.time() - t0
    print(f"[encode] {total:,} vectors in {dt:.0f}s ({total/max(dt,1e-9):,.0f}/s) "
          f"-> {vdir}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
