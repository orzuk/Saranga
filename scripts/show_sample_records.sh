#!/bin/bash
# Print one full sample record from each dataset: LeanDojo, Herald statements, Herald proofs

source /<cluster>/<user>/authomathics-venv/bin/activate

DATA_DIR=/<cluster>/<user>/projects/Authomathics

python3 << 'PYEOF'
import json
import os

DATA_DIR = os.environ.get('DATA_DIR', '/<cluster>/<user>/projects/Authomathics')

# 1. LeanDojo corpus.jsonl — one line = one Lean FILE with its premises
print("=" * 80)
print("1. LeanDojo corpus.jsonl — ONE FILE ENTRY (showing first premise in detail)")
print("=" * 80)
corpus_path = os.path.join(DATA_DIR, 'mathlib/raw/leandojo_benchmark_4/corpus.jsonl')
with open(corpus_path) as f:
    # Find an entry with a theorem premise
    for line in f:
        entry = json.loads(line)
        premises = entry.get('premises', [])
        has_thm = any('theorem' in p.get('code', '')[:50] for p in premises)
        if has_thm and len(premises) > 0:
            print(f"\nFile-level keys: {list(entry.keys())}")
            print(f"  path: {entry['path']}")
            print(f"  imports: {entry.get('imports', [])[:3]} ... ({len(entry.get('imports', []))} total)")
            print(f"  premises: {len(premises)} in this file")
            # Show first theorem premise in full
            for p in premises:
                if 'theorem' in p.get('code', '')[:50]:
                    print(f"\n  --- First theorem premise (all fields) ---")
                    for k, v in p.items():
                        val = str(v)
                        if len(val) > 300:
                            val = val[:300] + "..."
                        print(f"    {k}: {val}")
                    break
            break

# 2. LeanDojo theorem entry (from train/val/test JSON)
print("\n" + "=" * 80)
print("2. LeanDojo theorem entry (from random/train.json)")
print("=" * 80)
train_path = os.path.join(DATA_DIR, 'mathlib/raw/leandojo_benchmark_4/random/train.json')
with open(train_path) as f:
    data = json.load(f)
    # Pick a smallish entry
    for t in data:
        if t.get('traced_tactics') and len(str(t)) < 2000:
            print(f"\nKeys: {list(t.keys())}")
            for k, v in t.items():
                val = str(v)
                if len(val) > 400:
                    val = val[:400] + "..."
                print(f"  {k}: {val}")
            break

# 3. Herald statement
print("\n" + "=" * 80)
print("3. Herald statement (all fields)")
print("=" * 80)
stmt_path = os.path.join(DATA_DIR, 'mathlib/raw/herald_statements.jsonl')
with open(stmt_path) as f:
    line = f.readline()
    entry = json.loads(line)
    print(f"\nKeys: {list(entry.keys())}")
    for k, v in entry.items():
        val = str(v)
        if len(val) > 500:
            val = val[:500] + "..."
        print(f"  {k}: {val}")

# 4. Herald proof
print("\n" + "=" * 80)
print("4. Herald proof (all fields)")
print("=" * 80)
proof_path = os.path.join(DATA_DIR, 'mathlib/raw/herald_proofs.jsonl')
with open(proof_path) as f:
    line = f.readline()
    entry = json.loads(line)
    print(f"\nKeys: {list(entry.keys())}")
    for k, v in entry.items():
        val = str(v)
        if len(val) > 500:
            val = val[:500] + "..."
        print(f"  {k}: {val}")
PYEOF
