#!/usr/bin/env python3
"""TheoremGraph (Kurgan et al., arXiv:2606.25363; uw-math-ai/math-graph) as an extractor on SARANGA's gold
sets: its statements and within-paper dependencies of each gold paper and blueprint, written as
<gold dir>/theoremgraph.json (every method) and theoremgraph_det.json (its deterministic edges only), so
score_gold.py --extractors theoremgraph,theoremgraph_det scores them like the others.

    theoremgraph_preds.py tg_gold.json      (made on the cluster by tg_extract.py from the CSVs)

TheoremGraph withholds the text of papers without an open licence, so a statement is matched to the gold
by its LaTeX \\label, or, when it has none, by its printed number through the paper's own labels
(latex_facts: number -> environment -> its \\label). An edge src -> dep ("src refers to dep") becomes the
canonical dep -> src (src depends on dep).
"""
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src"), str(Path(__file__).resolve().parent)]
import node_types as NT                                   # noqa: E402
import score_gold as SG                                   # noqa: E402


def facts_labels(tex: Path) -> dict:
    """{(env, number): [labels]} and {number: [labels]} of a LaTeX source's numbered environments."""
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "facts.json"
        subprocess.run([sys.executable, str(REPO / "src/latex_facts.py"), str(tex), "--out", str(out)],
                       capture_output=True, timeout=600)
        if not out.is_file():
            return {}
        d = json.loads(out.read_text())
    by_kind, by_num = {}, defaultdict(list)
    for f in d.get("facts") or []:
        if f.get("number") and f.get("labels"):
            by_kind[(str(f.get("env") or "").lower(), str(f["number"]))] = list(f["labels"])
            by_num[str(f["number"])].append(list(f["labels"]))
    return {"kind": by_kind, "num": {k: v[0] for k, v in by_num.items() if len(v) == 1}}


def graph(stmts: dict, edges: list, fl: dict, deterministic: bool) -> dict:
    nodes = []
    for sid, s in sorted(stmts.items(), key=lambda kv: int(kv[1].get("ordinal") or 0)):
        kind, ref = (s.get("kind") or "").lower(), (s.get("ref") or "").strip()
        t = NT.normalize_node_type(kind)
        t = t if t in NT.SUBCLASS_VALUES else NT.REMARK
        labels = [s["label"]] if s.get("label") else (fl.get("kind", {}).get((kind, ref)) or fl.get("num", {}).get(ref) or [])
        nodes.append({"id": sid, "type": t, "name": f"{kind.capitalize()} {ref}".strip(), "statement": s.get("body") or "",
                      "labels": labels, **({"label": labels[0]} if labels else {})})
    ids = {n["id"] for n in nodes}
    seen, out = set(), []
    for e in edges:
        methods = e.get("methods") or ""
        if deterministic and "deterministic" not in methods:
            continue
        src, dep = e.get("src_id"), e.get("dep_id")
        if src in ids and dep in ids and src != dep and (dep, src) not in seen:
            seen.add((dep, src))
            out.append({"source": dep, "target": src, "type": "uses"})
    return {"metadata": {"source": "TheoremGraph (uw-math-ai/math-graph)", "deterministic_only": deterministic},
            "nodes": nodes, "edges": out}


def main():
    tg = json.loads(Path(sys.argv[1]).read_text())
    by_key = {(p["kind"], p["key"].lower()): pid for pid, p in tg["papers"].items()}
    stmts = defaultdict(dict)
    for sid, s in tg["statements"].items():
        stmts[s["paper_id"]][sid] = s
    edges = defaultdict(list)
    for e in tg["edges"]:
        pid = tg["statements"][e["src_id"]]["paper_id"]
        edges[pid].append(e)
    bp_index = {r["id"]: r for r in json.loads((REPO / "corpus/gold_blueprints/index.json").read_text())}
    found = missing = 0
    for name in ("author", "blueprint"):
        for d in SG.items(name):
            if name == "author":
                pid, tex = by_key.get(("arxiv", re.sub(r"v\d+$", "", d.name).lower())), d / "paper.tex"
            else:
                slug = (bp_index.get(d.name, {}).get("repo") or "").split("/")[-1].lower()
                pid, tex = by_key.get(("blueprint", slug)), SG.blueprint_tex(d)
            if not pid or not stmts.get(pid):
                missing += 1
                for x in ("theoremgraph", "theoremgraph_det"):
                    (d / f"{x}.json").write_text(json.dumps({"metadata": {"source": "TheoremGraph", "absent": True},
                                                             "nodes": [], "edges": []}))
                continue
            found += 1
            fl = facts_labels(tex)
            for x, det in (("theoremgraph", False), ("theoremgraph_det", True)):
                (d / f"{x}.json").write_text(json.dumps(graph(stmts[pid], edges[pid], fl, det)))
    print(f"{found} gold items in TheoremGraph, {missing} absent (scored as empty)")


if __name__ == "__main__":
    main()
