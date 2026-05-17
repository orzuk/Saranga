"""Convert per-chapter book JSONs from their original extraction schema to the
unified Saranga JSON schema (per src/annotation_schema.md).

This is a pure JSON-to-JSON transform — NO LLM calls, no re-extraction. It
preserves the existing extraction work (the books were parsed with Claude
across several prompt revisions; ~$ already sunk).

The input lives at `<repo>/textbooks/extracted/<book_id>/chapter_*.json` (and
occasionally `<book_id>/*.json` for variant-naming books). Schema variance
across the 117 extracted books:

  Top-level keys (most common forms):
    {book_id, chapter_num, chapter_title, page_range, nodes, edges}   # dominant
    {chapter_id, chapter_title, nodes(, edges)}                       # variant
    {chapter, title, nodes, edges}                                    # variant

  Node text fields (any subset):
    raw_text, raw_latex, statement, statement_latex, statement_clean,
    clean_text, text

  Edge field names:
    {source, target, type}    # canonical
    {from, to, type}          # variant
    {src, dst, type}          # variant
    {source, target, relation}  # variant

  Edge types (book-specific to canonical):
    uses, proves, depends_on, follows_from, has_part,
    generalizes, related_to, equivalent_to, mentions_concept,
    specializes -> pass through (in / compatible with unified vocab)
    cross_reference   -> related_to
    contains_named_result -> has_part
    about, illustrates -> mentions_concept
    special_case_of   -> generalizes (with direction FLIPPED:
                         "B special_case_of A" becomes "A generalizes B")
    derives           -> follows_from
    equals            -> equivalent_to
    tests             -> DROPPED (exercise->result edges have no
                         analogue in the math-graph vocabulary).

Output is TWO JSON files per chapter, co-located so side-by-side comparison
is trivial:
    <DATA_DIR>/foundation/books/<book_id>/<chapter_id>.original.json
        Verbatim copy of the original extraction (legacy scheme).
    <DATA_DIR>/foundation/books/<book_id>/<chapter_id>.unified.json
        Converted to the unified Saranga schema.
Plus a `manifest.csv` summarizing per-book results.

Usage:
    python -m structured_math.books.migrate_to_unified --limit 5     # dry-ish
    python -m structured_math.books.migrate_to_unified --all         # full
    python -m structured_math.books.migrate_to_unified --book b006_axler
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent           # .../Saranga/src
_REPO = _SRC.parent                  # .../Saranga
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config import DATA_DIR  # noqa: E402
from node_types import normalize_node_type  # noqa: E402

EXTRACTED_DIR = _REPO / 'textbooks' / 'extracted'
DEFAULT_OUT_DIR = DATA_DIR / 'foundation' / 'books'

# ── Edge type normalization ──────────────────────────────────────────────────

# Map from book-edge-type -> (canonical_type, flip?)
# `flip=True` means swap source<->target during conversion.
EDGE_TYPE_MAP: Dict[str, Tuple[str, bool]] = {
    # pass-through
    'uses':                  ('uses', False),
    'proves':                ('proves', False),
    'depends_on':            ('depends_on', False),
    'follows_from':          ('follows_from', False),
    'has_part':              ('has_part', False),
    'generalizes':           ('generalizes', False),
    'specializes':           ('specializes', False),
    'related_to':            ('related_to', False),
    'equivalent_to':         ('equivalent_to', False),
    'mentions_concept':      ('mentions_concept', False),
    'grounded_to':           ('grounded_to', False),
    # book-specific -> canonical
    'cross_reference':       ('related_to', False),
    'contains_named_result': ('has_part', False),
    'about':                 ('mentions_concept', False),
    'illustrates':           ('mentions_concept', False),
    'special_case_of':       ('generalizes', True),   # flip direction
    'derives':               ('follows_from', False),
    'equals':                ('equivalent_to', False),
}

# Edge types that have no useful analogue in the unified math-graph vocabulary
EDGE_TYPE_DROP = {'tests'}


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class BookStats:
    book_id: str
    chapters_in: int = 0
    chapters_out: int = 0
    nodes_in: int = 0
    nodes_out: int = 0
    edges_in: int = 0
    edges_out: int = 0
    edges_dropped: int = 0
    edges_remapped: int = 0
    top_level_variants: Counter = field(default_factory=Counter)
    edge_type_in: Counter = field(default_factory=Counter)
    edge_type_out: Counter = field(default_factory=Counter)
    skipped_files: List[str] = field(default_factory=list)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _is_valid_chapter_payload(data: Any) -> bool:
    return (isinstance(data, dict)
            and isinstance(data.get('nodes'), list)
            and isinstance(data.get('edges'), list)
            and len(data['nodes']) > 0)


def _iter_chapter_files(book_dir: Path):
    """Yield chapter JSON files under a book dir. Skip `_scripts`/`_pdftxt`
    subdirs and any file that isn't shaped like a chapter payload."""
    for f in sorted(book_dir.rglob('*.json')):
        try:
            rel = f.relative_to(book_dir)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in ('_scripts', '_pdftxt'):
            continue
        # Quick name-based filter (book.json / progress.json / *_summary.json
        # are clearly not chapter payloads). We still validate below.
        if f.name in ('book.json', 'progress.json'):
            continue
        if f.name.endswith('_summary.json') or f.name.endswith('_progress.json'):
            continue
        if 'extraction_failed' in f.name:
            continue
        yield f


