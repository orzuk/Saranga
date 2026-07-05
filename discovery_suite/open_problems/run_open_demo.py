"""T-OPEN demo: plant problem↔resolution twins → O1 retrieve → score recall.

    python discovery_suite/open_problems/run_open_demo.py --papers 300 --twins 40
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _SUITE / "eval_harness", _SUITE / "open_problems"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import load_papers  # noqa: E402
from open_planter import plant_twins  # noqa: E402
from scorer import evaluate  # noqa: E402
from o1_retrieve import retrieve  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--papers", type=int, default=300)
    ap.add_argument("--twins", type=int, default=40)
    ap.add_argument("--levels", default="L0,L1,L2")
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--llm", default=None)
    args = ap.parse_args()

    paraphraser = None
    if args.llm:
        from llm_paraphrase import make_paraphraser
        paraphraser = make_paraphraser(model=args.llm)

    print(f"[1/3] loading up to {args.papers} papers …", flush=True)
    papers = load_papers(root=args.root, limit=args.papers)
    print(f"      {len(papers)} papers, {sum(len(p.nodes) for p in papers)} nodes")

    levels = tuple(args.levels.split(","))
    print(f"[2/3] planting {args.twins} open-problem/theorem twins {levels} …", flush=True)
    po = plant_twins(papers, n_twins=args.twins, levels=levels, paraphraser=paraphraser)
    gold = po.gold_pairs()
    print(f"      planted {len(gold)} twins")

    print(f"[3/3] O1 retrieve (top_k={args.top_k}) …", flush=True)
    preds = retrieve(po.papers, top_k=args.top_k)
    print(f"      {len(preds)} problem→theorem candidate pairs")

    res = evaluate(preds, gold, gold_levels=po.gold_levels())
    print("\n=== O1 evaluation ===")
    print(res.format())

    planted_keys = {k for gp in gold for k in gp}
    novel = [(a, b, s) for a, b, s in preds
             if a not in planted_keys and b not in planted_keys][:10]
    if novel:
        print("\n=== top non-planted (real) problem→theorem candidates ===")
        for a, b, s in novel:
            print(f"  {s:.3f}  {a}  =>  {b}")


if __name__ == "__main__":
    main()
