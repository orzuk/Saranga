#!/usr/bin/env python3
"""Normalize edge directions in extracted JSONs against the canonical schema.

Some extractions emit structural edges (`proves`, `illustrates`, `solves`,
`tests`, `resolves`) with source/target swapped, because the grammatical reading
("B proves A") runs opposite to the wire direction that `src/edge_types.py`
declares via source_types/target_types. This flips them to canonical form.

An edge is flipped only when it is UNAMBIGUOUSLY backwards: the current source
type is not allowed at source, AND the current target type IS allowed at source
(and vice versa). Ambiguous or already-correct edges are left untouched.

Usage:
    python scripts/normalize_edge_directions.py --dir corpus/silver/opus-5__v5 [--dry-run]
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
import edge_types as ET  # noqa: E402


def wants(edge_type):
    return (ET.get_allowed_source_types(edge_type),
            ET.get_allowed_target_types(edge_type))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(REPO, "corpus/silver/opus-5__v5"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total = Counter()
    for f in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        pid = os.path.basename(f)[:-5]
        d = json.load(open(f, encoding="utf-8"))
        ntype = {n.get("id"): n.get("type") for n in d.get("nodes", [])}
        flipped = Counter()
        for e in d.get("edges", []):
            et = e.get("type")
            src_ok, tgt_ok = wants(et)
            if src_ok is None and tgt_ok is None:
                continue                      # unconstrained (uses/specializes/...)
            s, t = ntype.get(e.get("source")), ntype.get(e.get("target"))
            if s is None or t is None:
                continue
            cur_ok = (src_ok is None or s in src_ok) and (tgt_ok is None or t in tgt_ok)
            rev_ok = (src_ok is None or t in src_ok) and (tgt_ok is None or s in tgt_ok)
            if not cur_ok and rev_ok:         # unambiguously backwards
                e["source"], e["target"] = e["target"], e["source"]
                flipped[et] += 1
        if flipped:
            print("%-10s flipped: %s" % (pid, dict(flipped)))
            total.update(flipped)
            if not args.dry_run:
                json.dump(d, open(f, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        else:
            print("%-10s already canonical" % pid)
    print("\n%s total flips: %s" % ("(dry-run) " if args.dry_run else "", dict(total) or "none"))


if __name__ == "__main__":
    main()
