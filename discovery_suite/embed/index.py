"""Stage 3 — nearest-neighbour search over the vector store.

The scale argument that justifies the whole approach, stated once:

    A bi-encoder is O(N), not O(N^2). We run 1.6M forward passes ONCE. Scoring is
    then a dense matmul — 15,143 problems x 1,589,327 theorems x 1024 dims is
    2.4e13 FLOPs, well under a minute of L40s tensor-core time, against ~57 CPU
    minutes for the lexical inverted-index rank. Pairs are never materialized
    until the cross-encoder rerank, and only for the top-k survivors.

Structure is map-reduce over DOC shards, which is what keeps this working when
the corpus goes from 100k to 3M papers:

    map     one task holds the (small) query matrix and ONE doc shard, scores
            them, and writes its own per-query top-k.
    reduce  merge the per-shard top-k lists into a global one.

Nothing ever needs the whole doc matrix in memory, and tasks share no state.

Hard filters are applied INSIDE the scoring loop, not afterwards: a resolution
cannot predate its problem, and a paper does not resolve itself. Filtering after
top-k would silently shrink k (the list would fill with self-matches, which score
~1.0 and would otherwise crowd out every real candidate).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

NEG = np.float32(-1e9)


# ── ctx-late: the free contextual view ───────────────────────────────────────

def build_ctx_late(
    vecs: np.ndarray,
    metas: Sequence[dict],
    *,
    alpha: float = 0.7,
) -> np.ndarray:
    """v = normalize(α·v_node + (1-α)·Σ wᵢ·v_neighbourᵢ) — no extra GPU work.

    The neighbours of a node are always in the same shard: shards are split by
    FILE and a paper is one file, so every ``ctx_keys`` entry resolves locally.
    That is what makes this view free rather than a distributed join.

    α is the dial between "the statement itself" (α=1, identical to the `node`
    view) and "what it is built on" (α→0). It is swept post-hoc on the benchmark
    because nothing here needs re-encoding.
    """
    if vecs.shape[0] == 0:
        return vecs
    row_of = {m["key"]: i for i, m in enumerate(metas)}
    base = vecs.astype(np.float32)
    out = alpha * base
    n_ctx = 0
    for i, m in enumerate(metas):
        keys = m.get("ctx_keys") or []
        if isinstance(keys, str):
            keys = json.loads(keys)
        if not keys:
            continue
        weights = m.get("ctx_weights") or []
        if isinstance(weights, str):
            weights = json.loads(weights)
        rows, ws = [], []
        for k, w in zip(keys, list(weights) + [1.0] * len(keys)):
            j = row_of.get(k)
            if j is not None:
                rows.append(j)
                ws.append(float(w))
        if not rows:
            continue
        w = np.asarray(ws, dtype=np.float32)
        w /= max(w.sum(), 1e-9)
        out[i] += (1.0 - alpha) * (w[:, None] * base[rows]).sum(0)
        n_ctx += 1
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return (out / np.maximum(norms, 1e-12)).astype(np.float16)


# ── filters ──────────────────────────────────────────────────────────────────

def code_ids(values: Iterable[str], table: dict) -> np.ndarray:
    """Map strings to dense ints using a shared, growing table.

    Paper-identity filtering needs an (nq, nd) equality test; doing that on
    Python strings is orders of magnitude slower than on int64. The table is
    shared between the query side and every doc shard so codes stay comparable.
    """
    return np.fromiter((table.setdefault(v, len(table)) for v in values),
                       dtype=np.int64, count=-1)


class QuerySide:
    """The (small) query matrix plus the metadata the filters need."""

    def __init__(self, vecs: np.ndarray, metas: Sequence[dict],
                 paper_table: Optional[dict] = None) -> None:
        self.vecs = np.ascontiguousarray(vecs)
        self.metas = list(metas)
        self.paper_table = paper_table if paper_table is not None else {}
        self.paper = code_ids((m["paper_id"] for m in self.metas), self.paper_table)
        self.yymm = np.asarray([int(m.get("yymm") or 0) for m in self.metas], dtype=np.int64)
        self.keys = [m["key"] for m in self.metas]

    def __len__(self) -> int:
        return len(self.metas)


def _mask_block(q: QuerySide, q0: int, q1: int, d_paper: np.ndarray,
                d_yymm: np.ndarray, *, temporal: bool) -> np.ndarray:
    """True where the (query, doc) pair is INVALID and must be suppressed."""
    bad = q.paper[q0:q1, None] == d_paper[None, :]           # same paper
    if temporal:
        bad |= d_yymm[None, :] < q.yymm[q0:q1, None]         # solution predates problem
    return bad


# ── backends ─────────────────────────────────────────────────────────────────

def _topk_torch(qv, dv, k, device):
    import torch
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    with torch.no_grad():
        a = torch.as_tensor(np.ascontiguousarray(qv)).to(device=device, dtype=dtype)
        b = torch.as_tensor(np.ascontiguousarray(dv)).to(device=device, dtype=dtype)
        return a @ b.T


def search_shard(
    q: QuerySide,
    d_vecs: np.ndarray,
    d_metas: Sequence[dict],
    *,
    k: int = 50,
    backend: str = "auto",
    temporal: bool = True,
    min_score: float = 0.0,
    q_block: int = 1024,
    paper_table: Optional[dict] = None,
    on_block=None,
) -> tuple[np.ndarray, np.ndarray]:
    """Score every query against ONE doc shard; return per-query top-k.

    Returns ``(doc_idx[nq, k] int32, score[nq, k] float32)`` where doc_idx
    indexes ``d_metas`` (-1 padding when fewer than k pairs survive the filters).
    """
    nq, nd = len(q), int(d_vecs.shape[0])
    kk = min(k, nd) if nd else 0
    idx_out = np.full((nq, k), -1, dtype=np.int32)
    sc_out = np.full((nq, k), NEG, dtype=np.float32)
    if nq == 0 or nd == 0:
        return idx_out, sc_out

    table = paper_table if paper_table is not None else q.paper_table
    d_paper = code_ids((m["paper_id"] for m in d_metas), table)
    d_yymm = np.asarray([int(m.get("yymm") or 0) for m in d_metas], dtype=np.int64)

    if backend == "auto":
        backend = "torch" if _torch_device() != "cpu" else "numpy"
    device = _torch_device() if backend == "torch" else "cpu"

    dv = np.ascontiguousarray(d_vecs)
    for q0 in range(0, nq, q_block):
        q1 = min(q0 + q_block, nq)
        qv = q.vecs[q0:q1]
        if backend == "torch":
            scores = _topk_torch(qv, dv, kk, device).float().cpu().numpy()
        else:
            scores = (qv.astype(np.float32) @ dv.astype(np.float32).T)
        scores[_mask_block(q, q0, q1, d_paper, d_yymm, temporal=temporal)] = NEG
        if min_score > 0:
            scores[scores < min_score] = NEG
        # argpartition is O(nd) per row vs O(nd log nd) for a full sort; the
        # exact order only matters within the k we keep.
        part = np.argpartition(-scores, kk - 1, axis=1)[:, :kk] if kk < nd else \
            np.argsort(-scores, axis=1)[:, :kk]
        rows = np.arange(scores.shape[0])[:, None]
        top_sc = scores[rows, part]
        order = np.argsort(-top_sc, axis=1)
        idx_out[q0:q1, :kk] = part[rows, order].astype(np.int32)
        sc_out[q0:q1, :kk] = top_sc[rows, order]
        if on_block is not None:
            on_block(q1 - q0)
    # Drop filtered-out placeholders so the reduce never sees a fake candidate.
    idx_out[sc_out <= NEG / 2] = -1
    return idx_out, sc_out


def _torch_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


# ── faiss (only needed past ~10M docs) ───────────────────────────────────────

def faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
        return True
    except ImportError:
        return False


def search_shard_faiss(
    q: QuerySide,
    d_vecs: np.ndarray,
    d_metas: Sequence[dict],
    *,
    k: int = 50,
    temporal: bool = True,
    index_type: str = "hnsw",
    over_fetch: int = 4,
    nlist: int = 4096,
    nprobe: int = 32,
    m_pq: int = 32,
) -> tuple[np.ndarray, np.ndarray]:
    """Approximate search for when exact GEMM stops being cheap (3M corpus).

    ANN cannot apply our filters inside the search, so it over-fetches ``k *
    over_fetch`` and filters afterwards. That is an approximation with a real
    failure mode — if a query's whole neighbourhood is same-paper or
    future-dated, over-fetch can come back short — which is exactly why the 100k
    run uses the exact backend and this is reserved for scales where exact is
    infeasible. Recall against `search_shard` should be measured before trusting it.
    """
    import faiss
    nd, dim = d_vecs.shape
    xb = np.ascontiguousarray(d_vecs, dtype=np.float32)
    if index_type == "hnsw":
        index = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efSearch = max(64, k * over_fetch)
    elif index_type == "ivfpq":
        quant = faiss.IndexFlatIP(dim)
        index = faiss.IndexIVFPQ(quant, dim, min(nlist, max(1, nd // 40)), m_pq, 8)
        index.train(xb)
        index.nprobe = nprobe
    else:
        index = faiss.IndexFlatIP(dim)
    index.add(xb)

    table = q.paper_table
    d_paper = code_ids((m["paper_id"] for m in d_metas), table)
    d_yymm = np.asarray([int(m.get("yymm") or 0) for m in d_metas], dtype=np.int64)

    fetch = min(nd, k * over_fetch)
    scores, ids = index.search(np.ascontiguousarray(q.vecs, dtype=np.float32), fetch)
    idx_out = np.full((len(q), k), -1, dtype=np.int32)
    sc_out = np.full((len(q), k), NEG, dtype=np.float32)
    for i in range(len(q)):
        kept = 0
        for j, s in zip(ids[i], scores[i]):
            if j < 0:
                continue
            if d_paper[j] == q.paper[i]:
                continue
            if temporal and d_yymm[j] < q.yymm[i]:
                continue
            idx_out[i, kept] = j
            sc_out[i, kept] = s
            kept += 1
            if kept >= k:
                break
    return idx_out, sc_out


# ── reduce ───────────────────────────────────────────────────────────────────

class TopKMerger:
    """Running per-query top-k across doc shards.

    Keeps only k per query, so memory is O(nq * k) no matter how many shards or
    how large the corpus — the property that makes the 3M run a scheduling
    problem rather than a memory problem.
    """

    def __init__(self, n_queries: int, k: int) -> None:
        self.k = k
        self.scores = np.full((n_queries, k), NEG, dtype=np.float32)
        self.shard = np.full((n_queries, k), -1, dtype=np.int32)
        self.doc = np.full((n_queries, k), -1, dtype=np.int32)

    def add(self, shard_id: int, doc_idx: np.ndarray, scores: np.ndarray) -> None:
        cat_s = np.concatenate([self.scores, scores.astype(np.float32)], axis=1)
        cat_d = np.concatenate([self.doc, doc_idx.astype(np.int32)], axis=1)
        cat_sh = np.concatenate(
            [self.shard,
             np.where(doc_idx >= 0, shard_id, -1).astype(np.int32)], axis=1)
        order = np.argsort(-cat_s, axis=1)[:, :self.k]
        rows = np.arange(cat_s.shape[0])[:, None]
        self.scores = cat_s[rows, order]
        self.doc = cat_d[rows, order]
        self.shard = cat_sh[rows, order]

    def results(self) -> Iterable[tuple[int, list[tuple[int, int, float]]]]:
        """Yield (query_row, [(shard_id, doc_idx, score), …]) best-first."""
        for i in range(self.scores.shape[0]):
            hits = [(int(self.shard[i, j]), int(self.doc[i, j]), float(self.scores[i, j]))
                    for j in range(self.k)
                    if self.doc[i, j] >= 0 and self.scores[i, j] > NEG / 2]
            yield i, hits


def save_partial(path: Path, shard_id: int, doc_idx: np.ndarray,
                 scores: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write through an explicit handle: np.savez_compressed appends '.npz' to any
    # path that doesn't already end in it, so passing a '*.npz.tmp' name would
    # silently produce '*.npz.tmp.npz' and the rename below would fail.
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        np.savez_compressed(fh, shard_id=np.int32(shard_id), doc_idx=doc_idx,
                            scores=scores)
    tmp.replace(path)


def load_partial(path: Path) -> tuple[int, np.ndarray, np.ndarray]:
    z = np.load(path)
    return int(z["shard_id"]), z["doc_idx"], z["scores"]
