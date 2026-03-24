"""
Convert Lean Mathlib data (LeanDojo + Herald) to Automath mid-level representation.

Input sources (both downloadable, no Lean required):
  1. LeanDojo Benchmark 4 (Zenodo): theorem names, file paths, tactic proofs, premises
     Download: https://zenodo.org/records/15382959/files/leandojo_benchmark_4.tar.gz
  2. Herald statements (HuggingFace): NL descriptions of Mathlib theorems
     HuggingFace: FrenzyMath/Herald_statements
  3. Herald proofs (HuggingFace): NL proofs of Mathlib theorems
     HuggingFace: FrenzyMath/Herald_proofs

The script:
  - Loads LeanDojo corpus (theorem names, code, dependencies)
  - Loads Herald NL translations (matched by theorem name)
  - Merges into mid-level JSON using Automath math_classes

Usage:
    # Step 1: Download LeanDojo (do this first manually):
    #   wget https://zenodo.org/records/15382959/files/leandojo_benchmark_4.tar.gz
    #   tar xzf leandojo_benchmark_4.tar.gz

    # Step 2: Run conversion (Herald downloaded automatically via HuggingFace):
    python convert_to_midlevel.py \\
        --leandojo-dir /path/to/leandojo_benchmark_4 \\
        --output-dir /path/to/output \\
        --herald   # optional: also download and merge Herald NL descriptions

    # Test with limit:
    python convert_to_midlevel.py --leandojo-dir ./leandojo_benchmark_4 --output-dir ./test --limit 500
"""

import json
import re
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, List

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / 'src'))

from math_classes import (
    TheoremLike, Definition, Proof, Relation, PaperGraph
)


# ============================================================================
# LeanDojo loading
# ============================================================================

def load_leandojo_corpus(corpus_path: str, limit: Optional[int] = None) -> dict:
    """
    Load LeanDojo corpus.jsonl — one line per Lean file, each containing premises.

    Returns:
        name2premise: dict mapping full_name -> {full_name, code, kind, file_path}
        file_deps: dict mapping file_path -> list of imported file paths
    """
    name2premise = {}
    file_deps = {}
    count = 0

    with open(corpus_path, 'r') as f:
        for line in f:
            entry = json.loads(line)
            file_path = entry['path']
            file_deps[file_path] = entry.get('imports', [])

            for p in entry.get('premises', []):
                if limit and count >= limit:
                    break
                p['file_path'] = file_path
                name2premise[p['full_name']] = p
                count += 1

            if limit and count >= limit:
                break

    return name2premise, file_deps


def load_leandojo_theorems(leandojo_dir: str) -> list:
    """
    Load theorem entries from train/val/test JSON files.
    Returns list of {full_name, file_path, traced_tactics, ...}.
    """
    theorems = []
    for split_dir in ['random', 'novel_premises']:
        dir_path = os.path.join(leandojo_dir, split_dir)
        if not os.path.isdir(dir_path):
            continue
        for split_file in ['train.json', 'val.json', 'test.json']:
            fpath = os.path.join(dir_path, split_file)
            if os.path.exists(fpath):
                with open(fpath) as f:
                    data = json.load(f)
                # Deduplicate by full_name (same theorem in random/ and novel_premises/)
                for d in data:
                    d['_split_dir'] = split_dir
                    d['_split'] = split_file.replace('.json', '')
                theorems.extend(data)
    return theorems


def extract_dependencies_from_tactics(traced_tactics: list) -> list:
    """
    Extract premise names referenced in annotated tactics.
    LeanDojo format: annotated_tactic is [tactic_string, [[premise_name, file, start, end], ...]]
    """
    deps = set()
    for tactic_info in traced_tactics:
        annotated = tactic_info.get('annotated_tactic')
        if not annotated:
            continue
        # Format: [tactic_text, [{"full_name": ..., "def_path": ..., ...}, ...]]
        if isinstance(annotated, list) and len(annotated) >= 2:
            for premise_ref in annotated[1]:
                if isinstance(premise_ref, dict) and 'full_name' in premise_ref:
                    deps.add(premise_ref['full_name'])
                elif isinstance(premise_ref, list) and len(premise_ref) >= 1:
                    deps.add(premise_ref[0])
        elif isinstance(annotated, str):
            # Fallback: older format with <a> tags
            for m in re.finditer(r'<a>(.*?)</a>', annotated):
                deps.add(m.group(1))
    return list(deps)


