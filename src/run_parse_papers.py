#!/usr/bin/env python3
"""
Batch runner for math_paper_parser on many arXiv papers, using Or's existing
arXiv infrastructure (extract_arxiv_funcs / extract_arxiv_data).

It does NOT read any external metadata JSON file directly. Instead it uses
fetch_arxiv_batch(), which internally uses:

  - arxiv-metadata-oai-snapshot.json / HDF5 index
  - list_arxiv_ids_local / list_arxiv_ids_remote

Example usages (from repo root):

  # last 30 days, math.PR, up to 20 papers, JSON only
  python run_parse_papers.py \
      --category math.PR \
      --days 30 \
      --top-k 20 \
      --out-dir parsed_math_pr_30d

  # explicit date range, any math category, draw graphs as PNGs
  python run_parse_papers.py \
      --start 2025-01-01 \
      --end   2025-01-31 \
      --category math.PR \
      --top-k 10 \
      --out-dir parsed_math_jan2025 \
      --draw-graphs
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from math_paper_parser import (
    PaperParser,
    resolve_source_to_tex,
    paper_to_network,
)

# THIS is your infra for IDs + metadata + local HDF5 snapshot:
from extract_arxiv_funcs import fetch_arxiv_batch


def compute_date_range(
    start: Optional[str],
    end: Optional[str],
    days: Optional[int],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Decide start_date / end_date strings in 'YYYY-MM-DD' format for fetch_arxiv_batch.

    Priority:
      - If start/end explicitly given, use them as-is.
      - Else if days is given, use [today - days, today].
      - Else no date filter.
    """
    if start or end:
        return start, end

    if days is None:
        return None, None

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days)
    end_date = today
    return start_date.isoformat(), end_date.isoformat()


