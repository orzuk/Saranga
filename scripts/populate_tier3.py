#!/usr/bin/env python3
"""Download papers from HF dataset and upload to HF space as tier3.

Usage:
    python scripts/populate_tier3.py [--per-category 50] [--dry-run]

Steps:
    1. List categories and files from RHCPP/saranga dataset
    2. Sample N papers per category
    3. Download json + html pairs to portal/data/tier3/{cat}/{year}/ and
       portal/graphs/tier3/{cat}/{year}/
    4. Build manifest entries with json_path / graph_path
    5. Upload to HF space
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from huggingface_hub import HfApi, list_repo_tree

DATASET_ID = "RHCPP/saranga"
SPACE_ID = "RHCPP/saranga"
PORTAL_DIR = Path(__file__).resolve().parent.parent / "portal"

THM_TYPES = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"}
OTHER_TYPES = {"equation", "problem", "open_problem", "assumption", "example", "remark"}


def arxiv_year(paper_id: str) -> str:
    """Extract year from arxiv id: '1001.0200v1_manual' -> '2010'."""
    yy = paper_id[:2]
    return "20" + yy


def build_manifest_entry(paper_id: str, json_path: str, graph_path: str,
                         category: str, nodes: list) -> dict:
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
        "json_path": json_path,
        "graph_path": graph_path,
    }


def list_dataset_categories(api: HfApi) -> list[str]:
    """List top-level category directories in the dataset."""
    items = list(list_repo_tree(DATASET_ID, repo_type="dataset", path_in_repo=""))
    cats = []
    for item in items:
        # Only dirs that have json/ and html/ subdirs (category dirs)
        if hasattr(item, "rfilename"):
            continue  # it's a file
        name = item.path if hasattr(item, "path") else str(item)
        # Skip non-category dirs
        if name.startswith(".") or name in ("alignment_benchmark",):
            continue
        cats.append(name)
    return sorted(cats)


def list_category_htmls(api: HfApi, category: str) -> list[str]:
    """List html filenames in a category's html/ dir (ensures both html+json exist)."""
    path = f"{category}/html"
    try:
        items = list(list_repo_tree(DATASET_ID, repo_type="dataset", path_in_repo=path))
    except Exception:
        return []
    names = []
    for item in items:
        fname = item.path.split("/")[-1] if hasattr(item, "path") else str(item).split("/")[-1]
        if fname.endswith(".html") and "_manual" in fname:
            names.append(fname)
    return sorted(names)


def download_file(url: str, dest: Path, retries: int = 3):
    """Download a file with retries."""
    for attempt in range(retries):
        try:
            urllib.request.urlretrieve(url, dest)
            return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"    FAILED: {e}")
                return False


