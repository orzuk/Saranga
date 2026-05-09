#!/usr/bin/env python3
"""Show foundation-graph link statistics from extracted paper JSONs."""
import json
import glob
import sys
from collections import Counter

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

counts_all = Counter()
counts_specific = Counter()
n_linked = 0
n_total = 0
n_generic_edges = 0
n_specific_edges = 0

for jp in sorted(glob.glob(out_dir + "/**/*_rules.json", recursive=True)):
    n_total += 1
    with open(jp) as f:
        data = json.load(f)
    has_link = False
    for e in data.get("edges", []):
        if e.get("type") == "grounded_to":
            source = e.get("source", "?")
            is_generic = e.get("generic", False)
            counts_all[source] += 1
            has_link = True
            if is_generic:
                n_generic_edges += 1
            else:
                n_specific_edges += 1
                counts_specific[source] += 1
    if has_link:
        n_linked += 1

print(f"Papers with foundation links: {n_linked}/{n_total}")
print(f"Total grounded_to edges: {n_generic_edges + n_specific_edges}")
print(f"  Specific (df<=10%): {n_specific_edges}")
print(f"  Generic  (df>10%):  {n_generic_edges}")
print(f"Distinct foundation terms matched: {len(counts_all)}")
print(f"  Specific: {len(counts_specific)}")

print(f"\nTop 20 SPECIFIC matched foundation terms:")
for term, n in counts_specific.most_common(20):
    print(f"  {n:>4}  {term}")

print(f"\nTop 20 ALL matched foundation terms (including generic):")
for term, n in counts_all.most_common(20):
    tag = " [generic]" if term not in counts_specific else ""
    print(f"  {n:>4}  {term}{tag}")
