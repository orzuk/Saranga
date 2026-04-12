#!/bin/bash
# Find readable Herald examples showing NL + Lean 4 side by side
# Run on cluster: bash scripts/find_herald_examples.sh

source /sci/labs/orzuk/orzuk/authomathics-venv/bin/activate

DATA_DIR=/sci/labs/orzuk/orzuk/projects/Authomathics

python3 << 'PYEOF'
import json
import os

DATA_DIR = os.environ.get('DATA_DIR', '/sci/labs/orzuk/orzuk/projects/Authomathics')
proofs_path = os.path.join(DATA_DIR, 'mathlib/raw/herald_proofs.jsonl')

count = 0
found = 0
with open(proofs_path) as f:
    for line in f:
        entry = json.loads(line)
        name = entry.get('name', '')
        informal_thm = entry.get('informal_theorem', '')
        formal_thm = entry.get('formal_theorem', '')
        informal_proof = entry.get('informal_proof', '')
        formal_proof = entry.get('formal_proof', '')

        # Filter for short, readable, interesting examples
        if (100 < len(informal_thm) < 500
            and 50 < len(informal_proof) < 600
            and len(formal_proof) < 400
            and any(kw in informal_thm.lower() for kw in
                    ['prime', 'sum', 'continuous', 'converge', 'group',
                     'inequality', 'finite', 'injective', 'surjective',
                     'compact', 'open set', 'subgroup', 'divides',
                     'even', 'odd', 'square', 'inverse', 'identity'])):

            found += 1
            print('=' * 80)
            print(f'Example {found}: {name}')
            print()
            print('--- Natural language theorem ---')
            print(informal_thm)
            print()
            print('--- Lean 4 formal statement ---')
            print(formal_thm)
            print()
            print('--- Natural language proof ---')
            print(informal_proof)
            print()
            print('--- Lean 4 formal proof ---')
            print(formal_proof)
            print()

            if found >= 10:
                break

        count += 1

print(f'\nScanned {count} entries, found {found} readable examples')
PYEOF
