#!/bin/bash
# Find Herald examples by Lean NAMESPACE prefix (much more precise than NL keywords)
# Mathlib organizes by topic, so prefix matching = topic matching
# Run on cluster: bash scripts/find_herald_examples_concrete.sh

source /sci/labs/orzuk/orzuk/authomathics-venv/bin/activate

DATA_DIR=/sci/labs/orzuk/orzuk/projects/Authomathics

python3 << 'PYEOF'
import json
import os

DATA_DIR = os.environ.get('DATA_DIR', '/sci/labs/orzuk/orzuk/projects/Authomathics')
proofs_path = os.path.join(DATA_DIR, 'mathlib/raw/herald_proofs.jsonl')

# Match by Lean namespace prefix — much more reliable than NL keywords
AREA_PREFIXES = {
    'matrices': ['Matrix.'],
    'linear_algebra': ['LinearMap.', 'LinearEquiv.', 'Module.', 'Submodule.'],
    'combinatorics_finset': ['Finset.', 'Fintype.', 'Multiset.'],
    'graph_theory': ['SimpleGraph.'],
    'polynomial': ['Polynomial.'],
    'nat_arithmetic': ['Nat.Prime', 'Nat.factorial', 'Nat.choose', 'Nat.gcd',
                       'Nat.Coprime', 'Nat.div', 'Nat.mod'],
    'real_analysis': ['Real.sqrt', 'Real.exp', 'Real.log', 'Real.sin', 'Real.cos',
                      'MeanInequalities'],
    'probability': ['ProbabilityTheory.'],
}

count = 0
found_by_area = {area: [] for area in AREA_PREFIXES}

with open(proofs_path) as f:
    for line in f:
        entry = json.loads(line)
        name = entry.get('name', '')
        informal_thm = entry.get('informal_theorem', '')
        formal_thm = entry.get('formal_theorem', '')
        informal_proof = entry.get('informal_proof', '')
        formal_proof = entry.get('formal_proof', '')

        # Filter for short, readable examples
        if not (60 < len(informal_thm) < 500
                and 30 < len(informal_proof) < 600
                and len(formal_proof) < 500):
            count += 1
            continue

        for area, prefixes in AREA_PREFIXES.items():
            if len(found_by_area[area]) >= 5:
                continue
            if any(name.startswith(p) or ('.' + p.rstrip('.') + '.') in name
                   for p in prefixes):
                found_by_area[area].append({
                    'name': name,
                    'informal_thm': informal_thm,
                    'formal_thm': formal_thm,
                    'informal_proof': informal_proof,
                    'formal_proof': formal_proof,
                })

        count += 1

# Print results grouped by area
total_found = 0
for area, examples in found_by_area.items():
    print(f'\n{"#" * 80}')
    print(f'# AREA: {area.upper().replace("_", " ")} ({len(examples)} examples)')
    print(f'{"#" * 80}')
    if not examples:
        print('  (no examples found)')
        continue
    for i, ex in enumerate(examples, 1):
        total_found += 1
        print(f'\n{"=" * 70}')
        print(f'Example {i}: {ex["name"]}')
        print()
        print('--- Natural language theorem ---')
        print(ex['informal_thm'])
        print()
        print('--- Lean 4 formal statement ---')
        print(ex['formal_thm'])
        print()
        print('--- Natural language proof ---')
        print(ex['informal_proof'])
        print()
        print('--- Lean 4 formal proof ---')
        print(ex['formal_proof'])

# Summary + counts of ALL entries per area (not just filtered)
print(f'\n\n{"=" * 70}')
print(f'SUMMARY: Scanned {count} entries, found {total_found} readable examples')
for area, examples in sorted(found_by_area.items()):
    print(f'  {area:25s}: {len(examples)} examples shown')

# Also count total entries per area (ignoring length filters)
print(f'\n--- Total entries per area (any length) ---')
area_total = {area: 0 for area in AREA_PREFIXES}
with open(proofs_path) as f:
    for line in f:
        name = json.loads(line).get('name', '')
        for area, prefixes in AREA_PREFIXES.items():
            if any(name.startswith(p) or ('.' + p.rstrip('.') + '.') in name
                   for p in prefixes):
                area_total[area] += 1
for area, n in sorted(area_total.items()):
    print(f'  {area:25s}: {n} total')
PYEOF
