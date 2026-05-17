"""
foundation_linker.py

Link extracted paper mid-level representations to the foundation knowledge graph
(NaturalProofs, Mathlib/LeanDojo).

Tier 1: Name/keyword substring matching against NaturalProofs index entries.
For each extracted object, check if any NaturalProofs theorem/definition name
appears in its text, and add grounded_to edges.

Usage:
    from foundation_linker import FoundationLinker

    linker = FoundationLinker()
    linker.load_naturalproofs_index('/path/to/naturalproofs/midlevel/')
    new_relations = linker.link_paper(paper_graph)
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict

# Resolve math_classes from src/LLMVersion/ (single source of truth)
_LLMV = Path(__file__).resolve().parent / 'LLMVersion'
if str(_LLMV) not in sys.path:
    sys.path.insert(0, str(_LLMV))

from math_classes import Relation, PaperGraph, REL_GROUNDED_TO


class FoundationLinker:
    """
    Links extracted paper objects to foundation knowledge graph entries
    via name/keyword matching (Tier 1).
    """

    def __init__(self):
        # name_lower -> list of {id, name, type, source}
        self._term_index: Dict[str, List[Dict]] = {}
        # all index entries by id
        self._entries: Dict[str, Dict] = {}

    def load_naturalproofs_index(self, midlevel_dir: str) -> None:
        """
        Load NaturalProofs index files from the midlevel output directory.
        Expects: proofwiki_index.json, stacks_index.json, trench_index.json
        """
        loaded = 0
        for fname in os.listdir(midlevel_dir):
            if fname.endswith('_index.json'):
                fpath = os.path.join(midlevel_dir, fname)
                with open(fpath) as f:
                    entries = json.load(f)
                for entry in entries:
                    self._entries[entry['id']] = entry
                loaded += len(entries)

        self._build_index()
        print(f"FoundationLinker: loaded {loaded} entries from {midlevel_dir}, "
              f"{len(self._term_index)} unique terms indexed")

    def load_mathlib_index(self, midlevel_dir: str) -> None:
        """
        Load Mathlib index file from the midlevel output directory.
        Expects: mathlib4_index.json
        """
        fpath = os.path.join(midlevel_dir, 'mathlib4_index.json')
        if not os.path.exists(fpath):
            print(f"FoundationLinker: {fpath} not found, skipping Mathlib")
            return

        with open(fpath) as f:
            entries = json.load(f)
        loaded = 0
        for entry in entries:
            self._entries[entry['id']] = entry
            loaded += 1

        self._build_index()
        print(f"FoundationLinker: loaded {loaded} Mathlib entries, "
              f"{len(self._term_index)} unique terms indexed")

    def load_unified_index(self, json_path: str) -> None:
        """Load a single merged foundation index (the output of
        scripts/add_books_to_foundation.py).

        File format:
            {"meta": {...},
             "index": {normalized_key: entry, ...}}
        Each entry should carry at least {name, source, type}. If `id` is
        missing or empty, we synthesize one from the normalized key so the
        linker's per-edge provenance still works.

        Use this in place of the per-source `load_naturalproofs_index` calls
        when working with the merged broad-math index. Mathlib is loaded
        separately via `load_mathlib_index` regardless.
        """
        if not os.path.exists(json_path):
            print(f"FoundationLinker: {json_path} not found, "
                  f"skipping unified index")
            return
        with open(json_path) as f:
            data = json.load(f)
        index = data.get('index') if isinstance(data, dict) else None
        if not isinstance(index, dict):
            print(f"FoundationLinker: {json_path} has no 'index' dict; "
                  f"skipping (got keys: {list(data) if isinstance(data, dict) else type(data).__name__})")
            return
        loaded = 0
        for key, entry in index.items():
            if not isinstance(entry, dict):
                continue
            eid = entry.get('id') or f"unified:{key}"
            entry = {**entry, 'id': eid}
            self._entries[eid] = entry
            loaded += 1
        self._build_index()
        meta = data.get('meta', {}) or {}
        srcs = meta.get('books_sources') or []
        print(f"FoundationLinker: loaded {loaded} unified entries from {json_path}")
        print(f"  index_size meta={meta.get('index_size')}, "
              f"books_count meta={meta.get('books_count')}, "
              f"{len(self._term_index)} unique terms indexed")

    def _build_index(self) -> None:
        """Build term index from entry names for substring matching."""
        self._term_index = {}
        for eid, entry in self._entries.items():
            name = entry.get('name', '')
            if not name:
                continue
            # Clean and normalize the name
            terms = self._extract_searchable_terms(name)
            for term in terms:
                if len(term) < 4:  # skip very short terms
                    continue
                self._term_index.setdefault(term, []).append(entry)

    def _extract_searchable_terms(self, name: str) -> List[str]:
        """
        Extract searchable terms from an entry name.
        E.g., "Cauchy-Schwarz Inequality" -> ["cauchy-schwarz inequality", "cauchy-schwarz"]
        Also handles NaturalProofs names like "Brooks' Theorem" or "Spectral Gap Theorem".
        """
        terms = []
        # Full name, lowered and normalized
        clean = name.strip().lower()
        # Remove possessive apostrophes for matching flexibility
        clean_no_apos = clean.replace("'s ", " ").replace("' ", " ")
        # Remove common prefixes/suffixes that don't help matching
        for prefix in ['definition of ', 'definition:', 'theorem:']:
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip()
                clean_no_apos = clean_no_apos[len(prefix):].strip()
        if clean:
            terms.append(clean)
        if clean_no_apos != clean:
            terms.append(clean_no_apos)

        # Also index without trailing "theorem", "lemma", etc.
        for suffix in [' theorem', ' lemma', ' inequality', ' formula',
                        ' conjecture', ' proposition', ' identity', ' law',
                        ' bound', ' principle']:
            for variant in [clean, clean_no_apos]:
                if variant.endswith(suffix):
                    base = variant[:-len(suffix)].strip()
                    if len(base) >= 4:
                        terms.append(base)

        return list(set(terms))

    def link_paper(self, paper_graph: PaperGraph,
                   min_term_len: int = 6) -> List[Relation]:
        """
        Link extracted paper objects to foundation graph entries.

        For each object in the paper, search its clean_text and raw_latex
        for foundation entry names. Returns list of new Relation objects.

        Args:
            paper_graph: The extracted paper's mid-level representation.
            min_term_len: Minimum term length to consider (avoids false positives).

        Returns:
            List of Relation objects (grounded_to edges).
        """
        new_relations = []
        seen = set()  # (source_id, target_id) to avoid duplicates

        for obj_id, obj in paper_graph.objects.items():
            # Build searchable text from the object
            texts = []
            if hasattr(obj, 'clean_text') and obj.clean_text:
                texts.append(obj.clean_text.lower())
            if hasattr(obj, 'raw_latex') and obj.raw_latex:
                texts.append(obj.raw_latex.lower())
            if hasattr(obj, 'label') and obj.label:
                texts.append(obj.label.lower())
            if hasattr(obj, 'name') and obj.name:
                texts.append(obj.name.lower())

            search_text = ' '.join(texts)
            if not search_text:
                continue

            # Match against foundation index
            for term, entries in self._term_index.items():
                if len(term) < min_term_len:
                    continue
                if term in search_text:
                    for entry in entries:
                        target_id = entry['id']
                        key = (obj_id, target_id)
                        if key in seen:
                            continue
                        seen.add(key)

                        rel = Relation(
                            source_id=obj_id,
                            target_id=target_id,
                            relation_type=REL_GROUNDED_TO,
                            category='conceptual',
                            metadata={
                                'matched_term': term,
                                'method': 'name_substring',
                                'confidence': 0.5,
                                'foundation_source': entry.get('source', ''),
                                'foundation_name': entry.get('name', ''),
                                'foundation_type': entry.get('type', ''),
                            }
                        )
                        new_relations.append(rel)

        return new_relations

    def link_and_update(self, paper_graph: PaperGraph,
                        min_term_len: int = 6) -> int:
        """
        Link paper objects to foundation graph and add relations in-place.
        Returns number of new relations added.
        """
        new_rels = self.link_paper(paper_graph, min_term_len=min_term_len)
        paper_graph.relations.extend(new_rels)
        return len(new_rels)

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics about the loaded foundation index."""
        type_counts = defaultdict(int)
        source_counts = defaultdict(int)
        for entry in self._entries.values():
            type_counts[entry.get('type', 'unknown')] += 1
            source_counts[entry.get('source', 'unknown')] += 1
        return {
            'total_entries': len(self._entries),
            'unique_terms': len(self._term_index),
            'by_type': dict(type_counts),
            'by_source': dict(source_counts),
        }


