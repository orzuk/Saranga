"""Fetch arXiv titles for manifest entries with empty titles.

Usage:
    python scripts/fetch_arxiv_titles.py [--dry-run] [--batch-size 100]
"""
import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import urlopen

PORTAL_DIR = Path(__file__).resolve().parent.parent / "portal"
ARXIV_API = "http://export.arxiv.org/api/query"


def strip_arxiv_id(paper_id: str) -> str:
    """Extract clean arxiv ID: '1001.0340v3_manual' -> '1001.0340'."""
    clean = paper_id.replace("_manual", "").replace("_rules", "")
    clean = re.sub(r"v\d+$", "", clean)
    return clean


def fetch_titles(arxiv_ids: list[str]) -> dict[str, str]:
    """Query arXiv API for titles. Returns {arxiv_id: title}."""
    id_list = ",".join(arxiv_ids)
    url = f"{ARXIV_API}?id_list={id_list}&max_results={len(arxiv_ids)}"
    resp = urlopen(url, timeout=30)
    xml = resp.read().decode()
    root = ET.fromstring(xml)

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    titles = {}
    for entry in root.findall("atom:entry", ns):
        eid = entry.find("atom:id", ns)
        title = entry.find("atom:title", ns)
        if eid is not None and title is not None:
            # ID looks like http://arxiv.org/abs/1001.0340v3
            aid = eid.text.strip().split("/")[-1]
            aid_clean = re.sub(r"v\d+$", "", aid)
            t = " ".join(title.text.strip().split())  # normalize whitespace
            titles[aid_clean] = t
    return titles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--delay", type=float, default=5,
                        help="Seconds between API requests (default: 5)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest_path = PORTAL_DIR / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    # Collect all entries with empty titles across all tiers
    entries_to_fix = []
    for tier_key, papers in manifest.get("papers", {}).items():
        for entry in papers:
            if not entry.get("title"):
                entries_to_fix.append(entry)

    if not entries_to_fix:
        print("All entries already have titles!")
        return

    # Deduplicate arxiv IDs
    id_to_entries = {}
    for entry in entries_to_fix:
        aid = strip_arxiv_id(entry["paper_id"])
        id_to_entries.setdefault(aid, []).append(entry)

    unique_ids = sorted(id_to_entries.keys())
    print(f"Need titles for {len(unique_ids)} unique papers ({len(entries_to_fix)} entries)")

    if args.dry_run:
        for aid in unique_ids[:10]:
            print(f"  {aid}")
        if len(unique_ids) > 10:
            print(f"  ... and {len(unique_ids) - 10} more")
        return

    # Fetch in batches with retry and incremental saves
    fetched = 0
    failed = 0
    save_every = 500  # save manifest every N successful fetches
    since_save = 0
    for i in range(0, len(unique_ids), args.batch_size):
        batch = unique_ids[i:i + args.batch_size]
        end = i + len(batch)
        print(f"  Fetching {i+1}-{end} of {len(unique_ids)}...", end=" ", flush=True)
        ok = False
        for attempt in range(3):
            try:
                titles = fetch_titles(batch)
                for aid, title in titles.items():
                    for entry in id_to_entries.get(aid, []):
                        entry["title"] = title
                fetched += len(titles)
                since_save += len(titles)
                not_found = len(batch) - len(titles)
                if not_found:
                    print(f"ok ({len(titles)} found, {not_found} missing)")
                else:
                    print(f"ok ({len(titles)})")
                ok = True
                break
            except Exception as e:
                if attempt < 2:
                    wait = args.delay * (attempt + 2)
                    print(f"retry ({e})...", end=" ", flush=True)
                    time.sleep(wait)
                else:
                    print(f"FAILED after 3 attempts: {e}")
                    failed += len(batch)
        # Save incrementally
        if since_save >= save_every:
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False))
            print(f"    [saved — {fetched} titles so far]")
            since_save = 0
        if end < len(unique_ids):
            time.sleep(args.delay)

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nDone! Updated {fetched} titles ({failed} failed)")


if __name__ == "__main__":
    main()
