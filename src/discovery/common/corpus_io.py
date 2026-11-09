"""Walk SARANGA tier3 JSONs and yield paper-level records.

On-disk schema (per `src/annotation_schema.md`):
    {"metadata": {"paper_id": "1805.11176"}, "nodes": [...], "edges": [...]}

Filename suffixes encountered in practice:
    *_rules.json   current convention (rule-based extractor)
    *_manual.json  legacy suffix from older runs; same content
    *.json         occasional bare files

A root may also hold bundles (portal/bundle_t3.py, docs/tier3_bundles.md): <cat>/<year>.json.xz with
<cat>/<year>.idx.json. walk() then yields one path per paper, <cat>/<year>.json.xz#<id>, and
read_paper() reads that paper from the bundle, so callers work the same on either layout.

A third layout is the full-arXiv run: <YYYY>/<MM>/<DD>.tar.gz, one gzipped tar per submission day with
json/<id>_rules.json members. A gzipped tar is read front to back, so walk() yields ONE path per archive,
<DD>.tar.gz#*, and read_papers() streams its papers; read_paper() on such a path returns None. Use
iter_papers() or read_papers() to cover all three layouts. These papers have no category directory: their
category comes from set_categories() (an id -> category table), else it is "".

About 1-2% of files in the local sample are list-typed (older / malformed)
and skipped silently.
"""
import gzip
import json
import lzma
import os
import re
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Sequence

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent  # .../Saranga/src
for _p in (_SRC, _HERE, _SRC.parent / "portal"):        # portal/: bundle_t3, the bundle format
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
    whole tree takes minutes on the cluster's 100k-file Lustre before yielding one.
    A paper in a bundle is yielded as <bundle>.json.xz#<id> (see the module docstring)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for f in sorted(filenames):
            if f.endswith(_SUFFIXES) or accept_bare_json and f.endswith(".json"):
                yield Path(dirpath) / f
            elif f.endswith(".json.xz") and f[:-8] + ".idx.json" in filenames:
                yield from (Path(dirpath) / f"{f}#{pid}" for pid in _bundle_index(Path(dirpath) / f))
            elif f.endswith(".tar.gz"):
                yield Path(dirpath) / f"{f}#*"          # a day archive: all its papers (read_papers)


_BUNDLE_IDX: dict = {}      # the last bundle's index, per process (papers come bundle by bundle)


def _bundle_index(bundle: Path) -> dict:
    if bundle not in _BUNDLE_IDX:
        _BUNDLE_IDX.clear()
        _BUNDLE_IDX[bundle] = json.loads(Path(str(bundle)[:-8] + ".idx.json").read_text(encoding="utf-8"))
    return _BUNDLE_IDX[bundle]


def read_json(jp: Path) -> dict:
    """The JSON at a path walk() yields: a file, or a paper in a bundle (<bundle>#<id>)."""
    if "#" not in jp.name:
        return json.loads(jp.read_text(encoding="utf-8"))
    from bundle_t3 import unpack
    name, pid = jp.name.split("#", 1)
    bundle = jp.with_name(name)
    entry = _bundle_index(bundle)[pid]
    with open(bundle, "rb") as fh:
        fh.seek(entry[0])
        return unpack(fh.read(entry[1]), entry)


_OLD_ID_RE = re.compile(r"^([a-z]+(?:-[a-z]+)?(?:\.[A-Z]{2,3})?)_(\d{7}(?:v\d+)?)$")
_CATEGORIES: dict = {}      # arXiv id -> category, for layouts without a category directory


def set_categories(table) -> int:
    """Load an id -> category table (a .tsv or .tsv.gz of "<arxiv id>\t<category>" lines, or a dict) used
    for papers whose path carries no category (day archives). Returns the number of ids."""
    _CATEGORIES.clear()
    if isinstance(table, dict):
        _CATEGORIES.update(table)
    else:
        opener = gzip.open if str(table).endswith(".gz") else open
        with opener(table, "rt", encoding="utf-8") as fh:
            for line in fh:
                k, _, v = line.rstrip("\n").partition("\t")
                if v:
                    _CATEGORIES[k] = v
    return len(_CATEGORIES)


def _paper_from(data, stem: str, path: Path, category) -> Optional[Paper]:
    """A Paper from a parsed JSON; `category` is a string or None (= look the id up in the table)."""
    try:
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        raw = meta.get("paper_id") or _strip_known_suffix(stem)
        m = _OLD_ID_RE.match(raw)                      # math_9803158v1: the file-name form of math/9803158v1
        pid = normalize_arxiv_id(f"{m.group(1)}/{m.group(2)}" if m else raw)
        year = year_from_arxiv_id(pid)
    except (ValueError, AttributeError, KeyError):
        return None
    nodes, edges = data.get("nodes"), data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    if category is None:
        category = _CATEGORIES.get(pid, "")
    return Paper(paper_id=pid, year=year, category=category, path=path, nodes=nodes, edges=edges)


def read_paper(jp: Path, root: Path) -> Optional[Paper]:
    """The Paper in one JSON (or a bundle's paper, <bundle>#<id>), or None (unreadable, not a dict,
    no arXiv id, no node/edge lists; also for a day archive, <DD>.tar.gz#*: see read_papers)."""
    if jp.name.endswith("#*"):
        return None
    try:
        data = read_json(jp)
    except (ValueError, OSError, KeyError, EOFError, lzma.LZMAError):  # JSONDecodeError is a ValueError
        return None
    if not isinstance(data, dict):
        return None
    jp_stem = jp.name.split("#", 1)[1] if "#" in jp.name else jp.stem
    return _paper_from(data, jp_stem, jp, _category_from_path(jp, root))


def read_papers(jp: Path, root: Path) -> Iterator[Paper]:
    """Every Paper behind one path walk() yields: one for a file or a bundle entry, all the papers of a
    day archive (<DD>.tar.gz#*), streamed in the archive's order. Unreadable members are skipped."""
    if not jp.name.endswith("#*"):
        p = read_paper(jp, root)
        if p:
            yield p
        return
    archive = jp.with_name(jp.name[:-2])
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                name = member.name.rsplit("/", 1)[-1]
                if not member.isfile() or not name.endswith(_SUFFIXES):
                    continue
                try:
                    data = json.load(tar.extractfile(member))
                except (ValueError, OSError, EOFError):
                    continue
                if isinstance(data, dict):
                    p = _paper_from(data, name[:-5], archive.with_name(f"{archive.name}#{name}"), None)
                    if p:
                        yield p
    except (OSError, EOFError, tarfile.TarError):
        return


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
        if jp.name.endswith("#*"):                      # a day archive: its category is per paper
            for p in read_papers(jp, root):
                if (not categories or p.category in categories) and \
                        (year_min is None or p.year >= year_min) and (year_max is None or p.year <= year_max):
                    yield p
            continue
        if categories and _category_from_path(jp, root) not in categories:
            continue
        p = read_paper(jp, root)
        if p and (year_min is None or p.year >= year_min) and (year_max is None or p.year <= year_max):
            yield p


def count_papers(root: Optional[Path] = None, **kwargs) -> int:
    """Convenience: count without materializing the list."""
    return sum(1 for _ in iter_papers(root=root, **kwargs))