# =============================================================================
# CLI for testing
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Link paper extractions to the foundation knowledge graph.')
    parser.add_argument('--paper-json', required=True,
                        help='Path to paper mid-level JSON')
    parser.add_argument('--naturalproofs-dir', default=None,
                        help='Path to NaturalProofs midlevel/ directory '
                             '(legacy multi-file loader)')
    parser.add_argument('--unified-index', default=None,
                        help='Path to merged broad-math foundation file '
                             '(e.g. clean_foundation_with_books.json). '
                             'Replaces --naturalproofs-dir when given.')
    parser.add_argument('--mathlib-dir', default=None,
                        help='Path to Mathlib midlevel/ directory')
    parser.add_argument('--min-term-len', type=int, default=6,
                        help='Minimum term length for matching (default: 6)')
    parser.add_argument('--output', default=None,
                        help='Output JSON path (default: overwrite input)')

    args = parser.parse_args()

    # Load foundation index
    linker = FoundationLinker()
    if args.unified_index:
        linker.load_unified_index(args.unified_index)
    if args.naturalproofs_dir:
        linker.load_naturalproofs_index(args.naturalproofs_dir)
    if args.mathlib_dir:
        linker.load_mathlib_index(args.mathlib_dir)

    print(f"Foundation stats: {json.dumps(linker.get_stats(), indent=2)}")

    # Load paper
    with open(args.paper_json) as f:
        data = json.load(f)
    paper = PaperGraph.from_dict(data)

    # Link
    n_before = len(paper.relations)
    n_new = linker.link_and_update(paper, min_term_len=args.min_term_len)
    print(f"Added {n_new} grounded_to relations (was {n_before}, now {len(paper.relations)})")

    # Show matches
    for rel in paper.relations:
        if rel.relation_type == REL_GROUNDED_TO:
            meta = rel.metadata or {}
            src_obj = paper.objects.get(rel.source_id)
            src_label = getattr(src_obj, 'label', rel.source_id) if src_obj else rel.source_id
            print(f"  {src_label} -> {meta.get('foundation_name', rel.target_id)} "
                  f"[{meta.get('foundation_source', '?')}, "
                  f"matched: '{meta.get('matched_term', '?')}']")

    # Save
    out_path = args.output or args.paper_json
    with open(out_path, 'w') as f:
        json.dump(paper.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"Saved to {out_path}")


if __name__ == '__main__':
    main()
