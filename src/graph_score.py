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
  skip_tags        reference nodes not scored (section boxes of an author's diagram)
  gold_kinds       reference edges scored, by kind: a blueprint's "uses" (declared) and "ref" (named in
                   the text only); None: all

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
                   precision_scope="gold", skip_tags=("section",)),
    "blueprint": dict(node_metric="m1g", match="label", edges=True, edge_recall="direct",
                      precision_scope="all"),                         # gold: \\uses and the results the text names
    "blueprint_uses": dict(node_metric="m1g", match="label", edges=True, edge_recall="direct",
                           precision_scope="all", gold_kinds=("uses",)),   # gold: \\uses only
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


def _with_labels(g):
    """g's nodes, each with the labels metadata.labels gives it."""
    extra = defaultdict(list)
    for lab, v in ((g.get("metadata") or {}).get("labels") or {}).items():
        extra[v.get("node") if isinstance(v, dict) else v].append(lab)
    return [dict(n, labels=list(n.get("labels") or []) + extra[n["id"]]) if extra[n["id"]] else n for n in g["nodes"]]


def match_nodes(pred, gold, node_metric="m1g", match="text", threshold=NM.THRESHOLD):
    """One-to-one {pred index: (gold index, credit)}: by label first (match='label'), then the
    rest by text overlap, paired as node_metrics pairs them."""
    w, out = _WEIGHT[node_metric], {}
    if match == "label":
        owner = {lab: j for j, g in enumerate(gold) for lab in _labels(g)}
        for i, p in enumerate(pred):
            j = next((owner[lab] for lab in _labels(p) if lab in owner), None)
            if j is not None and j not in {v[0] for v in out.values()}:
                out[i] = (j, w(p.get("type"), gold[j].get("type")))
    taken = {v[0] for v in out.values()}
    rest_p, rest_g = [i for i in range(len(pred)) if i not in out], [j for j in range(len(gold)) if j not in taken]
    tok = lambda xs, ix: [(xs[k].get("type"), mm.tokens(_text(xs[k]))) for k in ix]
    out |= {rest_p[a]: (rest_g[b], c) for a, (b, c) in NM._one_to_one(tok(pred, rest_p), tok(gold, rest_g), w, threshold).items()}
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
          precision_scope="all", skip_tags=(), threshold=NM.THRESHOLD, cover=NM.COVER, gold_kinds=None) -> dict:
    """Counts for one paper. Nodes: P = node_p_credit / node_p_n, R = node_g_credit / node_g_n;
    edges (dependencies between results) likewise. Pool over papers with pooled()."""
    gn = [n for n in _with_labels(gold) if not set(n.get("tags") or []) & set(skip_tags)]
    pn = _with_labels(pred)
    if node_metric == "m3":
        pc, gc = NM.score([(n.get("type"), _text(n)) for n in pn], [(n.get("type"), _text(n)) for n in gn], "m3", threshold, cover)
        return {"node_p_credit": sum(pc), "node_p_n": len(pn), "node_g_credit": sum(gc), "node_g_n": len(gn)}
    m = match_nodes(pn, gn, node_metric, match, threshold)
    credit = sum(c for _, c in m.values())
    out = {"node_p_credit": credit, "node_p_n": len(pn) if precision_scope == "all" else len(m),
           "node_g_credit": credit, "node_g_n": len(gn)}
    if not edges:
        return out
    p2g = {pn[i]["id"]: gn[j]["id"] for i, (j, _) in m.items()}
    gdep = dependencies(gn, [e for e in gold["edges"] if not gold_kinds or e.get("kind", "uses") in gold_kinds or e["type"] != "uses"], {n["id"] for n in gn if n.get("type") not in _NOT_RESULTS})
    presults = {n["id"] for n in pn if n.get("type") not in _NOT_RESULTS}
    pdep = {(p2g[a], p2g[b]) for a, b in dependencies(pn, pred["edges"], presults | set(p2g)) if a in p2g and b in p2g}
    p_found = _implied(pdep) if edge_recall == "path" else pdep
    if precision_scope == "gold":       # only among the drawn results; implied by the drawing: not an error
        p_ok, p_n = len(pdep & _implied(gdep)), len(pdep)
    else:
        p_ok, p_n = len(pdep & gdep), len(dependencies(pn, pred["edges"], presults))
    return out | {"edge_p_credit": p_ok, "edge_p_n": p_n, "edge_g_credit": len(gdep & p_found), "edge_g_n": len(gdep)}


def pooled(counts: list) -> dict:
    """P/R/F1 for nodes and edges, pooled over papers."""
    tot = defaultdict(float)
    for c in counts:
        for k, v in c.items():
            tot[k] += v
    out = {}
    for x in ("node", "edge"):
        if f"{x}_g_n" in tot:
            out |= dict(zip((f"{x}_P", f"{x}_R", f"{x}_F1"), ns.prf(tot[f"{x}_p_credit"], tot[f"{x}_g_credit"],
                        tot[f"{x}_p_n"] - tot[f"{x}_p_credit"], tot[f"{x}_g_n"] - tot[f"{x}_g_credit"])))
            out[f"{x}_n_gold"] = int(tot[f"{x}_g_n"])
    return out
