#!/usr/bin/env python3
"""Sanity check: what drives the high % link in the cross-category table?

For each category, reports:
  1. % papers with ANY foundation edge (current % link)
  2. % papers with at least one SPECIFIC (non-generic) edge
  3. Top matched terms by paper count (with generic flag)
  4. Distribution of foundation edges per paper

Usage (on cluster):
    python scripts/sanity_check_links.py \
        --base-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k \
        --categories math.CO math.GR cs.LG math-ph

    # Or check all categories:
    python scripts/sanity_check_links.py \
        --base-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ALL_CATEGORIES = [
    "math.LO", "math.AT", "math.CO", "math.NT", "math.AG",
    "math.GR", "math.RT", "math.DG", "math.AP", "math.CA",
    "math.FA", "math.PR", "math-ph",
    "cs.CC", "cs.DS", "cs.IT", "cs.LG",
    "math.OC", "math.NA", "stat.TH",
]


def cat_to_dirname(cat: str) -> str:
    return cat.replace(".", "_").replace("-", "_")


def analyze_category(cat_dir: Path, cat_name: str, sample_limit: int = 0):
    """Analyze foundation links for one category."""
    json_dir = cat_dir / "json"
    if not json_dir.exists():
        print(f"  {cat_name}: no json/ directory found")
        return

    json_files = sorted(json_dir.glob("*.json"))
    if sample_limit > 0:
        json_files = json_files[:sample_limit]

    n_papers = 0
    n_any_link = 0
    n_specific_link = 0  # at least one non-generic edge
    term_paper_count = Counter()       # term -> how many papers
    generic_terms = set()
    edges_per_paper = []

    for jp in json_files:
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        n_papers += 1
        foundation_edges = [
            e for e in data.get("edges", [])
            if e.get("type") in ("grounded_to", "mentions_concept")
        ]
        n_found = len(foundation_edges)
        edges_per_paper.append(n_found)

        if n_found > 0:
            n_any_link += 1

        has_specific = False
        seen_terms = set()
        for e in foundation_edges:
            is_generic = e.get("generic", False)
            # Derive term name from source (format: "FG:Name" or just "Name")
            term = e.get("source", "").replace("FG:", "")
            note = e.get("note", "")
            if is_generic:
                generic_terms.add(term)
            else:
                has_specific = True

            if term not in seen_terms:
                term_paper_count[term] += 1
                seen_terms.add(term)

        if has_specific:
            n_specific_link += 1

    if n_papers == 0:
        print(f"  {cat_name}: no papers found")
        return

    pct_any = n_any_link / n_papers * 100
    pct_specific = n_specific_link / n_papers * 100
    avg_edges = sum(edges_per_paper) / n_papers
    median_edges = sorted(edges_per_paper)[n_papers // 2]
    zero_count = edges_per_paper.count(0)

    print(f"\n{'='*60}")
    print(f"  {cat_name}  ({n_papers} papers)")
    print(f"{'='*60}")
    print(f"  % link (any edge):          {pct_any:.1f}%  ({n_any_link}/{n_papers})")
    print(f"  % link (specific only):     {pct_specific:.1f}%  ({n_specific_link}/{n_papers})")
    print(f"  Papers with 0 edges:        {zero_count}")
    print(f"  Avg edges/paper:            {avg_edges:.1f}")
    print(f"  Median edges/paper:         {median_edges}")

    # Top terms
    print(f"\n  Top 20 matched terms (by # papers):")
    for term, count in term_paper_count.most_common(20):
        pct = count / n_papers * 100
        flag = " [GENERIC]" if term in generic_terms else ""
        print(f"    {count:>5} papers ({pct:5.1f}%): {term}{flag}")

    # Edge count distribution
    buckets = {"0": 0, "1-5": 0, "6-20": 0, "21-50": 0, "51+": 0}
    for e in edges_per_paper:
        if e == 0:
            buckets["0"] += 1
        elif e <= 5:
            buckets["1-5"] += 1
        elif e <= 20:
            buckets["6-20"] += 1
        elif e <= 50:
            buckets["21-50"] += 1
        else:
            buckets["51+"] += 1
    print(f"\n  Edge count distribution:")
    for label, count in buckets.items():
        bar = "#" * (count * 40 // n_papers)
        print(f"    {label:>5}: {count:>5} ({count/n_papers*100:5.1f}%) {bar}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-dir", required=True,
                        help="Base directory containing category subdirectories")
    parser.add_argument("--categories", nargs="*", default=None,
                        help="Categories to check (default: all 20)")
    parser.add_argument("--sample", type=int, default=0,
                        help="Limit to first N papers per category (0 = all)")
    args = parser.parse_args()

    base = Path(args.base_dir)
    cats = args.categories or ALL_CATEGORIES

    for cat in cats:
        dirname = cat_to_dirname(cat)
        cat_dir = base / dirname
        if not cat_dir.exists():
            print(f"  {cat}: directory {cat_dir} not found, skipping")
            continue
        analyze_category(cat_dir, cat, sample_limit=args.sample)


if __name__ == "__main__":
    main()
