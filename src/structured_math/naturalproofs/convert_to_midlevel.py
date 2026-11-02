"""
Convert NaturalProofs data (Zenodo) to Automath mid-level representation.

Uses the existing math_classes.py data model (TheoremLike, Definition, Proof,
Relation, PaperGraph) so the output is compatible with the rest of the Authomathics
pipeline (evaluation, visualization, etc.).

Input: NaturalProofs JSON files from https://zenodo.org/records/4902289
  - naturalproofs_proofwiki.json  (19K theorems, 12K definitions)
  - naturalproofs_stacks.json     (12K theorems, 1.7K definitions)
  - naturalproofs_trench.json     (298 theorems, 86 definitions)

Output per source file:
  - {source}_midlevel.json   : full PaperGraph-compatible JSON (objects + relations)
  - {source}_index.json      : lightweight search index (id, name, type, categories)
  - {source}_stats.json      : summary statistics
  - with --unified FILE: the definitions and named results as one unified graph (book format,
    {metadata, nodes, edges}) for the textbook concept layer (structured_math/books/concepts.py)

Usage:
    # Convert all files in a directory:
    python convert_to_midlevel.py --input-dir /path/to/zenodo/ --output-dir ./foundation_graph/

    # Convert a single file:
    python convert_to_midlevel.py --input-file naturalproofs_proofwiki.json --output-dir ./output/

    # ProofWiki definitions and named results for the book concept layer:
    python convert_to_midlevel.py --input-file naturalproofs_proofwiki.json --output-dir ./output/ \
        --unified $DATA/foundation/books_v7b/assembled/proofwiki.json

    # Test on first N entries per type:
    python convert_to_midlevel.py --input-file naturalproofs_proofwiki.json --output-dir ./output/ --limit 50
"""

import ast
import json
import re
import os
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any

# Resolve math_classes from src/LLMVersion/ (single source of truth)
REPO_ROOT = Path(__file__).resolve().parents[3]  # Authomathics/
sys.path.insert(0, str(REPO_ROOT / 'src' / 'LLMVersion'))

from math_classes import (
    TheoremLike, Definition, Proof, Relation, PaperGraph, MathObject
)
sys.path.insert(0, str(REPO_ROOT / 'src'))
from structured_math.books.concepts import RESULT_NAME  # noqa: E402


# ============================================================================
# ProofWiki markup cleaning
# ============================================================================

