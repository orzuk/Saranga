"""End-to-end demo: plant reuse → detect with P1 → score the curve.

Proves the measurement loop on real portal data with the cheapest detector.

    python discovery_suite/eval_harness/run_plag_p1_demo.py --papers 200 --plants 60
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _SUITE / "eval_harness", _SUITE / "plagiarism"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import load_papers  # noqa: E402
from planter import plant  # noqa: E402
from scorer import evaluate  # noqa: E402
from p1_shingle import detect_reuse  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="tier3 root (default: local portal)")
    ap.add_argument("--papers", type=int, default=200)
    ap.add_argument("--plants", type=int, default=60)
    ap.add_argument("--levels", default="L0,L1,L2")
    ap.add_argument("--min-jaccard", type=float, default=0.2)
    ap.add_argument("--llm", default=None,
                    help="model key (haiku/sonnet/opus) for LLM paraphrase of L2-L4; "
                         "omit for rule-based obfuscation")
    args = ap.parse_args()

    paraphraser = None
    if args.llm:
        from llm_paraphrase import make_paraphraser
        paraphraser = make_paraphraser(model=args.llm)
        print(f"      using LLM paraphraser ({args.llm}) for L2-L4")

    print(f"[1/3] loading up to {args.papers} papers …", flush=True)
    papers = load_papers(root=args.root, limit=args.papers)
    print(f"      loaded {len(papers)} papers, "
          f"{sum(len(p.nodes) for p in papers)} nodes")

    levels = tuple(args.levels.split(","))
    print(f"[2/3] planting {args.plants} reuse cases across {levels} …", flush=True)
    pc = plant(papers, n_plants=args.plants, levels=levels, paraphraser=paraphraser)
    gold = pc.gold_pairs()
    gold_levels = {
        frozenset({f"{g.source_paper_id}::{g.source_node_id}",
                   f"{g.target_paper_id}::{g.target_node_id}"}): g.level
        for g in pc.gold
    }

    print(f"[3/3] P1 detect (min_jaccard={args.min_jaccard}) …", flush=True)
    preds = detect_reuse(pc.papers, min_jaccard=args.min_jaccard)
    print(f"      {len(preds)} candidate cross-paper node pairs")

    res = evaluate(preds, gold, gold_levels=gold_levels)
    print("\n=== P1 evaluation ===")
    print(res.format())

    # Any high-scoring non-planted pair is a *real* candidate worth a look.
    planted_keys = {k for gp in gold for k in gp}
    novel = [(a, b, s) for a, b, s in preds
             if a not in planted_keys and b not in planted_keys][:10]
    if novel:
        print("\n=== top non-planted (real) candidates ===")
        for a, b, s in novel:
            print(f"  {s:.3f}  {a}  <->  {b}")


if __name__ == "__main__":
    main()
