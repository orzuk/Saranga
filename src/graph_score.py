"""One scorer for a predicted paper graph against a reference graph: nodes, edges, or both.

Every comparison is a preset of the same options (PRESETS):

  distill     distilled vs LLM silver: nodes by text overlap (node_metrics m1g), as the
              distillation comparison reports
  author      an author's dependency diagram (corpus/gold_candidates): partial, so
              precision is judged only among the results the authors drew
  blueprint   a Lean blueprint (corpus/gold_blueprints): complete, so full precision

Options
  node_metric      m1g | m1 | m3 (node_metrics), the credit of a node pair
  threshold        token overlap for a text pair to qualify (0.7)
  cover            m3: share of a node covered by the other side (0.7)
  match            text: pairs by text overlap; label: first by LaTeX label (a reference box
                   lists the labels it cites), then text for the rest
  edges            score edges too, through the node matching
  edge_recall      direct: the predicted graph has a dependency between the two matched
                   nodes, possibly through unmatched nodes (a proof, its steps); path: any path
  precision_scope  all: every prediction counts; gold: only predictions between matched
                   reference nodes (the rest cannot be judged), and a predicted dependency that
                   the reference implies through a path is not an error
  skip_tags        reference nodes not scored (section boxes and non-result boxes of an author's diagram)
  edge_mode        structure: dependencies between the results each side names (a result one side names
                   and the other keeps inside a proof changes the edges); invariant: only the results both
                   sides name, connected through anything in between, reduced to their transitive reduction,
                   so two graphs that differ only in hierarchy score 1 (docs: proof_dag_hierarchy.pdf)
  pred_types       predictions scored for node precision: all, or "gold" (only the node types the
                   reference annotates: a blueprint has no equation nodes)
  gold_kinds       reference edges scored, by kind: a blueprint's "uses" (declared) and "ref" (named in
                   the text only); None: all
  copies           also match reference nodes that are copies of a matched prediction (copy_matches): a
                   result the reference states twice and the prediction keeps once (v7: also_stated_at)

Edges point from the result used to the result that uses it (source -> target).
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "LLMVersion"))
import match_modes as mm                                    # noqa: E402
import node_metrics as NM                                   # noqa: E402
import node_similarity as ns                                # noqa: E402

PRESETS = {
    "distill": dict(node_metric="m1g", match="text", edges=False),
    "author": dict(node_metric="m1g", match="label", edges=True, edge_recall="path",
                   precision_scope="gold", skip_tags=("section", "non_result")),
    "blueprint": dict(node_metric="m1g", match="label", edges=True, edge_recall="direct",
                      precision_scope="all", pred_types="gold", copies=True),            # gold: \\uses and the results the text names
    "author_inv": dict(node_metric="m1g", match="label", edges=True, edge_mode="invariant", skip_tags=("section", "non_result"),
                       precision_scope="gold"),
    "blueprint_inv": dict(node_metric="m1g", match="label", edges=True, edge_mode="invariant", pred_types="gold", copies=True),
    "blueprint_uses": dict(node_metric="m1g", match="label", edges=True, edge_recall="direct",
                           precision_scope="all", pred_types="gold", gold_kinds=("uses",), copies=True),   # gold: \\uses only
}
_WEIGHT = {"m1g": ns.type_compat, "m1": lambda a, b: 1.0 if a == b else 0.0}
_RESULT_EDGES = ("uses", "proves", "generalizes", "specializes")
_NOT_RESULTS = {"proof", "proof_step", "equation", "algorithm_step"}


def _text(n):
    return n.get("statement") or n.get("raw_latex") or n.get("name") or ""


def _labels(n):
    """A node's LaTeX labels: its own `label`, the `labels` a reference box cites (score() adds
    those a graph keeps in metadata.labels, as the rule-based parser does)."""
    return set(n.get("labels") or []) | ({n["label"]} if n.get("label") else set())


def _label_order(n):
    """_labels(n) in a fixed order, the node's own label first (a set's order varies from run to run)."""
    return ([n["label"]] if n.get("label") else []) + sorted(_labels(n) - {n.get("label")})


def _with_labels(g):
    """g's nodes, each with the labels metadata.labels gives it."""
    extra = defaultdict(list)
    for lab, v in ((g.get("metadata") or {}).get("labels") or {}).items():
        extra[v.get("node") if isinstance(v, dict) else v].append(lab)
    return [dict(n, labels=list(n.get("labels") or []) + extra[n["id"]]) if extra[n["id"]] else n for n in g["nodes"]]


def gtype_of(nodes, i):
    return next((n.get("type") for n in nodes if n["id"] == i), None)


