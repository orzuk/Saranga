#!/usr/bin/env python3
"""Point every generated `distilled_rules.py` at the ONE shared LaTeX cleaner.

Each codegen wrote its own `_clean_latex`, and they masked math as the literal
token `[MATH]` while the base parser preserves math as words. Containment
between two *identical* theorem statements cleaned by the two functions
measures 0.44 — below the 0.7 dedup bar — so identical statements survived as
duplicate nodes, which is the bulk of what looked like distillation losing
precision.

`latex_clean.py` already declares itself the single cleaner for "the base regex
parser AND all distilled-rule extractors"; the codegen prompt quietly violated
that. The prompt is fixed for new runs; this repairs the artifacts already on
disk. No LLM calls — it swaps the function body and leaves every call site.

Usage:
    python scripts/repair_distilled_cleaners.py --dry-run
    python scripts/repair_distilled_cleaners.py            # writes, with .bak
"""

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

from silver_distillation_merged import canonicalize_clean_latex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO),
                    help="tree to sweep for distilled_rules.py")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--include-history", action="store_true",
                    help="ALSO rewrite snapshots/ and sweep/ files. Off by "
                         "default: those are the frozen record of what a past "
                         "run actually executed, and rewriting them means that "
                         "run's published numbers no longer reproduce.")
    args = ap.parse_args()

    files = sorted(p for p in Path(args.root).rglob("distilled_rules.py")
                   if p.is_file() and not p.is_symlink())
    if not args.include_history:
        hist = [p for p in files
                if "snapshots" in p.parts or "sweep" in p.parts]
        files = [p for p in files if p not in set(hist)]
        if hist:
            print(f"skipping {len(hist)} historical file(s) under snapshots/ "
                  f"and sweep/ (--include-history to rewrite them)\n")
    changed = skipped = already = 0
    for f in files:
        try:
            src = f.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  [skip] {f}: {e}")
            skipped += 1
            continue
        if "_shared_clean_latex" in src:
            already += 1
            continue
        new, ok = canonicalize_clean_latex(src)
        if not ok:
            skipped += 1
            continue
        had_math = "[MATH]" in src
        rel = f.relative_to(REPO)
        print(f"  {'would fix' if args.dry_run else 'fixed'} {rel}"
              f"{'   (was masking math as [MATH])' if had_math else ''}")
        if not args.dry_run:
            if not args.no_backup:
                shutil.copy2(f, f.with_suffix(".py.precleaner_bak"))
            f.write_text(new, encoding="utf-8")
        changed += 1

    print(f"\nscanned {len(files)} file(s): {changed} "
          f"{'to fix' if args.dry_run else 'fixed'}, {already} already canonical, "
          f"{skipped} without a local _clean_latex")


if __name__ == "__main__":
    main()