def clean_proofwiki_markup(text: str) -> str:
    """Convert ProofWiki/MediaWiki markup to cleaner text."""
    if not text:
        return ""
    # [[Definition:Foo|bar]] -> bar ;  [[Foo]] -> Foo
    text = re.sub(r'\[\[[^\]]*\|([^\]]*)\]\]', r'\1', text)
    text = re.sub(r'\[\[([^\]]*)\]\]', r'\1', text)
    # Templates
    text = re.sub(r'\{\{begin-eqn\}\}', '', text)
    text = re.sub(r'\{\{end-eqn\}\}', '', text)
    text = re.sub(r'\{\{eqn\s*\|[^}]*\}\}', '', text)
    text = re.sub(r'\{\{[^}]*\}\}', '', text)
    # :$...$ display math prefix
    text = re.sub(r'^:(\$)', r'\1', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def join_contents(contents: list) -> str:
    """Join a list of content lines into a single string."""
    if not contents:
        return ""
    return '\n'.join(str(c) for c in contents)


def heuristic_split_assumptions(text: str) -> tuple:
    """
    Simple heuristic: lines starting with 'Let', 'Suppose', 'Assume', 'Given'
    are assumptions; the rest is the conclusion.
    Returns (assumptions_list, conclusions_list), each a list of sentence
    strings. Matches the List[str] schema used by TheoremLike.
    """
    lines = text.strip().split('\n')
    assumption_lines = []
    conclusion_lines = []
    in_assumptions = True

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if in_assumptions and re.match(
            r'^(Let|Suppose|Assume|Given|Consider|If)\b', stripped, re.IGNORECASE
        ):
            assumption_lines.append(stripped)
        else:
            in_assumptions = False
            conclusion_lines.append(stripped)

    return (assumption_lines, conclusion_lines)


# ============================================================================
# Main conversion
# ============================================================================

def convert_naturalproofs_file(input_path: str, source_name: str,
                                limit: Optional[int] = None) -> dict:
    """
    Convert one NaturalProofs JSON file to Automath mid-level format.

    Returns dict with 'graph' (PaperGraph-compatible), 'index', and 'stats'.
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    dataset = raw.get('dataset', raw)

    objects = {}       # id -> MathObject
    relations = []     # list of Relation
    index_entries = []

    # ID mapping: NaturalProofs numeric id -> our string id
    np_id_to_our_id = {}

    # Running counters for index field
    counters = {'theorem': 0, 'definition': 0, 'proof': 0, 'other': 0}

    # --- Process theorems ---
    theorems = dataset.get('theorems', [])
    if limit:
        theorems = theorems[:limit]

    for item in theorems:
        our_id = f"T_{source_name}_{item['id']}"
        np_id_to_our_id[item['id']] = our_id

        raw_text = join_contents(item.get('contents', []))
        clean_text = clean_proofwiki_markup(raw_text)
        assumptions, conclusions = heuristic_split_assumptions(clean_text)

        counters['theorem'] += 1
        obj = TheoremLike(
            id=our_id,
            kind=item.get('type', 'theorem'),
            index=counters['theorem'],
            label=item.get('label', None),
            name=item.get('title', ''),
            raw_latex=raw_text,
            clean_text=clean_text,
            paper_id=f"naturalproofs_{source_name}",
            env_name=item.get('type', 'theorem'),
            assumptions=assumptions,
            conclusions=conclusions,
        )
        objects[our_id] = obj

        index_entries.append({
            'id': our_id,
            'name': item.get('title', ''),
            'type': item.get('type', 'theorem'),
            'source': source_name,
            'categories': item.get('categories', []),
        })

        # Proofs
        for p_idx, proof_data in enumerate(item.get('proofs', [])):
            proof_id = f"P_{source_name}_{item['id']}_{p_idx}"
            proof_raw = join_contents(proof_data.get('contents', []))

            counters['proof'] += 1
            proof_obj = Proof(
                id=proof_id,
                kind='proof',
                index=counters['proof'],
                label=None,
                name=f"Proof of {item.get('title', our_id)}",
                raw_latex=proof_raw,
                clean_text=clean_proofwiki_markup(proof_raw),
                paper_id=f"naturalproofs_{source_name}",
                parent_id=our_id,
            )
            objects[proof_id] = proof_obj

            relations.append(Relation(
                source_id=proof_id,
                target_id=our_id,
                relation_type='proves',
                category='logical',
            ))

            # Proof references
            for ref_id in proof_data.get('ref_ids', []):
                # Will resolve later
                relations.append(Relation(
                    source_id=proof_id,
                    target_id=f"__np_{ref_id}",  # placeholder
                    relation_type='uses',
                    category='logical',
                ))

        # Theorem references
        for ref_id in item.get('ref_ids', []):
            relations.append(Relation(
                source_id=our_id,
                target_id=f"__np_{ref_id}",
                relation_type='uses',
                category='logical',
            ))

    # --- Process definitions ---
    definitions = dataset.get('definitions', [])
    if limit:
        definitions = definitions[:limit]

    for item in definitions:
        our_id = f"D_{source_name}_{item['id']}"
        np_id_to_our_id[item['id']] = our_id

        raw_text = join_contents(item.get('contents', []))
        clean_text = clean_proofwiki_markup(raw_text)

        counters['definition'] += 1
        obj = Definition(
            id=our_id,
            kind='definition',
            index=counters['definition'],
            label=item.get('label', None),
            name=item.get('title', ''),
            raw_latex=raw_text,
            clean_text=clean_text,
            paper_id=f"naturalproofs_{source_name}",
            env_name='definition',
        )
        objects[our_id] = obj

        index_entries.append({
            'id': our_id,
            'name': item.get('title', ''),
            'type': 'definition',
            'source': source_name,
            'categories': item.get('categories', []),
        })

        for ref_id in item.get('ref_ids', []):
            relations.append(Relation(
                source_id=our_id,
                target_id=f"__np_{ref_id}",
                relation_type='uses',
                category='logical',
            ))

    # --- Process "others" (lemmas, corollaries, etc.) ---
    others = dataset.get('others', dataset.get('other', []))
    if limit:
        others = others[:limit]

    for item in others:
        our_id = f"O_{source_name}_{item['id']}"
        np_id_to_our_id[item['id']] = our_id

        raw_text = join_contents(item.get('contents', []))
        clean_text = clean_proofwiki_markup(raw_text)
        assumptions, conclusions = heuristic_split_assumptions(clean_text)

        counters['other'] += 1
        obj = TheoremLike(
            id=our_id,
            kind=item.get('type', 'other'),
            index=counters['other'],
            label=item.get('label', None),
            name=item.get('title', ''),
            raw_latex=raw_text,
            clean_text=clean_text,
            paper_id=f"naturalproofs_{source_name}",
            env_name=item.get('type', 'other'),
            assumptions=assumptions,
            conclusions=conclusions,
        )
        objects[our_id] = obj

        index_entries.append({
            'id': our_id,
            'name': item.get('title', ''),
            'type': item.get('type', 'other'),
            'source': source_name,
            'categories': item.get('categories', []),
        })

        for ref_id in item.get('ref_ids', []):
            relations.append(Relation(
                source_id=our_id,
                target_id=f"__np_{ref_id}",
                relation_type='uses',
                category='logical',
            ))

    # --- Resolve placeholder IDs in relations ---
    resolved_relations = []
    unresolved_count = 0
    for rel in relations:
        if rel.target_id.startswith('__np_'):
            np_id = int(rel.target_id.replace('__np_', ''))
            if np_id in np_id_to_our_id:
                rel.target_id = np_id_to_our_id[np_id]
                resolved_relations.append(rel)
            else:
                unresolved_count += 1
        else:
            resolved_relations.append(rel)

    # Remove self-references
    resolved_relations = [r for r in resolved_relations if r.source_id != r.target_id]

    # Build stats
    stats = {
        'source': source_name,
        'total_objects': len(objects),
        'theorems': sum(1 for o in objects.values() if isinstance(o, TheoremLike) and o.kind == 'theorem'),
        'definitions': sum(1 for o in objects.values() if isinstance(o, Definition)),
        'proofs': sum(1 for o in objects.values() if isinstance(o, Proof)),
        'other': sum(1 for o in objects.values() if isinstance(o, TheoremLike) and o.kind not in ('theorem',)),
        'relations': len(resolved_relations),
        'unresolved_refs': unresolved_count,
    }

    return {
        'objects': objects,
        'relations': resolved_relations,
        'index': index_entries,
        'stats': stats,
    }


# ============================================================================
# Unified graph for the concept layer
# ============================================================================

# pages that are about words, history or notation, not mathematics ("Left Hand Side")
SKIP_CATEGORIES = {"Definitions/Language Definitions", "Definitions/Philosophy", "Historical Notes",
                   "Linguistic Notes", "Definitions/Branches of Mathematics"}
SKIP_SUBPAGES = {"Historical Note", "Linguistic Note", "Also known as", "Also defined as", "Examples",
                 "Notation", "Technical Note", "Mistake", "Symbol"}


def _term_and_sense(title: str) -> tuple:
    """"Definition:Ring (Abstract Algebra)/Definition 2" -> ("Ring", "Abstract Algebra"); a subpage
    that is not a numbered variant names the sense too ("Continuous Mapping/Metric Space")."""
    parts = re.sub(r"^Definition:", "", title).split("/")
    m = re.match(r"(.*?)\s*\(([^()]*)\)\s*$", parts[0])
    term, senses = (m.group(1), [m.group(2)]) if m else (parts[0], [])
    senses += [x for x in parts[1:] if not re.match(r"Definition \d+$|General Definition$", x)]
    return term.strip(), " / ".join(senses) or None


def to_unified(result: dict, source_name: str) -> dict:
    """The definitions and the named results of a converted source as a unified graph: a
    definition node per page (definiendum = its title's term, sense = its qualifier), a theorem
    node with `main` for a result whose title is a name ("Pythagoras's Theorem"), and a `uses`
    edge for each reference between kept nodes. Proofs, unnamed results and pages about words,
    history or notation are left out."""
    cats = {e["id"]: e["categories"] for e in result["index"]}
    def categories(oid):
        c = cats.get(oid) or []
        return ast.literal_eval(c) if isinstance(c, str) else c     # the Zenodo file stores lists as their repr
    by_title = {o.name: oid for oid, o in result["objects"].items()}
    nodes = []
    for oid, o in result["objects"].items():
        title = o.name or ""
        if isinstance(o, Definition):
            if title.split("/")[-1] in SKIP_SUBPAGES or not (o.clean_text or "").strip():
                continue                       # an empty page lists its subpages (disambiguation)
            parent = by_title.get(title.split("/")[0], oid)   # a subpage inherits the page's categories
            if SKIP_CATEGORIES & set(categories(oid) or categories(parent)):
                continue
            term, sense = _term_and_sense(title)
            # a subpage defines the words it sets in bold ("Operation/Arity" defines '''arity''')
            # (a bold word that shares no word with the page's title is a side remark)
            title_words = set(re.findall(r"[a-z]+", title.lower()))
            bold = [b.strip() for b in re.findall(r"'''(.+?)'''", o.clean_text or "")
                    if 1 < len(b.strip()) <= 60 and "$" not in b
                    and title_words & set(re.findall(r"[a-z]+", b.lower()))]
            definiendum = bold if "/" in title and bold else term
            nodes.append({"id": oid, "type": "definition", "name": re.sub(r"^Definition:", "", title),
                          "statement": o.clean_text, "definiendum": definiendum, "sense": sense,
                          "origin": "external", "origin_citation": f"ProofWiki: {title}"})
        elif isinstance(o, TheoremLike) and o.kind == "theorem" and "/" not in title and RESULT_NAME.search(title):
            nodes.append({"id": oid, "type": "theorem", "name": title, "main": True,
                          "statement": o.clean_text, "origin": "external", "origin_citation": f"ProofWiki: {title}"})
    kept = {n["id"] for n in nodes}
    edges = [{"source": r.target_id, "target": r.source_id, "type": "uses", "basis": "named",
              "confidence": 0.9} for r in result["relations"]
             if r.relation_type == "uses" and r.source_id in kept and r.target_id in kept]
    meta = {"book_id": source_name, "title": f"NaturalProofs: {source_name}", "kind": "reference",
            "license": "CC BY-SA 3.0" if source_name == "proofwiki" else None, "chapters": []}
    return {"metadata": meta, "nodes": nodes, "edges": edges}


# ============================================================================
# Output
# ============================================================================

def write_output(result: dict, source_name: str, output_dir: str):
    """Write converted data using PaperGraph.to_dict() compatible format."""
    os.makedirs(output_dir, exist_ok=True)

    graph = PaperGraph(
        paper_id=f"naturalproofs_{source_name}",
        objects=result['objects'],
        relations=result['relations'],
    )

    # Write full graph as JSON
    data_path = os.path.join(output_dir, f"{source_name}_midlevel.json")
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(graph.to_dict(), f, indent=2, ensure_ascii=False)
    n_obj = len(result['objects'])
    n_rel = len(result['relations'])
    print(f"  Data:  {data_path} ({n_obj} objects, {n_rel} relations)")

    # Write index
    index_path = os.path.join(output_dir, f"{source_name}_index.json")
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(result['index'], f, indent=2, ensure_ascii=False)
    print(f"  Index: {index_path} ({len(result['index'])} entries)")

    # Write stats
    stats_path = os.path.join(output_dir, f"{source_name}_stats.json")
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(result['stats'], f, indent=2)
    print(f"  Stats: {stats_path}")
    for k, v in result['stats'].items():
        print(f"    {k}: {v}")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Convert NaturalProofs (Zenodo) to Automath mid-level JSON.'
    )
    parser.add_argument('--input-dir', default=None,
                        help='Directory with naturalproofs_*.json files')
    parser.add_argument('--input-file', default=None,
                        help='Single NaturalProofs JSON file')
    parser.add_argument('--output-dir', required=True,
                        help='Output directory')
    parser.add_argument('--limit', type=int, default=None,
                        help='Max entries per type (for testing)')
    parser.add_argument('--unified', default=None,
                        help='also write the definitions and named results as a unified graph (with --input-file)')

    args = parser.parse_args()

    if args.input_file:
        source = Path(args.input_file).stem.replace('naturalproofs_', '')
        print(f"Converting {args.input_file} (source: {source})...")
        result = convert_naturalproofs_file(args.input_file, source, limit=args.limit)
        write_output(result, source, args.output_dir)
        if args.unified:
            g = to_unified(result, source)
            Path(args.unified).parent.mkdir(parents=True, exist_ok=True)
            Path(args.unified).write_text(json.dumps(g, ensure_ascii=False), encoding='utf-8')
            print(f"  Unified: {args.unified} ({len(g['nodes'])} nodes, {len(g['edges'])} edges)")

    elif args.input_dir:
        for fname in sorted(os.listdir(args.input_dir)):
            if fname.startswith('naturalproofs_') and fname.endswith('.json'):
                source = fname.replace('naturalproofs_', '').replace('.json', '')
                print(f"\n=== Converting {fname} (source: {source}) ===")
                result = convert_naturalproofs_file(
                    os.path.join(args.input_dir, fname), source, limit=args.limit
                )
                write_output(result, source, args.output_dir)
    else:
        parser.error("Specify --input-dir or --input-file")


if __name__ == '__main__':
    main()
