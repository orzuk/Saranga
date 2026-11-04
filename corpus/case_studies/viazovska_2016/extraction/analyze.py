"""Numbers for the Viazovska case study (SUMMARY.md) and the slide's results view."""
import json, re, sys
from collections import defaultdict, Counter
from pathlib import Path
REPO = Path("/mnt/c/Code/Github/Saranga")
sys.path[:0] = [str(REPO / "src"), str(REPO / "src/LLMVersion"), str(REPO / "scripts/gold_candidates"), str(REPO / "portal")]
import graph_score as GS
import latex_facts

HERE = Path(__file__).parent
D = REPO / "corpus/case_studies/viazovska_2016"
LLM = json.load(open(REPO / "corpus/silver/opus-5.5__v7_cases/viazovska_2016.json"))
RUL = json.load(open(D / "viazovska_2016_rules.json"))
BPD = REPO / "corpus/gold_blueprints/thefundamentaltheor3m__Sphere-Packing-Lean"
BP = json.load(open(BPD / "graph.json"))
KEY = {v: k for k, v in json.load(open(HERE / "ids.json")).items()}      # my key -> id
IDK = {v: k for k, v in KEY.items()}
RESULTS = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"}
NUMBERED = {"theorem", "lemma", "proposition", "corollary"}
LIFT = {"equation", "proof_step", "algorithm_step"}


def lift(g):
    """edges with nested equations / steps replaced by their container (mentions dropped)"""
    by = {n["id"]: n for n in g["nodes"]}

    def unit(i):
        seen = set()
        while by.get(i, {}).get("type") in LIFT and by[i].get("parent_id") and i not in seen:
            seen.add(i)
            i = by[i]["parent_id"]
        return i
    E = set()
    proved = defaultdict(set)              # a proof's own results: its references to their equations are not uses
    for e in g["edges"]:
        if e.get("type") == "proves":
            proved[e["source"]].add(e["target"])
    for e in g["edges"]:
        if e.get("mention") or (e.get("type") or "uses") not in GS._RESULT_EDGES:
            continue
        s, t = unit(e["source"]), unit(e["target"])
        if s != t and s not in proved.get(t, ()):
            E.add((s, t, e.get("type") or "uses"))
    return by, unit, E


def label(n):
    if n.get("display") and n.get("number"):
        return f"{n['display']} {n['number']}"
    return None


def closure(E):
    adj = defaultdict(set)
    for s, t, *_ in E:
        adj[s].add(t)
    def down(a):
        seen, todo = set(), [a]
        while todo:
            for v in adj[todo.pop()] - seen:
                seen.add(v); todo.append(v)
        return seen
    return adj, down


def longest_to(target, E):
    pred = defaultdict(set)
    for s, t, *_ in E:
        pred[t].add(s)
    memo = {}
    def f(v, stack=()):
        if v in memo:
            return memo[v]
        best = (0, [v])
        for u in pred[v]:
            if u in stack:
                continue
            d, p = f(u, stack + (v,))
            if d + 1 > best[0]:
                best = (d + 1, p + [v])
        memo[v] = best
        return best
    return f(target)


VOCAB = {"definition", "assumption", "remark", "problem", "open_problem"}


def results_view(g, keep_types, logical=False):
    """logical: paths may not pass through definitions (vocabulary), only proofs, steps, equations, results"""
    by, unit, E = lift(g)
    if logical:
        E = {(s, t, ty) for s, t, ty in E if by[s]["type"] not in VOCAB and by[t]["type"] not in VOCAB}
    nodes = [dict(by[i], id=i) for i in by]
    keep = {n["id"] for n in g["nodes"] if n["type"] in keep_types}
    deps = GS.dependencies(g["nodes"], [{"source": s, "target": t, "type": ty} for s, t, ty in E], keep)
    return by, E, keep, deps, GS.reduction(deps)


out = {}
# ------------------------------------------------------------------ LLM graph
by, unit, E = lift(LLM)
out["llm_counts"] = {"nodes": len(LLM["nodes"]), "edges": len(LLM["edges"]),
                     "types": Counter(n["type"] for n in LLM["nodes"]),
                     "edge_types": Counter(e["type"] for e in LLM["edges"]),
                     "external": sum(n["origin"] == "external" for n in LLM["nodes"]),
                     "level1": sum(n["type"] not in LIFT for n in LLM["nodes"]),
                     "edge_basis": Counter(e.get("basis", "-") for e in LLM["edges"]),
                     "mentions": sum(bool(e.get("mention")) for e in LLM["edges"]),
                     "rigor": {n["id"]: n["rigor"] for n in LLM["nodes"] if n.get("rigor")}}
