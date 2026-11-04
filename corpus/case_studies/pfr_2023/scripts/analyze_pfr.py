"""Case-study analysis of the PFR paper graphs (LLM v7, rules alg3) against the Lean blueprint."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
REPO = Path("/mnt/c/Code/Github/Saranga")
sys.path[:0] = [str(REPO / "src"), str(REPO / "scripts/gold_candidates")]
import networkx as nx
import latex_facts
import score_bp_papers as SB
import graph_score as GS

C = REPO / "corpus/case_studies/pfr_2023"
BP = REPO / "corpus/gold_blueprints/teorth__pfr"
LLM = json.loads((REPO / "corpus/silver/opus-5.5__v7_cases/pfr_2023.json").read_text())
RUL = json.loads((C / "pfr_2023_rules.json").read_text())
BPG = json.loads((BP / "graph.json").read_text())
RES = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"}


def results_view(g, res=RES):
    """Fold every node into the result it belongs to (an equation or step into its container,
    a proof into the result it proves); keep result->result dependencies (mentions dropped)."""
    nodes = {n["id"]: n for n in g["nodes"]}
    proves = {}
    for e in g["edges"]:
        if e["type"] == "proves" and not e.get("alternative"):
            proves.setdefault(e["source"], e["target"])

    def owner(x, seen=()):
        while x in nodes and x not in seen:
            n = nodes[x]
            if n["type"] in res:
                return x
            if n["type"] == "proof":
                return proves.get(x)
            seen = seen + (x,)
            x = n.get("parent_id")
        return None
    G = nx.DiGraph()
    for n in g["nodes"]:
        if n["type"] in res:
            G.add_node(n["id"])
    for e in g["edges"]:
        if e.get("mention") or e["type"] in ("proves", "grounded_to", "resolves"):
            continue
        a, b = owner(e["source"]), owner(e["target"])
        if a and b and a != b:
            G.add_edge(a, b)
    return G, nodes


def depth_to(G, target):
    anc = nx.ancestors(G, target) | {target}
    H = G.subgraph(anc)
    if not nx.is_directed_acyclic_graph(H):
        H = H.copy()
        for c in nx.simple_cycles(H):
            H.remove_edge(c[-1], c[0])
    return nx.dag_longest_path(H), anc


def label_name(n):
    return f"{n.get('display', n['type']).title()} {n['number']}" if n.get("number") else n.get("name")


out = {}
# ------------------------------------------------------------------ LLM graph
G, N = results_view(LLM)
main = "TP5"
path, anc = depth_to(G, main)
path9, anc9 = depth_to(G, "TP9")
H = G.subgraph(anc)
fan = {x: len(nx.descendants(H, x)) for x in H}
outdeg = {x: H.out_degree(x) for x in H}
out["llm"] = {
    "nodes": len(LLM["nodes"]), "edges": len(LLM["edges"]),
    "node_types": Counter(n["type"] for n in LLM["nodes"]), "edge_types": Counter(e["type"] for e in LLM["edges"]),
    "edge_basis": Counter(e.get("basis") for e in LLM["edges"]),
    "results_view": {"results": G.number_of_nodes(), "edges": G.number_of_edges(),
                     "ancestors_of_main": len(anc) - 1, "longest_chain": [(x, label_name(N[x])) for x in path]},
    "most_used_in_main_chain": sorted(((fan[x], outdeg[x], x, label_name(N[x]), N[x]["name"]) for x in H if x != main), reverse=True)[:12],
}
# ------------------------------------------------------------------ rules graph
GR, NR = results_view(RUL)
rmain = next(n["id"] for n in RUL["nodes"] if n.get("label") == "pfr")
rpath, ranc = depth_to(GR, rmain)
out["rules"] = {"nodes": len(RUL["nodes"]), "edges": len(RUL["edges"]),
                "node_types": Counter(n["type"] for n in RUL["nodes"]), "edge_types": Counter(e["type"] for e in RUL["edges"]),
                "results_view": {"results": GR.number_of_nodes(), "edges": GR.number_of_edges(),
                                 "ancestors_of_main": len(ranc) - 1, "longest_chain": rpath,
                                 "edges_list": sorted(GR.edges())}}
# LLM vs rules: result nodes matched by LaTeX label, edges among them compared
lab_l = {n["id"]: n.get("label") for n in LLM["nodes"] if n.get("label")}
lab_r = {n["id"]: n.get("label") for n in RUL["nodes"] if n.get("label")}
El = {(lab_l.get(a), lab_l.get(b)) for a, b in G.edges() if lab_l.get(a) and lab_l.get(b)}
Er = {(lab_r.get(a), lab_r.get(b)) for a, b in GR.edges() if lab_r.get(a) and lab_r.get(b)}
out["llm_vs_rules"] = {"labelled_result_edges_llm": len(El), "labelled_result_edges_rules": len(Er),
                       "common": sorted(El & Er), "llm_only": sorted(El - Er), "rules_only": sorted(Er - El),
                       "llm_unlabelled_results": sorted((x, N[x]["name"]) for x in G if x not in lab_l),
                       "rules_unlabelled_results": sorted((x, NR[x].get("name")) for x in GR if x not in lab_r)}
# ------------------------------------------------------------------ blueprint
tex = latex_facts.read_tex(str(latex_facts.find_main_tex(BP / "paper/source")))
bres = [n for n in BPG["nodes"] if n.get("type") not in GS._NOT_RESULTS]
GB, NB = results_view(BPG, RES)
bmain = next(n["id"] for n in BPG["nodes"] if n.get("label") == "pfr")
bpath, banc = depth_to(GB, bmain)
bfan = {x: len(nx.descendants(GB.subgraph(banc), x)) for x in banc}
out["blueprint"] = {"nodes": len(BPG["nodes"]), "edges": len(BPG["edges"]), "results": len(bres),
                    "results_view_edges": GB.number_of_edges(), "main": (bmain, NB[bmain]["name"]),
                    "ancestors_of_main": len(banc) - 1, "longest_chain": [(x, NB[x].get("name"), NB[x].get("label")) for x in bpath],
                    "most_used": sorted(((bfan[x], x, NB[x].get("name"), NB[x].get("label")) for x in banc if x != bmain), reverse=True)[:12],
                    "sections_of_main_chain": Counter(NB[x].get("section") for x in banc)}
for name, g, gv, ancP in (("llm", LLM, G, anc), ("rules", RUL, GR, ranc)):
    a, by_num = SB.align(bres, g, tex, 0.5)
    inv = {p: b for b, p in a.items()}
    core_al = [b for b in banc if b in a]
    aligned_in_main = [b for b in core_al if a[b] in ancP]
    # blueprint dependencies among core statements that are aligned on both ends
    bE = {(x, y) for x, y in GB.subgraph(banc).edges() if x in a and y in a}
    pE = {(a[x], a[y]) for x, y in bE}
    hit = {(x, y) for x, y in bE if gv.has_edge(a[x], a[y]) or (a[x] in gv and a[y] in gv and nx.has_path(gv, a[x], a[y]))}
    out[f"bp_vs_{name}"] = {
        "aligned_total": len(a), "aligned_by_number": by_num, "blueprint_core_statements": len(banc),
        "core_aligned": len(core_al), "core_aligned_and_in_paper_main_chain": len(aligned_in_main),
        "core_unaligned": sorted((x, NB[x].get("name"), NB[x].get("label"), NB[x].get("section")) for x in banc if x not in a),
        "core_edges_both_aligned": len(bE), "recovered_direct_or_path": len(hit),
        "alignment": sorted((b, NB[b].get("name") if b in NB else None, p,
                             (g_nodes := {n["id"]: n for n in g["nodes"]})[p].get("name")) for b, p in a.items()),
    }
json.dump(out, open(C / "analysis.json", "w"), indent=1, default=list)

# ------------------------------------------------------------------ compact results view for a slide (LLM graph)
keep = set(anc) | {"TP7", "CP1", "CP2", "CP3", "CP4", "CnjP1"}
keep = {x for x in keep if N[x].get("rigor") != "heuristic"}
V = G.subgraph(keep)
lvl = {}
for x in nx.topological_sort(V):
    lvl[x] = max((lvl[p] + 1 for p in V.predecessors(x)), default=0)
slide = {"metadata": {"title": "On a conjecture of Marton (PFR), results view", "arxiv_id": "2311.05762",
                      "source_graph": "corpus/silver/opus-5.5__v7_cases/pfr_2023.json",
                      "view": "results (theorem/lemma/proposition/corollary/claim) and their dependencies; proofs folded into the result they prove, equations and steps into their container, mentions dropped",
                      "edge_convention": "A -> B: B depends on A", "main": [main, "TP9"]},
         "nodes": [{"id": x, "type": N[x]["type"], "name": N[x]["name"], "number": N[x].get("number"),
                    "label": N[x].get("label"), "origin": N[x]["origin"], "main": bool(N[x].get("main")),
                    "level": lvl[x], "used_by_n_results": len(nx.descendants(V, x)),
                    "statement_short": N[x].get("statement_short")} for x in sorted(V, key=lambda k: (lvl[k], k))],
         "edges": [{"source": a, "target": b, "type": "uses"} for a, b in sorted(V.edges())]
                  + [{"source": e["source"], "target": e["target"], "type": "resolves"} for e in LLM["edges"]
                     if e["type"] == "resolves" and e["source"] in V and e["target"] in V],
         "longest_chain_to_main": [x for x in path]}
json.dump(slide, open(C / "results_view.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: (v if k not in ("llm_vs_rules",) else {kk: vv for kk, vv in v.items()}) for k, v in out.items()}, indent=1, default=list)[:20000])
