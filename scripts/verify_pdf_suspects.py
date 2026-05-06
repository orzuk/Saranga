#!/usr/bin/env python3
"""
Verify suspected PDF parses by checking the original source files.

Two-phase approach:
  Phase 1: Single-pass scan of all .tex files under tex-dir, build
           filename→path index (fast, no repeated rglob).
  Phase 2: For each suspect from the CSV, look up the index and
           classify the source into tiers.

Tiers:
  1. confirmed_pdf      — starts with %PDF
  2. confirmed_binary   — high binary byte ratio (PostScript, DVI, etc.)
  3. likely_not_latex    — no documentclass or begin{document} found
  4. false_positive      — source is valid LaTeX (JSON detection was wrong)
  5. source_not_found    — could not locate .tex file

Usage:
    python scripts/verify_pdf_suspects.py \
        --csv suspected_pdfs.csv \
        --tex-dir /path/to/full_papers_advanced \
        [--output verified_pdfs.csv]
"""

import argparse
import csv
import os
import re
from pathlib import Path


def build_tex_index(tex_base: str) -> dict[str, str]:
    """Walk tex_base once and build paper_id → tex_path mapping."""
    index = {}
    tex_root = Path(tex_base)
    count = 0
    for tex_file in tex_root.rglob("*.tex"):
        count += 1
        if count % 10000 == 0:
            print(f"[DEBUG] Indexing .tex files: {count:,} found so far ...", flush=True)
        stem = tex_file.stem  # e.g. "1009.4441v1"
        # Store by full stem (versioned) and base ID (unversioned)
        index[stem] = str(tex_file)
        m = re.match(r'(\d{4}\.\d{4,5})', stem)
        if m:
            base = m.group(1)
            # Don't overwrite if already set (keep first match)
            if base not in index:
                index[base] = str(tex_file)
    print(f"[DEBUG] Indexed {count:,} .tex files, {len(index):,} index entries", flush=True)
    return index


def classify_source(tex_path: str) -> tuple[str, str]:
    """Classify a source file. Returns (tier, detail)."""
    # Tier 1: PDF magic bytes
    try:
        with open(tex_path, "rb") as f:
            header = f.read(1024)
    except Exception as e:
        return "read_error", str(e)

    if header.startswith(b"%PDF"):
        return "confirmed_pdf", "starts with %PDF"

    # Tier 2: high binary ratio in first 1KB
    if len(header) > 0:
        non_text = sum(1 for b in header
                       if b > 127 or (b < 9) or (b == 11) or (b == 12)
                       or (14 <= b < 32))
        ratio = non_text / len(header)
        if ratio > 0.10:
            detail = f"binary ratio {ratio:.0%}"
            if header.startswith(b"%!PS"):
                detail = "PostScript file"
            elif header[:2] == b"\xf7\x02":
                detail = "DVI file"
            elif header[:2] == b"\x1f\x8b":
                detail = "gzip compressed"
            elif header[:4] == b"PK\x03\x04":
                detail = "ZIP archive"
            return "confirmed_binary", detail

    # Tier 3: no LaTeX markers in first 10KB
    try:
        with open(tex_path, "r", errors="replace") as f:
            head = f.read(10_000)
    except Exception as e:
        return "read_error", str(e)

    has_documentclass = "\\documentclass" in head or "\\documentstyle" in head
    has_begin_doc = "\\begin{document}" in head

    if not has_documentclass and not has_begin_doc:
        detail = "no LaTeX markers"
        if "<html" in head.lower() or "<!doctype" in head.lower():
            detail = "HTML file"
        elif head.strip().startswith("{"):
            detail = "JSON file"
        elif "\\input" in head or "\\section" in head or "\\def" in head:
            detail = "LaTeX fragment (no preamble but has LaTeX commands)"
        return "likely_not_latex", detail

    # Tier 4: valid LaTeX
    return "false_positive", "valid LaTeX source"


