"""
Split-field Jaccard sigma: compare assumptions, conclusions, and name
SEPARATELY, then combine with weighted average.

Default weights (tunable):
  name:        0.1   (short, often missing)
  assumptions: 0.2   (diverge across frameworks — RIP vs CS conditions)
  conclusions: 0.7   (carry shared semantic content — "l1 recovers signal")

Falls back to full-statement Jaccard when neither node has separated
assumptions/conclusions (e.g., definitions, proofs, equations).

Usage:
    python scripts/run_alignment_benchmark.py \
        --sigma-import scripts.canonicalize.jaccard_split_sigma.sigma ...
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_REPO_SCRIPTS))

from graph_alignment import type_compat  # type: ignore  # noqa: F401

# ── Weights (edit here to tune) ──────────────────────────────────────────
W_NAME = 0.1
W_ASSUMPTIONS = 0.2
W_CONCLUSIONS = 0.7
# Must sum to 1.0 for interpretability, but the pipeline doesn't require it.

# Tokenizer and set metric come from the one canonical implementation; this
# file's copies were byte-identical to graph_alignment's (its own comment said
# "same as graph_alignment.py for consistency" — now enforced rather than
# hoped for).
from node_similarity import Profile as _Profile          # noqa: E402
from node_similarity import jaccard_sets as _jaccard     # noqa: E402
from node_similarity import tokenize as _ns_tokenize     # noqa: E402


def _tokenize(text: str) -> set:
    return _ns_tokenize(text, _Profile.ALIGNMENT)


def _concat_list(items) -> str:
    if isinstance(items, list):
        return " ".join(str(x) for x in items)
    if items:
        return str(items)
    return ""


def _full_text(node: dict) -> str:
    parts = [node.get("name", ""), node.get("statement", "")]
    for fld in ("assumptions", "conclusions"):
        v = node.get(fld)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
        elif v:
            parts.append(str(v))
    return " ".join(parts)


def sigma(node_a: dict, node_b: dict) -> float:
    """Split-field Jaccard with type compatibility."""

    a_assum = node_a.get("assumptions", [])
    a_concl = node_a.get("conclusions", [])
    b_assum = node_b.get("assumptions", [])
    b_concl = node_b.get("conclusions", [])

    has_fields_a = bool(a_assum) or bool(a_concl)
    has_fields_b = bool(b_assum) or bool(b_concl)

    if has_fields_a and has_fields_b:
        # Both have structured assumption/conclusion fields → split compare
        j_name = _jaccard(
            _tokenize(node_a.get("name", "")),
            _tokenize(node_b.get("name", "")),
        )
        j_assum = _jaccard(
            _tokenize(_concat_list(a_assum)),
            _tokenize(_concat_list(b_assum)),
        )
        j_concl = _jaccard(
            _tokenize(_concat_list(a_concl)),
            _tokenize(_concat_list(b_concl)),
        )
        j = W_NAME * j_name + W_ASSUMPTIONS * j_assum + W_CONCLUSIONS * j_concl
    else:
        # Fallback: full-statement bag-of-words (same as original jaccard_sim)
        j = _jaccard(_tokenize(_full_text(node_a)), _tokenize(_full_text(node_b)))

    # Type compatibility
    ta = node_a.get("type", node_a.get("kind", ""))
    tb = node_b.get("type", node_b.get("kind", ""))
    return j * type_compat(ta, tb)
