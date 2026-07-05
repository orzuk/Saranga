"""MinHash + LSH shingling — the light (P1) matching primitive.

Deterministic (crc32 shingle hashes, seeded permutations) so index-time and
query-time signatures agree and runs are reproducible. Node-granular: each node
becomes a shingle set → MinHash signature; LSH banding yields candidate node
pairs sharing sub-signatures, which the task heads aggregate to paper pairs.

This is the graph-native descendant of the old Bloom-filter n-gram stage
(Plagiarism Detection Pipeline Report, Stage 3), but per-node and math-aware.
"""
from __future__ import annotations

import zlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np

_MERSENNE = (1 << 61) - 1
_MAX = np.uint64(_MERSENNE)


def k_shingles(text: str, k: int = 5) -> set[str]:
    """Word-level k-shingles (k consecutive tokens joined by space)."""
    toks = text.split()
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def _hash_shingles(shingles: Iterable[str]) -> np.ndarray:
    arr = [np.uint64(zlib.crc32(s.encode("utf-8"))) for s in shingles]
    return np.array(arr, dtype=np.uint64) if arr else np.empty(0, dtype=np.uint64)


class MinHasher:
    """Classic (a*h + b) mod prime MinHash with `num_perm` permutations."""

    def __init__(self, num_perm: int = 128, seed: int = 1):
        rng = np.random.default_rng(seed)
        self.num_perm = num_perm
        self.a = rng.integers(1, _MERSENNE, size=num_perm, dtype=np.uint64)
        self.b = rng.integers(0, _MERSENNE, size=num_perm, dtype=np.uint64)

    def signature(self, shingles: Iterable[str]) -> np.ndarray:
        h = _hash_shingles(shingles)
        if h.size == 0:
            return np.full(self.num_perm, _MAX, dtype=np.uint64)
        # (num_perm, n_shingles) hashed permutations, then row-wise min.
        M = (self.a[:, None] * h[None, :] + self.b[:, None]) % _MERSENNE
        return M.min(axis=1)


def jaccard_estimate(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
    return float(np.mean(sig_a == sig_b))


@dataclass
class LSHItem:
    key: str            # global node key (paper_id::node_id)
    paper_id: str
    signature: np.ndarray


class LSHIndex:
    """Banded LSH over MinHash signatures → cross-paper candidate node pairs."""

    def __init__(self, num_perm: int = 128, bands: int = 32):
        assert num_perm % bands == 0, "bands must divide num_perm"
        self.num_perm = num_perm
        self.bands = bands
        self.rows = num_perm // bands
        self._buckets: list[dict[bytes, list[int]]] = [defaultdict(list) for _ in range(bands)]
        self._items: list[LSHItem] = []

    def add(self, key: str, paper_id: str, signature: np.ndarray) -> None:
        idx = len(self._items)
        self._items.append(LSHItem(key, paper_id, signature))
        for bi in range(self.bands):
            band = signature[bi * self.rows:(bi + 1) * self.rows].tobytes()
            self._buckets[bi][band].append(idx)

    def candidate_pairs(self, *, cross_paper_only: bool = True,
                        max_bucket: int = 400) -> set[tuple[int, int]]:
        """Enumerate in-bucket candidate pairs. Buckets larger than `max_bucket`
        are skipped: at corpus scale these are boilerplate/near-empty nodes that
        collide en masse and would blow up O(bucket^2). None = no cap."""
        pairs: set[tuple[int, int]] = set()
        for buckets in self._buckets:
            for members in buckets.values():
                if len(members) < 2:
                    continue
                if max_bucket is not None and len(members) > max_bucket:
                    continue
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        a, b = members[i], members[j]
                        if cross_paper_only and self._items[a].paper_id == self._items[b].paper_id:
                            continue
                        pairs.add((a, b) if a < b else (b, a))
        return pairs

    def item(self, idx: int) -> LSHItem:
        return self._items[idx]

    def scored_pairs(
        self, *, cross_paper_only: bool = True, min_jaccard: float = 0.0,
        max_bucket: int = 400
    ) -> list[tuple[str, str, float]]:
        """Ranked (key_a, key_b, est_jaccard), high→low, above min_jaccard."""
        out: list[tuple[str, str, float]] = []
        for a, b in self.candidate_pairs(cross_paper_only=cross_paper_only,
                                         max_bucket=max_bucket):
            s = jaccard_estimate(self._items[a].signature, self._items[b].signature)
            if s >= min_jaccard:
                out.append((self._items[a].key, self._items[b].key, s))
        out.sort(key=lambda x: -x[2])
        return out
