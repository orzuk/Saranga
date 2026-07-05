"""T-ALIGN A2 — bipartite node alignment (wraps src/graph_alignment).

Thin adapter: turns two Paper records into the graph dicts that
``graph_alignment.align_graphs`` expects and runs its iterative Hungarian +
structural-refinement aligner. sigma='jaccard' (light, no GPU) or 'embedding'
(bge-large via the existing embedding_sigma). Returns the raw align_graphs
result dict: {'matching': {a_id->b_id}, 'score', 'node_score', ...}.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

import graph_alignment as ga  # noqa: E402

_SIGMA = {
    "jaccard": ga.jaccard_sim,
    "statement": ga.jaccard_statement,
    "combined": ga.jaccard_combined,
    "embedding": ga.embedding_sim,   # lazy-loads sentence-transformers
}


# graph_alignment.node_text does n.get("name", "") which returns None when the
# key is present but null (common in real nodes). Coerce text fields to strings
# so the imported aligner never sees None. We copy nodes; originals untouched.
_TEXT_FIELDS = ("name", "statement", "clean_text", "proof_strategy")


def _sanitize(node: dict) -> dict:
    m = dict(node)
    for f in _TEXT_FIELDS:
        if m.get(f) is None:
            m[f] = ""
    for f in ("assumptions", "conclusions"):
        if m.get(f) is None:
            m[f] = ""
    return m


def _to_graph(paper) -> dict:
    return {"nodes": [_sanitize(n) for n in paper.nodes],
            "edges": list(paper.edges)}


def align(paper_a, paper_b, *, sigma: str = "jaccard", alpha: float = 0.5,
          threshold: float = 0.1, n_iters: int = 5) -> dict:
    sigma_fn = _SIGMA.get(sigma, ga.jaccard_sim)
    return ga.align_graphs(_to_graph(paper_a), _to_graph(paper_b),
                           sigma_fn=sigma_fn, alpha=alpha,
                           threshold=threshold, n_iters=n_iters)


def significance(paper_a, paper_b, observed_score: float, *, sigma: str = "jaccard",
                 n_permutations: int = 200) -> tuple[float, float]:
    """Monte-Carlo z, p for an observed alignment score (calibration)."""
    sigma_fn = _SIGMA.get(sigma, ga.jaccard_sim)
    return ga.significance_test(_to_graph(paper_a), _to_graph(paper_b),
                                observed_score, sigma_fn=sigma_fn,
                                n_permutations=n_permutations)