def match_nodes(pred, gold, node_metric="m1g", match="text", threshold=NM.THRESHOLD):
    """One-to-one {pred index: (gold index, credit)}: by label first (match='label'), then the
    rest by text overlap, paired as node_metrics pairs them."""
    w, out = _WEIGHT[node_metric], {}
    if match == "label":
        owner = {lab: j for j, g in enumerate(gold) for lab in _labels(g)}
        for i, p in enumerate(pred):
            j = next((owner[lab] for lab in _label_order(p) if lab in owner), None)
            if j is not None and j not in {v[0] for v in out.values()}:
                out[i] = (j, w(p.get("type"), gold[j].get("type")))
    taken = {v[0] for v in out.values()}
    rest_p, rest_g = [i for i in range(len(pred)) if i not in out], [j for j in range(len(gold)) if j not in taken]
    tok = lambda xs, ix: [(xs[k].get("type"), mm.tokens(_text(xs[k]))) for k in ix]
    out |= {rest_p[a]: (rest_g[b], c) for a, (b, c) in NM._one_to_one(tok(pred, rest_p), tok(gold, rest_g), w, threshold).items()}
    return out


def copy_matches(pred, gold, m, threshold=NM.THRESHOLD):
    """{gold index: pred index} for reference nodes the one-to-one matching m left out that copy a prediction:
    they carry one of its labels (a label defined twice, a result stated twice), or their text is one of the
    restatements it lists in also_stated_at (the v7 prompt keeps one node per result)."""
    taken, owner, out = {j for j, _ in m.values()}, defaultdict(list), {}
    for j, g in enumerate(gold):
        for lab in _labels(g):
            owner[lab].append(j)
    for i, p in enumerate(pred):
        for j in (j for lab in _label_order(p) for j in owner.get(lab, ())):
            if j not in taken:
                out.setdefault(j, i)
    alts = [(i, mm.tokens(s if isinstance(s, str) else _text(s))) for i, p in enumerate(pred) for s in p.get("also_stated_at") or []]
    for j in (j for j in range(len(gold)) if j not in taken and j not in out):
        b = mm.tokens(_text(gold[j]))
        ov, i = max(((mm.sym_containment(a, b), i) for i, a in alts), default=(0.0, None))
        if ov >= threshold:
            out[j] = i
    return out


def dependencies(nodes, edges, keep):
    """{(a, b)}: a and b in keep, and a path a -> ... -> b whose inner nodes are not in keep
    (a lemma used in a proof of the theorem: lemma -> proof -> theorem)."""
    adj = defaultdict(set)
    for e in edges:
        if (e.get("type") or "uses") in _RESULT_EDGES and not e.get("mention"):
            adj[e["source"]].add(e["target"])
    out = set()
    for a in keep:
        seen, todo = set(), [a]
        while todo:
            for v in adj[todo.pop()] - seen:
                seen.add(v)
                (out.add((a, v)) if v in keep else todo.append(v))
    return {(a, b) for a, b in out if a != b}


def reduction(deps):
    """The transitive reduction of a dependency set: (a, b) is dropped when b is also reached from a
    through another dependency (unique for a DAG; Aho, Garey and Ullman 1972)."""
    adj = defaultdict(set)
    for a, b in deps:
        adj[a].add(b)
    reach = {a: {y for x, y in _implied(deps) if x == a} for a in adj}
    return {(a, b) for a, b in deps if not any(b in reach.get(c, ()) for c in adj[a] if c != b)}


def _implied(deps):
    """The transitive closure of a dependency set."""
    adj = defaultdict(set)
    for a, b in deps:
        adj[a].add(b)
    out = set()
    for a in list(adj):
        seen, todo = set(), [a]
        while todo:
            for v in adj[todo.pop()] - seen:
                seen.add(v); todo.append(v); out.add((a, v))
    return out


