#!/usr/bin/env python3
"""Debug why definition F1 = 0 in bootstrap_t1_cis.

Check, for each T1 paper:
  - how many definition-type nodes are in the manual gold
  - how many definition-type nodes are in the Opus (anthropic) extraction
  - how many definition-type nodes are in the GPT-4o (openai) extraction
  - what 'origin' values they have (paper / external)
"""
import json
import glob
from collections import Counter
from pathlib import Path

T1_DIR = Path("portal/data/tier1")

manual_papers = sorted(T1_DIR.glob("*_manual.json"))
manual_papers = [p for p in manual_papers if "candes_tao" not in p.name and "sinkhorn" not in p.name]

print(f"{'Paper':<22s} {'Tier':<10s} {'definition (paper)':>20s} {'definition (external)':>22s} {'definition (no origin)':>23s}")
print("-" * 110)
for gold in manual_papers:
    aid = gold.stem.replace("_manual", "")
    for suffix in ["_manual", "_anthropic", "_openai"]:
        f = T1_DIR / f"{aid}{suffix}.json"
        if not f.exists(): continue
        try:
            d = json.load(open(f))
        except: continue
        nodes = d.get("nodes") or []
        defs = [n for n in nodes if isinstance(n, dict) and n.get("type") == "definition"]
        n_paper = sum(1 for n in defs if (n.get("origin") or "").lower() == "paper")
        n_external = sum(1 for n in defs if (n.get("origin") or "").lower() == "external")
        n_none = sum(1 for n in defs if not n.get("origin"))
        tier = {"_manual": "manual", "_anthropic": "Opus", "_openai": "GPT-4o"}[suffix]
        print(f"{aid:<22s} {tier:<10s} {n_paper:>20d} {n_external:>22d} {n_none:>23d}")
    print()
