#!/usr/bin/env python3
"""Compact verbose extraction-JSON IDs to the project convention.

Many extractions invent verbose IDs like `paper5_ch01_def07` when the
project uses compact `DP5.7` (Definition Paper-5 #7). This script
remaps IDs in-place using the convention from the existing 270-paper
Opus extractions:

    definition  → DP<paper_num>.<idx>
    theorem     → TP<paper_num>.<idx>
    lemma       → LP<paper_num>.<idx>
    proposition → PrP<paper_num>.<idx>     (avoid clash with Proof's PP)
    corollary   → CP<paper_num>.<idx>
    proof       → PP<paper_num>.<idx>
    proof_step  → PSP<paper_num>.<idx>
    algorithm   → AP<paper_num>.<idx>
    equation    → EP<paper_num>.<idx>
    example     → ExP<paper_num>.<idx>
    remark      → RP<paper_num>.<idx>
    problem     → ProbP<paper_num>.<idx>
    claim       → ClP<paper_num>.<idx>
    conjecture  → CnjP<paper_num>.<idx>

Edge endpoint IDs are remapped consistently. Edits in place; backs up
the original to <stem>.bak unless --no-backup. Idempotent (running
twice on the same file is safe).

Usage:
    python3 compact_ids.py path/to/gold_opus4_7_new.json
    python3 compact_ids.py --paper-num 5 path/to/file.json   # explicit paper-num
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List

# Type → ID prefix
_TYPE_PREFIX = {
    "definition":  "DP",
    "theorem":     "TP",
    "lemma":       "LP",
    "proposition": "PrP",
    "corollary":   "CP",
    "proof":       "PP",
    "proof_step":  "PSP",
    "algorithm":   "AP",
    "equation":    "EP",
    "example":     "ExP",
    "remark":      "RP",
    "problem":     "ProbP",
    "claim":       "ClP",
    "conjecture":  "CnjP",
}

# Match an ID that is ALREADY in the compact form (any known prefix
# followed by NUM.NUM). If matched, the script leaves it alone.
_COMPACT_RE = re.compile(
    r'^(?:' + '|'.join(_TYPE_PREFIX.values()) + r')\d+\.\d+(?:[a-z])?$'
)


def infer_paper_num(json_path: Path, override: int | None) -> int:
    if override is not None:
        return override
    # Try to extract from path: .../papers/paperN/...
    for part in json_path.parts:
        m = re.match(r'paper(\d+)$', part)
        if m:
            return int(m.group(1))
    # Fallback: from filename or metadata.json sibling
    metadata = json_path.parent / "metadata.json"
    if metadata.exists():
        try:
            md = json.loads(metadata.read_text())
            pn = md.get("paper_num")
            if pn is not None:
                return int(pn)
        except Exception:
            pass
    raise ValueError(
        f"Could not infer paper_num from {json_path}; pass --paper-num."
    )


def compact_one(json_path: Path, paper_num: int, no_backup: bool = False) -> int:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    if not nodes:
        print(f"  {json_path.name}: no nodes; skip")
        return 0

    # Build old→new ID map. Per-type counter so we get .1, .2, .3 etc.
    # If an ID is already in compact form, keep it.
    id_map: Dict[str, str] = {}
    counters: Dict[str, int] = {}
    for n in nodes:
        old_id = n.get("id")
        if not old_id:
            continue
        if _COMPACT_RE.match(str(old_id)):
            id_map[old_id] = old_id
            continue
        ntype = n.get("type", "definition")
        prefix = _TYPE_PREFIX.get(ntype, "XP")  # XP for unknown types
        counters[prefix] = counters.get(prefix, 0) + 1
        new_id = f"{prefix}{paper_num}.{counters[prefix]}"
        id_map[old_id] = new_id

    if not any(o != n for o, n in id_map.items()):
        print(f"  {json_path.name}: already compact; skip")
        return 0

    # Apply: rename id; remap any field that references node IDs.
    # Reference fields can include: parent_proof_id, proves_id, depends_on,
    # depends_on_step_ids, uses_node_ids, parent_proof, proves, parent.
    REF_FIELDS_SCALAR = {"parent_proof_id", "parent_proof", "proves_id",
                         "proves", "parent", "depends_on"}
    REF_FIELDS_LIST = {"depends_on_step_ids", "uses_node_ids",
                       "depends_on_ids", "uses"}

    for n in nodes:
        if n.get("id") in id_map:
            n["id"] = id_map[n["id"]]
        for fld in REF_FIELDS_SCALAR:
            v = n.get(fld)
            if isinstance(v, str) and v in id_map:
                n[fld] = id_map[v]
        for fld in REF_FIELDS_LIST:
            v = n.get(fld)
            if isinstance(v, list):
                n[fld] = [id_map.get(x, x) if isinstance(x, str) else x for x in v]

    # Edges
    for e in data.get("edges", []):
        for fld in ("source", "target"):
            v = e.get(fld)
            if isinstance(v, str) and v in id_map:
                e[fld] = id_map[v]

    # Backup, then overwrite
    if not no_backup:
        bak = json_path.with_suffix(json_path.suffix + ".bak")
        if not bak.exists():
            shutil.copy(json_path, bak)

    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    n_changed = sum(1 for o, n in id_map.items() if o != n)
    print(f"  {json_path.name}: remapped {n_changed} IDs (paper_num={paper_num})")
    return n_changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Compact verbose JSON IDs to project convention")
    ap.add_argument("files", nargs="+", help="JSON files to compact")
    ap.add_argument("--paper-num", type=int, default=None,
                    help="Override paper number (inferred from path otherwise)")
    ap.add_argument("--no-backup", action="store_true",
                    help="Don't write a .bak alongside the modified file")
    args = ap.parse_args()

    total = 0
    for f in args.files:
        p = Path(f)
        if not p.exists():
            print(f"[WARN] {f} not found; skip")
            continue
        try:
            pn = infer_paper_num(p, args.paper_num)
            total += compact_one(p, pn, args.no_backup)
        except Exception as e:
            print(f"[WARN] {f}: {type(e).__name__}: {e}")
    print(f"\n[DONE] total IDs remapped: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
