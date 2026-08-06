#!/usr/bin/env python3
"""Graph alignment for mathematical knowledge graphs.

Implements a three-tier pipeline:
  1. Signature prefilter (foundation-term TF-IDF)
  2. Fast bipartite matching (Hungarian)
  3. Iterative structural refinement

Plus statistical significance via Monte Carlo permutation testing.

Usage:
    from graph_alignment import align_papers, significance_test
    result = align_papers(graph_A, graph_B, sigma_fn=jaccard_sim)
    z, p = significance_test(graph_A, graph_B, result, sigma_fn)
"""
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment


# ── Type compatibility & tokenisation ────────────────────────────────────────
# Canonical definitions now live in src/node_similarity.py so that cross-paper
# alignment and same-paper extraction evaluation cannot drift apart. Re-exported
# here under the historical names; behaviour is byte-identical (regression-
# checked over 4000 real node pairs).
from node_similarity import jaccard_sets as _ns_jaccard
from node_similarity import tokenize as _ns_tokenize
from node_similarity import (            # noqa: F401  (re-export)
    TYPE_COMPAT,
    TYPE_COMPAT_PROPOSED,
    type_compat,
    node_text,
    node_proof_text,
    Profile as _Profile,
)


def tokenize(text):
    """Lowercase token set (words, LaTeX commands, numbers)."""
    return _ns_tokenize(text, _Profile.ALIGNMENT)


def _raw_jaccard(ta, tb):
    return _ns_jaccard(ta, tb)


def jaccard_sim(node_a, node_b, use_type=True):
    """Jaccard similarity on name+statement+assum+concl (the 'statement' axis).

    Historical default sigma for the alignment benchmark. Kept for backward
    compatibility; new multi-dimensional analysis uses jaccard_statement/_proof.
    """
    j = _raw_jaccard(tokenize(node_text(node_a)), tokenize(node_text(node_b)))
    if use_type:
        j *= type_compat(node_a.get("type", ""), node_b.get("type", ""))
    return j


def jaccard_statement(node_a, node_b, use_type=True):
    """Sigma axis 1: Jaccard on name+statement+assumptions+conclusions only.

    Identical to jaccard_sim; kept as an explicitly-named axis for the
    multi-dimensional analysis.
    """
    return jaccard_sim(node_a, node_b, use_type=use_type)


def jaccard_proof(node_a, node_b, use_type=True):
    """Sigma axis 2: Jaccard on proof_strategy text only.

    Non-zero only when both nodes have non-empty proof_strategy fields.
    Type compatibility still applies so proof<->theorem gets damped.
    """
    ta = tokenize(node_proof_text(node_a))
    tb = tokenize(node_proof_text(node_b))
    j = _raw_jaccard(ta, tb)
    if use_type:
        j *= type_compat(node_a.get("type", ""), node_b.get("type", ""))
    return j


def jaccard_combined(node_a, node_b, use_type=True):
    """Combined sigma: Jaccard on the UNION of statement and proof_strategy
    token bags. Richer content per node -> higher signal when dimensions
    align (the common case). Edge case 'same theorem, different proof' is
    damped but still detectable when statement similarity dominates.
    """
    ta = tokenize(node_text(node_a) + " " + node_proof_text(node_a))
    tb = tokenize(node_text(node_b) + " " + node_proof_text(node_b))
    j = _raw_jaccard(ta, tb)
    if use_type:
        j *= type_compat(node_a.get("type", ""), node_b.get("type", ""))
    return j


# ── Embedding-based node similarity ─────────────────────────────────────────
# Lazy-loaded from scripts/embedding_sigma.py to avoid mandatory heavy
# dependencies (sentence-transformers) when only Jaccard is needed.

_embedding_module = None


