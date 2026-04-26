#!/usr/bin/env python3
"""Rename per-paper extraction artifacts to model-tagged convention.

Bare ``gold.json`` is ambiguous about which model produced it. This script
applies the convention agreed on (2026-04-26):

    gold.json                  -> gold_opus_4_7.json     (post-Apr-16 era)
    gold.backup-opus46.json    -> gold_opus_4_6.json     (pre-Apr-16 era)
    gold_opus4_7_new.json      -> gold_opus_4_7_v2prompt.json   (paper5 only)

Sibling artifacts (.html, .png, .svg, .json.bak) are renamed in lockstep
so each paper folder remains self-consistent.

The mtime cutoff for 4.6 vs 4.7 is set by the Opus 4.7 release date
(2026-04-16); files in the corpus are all >=2026-04-19, well clear of
the ambiguity zone, so we tag them all 4.7.

Usage:
    python3 scripts/silver_gold/rename_extractions.py \\
        --base-dir /mnt/g/.../alignment_benchmark
    # add --execute to actually rename (default: dry-run)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

# (old_stem, new_stem) for files we rename
RENAME_RULES: List[Tuple[str, str]] = [
    ("gold",                 "gold_opus_4_7"),
    ("gold.backup-opus46",   "gold_opus_4_6"),
    ("gold_opus4_7_new",     "gold_opus_4_7_v2prompt"),
]

# Suffixes we rename in lockstep (the json + every visualization sibling)
SIBLING_SUFFIXES = [".json", ".json.bak", ".html", ".png", ".svg",
                    "_nolegend.png", "_nolegend.svg",
                    ".linked.json"]


def collect_renames(base_dir: Path) -> List[Tuple[Path, Path]]:
    """Walk papers/ and produce a list of (src, dst) rename operations.

    Skips operations whose dst already exists (idempotent re-runs)."""
    pairs: List[Tuple[Path, Path]] = []
    papers_dir = base_dir / "papers"
    if not papers_dir.exists():
        sys.exit(f"[ERROR] {papers_dir} not found")

    for pdir in sorted(papers_dir.iterdir()):
        if not pdir.is_dir():
            continue
        for old_stem, new_stem in RENAME_RULES:
            for suffix in SIBLING_SUFFIXES:
                src = pdir / f"{old_stem}{suffix}"
                dst = pdir / f"{new_stem}{suffix}"
                if not src.exists():
                    continue
                if dst.exists():
                    print(f"[skip] {dst} already exists, leaving {src} alone")
                    continue
                pairs.append((src, dst))
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-dir", type=Path,
                    default=Path("/mnt/g/My Drive/Research/Automath/alignment_benchmark"),
                    help="alignment_benchmark dir (parent of papers/)")
    ap.add_argument("--execute", action="store_true",
                    help="actually do the renames (default: dry-run)")
    args = ap.parse_args()

    pairs = collect_renames(args.base_dir)

    if not pairs:
        print("[INFO] no renames to perform")
        return 0

    by_rule: dict = {}
    for src, dst in pairs:
        # collapse: count by (old_stem -> new_stem)
        for old_stem, new_stem in RENAME_RULES:
            if src.name.startswith(old_stem + ".") or src.name == old_stem:
                key = f"{old_stem}.* -> {new_stem}.*"
                by_rule[key] = by_rule.get(key, 0) + 1
                break

    print(f"[{'EXECUTE' if args.execute else 'DRY-RUN'}] {len(pairs)} renames planned:")
    for k, v in sorted(by_rule.items()):
        print(f"    {v:4d} × {k}")

    if not args.execute:
        print("\n[DRY-RUN] showing first 8 examples:")
        for src, dst in pairs[:8]:
            print(f"    {src} -> {dst.name}")
        print("\nRe-run with --execute to apply.")
        return 0

    n_ok = 0
    n_fail = 0
    for src, dst in pairs:
        try:
            src.rename(dst)
            n_ok += 1
        except Exception as e:
            print(f"[FAIL] {src} -> {dst.name}: {type(e).__name__}: {e}")
            n_fail += 1

    print(f"\n[DONE] {n_ok} renamed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
