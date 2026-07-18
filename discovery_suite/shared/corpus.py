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

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT / "src", _REPO_ROOT / "src" / "discovery"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from common.corpus_io import Paper, iter_papers  # noqa: E402  (re-exported)
from arxiv_id import normalize_arxiv_id, year_from_arxiv_id  # noqa: E402

# Local, always-present default (portal mirror). Override with root=... for the
# full 100k parse on the cluster.
DEFAULT_ROOT = _REPO_ROOT / "portal" / "data" / "tier3"

_SUFFIXES = ("_rules.json", "_manual.json")


def _lazy_walk(root: Path) -> Iterator[Path]:
    """Yield paper JSON paths lazily via os.walk — NO upfront global sort.

    corpus_io.iter_papers does ``sorted(root.rglob("*.json"))`` which enumerates
    and sorts the ENTIRE tree before yielding one path — minutes on a 100k-file
    networked FS (Lustre). We sort only per-directory (cheap, still deterministic)
    and yield as we go, so ``limit`` returns almost immediately.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.endswith(_SUFFIXES):
                yield Path(dirpath) / fn


def _build_paper(path: Path, root: Path) -> Optional[Paper]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    stem = path.stem
    for s in ("_rules", "_manual"):
        if stem.endswith(s):
            stem = stem[: -len(s)]
    pid_raw = meta.get("paper_id") or stem
    try:
        pid = normalize_arxiv_id(pid_raw)
        year = year_from_arxiv_id(pid)
    except ValueError:
        return None
    try:
        cat = path.relative_to(root).parts[0]
    except (ValueError, IndexError):
        cat = ""
    nodes, edges = data.get("nodes"), data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    return Paper(paper_id=pid, year=year, category=cat, path=path,
                 nodes=nodes, edges=edges)


def stream_papers(
    root: Optional[Path] = None,
    *,
    categories: Optional[Sequence[str]] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    on_progress=None,
) -> Iterator[Paper]:
    """Yield Paper records ONE AT A TIME (lazy) so callers can extract-and-discard
    without ever holding the whole corpus in memory. Same filters as load_papers.
    ``on_progress(scanned)`` fires every 5000 files scanned. Use this — not
    load_papers — for corpus-scale sweeps: a full 100k list of Paper objects
    (all nodes+edges+raw_latex) is ~10-20GB, but most of it is never needed.
    """
    root = Path(root) if root else DEFAULT_ROOT
    cat_filter = set(categories) if categories else None
    scanned = 0
    for path in _lazy_walk(root):
        scanned += 1
        if on_progress is not None and scanned % 5000 == 0:
            on_progress(scanned)
        p = _build_paper(path, root)
        if p is None:
            continue
        if cat_filter is not None and p.category not in cat_filter:
            continue
        if year_min is not None and p.year < year_min:
            continue
        if year_max is not None and p.year > year_max:
            continue
        yield p


def load_papers(
    root: Optional[Path] = None,
    *,
    categories: Optional[Sequence[str]] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    limit: Optional[int] = None,
    on_progress=None,
) -> list[Paper]:
    """Eagerly load Paper records (list, so tools can index/shuffle).

    Uses a lazy per-directory walk (fast on big networked corpora); stops as soon
    as ``limit`` papers are collected. ``on_progress(scanned, kept)`` (optional)
    fires every 5000 files scanned so long cluster loads aren't a black box.
    """
    root = Path(root) if root else DEFAULT_ROOT
    cat_filter = set(categories) if categories else None
    out: list[Paper] = []
    scanned = 0
    for path in _lazy_walk(root):
        scanned += 1
        if on_progress is not None and scanned % 5000 == 0:
            on_progress(scanned, len(out))
        p = _build_paper(path, root)
        if p is None:
            continue
        if cat_filter is not None and p.category not in cat_filter:
            continue
        if year_min is not None and p.year < year_min:
            continue
        if year_max is not None and p.year > year_max:
            continue
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
