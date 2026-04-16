"""
Canonical-aware Jaccard sigma.

Wraps the existing jaccard_sim from scripts.graph_alignment, but swaps in
the *_canonical_local fields on each node before computing similarity.

Fields swapped (when a _canonical_local counterpart exists and is non-empty):
    statement      -> statement_canonical_local
    raw_latex      -> raw_latex_canonical_local
    assumptions    -> assumptions_canonical_local
    conclusions    -> conclusions_canonical_local
    name           -> name_canonical_local

Use as:
    python scripts/run_alignment_benchmark.py \\
        --config ... \\
        --sigma-import scripts.canonicalize.jaccard_canonical_sigma.sigma \\
        ...
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sibling "scripts/*.py" importable even when run via -m
_REPO_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_REPO_SCRIPTS))

# Import the baseline jaccard similarity from graph_alignment.py.
# We wrap it, not replace it.
try:
    from graph_alignment import jaccard_sim  # type: ignore
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "Could not import `jaccard_sim` from graph_alignment. Ensure "
        "scripts/graph_alignment.py exists and exposes jaccard_sim."
    ) from e


_FIELDS_WITH_CANONICAL = ["statement", "raw_latex", "name"]
_LIST_FIELDS_WITH_CANONICAL = ["assumptions", "conclusions"]


def _swap_to_canonical(node: dict) -> dict:
    """Return a new node dict where string fields are overridden by their
    *_canonical_local counterparts, if those exist and are non-empty.

    Leaves the original fields alone if no canonical version exists
    (graceful fallback).
    """
    out = dict(node)
    for f in _FIELDS_WITH_CANONICAL:
        c_field = f"{f}_canonical_local"
        if c_field in out and out[c_field]:
            out[f] = out[c_field]
    for f in _LIST_FIELDS_WITH_CANONICAL:
        c_field = f"{f}_canonical_local"
        if c_field in out and out[c_field]:
            out[f] = out[c_field]
    return out


def sigma(node_a: dict, node_b: dict) -> float:
    """Jaccard similarity computed on canonicalized text fields."""
    return jaccard_sim(_swap_to_canonical(node_a), _swap_to_canonical(node_b))
