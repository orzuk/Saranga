"""Tally corpus scale: node/edge counts + type histograms. Cluster-ready.

    python discovery_suite/eval_harness/corpus_stats.py --out runs/corpus_stats.json
    # or on the v4 100k:
    python discovery_suite/eval_harness/corpus_stats.py --root $ROOT --out ...
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
if str(_SUITE) not in sys.path:
    sys.path.insert(0, str(_SUITE))

from shared.corpus import load_papers  # noqa: E402

PROBLEM_TYPES = {"conjecture", "open_problem", "problem"}
THEOREM_TYPES = {"theorem", "lemma", "proposition", "corollary"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(_HERE / "runs" / "corpus_stats.json"))
    args = ap.parse_args()

    papers = load_papers(root=args.root, limit=args.limit)
    nt, et = Counter(), Counter()
    n_nodes = n_edges = 0
    for p in papers:
        n_nodes += len(p.nodes); n_edges += len(p.edges)
        for n in p.nodes:
            nt[n.get("type") or "?"] += 1
        for e in p.edges:
            et[e.get("type") or "?"] += 1

    n_papers = len(papers)
    probs = sum(nt[t] for t in PROBLEM_TYPES)
    thms = sum(nt[t] for t in THEOREM_TYPES)
    scale = 100_000 / n_papers if n_papers else 0
    out = {
        "papers": n_papers, "nodes": n_nodes, "edges": n_edges,
        "node_types": dict(nt.most_common()),
        "edge_types": dict(et.most_common()),
        "problems": probs, "theorems": thms,
        "proj_100k": {
            "nodes": round(n_nodes * scale), "edges": round(n_edges * scale),
            "problems": round(probs * scale), "theorems": round(thms * scale),
        },
    }
    outp = Path(args.out); outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=2))
    print(f"papers={n_papers} nodes={n_nodes} edges={n_edges} "
          f"problems={probs} theorems={thms}")
    print("wrote", outp)


if __name__ == "__main__":
    main()
