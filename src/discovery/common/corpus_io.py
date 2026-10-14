"""Walk SARANGA tier3 JSONs and yield paper-level records.

On-disk schema (per `src/annotation_schema.md`):
    {"metadata": {"paper_id": "1805.11176"}, "nodes": [...], "edges": [...]}

Filename suffixes encountered in practice:
    *_rules.json   current convention (rule-based extractor)
    *_manual.json  legacy suffix from older runs; same content
    *.json         occasional bare files

About 1-2% of files in the local sample are list-typed (older / malformed)
and skipped silently.
"""
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Sequence

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent  # .../Saranga/src
for _p in (_SRC, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from arxiv_id import normalize_arxiv_id, year_from_arxiv_id  # noqa: E402

from config import TIER3_DIR  # noqa: E402

_SUFFIXES = ("_rules.json", "_manual.json")


@dataclass
class Paper:
    paper_id: str          # base arxiv ID (with version suffix stripped)
    year: int
    category: str          # e.g. "math_CO" (top dir under root)
    path: Path
    nodes: list
    edges: list


def _strip_known_suffix(stem: str) -> str:
    for s in ("_rules", "_manual"):
        if stem.endswith(s):
            return stem[: -len(s)]
    return stem


def _category_from_path(p: Path, root: Path) -> str:
    try:
        parts = p.relative_to(root).parts
    except ValueError:
        return ""
    return parts[0] if parts else ""


def walk(root: Path, accept_bare_json: bool = False) -> Iterator[Path]:
    """Paper JSON paths, lazily (os.walk, sorted per directory): a global sort of the
    whole tree takes minutes on the cluster's 100k-file Lustre before yielding one."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        yield from (Path(dirpath) / f for f in sorted(filenames)
                    if f.endswith(_SUFFIXES) or accept_bare_json and f.endswith(".json"))


def read_paper(jp: Path, root: Path) -> Optional[Paper]:
    """The Paper in one JSON, or None (unreadable, not a dict, no arXiv id, no node/edge lists)."""
    try:
        data = json.loads(jp.read_text(encoding="utf-8"))
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        pid = normalize_arxiv_id(meta.get("paper_id") or _strip_known_suffix(jp.stem))
        year = year_from_arxiv_id(pid)
    except (ValueError, AttributeError, OSError):      # JSONDecodeError is a ValueError
        return None
    nodes, edges = data.get("nodes"), data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    return Paper(paper_id=pid, year=year, category=_category_from_path(jp, root), path=jp, nodes=nodes, edges=edges)


def iter_papers(
    root: Optional[Path] = None,
    *,
    categories: Optional[Sequence[str]] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    accept_bare_json: bool = False,
    on_progress=None,
) -> Iterator[Paper]:
    """Yield Paper records for every JSON under `root` that matches filters, lazily.

    Args:
        root: defaults to config.TIER3_DIR.
        categories: restrict to these top-level subdirs (e.g. ["math_CO"]).
        year_min, year_max: inclusive year bounds (None = unbounded).
        accept_bare_json: include `.json` files without a `_rules`/`_manual`
            suffix. Off by default — those are usually report files
            (anomalies_detail.json, corpus_stats.csv) not paper extractions.
        on_progress: called with the number of files scanned, every 5000.
    """
    root = Path(root) if root else TIER3_DIR
    for i, jp in enumerate(walk(root, accept_bare_json), 1):
        if on_progress and i % 5000 == 0:
            on_progress(i)
        if categories and _category_from_path(jp, root) not in categories:
            continue
        p = read_paper(jp, root)
        if p and (year_min is None or p.year >= year_min) and (year_max is None or p.year <= year_max):
            yield p


def count_papers(root: Optional[Path] = None, **kwargs) -> int:
    """Convenience: count without materializing the list."""
    return sum(1 for _ in iter_papers(root=root, **kwargs))
