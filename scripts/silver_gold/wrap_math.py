#!/usr/bin/env python3
"""Post-process extraction JSONs to wrap bare math fragments in $..$.

The visualizer renders text inside $..$ as math (proper subscripts,
superscripts, Greek letters). Without $..$, "R_+^{d x d}" shows up as
plain "R_+^{d x d}" — exactly what the user is seeing on paper5.

Memory rule (json_extraction_rules.md, visualization_principles.md):
  > JSON SHOULD have $...$ around LaTeX math expressions.
  > If a gold JSON is missing $ delimiters, ADD them (this is fixing
  > the data, not a rendering hack).

This script identifies math-like tokens and wraps them. Conservative:
- A token gets wrapped if it contains `_`, `^`, or starts with `\`
  (the three ironclad math signatures).
- Already-wrapped runs ($..$) are left alone.
- Plain English words pass through untouched.

Usage:
    python3 scripts/silver_gold/wrap_math.py \\
        path/to/gold.json [path/to/another.json ...]
    # or by directory tree:
    python3 scripts/silver_gold/wrap_math.py \\
        --base-dir /path/alignment_benchmark \\
        --paper-ids paper1,paper2,paper5 \\
        --suffixes "" _deepseek_r _deepseek4

Modifies files IN PLACE. Backs up original to <file>.bak unless --no-backup.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable, List

# A token is math if it contains any of these signatures:
#   _<word-char>        e.g.  R_+, sigma_i, x_{ij}
#   ^<word-char>        e.g.  P^T, x^2, R^{d x d}
#   \<lowercase-cmd>    e.g.  \delta, \sum, \mathbb
_HAS_SUB = re.compile(r'[A-Za-z0-9}\)]_')    # underscore as subscript marker
_HAS_SUP = re.compile(r'[A-Za-z0-9}\)]\^')   # caret as superscript marker
_HAS_CMD = re.compile(r'\\[A-Za-z]')          # LaTeX command

# Trailing punctuation we should NOT include in $..$ (it belongs to the
# surrounding sentence). Note: keep ) since it's often part of math like f(x).
_TRAILING_PUNCT = re.compile(r'[.,;:!?]+$')


def looks_mathy(token: str) -> bool:
    """True if a non-whitespace token looks like a math fragment."""
    if not token or token.startswith("$"):
        return False
    return bool(
        _HAS_SUB.search(token) or
        _HAS_SUP.search(token) or
        _HAS_CMD.search(token)
    )


def find_math_runs(text: str):
    """Yield (start, end) tuples of math runs in `text`, treating balanced
    {..} groups as part of a single token (so R_+^{d x d} stays glued)."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "$":
            # Skip already-wrapped span
            j = text.find("$", i + 1)
            if j < 0:
                i += 1
                continue
            i = j + 1
            continue

        # Walk a token: until we hit whitespace WITHOUT being inside {..}
        start = i
        depth = 0
        while i < n:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
            elif ch.isspace() and depth == 0:
                break
            elif ch == "$" and depth == 0:
                break  # bumped into a wrapped span; back off
            i += 1
        end = i
        token = text[start:end]
        if looks_mathy(token):
            yield (start, end)


def wrap_math_in_text(text: str) -> str:
    """Wrap math runs in $..$, leaving English alone and respecting
    pre-existing $..$ wrappers. Strips trailing punctuation out of the
    wrap."""
    if not text or not isinstance(text, str):
        return text

    runs = list(find_math_runs(text))
    if not runs:
        return text

    out = []
    last = 0
    for s, e in runs:
        out.append(text[last:s])
        token = text[s:e]
        m = _TRAILING_PUNCT.search(token)
        if m:
            tail = m.group(0)
            token = token[:-len(tail)]
        else:
            tail = ""
        if token:
            out.append(f"${token}$")
        out.append(tail)
        last = e
    out.append(text[last:])
    return "".join(out)


