"""Hand alignment of the blueprint's core (ancestors of 'pfr') to the LLM graph, read off the two texts.
status: node   = a Level-1 node of the LLM graph states it
        inside = the paper states it, but only inside a proof or another node (equation, step, clause)
        cited  = a cited result the paper only applies (no statement)
        implicit = the paper never states it (used silently, or folklore)"""
import json, networkx as nx
from collections import Counter
from pathlib import Path
REPO = Path("/mnt/c/Code/Github/Saranga"); C = REPO / "corpus/case_studies/pfr_2023"
M = {  # blueprint label: (status, LLM node or None, note)
 "lem:100pc": ("node", "LP1", ""), "zero-large": ("cited", None, "inside Tao 2010 Thm 1.11(i), applied in PP4"),
 "sym-zero": ("cited", None, "Tao 2010 Thm 1.11(i)"), "lem:100pc-self": ("cited", None, "Tao 2010 Thm 1.11(i), applied in PP4"),
 "sym-group-def": ("cited", None, "symmetry group, inside Tao 2010"), "sym-group": ("cited", None, "inside Tao 2010"),
 "concave": ("implicit", None, "behind 'by Jensen's inequality'"), "pfr_aux": ("inside", "PP18", "Appendix B covering argument"),
 "pfr": ("node", "TP5", ""), "ruz-cov": ("cited", None, "Tao-Vu Lemma 2.14, applied in PP18"),
 "shear-ent": ("inside", "ClP18", "first display of ClP18"), "ruzsa-diff": ("node", "ClP21", ""),
 "cond-indep-exist": ("inside", "PP17", "conditionally independent trials, introduced in a step"),
 "kv": ("node", "LP6", ""), "cond-dist-fact": ("node", "LP2", ""), "sumset-lower-gen": ("node", "ClP18", ""),
 "entropic-bsg": ("node", "LP7", ""), "first-useful": ("node", "LP3", ""), "sumset-lower": ("node", "ClP20", ""),
 "cond-dist-alt": ("node", "ClP23", ""), "ruzsa-nonneg": ("implicit", None, "d >= 0 never stated"),
 "ruz-copy": ("inside", "DP3", "'depends only on the individual distributions' (sentence after the definition)"),
 "ruzsa-triangle": ("node", "TP16", ""), "neg-ent": ("implicit", None, ""), "independent-exist": ("implicit", None, ""),
 "copy-ent": ("implicit", None, ""), "second-useful": ("node", "LP4", ""), "ruz-dist-def": ("node", "DP3", ""),
 "cond-dist-def": ("node", "DP16", ""), "ruz-indep": ("inside", "DP3", "restated in Appendix A ('recall the definition')"),
 "ruzsa-triangle-improved": ("inside", "PP15", "parenthetical: independence of X and Y not used"),
 "unif-exist": ("implicit", None, ""), "alternative-mutual": ("node", "DP14", ""), "uniform-entropy-II": ("inside", "PP18", "H[U_A] = log|A|"),
 "conditional-independent-def": ("implicit", None, "used in ClP17 and PP17, never defined"), "relabeled-entropy-cond": ("implicit", None, ""),
 "add-entropy": ("node", "DP14", "(A.4)"), "chain-rule": ("node", "TP14", ""), "cond-reduce": ("node", "DP14", "(A.5)"),
 "conditional-vanish": ("node", "ClP17", ""), "uniform-def": ("inside", "TP9", "'U_H denotes the uniform distribution on H'"),
 "relabeled-entropy": ("implicit", None, "'since Z_1 - Z_2 determines pi(Z_1 - Z_2)' etc."), "subadditive": ("implicit", None, ""),
 "conditional-mutual-def": ("node", "DP15", ""), "conditional-entropy-def": ("node", "DP12", ""), "independent-def": ("implicit", None, ""),
 "entropy-comm": ("implicit", None, ""), "alt-submodularity": ("node", "TP15", "(A.7)"), "jensen-bound": ("node", "ClP13", ""),
 "submodularity": ("node", "TP15", ""), "mutual-nonneg": ("node", "DP14", "asserted inside the definition sentence"),
 "cond-trial-ent": ("inside", "PP17", "(A.17)"), "entropy-def": ("implicit", None, "Shannon entropy is never defined"),
 "condition-event-def": ("node", "DP12", "'X|Y=y denotes ...'"), "information-def": ("node", "DP14", ""),
 "conditional-mutual-alt": ("node", "ClP16", "(A.9)"), "bound-conc": ("node", "ClP14", ""), "vanish-entropy": ("node", "DP14", ""),
 "eta-def": ("node", "DP6", ""), "tau-min-def": ("inside", "PP5", "'any minimizer of the functional tau'"),
 "tau-copy": ("inside", "DP7", "sentence after (2.1), not extracted as a node"),
 "tau-min": ("inside", "PP5", "compactness step"), "tau-def": ("node", "DP7", ""), "distance-lower": ("node", "ClP8", ""),
 "cond-distance-lower": ("node", "ClP11", ""), "foursum-bound": ("node", "ClP12", ""), "first-estimate": ("node", "ClP9", ""),
 "first-fibre": ("inside", "PP8", "(5.1)"), "first-cond": ("inside", "PP8", "(5.2)"), "first-upper": ("inside", "PP8", "(5.7)-(5.8) and the two displays before"),
 "first-dist-sum": ("inside", "PP8", "display after (5.1)"), "second-estimate": ("node", "ClP10", ""),
 "second-estimate-aux": ("inside", "PP11", "(6.6)"), "dist-sums": ("inside", "PP11", "(6.5)"),
 "key-ident": ("inside", "PP12", "(7.4)"), "uvw-s": ("inside", "PP12", "(7.2)"), "construct-good-prelim": ("node", "LP5", "Lemma 7.2 (its proof's (7.7))"),
 "total-dist": ("inside", "PP12", "(7.3)"), "de-prop": ("node", "PrP1", "blueprint states the contrapositive (minimisers have d=0)"),
 "symm-lemma": ("node", "ClP4", "'I_2 = I_3 ... by interchanging the names' (Section 3 plan)"),
 "construct-good": ("inside", "PP12", "(7.8)"), "entropy-pfr": ("node", "TP9", ""), "fibring-ident": ("node", "PrP2", ""),
 "cor-fibre": ("node", "CP5", ""),
}
bp = json.load(open(REPO / "corpus/gold_blueprints/teorth__pfr/graph.json"))
BN = {n["id"]: n for n in bp["nodes"]}
proves = {e["source"]: e["target"] for e in bp["edges"] if e["type"] == "proves"}
own = lambda x: proves.get(x) if BN[x]["type"] == "proof" else x
GB = nx.DiGraph()
for e in bp["edges"]:
    if e["type"] != "proves":
        a, b = own(e["source"]), own(e["target"])
        if a and b and a != b:
            GB.add_edge(a, b)
