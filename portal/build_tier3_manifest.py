#!/usr/bin/env python3
"""
Fetch the list of HTML graph files from the RHCPP/saranga HF Space
and build the tier3 section of data/manifest.json.

Usage:
    python build_tier3_manifest.py
"""

import json
import re
import urllib.request
from pathlib import Path

SPACE_API = "https://huggingface.co/api/spaces/RHCPP/saranga/tree/main/html"
GRAPH_BASE = "https://rhcpp-saranga.static.hf.space/html"

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "data" / "manifest.json"


def fetch_json(url: str) -> list:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> None:
    # Load existing manifest
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    else:
        manifest = {"papers": {"tier1": [], "tier2": [], "tier3": []}, "pairs": []}

    # Get category folders
    print("Fetching category list...")
    categories = []
    for item in fetch_json(SPACE_API):
        if item.get("type") == "directory":
            cat = item["path"].split("/")[-1]  # e.g. "math_GR"
            categories.append(cat)
    print(f"  Found {len(categories)} categories: {', '.join(sorted(categories))}")

    # Fetch files per category
    tier3 = []
    for cat in sorted(categories):
        url = f"{SPACE_API}/{cat}"
        print(f"  {cat}: ", end="", flush=True)
        files = fetch_json(url)
        n = 0
        for f in files:
            fname = f["path"].split("/")[-1]  # e.g. "1001.0212v2_manual.html"
            if not fname.endswith(".html"):
                continue
            paper_id = fname.replace("_manual.html", "")
            graph_url = f"{GRAPH_BASE}/{cat}/{fname}"
            tier3.append({
                "paper_id": paper_id,
                "title": "",
                "n_nodes": 0,
                "category": cat.replace("_", "."),
                "graph_url": graph_url,
                "tier": 3,
            })
            n += 1
        print(f"{n} papers")

    manifest["papers"]["tier3"] = tier3

    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote {MANIFEST_PATH}  (tier3: {len(tier3)} papers)")


if __name__ == "__main__":
    main()
