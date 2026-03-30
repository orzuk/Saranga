#!/bin/bash
# Find Herald examples that are CONCRETE and INTERESTING:
# - Probability inequalities (Markov, Chebyshev, Hoeffding, ...)
# - Graph existence/properties (chromatic number, clique, matching, ...)
# - Combinatorial identities (binomial, Catalan, Stirling, ...)
# - Matrix identities (det, trace, rank, ...)
# - Classic named results
#
# Strategy: combine namespace prefix + NL content patterns
# Run on cluster: bash scripts/find_herald_examples_favorites.sh

source /sci/labs/orzuk/orzuk/authomathics-venv/bin/activate

DATA_DIR=/sci/labs/orzuk/orzuk/projects/Authomathics

python3 << 'PYEOF'
import json
import os
import re

DATA_DIR = os.environ.get('DATA_DIR', '/sci/labs/orzuk/orzuk/projects/Authomathics')
proofs_path = os.path.join(DATA_DIR, 'mathlib/raw/herald_proofs.jsonl')

# Each target: (label, name_patterns, nl_patterns)
# name_patterns: substrings to match in theorem name
# nl_patterns: substrings to match in NL theorem text (lowered)
TARGETS = [
    # Probability / measure inequalities
    ('prob_inequality',
     ['markov', 'chebyshev', 'hoeffding', 'chernoff', 'jensen',
      'ProbabilityTheory', 'variance', 'expect'],
     ['probability', 'expected value', 'expectation', 'variance',
      'random variable', 'almost surely', 'a.e.']),

    # Graph theory
    ('graph_theory',
     ['SimpleGraph', 'Coloring', 'chromatic', 'clique', 'Walk',
      'Hamiltonian', 'Connectivity', 'degree'],
     ['graph', 'vertex', 'edge', 'adjacent', 'coloring', 'chromatic',
      'clique', 'path', 'cycle', 'connected', 'degree']),

    # Combinatorial identities / counting
    ('combinatorial_identity',
     ['Nat.choose', 'Nat.factorial', 'Nat.descFactorial', 'catalan',
      'Finset.card', 'Finset.sum', 'Finset.prod', 'Nat.fibonacci',
      'bernoulli', 'stirling', 'Composition', 'Partition'],
     ['binomial', 'choose', 'factorial', 'pascal', 'vandermonde',
      'inclusion-exclusion', 'pigeonhole', 'counting',
      'catalan', 'fibonacci', 'partition']),

    # Matrix / linear algebra concrete
    ('matrix_concrete',
     ['Matrix.det', 'Matrix.trace', 'Matrix.rank', 'Matrix.mul',
      'Matrix.transpose', 'Matrix.inv', 'Matrix.eigenvalue',
      'Matrix.PosSemidef', 'Matrix.PosDef', 'det_', 'trace_'],
     ['determinant', 'trace', 'transpose', 'eigenvalue', 'rank',
      'positive definite', 'invertible matrix', 'matrix multiplication']),

    # Polynomial identities
    ('polynomial',
     ['Polynomial.eval', 'Polynomial.degree', 'Polynomial.root',
      'Polynomial.coeff', 'Polynomial.div'],
     ['polynomial', 'root', 'coefficient', 'degree of']),

    # Classic inequalities (AM-GM, Cauchy-Schwarz, triangle, ...)
    ('classic_inequality',
     ['inner_mul_le', 'sq_nonneg', 'abs_add', 'norm_add',
      'MeanInequalities', 'pow_arith_mean'],
     ['cauchy-schwarz', 'triangle inequality', 'am-gm',
      'arithmetic mean', 'geometric mean', 'holder',
      'minkowski', 'young']),

    # Basic real analysis (concrete functions)
    ('real_functions',
     ['Real.exp_', 'Real.log_', 'Real.sqrt_', 'Real.sin_', 'Real.cos_',
      'Real.rpow', 'Real.exp_add', 'Real.log_mul'],
     ['exponential', 'logarithm', 'sine', 'cosine',
      'square root', 'power function']),
]

count = 0
found = {label: [] for label, _, _ in TARGETS}

with open(proofs_path) as f:
    for line in f:
        entry = json.loads(line)
        name = entry.get('name', '')
        informal_thm = entry.get('informal_theorem', '')
        formal_thm = entry.get('formal_theorem', '')
        informal_proof = entry.get('informal_proof', '')
        formal_proof = entry.get('formal_proof', '')

        # Readability filters
        if not (60 < len(informal_thm) < 600
                and 30 < len(informal_proof) < 800
                and len(formal_proof) < 600):
            count += 1
            continue

        name_lower = name.lower()
        thm_lower = informal_thm.lower()

        for label, name_pats, nl_pats in TARGETS:
            if len(found[label]) >= 8:
                continue
            name_hit = any(p.lower() in name_lower for p in name_pats)
            nl_hit = any(p in thm_lower for p in nl_pats)
            if name_hit or nl_hit:
                found[label].append({
                    'name': name,
                    'informal_thm': informal_thm,
                    'formal_thm': formal_thm,
                    'informal_proof': informal_proof,
                    'formal_proof': formal_proof,
                    'match': 'name' if name_hit else 'nl',
                })

        count += 1

# Print
total = 0
for label, _, _ in TARGETS:
    examples = found[label]
    print(f'\n{"#" * 80}')
    print(f'# {label.upper().replace("_", " ")} ({len(examples)} examples)')
    print(f'{"#" * 80}')
    if not examples:
        print('  (none found)')
        continue
    for i, ex in enumerate(examples, 1):
        total += 1
        print(f'\n{"=" * 70}')
        print(f'Example {i}: {ex["name"]}  [matched via {ex["match"]}]')
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

print(f'\n\n{"=" * 70}')
print(f'Scanned {count} entries, found {total} examples')
for label, _, _ in TARGETS:
    print(f'  {label:25s}: {len(found[label])}')
PYEOF
