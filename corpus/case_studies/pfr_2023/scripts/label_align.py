"""Supplementary: align blueprint core statements to paper-graph nodes by shared LaTeX label."""
import json, sys
from pathlib import Path
import networkx as nx
sys.path.insert(0, "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/181b34d2-e85e-4795-8729-4e70122e8101/scratchpad")
REPO = Path("/mnt/c/Code/Github/Saranga"); C = REPO / "corpus/case_studies/pfr_2023"
import importlib.util
spec = importlib.util.spec_from_file_location("an", "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/181b34d2-e85e-4795-8729-4e70122e8101/scratchpad/analyze_pfr.py")
an = importlib.util.module_from_spec(spec); spec.loader.exec_module(an)
out = json.load(open(C / "analysis.json"))
GB, NB = an.results_view(an.BPG)
bmain = next(n["id"] for n in an.BPG["nodes"] if n.get("label") == "pfr")
banc = nx.ancestors(GB, bmain) | {bmain}
core = GB.subgraph(banc)
res = {}
for name, g in (("llm", an.LLM), ("rules", an.RUL)):
    G, N = an.results_view(g)
    nodes = {n["id"]: n for n in g["nodes"]}
    lab = {}
    for n in g["nodes"]:
        if n.get("label"):
            lab[n["label"]] = n["id"]
    for k, v in (g["metadata"].get("labels") or {}).items():
        if k not in lab and (v.get("node") or v.get("within")):
            lab[k] = v.get("node") or v.get("within")
    def own(x):
        while x in nodes and x not in G:
            n = nodes[x]
            if n["type"] == "proof":
                x = next((e["target"] for e in g["edges"] if e["source"] == x and e["type"] == "proves"), None)
            else:
                x = n.get("parent_id")
        return x if x in G else None
    m = {}
    for b in banc:
        l = NB[b].get("label")
        if l in lab and own(lab[l]):
            m[b] = own(lab[l])
    E = [(x, y) for x, y in core.edges() if x in m and y in m and m[x] != m[y]]
    direct = [(x, y) for x, y in E if G.has_edge(m[x], m[y])]
    path = [(x, y) for x, y in E if nx.has_path(G, m[x], m[y])]
    res[name] = {"core_statements": len(banc), "matched_by_label": len(m),
                 "matched": sorted((b, NB[b].get("name"), NB[b].get("label"), m[b]) for b in m),
                 "core_edges_between_matched": len(E), "recovered_direct": len(direct), "recovered_as_path": len(path),
                 "missed": sorted((NB[x].get("label"), NB[y].get("label")) for x, y in E if (x, y) not in path)}
res["unmatched_core"] = sorted((b, NB[b].get("name"), NB[b].get("label"), NB[b].get("section")) for b in banc if b not in [k for k, *_ in res["llm"]["matched"]])
out["label_alignment"] = res
json.dump(out, open(C / "analysis.json", "w"), indent=1, default=list)
for k in ("llm", "rules"):
    print(k, {a: res[k][a] for a in res[k] if a not in ("matched",)})
print([x[2] for x in res["llm"]["matched"]])
print(len(res["unmatched_core"]))