# ============================================================================
# Herald loading
# ============================================================================

def load_herald_statements(limit: Optional[int] = None) -> dict:
    """
    Load Herald NL statements from HuggingFace.
    Returns dict mapping cleaned theorem name -> informal_statement.
    """
    from datasets import load_dataset

    print("  Loading Herald statements from HuggingFace...")
    ds = load_dataset('FrenzyMath/Herald_statements', split='train',
                       streaming=True)

    name2nl = {}
    count = 0
    for entry in ds:
        formal = entry['formal_statement']
        # Extract theorem name: "theorem NAME_extracted ..." or "def NAME_extracted ..."
        m = re.search(
            r'(?:theorem|def|lemma|instance|class|structure|abbrev)\s+(\S+?)(?:_extracted)?\s',
            formal
        )
        if m:
            name = m.group(1)
            clean_name = name.replace('_extracted', '')
            name2nl[clean_name] = entry['informal_statement']
            if name != clean_name:
                name2nl[name] = entry['informal_statement']

        count += 1
        if limit and count >= limit:
            break

    print(f"  Loaded {len(name2nl)} Herald NL statements")
    return name2nl


def build_herald_matcher(herald_nl: dict, all_full_names: list) -> dict:
    """
    Match Herald short names to LeanDojo full names.
    Herald uses 'foo_bar' while LeanDojo uses 'Namespace.foo_bar'.
    Build a map: full_name -> NL description.
    """
    # Index: short suffix -> list of full names
    suffix_to_full = defaultdict(list)
    for fn in all_full_names:
        # Last component after the last dot
        suffix = fn.rsplit('.', 1)[-1] if '.' in fn else fn
        suffix_to_full[suffix].append(fn)

    matched = {}
    ambiguous = 0
    for herald_name, nl_text in herald_nl.items():
        clean = herald_name.replace('_extracted', '')
        # Try exact match first
        if clean in {fn for fn in all_full_names}:
            matched[clean] = nl_text
            continue
        # Try suffix match
        candidates = suffix_to_full.get(clean, [])
        if len(candidates) == 1:
            matched[candidates[0]] = nl_text
        elif len(candidates) > 1:
            # Ambiguous — assign to all (better than none)
            for c in candidates:
                matched[c] = nl_text
            ambiguous += 1

    print(f"  Herald matcher: {len(matched)} matched ({ambiguous} ambiguous suffix matches)")
    return matched


def load_herald_proofs(limit: Optional[int] = None) -> dict:
    """
    Load Herald NL proofs from HuggingFace.
    Returns dict mapping theorem name -> {informal_theorem, informal_proof}.
    """
    from datasets import load_dataset

    print("  Loading Herald proofs from HuggingFace...")
    ds = load_dataset('FrenzyMath/Herald_proofs', split='train',
                       streaming=True)

    name2proof = {}
    count = 0
    for entry in ds:
        name = entry.get('name', '')
        if name:
            clean_name = name.replace('_extracted', '')
            name2proof[clean_name] = {
                'informal_theorem': entry.get('informal_theorem', ''),
                'informal_proof': entry.get('informal_proof', ''),
            }
        count += 1
        if limit and count >= limit:
            break

    print(f"  Loaded {len(name2proof)} Herald NL proofs")
    return name2proof


# ============================================================================
# Classify Lean declarations
# ============================================================================

