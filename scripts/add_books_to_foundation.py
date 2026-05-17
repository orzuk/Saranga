#!/usr/bin/env python3
"""Append textbook entries to clean_foundation.json -> clean_foundation_with_books.json.

Default behavior: auto-discover every book directory under
`<repo>/textbooks/extracted/b*/` and pull entries from each. (Previously the
script was pinned to 3 books — gowers PCM, higham PCAM, MAT520 functional
analysis. Auto-discovery makes the script work with the full 117-book
extraction set.)

For each book, walks every chapter/article JSON, pulls every node that has a
usable name/label, and registers it in the merged foundation index keyed by a
normalized lowercase form. Existing keys (already present from proofwiki etc.)
are NOT overwritten — first-seen wins, so order matters when multiple books
define the same named result. The source-tag is derived from the book dir
name: `b006_axler` -> `book:axler`. Three books retain their historical tags
(gowers / higham / functional_analysis) for continuity.

Output: clean_foundation_with_books.json next to the source clean_foundation.json.

Usage:
    python scripts/add_books_to_foundation.py                 # all books
    python scripts/add_books_to_foundation.py --books-only b006_axler,b026_judson
    python scripts/add_books_to_foundation.py --legacy-3-books  # old behavior
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = REPO_ROOT / "textbooks" / "extracted"

DEFAULT_FOUNDATION = Path(
    "/mnt/g/My Drive/Research/Automath/naturalproofs/clean_foundation.json"
)
DEFAULT_OUT = DEFAULT_FOUNDATION.parent / "clean_foundation_with_books.json"

LEGACY_BOOKS = [
    # (subdir_name, source_tag, pretty_label_prefix)
    ("b245_gowers_pcm",  "book:gowers",               "Gowers"),
    ("b246_higham_pcam", "book:higham",               "Higham"),
    ("b221_mat520",      "book:functional_analysis",  "FunctAn"),
]

# Books whose source_tag we want to pin to a stable, well-known name rather
# than the dir-derived default. Keys: subdir name; values: (source_tag, label).
PINNED_SOURCE_TAGS = {
    "b245_gowers_pcm":  ("book:gowers",              "Gowers"),
    "b246_higham_pcam": ("book:higham",              "Higham"),
    "b221_mat520":      ("book:functional_analysis", "FunctAn"),
}


def _label_from_dir_name(subdir_name: str) -> tuple[str, str]:
    """Derive (source_tag, pretty_label) from a book subdir name.

    `b006_axler`        -> ("book:axler", "Axler")
    `b001_openstax_calc1` -> ("book:openstax_calc1", "Openstax_Calc1")
    """
    if subdir_name in PINNED_SOURCE_TAGS:
        return PINNED_SOURCE_TAGS[subdir_name]
    # Strip the "b\d+_" prefix
    m = re.match(r"^b\d+[_-](.+)$", subdir_name)
    handle = m.group(1) if m else subdir_name
    return (f"book:{handle}", handle.replace("_", " ").title().replace(" ", "_"))


def discover_books(extracted_dir: Path) -> list[tuple[str, str, str]]:
    """Auto-discover all book subdirs under extracted_dir that contain content.

    Returns list of (subdir_name, source_tag, label_prefix) tuples, sorted by
    subdir name. A directory counts as a book if it matches ^b\\d and contains
    at least one JSON file with a `nodes` list.
    """
    out: list[tuple[str, str, str]] = []
    if not extracted_dir.is_dir():
        return out
    for d in sorted(extracted_dir.iterdir()):
        if not d.is_dir():
            continue
        if not re.match(r"^b\d", d.name):
            continue
        # Cheap content check: any *.json with a "nodes" key?
        has_content = False
        for fp in d.glob("*.json"):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    head = f.read(2048)
                if '"nodes"' in head:
                    has_content = True
                    break
            except Exception:
                continue
        if not has_content:
            continue
        tag, label = _label_from_dir_name(d.name)
        out.append((d.name, tag, label))
    return out


def _normalize_key(title: str) -> str:
    t = (title or "").strip().lower()
    for prefix in ("the ", "a ", "an ", "definition:", "definition: ", "theorem:", "theorem: "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    t = re.sub(r"['']s\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _node_name(n: Dict[str, Any]) -> str:
    """Return the best human-readable name for a node, or '' if none."""
    return (n.get("name") or n.get("label") or n.get("title") or "").strip()


def _node_type(n: Dict[str, Any]) -> str:
    """Map a book node 'type' to one of definition/theorem/concept/etc."""
    raw = (n.get("type") or "").strip().upper()
    rmap = {
        "DEFINITION":      "definition",
        "THEOREM":         "theorem",
        "THEOREM_LIKE":    "theorem",
        "LEMMA":           "lemma",
        "PROPOSITION":     "proposition",
        "COROLLARY":       "corollary",
        "EXAMPLE":         "example",
        "REMARK":          "remark",
        "NAMED_RESULT":    "theorem",
        "CONCEPT_ARTICLE": "concept",
    }
    return rmap.get(raw, raw.lower() if raw else "concept")


def _is_useful(n: Dict[str, Any]) -> bool:
    """Filter to entries that make for good foundation matches."""
    t = (n.get("type") or "").upper()
    # Skip edge-like items that sometimes leak into the nodes list
    if t in ("CROSS_REFERENCE", "CONTAINS_NAMED_RESULT"):
        return False
    name = _node_name(n)
    if not name:
        return False
    if len(name) < 4:
        return False
    return True


def _iter_book_nodes(book_dir: Path) -> Iterable[Dict[str, Any]]:
    """Yield every node dict from every JSON in a book directory."""
    for fp in sorted(book_dir.glob("*.json")):
        if fp.name in ("progress.json", "book.json", "extraction_log.txt"):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        # Some files use {"nodes": [...]}, others are bare lists.
        if isinstance(data, list):
            nodes = data
        elif isinstance(data, dict):
            nodes = data.get("nodes") or data.get("entries") or []
        else:
            nodes = []
        if not isinstance(nodes, list):
            continue
        for n in nodes:
            if isinstance(n, dict):
                yield n


def build_book_entries(books: list[tuple[str, str, str]]) -> Dict[str, Dict[str, Any]]:
    """Walk every book in `books`, return merged {key: entry} dict.

    `books` is a list of (subdir_name, source_tag, pretty_label) tuples — the
    same shape as the legacy hardcoded BOOKS list. First-seen-wins: if two
    books define the same normalized key, the earlier book's entry is kept.
    """
    out: Dict[str, Dict[str, Any]] = {}
    per_book_counts: Dict[str, int] = {}

    for subdir, source_tag, label_prefix in books:
        bdir = EXTRACTED_DIR / subdir
        if not bdir.is_dir():
            print(f"[skip] {bdir} not found")
            per_book_counts[source_tag] = 0
            continue

        added = 0
        for n in _iter_book_nodes(bdir):
            if not _is_useful(n):
                continue
            name = _node_name(n)
            key = _normalize_key(name)
            if not key:
                continue
            # don't overwrite a richer existing book entry from same pass
            if key in out:
                continue
            entry = {
                "name":             name,
                "id":               n.get("id", ""),
                "type":             _node_type(n),
                "source":           source_tag,        # e.g. "book:gowers"
                "field":            (n.get("part_name")
                                     or n.get("chapter_title")
                                     or label_prefix),
                "categories":       n.get("domain_tags") or [],
                "contents_preview": (n.get("statement")
                                     or n.get("summary")
                                     or "")[:400],
                "book_label":       label_prefix,      # used by visualizer for "Gowers: ..."
            }
            out[key] = entry
            added += 1
        per_book_counts[source_tag] = added
        print(f"[load] {subdir}: {added} entries")

    print(f"[total] {sum(per_book_counts.values())} book entries "
          f"across {len(books)} books")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--foundation",
                    default=str(DEFAULT_FOUNDATION),
                    help="Source clean_foundation.json (default: drive path).")
    ap.add_argument("--output",
                    default=str(DEFAULT_OUT),
                    help="Output path for merged foundation_with_books JSON.")
    ap.add_argument("--legacy-3-books", action="store_true",
                    help="Use the original 3-book hardcoded list (gowers + higham + "
                         "functional_analysis). Default is auto-discovery of all "
                         "extracted books.")
    ap.add_argument("--books-only", default=None,
                    help="Comma-sep subdir names to restrict the run to "
                         "(e.g. 'b006_axler,b026_judson').")
    args = ap.parse_args()

    if args.legacy_3_books:
        books = LEGACY_BOOKS
        print(f"[mode] legacy 3-book list ({len(books)} books)")
    else:
        books = discover_books(EXTRACTED_DIR)
        if args.books_only:
            allow = {s.strip() for s in args.books_only.split(",") if s.strip()}
            books = [b for b in books if b[0] in allow]
        print(f"[mode] auto-discovery: {len(books)} books found under {EXTRACTED_DIR}")

    fnd_path = Path(args.foundation)
    if not fnd_path.exists():
        raise SystemExit(f"Foundation source not found: {fnd_path}")

    print(f"[read] base foundation: {fnd_path}")
    with open(fnd_path, "r", encoding="utf-8") as f:
        base = json.load(f)
    base_index = base.get("index", {})
    print(f"[read]   base entries: {len(base_index)}")

    book_entries = build_book_entries(books)

    merged = dict(base_index)
    n_collisions = 0
    n_added = 0
    for key, entry in book_entries.items():
        if key in merged:
            n_collisions += 1
            continue
        merged[key] = entry
        n_added += 1

    print(f"[merge] new book entries added: {n_added} (collisions skipped: {n_collisions})")
    print(f"[merge] total entries in output: {len(merged)}")

    out = {
        "meta": {
            **(base.get("meta", {}) or {}),
            "books_added":      n_added,
            "books_collisions": n_collisions,
            "books_sources":    [b[1] for b in books],
            "books_count":      len(books),
            "index_size":       len(merged),
        },
        "index": merged,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[write] {out_path}")


if __name__ == "__main__":
    main()
