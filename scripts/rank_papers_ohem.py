#!/usr/bin/env python3
"""Rank papers by how badly the BASE parser does on them — hard-example mining.

Standalone sibling of the `--order worst-first` path inside
`silver_distillation_merged.py`, so a pool can be ranked and inspected WITHOUT
paying for a distillation run. Pool-agnostic: point it at the 17 v4.1 train
papers or at the 200-paper v5.1 corpus with the same command.

Ranked by **dark-knowledge count** (gold items the base parser fails to account
for), not by base F1 — F1 is low both when a paper is rich in missable structure
and when it is merely pathological, and ranking on raw badness feeds you the
pathological ones.

Draws only from the split you ask for. Distillation writes rules FROM these
papers, so ranking over test papers and then distilling them is training on the
test set; `--split train` is the default for that reason.

Usage:
    python scripts/rank_papers_ohem.py \
        --tex-dir /path/to/alignment/papers \
        --t2-dir corpus/silver/opus-4.8__v4.1 \
        --split train
"""

import argparse
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

import silver_distillation_sequential as seq
from silver_distillation_sequential import FNAME_MAP, convert_t2_to_gold_csv
from silver_distillation_merged import (SILVER_METADATA, base_method_groups,
                                        baseline_snapshot, load_splits,
                                        rank_worst_first)

TYPES = list(FNAME_MAP.keys())


def load_json_paths(metadata_csv: Path) -> dict:
    """{paper_id: json_path} straight from the corpus index.

    Not derivable from one --t2-dir: the 17 train papers alone span two
    extraction dirs (14 under opus-4.8__v4.1, 3 under opus-4.7__v4.1), so
    assuming a single directory silently drops papers.
    """
    out = {}
    if not Path(metadata_csv).exists():
        return out
    with open(metadata_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid, jp = row.get("paper_id"), row.get("json_path")
            if pid and jp and pid not in out:
                out[pid] = REPO / jp
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex-dir", required=True,
                    help="root holding <paper_id>/source/*.tex")
    ap.add_argument("--t2-dir", default="corpus/silver/opus-4.8__v4.1",
                    help="silver JSONs to build gold from")
    ap.add_argument("--split", default="train",
                    help="split to draw from ('train', 'test', 'pool', or "
                         "'any'). Default train — distillation writes rules "
                         "FROM these papers.")
    ap.add_argument("--papers", default=None,
                    help="explicit comma list, overrides --split")
    ap.add_argument("--metadata", default=str(SILVER_METADATA))
    ap.add_argument("--work-dir", default=None)
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--match-mode", default="m1", choices=["m1", "m3"])
    ap.add_argument("--cover", type=float, default=0.7)
    ap.add_argument("--match-metric", default="containment",
                    choices=["jaccard", "containment"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    seq._MATCH_METRIC = args.match_metric
    t2_dir = (REPO / args.t2_dir) if not Path(args.t2_dir).is_absolute() \
        else Path(args.t2_dir)
    tex_dir = Path(args.tex_dir)

    splits = load_splits(Path(args.metadata))
    json_paths = load_json_paths(Path(args.metadata))
    if args.papers:
        papers = [p.strip() for p in args.papers.split(",") if p.strip()]
    elif args.split == "any":
        papers = sorted(splits)
    else:
        papers = sorted(p for p, s in splits.items() if s == args.split)
    def _json_for(pid):
        jp = json_paths.get(pid)
        return jp if (jp and jp.exists()) else (t2_dir / f"{pid}.json")

    papers = [p for p in papers if _json_for(p).exists()
              and (tex_dir / p / "source").is_dir()]
    if not papers:
        sys.exit(f"No usable papers for split={args.split} "
                 f"(need both {t2_dir}/<id>.json and {tex_dir}/<id>/source/)")

    work = Path(args.work_dir) if args.work_dir else \
        REPO / "src" / "LLMVersion" / "_ohem_rank"
    gold_dir = work / "gold"
    if gold_dir.exists():
        import shutil
        shutil.rmtree(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)
    for pid in papers:
        for t in TYPES:
            convert_t2_to_gold_csv(_json_for(pid), t, gold_dir)

    groups = base_method_groups(TYPES)
    base_snap = baseline_snapshot(work, groups)

    print(f"ranking {len(papers)} paper(s) from split={args.split} "
          f"(mode={args.match_mode}, metric={args.match_metric})\n")
    ranked = rank_worst_first(papers, tex_dir, TYPES, gold_dir, base_snap,
                              args.threshold, match_mode=args.match_mode,
                              cover=args.cover)

    print(f"\n{'rank':>4}  {'paper':<12} {'missed':>7} {'gold':>6} {'miss rate':>10}")
    for i, (pid, missed, n_gold) in enumerate(ranked, 1):
        rate = missed / n_gold if n_gold else 0.0
        print(f"{i:>4}  {pid:<12} {missed:>7} {n_gold:>6} {rate:>9.2f}")

    out = Path(args.out) if args.out else work / "paper_ranking.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "paper_id", "n_missed", "n_gold", "miss_rate", "split"])
        for i, (pid, missed, n_gold) in enumerate(ranked, 1):
            w.writerow([i, pid, missed, n_gold,
                        round(missed / n_gold, 4) if n_gold else 0.0,
                        splits.get(pid, "")])
    print(f"\nWrote {out}")
    print("Distil in this order with: --pilot-papers "
          + ",".join(pid for pid, _, _ in ranked))


if __name__ == "__main__":
    main()
