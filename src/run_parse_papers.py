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
      --start 2019-01-01 \
      --end   2019-01-31 \
      --category math.PR \
      --top-k 20 \
      --out-dir parsed_math_pr_2019_01 \
      --draw-graphs \
      --verbose
"""

import argparse
import json
import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from config import FULL_PAPERS_DIR

# Import from your parser module
from math_paper_parser import PaperParser, paper_to_network

# Your arXiv infra
from extract_arxiv_funcs import (
    fetch_arxiv_batch,
    resolve_source_to_tex_local_first,
)


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

    # ------------------------------------------------------------
    # 1. FETCH METADATA ONCE (no source downloading)
    # ------------------------------------------------------------
    data = fetch_arxiv_batch(
        regex_id=regex_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        formats="metadata",
        output_dir=None,
        verbose=verbose,
    )

    if verbose:
        print(f"[DEBUG] fetch_arxiv_batch returned {len(data)} versioned IDs")

    if not data:
        print("[WARN] No papers matched the filters. Nothing to do.")
        return

    # ------------------------------------------------------------
    # 2. COLLAPSE VERSIONED → BASE IDs (latest metadata kept)
    # ------------------------------------------------------------
    base_to_meta: Dict[str, Dict[str, Any]] = {}
    for vid, entry in data.items():
        base_id = vid.split("v")[0]
        md = entry.get("metadata", entry)
        base_to_meta[base_id] = md

    print(f"[INFO] Collapsed to {len(base_to_meta)} unique base IDs.")

    # ------------------------------------------------------------
    # 3. SORT BY DATE (published / created)
    # ------------------------------------------------------------
    def extract_date(md: dict) -> datetime:
        for key in ("published", "created"):
            if md.get(key):
                try:
                    return datetime.strptime(str(md[key])[:10], "%Y-%m-%d")
                except Exception:
                    pass
        return datetime(1970, 1, 1)

    items = list(base_to_meta.items())
    items.sort(key=lambda kv: extract_date(kv[1]), reverse=True)

    if top_k and top_k > 0:
        items = items[:top_k]

    print(f"[INFO] Will process {len(items)} base IDs after top_k filter.")

    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # 4. MAIN LOOP: resolve tex → parse → save JSON/PNG
    # ------------------------------------------------------------
    for i, (base_id, md) in enumerate(items, start=1):
        print(f"\n[INFO] ({i}/{len(items)}) Processing {base_id}")

        # ---------- STEP 1: GET LOCAL OR FETCHED TEX ----------
        try:
            tex_path, versioned_id = resolve_source_to_tex_local_first(
                base_id=base_id,
                meta=md,
                full_papers_dir=out_dir,
                verbose=verbose,
            )
            print(f"[INFO]   Resolved source -> {tex_path}")
        except Exception as e:
            status = f"FETCH_ERROR: {e}"
            print(f"[WARN]   Failed to fetch/resolve source for {base_id}: {e}")
            # log fetch failure and continue to next paper
            with open(out_dir / "status_log.csv", "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([base_id, "", status])
            continue

        # ---------- STEP 2: PARSE ----------
        try:
            parser = PaperParser(paper_id=versioned_id)
            graph = parser.parse_file(tex_path)
            status = "OK"
        except Exception as e:
            status = f"PARSE_ERROR: {e}"
            print(f"[WARN]   Failed to parse {base_id}: {e}")
            with open(out_dir / "status_log.csv", "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([base_id, versioned_id, status])
            continue

        # If we got here, both fetch + parse succeeded, log success
        with open(out_dir / "status_log.csv", "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([base_id, versioned_id, status])

        # ---------- STEP 3: DETERMINE OUTPUT DIR (same YYYY/MM/DD as metadata) ----------
        pub_raw = md.get("published") or md.get("created")
        if pub_raw:
            date_str = str(pub_raw)[:10]
            try:
                year, month, day = date_str.split("-")
            except Exception:
                year, month, day = ("unknown", "unknown", "unknown")
        else:
            year, month, day = ("unknown", "unknown", "unknown")

        base_day_dir = out_dir / year / month / day

        # ---------- STEP 4: WRITE JSON ----------
        json_dir = base_day_dir / "json"
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / f"{versioned_id}.json"

        json_path.write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")
        print(f"[OK]   Saved graph for {base_id} -> {json_path}")

        # ---------- STEP 5: DRAW PNG ----------
        if draw_graphs:
            png_dir = base_day_dir / "png"
            png_dir.mkdir(parents=True, exist_ok=True)
            out_png = png_dir / f"{versioned_id}.png"

            try:
                paper_to_network(
                    paper=graph,
                    out_png=str(out_png),
                    node_label_attr="label",  # or "id" / "name"
                    include_kinds=[
                        "theorem",
                        "lemma",
                        "proposition",
                        "corollary",
                        "definition",
                        "proof",
                        "proposition",
                        "conjecture",
                        "claim",
                        "problem",
                    ],
                    figsize=(16, 10),
                    include_relation_types=None,
                )
                print(f"[OK]   Saved PNG for {base_id} -> {out_png}")
            except Exception as e:
                print(f"[WARN] Could not draw network for {base_id}: {e}")

    print("[INFO] Done.")


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
        default=FULL_PAPERS_DIR,
        help=(
            "Root directory for outputs. "
            "Defaults to FULL_PAPERS_DIR from config.py."
        ),
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
