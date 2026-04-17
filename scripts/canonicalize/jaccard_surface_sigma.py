"""
Surface-only canonicalized Jaccard sigma.

Applies L0 surface normalization (operator/bracket/arrow/fraction/etc.)
WITHOUT variable alpha-renaming (which has known bugs under Jaccard).

Use as:
    python scripts/run_alignment_benchmark.py \
        --sigma-import scripts.canonicalize.jaccard_surface_sigma.sigma ...
"""
import sys
from pathlib import Path

_REPO_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_REPO_SCRIPTS))

from graph_alignment import jaccard_sim  # type: ignore
from scripts.canonicalize.core import canonicalize_text

_STR_FIELDS = ["statement", "raw_latex", "name"]
_LIST_FIELDS = ["assumptions", "conclusions"]


def _surface_canonicalize(node: dict) -> dict:
    """Apply surface-only canonicalization (no variable rename) on the fly."""
    out = dict(node)
    for f in _STR_FIELDS:
        val = out.get(f, "")
        if isinstance(val, str) and val:
            out[f] = canonicalize_text(val, rename_map=None, prose_rewrites=False)
    for f in _LIST_FIELDS:
        items = out.get(f, [])
        if isinstance(items, list):
            out[f] = [canonicalize_text(x, rename_map=None) for x in items
                      if isinstance(x, str)]
    return out


def sigma(node_a: dict, node_b: dict) -> float:
    """Jaccard on surface-canonicalized text (no alpha-rename)."""
    return jaccard_sim(_surface_canonicalize(node_a), _surface_canonicalize(node_b))
