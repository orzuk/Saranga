#!/bin/bash
# Debug Herald dataset sizes and name extraction rates
# Run on cluster: bash scripts/debug_herald_counts.sh

source /sci/labs/orzuk/orzuk/authomathics-venv/bin/activate

python3 << 'PYEOF'
from datasets import load_dataset
import re

# Count raw Herald statements
print("Loading Herald statements...")
ds = load_dataset('FrenzyMath/Herald_statements', split='train', streaming=True)
total_s, matched_s = 0, 0
sample_misses = []
for entry in ds:
    total_s += 1
    formal = entry['formal_statement']
    m = re.search(r'(?:theorem|def|lemma|instance|class|structure|abbrev)\s+(\S+?)(?:_extracted)?\s', formal)
    if m:
        matched_s += 1
    elif len(sample_misses) < 5:
        sample_misses.append(formal[:120])

print(f'Herald statements: {total_s} total, {matched_s} regex-matched ({100*matched_s/max(total_s,1):.1f}%)')
print(f'  Missed by regex: {total_s - matched_s}')
if sample_misses:
    print(f'  Sample misses:')
    for s in sample_misses:
        print(f'    {s}')

# Count raw Herald proofs
print("\nLoading Herald proofs...")
ds2 = load_dataset('FrenzyMath/Herald_proofs', split='train', streaming=True)
total_p, matched_p = 0, 0
for entry in ds2:
    total_p += 1
    if entry.get('name', ''):
        matched_p += 1

print(f'Herald proofs: {total_p} total, {matched_p} with name ({100*matched_p/max(total_p,1):.1f}%)')
print(f'  Missing name: {total_p - matched_p}')
PYEOF
