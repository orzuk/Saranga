"""
Improved sigma: α-rename + split-field comparison.

Uses:
  - α-rename via canonical fields (reads statement_canonical_local etc.)
  - Split-field: assumptions and conclusions compared separately with
    weighted average (0.2 assum + 0.7 concl + 0.1 name)
  - Hard Jaccard on natural tokens (proven to work, ratio 2.46)

Does NOT use (kept in math_tokenizer.py for future experiments):
  - Constructed tokens (operator/structure tokens — inflate negatives)
  - Soft Jaccard / Monge-Elkan (partial credit drowns signal)

Usage:
    python scripts/run_alignment_benchmark.py \
        --sigma-import scripts.canonicalize.improved_sigma.sigma ...
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_REPO_SCRIPTS))

from graph_alignment import type_compat  # type: ignore

# ── Weights for field splitting (tune as needed) ─────────────────────────
W_NAME = 0.1
W_ASSUMPTIONS = 0.2
W_CONCLUSIONS = 0.7

# ── Tokenizer (same as graph_alignment.py — natural tokens only) ─────────
_TOKEN_RE = re.compile(r"[a-zA-Z]+|\\[a-zA-Z]+|[0-9]+")


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return set(t.lower() for t in _TOKEN_RE.findall(str(text)))


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


# ── Field access helpers ─────────────────────────────────────────────────

def _get_text(node: dict, field: str) -> str:
    """Read canonical version of a field if available, else original."""
    canonical = f"{field}_canonical_local"
    val = node.get(canonical) or node.get(field, "")
    if isinstance(val, list):
        return " ".join(str(x) for x in val)
    return str(val) if val else ""


def _get_list_text(node: dict, field: str) -> str:
    """Read canonical list field, concatenate to string."""
    canonical = f"{field}_canonical_local"
    items = node.get(canonical) or node.get(field, [])
    if isinstance(items, list):
        return " ".join(str(x) for x in items)
    return str(items) if items else ""


def _full_text(node: dict) -> str:
    """All text fields concatenated (fallback for nodes without split fields)."""
    parts = [
        _get_text(node, "name"),
        _get_text(node, "statement"),
        _get_list_text(node, "assumptions"),
        _get_list_text(node, "conclusions"),
    ]
    return " ".join(p for p in parts if p)


# ── Main sigma ───────────────────────────────────────────────────────────

def sigma(node_a: dict, node_b: dict) -> float:
    """Improved sigma: α-rename (via canonical fields) + split-field + hard Jaccard.

    Reads *_canonical_local fields when present (from canonicalize_paper),
    falls back to original fields otherwise.
    """
    assum_a = _get_list_text(node_a, "assumptions")
    assum_b = _get_list_text(node_b, "assumptions")
    concl_a = _get_list_text(node_a, "conclusions")
    concl_b = _get_list_text(node_b, "conclusions")

    has_split_a = bool(assum_a.strip()) or bool(concl_a.strip())
    has_split_b = bool(assum_b.strip()) or bool(concl_b.strip())

    if has_split_a and has_split_b:
        s = (W_NAME * _jaccard(_tokenize(_get_text(node_a, "name")),
                                _tokenize(_get_text(node_b, "name")))
             + W_ASSUMPTIONS * _jaccard(_tokenize(assum_a), _tokenize(assum_b))
             + W_CONCLUSIONS * _jaccard(_tokenize(concl_a), _tokenize(concl_b)))
    else:
        s = _jaccard(_tokenize(_full_text(node_a)), _tokenize(_full_text(node_b)))

    ta = node_a.get("type", node_a.get("kind", ""))
    tb = node_b.get("type", node_b.get("kind", ""))
    return s * type_compat(ta, tb)