def score(pred: dict, gold: dict, node_metric="m1g", match="text", edges=True, edge_recall="direct",
          precision_scope="all", skip_tags=(), threshold=NM.THRESHOLD, cover=NM.COVER, gold_kinds=None,
          pred_types="all", edge_mode="structure", copies=False) -> dict:
    """Counts for one paper. Nodes: P = node_p_credit / node_p_n, R = node_g_credit / node_g_n;
    edges (dependencies between results) likewise. Pool over papers with pooled()."""
    gn = [n for n in _with_labels(gold) if not set(n.get("tags") or []) & set(skip_tags)]
    pn = _with_labels(pred)
    if pred_types == "gold":
        pn = [n for n in pn if n.get("type") in {g.get("type") for g in gn}]
    if node_metric == "m3":
        pc, gc = NM.score([(n.get("type"), _text(n)) for n in pn], [(n.get("type"), _text(n)) for n in gn], "m3", threshold, cover)
        return {"node_p_credit": sum(pc), "node_p_n": len(pn), "node_g_credit": sum(gc), "node_g_n": len(gn)}
    m = match_nodes(pn, gn, node_metric, match, threshold)
    cm = copy_matches(pn, gn, m, threshold) if copies else {}
    credit = sum(c for _, c in m.values())
    out = {"node_p_credit": credit, "node_p_n": len(pn) if precision_scope == "all" else len(m),
           "node_g_credit": credit + sum(_WEIGHT[node_metric](pn[i].get("type"), gn[j].get("type")) for j, i in cm.items()),
           "node_g_n": len(gn)}
    if not edges:
        return out
    p2g = defaultdict(list)            # a prediction -> the reference nodes it stands for (one, or with its copies)
    for i, (j, _) in m.items():
        p2g[pn[i]["id"]].append(gn[j]["id"])
    for j, i in cm.items():
        p2g[pn[i]["id"]].append(gn[j]["id"])
    if edge_mode == "invariant":       # the results both name, through anything in between, reduced
        gm = {g for gs in p2g.values() for g in gs if gtype_of(gn, g) not in _NOT_RESULTS}
        gk = [e for e in gold["edges"] if not gold_kinds or e.get("kind", "uses") in gold_kinds or e["type"] != "uses"]
        ge = reduction(dependencies(gn, gk, gm))
        pe = reduction({(x, y) for a, b in dependencies(pn, pred["edges"], {a for a, gs in p2g.items() if set(gs) & gm})
                        for x in p2g[a] if x in gm for y in p2g[b] if y in gm and x != y})
        return out | {"edge_p_credit": len(pe & ge), "edge_p_n": len(pe), "edge_g_credit": len(pe & ge), "edge_g_n": len(ge)}
    gres = {n["id"] for n in gn if n.get("type") not in _NOT_RESULTS}
    gdep = dependencies(gn, [e for e in gold["edges"] if not gold_kinds or e.get("kind", "uses") in gold_kinds or e["type"] != "uses"], gres)
    # results only on both sides: a matched proof is collapsed like any proof, never an endpoint
    presults = {n["id"] for n in pn if n.get("type") not in _NOT_RESULTS}
    # an arrow the authors drew as an equivalence (A <=> B) is matched in either direction
    geq = {(e["source"], e["target"]) for e in gold["edges"] if e.get("equivalence")}
    flip = lambda a, b: (b, a) if (b, a) in geq and (a, b) not in gdep else (a, b)
    ppairs = dependencies(pn, pred["edges"], presults)
    by_pair = {(a, b): {flip(x, y) for x in p2g.get(a, ()) if x in gres for y in p2g.get(b, ()) if y in gres and x != y}
               for a, b in ppairs}
    pdep = set().union(*by_pair.values())
    p_found = _implied(pdep) if edge_recall == "path" else pdep
    if precision_scope == "gold":       # only among the drawn results; implied by the drawing: not an error
        p_ok, p_n = len(pdep & _implied(gdep)), len(pdep)
    else:
        # one credit per predicted dependency (a copy can give it several reference pairs), per reference pair
        p_ok, p_n = len({min(s & gdep) for s in by_pair.values() if s & gdep}), len(ppairs)
    gtype = {n["id"]: n.get("type") for n in gn}
    gdef = {d for d in gdep if gtype.get(d[0]) == "definition"}     # recall split: dependencies on definitions
    return out | {"edge_p_credit": p_ok, "edge_p_n": p_n, "edge_g_credit": len(gdep & p_found), "edge_g_n": len(gdep),
                  "def_g_credit": len(gdef & p_found), "def_g_n": len(gdef),
                  "res_g_credit": len((gdep - gdef) & p_found), "res_g_n": len(gdep - gdef)}


def pooled(counts: list) -> dict:
    """P/R/F1 for nodes and edges, pooled over papers."""
    tot = defaultdict(float)
    for c in counts:
        for k, v in c.items():
            tot[k] += v
    out = {}
    for x in ("def", "res"):                            # recall only: on definitions, on results
        if tot.get(f"{x}_g_n"):
            out[f"edge_R_{x}"] = tot[f"{x}_g_credit"] / tot[f"{x}_g_n"]
    for x in ("node", "edge"):
        if f"{x}_g_n" in tot:
            out |= dict(zip((f"{x}_P", f"{x}_R", f"{x}_F1"), ns.prf(tot[f"{x}_p_credit"], tot[f"{x}_g_credit"],
                        tot[f"{x}_p_n"] - tot[f"{x}_p_credit"], tot[f"{x}_g_n"] - tot[f"{x}_g_credit"])))
            out[f"{x}_n_gold"] = int(tot[f"{x}_g_n"])
    return out