def wrap_math_in_node(node: dict) -> int:
    """Apply wrap_math_in_text to all string-valued fields a node may have.
    Returns count of fields modified."""
    fields_to_wrap = ("name", "statement", "raw_text", "raw_latex",
                      "clean_text", "definition", "proof_strategy")
    n_changed = 0
    for fld in fields_to_wrap:
        v = node.get(fld)
        if isinstance(v, str):
            new_v = wrap_math_in_text(v)
            if new_v != v:
                node[fld] = new_v
                n_changed += 1

    # List-of-string fields (assumptions, conclusions)
    for fld in ("assumptions", "conclusions"):
        v = node.get(fld)
        if isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, str):
                    new_item = wrap_math_in_text(item)
                    if new_item != item:
                        n_changed += 1
                    new_list.append(new_item)
                else:
                    new_list.append(item)
            node[fld] = new_list
    return n_changed


def process_one(path: Path, no_backup: bool = False, dry_run: bool = False) -> int:
    """Process a single JSON file. Returns number of node-fields modified."""
    if not path.exists():
        print(f"  [SKIP] {path.name}: does not exist")
        return 0
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        print(f"  [SKIP] {path.name}: no 'nodes' list")
        return 0

    n_modified_total = 0
    n_nodes_modified = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        n = wrap_math_in_node(node)
        if n > 0:
            n_modified_total += n
            n_nodes_modified += 1

    if dry_run:
        print(f"  {path.name}: would modify {n_nodes_modified}/{len(nodes)} nodes "
              f"({n_modified_total} fields total)")
        return n_modified_total

    if n_modified_total == 0:
        print(f"  {path.name}: no math to wrap (already clean or no math)")
        return 0

    # Backup, then overwrite
    if not no_backup:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            shutil.copy(path, bak)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  {path.name}: wrapped math in {n_nodes_modified}/{len(nodes)} nodes "
          f"({n_modified_total} fields)")
    return n_modified_total


def collect_paths(args) -> List[Path]:
    """Resolve --files or --base-dir/--paper-ids/--suffixes into a list."""
    if args.files:
        return [Path(p) for p in args.files]

    if not args.base_dir:
        sys.exit("[ERROR] specify either positional file paths or --base-dir + --paper-ids/--suffixes")

    base = Path(args.base_dir)
    papers_dir = base / "papers"
    if not papers_dir.exists():
        sys.exit(f"[ERROR] {papers_dir} does not exist")

    paper_ids = (
        [s.strip() for s in args.paper_ids.split(",") if s.strip()]
        if args.paper_ids
        else sorted(p.name for p in papers_dir.iterdir() if p.is_dir())
    )

    paths: List[Path] = []
    if args.suffixes is not None:
        suffix_list = [s for s in args.suffixes.split(",")]   # keep "" entries
    else:
        suffix_list = None

    for pid in paper_ids:
        pdir = papers_dir / pid
        if not pdir.exists():
            continue
        if suffix_list is not None:
            for suf in suffix_list:
                paths.append(pdir / f"gold{suf}.json")
        else:
            # auto-discover all gold*.json (excluding .linked.json)
            for f in sorted(pdir.glob("gold*.json")):
                if f.name.endswith(".linked.json"):
                    continue
                paths.append(f)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Wrap bare math fragments in $..$ inside extraction JSONs."
    )
    ap.add_argument("files", nargs="*",
                    help="JSON files to process (alternative to --base-dir)")
    ap.add_argument("--base-dir", type=Path, default=None,
                    help="alignment_benchmark dir (parent of papers/)")
    ap.add_argument("--paper-ids", default="",
                    help="comma-separated paper_ids (default: all in papers/)")
    ap.add_argument("--suffixes", default=None,
                    help="comma-separated list (e.g. ',_deepseek_r'). "
                         "Empty string targets gold.json. "
                         "Default: auto-discover gold*.json in each paper folder.")
    ap.add_argument("--no-backup", action="store_true",
                    help="don't write a .bak alongside the modified file")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing files")
    args = ap.parse_args()

    paths = collect_paths(args)
    if not paths:
        sys.exit("[ERROR] no JSON files resolved")

    print(f"[INFO] processing {len(paths)} JSON file(s)"
          + ("  (DRY RUN)" if args.dry_run else ""))

    total_changed = 0
    n_changed_files = 0
    for p in paths:
        n = process_one(p, no_backup=args.no_backup, dry_run=args.dry_run)
        if n > 0:
            n_changed_files += 1
        total_changed += n

    print(f"\n[DONE] {n_changed_files}/{len(paths)} files had math to wrap; "
          f"{total_changed} fields modified total"
          + ("  (DRY RUN — nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