main = next(n["id"] for n in bp["nodes"] if n.get("label") == "pfr")
core = nx.ancestors(GB, main) | {main}
labs = {BN[x]["label"] for x in core}
assert labs == set(M), (labs - set(M), set(M) - labs)
st = Counter(M[BN[x]["label"]][0] for x in core)
types = Counter((BN[x]["type"], M[BN[x]["label"]][0]) for x in core)
# LLM graph folded to Level-1 nodes (steps/equations into container, proofs into their result), mentions dropped
L = json.load(open(REPO / "corpus/silver/opus-5.5__v7_cases/pfr_2023.json"))
N = {n["id"]: n for n in L["nodes"]}
pv = {e["source"]: e["target"] for e in L["edges"] if e["type"] == "proves" and not e.get("alternative")}
TOP = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture", "definition", "assumption", "remark", "example"}
def fold(x):
    while x in N:
        if N[x]["type"] in TOP: return x
        if N[x]["type"] == "proof": return pv.get(x, x)
        x = N[x].get("parent_id") or x
        if N[x]["type"] not in TOP and not N[x].get("parent_id") and N[x]["type"] != "proof": return x
    return x
GL = nx.DiGraph()
for e in L["edges"]:
    if e.get("mention") or e["type"] == "proves": continue
    a, b = fold(e["source"]), fold(e["target"])
    if a != b: GL.add_edge(a, b)
m = {x: fold(M[BN[x]["label"]][1]) for x in core if M[BN[x]["label"]][0] == "node"}
E = [(x, y) for x, y in GB.subgraph(core).edges() if x in m and y in m and m[x] != m[y]]
direct = [(x, y) for x, y in E if GL.has_edge(m[x], m[y])]
path = [(x, y) for x, y in E if m[x] in GL and m[y] in GL and nx.has_path(GL, m[x], m[y])]
missed = [(BN[x]["label"], BN[y]["label"], m[x], m[y]) for x, y in E if (x, y) not in path]
# reverse: LLM dependencies among aligned nodes that the blueprint lacks
inv = {}
for x, v in m.items(): inv.setdefault(v, []).append(x)
extra = [(a, b) for a, b in GL.edges() if a in inv and b in inv and not any(GB.has_edge(p, q) or nx.has_path(GB, p, q) for p in inv[a] for q in inv[b])]
out = {"blueprint_core_statements": len(core), "status_counts": st, "by_type": {f"{a}/{b}": c for (a, b), c in types.items()},
       "core_edges": GB.subgraph(core).number_of_edges(),
       "edges_between_aligned_distinct_nodes": len(E), "recovered_direct": len(direct), "recovered_as_path": len(path),
       "missed": missed, "llm_edges_not_in_blueprint": extra,
       "rows": sorted([(x, BN[x]["type"], BN[x].get("name"), BN[x]["label"], BN[x]["section"]) + M[BN[x]["label"]] for x in core], key=lambda r: r[4])}
json.dump(out, open(C / "blueprint_manual_alignment.json", "w"), indent=1, default=list)
print({k: v for k, v in out.items() if k != "rows"})
