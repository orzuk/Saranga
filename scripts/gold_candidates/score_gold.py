#!/usr/bin/env python3
"""Extract the gold papers and blueprints with the free extractors and score them against the gold.

  author      corpus/gold_candidates/papers/<id>: the paper's LaTeX -> <extractor>.json, scored against
              gold.json (graph_score preset 'author'); the good diagrams of index.json
  blueprint   corpus/gold_blueprints/<id>: the blueprint without \\uses, \\lean, \\leanok, \\proves -> blueprint.tex
              -> <extractor>.json, scored against graph.json (presets 'blueprint' and 'blueprint_uses');
              human or mixed blueprints with proofs, not degenerate

Per item: scores.json ({extractor: {preset: counts and P/R/F1}}). Per set: scores_summary.json, pooled over
items with 95% bootstrap intervals (items resampled). The portals show both.

    score_gold.py [--sets author,blueprint] [--extractors rules,tagger] [--jobs 6] [--redo]
"""
import argparse
import json
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src"), str(Path(__file__).resolve().parent)]
import graph_score as GS                                # noqa: E402

EXTRACTORS = {"rules": REPO / "extractors/rules/silver_v6__sentence_rules_haiku__2026-10",
              "tagger": REPO / "extractors/rules/silver_v6__sentence_tagger__2026-10"}
SETS = {"author": (REPO / "corpus/gold_candidates", "papers", "gold.json", ("author", "author_inv")),
        "blueprint": (REPO / "corpus/gold_blueprints", "", "graph.json", ("blueprint", "blueprint_uses", "blueprint_inv"))}
_ENVS = ("theorem", "lemma", "proposition", "corollary", "definition", "remark", "example", "claim", "conjecture",
         "notation", "assumption", "question", "problem", "fact")


def items(name):
    root, sub, _, _ = SETS[name]
    index = json.loads((root / "index.json").read_text())
    if name == "author":
        return [root / sub / r["id"] for r in index if r["good"]]
    out = []
    for r in index:
        m = root / r["id"] / "meta.json"
        if m.is_file() and r.get("provenance") in ("human", "mixed"):
            m = json.loads(m.read_text())
            out += [root / r["id"]] if m.get("n_proofs") and not m.get("degenerate") else []
    return out


def blueprint_tex(d: Path) -> Path:
    """The blueprint as a paper: its compiled LaTeX without the Lean markers, in a document with the usual
    theorem environments (blueprints declare them in a macro file of their own)."""
    import blueprint_to_graph as B
    t = re.sub(r"\\(?:uses|lean|proves|discussion)\s*\{(?:[^{}]|\{[^{}]*\})*\}|\\(?:leanok|mathlibok|notready)\b", "",
               B.compiled((d / "all.tex").read_text(encoding="utf-8", errors="replace")))
    f = d / "blueprint.tex"
    f.write_text("\\documentclass{article}\n\\usepackage{amsthm}\n"
                 + "".join(f"\\newtheorem{{{e}}}{{{e.capitalize()}}}\n" for e in _ENVS)
                 + "\\begin{document}\n" + t + "\n\\end{document}\n", encoding="utf-8")
    return f


def direction(gold, rules):
    """Which way a diagram's arrows point, judged by the paper's own references (the rule-based graph's
    dependencies between the drawn results, through any path): (verdict, arrows agreeing, arrows reversed).
    reversed: at least 2 judged arrows and twice as many backwards as forwards; mixed: both, not decisively;
    forward; unknown: fewer than 2 arrows judged. One decision per diagram, never per arrow."""
    gn, pn = GS._with_labels(gold), GS._with_labels(rules)
    p2g = {pn[i]["id"]: gn[j]["id"] for i, (j, _) in GS.match_nodes(pn, gn, "m1g", "label").items()}
    reach = GS._implied({(p2g[a], p2g[b]) for a, b in GS.dependencies(
        pn, rules["edges"], {n["id"] for n in pn if n.get("type") not in GS._NOT_RESULTS}) if a in p2g and b in p2g})
    fwd = sum((e["source"], e["target"]) in reach for e in gold["edges"])
    back = sum((e["target"], e["source"]) in reach for e in gold["edges"])
    return ("unknown" if fwd + back < 2 else "reversed" if back >= 2 * max(1, fwd) else
            "mixed" if back and fwd < 2 * back else "forward"), fwd, back


