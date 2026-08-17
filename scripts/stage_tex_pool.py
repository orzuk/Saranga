#!/usr/bin/env python3
"""Stage the flat silver tex pool into the nested layout distillation expects.

`corpus/silver/tex_pool/` is FLAT (`<arxiv_id>.tex`), but
`silver_distillation_merged.py --tex-dir` wants `<tex_dir>/<paper>/source/*.tex`.
`eval_distill_heldout.py` already stages internally, so it can consume the flat
pool directly — the merged distillation runner cannot. This bridges that gap.

Reuses `stage_flat_tex()` from eval_distill_heldout so both paths share one
implementation (symlinks where the filesystem allows, copies otherwise).

Papers are selected from the split file so staging matches the corpus index:

    python scripts/stage_tex_pool.py --split train      # 60 v5.1 train papers
    python scripts/stage_tex_pool.py --split all --out /tmp/tex_staged

Then:

    python scripts/silver_distillation_merged.py \\
        --t2-dir corpus/silver/opus-5__v5.1 \\
        --tex-dir corpus/silver/tex_staged \\
        --pilot-papers "$(python scripts/stage_tex_pool.py --split train --print-ids)" \\
        --eval-dir <out>
"""
import argparse
import csv
import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPLIT_CSV = REPO / "corpus/silver/split_opus5.csv"
POOL = REPO / "corpus/silver/tex_pool"
DEFAULT_OUT = REPO / "corpus/silver/tex_staged"


def _stage_flat_tex():
    """Borrow the staging helper from eval_distill_heldout (single source)."""
    p = Path(__file__).resolve().parent / "eval_distill_heldout.py"
    spec = importlib.util.spec_from_file_location("_edh", p)
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(p.parent))
    spec.loader.exec_module(m)
    return m.stage_flat_tex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train", choices=["train", "test", "all"])
    ap.add_argument("--split-csv", default=str(SPLIT_CSV))
    ap.add_argument("--pool", default=str(POOL))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--print-ids", action="store_true",
                    help="print the comma-separated ids and exit (for --pilot-papers)")
    args = ap.parse_args()

    if not os.path.isfile(args.split_csv):
        sys.exit("missing %s — run scripts/assign_split_opus5.py first" % args.split_csv)
    rows = list(csv.DictReader(open(args.split_csv, encoding="utf-8")))
    papers = sorted(r["arxiv_id"] for r in rows
                    if args.split == "all" or r["split"] == args.split)

    if args.print_ids:
        print(",".join(papers))
        return 0

    print("staging %d %s paper(s) from %s" % (len(papers), args.split,
                                              os.path.relpath(args.pool, REPO)))
    staged, missing = _stage_flat_tex()(papers, Path(args.pool), Path(args.out))
    if missing:
        print("  MISSING tex for %d paper(s) — refetch with:\n"
              "    python scripts/fetch_tex_for_targets.py --ids %s"
              % (len(missing), ",".join(missing[:10]) + (" ..." if len(missing) > 10 else "")))
        return 1
    print("  all %d paper(s) have tex -> --tex-dir %s"
          % (len(papers), os.path.relpath(staged, REPO)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
