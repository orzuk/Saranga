#!/usr/bin/env python3
"""Rebuild tier3 manifest entries from local files on disk.

Scans portal/data/tier3/ for JSON files with matching HTML graphs and
adds any missing entries to the manifest. Safe to run anytime — existing
entries are preserved, only new ones are added.

Usage:
    python scripts/rebuild_tier3_manifest.py [--dry-run]
"""
import argparse
import json
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent.parent / "portal"

THM_TYPES = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"}
OTHER_TYPES = {"equation", "problem", "open_problem", "assumption", "example", "remark"}


def build_manifest_entry(paper_id, json_rel, graph_rel, category, nodes):
    tc = {}
    for n in nodes:
        t = n.get("type", "unknown")
        tc[t] = tc.get(t, 0) + 1
    return {
        "paper_id": paper_id,
        "display_id": paper_id.replace("_manual", ""),
        "title": "",
        "n_nodes": len(nodes),
        "type_counts": tc,
        "buckets": {
            "def": tc.get("definition", 0),
            "thm": sum(tc.get(t, 0) for t in THM_TYPES),
            "alg": tc.get("algorithm", 0),
            "pf": tc.get("proof", 0),
            "steps": tc.get("proof_step", 0) + tc.get("algorithm_step", 0),
            "other": sum(tc.get(t, 0) for t in OTHER_TYPES),
        },
        "top_node_types": sorted(tc.items(), key=lambda x: -x[1])[:6],
        "tier": 3,
        "category": category,
        "json_path": json_rel,
        "graph_path": graph_rel,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild tier3 manifest from local files")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest_path = PORTAL_DIR / "data" / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"papers": {"tier1": [], "tier2": [], "tier3": []}, "pairs": []}

    existing = {e["paper_id"]: e for e in manifest["papers"].get("tier3", [])}
    print(f"Existing tier3 in manifest: {len(existing)}")

    json_dir = PORTAL_DIR / "data" / "tier3"
    new_count = 0
    errors = 0
    for jf in sorted(json_dir.rglob("*.json")):
        pid = jf.stem
        if pid in existing:
            continue
        rel = jf.relative_to(json_dir)
        graph = PORTAL_DIR / "graphs" / "tier3" / rel.parent / (pid + ".html")
        if not graph.exists():
            continue
        json_rel = f"data/tier3/{rel}"
        graph_rel = f"graphs/tier3/{rel.parent}/{pid}.html"
        cat = str(rel.parts[0])
        try:
            data = json.loads(jf.read_text())
            entry = build_manifest_entry(
                pid, json_rel, graph_rel, cat, data.get("nodes", []))
            existing[pid] = entry
            new_count += 1
        except Exception as e:
            print(f"  skip {pid}: {e}")
            errors += 1

    print(f"New entries: {new_count} ({errors} errors)")

    if args.dry_run:
        print("Dry run — not writing manifest.")
        return

    manifest["papers"]["tier3"] = sorted(
        existing.values(), key=lambda e: e["paper_id"])
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False))
    total = len(manifest["papers"]["tier3"])
    print(f"Wrote {manifest_path}  (tier3: {total} papers)")


if __name__ == "__main__":
    main()