def one(job):
    name, d, extractors, redo = job
    from math_paper_parser import parse_to_unified
    _, _, gold_file, presets = SETS[name]
    gold = json.loads((d / gold_file).read_text())
    if name == "author":
        rules_f = d / "rules.json"
        if redo or not rules_f.is_file():
            rules_f.write_text((d / "full.json").read_text())
        # the arrows' direction: the reviewer's answer, else detected from the paper's own references
        verdict, fwd, back = direction(gold, json.loads(rules_f.read_text()))
        review = json.loads((d / "review.json").read_text()) if (d / "review.json").is_file() else {}
        said = {"B uses A (reversed)": "reversed", "A used for B": "forward"}.get(review.get("arrow_meaning"))
        flip = (said or verdict) == "reversed"
        if flip:
            gold["edges"] = [dict(e, source=e["target"], target=e["source"]) for e in gold["edges"]]
        meta = json.loads((d / "meta.json").read_text())
        meta["direction"] = {"detected": verdict, "agree": fwd, "reversed": back, "reviewer": said, "scored_reversed": flip}
        (d / "meta.json").write_text(json.dumps(meta, indent=1))
    out = {}
    for x in extractors:
        f = d / f"{x}.json"
        if redo or not f.is_file():
            if name == "author" and x == "rules" and (d / "full.json").is_file():
                f.write_text((d / "full.json").read_text())        # the review pages' extraction, same rule set
            else:
                tex = d / "paper.tex" if name == "author" else blueprint_tex(d)
                f.write_text(json.dumps(parse_to_unified(str(tex), d.name, str(EXTRACTORS[x]))))
        pred = json.loads(f.read_text())
        out[x] = {p: (c := GS.score(pred, gold, **GS.PRESETS[p])) | GS.pooled([c]) for p in presets}
    (d / "scores.json").write_text(json.dumps(out, indent=1))
    return d.name, out


def summary(results, extractors, presets, n_boot=1000):
    """Pooled P/R/F1 per extractor and preset, with 95% bootstrap intervals over items."""
    rnd, out = random.Random(0), {}
    ids = sorted(results)
    for x in extractors:
        for p in presets:
            counts = [{k: v for k, v in results[i][x][p].items() if k.endswith(("_credit", "_n"))} for i in ids]
            point = GS.pooled(counts)
            boots = [GS.pooled([counts[rnd.randrange(len(ids))] for _ in ids]) for _ in range(n_boot)]
            ci = {k: [sorted(b.get(k, 0) for b in boots)[int(.025 * n_boot)], sorted(b.get(k, 0) for b in boots)[int(.975 * n_boot) - 1]]
                  for k in point if not k.endswith("_n_gold")}
            out[f"{x}/{p}"] = {"n_items": len(ids), **point, "ci95": ci}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="author,blueprint")
    ap.add_argument("--extractors", default="rules,tagger")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    ex = a.extractors.split(",")
    for name in a.sets.split(","):
        jobs = [(name, d, ex, a.redo) for d in items(name)]
        with ProcessPoolExecutor(a.jobs) as pool:
            results = dict(pool.map(one, jobs))
        s = summary(results, ex, SETS[name][3])
        (SETS[name][0] / "scores_summary.json").write_text(json.dumps(s, indent=1))
        print(f"{name}: {len(results)} items")
        for k, v in s.items():
            print(f"  {k:24s} nodes P/R/F1 {v['node_P']:.3f}/{v['node_R']:.3f}/{v['node_F1']:.3f}   "
                  f"deps P/R/F1 {v['edge_P']:.3f}/{v['edge_R']:.3f}/{v['edge_F1']:.3f}"
                  + (f"   R on definitions {v['edge_R_def']:.3f}, on results {v['edge_R_res']:.3f}" if "edge_R_def" in v else ""))


if __name__ == "__main__":
    main()
