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


def iter_papers(
    root: Optional[Path] = None,
    *,
    categories: Optional[Sequence[str]] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    accept_bare_json: bool = False,
) -> Iterator[Paper]:
    """Yield Paper records for every JSON under `root` that matches filters.

    Args:
        root: defaults to config.TIER3_DIR.
        categories: restrict to these top-level subdirs (e.g. ["math_CO"]).
        year_min, year_max: inclusive year bounds (None = unbounded).
        accept_bare_json: include `.json` files without a `_rules`/`_manual`
            suffix. Off by default — those are usually report files
            (anomalies_detail.json, corpus_stats.csv) not paper extractions.
    """
    root = Path(root) if root else TIER3_DIR
    cat_filter = set(categories) if categories else None

    for jp in sorted(root.rglob("*.json")):
        name = jp.name
        if name.endswith(_SUFFIXES):
            pass
        elif accept_bare_json:
            pass
        else:
            continue

        cat = _category_from_path(jp, root)
        if cat_filter is not None and cat not in cat_filter:
            continue

        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        pid_raw = meta.get("paper_id") or _strip_known_suffix(jp.stem)
        try:
            pid_base = normalize_arxiv_id(pid_raw)
            year = year_from_arxiv_id(pid_base)
        except ValueError:
            continue

        if year_min is not None and year < year_min:
            continue
        if year_max is not None and year > year_max:
            continue

        nodes = data.get("nodes")
        edges = data.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            continue

        yield Paper(paper_id=pid_base, year=year, category=cat, path=jp,
                    nodes=nodes, edges=edges)


def count_papers(root: Optional[Path] = None, **kwargs) -> int:
    """Convenience: count without materializing the list."""
    return sum(1 for _ in iter_papers(root=root, **kwargs))