def _chapter_id_from_filename(p: Path) -> str:
    """Stable chapter id from filename. `chapter_2.json` -> `chapter_2`."""
    return p.stem


def _coerce_text_fields(node: Dict[str, Any]) -> Tuple[str, str]:
    """Return (raw_latex, clean_text) by preferring richer fields first."""
    raw = (node.get('statement_latex')
           or node.get('raw_latex')
           or node.get('raw_text')
           or node.get('statement')
           or node.get('clean_text')
           or '')
    clean = (node.get('statement_clean')
             or node.get('clean_text')
             or node.get('statement')
             or node.get('raw_text')
             or '')
    return raw, clean


def _normalize_node(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a book node to the unified schema. Returns None to drop."""
    nid = node.get('id')
    if not nid:
        return None
    raw_latex, clean_text = _coerce_text_fields(node)
    name = (node.get('name') or '').strip() or None
    label = node.get('label') or None
    ntype = normalize_node_type(node.get('type'))
    out: Dict[str, Any] = {
        'id': nid,
        'type': ntype,
        'name': name,
        'label': label,
        'raw_latex': raw_latex,
        'clean_text': clean_text,
        'statement': clean_text,            # alias used by some consumers
        'origin': 'book',
    }
    # Preserve secondary fields under metadata
    extra = {}
    for k in ('page', 'subclass', 'tags', 'env_name', 'rigor'):
        if k in node and node[k] not in (None, '', []):
            extra[k] = node[k]
    if extra:
        out['metadata'] = extra
    return out


def _normalize_edge_keys(edge: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Coerce edge to {source, target, type, ...}. Returns None on malformed."""
    src = edge.get('source') or edge.get('from') or edge.get('src')
    tgt = edge.get('target') or edge.get('to') or edge.get('dst')
    etype = edge.get('type') or edge.get('relation')
    if not (src and tgt and etype):
        return None
    rest = {k: v for k, v in edge.items()
            if k not in ('source', 'target', 'type', 'from', 'to', 'src', 'dst', 'relation')}
    return {'source': src, 'target': tgt, 'type': etype, **rest}


def _map_edge_type(edge: Dict[str, Any], stats: BookStats) -> Optional[Dict[str, Any]]:
    """Apply the edge-type mapping. Returns None to drop."""
    et = edge['type']
    stats.edge_type_in[et] += 1
    if et in EDGE_TYPE_DROP:
        stats.edges_dropped += 1
        return None
    mapping = EDGE_TYPE_MAP.get(et)
    if mapping is None:
        # Unknown type: keep as-is, let downstream consumers complain if
        # they care. Counts as remapped only when actually changed.
        stats.edge_type_out[et] += 1
        return edge
    new_type, flip = mapping
    if new_type != et:
        stats.edges_remapped += 1
    edge_out = dict(edge)
    edge_out['type'] = new_type
    if flip:
        edge_out['source'], edge_out['target'] = edge_out['target'], edge_out['source']
        edge_out.setdefault('_remap', []).append(f'flipped({et})')
    stats.edge_type_out[new_type] += 1
    return edge_out


# ── Per-chapter conversion ──────────────────────────────────────────────────

def convert_chapter(
    src_path: Path,
    book_id: str,
    stats: BookStats,
) -> Optional[Dict[str, Any]]:
    """Read one book-chapter JSON and emit the unified-schema dict, or None."""
    try:
        data = json.loads(src_path.read_text(encoding='utf-8'))
    except Exception as e:
        stats.skipped_files.append(f'{src_path.name} (parse-error: {e})')
        return None
    if not _is_valid_chapter_payload(data):
        stats.skipped_files.append(f'{src_path.name} (no nodes+edges)')
        return None

    stats.top_level_variants[tuple(sorted(data.keys()))] += 1
    stats.chapters_in += 1
    stats.nodes_in += len(data['nodes'])
    stats.edges_in += len(data['edges'])

    # Normalize chapter-level metadata
    chapter_num = (data.get('chapter_num')
                   or data.get('chapter_id')
                   or data.get('chapter'))
    chapter_title = data.get('chapter_title') or data.get('title')
    page_range = data.get('page_range')
    book_id_field = data.get('book_id') or book_id

    metadata: Dict[str, Any] = {
        'source': 'book',
        'book_id': book_id_field,
        'chapter_id': _chapter_id_from_filename(src_path),
    }
    if chapter_num is not None:
        metadata['chapter_num'] = chapter_num
    if chapter_title:
        metadata['chapter_title'] = chapter_title
    if page_range:
        metadata['page_range'] = page_range
    if 'extraction_date' in data:
        metadata['extraction_date'] = data['extraction_date']
    if 'model_used' in data:
        metadata['extraction_model'] = data['model_used']

    # Normalize nodes
    out_nodes: List[Dict[str, Any]] = []
    kept_node_ids: set = set()
    for n in data['nodes']:
        if not isinstance(n, dict):
            continue
        norm = _normalize_node(n)
        if norm is None:
            continue
        out_nodes.append(norm)
        kept_node_ids.add(norm['id'])
    stats.nodes_out += len(out_nodes)

    # Normalize edges
    out_edges: List[Dict[str, Any]] = []
    for e in data['edges']:
        if not isinstance(e, dict):
            continue
        coerced = _normalize_edge_keys(e)
        if coerced is None:
            stats.edges_dropped += 1
            continue
        if coerced['source'] not in kept_node_ids or coerced['target'] not in kept_node_ids:
            # Edge endpoints reference dropped nodes; drop the edge.
            stats.edges_dropped += 1
            continue
        mapped = _map_edge_type(coerced, stats)
        if mapped is None:
            continue
        out_edges.append(mapped)
    stats.edges_out += len(out_edges)

    return {
        'metadata': metadata,
        'nodes': out_nodes,
        'edges': out_edges,
    }


def convert_book(book_dir: Path, out_root: Path) -> BookStats:
    book_id = book_dir.name
    stats = BookStats(book_id=book_id)
    out_dir = out_root / book_id
    out_dir.mkdir(parents=True, exist_ok=True)

    for src in _iter_chapter_files(book_dir):
        chapter_id = _chapter_id_from_filename(src)
        unified_path = out_dir / f'{chapter_id}.unified.json'
        original_path = out_dir / f'{chapter_id}.original.json'
        result = convert_chapter(src, book_id, stats)
        if result is None:
            continue
        # Write both versions side-by-side. The .original.json is a verbatim
        # copy of the legacy-scheme extraction; .unified.json is the converted
        # form. Filenames make the scheme obvious.
        unified_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        try:
            original_path.write_text(
                src.read_text(encoding='utf-8'),
                encoding='utf-8',
            )
        except Exception:
            pass
        stats.chapters_out += 1

    return stats


# ── Driver ──────────────────────────────────────────────────────────────────

def _write_manifest(all_stats: List[BookStats], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['book_id', 'chapters_in', 'chapters_out',
                    'nodes_in', 'nodes_out',
                    'edges_in', 'edges_out',
                    'edges_dropped', 'edges_remapped',
                    'top_level_variants',
                    'edge_types_in_top5',
                    'skipped_files'])
        for s in sorted(all_stats, key=lambda x: x.book_id):
            variants = ','.join(f'{"+".join(k[:3] for k in sig)}({n})'
                                for sig, n in s.top_level_variants.most_common(3))
            top_edges = ','.join(f'{t}:{n}' for t, n in s.edge_type_in.most_common(5))
            w.writerow([
                s.book_id, s.chapters_in, s.chapters_out,
                s.nodes_in, s.nodes_out,
                s.edges_in, s.edges_out,
                s.edges_dropped, s.edges_remapped,
                variants, top_edges,
                '; '.join(s.skipped_files[:5]),
            ])


def _print_summary(all_stats: List[BookStats]) -> None:
    total_books = len(all_stats)
    converted = sum(1 for s in all_stats if s.chapters_out > 0)
    print(f"\nConverted {converted}/{total_books} books "
          f"to unified schema.")
    print(f"Chapters: in={sum(s.chapters_in for s in all_stats)} "
          f"out={sum(s.chapters_out for s in all_stats)}")
    print(f"Nodes:    in={sum(s.nodes_in for s in all_stats)} "
          f"out={sum(s.nodes_out for s in all_stats)}")
    print(f"Edges:    in={sum(s.edges_in for s in all_stats)} "
          f"out={sum(s.edges_out for s in all_stats)} "
          f"(dropped={sum(s.edges_dropped for s in all_stats)}, "
          f"remapped={sum(s.edges_remapped for s in all_stats)})")
    agg_type_in: Counter = Counter()
    for s in all_stats:
        agg_type_in.update(s.edge_type_in)
    if agg_type_in:
        print("Edge types in source (top 10):")
        for t, n in agg_type_in.most_common(10):
            print(f"  {t:<25} {n}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--all', action='store_true',
                   help='Convert every book under textbooks/extracted/')
    g.add_argument('--book', help='Convert a single book (e.g. b006_axler)')
    g.add_argument('--limit', type=int,
                   help='Convert the first N books (alphabetical)')
    ap.add_argument('--extracted-dir', default=str(EXTRACTED_DIR))
    ap.add_argument('--out-dir', default=str(DEFAULT_OUT_DIR))
    ap.add_argument('--manifest', default=None,
                    help='Manifest CSV path (default: <out-dir>/manifest.csv)')
    args = ap.parse_args()

    extracted_dir = Path(args.extracted_dir)
    out_dir = Path(args.out_dir)
    manifest = Path(args.manifest) if args.manifest else out_dir / 'manifest.csv'

    if not extracted_dir.exists():
        print(f"FATAL: extracted dir does not exist: {extracted_dir}",
              file=sys.stderr)
        sys.exit(2)

    candidates = sorted(d for d in extracted_dir.iterdir()
                        if d.is_dir() and re.match(r'^b\d', d.name))
    if args.book:
        candidates = [d for d in candidates if d.name == args.book]
        if not candidates:
            print(f"No such book: {args.book}", file=sys.stderr); sys.exit(2)
    elif args.limit:
        candidates = candidates[:args.limit]
    elif not args.all:
        ap.error("specify exactly one of --all / --book / --limit")

    out_dir.mkdir(parents=True, exist_ok=True)

    all_stats: List[BookStats] = []
    for d in candidates:
        s = convert_book(d, out_dir)
        all_stats.append(s)
        print(f"[{s.book_id}] chapters {s.chapters_in}->{s.chapters_out} "
              f"nodes {s.nodes_in}->{s.nodes_out} "
              f"edges {s.edges_in}->{s.edges_out} "
              f"(drop={s.edges_dropped}, remap={s.edges_remapped})")

    _write_manifest(all_stats, manifest)
    _print_summary(all_stats)
    print(f"\nManifest: {manifest}")
    print(f"Output:   {out_dir}")


if __name__ == '__main__':
    main()