def classify_lean_kind(full_name: str, code: str, decl_kind: str) -> str:
    """
    Classify a Lean declaration into theorem/definition/other.
    Lean kernel has: theorem, def, instance, inductive, structure, class, axiom, opaque.
    """
    if 'theorem' in code[:50] or decl_kind == 'theorem':
        return 'theorem'
    elif any(kw in code[:50] for kw in ['def ', 'noncomputable def']):
        # Heuristic: if name contains typical definition patterns
        if 'Definition' in full_name or 'Def' in full_name:
            return 'definition'
        return 'definition'
    elif 'instance' in code[:50]:
        return 'instance'  # typeclass instance — infrastructure, not math content
    elif 'structure' in code[:50] or 'class' in code[:50]:
        return 'definition'
    elif 'inductive' in code[:50]:
        return 'definition'
    elif 'axiom' in code[:50]:
        return 'axiom'
    else:
        return 'other'


# ============================================================================
# Main conversion
# ============================================================================

def convert_mathlib(leandojo_dir: str, output_dir: str,
                    use_herald: bool = False, limit: Optional[int] = None):
    """
    Convert LeanDojo + optional Herald data to Automath mid-level JSON.
    """
    print("Loading LeanDojo corpus...")
    corpus_path = os.path.join(leandojo_dir, 'corpus.jsonl')
    name2premise, file_deps = load_leandojo_corpus(corpus_path, limit=None)
    print(f"  {len(name2premise)} premises loaded")

    print("Loading LeanDojo theorems...")
    theorems = load_leandojo_theorems(leandojo_dir)
    # Deduplicate by full_name
    seen = set()
    unique_theorems = []
    for t in theorems:
        if t['full_name'] not in seen:
            seen.add(t['full_name'])
            unique_theorems.append(t)
    theorems = unique_theorems
    print(f"  {len(theorems)} unique theorems")

    # Load Herald if requested
    herald_nl = {}
    herald_proofs = {}
    if use_herald:
        print("Loading Herald data...")
        raw_herald_nl = load_herald_statements(limit=limit)
        raw_herald_proofs = load_herald_proofs(limit=limit)

        # Match Herald short names to LeanDojo full names
        all_full_names = list(name2premise.keys())
        herald_nl = build_herald_matcher(raw_herald_nl, all_full_names)
        herald_proofs_matched = build_herald_matcher(
            {k: json.dumps(v) for k, v in raw_herald_proofs.items()}, all_full_names
        )
        # Convert back from JSON strings
        herald_proofs = {}
        for fn, v_str in herald_proofs_matched.items():
            try:
                herald_proofs[fn] = json.loads(v_str)
            except:
                pass
        print(f"  Herald proofs matched: {len(herald_proofs)}")

    # Build objects
    print("Converting to mid-level representation...")
    objects = {}
    relations = []
    index_entries = []

    counters = {'theorem': 0, 'definition': 0, 'proof': 0, 'other': 0}

    # Process corpus premises (definitions, theorems, etc.)
    if limit:
        premises_to_process = dict(list(name2premise.items())[:limit])
    else:
        premises_to_process = name2premise

    for full_name, premise in premises_to_process.items():
        code = premise.get('code', '')
        kind = classify_lean_kind(full_name, code, premise.get('kind', ''))

        # Skip infrastructure (instances, recursors, etc.)
        if kind in ('instance', 'other') and not any(
            kw in full_name for kw in ['Theorem', 'Lemma', 'Proposition']
        ):
            continue

        our_id = f"ML_{full_name.replace('.', '_')}"

        # Get NL description from Herald if available
        nl_text = herald_nl.get(full_name, '')

        if kind == 'definition':
            counters['definition'] += 1
            obj = Definition(
                id=our_id,
                kind='definition',
                index=counters['definition'],
                label=full_name,
                name=full_name,
                raw_latex=code,
                clean_text=nl_text or code,
                paper_id='mathlib4',
                env_name='definition',
            )
        else:
            counters['theorem'] += 1
            obj = TheoremLike(
                id=our_id,
                kind=kind if kind in ('theorem', 'lemma', 'axiom') else 'theorem',
                index=counters['theorem'],
                label=full_name,
                name=full_name,
                raw_latex=code,
                clean_text=nl_text or code,
                paper_id='mathlib4',
                env_name=kind,
                assumptions='',  # Would need Lean type parsing to extract
                statement=nl_text or code,
            )

        objects[our_id] = obj
        index_entries.append({
            'id': our_id,
            'name': full_name,
            'type': kind,
            'source': 'mathlib4',
            'file_path': premise.get('file_path', ''),
        })

    # Add proof information from traced theorems
    # Map full_name -> our_id for both index entries and direct construction
    thm_name_to_id = {}
    for ie in index_entries:
        thm_name_to_id[ie['name']] = ie['id']

    for thm in theorems:
        thm_id = thm_name_to_id.get(thm['full_name'])
        if not thm_id:
            continue

        tactics = thm.get('traced_tactics', [])
        if not tactics:
            continue

        # Extract dependencies
        deps = extract_dependencies_from_tactics(tactics)
        for dep_name in deps:
            dep_id = thm_name_to_id.get(dep_name)
            if dep_id and dep_id != thm_id:
                relations.append(Relation(
                    source_id=thm_id,
                    target_id=dep_id,
                    relation_type='uses',
                    category='logical',
                ))

        # Add Herald NL proof if available
        herald_p = herald_proofs.get(thm['full_name'])
        if herald_p and herald_p.get('informal_proof'):
            counters['proof'] += 1
            proof_id = f"P_ML_{thm['full_name'].replace('.', '_')}"
            proof_obj = Proof(
                id=proof_id,
                kind='proof',
                index=counters['proof'],
                label=None,
                name=f"Proof of {thm['full_name']}",
                raw_latex='',
                clean_text=herald_p['informal_proof'],
                paper_id='mathlib4',
                parent_id=thm_id,
            )
            objects[proof_id] = proof_obj
            relations.append(Relation(
                source_id=proof_id,
                target_id=thm_id,
                relation_type='proves',
                category='logical',
            ))

    # Deduplicate relations
    seen_rels = set()
    unique_relations = []
    for r in relations:
        key = (r.source_id, r.target_id, r.relation_type)
        if key not in seen_rels:
            seen_rels.add(key)
            unique_relations.append(r)

    # Stats
    stats = {
        'source': 'mathlib4',
        'total_objects': len(objects),
        'theorems': counters['theorem'],
        'definitions': counters['definition'],
        'proofs': counters['proof'],
        'relations': len(unique_relations),
        'herald_nl_matched': len(herald_nl),
        'herald_proofs_matched': len(herald_proofs),
    }

    # Write output
    os.makedirs(output_dir, exist_ok=True)

    graph = PaperGraph(
        paper_id='mathlib4',
        objects=objects,
        relations=unique_relations,
    )

    data_path = os.path.join(output_dir, 'mathlib4_midlevel.json')
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(graph.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"  Data:  {data_path} ({len(objects)} objects, {len(unique_relations)} relations)")

    index_path = os.path.join(output_dir, 'mathlib4_index.json')
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index_entries, f, indent=2, ensure_ascii=False)
    print(f"  Index: {index_path} ({len(index_entries)} entries)")

    stats_path = os.path.join(output_dir, 'mathlib4_stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)
    print(f"  Stats:")
    for k, v in stats.items():
        print(f"    {k}: {v}")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Convert LeanDojo + Herald to Automath mid-level JSON.'
    )
    parser.add_argument('--leandojo-dir', required=True,
                        help='Path to extracted leandojo_benchmark_4/ directory')
    parser.add_argument('--output-dir', required=True,
                        help='Output directory')
    parser.add_argument('--herald', action='store_true',
                        help='Also load Herald NL descriptions from HuggingFace')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit entries (for testing)')

    args = parser.parse_args()
    convert_mathlib(
        args.leandojo_dir, args.output_dir,
        use_herald=args.herald, limit=args.limit
    )


if __name__ == '__main__':
    main()
