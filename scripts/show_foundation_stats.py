#!/usr/bin/env python3
"""Show foundation-graph link statistics from extracted paper JSONs."""
import json
import glob
import sys
from collections import Counter

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

counts = Counter()
n_linked = 0
n_total = 0

for jp in sorted(glob.glob(out_dir + "/**/*_manual.json", recursive=True)):
    n_total += 1
    with open(jp) as f:
        data = json.load(f)
    has_link = False
    for e in data.get("edges", []):
        if e.get("type") == "grounded_to":
            counts[e.get("source", "?")] += 1
            has_link = True
    if has_link:
        n_linked += 1

print(f"Papers with foundation links: {n_linked}/{n_total}")
print(f"Total grounded_to edges: {sum(counts.values())}")
print(f"Distinct foundation terms matched: {len(counts)}")
print()
print("Top 20 matched foundation terms:")
for term, n in counts.most_common(20):
    print(f"  {n:>4}  {term}")
