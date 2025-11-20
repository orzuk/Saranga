#!/usr/bin/env python
"""
Batch runner for math_paper_parser on many arXiv papers from a metadata JSON.

Example:

    python run_parse_papers.py output/arxiv_metadata.json \
        --category math.PR \
        --days 30 \
        --top-k 20 \
        --out-dir parsed_math_pr_30d \
        --draw-graphs
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from math_paper_parser import (
    PaperParser,
    resolve_source_to_tex,
    paper_to_network,
)

# --------------------------- helpers ---------------------------------

DATE_KEYS = ["published", "submitted", "updated", "update_date", "date"]


def parse_date_from_metadata(paper: Dict[str, Any]) -> Optional[datetime]:
    """Extract a datetime from common keys in a metadata record, if possible."""
    for key in DATE_KEYS:
        val = paper.get(key)
        if not val:
            continue
        s = str(val)[:10]  # 'YYYY-MM-DD' part
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            continue
    return None


def matches_category(paper: Dict[str, Any], categories: List[str]) -> bool:
    """
    Return True if the paper matches at least one of the requested categories.

    We treat 'categories' in metadata as either:
      - space-separated string like 'math.PR math.DS'
      - list of strings
    """
    if not categories:
        return True  # no filter

    meta_cats = paper.get("categories") or paper.get("category")
    if meta_cats is None:
        return False

    if isinstance(meta_cats, str):
        paper_cats = meta_cats.split()
    elif isinstance(meta_cats, list):
        paper_cats = meta_cats
    else:
        paper_cats = [str(meta_cats)]

    for c in paper_cats:
        for wanted in categories:
            if c == wanted or c.startswith(wanted):
                return True
    return False


def filter_metadata(
    metadata: List[Dict[str, Any]],
    categories: List[str],
    days: Optional[int],
    top_k: Optional[int],
) -> List[Dict[str, Any]]:
    """Filter metadata by category and recency (days), then take top_k."""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days) if days is not None else None

    filtered: List[Dict[str, Any]] = []
    for paper in metadata:
        if not matches_category(paper, categories):
            continue

        if cutoff is not None:
            d = parse_date_from_metadata(paper)
            if d is None or d < cutoff:
                continue

        filtered.append(paper)

    # deterministic order: sort by date desc, then id
    def key_fn(p: Dict[str, Any]):
        d = parse_date_from_metadata(p)
        return (d or datetime(1970, 1, 1), p.get("id", ""))

    filtered.sort(key=key_fn, reverse=True)

    if top_k is not None and top_k > 0 and len(filtered) > top_k:
        filtered = filtered[:top_k]

    return filtered


# --------------------------- main batch logic -------------------------


def run_batch(
    metadata_file: Path,
    out_dir: Path,
    categories: List[str],
    days: Optional[int],
    top_k: Optional[int],
    draw_graphs: bool,
) -> None:
    print(f"[INFO] Loading metadata from {metadata_file}")
    raw = metadata_file.read_text(encoding="utf-8")
    try:
        metadata = json.loads(raw)
    except Exception as e:
        print(f"[ERROR] Could not parse JSON from {metadata_file}: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(metadata, list):
        print(
            f"[ERROR] Metadata JSON is not a list (got {type(metadata)}). "
            "Expected a list of paper dicts.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[INFO] Loaded {len(metadata)} metadata records.")

    selected = filter_metadata(metadata, categories, days, top_k)
    print(f"[INFO] Selected {len(selected)} papers after filtering "
          f"(categories={categories or 'ANY'}, days={days}, top_k={top_k}).")

    if not selected:
        print("[WARN] No papers matched the filters. Nothing to do.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    for i, paper in enumerate(selected, start=1):
        arxiv_id = paper.get("id")
        if not arxiv_id:
            print(f"[WARN] Skipping metadata entry without 'id': {paper}")
            continue

        print(f"\n[INFO] ({i}/{len(selected)}) Processing {arxiv_id}")

        try:
            tex_path, inferred_id = resolve_source_to_tex(arxiv_id)
            print(f"[INFO]   Resolved source -> {tex_path}")
        except Exception as e:
            print(f"[WARN]   Could not resolve source for {arxiv_id}: {e}")
            continue

        try:
            parser = PaperParser(paper_id=inferred_id)
            graph = parser.parse_file(tex_path)
        except Exception as e:
            print(f"[WARN]   Failed to parse {arxiv_id}: {e}")
            continue

        # Save JSON
        json_path = out_dir / f"{inferred_id}.json"
        json_path.write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")
        print(
            f"[OK]   Saved graph for {arxiv_id} -> {json_path.name} "
            f"({len(graph.objects)} objects, {len(graph.relations)} relations)"
        )

        # Optionally draw network figure
        if draw_graphs:
            png_path = out_dir / f"{inferred_id}.png"
            try:
                paper_to_network(json_path, str(png_path))
                print(f"[OK]   Saved network plot -> {png_path.name}")
            except Exception as e:
                print(f"[WARN]   Failed to draw network for {arxiv_id}: {e}")


def main():
    print("[DEBUG] run_parse_papers.py main() starting")
    parser = argparse.ArgumentParser(
        description="Batch-run math_paper_parser on many arXiv papers from a metadata JSON."
    )
    parser.add_argument(
        "metadata_file",
        type=str,
        help="Path to arXiv metadata JSON file (list of dicts with at least 'id').",
    )
    parser.add_argument(
        "--category",
        "-c",
        action="append",
        default=[],
        help=(
            "Filter by arXiv category (e.g. math.PR). "
            "Can be specified multiple times. If omitted, no category filter is applied."
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only include papers from the last N days (based on metadata dates).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Process at most this many papers after filtering. Use <=0 for no limit.",
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

    args = parser.parse_args()
    print(f"[DEBUG] Parsed args: {args}")

    metadata_path = Path(args.metadata_file)
    if not metadata_path.exists():
        print(f"[ERROR] Metadata file not found: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    top_k = args.top_k if args.top_k and args.top_k > 0 else None

    run_batch(
        metadata_file=metadata_path,
        out_dir=Path(args.out_dir),
        categories=args.category,
        days=args.days,
        top_k=top_k,
        draw_graphs=args.draw_graphs,
    )
    print("[INFO] Done.")


if __name__ == "__main__":
    main()
