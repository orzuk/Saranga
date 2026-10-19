#!/usr/bin/env python3
"""Score the v7 gold-author extractions against the authors' diagrams, with an error breakdown.

    python3 docs/v7_handoff/gold_eval_v7.py [--out docs/v7_handoff/gold_eval_v7.json]

Per paper and pooled (95% bootstrap over papers): node P/R, edge P/R/F1 (graph_score preset
'author', diagram direction as scored by score_gold.py), for v7 and the rule-based extractor.
Breakdown of the diagram arrows v7 misses: reversed (v7 has the opposite dependency), endpoint
unmatched (a box matched to no v7 node), and missed between matched results; and of v7's extra
dependencies among drawn results.
"""
import argparse
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src/LLMVersion"), str(REPO / "src")]
import graph_score as GS  # noqa: E402

PAPERS = REPO / "corpus/gold_candidates/papers"
V7 = REPO / "corpus/silver/opus-5.5__v7_gold"
K = ("node_P", "node_R", "edge_P", "edge_R", "edge_F1")


def gold_of(d):
    gold = json.loads((d / "gold.json").read_text())
    meta = json.loads((d / "meta.json").read_text())
    if meta.get("direction", {}).get("scored_reversed"):
        gold["edges"] = [dict(e, source=e["target"], target=e["source"]) for e in gold["edges"]]
    return gold


def breakdown(pred, gold):
    """The arrows behind the edge scores, by kind of error."""
    gn, pn = GS._with_labels(gold), GS._with_labels(pred)
    gn = [n for n in gn if not {"section", "non_result"} & set(n.get("tags") or [])]
    m = GS.match_nodes(pn, gn, "m1g", "label")
    p2g = {pn[i]["id"]: gn[j]["id"] for i, (j, _) in m.items()}
    gres = {n["id"] for n in gn if n.get("type") not in GS._NOT_RESULTS}
    gdep = GS.dependencies(gn, gold["edges"], gres)
    presults = {n["id"] for n in pn if n.get("type") not in GS._NOT_RESULTS}
    pdep = {(p2g[a], p2g[b]) for a, b in GS.dependencies(pn, pred["edges"], presults)
            if p2g.get(a) in gres and p2g.get(b) in gres}
    found, gclose = GS._implied(pdep), GS._implied(gdep)
    matched = set(p2g.values())
    missed = gdep - found
    label = {n["id"]: (n.get("label") or n.get("name") or n["id"]) for n in gn}
    return {
        "gold_boxes": len(gn), "boxes_unmatched": [label[n["id"]] for n in gn if n["id"] not in matched],
        "arrows": len(gdep),
        "missed_reversed": [(label[a], label[b]) for a, b in missed if (b, a) in found],
        "missed_unmatched_end": [(label[a], label[b]) for a, b in missed if a not in matched or b not in matched],
        "missed_other": [(label[a], label[b]) for a, b in missed
                         if a in matched and b in matched and (b, a) not in found],
        "extra": [(label[a], label[b]) for a, b in pdep - gclose],
    }


def boot(counts, n=1000, seed=0):
    rnd = random.Random(seed)
    pts = [GS.pooled([counts[rnd.randrange(len(counts))] for _ in counts]) for _ in range(n)]
    return {k: [round(sorted(p[k] for p in pts)[int(.025 * n)], 3), round(sorted(p[k] for p in pts)[int(.975 * n) - 1], 3)]
            for k in K}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=str(REPO / "docs/v7_handoff/gold_eval_v7.json"))
    a = ap.parse_args()
    ids = sorted(p.stem for p in V7.glob("*.json"))
    rows, cv, cr = [], [], []
    for i in ids:
        d = PAPERS / i
        gold = gold_of(d)
        pred = json.loads((V7 / f"{i}.json").read_text())
        c = GS.score(pred, gold, **GS.PRESETS["author"])
        r = GS.score(json.loads((d / "rules.json").read_text()), gold, **GS.PRESETS["author"])
        cv.append(c)
        cr.append(r)
        rows.append({"paper": i, "v7": {k: round(GS.pooled([c])[k], 3) for k in K},
                     "rules": {k: round(GS.pooled([r])[k], 3) for k in K}, **breakdown(pred, gold)})
    summary = {x: {"pooled": {k: round(GS.pooled(c)[k], 3) for k in K}, "ci95": boot(c)}
               for x, c in (("v7", cv), ("rules", cr))}
    tot = {k: sum(len(r[k]) for r in rows) for k in ("missed_reversed", "missed_unmatched_end", "missed_other", "extra")}
    tot["arrows"] = sum(r["arrows"] for r in rows)
    tot["boxes"], tot["boxes_unmatched"] = sum(r["gold_boxes"] for r in rows), sum(len(r["boxes_unmatched"]) for r in rows)
    Path(a.out).write_text(json.dumps({"papers": len(ids), "summary": summary, "errors": tot, "per_paper": rows}, indent=1))
    print(f"{len(ids)} papers")
    for x, s in summary.items():
        print(x, " ".join(f"{k}={v}" for k, v in s["pooled"].items()), " CI", s["ci95"]["edge_F1"])
    print("errors:", tot)
    for r in sorted(rows, key=lambda r: r["v7"]["edge_F1"]):
        print(f"{r['paper']:12s} v7 F1 {r['v7']['edge_F1']:.2f} (P {r['v7']['edge_P']:.2f} R {r['v7']['edge_R']:.2f})"
              f"  rules {r['rules']['edge_F1']:.2f}  arrows {r['arrows']:3d} rev {len(r['missed_reversed'])}"
              f" unm {len(r['missed_unmatched_end'])} miss {len(r['missed_other'])} extra {len(r['extra'])}"
              f" boxes_unmatched {len(r['boxes_unmatched'])}/{r['gold_boxes']}")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
