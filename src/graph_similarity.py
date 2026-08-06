"""Graph-to-graph comparison: two extractions, or two papers.

Sits on top of `node_similarity` (node↔node) and `edge_similarity` (edge↔edge)
and adds the thing neither can do alone — **structural correspondence that is
not one-to-one**.

Why 1:1 matching is the wrong primitive
---------------------------------------
Two faithful extractions of the same paper routinely disagree on *packaging*
rather than content:

  * one emits `theorem: "A and B"`, the other emits `theorem: A`, `theorem: B`
  * one decomposes a proof into `proof_step`s, the other does not
  * one includes the `\\begin{theorem}` header in the span, the other does not

Under greedy 1:1 matching each of these is scored as a false positive *and* a
false negative. But in every case the two sides cover the same source text, so
the honest similarity of `AB` vs `(A, B)` is ~1.0, not ~0.

This module therefore aligns **groups**: it links nodes that share source text,
takes connected components of that bipartite link graph, and scores each
component by how well the two sides' pooled text covers each other. A 1:n
component is a *split*, n:1 a *merge*; both are reported as structure, not
subtracted from the score.

What comes out
--------------
Four separable numbers, so a disagreement lands in exactly one of them:

  node retrieval   did we find the same mathematical content?  (group coverage)
  structure        how did packaging differ?  (splits / merges / granularity)
  typing           type-confusion matrix over matched groups
  edges            via edge_similarity, with intra-group edges dropped

Keeping them apart is the whole point: a mislabelled-but-correctly-found
theorem should cost the typing number and nothing else.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import node_similarity as NS
import edge_similarity as ES

# Link threshold for grouping. Containment (not Jaccard) is the right metric
# here: a part is *contained* in the whole, so "A" vs "A and B" has containment
# ~1.0 but Jaccard ~0.5. Jaccard would refuse to link a split.
DEFAULT_LINK_THRESHOLD = 0.5
# ...but containment alone over-links: a 10-token equation sharing 5 generic
# tokens with a 500-token proof scores 0.5 and would be "matched". Measured on
# the gold quadruples this produced proof<->equation groups at coverage 0.017
# and inflated F1 from 0.52 to 0.86. Two guards keep containment honest:
#   * an absolute floor on the overlap, so a handful of common tokens is not
#     enough however small the node;
#   * a Jaccard floor, which rejects absurd size ratios (a genuine split has
#     Jaccard ~0.5; the proof/equation artefact has ~0.01).
DEFAULT_MIN_OVERLAP_TOKENS = 5
DEFAULT_MIN_JACCARD = 0.10
# A component this large means the link threshold has collapsed the graph;
# fall back rather than declare everything mutually matched.
MAX_GROUP_SIZE = 12


def _tokens(node, profile, **text_kw):
    return NS.tokenize(NS.node_text(node, **text_kw), profile)


def _components(links, n_a, n_b):
    """Connected components of the bipartite link graph. Nodes are ('a', i)
    and ('b', j); returns list of (set_of_a_idx, set_of_b_idx)."""
    adj = defaultdict(set)
    for i, j, _ in links:
        adj[("a", i)].add(("b", j))
        adj[("b", j)].add(("a", i))
    seen, out = set(), []
    for start in list(adj):
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.add(cur)
            stack.extend(adj[cur] - seen)
        out.append(({i for s, i in comp if s == "a"},
                    {j for s, j in comp if s == "b"}))
    return out


def align_nodes(nodes_a, nodes_b, *, profile=NS.Profile.CANONICAL,
                link_threshold=DEFAULT_LINK_THRESHOLD,
                min_overlap=DEFAULT_MIN_OVERLAP_TOKENS,
                min_jaccard=DEFAULT_MIN_JACCARD,
                type_policy=NS.TypePolicy.BLIND,
                granularity="level1", edges_a=None, edges_b=None,
                max_group=MAX_GROUP_SIZE, **text_kw):
    """Group-aware alignment of two node sets.

    `granularity="level1"` collapses `proof_step`/`algorithm_step` into their
    parents on BOTH sides first, so an extractor that does not emit steps is
    neither rewarded nor punished. Use "as_is" to compare step decompositions.

    `type_policy` defaults to BLIND: grouping is about *content*. Typing is
    reported separately by `type_confusion`.

    Returns a dict with `groups`, `map_a`/`map_b` (node id -> group id, for
    edge_similarity), and the collapsed node lists actually compared.
    """
    if granularity == "level1":
        nodes_a, edges_a = NS.collapse_to_level1(nodes_a, edges_a)
        nodes_b, edges_b = NS.collapse_to_level1(nodes_b, edges_b)

    tok_a = [_tokens(n, profile, **text_kw) for n in nodes_a]
    tok_b = [_tokens(n, profile, **text_kw) for n in nodes_b]

    links = []
    for i, ta in enumerate(tok_a):
        if not ta:
            continue
        for j, tb in enumerate(tok_b):
            if not tb:
                continue
            inter = len(ta & tb)
            if inter < min_overlap:
                continue
            if NS.jaccard_sets(ta, tb) < min_jaccard:
                continue
            c = NS.containment_sets(ta, tb)
            if c >= link_threshold:
                if type_policy != NS.TypePolicy.BLIND:
                    c *= NS.type_compat(nodes_a[i].get("type", ""),
                                        nodes_b[j].get("type", ""))
                    if c < link_threshold:
                        continue
                links.append((i, j, c))

    comps = _components(links, len(nodes_a), len(nodes_b))

    # Runaway component guard: if the threshold has fused a huge blob, keep
    # only each side's single strongest link inside it.
    fixed = []
    for ai, bj in comps:
        if len(ai) + len(bj) <= max_group:
            fixed.append((ai, bj))
            continue
        best = {}
        for i, j, c in links:
            if i in ai and j in bj:
                if i not in best or c > best[i][1]:
                    best[i] = (j, c)
        for i, (j, _) in best.items():
            fixed.append(({i}, {j}))
    comps = fixed

    seen_a = {i for ai, _ in comps for i in ai}
    seen_b = {j for _, bj in comps for j in bj}
    for i in range(len(nodes_a)):
        if i not in seen_a:
            comps.append(({i}, set()))
    for j in range(len(nodes_b)):
        if j not in seen_b:
            comps.append((set(), {j}))

    groups, map_a, map_b = [], {}, {}
    for gid, (ai, bj) in enumerate(comps):
        ua = set().union(*[tok_a[i] for i in ai]) if ai else set()
        ub = set().union(*[tok_b[j] for j in bj]) if bj else set()
        coverage = NS.jaccard_sets(ua, ub)
        kind = ("only_a" if not bj else "only_b" if not ai else
                "1:1" if len(ai) == 1 and len(bj) == 1 else
                "split" if len(ai) == 1 else
                "merge" if len(bj) == 1 else "n:m")
        gkey = "g%d" % gid
        for i in ai:
            map_a[nodes_a[i].get("id")] = gkey
        for j in bj:
            map_b[nodes_b[j].get("id")] = gkey
        groups.append({
            "id": gkey, "kind": kind, "coverage": coverage,
            "a": [nodes_a[i] for i in ai], "b": [nodes_b[j] for j in bj],
        })
    return {"groups": groups, "map_a": map_a, "map_b": map_b,
            "nodes_a": nodes_a, "nodes_b": nodes_b,
            "edges_a": edges_a, "edges_b": edges_b}


def node_metrics(groups, n_a, n_b):
    """Strict and coverage-weighted node P/R/F1 over groups.

    A matched group counts once, whatever its cardinality — that is what makes
    `AB` vs `(A, B)` score as one hit instead of one hit plus one miss and one
    spurious node.
    """
    matched = [g for g in groups if g["a"] and g["b"]]
    strict = len(matched)
    soft = sum(g["coverage"] for g in matched)
    # Denominators are group counts on each side, so splitting one side's node
    # into two does not inflate its denominator.
    da = strict + sum(1 for g in groups if g["a"] and not g["b"])
    db = strict + sum(1 for g in groups if g["b"] and not g["a"])

    def prf(hit, x, y):
        p = hit / x if x else 0.0
        r = hit / y if y else 0.0
        return p, r, (2 * p * r / (p + r) if (p + r) else 0.0)

    ps, rs, fs = prf(strict, da, db)
    pf, rf, ff = prf(soft, da, db)
    return {
        "n_nodes_a": n_a, "n_nodes_b": n_b,
        "groups_matched": strict, "only_a": da - strict, "only_b": db - strict,
        "precision": ps, "recall": rs, "f1": fs,
        "precision_soft": pf, "recall_soft": rf, "f1_soft": ff,
        "mean_coverage": (soft / strict) if strict else 0.0,
    }


def structure_report(groups):
    """Packaging differences, counted rather than penalised."""
    c = Counter(g["kind"] for g in groups)
    return {
        "one_to_one": c["1:1"], "split": c["split"], "merge": c["merge"],
        "many_to_many": c["n:m"], "only_a": c["only_a"], "only_b": c["only_b"],
    }


def type_confusion(groups):
    """{(type_a, type_b): n} over matched groups.

    For n:m groups the most common type on each side represents it, so a split
    theorem still reads as theorem↔theorem.
    """
    c = Counter()
    for g in groups:
        if not (g["a"] and g["b"]):
            continue
        ta = Counter(n.get("type", "") for n in g["a"]).most_common(1)[0][0]
        tb = Counter(n.get("type", "") for n in g["b"]).most_common(1)[0][0]
        c[(ta, tb)] += 1
    return c


def step_report(nodes_a, nodes_b):
    """Step-decomposition support on each side.

    Reported as a capability, never as a penalty: if only one side emits steps
    the L2 comparison is undefined, not failed.
    """
    sa, sb = NS.step_support(nodes_a), NS.step_support(nodes_b)
    return {"parents_decomposed_a": len(sa), "parents_decomposed_b": len(sb),
            "both": len(sa & sb),
            "comparable": bool(sa and sb)}


def compare_graphs(graph_a, graph_b, *, profile=NS.Profile.CANONICAL,
                   link_threshold=DEFAULT_LINK_THRESHOLD,
                   min_overlap=DEFAULT_MIN_OVERLAP_TOKENS,
                   min_jaccard=DEFAULT_MIN_JACCARD,
                   granularity="level1", use_edge_type=True, **text_kw):
    """Full comparison of two `{nodes, edges}` graphs.

    Works unchanged for two extractions of one paper and for two different
    papers — the operation is the same, only the expected magnitude differs.
    """
    na, ea = graph_a.get("nodes", []), graph_a.get("edges", [])
    nb, eb = graph_b.get("nodes", []), graph_b.get("edges", [])

    al = align_nodes(na, nb, profile=profile, link_threshold=link_threshold,
                     min_overlap=min_overlap, min_jaccard=min_jaccard,
                     granularity=granularity, edges_a=ea, edges_b=eb, **text_kw)

    em, ua, ub = ES.match_edges(al["edges_a"] or [], al["edges_b"] or [],
                                map_a=al["map_a"], map_b=al["map_b"],
                                use_type=use_edge_type)
    n_ea = len(em) + len(ua)
    n_eb = len(em) + len(ub)

    return {
        "nodes": node_metrics(al["groups"], len(al["nodes_a"]),
                              len(al["nodes_b"])),
        "structure": structure_report(al["groups"]),
        "types": type_confusion(al["groups"]),
        "steps": step_report(na, nb),
        "edges": ES.edge_metrics(em, n_ea, n_eb),
        "edge_types": ES.edge_type_confusion(em),
        "groups": al["groups"],
    }
