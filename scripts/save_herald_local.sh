#!/bin/bash
# Download Herald datasets from HuggingFace and save as local JSON files
# Output: $DATA_DIR/mathlib/raw/herald_statements.jsonl
#         $DATA_DIR/mathlib/raw/herald_proofs.jsonl

source /sci/labs/orzuk/orzuk/authomathics-venv/bin/activate

DATA_DIR=/sci/labs/orzuk/orzuk/projects/Authomathics
OUT_DIR=$DATA_DIR/mathlib/raw
mkdir -p $OUT_DIR

python3 << 'PYEOF'
import json
import os

DATA_DIR = os.environ.get('DATA_DIR', '/sci/labs/orzuk/orzuk/projects/Authomathics')
OUT_DIR = os.path.join(DATA_DIR, 'mathlib', 'raw')

from datasets import load_dataset

# Save Herald statements
print("Loading Herald statements...")
ds = load_dataset('FrenzyMath/Herald_statements', split='train', streaming=True)
out_path = os.path.join(OUT_DIR, 'herald_statements.jsonl')
count = 0
with open(out_path, 'w') as f:
    for entry in ds:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        count += 1
        if count % 100000 == 0:
            print(f"  statements: {count}...")
print(f"  Saved {count} statements to {out_path}")

# Save Herald proofs
print("Loading Herald proofs...")
ds2 = load_dataset('FrenzyMath/Herald_proofs', split='train', streaming=True)
out_path2 = os.path.join(OUT_DIR, 'herald_proofs.jsonl')
count = 0
with open(out_path2, 'w') as f:
    for entry in ds2:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        count += 1
        if count % 10000 == 0:
            print(f"  proofs: {count}...")
print(f"  Saved {count} proofs to {out_path2}")

print("\nDone! Files saved to:")
print(f"  {out_path}")
print(f"  {out_path2}")
PYEOF
