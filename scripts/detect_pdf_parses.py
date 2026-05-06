#!/usr/bin/env python3
"""
Detect JSON outputs that were likely parsed from PDF files (not LaTeX).

Checks two things:
1. The original .tex source file — does it start with %PDF or lack
   documentclass / begin{document}?
2. The resulting JSON — anomalies like 0 nodes with large file size,
   binary-looking content in text fields, etc.

Usage:
    python scripts/detect_pdf_parses.py \
        --parsed-dir /path/to/parsed_100k \
        --tex-dir /path/to/full_papers_advanced \
        [--output suspected_pdfs.csv]

If --tex-dir is omitted, detection is based solely on JSON anomalies.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path


def is_pdf_source(tex_path: str) -> bool:
    """Check if a .tex file is actually a PDF (or other binary)."""
    try:
        with open(tex_path, "rb") as f:
            header = f.read(256)
        # PDF magic bytes
        if header.startswith(b"%PDF"):
            return True
        # High ratio of non-ASCII bytes → binary file
        non_ascii = sum(1 for b in header if b > 127 or (b < 32 and b not in (9, 10, 13)))
        if len(header) > 0 and non_ascii / len(header) > 0.3:
            return True
        return False
    except Exception:
        return False


def lacks_latex_markers(tex_path: str) -> bool:
    """Check if a .tex file lacks basic LaTeX markers (might be plain text or PDF)."""
    try:
        with open(tex_path, "r", errors="replace") as f:
            # Read first 10KB — enough to find document preamble
            head = f.read(10_000)
        has_documentclass = "\\documentclass" in head or "\\documentstyle" in head
        has_begin_doc = "\\begin{document}" in head
        return not (has_documentclass or has_begin_doc)
    except Exception:
        return True


def analyze_json(json_path: str) -> dict:
    """Extract anomaly indicators from a parsed JSON.

    PDF-parsed JSONs have a distinctive fingerprint:
    - metadata.title and metadata.abstract are empty (no \\title{} to parse)
    - nodes are only 'equation' type (orphan eq regex matches binary noise)
    - node statement text contains binary garbage (high-ordinal chars, \\x00)
    - 0 edges
    - disproportionately large file size for few nodes
    """
    file_size = os.path.getsize(json_path)
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": str(e), "file_size_bytes": file_size}

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    metadata = data.get("metadata", {})
    num_nodes = len(nodes)
    num_edges = len(edges)

    title = metadata.get("title", "") or ""
    abstract = metadata.get("abstract", "") or ""
    has_title = len(title.strip()) > 0
    has_abstract = len(abstract.strip()) > 0

    # Check for binary-looking content in node text fields
    binary_score = 0
    total_text_len = 0
    for node in nodes:
        for field in ("statement", "name", "label", "body"):
            text = ""
            val = node.get(field, "")
            if isinstance(val, list):
                text = " ".join(str(v) for v in val)
            elif isinstance(val, str):
                text = val
            if text:
                total_text_len += len(text)
                # Count characters that look like binary garbage.
                # Allow: tab(9), newline(10), carriage return(13), space(32)+
                # Flag: null bytes, control chars, high-ordinal decoded binary
                binary_score += sum(1 for c in text
                                    if ord(c) > 255
                                    or (ord(c) < 9)
                                    or (ord(c) == 11) or (ord(c) == 12)
                                    or (14 <= ord(c) < 32))

    # Node type distribution
    type_counts = {}
    for node in nodes:
        t = node.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    # Only-equation check: all nodes are equations (or zero nodes)
    only_equations = all(n.get("type") == "equation" for n in nodes)

    return {
        "file_size_bytes": file_size,
        "num_nodes": num_nodes,
        "num_edges": num_edges,
        "total_text_len": total_text_len,
        "binary_chars": binary_score,
        "binary_ratio": binary_score / max(total_text_len, 1),
        "type_counts": type_counts,
        "has_title": has_title,
        "has_abstract": has_abstract,
        "only_equations": only_equations,
    }


def find_tex_for_json(json_name: str, tex_base: str, category: str) -> str | None:
    """Try to find the source .tex file for a given JSON."""
    # JSON name like "1210.4634v1_manual.json" → paper_id = "1210.4634v1"
    stem = json_name.rsplit("_", 1)[0]  # strip _manual.json suffix

    # Search under tex_base/category/ recursively
    cat_variants = [category, category.replace("_", "."), category.replace(".", "_")]
    for cat in cat_variants:
        cat_dir = Path(tex_base) / cat
        if not cat_dir.exists():
            continue
        for tex_file in cat_dir.rglob(f"{stem}*.tex"):
            return str(tex_file)
        # Also try without version suffix
        base_id = stem.split("v")[0]
        for tex_file in cat_dir.rglob(f"{base_id}*.tex"):
            return str(tex_file)
    return None


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def main():
    parser = argparse.ArgumentParser(description="Detect PDFs parsed as LaTeX in 100K corpus")
    parser.add_argument("--parsed-dir", required=True,
                        help="Root of parsed output (e.g. .../parsed_100k)")
    parser.add_argument("--tex-dir", default=None,
                        help="Root of downloaded .tex sources (e.g. .../full_papers_advanced)")
    parser.add_argument("--output", default=None,
                        help="Output CSV path (default: print to stdout)")
    args = parser.parse_args()

    parsed_root = Path(args.parsed_dir)
    suspects = []

    # Iterate all categories
    cat_dirs = sorted(d for d in parsed_root.iterdir() if d.is_dir())
    total_jsons = 0
    total_suspected = 0

    for cat_dir in cat_dirs:
        json_dir = cat_dir / "json"
        if not json_dir.exists():
            continue

        category = cat_dir.name
        print(f"[DEBUG] Scanning category {category} ...", flush=True)
        json_files = sorted(json_dir.glob("*.json"))
        print(f"[DEBUG]   Found {len(json_files):,} JSON files", flush=True)

        for jf in json_files:
            total_jsons += 1
            if total_jsons % 1000 == 0:
                print(f"[DEBUG]   Scanned {total_jsons:,} JSONs so far, {total_suspected:,} suspected ...", flush=True)
            info = analyze_json(str(jf))
            if "error" in info:
                continue

            # --- Determine if suspected PDF ---
            reason = []

            # Check source .tex if available
            tex_path = None
            if args.tex_dir:
                tex_path = find_tex_for_json(jf.name, args.tex_dir, category)
                if tex_path:
                    if is_pdf_source(tex_path):
                        reason.append("source_is_pdf")
                    elif lacks_latex_markers(tex_path):
                        reason.append("no_latex_markers")

            # JSON-based heuristics — PDF fingerprint:
            # 1. Binary garbage in node text (strongest signal)
            if info["binary_chars"] > 10:
                reason.append("binary_in_text")
            # 2. No title AND no abstract (no \title{} or \begin{abstract})
            if not info["has_title"] and not info["has_abstract"]:
                # Only flag if also has other anomalies
                if info["only_equations"] and info["num_nodes"] > 0:
                    reason.append("no_metadata+only_equations")
                elif info["num_nodes"] == 0 and info["file_size_bytes"] > 50_000:
                    reason.append("no_metadata+0_nodes+large_file")
            # 3. High binary ratio in text content
            if info["binary_ratio"] > 0.01 and info["total_text_len"] > 100:
                reason.append(f"binary_ratio={info['binary_ratio']:.1%}")

            if not reason:
                continue

            total_suspected += 1
            suspects.append({
                "category": category,
                "json_file": jf.name,
                "file_size": format_size(info["file_size_bytes"]),
                "file_size_bytes": info["file_size_bytes"],
                "num_nodes": info["num_nodes"],
                "num_edges": info["num_edges"],
                "total_text_len": info["total_text_len"],
                "binary_chars": info["binary_chars"],
                "binary_ratio": f"{info['binary_ratio']:.2%}",
                "has_title": info["has_title"],
                "has_abstract": info["has_abstract"],
                "only_equations": info["only_equations"],
                "reason": "; ".join(reason),
                "tex_source": tex_path or "",
            })

    # --- Print summary ---
    print(f"\n{'='*70}")
    print(f"PDF Detection Summary")
    print(f"{'='*70}")
    print(f"Total JSONs scanned:    {total_jsons:,}")
    print(f"Suspected PDF parses:   {total_suspected:,} ({100*total_suspected/max(total_jsons,1):.1f}%)")

    if suspects:
        # Per-category breakdown
        print(f"\nPer-category breakdown:")
        cat_counts = {}
        for s in suspects:
            cat_counts[s["category"]] = cat_counts.get(s["category"], 0) + 1
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"  {cat:12s}: {cnt:4d} suspected")

        # Reason breakdown
        print(f"\nDetection reasons:")
        reason_counts = {}
        for s in suspects:
            for r in s["reason"].split("; "):
                reason_counts[r] = reason_counts.get(r, 0) + 1
        for r, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"  {r:25s}: {cnt:4d}")

        # Size stats for suspects
        sizes = [s["file_size_bytes"] for s in suspects]
        print(f"\nSuspected PDF file sizes:")
        print(f"  Min:    {format_size(min(sizes))}")
        print(f"  Median: {format_size(sorted(sizes)[len(sizes)//2])}")
        print(f"  Max:    {format_size(max(sizes))}")
        print(f"  Total:  {format_size(sum(sizes))}")

        # Top 10 largest
        print(f"\nTop 10 largest suspected PDFs:")
        for s in sorted(suspects, key=lambda x: -x["file_size_bytes"])[:10]:
            print(f"  {s['file_size']:>10s}  {s['num_nodes']:3d} nodes  {s['category']:12s}  {s['json_file']}  [{s['reason']}]")

    # --- Write CSV ---
    if args.output:
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "category", "json_file", "file_size", "file_size_bytes",
                "num_nodes", "num_edges", "total_text_len", "binary_chars",
                "binary_ratio", "has_title", "has_abstract", "only_equations",
                "reason", "tex_source",
            ])
            writer.writeheader()
            writer.writerows(suspects)
        print(f"\nCSV written to {args.output}")

    print(f"{'='*70}")


if __name__ == "__main__":
    main()