adj, down = closure(E)
main = KEY["t_main"]

# results view: theorem/proposition/... and claims; the slide uses the numbered results + cited theorems
_, _, keepR, depsR, redR = results_view(LLM, RESULTS, logical=True)
_, _, keepN, depsN, redN = results_view(LLM, NUMBERED, logical=True)
_, _, _, depsRd, redRd = results_view(LLM, RESULTS)
_, _, _, depsNd, redNd = results_view(LLM, NUMBERED)
anc_main = {a for a, b in GS._implied(depsR) if b == main}
ancN = {a for a, b in GS._implied(depsN) if b == main}
d_main, path_main = longest_to(main, redR)
d_mainN, path_mainN = longest_to(main, redN)
d_full, path_full = longest_to(main, {(s, t) for s, t, _ in E})
out["results_view"] = {"results": len(keepR), "deps": len(depsR), "reduced": len(redR),
                       "ancestors_of_thm1": len(anc_main), "depth_to_thm1": d_main,
                       "longest_chain": [f"{p} {by[p]['name']}" for p in path_main],
                       "numbered_results": len(keepN), "numbered_deps": len(depsN), "numbered_reduced": len(redN),
                       "numbered_depth": d_mainN, "numbered_chain": [f"{label(by[p]) or p}: {by[p]['name']}" for p in path_mainN],
                       "with_definitions": {"deps": len(depsRd), "reduced": len(redRd), "depth": longest_to(main, redRd)[0],
                                             "ancestors_of_thm1": len({a for a, b in GS._implied(depsRd) if b == main}),
                                             "numbered_deps": len(depsNd), "numbered_depth": longest_to(main, redNd)[0],
                                             "numbered_chain": [label(by[p]) or by[p]["name"] for p in longest_to(main, redNd)[1]]},
                       "full_graph_depth_to_thm1": d_full, "full_graph_chain": [f"{p} {by[p]['type']} {by[p]['name']}" for p in path_full]}
# most used: direct dependents in the reduced results view, and all descendants (any node type)
dir_dep = Counter(a for a, b in depsR)
desc_res = {i: len(down(i) & keepR) for i in by if by[i]["type"] not in LIFT}
desc_all = {i: len({unit(x) for x in down(i)}) for i in by if by[i]["type"] not in LIFT}
out["most_used_results"] = [(i, label(by[i]), by[i]["name"], by[i]["origin"], dir_dep[i], desc_res[i])
                            for i in sorted(keepR, key=lambda i: (-dir_dep[i], -desc_res[i]))[:12]]
indeg = Counter()
for s, t, _ in E:
    indeg[s] += 1
out["most_used_nodes"] = [(i, by[i]["type"], by[i]["name"], indeg[i], desc_all[i])
                          for i in sorted(desc_all, key=lambda i: -indeg[i])[:15]]
# ancestors of Theorem 1 over the whole lifted graph, by type and origin
anc_all = {s for s in by if main in down(s)}
out["support_of_thm1"] = {"nodes": len(anc_all), "by_type": Counter(by[i]["type"] for i in anc_all),
                          "external": sorted((by[i]["name"] for i in anc_all if by[i]["origin"] == "external")),
                          "not_supporting_level1": sorted(by[i]["name"] for i in by if by[i]["type"] not in LIFT
                                                          and i not in anc_all and i != main)}
# magic functions
MAGIC = ["d_varphi", "d_phi", "d_a", "d_h", "d_psi", "d_b"]
mg = {}
for k in MAGIC:
    i = KEY[k]
    dd = down(i)
    mg[k] = {"id": i, "name": by[i]["name"], "section": by[i]["section"],
             "direct_users": sorted({by[t]["name"] for s, t, _ in E if s == i}),
             "downstream_results": sorted(label(by[x]) or by[x]["name"] for x in dd if x in keepR),
             "downstream_level1": len({unit(x) for x in dd}), "reaches_thm1": main in dd}
out["magic"] = mg
magic_down = set().union(*(down(KEY[k]) for k in MAGIC))
out["magic_share"] = {"results_ancestors_of_thm1": len(anc_main),
                      "of_which_downstream_of_magic": len(anc_main & magic_down),
                      "upstream_not_magic": sorted(by[i]["name"] for i in anc_main - magic_down)}
# the main chain (results view of the numbered results, plus the cited Cohn-Elkies theorem)
out["numbered_reduced_edges"] = sorted(f"{label(by[a]) or by[a]['name']} -> {label(by[b]) or by[b]['name']}" for a, b in redN)