def _load_embedding_module():
    global _embedding_module
    if _embedding_module is None:
        repo_root = Path(__file__).resolve().parents[1]
        scripts_dir = str(repo_root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import embedding_sigma as _mod
        _embedding_module = _mod
    return _embedding_module


def embedding_sim(node_a, node_b, use_type=True):
    """Embedding cosine similarity × type compatibility.

    Drop-in replacement for jaccard_sim. Requires sentence-transformers.
    """
    mod = _load_embedding_module()
    if use_type:
        return mod.sigma(node_a, node_b)
    return mod.sigma_no_type(node_a, node_b)


# Lookup table for --sigma CLI argument
SIGMA_FUNCTIONS = {
    "jaccard": jaccard_sim,
    "jaccard_statement": jaccard_statement,
    "jaccard_proof": jaccard_proof,
    "jaccard_combined": jaccard_combined,
    "embedding": embedding_sim,
}


# ── Edge similarity ──────────────────────────────────────────────────────────
def edge_sim(e_a, e_b):
    """Edge similarity: 1 if same type, 0.8 if both dependency subtypes,
    0.5 if both structural, 0.2 otherwise."""
    from edge_types import normalize_edge_type, DEPENDENCY_TYPES, STRUCTURAL_TYPES
    ra = normalize_edge_type(e_a.get("type") or e_a.get("relation_type"))
    rb = normalize_edge_type(e_b.get("type") or e_b.get("relation_type"))
    if ra == rb:
        return 1.0
    # Both dependency subtypes (uses/generalizes/specializes): high credit
    if ra in DEPENDENCY_TYPES and rb in DEPENDENCY_TYPES:
        return 0.8
    # proves↔solves: high (both "establishes" relationships)
    if {ra, rb} <= {"proves", "solves"}:
        return 0.8
    # proves↔resolves: high-ish (both "settles the truth of A", but
    # different source/target shapes: proof→theorem vs. theorem-like→
    # open_problem/conjecture).
    if {ra, rb} == {"proves", "resolves"}:
        return 0.6
    # Both structural (proves/solves/illustrates/tests/resolves): moderate credit
    if ra in STRUCTURAL_TYPES and rb in STRUCTURAL_TYPES:
        return 0.5
    # Mixed dependency/structural: low credit
    return 0.2


# ── Core alignment algorithm ─────────────────────────────────────────────────
def build_cost_matrix(nodes_a, nodes_b, sigma_fn):
    """Compute -similarity cost matrix (Hungarian minimizes)."""
    C = np.zeros((len(nodes_a), len(nodes_b)))
    for i, a in enumerate(nodes_a):
        for j, b in enumerate(nodes_b):
            C[i, j] = -sigma_fn(a, b)
    return C


def hungarian_match(nodes_a, nodes_b, C, threshold=0.1):
    """Solve assignment; filter matches below threshold.

    Returns dict node_a_id -> node_b_id and the total score.
    """
    # Pad if needed
    na, nb = len(nodes_a), len(nodes_b)
    n = max(na, nb)
    Cpad = np.zeros((n, n))
    Cpad[:na, :nb] = C
    # Padded cells have cost 0 (equivalent to not matching)
    Cpad[na:, :] = 0
    Cpad[:, nb:] = 0

    rows, cols = linear_sum_assignment(Cpad)
    matching = {}
    score = 0.0
    for i, j in zip(rows, cols):
        if i >= na or j >= nb:
            continue
        sim = -Cpad[i, j]
        if sim < threshold:
            continue
        matching[nodes_a[i]["id"]] = nodes_b[j]["id"]
        score += sim
    return matching, score


def structural_bonus(matching, nodes_a, nodes_b, edges_a, edges_b, alpha=0.5):
    """For each node pair (a, b), bonus = alpha * matched neighbors."""
    # Build neighbor lookup
    neigh_a = defaultdict(set)  # node_id -> set of neighbor_ids (out)
    for e in edges_a:
        neigh_a[e["source"]].add(e["target"])
    neigh_b = defaultdict(set)
    for e in edges_b:
        neigh_b[e["source"]].add(e["target"])

    id_of_a = {n["id"]: n for n in nodes_a}
    id_of_b = {n["id"]: n for n in nodes_b}

    B = np.zeros((len(nodes_a), len(nodes_b)))
    for i, a in enumerate(nodes_a):
        for j, b in enumerate(nodes_b):
            # Count neighbors that are also matched to each other
            a_out = neigh_a[a["id"]]
            b_out = neigh_b[b["id"]]
            matched_neighbors = sum(
                1 for an in a_out
                if an in matching and matching[an] in b_out
            )
            B[i, j] = alpha * matched_neighbors
    return B


def align_graphs(graph_a, graph_b, sigma_fn=jaccard_sim, alpha=0.5,
                 n_iters=5, threshold=0.1, verbose=False):
    """Iterative Hungarian alignment with structural refinement.

    Returns {
        'matching': dict (node_a_id -> node_b_id),
        'score': total score,
        'n_matches': number of matches,
        'iterations': number of iterations until convergence,
    }
    """
    nodes_a = graph_a.get("nodes", [])
    nodes_b = graph_b.get("nodes", [])
    edges_a = graph_a.get("edges", [])
    edges_b = graph_b.get("edges", [])

    if not nodes_a or not nodes_b:
        return {"matching": {}, "score": 0.0, "n_matches": 0, "iterations": 0}

    # Initial cost matrix (node similarity only)
    C_base = build_cost_matrix(nodes_a, nodes_b, sigma_fn)
    C = C_base.copy()

    prev_matching = None
    for it in range(n_iters):
        matching, score = hungarian_match(nodes_a, nodes_b, C, threshold=threshold)
        if matching == prev_matching:
            if verbose:
                print(f"  converged at iteration {it}")
            break
        prev_matching = matching
        # Add structural bonus
        B = structural_bonus(matching, nodes_a, nodes_b, edges_a, edges_b, alpha=alpha)
        C = C_base - B

    # Final score: node + edge
    node_score = sum(sigma_fn(next(n for n in nodes_a if n["id"] == aid),
                               next(n for n in nodes_b if n["id"] == bid))
                     for aid, bid in matching.items())
    # Edge score: count matched edges
    matched_edges = 0
    for e1 in edges_a:
        s1, t1 = matching.get(e1["source"]), matching.get(e1["target"])
        if s1 and t1:
            for e2 in edges_b:
                if e2["source"] == s1 and e2["target"] == t1:
                    matched_edges += alpha * edge_sim(e1, e2)
                    break
    total_score = node_score + matched_edges

    return {
        "matching": matching,
        "score": total_score,
        "node_score": node_score,
        "edge_score": matched_edges,
        "n_matches": len(matching),
        "iterations": it + 1,
    }


# ── Soft (threshold-free) precision/recall/F1 ────────────────────────────────
# Computed *after* Hungarian alignment, from the matched-pair list. Done this
# way (rather than baked into the solver) so that future many-to-one (B^3)
# extensions can plug in an alternative matching producer and reuse these
# metrics unchanged. Strict (threshold-based) metrics are still produced by
# the existing call sites; soft metrics live alongside them.
def soft_metrics(matching, graph_a, graph_b, sigma_fn=jaccard_sim, alpha=0.5,
                 edge_type_match_factor=0.5):
    """Threshold-free P/R/F1 from a Hungarian (or any 1-1) matching.

    Node side
    ---------
        P_soft = sum(sigma over matched pairs) / |graph_a.nodes|
        R_soft = sum(sigma over matched pairs) / |graph_b.nodes|
        F1_soft = 2 P R / (P + R)

    The same formulas apply for the dual-use case (cross-paper alignment OR
    same-paper extraction comparison): graph_a is the "predicted" / LLM /
    extracted side; graph_b is the "reference" / gold side. Names follow the
    convention already used by score_matching() in graph_alignment_eval.py.

    Edge side
    ---------
    For each matched edge pair, edge_score = sigma(src_pair) * sigma(tgt_pair) *
    type_factor, where type_factor = 1.0 if edge types match (under edge_sim
    equivalence => edge_sim == 1.0) and `edge_type_match_factor` (default 0.5)
    otherwise. Same denominators as nodes (|edges_a|, |edges_b|).

    Returns a dict with both node_* and edge_* soft metrics, plus a
    `matched_pairs` list of (a_id, b_id, sigma) for inspection.
    """
    nodes_a = graph_a.get("nodes", [])
    nodes_b = graph_b.get("nodes", [])
    edges_a = graph_a.get("edges", [])
    edges_b = graph_b.get("edges", [])

    a_by_id = {n["id"]: n for n in nodes_a}
    b_by_id = {n["id"]: n for n in nodes_b}

    # Per-pair sigma from the matching
    pair_sigma = {}
    for aid, bid in matching.items():
        if aid in a_by_id and bid in b_by_id:
            pair_sigma[(aid, bid)] = sigma_fn(a_by_id[aid], b_by_id[bid])

    sigma_sum = sum(pair_sigma.values())
    n_a = len(nodes_a)
    n_b = len(nodes_b)
    p_node = sigma_sum / n_a if n_a else 0.0
    r_node = sigma_sum / n_b if n_b else 0.0
    f1_node = (2 * p_node * r_node / (p_node + r_node)) if (p_node + r_node) else 0.0

    # Edge soft scoring. For every edge in A whose both endpoints are
    # matched, look for the corresponding edge in B (src1 -> src2 mapped).
    # If found, contribute sigma(src) * sigma(tgt) * type_factor.
    edge_score_sum = 0.0
    # Index B-edges by (source, target) for quick lookup
    edges_b_by_pair = defaultdict(list)
    for e in edges_b:
        edges_b_by_pair[(e["source"], e["target"])].append(e)

    for e1 in edges_a:
        s1 = matching.get(e1["source"])
        t1 = matching.get(e1["target"])
        if not (s1 and t1):
            continue
        cand = edges_b_by_pair.get((s1, t1))
        if not cand:
            continue
        # Best candidate by edge_sim
        e2 = max(cand, key=lambda e: edge_sim(e1, e))
        type_factor = 1.0 if edge_sim(e1, e2) == 1.0 else edge_type_match_factor
        sig_src = pair_sigma.get((e1["source"], s1), 0.0)
        sig_tgt = pair_sigma.get((e1["target"], t1), 0.0)
        edge_score_sum += sig_src * sig_tgt * type_factor

    n_ea = len(edges_a)
    n_eb = len(edges_b)
    p_edge = edge_score_sum / n_ea if n_ea else 0.0
    r_edge = edge_score_sum / n_eb if n_eb else 0.0
    f1_edge = (2 * p_edge * r_edge / (p_edge + r_edge)) if (p_edge + r_edge) else 0.0

    return {
        "precision_soft": p_node,
        "recall_soft": r_node,
        "f1_soft": f1_node,
        "edge_precision_soft": p_edge,
        "edge_recall_soft": r_edge,
        "edge_f1_soft": f1_edge,
        "sigma_sum": sigma_sum,
        "edge_score_sum": edge_score_sum,
        "matched_pairs": [
            {"a_id": aid, "b_id": bid, "sigma": s}
            for (aid, bid), s in pair_sigma.items()
        ],
    }


# ── Statistical significance: Monte Carlo permutation test ──────────────────
def significance_test(graph_a, graph_b, observed_score, sigma_fn=jaccard_sim,
                      alpha=0.5, n_perms=1000, seed=42, verbose=False):
    """Compute z-score and permutation p-value by shuffling node features.

    Shuffling: randomly permute the nodes of graph_b (keep topology, reassign
    text content via permutation of node identities within B).

    Returns dict with 'z_score', 'p_value', 'null_mean', 'null_std', 'null_scores'.
    """
    import random
    rng = random.Random(seed)

    nodes_b = graph_b.get("nodes", [])
    if len(nodes_b) < 2:
        return {"z_score": 0.0, "p_value": 1.0, "null_mean": 0.0,
                "null_std": 1.0, "null_scores": []}

    null_scores = []
    for t in range(n_perms):
        # Shuffle node identities in B (keep edges with same source/target ids,
        # but the underlying content gets swapped).
        # To do this cleanly: permute the node list, re-id to original ids.
        perm = list(range(len(nodes_b)))
        rng.shuffle(perm)
        shuffled_nodes = []
        original_ids = [n["id"] for n in nodes_b]
        for new_idx, old_idx in enumerate(perm):
            # Keep original id (so edges still match) but swap the content
            n_new = dict(nodes_b[old_idx])
            n_new["id"] = original_ids[new_idx]
            shuffled_nodes.append(n_new)
        shuffled_graph = {"nodes": shuffled_nodes, "edges": graph_b.get("edges", [])}
        result = align_graphs(graph_a, shuffled_graph, sigma_fn=sigma_fn,
                               alpha=alpha, n_iters=3, verbose=False)
        null_scores.append(result["score"])
        if verbose and t % 100 == 0:
            print(f"  perm {t}/{n_perms}: score={result['score']:.2f}")

    null_arr = np.array(null_scores)
    mu = null_arr.mean()
    sd = null_arr.std() + 1e-9
    z = (observed_score - mu) / sd
    p = (1 + int((null_arr >= observed_score).sum())) / (1 + n_perms)

    return {
        "z_score": float(z),
        "p_value": float(p),
        "null_mean": float(mu),
        "null_std": float(sd),
        "null_scores": null_scores,
    }


# ── Origin filtering helper ─────────────────────────────────────────────────
def _drop_origin(graph, exclude):
    """Return a copy of `graph` with nodes whose `origin` matches `exclude`
    removed (along with any incident edges). Nodes without an `origin` field
    default to 'paper' for backwards compatibility.
    """
    keep_ids = set()
    kept_nodes = []
    for n in graph.get("nodes", []):
        origin = n.get("origin", "paper")
        if origin == exclude:
            continue
        kept_nodes.append(n)
        if n.get("id"):
            keep_ids.add(n["id"])
    kept_edges = [
        e for e in graph.get("edges", [])
        if e.get("source") in keep_ids and e.get("target") in keep_ids
    ]
    out = dict(graph)
    out["nodes"] = kept_nodes
    out["edges"] = kept_edges
    return out


# ── CLI for testing ──────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph_a", help="Path to first paper JSON")
    parser.add_argument("graph_b", help="Path to second paper JSON")
    parser.add_argument("--sigma", choices=list(SIGMA_FUNCTIONS.keys()),
                        default="jaccard",
                        help="Node similarity function (default: jaccard)")
    parser.add_argument("--n-perms", type=int, default=500,
                        help="Number of permutations for significance (default 500)")
    parser.add_argument("--alpha", type=float, default=0.5,
                        help="Edge-match weight (default 0.5)")
    parser.add_argument("--skip-significance", action="store_true")
    parser.add_argument("--exclude-origin", choices=["external", "paper"],
                        default=None,
                        help="Drop nodes (and incident edges) with the given "
                             "origin value before alignment. Default sigma "
                             "treats external nodes as first-class; pass "
                             "'external' to score paper-only graphs.")
    args = parser.parse_args()

    sigma_fn = SIGMA_FUNCTIONS[args.sigma]

    with open(args.graph_a) as f:
        g_a = json.load(f)
    with open(args.graph_b) as f:
        g_b = json.load(f)

    if args.exclude_origin:
        g_a = _drop_origin(g_a, args.exclude_origin)
        g_b = _drop_origin(g_b, args.exclude_origin)
        print(f"--exclude-origin {args.exclude_origin}: nodes filtered.")

    print(f"Graph A: {args.graph_a}")
    print(f"  {len(g_a['nodes'])} nodes, {len(g_a.get('edges', []))} edges")
    print(f"Graph B: {args.graph_b}")
    print(f"  {len(g_b['nodes'])} nodes, {len(g_b.get('edges', []))} edges")
    print(f"Sigma:  {args.sigma}")

    print("\n=== Alignment ===")
    result = align_graphs(g_a, g_b, sigma_fn=sigma_fn, alpha=args.alpha)
    print(f"Total score: {result['score']:.3f}")
    print(f"  node component: {result['node_score']:.3f}")
    print(f"  edge component: {result['edge_score']:.3f}")
    print(f"Matches: {result['n_matches']}")
    print(f"Iterations: {result['iterations']}")
    print("\nMatched pairs:")
    # Look up names
    a_by_id = {n["id"]: n for n in g_a["nodes"]}
    b_by_id = {n["id"]: n for n in g_b["nodes"]}
    for aid, bid in sorted(result["matching"].items()):
        a = a_by_id[aid]
        b = b_by_id[bid]
        sim = sigma_fn(a, b)
        print(f"  {aid} ({a.get('type','')}) <-> {bid} ({b.get('type','')})  "
              f"sim={sim:.3f}")
        print(f"    A: {a.get('name','')[:70]}")
        print(f"    B: {b.get('name','')[:70]}")

    if not args.skip_significance:
        print(f"\n=== Significance (n_perms={args.n_perms}) ===")
        sig = significance_test(g_a, g_b, result["score"],
                                 sigma_fn=sigma_fn, alpha=args.alpha,
                                 n_perms=args.n_perms)
        print(f"Observed score: {result['score']:.3f}")
        print(f"Null mean:      {sig['null_mean']:.3f}")
        print(f"Null std:       {sig['null_std']:.3f}")
        print(f"Z-score:        {sig['z_score']:.2f}")
        print(f"p-value:        {sig['p_value']:.4f}")
        if sig["z_score"] > 6:
            print("  => VERY SIGNIFICANT cross-paper correspondence")
        elif sig["z_score"] > 3:
            print("  => mildly significant")
        else:
            print("  => not significantly different from random")


if __name__ == "__main__":
    main()
