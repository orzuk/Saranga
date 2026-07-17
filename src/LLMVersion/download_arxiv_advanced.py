#!/usr/bin/env python3
"""
Advanced by-date arXiv downloader (no parsing).

Downloads full-paper source for every arXiv paper in a date range into the
"advanced" per-paper layout:

    <out-dir>/<year>/<month>/<day>/<versioned_id>/<versioned_id>.tex      (unified/flattened tex)
    <out-dir>/<year>/<month>/<day>/<versioned_id>/<versioned_id>.tar.gz   (original source archive)

This is the same layout as `full_papers_advanced`, but driven by a DATE RANGE
instead of a category CSV (`download_from_csv.py`). With no `--category` filter
you get the whole arXiv for that range, with no category level in the tree.

It reuses the existing infra:
  - fetch_arxiv_batch(formats="metadata")      -> lists IDs from the LOCAL
                                                  JSONL+HDF5 snapshot (fast, no API)
  - resolve_source_to_tex_local_first(..., use_paper_subdir=True)
                                               -> advanced per-paper download
                                                  (fetch + flatten \\input + keep tar.gz)

Downloads run SEQUENTIALLY (one paper at a time) to avoid arXiv API rate-limit
problems seen with parallel jobs. Resolution is local-first, so re-running the
same range simply skips papers already on disk (free resume).

Usage (download one batch of years into all_arxiv_papers):

    python download_arxiv_advanced.py \
        --start 2000-01-01 --end 2003-12-31 \
        --out-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/all_arxiv_papers \
        --verbose

    # next batches: 2004-01-01..2007-12-31, ... up to 2025, and 1991-01-01.. for the earliest.

    # resume after a crash from a specific base id:
    python download_arxiv_advanced.py --start 2000-01-01 --end 2003-12-31 \
        --out-dir .../all_arxiv_papers --start-from 0704.1234
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from config import FULL_PAPERS_ADVANCED_DIR
from extract_arxiv_funcs import (
    fetch_arxiv_batch,
    resolve_source_to_tex_local_first,
)


def _pub_date(md: dict) -> datetime:
    for key in ("published", "created"):
        if md.get(key):
            try:
                return datetime.strptime(str(md[key])[:10], "%Y-%m-%d")
            except Exception:
                pass
    return datetime(1970, 1, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download full arXiv sources by date range into the advanced per-paper layout."
    )
    parser.add_argument("--start", dest="start_date", required=True,
                        help="Start date YYYY-MM-DD (submission date, inclusive).")
    parser.add_argument("--end", dest="end_date", required=True,
                        help="End date YYYY-MM-DD (submission date, inclusive).")
    parser.add_argument("--category", "-c", default=None,
                        help="Optional arXiv category filter (e.g. cs.CC). "
                             "Omit for the WHOLE arXiv in the range (no category level in the tree).")
    parser.add_argument("--regex-id", default=None,
                        help='Optional regex filter on IDs, e.g. "^2001\\.0".')
    parser.add_argument("--out-dir", default=FULL_PAPERS_ADVANCED_DIR,
                        help="Root output directory (default: FULL_PAPERS_ADVANCED_DIR from config).")
    parser.add_argument("--top-k", type=int, default=0,
                        help="Cap number of papers (<=0 means no limit; download everything in range).")
    parser.add_argument("--start-from", default=None,
                        help="Resume: skip papers until this base id is reached (in sorted order).")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="Seconds to sleep between paper downloads (be gentle on the arXiv API).")
    parser.add_argument("--verbose", action="store_true", help="Verbose debug prints.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    top_k = args.top_k if args.top_k and args.top_k > 0 else None

    print(f"[INFO] Listing metadata for {args.start_date} .. {args.end_date}"
          + (f" category={args.category}" if args.category else " (all categories)"))

    # ---- 1. List IDs + metadata from the LOCAL snapshot (no source download yet) ----
    data = fetch_arxiv_batch(
        regex_id=args.regex_id,
        start_date=args.start_date,
        end_date=args.end_date,
        category=args.category,
        formats="metadata",
        output_dir=None,
        verbose=args.verbose,
        top_k=(top_k * 3) if top_k else None,
    )
    if not data:
        print("[WARN] No papers matched the filters. Nothing to do.")
        return

    # ---- 2. Collapse versioned -> base id (keep metadata) ----
    base_to_meta: Dict[str, Dict[str, Any]] = {}
    for vid, entry in data.items():
        base_id = vid.split("v")[0]
        base_to_meta[base_id] = entry.get("metadata", entry)

    # ---- 3. Sort ascending by (date, id) for deterministic, resumable runs ----
    items = sorted(base_to_meta.items(), key=lambda kv: (_pub_date(kv[1]), kv[0]))
    if top_k:
        items = items[:top_k]

    # ---- 4. Resume support ----
    if args.start_from:
        idx = next((i for i, (bid, _) in enumerate(items) if bid == args.start_from), None)
        if idx is None:
            print(f"[WARN] --start-from {args.start_from} not found in range; downloading all.")
        else:
            skipped = idx
            items = items[idx:]
            print(f"[INFO] Resuming from {args.start_from} (skipped {skipped} earlier papers).")

    total = len(items)
    print(f"[INFO] {total} papers to download into {out_dir}")

    status_log = out_dir / "download_status_log.csv"
    ok = 0
    fail = 0
    for i, (base_id, md) in enumerate(items, start=1):
        print(f"\n[INFO] ({i}/{total}) {base_id}")
        try:
            tex_path, versioned_id = resolve_source_to_tex_local_first(
                base_id=base_id,
                meta=md,
                full_papers_dir=out_dir,
                verbose=args.verbose,
                use_paper_subdir=True,
            )
            ok += 1
            with open(status_log, "a", newline="") as f:
                csv.writer(f).writerow([base_id, versioned_id, "OK", str(tex_path)])
            print(f"[OK]   {versioned_id} -> {tex_path}")
        except Exception as e:
            fail += 1
            with open(status_log, "a", newline="") as f:
                csv.writer(f).writerow([base_id, "", f"ERROR: {e}", ""])
            print(f"[WARN] Failed {base_id}: {e}")

        if args.sleep and i < total:
            time.sleep(args.sleep)

    print(f"\n[DONE] {ok} downloaded, {fail} failed, {total} total. Log: {status_log}")


if __name__ == "__main__":
    main()
