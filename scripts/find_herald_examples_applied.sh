#!/bin/bash
# Find Herald examples in applied/concrete areas:
# statistics, probability, combinatorics, linear algebra, number theory basics
# Run on cluster: bash scripts/find_herald_examples_applied.sh

source /sci/labs/orzuk/orzuk/authomathics-venv/bin/activate

DATA_DIR=/sci/labs/orzuk/orzuk/projects/Authomathics

python3 << 'PYEOF'
import json
import os

DATA_DIR = os.environ.get('DATA_DIR', '/sci/labs/orzuk/orzuk/projects/Authomathics')
proofs_path = os.path.join(DATA_DIR, 'mathlib/raw/herald_proofs.jsonl')

# Keywords by area - more concrete/applied math
AREA_KEYWORDS = {
    'probability': ['probability', 'expectation', 'expected value', 'variance',
                    'random variable', 'measure', 'measurable', 'almost everywhere',
                    'conditional', 'independent', 'markov', 'chebyshev'],
    'statistics': ['estimator', 'bias', 'sample', 'mean', 'median',
                   'sufficient statistic', 'maximum likelihood', 'bayes'],
    'combinatorics': ['binomial', 'factorial', 'choose', 'permutation',
                      'pigeonhole', 'inclusion-exclusion', 'counting',
                      'partition', 'graph coloring', 'chromatic',
                      'matching', 'ramsey', 'catalan', 'stirling',
                      'card', 'finset', 'multiset'],
    'linear_algebra': ['matrix', 'determinant', 'eigenvalue', 'rank',
                       'trace', 'transpose', 'invertible', 'linear map',
                       'linear combination', 'basis', 'dimension',
                       'inner product', 'orthogonal', 'norm',
                       'positive definite', 'symmetric', 'diagonal'],
    'number_theory_basic': ['divisible', 'modulo', 'gcd', 'lcm', 'coprime',
                            'congruence', 'remainder', 'quotient',
                            'fibonacci', 'arithmetic progression'],
    'analysis_basic': ['limit', 'derivative', 'integral', 'bounded',
                       'maximum', 'minimum', 'triangle inequality',
                       'absolute value', 'monotone', 'convex', 'concave',
                       'cauchy-schwarz', 'holder', 'jensen'],
}

count = 0
found_by_area = {area: [] for area in AREA_KEYWORDS}

with open(proofs_path) as f:
    for line in f:
        entry = json.loads(line)
        name = entry.get('name', '')
        informal_thm = entry.get('informal_theorem', '')
        formal_thm = entry.get('formal_theorem', '')
        informal_proof = entry.get('informal_proof', '')
        formal_proof = entry.get('formal_proof', '')

        # Filter for short, readable examples
        if not (80 < len(informal_thm) < 500
                and 40 < len(informal_proof) < 600
                and len(formal_proof) < 500):
            count += 1
            continue

        thm_lower = informal_thm.lower()
        name_lower = name.lower()

        for area, keywords in AREA_KEYWORDS.items():
            if len(found_by_area[area]) >= 5:
                continue
            if any(kw in thm_lower or kw in name_lower for kw in keywords):
                found_by_area[area].append({
                    'name': name,
                    'informal_thm': informal_thm,
                    'formal_thm': formal_thm,
                    'informal_proof': informal_proof,
                    'formal_proof': formal_proof,
                    'matched_keyword': next(kw for kw in keywords
                                            if kw in thm_lower or kw in name_lower),
                })

        count += 1

# Print results grouped by area
total_found = 0
for area, examples in found_by_area.items():
    if not examples:
        continue
    print(f'\n{"#" * 80}')
    print(f'# AREA: {area.upper().replace("_", " ")} ({len(examples)} examples)')
    print(f'{"#" * 80}')
    for i, ex in enumerate(examples, 1):
        total_found += 1
        print(f'\n{"=" * 70}')
        print(f'Example {i}: {ex["name"]}')
        print(f'(matched keyword: "{ex["matched_keyword"]}")')
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

# Summary
print(f'\n\n{"=" * 70}')
print(f'SUMMARY: Scanned {count} entries')
for area, examples in sorted(found_by_area.items()):
    print(f'  {area:25s}: {len(examples)} examples found')
print(f'  {"TOTAL":25s}: {total_found}')
PYEOF
