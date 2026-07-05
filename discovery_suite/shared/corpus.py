"""Shared corpus access + node-text normalization for the discovery suite.

Thin wrapper over ``src/discovery/common/corpus_io.iter_papers`` (imported, never
modified). Adds:
  * a local default root (the on-Mac portal tier3 tree) so tools run without the
    cluster dataset present;
  * ``iter_nodes`` to flatten papers into globally-keyed nodes;
  * ``node_text`` / ``normalize_math_text`` used by every downstream method
    (shingling, embedding, judging) so the textual signal is defined in ONE place.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT / "src", _REPO_ROOT / "src" / "discovery"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from common.corpus_io import Paper, iter_papers  # noqa: E402  (re-exported)

# Local, always-present default (portal mirror). Override with root=... for the
# full 100k parse on the cluster.
DEFAULT_ROOT = _REPO_ROOT / "portal" / "data" / "tier3"


def load_papers(
    root: Optional[Path] = None,
    *,
    categories: Optional[Sequence[str]] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[Paper]:
    """Eagerly load Paper records (list, so tools can index/shuffle)."""
    root = Path(root) if root else DEFAULT_ROOT
    out: list[Paper] = []
    for p in iter_papers(root=root, categories=categories,
                         year_min=year_min, year_max=year_max):
        out.append(p)
        if limit is not None and len(out) >= limit:
            break
    return out


# ── Node keying & text ───────────────────────────────────────────────────────

def node_key(paper_id: str, node: dict) -> str:
    """Globally-unique node handle across the corpus."""
    return f"{paper_id}::{node.get('id')}"


def iter_nodes(papers: Iterable[Paper]) -> Iterator[tuple[str, dict]]:
    """Yield (paper_id, node) for every node in every paper."""
    for p in papers:
        for n in p.nodes:
            yield p.paper_id, n


_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\*?")          # \alpha, \begin, ...
_LATEX_PUNCT = re.compile(r"[{}$&#~^_\\]")          # structural TeX chars
_NON_WORD = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


def normalize_math_text(s: str) -> str:
    """Lowercase, strip LaTeX control sequences/structure, collapse whitespace.

    Keeps identifier words and math *tokens* (variable names survive) but drops
    the TeX scaffolding that would otherwise dominate shingles. Deterministic —
    used identically at index time and query time.
    """
    if not s:
        return ""
    s = _LATEX_CMD.sub(" ", s)
    s = _LATEX_PUNCT.sub(" ", s)
    s = _NON_WORD.sub(" ", s)
    s = _WS.sub(" ", s).strip().lower()
    return s


def node_text(node: dict, *, include_type: bool = True) -> str:
    """Canonical text for a node: type + name + statement + clean_text.

    Mirrors scripts/embedding_sigma.node_text_for_embedding but without the
    torch/sentence-transformers import, so the light (P1/P2) methods stay
    dependency-free. Prefers ``clean_text`` (parser-cleaned) then ``statement``.
    """
    parts: list[str] = []
    if include_type:
        t = node.get("type") or node.get("kind") or ""
        if t:
            parts.append(f"[{t}]")
    name = node.get("name")
    if name:
        parts.append(str(name))
    body = node.get("clean_text") or node.get("statement") or ""
    if isinstance(body, list):
        body = " ".join(str(x) for x in body)
    if body:
        parts.append(str(body))
    return " ".join(parts)


def node_norm_text(node: dict) -> str:
    """node_text run through normalize_math_text — the shingling substrate."""
    return normalize_math_text(node_text(node, include_type=False))
