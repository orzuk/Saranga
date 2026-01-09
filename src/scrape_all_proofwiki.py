#!/usr/bin/env python3
"""
scrape_all_proofwiki.py

Comprehensive script to scrape ALL mathematical content from ProofWiki.
Organizes output by topic (category).

Usage:
    # Scrape all major topics (default ~20 core math areas)
    python scrape_all_proofwiki.py --mode core --limit 200

    # Scrape specific topics
    python scrape_all_proofwiki.py --topics "Graph Theory" "Linear Algebra" --limit 500

    # Scrape ALL topics (130+ branches) - FULL RUN
    python scrape_all_proofwiki.py --mode all --limit 500

    # List available topics
    python scrape_all_proofwiki.py --list-topics
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from datetime import datetime

# Import the scraper functions
from proofwiki_scraper import (
    scrape_category_recursive,
    scrape_definitions_for_topic,
    get_subcategories,
    TOPIC_KEYWORDS,
    MathItem,
)

# Import config
try:
    from config import PROOFWIKI_DIR, ensure_data_dirs
except ImportError:
    PROOFWIKI_DIR = Path(".")
    def ensure_data_dirs():
        pass

# Core mathematical topics (most important ~20 areas)
CORE_TOPICS = [
    "Algebra",
    "Analysis",
    "Calculus",
    "Category Theory",
    "Combinatorics",
    "Complex Analysis",
    "Differential Equations",
    "Discrete Mathematics",
    "Euclidean Geometry",
    "Functional Analysis",
    "Galois Theory",
    "Graph Theory",
    "Group Theory",
    "Linear Algebra",
    "Logic",
    "Measure Theory",
    "Number Theory",
    "Probability Theory",
    "Real Analysis",
    "Ring Theory",
    "Set Theory",
    "Topology",
]

# Extended topics (all branches from ProofWiki)
EXTENDED_TOPICS = [
    "Abstract Algebra",
    "Algebraic Geometry",
    "Algebraic Number Theory",
    "Algebraic Topology",
    "Analytic Number Theory",
    "Boolean Algebra",
    "Coding Theory",
    "Commutative Algebra",
    "Differential Geometry",
    "Field Theory",
    "Fourier Analysis",
    "Game Theory",
    "Homological Algebra",
    "Homotopy Theory",
    "Information Theory",
    "Knot Theory",
    "Lattice Theory",
    "Lie Theory",
    "Mathematical Logic",
    "Matrix Theory",
    "Metric Spaces",
    "Model Theory",
    "Module Theory",
    "Nonstandard Analysis",
    "Operator Theory",
    "Order Theory",
    "Partition Theory",
    "Point-Set Topology",
    "Proof Theory",
    "Recursion Theory",
    "Representation Theory",
    "Riemannian Geometry",
    "Spectral Theory",
    "Universal Algebra",
]


def get_all_proofwiki_topics() -> list[str]:
    """Fetch all math branch topics from ProofWiki."""
    cats = get_subcategories("Definitions/Branches of Mathematics")
    # Extract topic names from "Definitions/TopicName" format
    topics = []
    for c in cats:
        if c.startswith("Definitions/"):
            topic = c.replace("Definitions/", "")
            topics.append(topic)
    return sorted(topics)


def scrape_topic(topic: str, limit: int = 200, depth: int = 2) -> dict:
    """
    Scrape a single topic: both theorems and definitions.
    Returns a dict with topic metadata and items.
    """
    print(f"\n{'='*60}")
    print(f"SCRAPING: {topic}")
    print(f"{'='*60}")

    all_items = []

    # 1. Scrape theorems from main category
    print(f"\n  [1/2] Scraping theorems from '{topic}'...")
    try:
        theorems = scrape_category_recursive(topic, max_depth=depth, limit=limit)
        all_items.extend(theorems)
        print(f"        Found {len(theorems)} theorems")
    except Exception as e:
        print(f"        Warning: Failed to scrape theorems: {e}")

    # 2. Scrape definitions
    print(f"\n  [2/2] Scraping definitions for '{topic}'...")
    try:
        # Generate keywords from topic name
        topic_keywords = topic.lower().replace(" ", "_").split("_")
        # Add the full topic name as keyword too
        topic_keywords.append(topic.lower())

        # Use existing TOPIC_KEYWORDS if available, else use generated ones
        if topic.replace(" ", "_") in TOPIC_KEYWORDS:
            pass  # Will use predefined keywords
        else:
            # Add to TOPIC_KEYWORDS temporarily
            TOPIC_KEYWORDS[topic.replace(" ", "_")] = topic_keywords

        definitions = scrape_definitions_for_topic(topic.replace(" ", "_"), limit=limit)
        all_items.extend(definitions)
        print(f"        Found {len(definitions)} definitions")
    except Exception as e:
        print(f"        Warning: Failed to scrape definitions: {e}")

    # Deduplicate by page_id
    seen_ids = set()
    unique_items = []
    for item in all_items:
        if item.page_id not in seen_ids:
            seen_ids.add(item.page_id)
            unique_items.append(item)

    print(f"\n  Total unique items for {topic}: {len(unique_items)}")

    return {
        "topic": topic,
        "item_count": len(unique_items),
        "items": [item.to_dict() for item in unique_items],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Scrape all mathematical content from ProofWiki"
    )
    parser.add_argument(
        "--mode",
        choices=["core", "extended", "all"],
        default="core",
        help="Which topics to scrape: core (~20), extended (~50), all (~130)",
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        help="Specific topics to scrape (overrides --mode)",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=10000,
        help="Max items per topic (default: 10000 = practically unlimited)",
    )
    parser.add_argument(
        "--depth",
        "-d",
        type=int,
        default=3,
        help="Max subcategory depth (default: 3)",
    )
    parser.add_argument(
        "--out-dir",
        "-o",
        default=None,
        help="Output directory (default: DATA_DIR/proofwiki/by_topic/)",
    )
    parser.add_argument(
        "--list-topics",
        action="store_true",
        help="List all available topics and exit",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help="Also create a combined JSON with all topics",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-scrape topics even if output file exists (default: skip existing)",
    )

    args = parser.parse_args()

    # List topics mode
    if args.list_topics:
        print("=== CORE TOPICS (--mode core) ===")
        for t in CORE_TOPICS:
            print(f"  {t}")

        print("\n=== EXTENDED TOPICS (--mode extended adds these) ===")
        for t in EXTENDED_TOPICS:
            print(f"  {t}")

        print("\n=== ALL PROOFWIKI TOPICS (--mode all) ===")
        all_topics = get_all_proofwiki_topics()
        for t in all_topics:
            print(f"  {t}")
        print(f"\nTotal: {len(all_topics)} topics")
        return

    # Determine which topics to scrape
    if args.topics:
        topics = args.topics
    elif args.mode == "core":
        topics = CORE_TOPICS
    elif args.mode == "extended":
        topics = CORE_TOPICS + EXTENDED_TOPICS
    else:  # all
        topics = get_all_proofwiki_topics()

    # Output directory
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = PROOFWIKI_DIR / "by_topic"

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"ProofWiki Comprehensive Scraper")
    print(f"================================")
    print(f"Topics to scrape: {len(topics)}")
    print(f"Limit per topic: {args.limit}")
    print(f"Output directory: {out_dir}")
    print(f"Start time: {datetime.now().isoformat()}")

    # Scrape each topic
    all_results = []
    total_items = 0
    skipped = 0

    for i, topic in enumerate(topics, 1):
        safe_name = topic.lower().replace(" ", "_").replace("/", "_")
        topic_file = out_dir / f"{safe_name}.json"

        # Skip if already exists (incremental mode)
        if topic_file.exists() and not args.force:
            print(f"\n[{i}/{len(topics)}] SKIP {topic} (already exists: {topic_file.name})")
            # Load existing data for summary
            try:
                existing = json.loads(topic_file.read_text())
                all_results.append({
                    "topic": topic,
                    "item_count": existing.get("metadata", {}).get("item_count", len(existing.get("items", []))),
                    "items": existing.get("items", []),
                })
                total_items += all_results[-1]["item_count"]
            except:
                pass
            skipped += 1
            continue

        print(f"\n[{i}/{len(topics)}] Processing {topic}...")

        try:
            result = scrape_topic(topic, limit=args.limit, depth=args.depth)
            all_results.append(result)
            total_items += result["item_count"]

            # Save individual topic file
            output = {
                "schema": "authomathics.proofwiki_topic.v1",
                "metadata": {
                    "topic": topic,
                    "scraped_at": datetime.now().isoformat(),
                    "item_count": result["item_count"],
                },
                "items": result["items"],
            }

            topic_file.write_text(
                json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  Saved to: {topic_file}")

            # Be nice to ProofWiki servers
            time.sleep(1)

        except Exception as e:
            print(f"  ERROR scraping {topic}: {e}")
            continue

    # Summary
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Topics requested: {len(topics)}")
    print(f"Topics skipped (already done): {skipped}")
    print(f"Topics scraped this run: {len(topics) - skipped}")
    print(f"Total items (all topics): {total_items}")
    print(f"Output directory: {out_dir}")

    # Create combined file if requested
    if args.combined:
        combined_file = out_dir / "_combined_all_topics.json"
        combined_output = {
            "schema": "authomathics.proofwiki_combined.v1",
            "metadata": {
                "scraped_at": datetime.now().isoformat(),
                "topics_count": len(all_results),
                "total_items": total_items,
                "topics": [r["topic"] for r in all_results],
            },
            "by_topic": {r["topic"]: r["items"] for r in all_results},
        }
        combined_file.write_text(
            json.dumps(combined_output, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Combined file: {combined_file}")

    # Save summary
    summary_file = out_dir / "_scrape_summary.json"
    summary = {
        "scraped_at": datetime.now().isoformat(),
        "mode": args.mode,
        "topics_requested": len(topics),
        "topics_scraped": len(all_results),
        "total_items": total_items,
        "per_topic": {r["topic"]: r["item_count"] for r in all_results},
    }
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary: {summary_file}")


if __name__ == "__main__":
    main()
