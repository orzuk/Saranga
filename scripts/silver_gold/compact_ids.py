#!/usr/bin/env python3
"""Compact verbose extraction-JSON IDs to the project convention.

Some extractions invent verbose IDs like `paper5_ch01_def07`. This script
renames them to the v6 convention, `<prefix><seq>` with a counter per type
(`DP7`, `TP2`, `PSP15`), the prefixes being the schema's
(`node_types.ID_PREFIX`, the table the extraction prompt shows). IDs already
compact (v6 `DP7`, or the earlier `DP5.7`) are left alone.

Edge endpoint IDs are remapped consistently. Edits in place; backs up
the original to <stem>.bak unless --no-backup. Idempotent (running
twice on the same file is safe).

Usage:
    python3 compact_ids.py path/to/file.json [more.json ...]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List

# Type → ID prefix: the schema's table (node_types.ID_PREFIX), so this script
# and the extraction prompt cannot disagree.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from node_types import ID_PREFIX as _TYPE_PREFIX  # noqa: E402

# An ID ALREADY in a compact form is left alone: v6 `DP3`, or the earlier
# `DP1.3`.
_COMPACT_RE = re.compile(
    r'^(?:' + '|'.join(sorted(_TYPE_PREFIX.values(), key=len, reverse=True)) + r')\d+(?:\.\d+)?(?:[a-z])?$'
)


def compact_one(json_path: Path, no_backup: bool = False) -> int:
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
        new_id = f"{prefix}{counters[prefix]}"          # v6 form: DP3
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
    print(f"  {json_path.name}: remapped {n_changed} IDs")
    return n_changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Compact verbose JSON IDs to project convention")
    ap.add_argument("files", nargs="+", help="JSON files to compact")
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
            total += compact_one(p, args.no_backup)
        except Exception as e:
            print(f"[WARN] {f}: {type(e).__name__}: {e}")
    print(f"\n[DONE] total IDs remapped: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