# ------------------------------------------------------------------ rules graph
rby, runit, rE = lift(RUL)
_, _, rkeepR, rdepsR, rredR = results_view(RUL, RESULTS, logical=True)
_, _, rkeepN, rdepsN, rredN = results_view(RUL, NUMBERED, logical=True)
rmain = next(n["id"] for n in RUL["nodes"] if n.get("label") == "thm: main")
rd, rpath = longest_to(rmain, rredR)
out["rules_counts"] = {"nodes": len(RUL["nodes"]), "edges": len(RUL["edges"]),
                       "types": Counter(n["type"] for n in RUL["nodes"]),
                       "edge_types": Counter(e["type"] for e in RUL["edges"]),
                       "learned_edges": sum(bool(e.get("provenance")) for e in RUL["edges"]),
                       "results": len(rkeepR), "deps": len(rdepsR), "reduced": len(rredR),
                       "depth_to_thm1": rd, "chain": [f"{p} {rby[p]['type']} {(rby[p].get('statement') or '')[:60]}" for p in rpath],
                       "ancestors_of_thm1": len({a for a, b in GS._implied(rdepsR) if b == rmain})}
# compare the numbered results views by \label
lab_llm = {n["id"]: n.get("label") for n in LLM["nodes"] if n.get("label")}
lab_rul = {n["id"]: n.get("label") for n in RUL["nodes"] if n.get("label")}
Lv = {(lab_llm.get(a), lab_llm.get(b)) for a, b in depsN}
Rv = {(lab_rul.get(a), lab_rul.get(b)) for a, b in rdepsN}
out["llm_vs_rules_numbered_deps"] = {"llm": len(Lv), "rules": len(Rv), "common": len(Lv & Rv),
                                     "llm_only": sorted(f"{a} -> {b}" for a, b in Lv - Rv),
                                     "rules_only": sorted(f"{a} -> {b}" for a, b in Rv - Lv)}
rl1 = [n for n in RUL["nodes"] if n["type"] not in LIFT]
out["rules_level1_without_label"] = Counter(n["type"] for n in rl1 if not n.get("label"))
out["llm_level1_prose"] = Counter(n["type"] for n in LLM["nodes"] if n["type"] not in LIFT and not n.get("label") and n["confidence"] < 1.0)

# ------------------------------------------------------------------ blueprint
import score_bp_papers as SB
tex = latex_facts.read_tex(str(D / "paper.tex"))
bp_results = [n for n in BP["nodes"] if n.get("type") not in GS._NOT_RESULTS]
bby = {n["id"]: n for n in BP["nodes"]}
bpE = {(e["source"], e["target"], e["type"]) for e in BP["edges"]}
bmain = next(n["id"] for n in BP["nodes"] if n.get("label") == "MainTheorem")
bkeep = {n["id"] for n in BP["nodes"] if n["type"] in RESULTS}
bdeps = GS.dependencies(BP["nodes"], BP["edges"], bkeep)
bred = GS.reduction(bdeps)
bd, bpath = longest_to(bmain, bred)
banc = {a for a, b in GS._implied(bdeps) if b == bmain}
out["blueprint"] = {"nodes": len(BP["nodes"]), "edges": len(BP["edges"]), "types": Counter(n["type"] for n in BP["nodes"]),
                    "statements": len(bp_results), "results": len(bkeep), "deps": len(bdeps), "reduced": len(bred),
                    "depth_to_main": bd, "chain": [f"{bby[p]['label'] or p}" for p in bpath],
                    "results_ancestors_of_main": len(banc),
                    "by_section": Counter(n["section"] for n in bp_results)}
