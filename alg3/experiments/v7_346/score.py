"""Scores of the v7 346-paper experiment, per evaluation subset.

    python3 alg3/experiments/v7_346/score.py [--split test]

E-S = 40 silver test papers, E-G = 28 gold-author test papers, E-A = all 68 (labels: v7).
E-D = the 28 gold-author test papers against the AUTHORS' diagrams (graph_score preset 'author').
Nodes: m1g pooled, from runs/compare/v7_346_alg3/results/per_paper.csv (compare_distillers).
Edges: Level-1 edge F1 (src/LLMVersion/edge_metrics.py) on the parsed graphs in alg3/runs/v7_346/graphs/.
95% intervals: paper bootstrap (1000); paired for the differences.
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path[:0] = [str(REPO / "src/LLMVersion"), str(REPO / "src"), str(REPO / "alg3")]
import edge_metrics as EM          # noqa: E402
import graph_score as GS           # noqa: E402

C = REPO / "alg3/cache/v7_346"
G = REPO / "alg3/runs/v7_346/graphs"
NODE_ARMS = ["base", "units_v6", "alg3_v6", "alg3_TS", "alg3_TG", "alg3_TA"]
EDGE_ARMS = [("base", "base"), ("units_v6", "units"), ("units_v6+stack", "units+stack"),
             ("alg3_v6", "release_v2b"), ("alg3_v6+stack", "release_v2b+stack"),
             ("alg3_TS+edges", "T-S+edges"), ("alg3_TG+edges", "T-G+edges"), ("alg3_TA+edges", "T-A+edges"),
             ("alg3_TA+allpairs", "T-A+allpairs"), ("alg3_TA+allpairs_acyclic", "T-A+allpairs_acyclic"),
             ("alg3_TA+allpairs_prev", "T-A+allpairs_old")]
PAIRS = [("alg3_TA", "alg3_TS"), ("alg3_TA", "alg3_TG"), ("alg3_TA", "alg3_v6"), ("alg3_TA", "units_v6"),
         ("alg3_TA+edges", "alg3_TS+edges"), ("alg3_TA+edges", "alg3_v6+stack"), ("alg3_TA+edges", "units_v6+stack"),
         ("alg3_TA+allpairs", "alg3_TA+edges"), ("alg3_TA+allpairs", "alg3_v6+stack"),
         ("alg3_TA+allpairs", "alg3_TA+allpairs_prev"), ("alg3_TA+allpairs_acyclic", "alg3_TA+allpairs"),
         ("alg3_TA+allpairs_prev", "alg3_TA+edges"), ("alg3_TA+allpairs_prev", "alg3_v6+stack")]
N_BOOT = 1000


def f1(tp_p, tp_r, n_pred, n_gold):
    p = tp_p / n_pred if n_pred else 0.0
    r = tp_r / n_gold if n_gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def boot(per: dict, pids: list, fn, ref: dict | None = None):
    rnd = random.Random(0)
    xs = []
    for _ in range(N_BOOT):
        s = [pids[rnd.randrange(len(pids))] for _ in pids]
        v = fn(sum((per[p] for p in s), Counter()))
        if ref is not None:
            v -= fn(sum((ref[p] for p in s), Counter()))
        xs.append(v)
    xs.sort()
    return xs[int(.025 * N_BOOT)], xs[int(.975 * N_BOOT) - 1]


def subsets(split):
    rows = list(csv.DictReader(open(C / "split_A.csv")))
    ids = {r["arxiv_id"]: r["source"] for r in rows if r["split"] == split}
    return {"E-S": sorted(p for p, s in ids.items() if s == "silver"),
            "E-G": sorted(p for p, s in ids.items() if s == "gold_author"),
            "E-A": sorted(ids)}


def node_counts(split):
    """arm -> pid -> Counter(tp, tp_recall, n_pred, n_gold), m1g, stratum all, pooled over types."""
    out = defaultdict(lambda: defaultdict(Counter))
    f = REPO / "runs/compare/v7_346_alg3/results/per_paper.csv"
    if not f.is_file():                     # compare_distillers not run here: no node table
        return out
    for r in csv.DictReader(open(f)):
        if r["split"] != split or r["mode"] != "m1g" or r["stratum"] != "all" or r["type"] == "all":
            continue
        c = out[r["arm"]][r["paper_id"]]
        for k in ("tp", "tp_recall", "n_pred", "n_gold"):
            c[k] += float(r[k])
    return out


def edge_counts(pids):
    out = {}
    for arm, d in EDGE_ARMS:
        if not (G / d).is_dir():
            continue
        out[arm] = {}
        for p in pids:                      # keep only what F1 needs: the bootstrap sums these 1000s of times
            c = EM.score_paper(G / d / f"{p}.json", C / "silver" / f"{p}.json")
            out[arm][p] = Counter({k: c[k] for k in ("tp", "pred", "ref")})
    return out


def node_f(c):
    return f1(c["tp"], c["tp_recall"], c["n_pred"], c["n_gold"])[2]


def edge_f(c):
    return EM.prf(c)[2]


def table(title, counts, sets, fn, prf_fn, arms):
    print(f"\n### {title}\n")
    print("| arm | " + " | ".join(f"{s} F1 [95% CI]" for s in sets) + " |")
    print("|---|" + "---|" * len(sets))
    for arm in arms:
        if arm not in counts:
            continue
        cells = []
        for s, pids in sets.items():
            tot = sum((counts[arm][p] for p in pids), Counter())
            p, r, f = prf_fn(tot)
            lo, hi = boot(counts[arm], pids, fn)
            cells.append(f"{f:.3f} [{lo:.3f}, {hi:.3f}] (P {p:.3f} R {r:.3f})")
        print(f"| {arm} | " + " | ".join(cells) + " |")
    print(f"\n{title}, paired differences:\n")
    for a, b in PAIRS:
        if a in counts and b in counts:
            cells = []
            for s, pids in sets.items():
                d = fn(sum((counts[a][p] for p in pids), Counter())) - fn(sum((counts[b][p] for p in pids), Counter()))
                lo, hi = boot(counts[a], pids, fn, counts[b])
                cells.append(f"{s} {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
            print(f"- {a} - {b}: " + "; ".join(cells))


def author_diagrams(pids):
    """E-D: graph_score 'author' preset against the authors' diagrams."""
    papers = REPO / "corpus/gold_candidates/papers"
    import importlib.util
    spec = importlib.util.spec_from_file_location("ge", REPO / "docs/v7_handoff/gold_eval_v7.py")
    ge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ge)
    arms = [(a, G / d) for a, d in EDGE_ARMS] + [("v7 LLM (silver)", C / "silver")]
    print(f"\n### E-D: {len(pids)} gold-author test papers vs the authors' diagrams (graph_score 'author')\n")
    print("| arm | node R | edge P | edge R | edge F1 [95% CI] |\n|---|---|---|---|---|")
    res = {}
    for name, d in arms + [("Or's rules.json", None)]:
        cs = []
        for p in pids:
            gold = ge.gold_of(papers / p)
            f = (papers / p / "rules.json") if d is None else d / f"{p}.json"
            if not f.is_file():
                break
            cs.append(GS.score(json.loads(f.read_text()), gold, **GS.PRESETS["author"]))
        else:
            s, ci = GS.pooled(cs), ge.boot(cs)
            res[name] = cs
            print(f"| {name} | {s['node_R']:.3f} | {s['edge_P']:.3f} | {s['edge_R']:.3f} | "
                  f"{s['edge_F1']:.3f} [{ci['edge_F1'][0]:.3f}, {ci['edge_F1'][1]:.3f}] |")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    a = ap.parse_args()
    sets = subsets(a.split)
    print(f"# v7 346-paper experiment — split {a.split}: " + ", ".join(f"{k} {len(v)}" for k, v in sets.items()))
    nc = node_counts(a.split)
    table("Nodes (m1g, pooled)", nc, sets, node_f,
          lambda c: f1(c["tp"], c["tp_recall"], c["n_pred"], c["n_gold"]), NODE_ARMS)
    ec = edge_counts(sets["E-A"])
    table("Edges (Level-1 edge F1)", ec, sets, edge_f, EM.prf, [a for a, _ in EDGE_ARMS])
    if a.split == "test":
        author_diagrams(sets["E-G"])


if __name__ == "__main__":
    main()
