#!/bin/bash
# Compare Herald statement names vs LeanDojo names to diagnose low match rate
# Herald statements: 579K entries but only 11K match LeanDojo (1.96%)
# Herald proofs: 44.5K entries and 40K match (90.5%)

source /sci/labs/orzuk/orzuk/authomathics-venv/bin/activate

DATA_DIR=/sci/labs/orzuk/orzuk/projects/Authomathics

python3 << 'PYEOF'
import json
import re
import os
from collections import defaultdict

DATA_DIR = os.environ.get('DATA_DIR', '/sci/labs/orzuk/orzuk/projects/Authomathics')

# Load LeanDojo names
print("Loading LeanDojo names...")
leandojo_names = set()
corpus_path = os.path.join(DATA_DIR, 'mathlib/raw/leandojo_benchmark_4/corpus.jsonl')
with open(corpus_path) as f:
    for line in f:
        entry = json.loads(line)
        for p in entry.get('premises', []):
            leandojo_names.add(p['full_name'])

print(f"  LeanDojo: {len(leandojo_names)} unique full names")

# Build suffix index
suffix_to_full = defaultdict(list)
for fn in leandojo_names:
    suffix = fn.rsplit('.', 1)[-1] if '.' in fn else fn
    suffix_to_full[suffix].append(fn)

# Load Herald statements names from local JSONL
statements_path = os.path.join(DATA_DIR, 'mathlib/raw/herald_statements.jsonl')
print(f"\nLoading Herald statement names from {statements_path}...")

herald_names = []
with open(statements_path) as f:
    for line in f:
        entry = json.loads(line)
        formal = entry['formal_statement']
        m = re.search(r'(?:theorem|def|lemma|instance|class|structure|abbrev)\s+(\S+?)(?:_extracted)?\s', formal)
        if m:
            name = m.group(1).replace('_extracted', '')
            herald_names.append(name)

print(f"  Herald statements: {len(herald_names)} names extracted")

# Check matching
exact = 0
suffix_unique = 0
suffix_ambig = 0
no_match = 0
sample_no_match = []

for name in herald_names:
    clean = name.replace('_extracted', '')
    if clean in leandojo_names:
        exact += 1
    else:
        candidates = suffix_to_full.get(clean, [])
        if len(candidates) == 1:
            suffix_unique += 1
        elif len(candidates) > 1:
            suffix_ambig += 1
        else:
            no_match += 1
            if len(sample_no_match) < 10:
                sample_no_match.append(clean)

print(f"\nMatching breakdown:")
print(f"  Exact match:       {exact}")
print(f"  Suffix unique:     {suffix_unique}")
print(f"  Suffix ambiguous:  {suffix_ambig}")
print(f"  No match:          {no_match}")

# Now do the same for proofs
proofs_path = os.path.join(DATA_DIR, 'mathlib/raw/herald_proofs.jsonl')
print(f"\nLoading Herald proof names from {proofs_path}...")
proof_names = []
with open(proofs_path) as f:
    for line in f:
        entry = json.loads(line)
        name = entry.get('name', '').replace('_extracted', '')
        if name:
            proof_names.append(name)

print(f"  Herald proofs: {len(proof_names)} names")

exact_p = 0
suffix_unique_p = 0
suffix_ambig_p = 0
no_match_p = 0
sample_no_match_p = []

for name in proof_names:
    if name in leandojo_names:
        exact_p += 1
    else:
        candidates = suffix_to_full.get(name.rsplit('.', 1)[-1] if '.' in name else name, [])
        if len(candidates) == 1:
            suffix_unique_p += 1
        elif len(candidates) > 1:
            suffix_ambig_p += 1
        else:
            no_match_p += 1
            if len(sample_no_match_p) < 10:
                sample_no_match_p.append(name)

print(f"\nProof matching breakdown:")
print(f"  Exact match:       {exact_p}")
print(f"  Suffix unique:     {suffix_unique_p}")
print(f"  Suffix ambiguous:  {suffix_ambig_p}")
print(f"  No match:          {no_match_p}")

print(f"\nSample UNMATCHED statement names:")
for s in sample_no_match[:10]:
    print(f"  {s}")

print(f"\nSample UNMATCHED proof names:")
for s in sample_no_match_p[:10]:
    print(f"  {s}")

# Show a few LeanDojo names for comparison
sample_ld = sorted(leandojo_names)[:10]
print(f"\nSample LeanDojo full names:")
for s in sample_ld:
    print(f"  {s}")
PYEOF