def run_batch(
    start_date: Optional[str],
    end_date: Optional[str],
    category: Optional[str],
    regex_id: Optional[str],
    top_k: Optional[int],
    out_dir: Path,
    draw_graphs: bool,
    verbose: bool,
) -> None:
    print(
        f"[INFO] Fetching arXiv IDs via fetch_arxiv_batch "
        f"(start={start_date}, end={end_date}, category={category}, regex_id={regex_id})"
    )

    # Use your existing infrastructure to get IDs + metadata (no sources here!)
    # formats='metadata' → fast local metadata via JSONL + HDF5, no PDF/source downloads.
    data = fetch_arxiv_batch(
        regex_id=regex_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        formats="metadata",
        output_dir=None,     # don't save any PDFs/sources here
        verbose=verbose,
    )

    if verbose:
        print(f"[DEBUG] fetch_arxiv_batch returned {len(data)} versioned IDs")

    if not data:
        print("[WARN] No papers matched the filters. Nothing to do.")
        return

    # Collapse versioned IDs ("2309.00543v1") → base IDs ("2309.00543").
    base_to_meta: Dict[str, Dict[str, Any]] = {}
    for vid, entry in data.items():
        base_id = vid.split("v")[0]
        md = entry.get("metadata", entry)  # depending on how you call fetch_arxiv_batch
        # Keep the "latest" metadata per base_id (arbitrary here; doesn't matter much)
        base_to_meta[base_id] = md

    print(f"[INFO] Collapsed to {len(base_to_meta)} unique base IDs.")

    # Sort by created/published date if available, so "top_k" is somewhat meaningful
    def extract_date(md: Dict[str, Any]) -> datetime:
        # Try a few keys inside metadata
        for key in ("published", "created", "versions"):
            val = md.get(key)
            if not val:
                continue
            if key == "versions":
                # typical arXiv JSON: versions[0]['created'] = "Tue, 1 Jan 2019 00:00:00 GMT"
                try:
                    created_full = val[0].get("created", "")
                    # we only need YYYY-MM-DD, but we'll parse robustly later if you want
                    # here: naive fallback: split on comma and space
                    # but we can just ignore and fallback if parsing fails
                except Exception:
                    continue
            # For "published" or "created", we might have ISO or RFC-style; we'll try first 10 chars
            s = str(val)[:10]
            try:
                return datetime.strptime(s, "%Y-%m-%d")
            except Exception:
                continue
        # fallback: very old date
        return datetime(1970, 1, 1)

    items = list(base_to_meta.items())
    items.sort(key=lambda kv: extract_date(kv[1]), reverse=True)  # newest first

    if top_k is not None and top_k > 0 and len(items) > top_k:
        items = items[:top_k]

    print(f"[INFO] Will process {len(items)} base IDs after top_k filter.")

    out_dir.mkdir(parents=True, exist_ok=True)

    for i, (base_id, md) in enumerate(items, start=1):
        print(f"\n[INFO] ({i}/{len(items)}) Processing {base_id}")

        # --- Step 1: get LaTeX source via math_paper_parser's own logic ---
        try:
            tex_path, inferred_id = resolve_source_to_tex(base_id)
            print(f"[INFO]   Resolved source -> {tex_path}")
        except Exception as e:
            print(f"[WARN]   Could not resolve source for {base_id}: {e}")
            continue

        # --- Step 2: parse with PaperParser ---
        try:
            parser = PaperParser(paper_id=inferred_id)
            graph = parser.parse_file(tex_path)
        except Exception as e:
            print(f"[WARN]   Failed to parse {base_id}: {e}")
            continue

        # --- Step 3: save JSON ---
        json_path = out_dir / f"{inferred_id}.json"
        json_path.write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")
        print(
            f"[OK]   Saved graph for {base_id} -> {json_path.name} "
            f"({len(graph.objects)} objects, {len(graph.relations)} relations)"
        )

        # --- Step 4: optionally draw network figure ---
        if draw_graphs:
            png_path = out_dir / f"{inferred_id}.png"
            try:
                paper_to_network(json_path, str(png_path))
                print(f"[OK]   Saved network plot -> {png_path.name}")
            except Exception as e:
                print(f"[WARN]   Failed to draw network for {base_id}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Batch-run math_paper_parser on many arXiv papers using the local "
            "arXiv snapshot + extract_arxiv_funcs (NO external metadata JSON)."
        )
    )

    parser.add_argument(
        "--start",
        dest="start_date",
        type=str,
        default=None,
        help="Start date YYYY-MM-DD (submission date).",
    )
    parser.add_argument(
        "--end",
        dest="end_date",
        type=str,
        default=None,
        help="End date YYYY-MM-DD (submission date).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=(
            "If start/end not given: use last N days as [today-N, today]. "
            "Ignored if --start or --end is provided."
        ),
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="ArXiv category, e.g. math.PR, math.DG. If omitted, no category filter.",
    )
    parser.add_argument(
        "--regex-id",
        type=str,
        default=None,
        help='Optional regex filter on base IDs, e.g. "^1901\\.05".',
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Process at most this many base IDs after filtering. Use <=0 for no limit.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="parsed_papers",
        help="Directory to store per-paper JSON (and optionally PNG) outputs.",
    )
    parser.add_argument(
        "--draw-graphs",
        action="store_true",
        help="If set, also draw a network PNG for each parsed paper.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose prints from fetch_arxiv_batch and ID filtering.",
    )

    args = parser.parse_args()
    print(f"[DEBUG] Parsed args: {args}")

    start_date, end_date = compute_date_range(
        args.start_date,
        args.end_date,
        args.days,
    )

    top_k = args.top_k if args.top_k and args.top_k > 0 else None

    run_batch(
        start_date=start_date,
        end_date=end_date,
        category=args.category,
        regex_id=args.regex_id,
        top_k=top_k,
        out_dir=Path(args.out_dir),
        draw_graphs=args.draw_graphs,
        verbose=args.verbose,
    )

    print("[INFO] Done.")


if __name__ == "__main__":
    main()
