"""T-ALIGN demo: clone-and-perturb → align → recover the node permutation.

For each level we clone a set of papers with known correspondence, run the
bipartite aligner (A2), and report mean matching accuracy. We also align each
original against an UNRELATED paper's clone as a negative control — accuracy
there should collapse toward 0, confirming the score is specific.

    python discovery_suite/alignment/run_align_demo.py --papers 120 --sample 20
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _SUITE / "eval_harness", _SUITE / "alignment"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import load_papers  # noqa: E402
from align_planter import alignment_accuracy, clone_perturbed  # noqa: E402
from a2_bipartite import align  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--papers", type=int, default=120)
    ap.add_argument("--sample", type=int, default=20, help="papers to clone/align")
    ap.add_argument("--levels", default="L0,L1,L2")
    ap.add_argument("--sigma", default="jaccard", choices=["jaccard", "statement", "combined", "embedding"])
    ap.add_argument("--min-nodes", type=int, default=6)
    ap.add_argument("--max-nodes", type=int, default=80)
    ap.add_argument("--llm", default=None)
    args = ap.parse_args()

    paraphraser = None
    if args.llm:
        from llm_paraphrase import make_paraphraser
        paraphraser = make_paraphraser(model=args.llm)

    papers = load_papers(root=args.root, limit=args.papers)
    pool = [p for p in papers if args.min_nodes <= len(p.nodes) <= args.max_nodes]
    rng = random.Random(3)
    rng.shuffle(pool)
    sample = pool[:args.sample]
    print(f"loaded {len(papers)} papers; {len(pool)} in node-range; "
          f"aligning {len(sample)} (sigma={args.sigma})")

    levels = args.levels.split(",")
    for level in levels:
        accs, ctrl = [], []
        for i, p in enumerate(sample):
            clone, gold = clone_perturbed(p, level, seed=i, paraphraser=paraphraser)
            res = align(p, clone, sigma=args.sigma)
            accs.append(alignment_accuracy(res["matching"], gold))
            # negative control: align p against a DIFFERENT paper's clone
            other = sample[(i + 1) % len(sample)]
            oclone, _ = clone_perturbed(other, level, seed=i, paraphraser=paraphraser)
            rc = align(p, oclone, sigma=args.sigma)
            # accuracy of matching p's nodes to their true clone ids (all wrong here)
            ctrl.append(alignment_accuracy(rc["matching"], gold))
        mean = sum(accs) / max(1, len(accs))
        cmean = sum(ctrl) / max(1, len(ctrl))
        print(f"  {level}: mean matching accuracy = {mean:.3f}   "
              f"(negative control = {cmean:.3f})")


if __name__ == "__main__":
    main()
