#!/usr/bin/env python3
"""
Delete confirmed PDF parses: both the garbage JSON and the source .tex file.

Reads verified_pdfs.csv and deletes files where tier == 'confirmed_pdf'.
Runs in dry-run mode by default — prints what would be deleted without
actually deleting anything. Pass --execute to perform the deletion.

Usage:
    # Dry run (safe — just prints):
    python scripts/delete_confirmed_pdfs.py \
        --csv verified_pdfs.csv \
        --parsed-dir /path/to/parsed_100k

    # Actual deletion:
    python scripts/delete_confirmed_pdfs.py \
        --csv verified_pdfs.csv \
        --parsed-dir /path/to/parsed_100k \
        --execute
"""

import argparse
import csv
import os


def main():
    parser = argparse.ArgumentParser(description="Delete confirmed PDF parses")
    parser.add_argument("--csv", required=True,
                        help="verified_pdfs.csv from verify_pdf_suspects.py")
    parser.add_argument("--parsed-dir", required=True,
                        help="Root of parsed output (e.g. .../parsed_100k)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually delete files. Without this flag, only prints what would be deleted.")
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"Mode: {mode}", flush=True)

    with open(args.csv, "r") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r["tier"] == "confirmed_pdf"]

    print(f"Found {len(rows):,} confirmed_pdf entries\n", flush=True)

    json_deleted = 0
    json_missing = 0
    json_total_bytes = 0
    tex_deleted = 0
    tex_missing = 0
    tex_total_bytes = 0
    errors = []

    for i, row in enumerate(rows):
        # JSON path
        json_path = os.path.join(args.parsed_dir, row["category"], "json", row["json_file"])
        tex_path = row.get("tex_path", "")

        # --- JSON file ---
        if os.path.exists(json_path):
            size = os.path.getsize(json_path)
            json_total_bytes += size
            if args.execute:
                try:
                    os.remove(json_path)
                    json_deleted += 1
                except Exception as e:
                    errors.append(f"JSON {json_path}: {e}")
            else:
                json_deleted += 1  # count as "would delete"
                if i < 10:
                    print(f"  [JSON] {json_path}  ({size:,} bytes)")
        else:
            json_missing += 1
            if json_missing <= 3:
                print(f"  [JSON NOT FOUND] {json_path}")

        # --- TEX file ---
        if tex_path and os.path.exists(tex_path):
            size = os.path.getsize(tex_path)
            tex_total_bytes += size
            if args.execute:
                try:
                    os.remove(tex_path)
                    tex_deleted += 1
                except Exception as e:
                    errors.append(f"TEX {tex_path}: {e}")
            else:
                tex_deleted += 1
                if i < 10:
                    print(f"  [TEX]  {tex_path}  ({size:,} bytes)")
        elif tex_path:
            tex_missing += 1

    # Summary
    def fmt_size(b):
        if b >= 1_048_576:
            return f"{b / 1_048_576:.1f} MB"
        elif b >= 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b} B"

    verb = "Deleted" if args.execute else "Would delete"
    print(f"\n{'='*60}")
    print(f"Summary ({mode})")
    print(f"{'='*60}")
    print(f"  JSON files:  {verb} {json_deleted:,}  ({fmt_size(json_total_bytes)})")
    print(f"  JSON missing (already deleted?): {json_missing:,}")
    print(f"  TEX files:   {verb} {tex_deleted:,}  ({fmt_size(tex_total_bytes)})")
    print(f"  TEX missing: {tex_missing:,}")
    print(f"  Total space freed: {fmt_size(json_total_bytes + tex_total_bytes)}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"    {e}")

    if not args.execute:
        print(f"\n  (This was a dry run. Pass --execute to actually delete.)")

    print(f"{'='*60}")


if __name__ == "__main__":
    main()