for name, g in (("llm", LLM), ("rules", RUL)):
    a, _ = SB.align(bp_results, g, tex, 0.5)
    pby = {n["id"]: n for n in g["nodes"]}
    un = [n for n in bp_results if n["id"] not in a]
    out[f"bp_align_{name}"] = {"aligned": len(a), "unaligned": len(un),
                               "unaligned_by_section": Counter(n["section"] for n in un),
                               "aligned_by_bp_section": Counter(bby[b]["section"] for b in a)}
    if name == "llm":
        out["bp_alignment_llm"] = sorted((bby[b]["label"] or b, bby[b]["type"], pby[p]["id"], pby[p]["type"], pby[p]["name"]) for b, p in a.items())
        out["bp_unaligned_llm"] = [(n["label"] or n["id"], n["type"], n["section"], re.sub(r"\s+", " ", n["statement"])[:120]) for n in un]
        # paper nodes with no blueprint counterpart: what the blueprint dropped
        used = set(a.values())
        out["llm_results_not_in_bp"] = sorted(f"{label(pby[i]) or i}: {pby[i]['name']} ({pby[i]['origin']})"
                                             for i in keepR if i not in used)
        # blueprint dependencies among aligned results that the paper graph does not have (path), and vice versa
        p2b = {p: b for b, p in a.items()}
        bal = set(a)
        bdep_al = GS.dependencies(BP["nodes"], BP["edges"], bal)
        pdep = GS.dependencies(g["nodes"], [{"source": s, "target": t, "type": ty} for s, t, ty in E], set(used))
        pdep_b = {(p2b[x], p2b[y]) for x, y in pdep}
        pclos = GS._implied(pdep_b)
        out["bp_deps_missing_in_llm"] = sorted(f"{bby[x]['label'] or x} -> {bby[y]['label'] or y}" for x, y in GS.reduction(bdep_al) if (x, y) not in pclos)
        bclos = GS._implied(bdep_al)
        out["llm_deps_not_in_bp"] = sorted(f"{bby[x]['label'] or x} -> {bby[y]['label'] or y}" for x, y in GS.reduction(pdep_b) if (x, y) not in bclos)
        out["bp_deps_found_in_llm"] = sum((x, y) in pclos for x, y in GS.reduction(bdep_al))
        out["bp_deps_aligned_reduced"] = len(GS.reduction(bdep_al))

# ------------------------------------------------------------------ slide JSON
NOTE = {("t_g", "t_g1"): "Theorem 4 restates the conditions (g1)-(g3) of Theorem 3 by reference; the same proof proves both",
        ("p1", "p5"): "method reuse: 'we repeat the arguments used in the proof of Proposition 1'",
        ("p3", "p7"): "method reuse ('analogous to the proof of Proposition 3'), plus a \\eqref to (a another integral) where (b another integral) is meant",
        ("c_radial", "t_g"): "why g is sought radial (Cohn-Elkies p. 695)",
        ("p1", "t_g"): "inferred (not cited): g-hat needs F(a)=a", ("p5", "t_g"): "inferred (not cited): g-hat needs F(b)=-b"}


def node_entry(i):
    n = by[i]
    return {"id": i, "label": label(n) or ("cited" if n["origin"] == "external" else "claim"), "name": n["name"],
            "type": n["type"], "origin": n["origin"] + (f" ({n['origin_citation']})" if n.get("origin_citation") else ""),
            "section": n.get("section"), "main": bool(n.get("main")),
            "depth": longest_to(i, redR)[0], "uses_magic_functions": i in magic_down,
            "statement_short": n.get("statement_short")}
core = sorted(anc_main | {main}, key=lambda i: by[i].get("section") or "")
core_numbered = sorted((ancN | {main}), key=lambda i: by[i].get("section") or "")
slide = {"paper": "Viazovska, The sphere packing problem in dimension 8 (arXiv:1603.04246)",
         "graph": "corpus/silver/opus-5.5__v7_cases/viazovska_2016.json (Claude Opus 5.5, v7 prompt)",
         "view": "results only: theorems, propositions and claims that Theorem 1 rests on; an edge A -> B means B depends on A "
                 "(paths through proofs, definitions and equations collapsed; transitive reduction)",
         "nodes": [node_entry(i) for i in core],
         "edges": sorted([dict({"source": a, "target": b, "implied_by_others": (a, b) not in redR}, **({"note": NOTE[(IDK[a], IDK[b])]} if (IDK[a], IDK[b]) in NOTE else {}))
                          for a, b in depsR if a in set(core) and b in set(core)], key=lambda e: (e["source"], e["target"])),
         "numbered_only": {"nodes": [{"id": i, "label": label(by[i]) or by[i]["name"], "name": by[i]["name"]} for i in core_numbered],
                           "edges": sorted(f"{label(by[a]) or by[a]['name']} -> {label(by[b]) or by[b]['name']}" for a, b in depsN
                                           if a in set(core_numbered) and b in set(core_numbered))},
         "magic_entry": [{"definition": by[KEY[k]]["name"], "id": KEY[k],
                          "first_results_using_it": sorted({label(by[t]) or by[t]["name"] for s, t in
                                                            GS.dependencies(LLM["nodes"], [{"source": s, "target": t, "type": ty} for s, t, ty in E], keepR | {KEY[k]})
                                                            if s == KEY[k]})} for k in MAGIC],
         "longest_chain_to_theorem_1": [label(by[p]) or by[p]["name"] for p in path_main]}
json.dump(slide, open(D / "results_view.json", "w"), indent=1, ensure_ascii=False)
json.dump(out, open(D / "analysis.json", "w"), indent=1, ensure_ascii=False, default=list)
print(json.dumps(out, indent=1, ensure_ascii=False, default=list)[:20000])