def main():
    parser = argparse.ArgumentParser(description="Verify suspected PDF parses")
    parser.add_argument("--csv", required=True,
                        help="Input CSV from detect_pdf_parses.py")
    parser.add_argument("--tex-dir", required=True,
                        help="Root of downloaded .tex sources")
    parser.add_argument("--output", default=None,
                        help="Output CSV with verification results")
    args = parser.parse_args()

    # Read suspects
    with open(args.csv, "r") as f:
        reader = csv.DictReader(f)
        suspects = list(reader)
    print(f"Loaded {len(suspects):,} suspects from {args.csv}", flush=True)

    # Phase 1: build index once
    print(f"\nPhase 1: Indexing .tex files under {args.tex_dir} ...", flush=True)
    tex_index = build_tex_index(args.tex_dir)

    # Phase 2: classify each suspect
    print(f"\nPhase 2: Classifying {len(suspects):,} suspects ...", flush=True)
    results = []
    tier_counts = {}
    tier_by_cat = {}
    not_found = 0

    for i, row in enumerate(suspects):
        if (i + 1) % 500 == 0:
            print(f"[DEBUG] Verified {i+1:,} / {len(suspects):,} ...", flush=True)

        json_name = row["json_file"]
        category = row["category"]
        paper_id = json_name.rsplit("_", 1)[0]  # "1907.08678v1_manual.json" → "1907.08678v1"

        # Look up in index: try versioned first, then base ID
        tex_path = tex_index.get(paper_id)
        if tex_path is None:
            base_id = paper_id.split("v")[0]
            tex_path = tex_index.get(base_id)

        if tex_path is None:
            tier = "source_not_found"
            detail = ""
            not_found += 1
        else:
            tier, detail = classify_source(tex_path)

        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        cat_key = (category, tier)
        tier_by_cat[cat_key] = tier_by_cat.get(cat_key, 0) + 1

        results.append({
            **row,
            "tier": tier,
            "detail": detail,
            "tex_path": tex_path or "",
        })

    # --- Summary ---
    print(f"\n{'='*70}")
    print(f"Verification Summary")
    print(f"{'='*70}")
    print(f"Total suspects verified: {len(suspects):,}")
    print()

    print("Classification tiers:")
    for tier in ["confirmed_pdf", "confirmed_binary", "likely_not_latex",
                 "false_positive", "source_not_found", "read_error"]:
        cnt = tier_counts.get(tier, 0)
        if cnt > 0:
            pct = 100 * cnt / len(suspects)
            print(f"  {tier:25s}: {cnt:5,} ({pct:5.1f}%)")

    confirmed_bad = (tier_counts.get("confirmed_pdf", 0)
                     + tier_counts.get("confirmed_binary", 0)
                     + tier_counts.get("likely_not_latex", 0))
    print(f"\n  Total non-LaTeX sources:  {confirmed_bad:,}")
    print(f"  False positives:          {tier_counts.get('false_positive', 0):,}")
    print(f"  Source not found:         {not_found:,}")

    # Per-category breakdown for confirmed non-LaTeX
    print(f"\nPer-category breakdown (confirmed non-LaTeX only):")
    cat_totals = {}
    for (cat, tier), cnt in tier_by_cat.items():
        if tier in ("confirmed_pdf", "confirmed_binary", "likely_not_latex"):
            cat_totals[cat] = cat_totals.get(cat, 0) + cnt
    for cat, cnt in sorted(cat_totals.items(), key=lambda x: -x[1]):
        print(f"  {cat:12s}: {cnt:4d}")

    # Detail breakdown for non-PDF non-LaTeX
    print(f"\nNon-PDF binary/non-LaTeX details:")
    detail_counts = {}
    for r in results:
        if r["tier"] in ("confirmed_binary", "likely_not_latex"):
            detail_counts[r["detail"]] = detail_counts.get(r["detail"], 0) + 1
    for detail, cnt in sorted(detail_counts.items(), key=lambda x: -x[1]):
        print(f"  {detail:35s}: {cnt:4d}")

    # Disk space wasted by confirmed non-LaTeX
    wasted = sum(int(r["file_size_bytes"]) for r in results
                 if r["tier"] in ("confirmed_pdf", "confirmed_binary", "likely_not_latex"))
    if wasted > 1_048_576:
        print(f"\nDisk wasted by non-LaTeX JSONs: {wasted / 1_048_576:.1f} MB")
    else:
        print(f"\nDisk wasted by non-LaTeX JSONs: {wasted / 1024:.1f} KB")

    # Write output CSV
    if args.output:
        fieldnames = list(results[0].keys())
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nCSV written to {args.output}")

    print(f"{'='*70}")


if __name__ == "__main__":
    main()
