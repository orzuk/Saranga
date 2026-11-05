#!/usr/bin/env python3
"""One graph of the paper and its Lean blueprint.

The paper's LLM graph is kept whole. Every statement of the blueprint's core (the ancestors of
its main theorem, proofs folded) is added as a node with `lean: {label, status, names}`:
  status node / inside -> placed inside the paper node that states it (`inside`), the result a
                          proof belongs to when the hand alignment points at a proof;
  status implicit      -> a statement the paper never writes down (folklore), apart;
  status cited         -> a cited result the blueprint had to prove, apart.
Blueprint dependencies among core statements are edges with `lean: 1`. An edge is `mismatch: 1`
when the other side has no counterpart: a Lean dependency between two paper results with no
paper path between them, or a paper dependency between two results whose Lean statements have
no Lean path.

    python3 merge_lean.py  ->  ../pfr_2023_lean.json
"""
import json, re, sys
from pathlib import Path
import networkx as nx

HERE = Path(__file__).resolve().parent
C = HERE.parent
REPO = C.parents[2]
PAPER = REPO / "corpus/silver/opus-5.5__v7_cases/pfr_2023.json"
BLUEPRINT = REPO / "corpus/gold_blueprints/teorth__pfr/graph.json"
OUT = C / "pfr_2023_lean.json"


def hand_alignment():
    """The M table of manual_align.py: blueprint label -> (status, paper node or None, note)."""
    src = (HERE / "manual_align.py").read_text(encoding="utf-8")
    i = src.index("M = {")
    depth, j = 0, i + 4
    for j in range(i + 4, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            break
    return eval(src[i + 4:j + 1])


def main():
    paper = json.loads(PAPER.read_text(encoding="utf-8"))
    bp = json.loads(BLUEPRINT.read_text(encoding="utf-8"))
    M = hand_alignment()
    pn = {n["id"]: n for n in paper["nodes"]}
    proves = {e["source"]: e["target"] for e in paper["edges"] if e["type"] == "proves"}

    def host(x):                      # the result a paper node belongs to: a step or equation -> its
        seen = set()                  # container, a proof -> what it proves
        while x in pn and pn[x].get("parent_id") and x not in seen:
            seen.add(x)
            x = pn[x]["parent_id"]
        if x in pn and pn[x]["type"] == "proof":
            return proves.get(x, x)
        return x

    # blueprint, proofs folded into what they prove; the core = ancestors of `pfr`
    BN = {n["id"]: n for n in bp["nodes"]}
    bproves = {e["source"]: e["target"] for e in bp["edges"] if e["type"] == "proves"}
    own = lambda x: bproves.get(x) if BN[x]["type"] == "proof" else x
    GB = nx.DiGraph()
    for e in bp["edges"]:
        if e["type"] != "proves":
            a, b = own(e["source"]), own(e["target"])
            if a and b and a != b:
                GB.add_edge(a, b)
    main_id = next(n["id"] for n in bp["nodes"] if n.get("label") == "pfr")
    core = nx.ancestors(GB, main_id) | {main_id}
    by_label = {BN[i].get("label"): i for i in core}

    # paper, result level: every edge lifted to results (proofs -> what they prove)
    GP = nx.DiGraph()
    GP.add_nodes_from(pn)
    for e in paper["edges"]:
        if e.get("mention"):
            continue
        a, b = host(e["source"]), host(e["target"])
        if a and b and a != b and a in pn and b in pn:
            GP.add_edge(a, b)

    lean_nodes, lid, placed = [], {}, {}
    for bid in sorted(core, key=lambda i: (BN[i].get("section") or "", BN[i].get("label") or "")):
        n = BN[bid]
        label = n.get("label") or bid
        status, target, note = M.get(label, ("unaligned", None, "not in the hand alignment"))
        node_id = "LN_" + re.sub(r"[^A-Za-z0-9]+", "_", label)
        lid[bid] = node_id
        inside = host(target) if target else ""
        if inside and inside not in pn:
            inside = ""
        names = n.get("lean_names")
        if isinstance(names, str):
            try:
                names = eval(names)
            except Exception:
                names = [names]
        rec = {
            "id": node_id, "type": n["type"], "name": label,
            "statement": n.get("statement") or "", "origin": "paper",
            "section": n.get("section") or "", "label": "",
            "lean": {"label": label, "status": status, "names": names or [],
                     "paper_node": target or "", "note": note},
        }
        if inside:
            rec["inside"] = inside
            rec["parent_id"] = target          # what the viewer's builder reads (a proof resolves to its result)
            placed.setdefault(inside, []).append(node_id)
        lean_nodes.append(rec)

    # Lean edges among core statements; mismatch when the paper has no path between the hosts
    lean_edges, lean_pairs = [], set()
    frame_of = {r["id"]: r.get("inside") for r in lean_nodes}
    for a, b in GB.edges():
        if a in core and b in core:
            ea, eb = lid[a], lid[b]
            fa, fb = frame_of[ea], frame_of[eb]
            x = {"source": ea, "target": eb, "type": "uses", "lean": 1, "confidence": 1.0}
            if fa and fb and fa != fb:
                lean_pairs.add((fa, fb))
                if not nx.has_path(GP, fa, fb):
                    x["mismatch"] = 1
            lean_edges.append(x)
    # paper edges between two results that both hold Lean statements, with no Lean path
    GL = nx.DiGraph(((lid[a], lid[b]) for a, b in GB.edges() if a in core and b in core))
    GL.add_nodes_from(lid.values())
    paper_edges = []
    for e in paper["edges"]:
        e = dict(e)
        a, b = host(e["source"]), host(e["target"])
        if a in placed and b in placed and a != b and not e.get("mention"):
            if not any(nx.has_path(GL, x, y) for x in placed[a] for y in placed[b]):
                e["mismatch"] = 1
        paper_edges.append(e)

    md = dict(paper.get("metadata", {}))
    md["title"] = md.get("title", "") + " — with the Lean blueprint (teorth/pfr)"
    md["lean_blueprint"] = {"project": "teorth/pfr", "core_statements": len(core),
                            "status_counts": {s: sum(1 for r in lean_nodes if r["lean"]["status"] == s)
                                              for s in ("node", "inside", "implicit", "cited", "unaligned")},
                            "lean_edges": len(lean_edges),
                            "lean_edges_mismatch": sum(1 for x in lean_edges if x.get("mismatch")),
                            "paper_edges_mismatch": sum(1 for x in paper_edges if x.get("mismatch"))}
    out = {"metadata": md, "nodes": paper["nodes"] + lean_nodes, "edges": paper_edges + lean_edges}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(md["lean_blueprint"], indent=1))
    print("hosts with Lean statements:", len(placed), "; most:", sorted(((len(v), k) for k, v in placed.items()), reverse=True)[:6])


if __name__ == "__main__":
    main()
