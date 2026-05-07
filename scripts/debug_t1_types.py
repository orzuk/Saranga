#!/usr/bin/env python3
"""For each provider's T1 JSONs, what node types ARE present?"""
import json
import glob
from collections import Counter
from pathlib import Path

T1_DIR = Path("portal/data/tier1")

manual_papers = sorted(T1_DIR.glob("*_manual.json"))
manual_papers = [p for p in manual_papers if "candes_tao" not in p.name and "sinkhorn" not in p.name]

# Aggregate type counts per provider across the 10 papers
agg = {"manual": Counter(), "anthropic": Counter(), "openai": Counter()}

for gold in manual_papers:
    aid = gold.stem.replace("_manual", "")
    for suffix, key in [("_manual", "manual"), ("_anthropic", "anthropic"), ("_openai", "openai")]:
        f = T1_DIR / f"{aid}{suffix}.json"
        if not f.exists():
            continue
        try: d = json.load(open(f))
        except: continue
        nodes = d.get("nodes") or []
        types = Counter(n.get("type") for n in nodes if isinstance(n, dict))
        for t, n in types.items():
            agg[key][t] += n

# Print combined table
all_types = set()
for c in agg.values():
    all_types.update(c.keys())
all_types = sorted(all_types, key=str)

print(f"{'Type':<20s} {'manual':>10s} {'Opus':>10s} {'GPT-4o':>10s}")
print("-" * 55)
for t in all_types:
    print(f"{str(t):<20s} {agg['manual'].get(t,0):>10d} {agg['anthropic'].get(t,0):>10d} {agg['openai'].get(t,0):>10d}")