def main():
    parser = argparse.ArgumentParser(description="Populate tier3 from HF dataset")
    parser.add_argument("--per-category", type=int, default=50,
                        help="Max papers per category (default: 50)")
    parser.add_argument("--category", type=str, default=None,
                        help="Single category to process (e.g. stat_TH, math_AG)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be downloaded without doing it")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Download and build manifest but don't upload to space")
    args = parser.parse_args()

    api = HfApi()
    dataset_base = f"https://huggingface.co/datasets/{DATASET_ID}/resolve/main"

    # Step 1: List categories
    if args.category:
        categories = [args.category]
        print(f"Single category: {args.category}")
    else:
        print("Listing categories...")
        categories = list_dataset_categories(api)
        print(f"  Found {len(categories)} categories: {', '.join(categories)}")

    # Step 2: List and sample files per category, spread across years
    all_papers = []  # (cat_raw, cat_display, paper_id, json_fname, html_fname)
    for cat in categories:
        cat_display = cat.replace("_", ".")
        print(f"  Listing {cat_display}...", end=" ", flush=True)
        htmls = list_category_htmls(api, cat)

        # Group by year (YYMM prefix -> 20YY)
        by_year = {}
        for hname in htmls:
            yy = hname[:2]
            year = "20" + yy
            by_year.setdefault(year, []).append(hname)

        # Sample evenly across years, round-robin
        n_target = args.per_category
        years_sorted = sorted(by_year.keys())
        per_year_base = max(1, n_target // len(years_sorted)) if years_sorted else 0
        sample = []
        # First pass: take up to per_year_base from each year
        remaining_budget = n_target
        for yr in years_sorted:
            take = min(per_year_base, len(by_year[yr]), remaining_budget)
            sample.extend(by_year[yr][:take])
            remaining_budget -= take
            if remaining_budget <= 0:
                break
        # Second pass: fill remaining budget from years that have more
        if remaining_budget > 0:
            for yr in years_sorted:
                already_taken = min(per_year_base, len(by_year[yr]))
                leftover = by_year[yr][already_taken:]
                take = min(len(leftover), remaining_budget)
                sample.extend(leftover[:take])
                remaining_budget -= take
                if remaining_budget <= 0:
                    break

        for hname in sample:
            paper_id = hname.replace(".html", "")
            json_name = paper_id + ".json"
            all_papers.append((cat, cat_display, paper_id, json_name, hname))

        year_counts = {yr: sum(1 for h in sample if h[:2] == yr[2:]) for yr in years_sorted}
        year_summary = ", ".join(f"{yr}:{c}" for yr, c in year_counts.items() if c > 0)
        print(f"{len(sample)} of {len(htmls)} ({year_summary})")

    print(f"\nTotal: {len(all_papers)} papers")

    if args.dry_run:
        print("Dry run — exiting.")
        return

    # Step 3: Download files
    print("\nDownloading...")
    tier3_entries = []
    failed = 0

    for i, (cat_raw, cat_display, paper_id, jname, hname) in enumerate(all_papers):
        year = arxiv_year(paper_id)
        json_rel = f"data/tier3/{cat_display}/{year}/{jname}"
        graph_rel = f"graphs/tier3/{cat_display}/{year}/{hname}"
        json_dest = PORTAL_DIR / json_rel
        graph_dest = PORTAL_DIR / graph_rel

        json_dest.parent.mkdir(parents=True, exist_ok=True)
        graph_dest.parent.mkdir(parents=True, exist_ok=True)

        # Skip if already downloaded
        if json_dest.exists() and graph_dest.exists():
            # Still need manifest entry
            try:
                data = json.loads(json_dest.read_text())
                entry = build_manifest_entry(paper_id, json_rel, graph_rel,
                                             cat_display, data.get("nodes", []))
                tier3_entries.append(entry)
            except Exception:
                pass
            continue

        print(f"  [{i+1}/{len(all_papers)}] {cat_display}/{year}/{paper_id}...", end=" ", flush=True)

        json_url = f"{dataset_base}/{cat_raw}/json/{jname}"
        html_url = f"{dataset_base}/{cat_raw}/html/{hname}"

        ok_j = download_file(json_url, json_dest)
        ok_h = download_file(html_url, graph_dest)

        if ok_j and ok_h:
            try:
                data = json.loads(json_dest.read_text())
                entry = build_manifest_entry(paper_id, json_rel, graph_rel,
                                             cat_display, data.get("nodes", []))
                tier3_entries.append(entry)
                print("ok")
            except Exception as e:
                print(f"json parse error: {e}")
                failed += 1
        else:
            failed += 1
            # Clean up partial downloads
            json_dest.unlink(missing_ok=True)
            graph_dest.unlink(missing_ok=True)

    print(f"\nDownloaded {len(tier3_entries)} papers ({failed} failed)")

    # Step 4: Update manifest (merge with existing tier3 entries from other categories)
    manifest_path = PORTAL_DIR / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    existing = manifest["papers"].get("tier3", [])
    # Remove entries for categories we just processed, keep the rest
    processed_cats = set(e["category"] for e in tier3_entries)
    kept = [e for e in existing if e.get("category") not in processed_cats]
    manifest["papers"]["tier3"] = kept + tier3_entries
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    total = len(manifest["papers"]["tier3"])
    print(f"Manifest updated: {len(tier3_entries)} new + {len(kept)} existing = {total} tier3 entries")

    if args.skip_upload:
        print("Skipping upload.")
        return

    # Step 5: Upload to space per category (one commit each, retry on rate limit)
    print("\nUploading to HF space...")

    import re as _re

    def _upload_with_retry(allow, label="files"):
        for attempt in range(5):
            try:
                api.upload_folder(
                    folder_path=str(PORTAL_DIR),
                    repo_id=SPACE_ID,
                    repo_type="space",
                    allow_patterns=allow,
                )
                return True
            except Exception as e:
                err = str(e)
                if "429" in err:
                    # Extract wait time from error message
                    m = _re.search(r"in (?:about )?(\d+) minute", err)
                    wait = int(m.group(1)) * 60 + 60 if m else 3660
                    print(f"\n    Rate limited. Waiting {wait//60} min...", flush=True)
                    time.sleep(wait)
                else:
                    print(f"\n    Error: {e}")
                    if attempt < 4:
                        time.sleep(30)
                    else:
                        return False
        return False

    # Upload manifest + JS first
    print("  manifest + JS...", end=" ", flush=True)
    _upload_with_retry(["js/paper.js", "js/list.js", "papers_tier3.html", "data/manifest.json"], "JS+manifest")
    print("ok")

    # Upload each category
    all_entries = manifest["papers"]["tier3"]
    cats = sorted(set(e["category"] for e in all_entries))
    for cat in cats:
        cat_entries = [e for e in all_entries if e["category"] == cat]
        allow = []
        for e in cat_entries:
            allow.append(e["json_path"])
            allow.append(e["graph_path"])
        print(f"  {cat}: {len(allow)} files...", end=" ", flush=True)
        _upload_with_retry(allow, cat)
        print("ok")

    print(f"\nDone! {len(all_entries)} papers across {len(cats)} categories.")


if __name__ == "__main__":
    main()
