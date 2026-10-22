#!/usr/bin/env python3
"""SARANGA's extractors against TheoremGraph (arXiv:2606.25363) on the gold items TheoremGraph covers:
edge P/R/F1 with 95% bootstrap CIs over papers, and paired differences against TheoremGraph.

    compare_theoremgraph.py [--out docs/v7_handoff/compare_theoremgraph.json]

Needs <gold dir>/theoremgraph.json and theoremgraph_det.json (theoremgraph_preds.py) and the cached
extractions score_gold.py and the v7 runs wrote (rules.json, ta.json, corpus/silver/opus-5.5__v7_gold,
opus-5.5__v7_blueprint). Author diagrams are scored with preset 'author' in the direction score_gold.py
fixed (meta.json); blueprints with preset 'blueprint' against graph.json.

The blueprint rows do not compare like with like: TheoremGraph keeps a blueprint's \\uses{...} inside the
statement text and its deterministic edges are those annotations, i.e. the gold itself, while SARANGA's
extractors read the blueprint with them removed. Only the author-diagram rows are a fair comparison.
"""
import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src/LLMVersion"), str(REPO / "src")]
import graph_score as GS                                  # noqa: E402

K = ("node_P", "node_R", "edge_P", "edge_R", "edge_F1")
SETS = {"author": (REPO / "corpus/gold_candidates/papers", "gold.json", "author", REPO / "corpus/silver/opus-5.5__v7_gold"),
        "blueprint": (REPO / "corpus/gold_blueprints", "graph.json", "blueprint", REPO / "corpus/silver/opus-5.5__v7_blueprint")}
PRED = {"v7 (LLM)": None, "rules (sentence rules)": "rules.json", "rules (T-A + all-pairs)": "ta.json",
        "TheoremGraph (all edges)": "theoremgraph.json", "TheoremGraph (deterministic)": "theoremgraph_det.json"}


def gold_of(d, f):
    gold = json.loads((d / f).read_text())
    m = d / "meta.json"
    if f == "gold.json" and m.is_file() and json.loads(m.read_text()).get("direction", {}).get("scored_reversed"):
        gold["edges"] = [dict(e, source=e["target"], target=e["source"]) for e in gold["edges"]]
    return gold


def boot(c, n=1000, seed=0):
    r = random.Random(seed)
    pts = sorted(GS.pooled([c[r.randrange(len(c))] for _ in c])["edge_F1"] for _ in range(n))
    return [round(pts[int(.025 * n)], 3), round(pts[int(.975 * n) - 1], 3)]


def paired(a, b, n=1000, seed=0):
    """Pooled edge F1 of a minus b, with a 95% bootstrap CI over the same papers."""
    r = random.Random(seed)
    f = lambda idx, c: GS.pooled([c[i] for i in idx])["edge_F1"]          # noqa: E731
    pts = sorted(f(idx, a) - f(idx, b) for idx in ([r.randrange(len(a)) for _ in a] for _ in range(n)))
    return round(f(range(len(a)), a) - f(range(len(b)), b), 3), [round(pts[int(.025 * n)], 3), round(pts[int(.975 * n) - 1], 3)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(REPO / "docs/v7_handoff/compare_theoremgraph.json"))
    a = ap.parse_args()
    report = {}
    for name, (root, gf, preset, v7dir) in SETS.items():
        ids = sorted(p.stem for p in v7dir.glob("*.json"))
        both = [i for i in ids if (root / i / "theoremgraph.json").is_file()
                and not json.loads((root / i / "theoremgraph.json").read_text())["metadata"].get("absent")]
        counts = {x: [] for x in PRED}
        for i in both:
            d = root / i
            gold = gold_of(d, gf)
            for x, f in PRED.items():
                p = v7dir / f"{i}.json" if f is None else d / f
                counts[x].append(GS.score(json.loads(p.read_text()), gold, **GS.PRESETS[preset]))
        res = {x: {**{k: round(GS.pooled(c)[k], 3) for k in K}, "edge_F1_ci95": boot(c)} for x, c in counts.items()}
        diff = {x: paired(counts[x], counts["TheoremGraph (all edges)"]) for x in PRED if not x.startswith("TheoremGraph")}
        report[name] = {"scored_by_v7": len(ids), "in_theoremgraph": len(both), "results": res,
                        "minus_theoremgraph_edge_F1": diff}
        print(f"\n{name}: {len(both)} of the {len(ids)} scored items are in TheoremGraph")
        for x, r in res.items():
            print(f"  {x:30s} edge P {r['edge_P']:.3f} R {r['edge_R']:.3f} F1 {r['edge_F1']:.3f} {r['edge_F1_ci95']}"
                  f"   node R {r['node_R']:.3f}")
        for x, (v, ci) in diff.items():
            print(f"  {x:30s} - TheoremGraph: {v:+.3f} {ci}")
    Path(a.out).write_text(json.dumps(report, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
