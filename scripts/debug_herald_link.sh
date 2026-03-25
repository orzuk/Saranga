#!/bin/bash
# Check if Herald statements and proofs can be linked
# Compare fields and find shared keys

source /sci/labs/orzuk/orzuk/authomathics-venv/bin/activate

DATA_DIR=/sci/labs/orzuk/orzuk/projects/Authomathics

python3 << 'PYEOF'
import json
import os

DATA_DIR = os.environ.get('DATA_DIR', '/sci/labs/orzuk/orzuk/projects/Authomathics')

# Show sample entries from each dataset
print("=== Herald STATEMENTS sample (first 3) ===")
with open(os.path.join(DATA_DIR, 'mathlib/raw/herald_statements.jsonl')) as f:
    for i, line in enumerate(f):
        if i >= 3:
            break
        entry = json.loads(line)
        print(f"\nEntry {i}: keys = {list(entry.keys())}")
        for k, v in entry.items():
            val = str(v)[:200]
            print(f"  {k}: {val}")

print("\n\n=== Herald PROOFS sample (first 3) ===")
with open(os.path.join(DATA_DIR, 'mathlib/raw/herald_proofs.jsonl')) as f:
    for i, line in enumerate(f):
        if i >= 3:
            break
        entry = json.loads(line)
        print(f"\nEntry {i}: keys = {list(entry.keys())}")
        for k, v in entry.items():
            val = str(v)[:200]
            print(f"  {k}: {val}")

# Check if proof names appear as substrings in statement formal_statement
print("\n\n=== Linkage check ===")
# Load all proof names
proof_names = {}
with open(os.path.join(DATA_DIR, 'mathlib/raw/herald_proofs.jsonl')) as f:
    for line in f:
        entry = json.loads(line)
        name = entry.get('name', '').replace('_extracted', '')
        if name:
            proof_names[name] = entry.get('informal_theorem', '')[:100]

print(f"Unique proof names: {len(proof_names)}")

# Check how many statement formal_statements contain a proof name
import re
stmt_names = {}  # short_name -> formal_statement
with open(os.path.join(DATA_DIR, 'mathlib/raw/herald_statements.jsonl')) as f:
    for line in f:
        entry = json.loads(line)
        formal = entry['formal_statement']
        m = re.search(r'(?:theorem|def|lemma|instance|class|structure|abbrev)\s+(\S+?)(?:_extracted)?\s', formal)
        if m:
            short = m.group(1).replace('_extracted', '')
            stmt_names[short] = formal[:300]

print(f"Unique statement short names: {len(stmt_names)}")

# Try matching: proof qualified name suffix == statement short name
from collections import defaultdict
proof_suffix_to_full = defaultdict(list)
for pn in proof_names:
    suffix = pn.rsplit('.', 1)[-1] if '.' in pn else pn
    proof_suffix_to_full[suffix].append(pn)

linked = 0
linked_unique = 0
not_linked = 0
for short_name in stmt_names:
    candidates = proof_suffix_to_full.get(short_name, [])
    if len(candidates) == 1:
        linked_unique += 1
    elif len(candidates) > 1:
        linked += 1
    else:
        not_linked += 1

print(f"\nStatement→Proof linkage (via suffix matching):")
print(f"  Unique match:    {linked_unique}")
print(f"  Ambiguous match: {linked}")
print(f"  No match:        {not_linked}")
print(f"  (Proof dataset only has {len(proof_names)} names vs {len(stmt_names)} statement names)")
PYEOF
