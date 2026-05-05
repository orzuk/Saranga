#!/usr/bin/env python3
"""Audit the NaturalProofs foundation index for duplicates and near-duplicates.

Checks:
1. Exact duplicate titles (within and across sources)
2. Near-duplicates after normalization (possessives, articles, theorem/lemma suffixes)
3. Ambiguous short stems (e.g., "Stein" matching both "Stein's Method" and "Stein's Unbiased Risk Estimator")
4. Titles that are too generic or too specific for useful matching

Usage:
    python scripts/audit_foundation_index.py [--data-dir /path/to/data]
"""
import json
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict, Counter


def normalize_title(title):
    """Aggressive normalization: lowercase, strip articles, possessives, type words."""
    t = title.strip().lower()
    # Strip leading articles
    for prefix in ("the ", "a ", "an "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    # Strip possessives
    t = re.sub(r"['']s\b", "", t)
    # Strip type suffixes/prefixes
    for word in ("theorem", "lemma", "corollary", "proposition", "definition",
                 "inequality", "bound", "formula", "algorithm", "conjecture",
                 "principle", "rule", "law", "criterion", "condition"):
        t = re.sub(r'\b' + word + r'\b', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def extract_name_stem(title):
    """Extract the core proper-name part of a theorem title.

    'Markov\'s Inequality' -> 'markov'
    'Cauchy-Schwarz Inequality' -> 'cauchy-schwarz'
    'Central Limit Theorem' -> 'central limit'
    """
    t = title.strip().lower()
    t = re.sub(r"['']s\b", "", t)
    # Remove type words
    for word in ("theorem", "lemma", "corollary", "proposition", "definition",
                 "inequality", "bound", "formula", "algorithm", "conjecture",
                 "principle", "rule", "law", "criterion", "condition",
                 "property", "identity", "equation", "method", "test",
                 "approximation", "transform", "series", "sequence",
                 "distribution", "model", "process", "function", "operator"):
        t = re.sub(r'\b' + word + r'\b', '', t)
    for prefix in ("the ", "a ", "an "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def load_all_items(data_dir):
    """Load all items from NaturalProofs JSONs."""
    np_dir = Path(data_dir) / "naturalproofs" / "raw"
    items = []

    for fp in sorted(np_dir.glob("naturalproofs_*.json")):
        with open(fp) as f:
            data = json.load(f)

        ds = data if isinstance(data, list) else data.get("dataset", data.get("theorems", []))
        source = fp.stem.replace("naturalproofs_", "")

        file_items = []
        if isinstance(ds, list):
            file_items = ds
        elif isinstance(ds, dict):
            for cat_name, cat_items in ds.items():
                if isinstance(cat_items, list):
                    file_items.extend(cat_items)

        for item in file_items:
            if isinstance(item, dict):
                title = item.get("title", "") or item.get("name", "")
                if title:
                    items.append({
                        "title": title,
                        "type": item.get("type", ""),
                        "id": item.get("id", ""),
                        "source": source,
                        "categories": item.get("categories", []),
                    })

        print(f"  {source}: {len(file_items)} items, {sum(1 for i in file_items if isinstance(i, dict) and (i.get('title') or i.get('name')))} with titles")

    return items


def audit(items):
    """Run all audit checks."""
    results = {}

    # ── 1. Exact duplicates ──
    print("\n" + "="*70)
    print("1. EXACT DUPLICATE TITLES")
    print("="*70)
    title_sources = defaultdict(list)
    for item in items:
        title_sources[item["title"]].append(item["source"])

    exact_dups = {t: srcs for t, srcs in title_sources.items() if len(srcs) > 1}
    print(f"  {len(exact_dups)} titles appear more than once")

    # Cross-source vs within-source
    cross_source = {t: srcs for t, srcs in exact_dups.items() if len(set(srcs)) > 1}
    within_source = {t: srcs for t, srcs in exact_dups.items() if len(set(srcs)) == 1}
    print(f"  Cross-source duplicates: {len(cross_source)}")
    print(f"  Within-source duplicates: {len(within_source)}")

    if cross_source:
        print("\n  Top 30 cross-source duplicates:")
        for t, srcs in sorted(cross_source.items(), key=lambda x: -len(x[1]))[:30]:
            src_counts = Counter(srcs)
            src_str = ", ".join(f"{s}×{c}" for s, c in src_counts.items())
            print(f"    [{src_str}] \"{t}\"")

    results["exact_dups"] = len(exact_dups)
    results["cross_source_dups"] = len(cross_source)

    # ── 2. Near-duplicates after normalization ──
    print("\n" + "="*70)
    print("2. NEAR-DUPLICATES (after normalization)")
    print("="*70)

    norm_groups = defaultdict(list)
    for item in items:
        norm = normalize_title(item["title"])
        if norm:  # skip empty after normalization
            norm_groups[norm].append(item["title"])

    near_dups = {norm: titles for norm, titles in norm_groups.items()
                 if len(set(titles)) > 1}
    print(f"  {len(near_dups)} normalized forms map to multiple distinct titles")

    print("\n  Examples (first 40):")
    for norm, titles in sorted(near_dups.items(), key=lambda x: -len(x[1]))[:40]:
        unique = sorted(set(titles))
        print(f"    \"{norm}\" <- {unique}")

    results["near_dups"] = len(near_dups)

    # ── 3. Ambiguous stems ──
    print("\n" + "="*70)
    print("3. AMBIGUOUS NAME STEMS (same name, different results)")
    print("="*70)

    stem_groups = defaultdict(set)
    for item in items:
        stem = extract_name_stem(item["title"])
        if stem and len(stem) >= 3:
            stem_groups[stem].add(item["title"])

    ambiguous = {stem: titles for stem, titles in stem_groups.items()
                 if len(titles) > 1}

    # Sort by number of distinct titles
    print(f"  {len(ambiguous)} stems map to multiple titles")
    print(f"\n  Most ambiguous stems (top 50):")
    for stem, titles in sorted(ambiguous.items(), key=lambda x: -len(x[1]))[:50]:
        print(f"    \"{stem}\" ({len(titles)} titles):")
        for t in sorted(titles)[:5]:
            print(f"      - {t}")
        if len(titles) > 5:
            print(f"      ... and {len(titles)-5} more")

    results["ambiguous_stems"] = len(ambiguous)

    # ── 4. Title quality issues ──
    print("\n" + "="*70)
    print("4. TITLE QUALITY ISSUES")
    print("="*70)

    # Too short (likely generic)
    short = [item for item in items if len(item["title"]) < 10]
    print(f"\n  Very short titles (<10 chars): {len(short)}")
    for item in sorted(short, key=lambda x: len(x["title"]))[:20]:
        print(f"    \"{item['title']}\" [{item['source']}, {item['type']}]")

    # Too long (likely too specific for matching)
    long_titles = [item for item in items if len(item["title"]) > 80]
    print(f"\n  Very long titles (>80 chars): {len(long_titles)}")
    for item in sorted(long_titles, key=lambda x: -len(x["title"]))[:20]:
        print(f"    \"{item['title'][:100]}...\" [{item['source']}]")

    # Numbered (e.g., "Theorem 3.2.1")
    numbered = [item for item in items if re.search(r'\b\d+\.\d+', item["title"])]
    print(f"\n  Titles with version/section numbers (X.Y): {len(numbered)}")
    for item in numbered[:15]:
        print(f"    \"{item['title']}\" [{item['source']}]")

    # Generic (just a type word like "Definition" or "Theorem")
    generic_pat = re.compile(r'^(theorem|definition|lemma|corollary|proposition|remark|example|exercise|proof|notation)\s*\d*$', re.I)
    generic = [item for item in items if generic_pat.match(item["title"].strip())]
    print(f"\n  Generic titles (just type + optional number): {len(generic)}")
    for item in generic[:15]:
        print(f"    \"{item['title']}\" [{item['source']}, id={item['id']}]")

    results["short_titles"] = len(short)
    results["long_titles"] = len(long_titles)
    results["numbered_titles"] = len(numbered)
    results["generic_titles"] = len(generic)

    # ── 5. Stein problem specifically ──
    print("\n" + "="*70)
    print("5. EXAMPLE: 'stein' entries (the user's concern)")
    print("="*70)
    stein = [item for item in items if "stein" in item["title"].lower()]
    print(f"  {len(stein)} entries containing 'stein':")
    for item in sorted(stein, key=lambda x: x["title"]):
        print(f"    \"{item['title']}\" [{item['source']}, {item['type']}]")

    # ── Summary ──
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Total items with titles: {len(items)}")
    for k, v in results.items():
        print(f"  {k}: {v}")

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None,
                        help="Path to Authomathics data dir (auto-detected if omitted)")
    args = parser.parse_args()

    if args.data_dir is None:
        # Auto-detect
        candidates = [
            Path("/<cluster>/<user>/projects/Authomathics"),
            Path("/mnt/c/Datasets/Authomathics_data"),
            Path.home() / "Datasets" / "Authomathics_data",
        ]
        for c in candidates:
            if (c / "naturalproofs" / "raw").exists():
                args.data_dir = str(c)
                break
        if args.data_dir is None:
            print("ERROR: Could not find NaturalProofs data. Use --data-dir.")
            sys.exit(1)

    print(f"Data dir: {args.data_dir}")
    print("Loading items...")
    items = load_all_items(args.data_dir)
    print(f"Loaded {len(items)} items total")

    audit(items)


if __name__ == "__main__":
    main()
