"""T-PLAG P1 — lexical fingerprint detector (MinHash + LSH over node text).

Cheapest rung of the plagiarism ladder: no GPU, no API. Builds node-level
shingle signatures for the whole corpus, LSH-buckets them, and returns ranked
cross-paper node pairs by estimated Jaccard. Aggregation to paper pairs is the
caller's job (sum/max of node-pair scores).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE / "shared", _SUITE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import node_norm_text  # noqa: E402
from shared.shingle import LSHIndex, MinHasher, k_shingles  # noqa: E402


def detect_reuse(
    papers: Sequence,
    *,
    k: int = 5,
    num_perm: int = 128,
    bands: int = 32,
    min_jaccard: float = 0.2,
    min_words: int = 8,
) -> list[tuple[str, str, float]]:
    """Return ranked (node_key_a, node_key_b, est_jaccard) cross-paper pairs."""
    hasher = MinHasher(num_perm=num_perm, seed=1)
    index = LSHIndex(num_perm=num_perm, bands=bands)
    for p in papers:
        for n in p.nodes:
            txt = node_norm_text(n)
            if len(txt.split()) < min_words:
                continue
            sig = hasher.signature(k_shingles(txt, k=k))
            index.add(f"{p.paper_id}::{n.get('id')}", p.paper_id, sig)
    return index.scored_pairs(cross_paper_only=True, min_jaccard=min_jaccard)
