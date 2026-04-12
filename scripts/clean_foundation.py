#!/usr/bin/env python3
"""Clean and deduplicate the NaturalProofs foundation index.

Produces a canonical foundation JSON from raw NaturalProofs files:
1. Drops Stacks Project entries (tag-based titles, useless for keyword matching)
2. Drops sub-pages (/Proof 1, /Proof 2, /Corollary, /Lemma sub-entries)
3. Drops junk (numeric titles, meta-definitions, very long titles)
4. Merges exact cross-source duplicates
5. Detects near-duplicates via content comparison

Output: clean_foundation.json with deduplicated entries ready for indexing.

Usage:
    python scripts/clean_foundation.py [--data-dir /path/to/data] [--verbose]
"""
import json
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher


def _normalize_key(title):
    """Normalize title for dedup comparison."""
    t = title.strip().lower()
    for prefix in ("the ", "a ", "an ", "definition:", "definition: "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    t = re.sub(r"['']s\b", "", t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _normalize_latex(contents_list):
    """Normalize LaTeX content list into a single comparable string."""
    text = " ".join(str(c) for c in contents_list if c)
    # Strip common LaTeX noise
    text = re.sub(r'\\(displaystyle|text|mathrm|mathbb|mathcal|operatorname)\b', '', text)
    text = re.sub(r'[{}\\$:,.]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def _content_similarity(contents_a, contents_b):
    """Compute similarity between two entries' contents (0-1)."""
    text_a = _normalize_latex(contents_a)
    text_b = _normalize_latex(contents_b)
    if not text_a or not text_b:
        return 0.0
    # For short texts, use SequenceMatcher; for long ones, use Jaccard on words
    if len(text_a) < 500 and len(text_b) < 500:
        return SequenceMatcher(None, text_a, text_b).ratio()
    else:
        words_a = set(text_a.split())
        words_b = set(text_b.split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)


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
                    item["_source"] = source
                    items.append(item)

        print(f"  Loaded {source}: {len(file_items)} items")

    return items


def filter_items(items, verbose=False):
    """Apply filtering rules. Returns (kept, dropped_with_reasons)."""
    kept = []
    dropped = defaultdict(list)

    for item in items:
        title = item.get("title", "") or item.get("name", "")
        source = item.get("_source", "")

        # Rule 1: Drop Stacks Project (tag-based titles, not human-readable)
        if source == "stacks":
            dropped["stacks_tag_title"].append(title)
            continue

        # Rule 2: Drop sub-pages (/Proof N, /Corollary, /Lemma sub-entries)
        if re.search(r'/(?:Proof|Corollary|Lemma|Also presented as|Historical Note|'
                     r'Linguistic Note|Mistake|Warning|Also known as|Also see)\b',
                     title):
            dropped["subpage"].append(title)
            continue

        # Rule 3: Drop numeric/junk titles
        stripped = title.strip()
        if len(stripped) < 5:
            dropped["too_short"].append(title)
            continue
        if re.match(r'^\d+$', stripped):
            dropped["numeric"].append(title)
            continue

        # Rule 4: Drop meta-definitions about math notation itself
        meta_patterns = [
            r'^Definition:(Theorem|Lemma|Corollary|Definition|Proposition|Formula|'
            r'Algorithm|Inequality|Principle|Bound|Proof|Conjecture|Axiom|Postulate'
            r')(/|$)',
        ]
        is_meta = False
        for pat in meta_patterns:
            if re.match(pat, title):
                is_meta = True
                break
        if is_meta:
            dropped["meta_definition"].append(title)
            continue

        # Rule 5: Drop very long titles (>100 chars) — too specific for matching
        if len(title) > 100:
            dropped["too_long"].append(title)
            continue

        kept.append(item)

    if verbose:
        print(f"\n  Filtering results:")
        print(f"    Kept: {len(kept)}")
        for reason, titles in sorted(dropped.items(), key=lambda x: -len(x[1])):
            print(f"    Dropped ({reason}): {len(titles)}")
            for t in titles[:3]:
                print(f"      e.g. \"{t[:80]}\"")

    return kept, dropped


def deduplicate(items, verbose=False):
    """Merge entries with same normalized key, using content comparison for ambiguous cases."""
    # Group by normalized key
    groups = defaultdict(list)
    for item in items:
        title = item.get("title", "") or item.get("name", "")
        key = _normalize_key(title)
        if key:
            groups[key].append(item)

    final = []
    merge_log = []
    ambiguous_log = []

    for key, group in sorted(groups.items()):
        if len(group) == 1:
            final.append(group[0])
            continue

        # Multiple entries with same normalized key
        unique_titles = list(set(
            (item.get("title", "") or item.get("name", "")) for item in group
        ))

        if len(unique_titles) == 1:
            # Exact same title from different sources — just keep first
            merge_log.append((key, unique_titles, "exact_title"))
            final.append(group[0])
            continue

        # Check if titles differ only by trivial prefixes ("The ", "Definition:")
        # or whitespace — if so, they're the same object regardless of content
        def _core_title(t):
            t = t.strip().lower()
            for pfx in ("the ", "a ", "an ", "definition:", "definition: "):
                if t.startswith(pfx):
                    t = t[len(pfx):]
            return re.sub(r'\s+', ' ', t).strip()

        core_titles = set(_core_title(t) for t in unique_titles)
        if len(core_titles) == 1:
            # Same core title — trivial variant, merge
            best = max(group, key=lambda x: len(str(x.get("contents", []))))
            merge_log.append((key, unique_titles, "trivial_variant"))
            final.append(best)
            continue

        # Different core titles — check content similarity
        contents_list = [item.get("contents", []) for item in group]
        all_similar = True
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                sim = _content_similarity(contents_list[i], contents_list[j])
                if sim < 0.5:
                    all_similar = False
                    break
            if not all_similar:
                break

        if all_similar:
            # Same mathematical content — merge, keep the one with richest content
            best = max(group, key=lambda x: len(str(x.get("contents", []))))
            merge_log.append((key, unique_titles, "content_similar"))
            final.append(best)
        else:
            # Genuinely different results — keep all
            ambiguous_log.append((key, unique_titles,
                                  [(item.get("title", ""), str(item.get("contents", []))[:100])
                                   for item in group]))
            final.extend(group)

    if verbose:
        print(f"\n  Deduplication results:")
        print(f"    Input: {len(items)} entries in {len(groups)} normalized groups")
        print(f"    Output: {len(final)} entries")
        print(f"    Merged: {len(merge_log)} groups")
        if merge_log:
            print(f"    Merged examples:")
            for key, titles, reason in merge_log[:20]:
                print(f"      \"{key}\": {titles} ({reason})")
        print(f"    Ambiguous (kept separate): {len(ambiguous_log)} groups")
        if ambiguous_log:
            print(f"    Ambiguous examples:")
            for key, titles, previews in ambiguous_log[:20]:
                print(f"      \"{key}\": {titles}")
                for title, preview in previews:
                    print(f"        {title}: {preview[:80]}...")

    return final, merge_log, ambiguous_log


def build_clean_index(items):
    """Build the final clean index dict: normalized_key -> entry."""
    index = {}
    for item in items:
        title = item.get("title", "") or item.get("name", "")
        key = _normalize_key(title)
        if not key or len(key) < 4:
            continue

        # Skip single-word keys after normalization (too ambiguous)
        words = [w for w in key.split() if len(w) > 2]
        if len(words) < 2:
            continue

        if key not in index:
            index[key] = {
                "name": title,
                "id": item.get("id", ""),
                "type": item.get("type", ""),
                "source": item.get("_source", ""),
                "field": (item.get("categories", [""])[0]
                          if item.get("categories") else ""),
                "categories": item.get("categories", []),
                "contents_preview": " ".join(
                    str(c) for c in item.get("contents", [])
                )[:200],
            }
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--output", default=None,
                        help="Output path (default: <data-dir>/naturalproofs/clean_foundation.json)")
    args = parser.parse_args()

    if args.data_dir is None:
        candidates = [
            Path("/sci/labs/orzuk/orzuk/projects/Authomathics"),
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

    # Step 1: Load
    print("\n1. Loading raw items...")
    items = load_all_items(args.data_dir)
    print(f"   Total: {len(items)} items")

    # Step 2: Filter
    print("\n2. Filtering...")
    kept, dropped = filter_items(items, verbose=args.verbose)
    print(f"   Kept: {len(kept)}, Dropped: {sum(len(v) for v in dropped.values())}")
    for reason, titles in sorted(dropped.items(), key=lambda x: -len(x[1])):
        print(f"     {reason}: {len(titles)}")

    # Step 3: Deduplicate
    print("\n3. Deduplicating...")
    deduped, merged, ambiguous = deduplicate(kept, verbose=args.verbose)
    print(f"   After dedup: {len(deduped)} entries")
    print(f"   Merged: {len(merged)} groups, Ambiguous (kept both): {len(ambiguous)} groups")

    # Step 4: Build index
    print("\n4. Building clean index...")
    index = build_clean_index(deduped)
    print(f"   Index entries (≥2 words, ≥4 chars): {len(index)}")

    # Step 5: Save
    output_path = args.output or str(
        Path(args.data_dir) / "naturalproofs" / "clean_foundation.json")
    output = {
        "meta": {
            "total_raw": len(items),
            "after_filter": len(kept),
            "after_dedup": len(deduped),
            "index_size": len(index),
            "dropped_summary": {k: len(v) for k, v in dropped.items()},
            "merged_groups": len(merged),
            "ambiguous_groups": len(ambiguous),
        },
        "index": index,
        "ambiguous": [
            {"stem": key, "titles": titles}
            for key, titles, _ in ambiguous
        ],
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n   Saved to {output_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Raw items:       {len(items):>6}")
    print(f"  After filtering: {len(kept):>6}")
    print(f"  After dedup:     {len(deduped):>6}")
    print(f"  Index entries:   {len(index):>6}")
    print(f"  Ambiguous stems: {len(ambiguous):>6} (kept separate)")

    # Show some ambiguous cases
    if ambiguous:
        print(f"\n  Ambiguous stems (different math, same stem):")
        for key, titles, previews in ambiguous[:30]:
            print(f"    \"{key}\":")
            for title, preview in previews:
                print(f"      - {title}")


if __name__ == "__main__":
    main()
