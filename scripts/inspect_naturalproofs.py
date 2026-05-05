#!/usr/bin/env python3
"""Inspect NaturalProofs entry structure — show fields and sample content."""
import json
import sys
from pathlib import Path

# Auto-detect data dir
candidates = [
    Path("/<cluster>/<user>/projects/Authomathics"),
    Path("/mnt/c/Datasets/Authomathics_data"),
    Path.home() / "Datasets" / "Authomathics_data",
]
data_dir = None
for c in candidates:
    if (c / "naturalproofs" / "raw").exists():
        data_dir = c
        break

if data_dir is None:
    print("ERROR: Could not find NaturalProofs data.")
    sys.exit(1)

base = data_dir / "naturalproofs" / "raw"

for fp in sorted(base.glob("naturalproofs_*.json")):
    with open(fp) as f:
        data = json.load(f)
    ds = data.get("dataset", data)
    items = []
    if isinstance(ds, list):
        items = ds
    elif isinstance(ds, dict):
        for cat, cat_items in ds.items():
            if isinstance(cat_items, list):
                items.extend(cat_items)

    print(f"\n{'='*60}")
    print(f"SOURCE: {fp.name} ({len(items)} items)")
    print(f"{'='*60}")
    shown = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "") or item.get("name", "")
        if not title or len(title) < 10:
            continue
        print(f"\n  Title: {title}")
        print(f"  Keys: {list(item.keys())}")
        for k, v in item.items():
            if k == "title":
                continue
            print(f"    {k}: {str(v)[:200]}")
        shown += 1
        if shown >= 3:
            break
