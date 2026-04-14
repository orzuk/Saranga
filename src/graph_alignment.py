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
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment


# ── Type compatibility matrix ────────────────────────────────────────────────
# Rewards theorem↔theorem, lemma↔theorem somewhat, etc.
TYPE_COMPAT = {
    # Same type = 1.0 (diagonal)
    # Cross-theorem-like = 0.9
    # Definition/Proof = more restrictive
    ("theorem", "theorem"): 1.0,
    ("theorem", "lemma"): 0.9, ("theorem", "proposition"): 0.9, ("theorem", "corollary"): 0.85,
    ("lemma", "lemma"): 1.0, ("lemma", "proposition"): 0.9, ("lemma", "corollary"): 0.85,
    ("proposition", "proposition"): 1.0, ("proposition", "corollary"): 0.85,
    ("corollary", "corollary"): 1.0,
    ("definition", "definition"): 1.0,
    ("definition", "theorem"): 0.1, ("definition", "lemma"): 0.1,
    ("proof", "proof"): 1.0,
    ("claim", "claim"): 1.0, ("claim", "theorem"): 0.8, ("claim", "lemma"): 0.8,
    ("algorithm", "algorithm"): 1.0,
    ("equation", "equation"): 1.0,
}


def type_compat(ta, tb):
    """Get type compatibility score, symmetric."""
    if (ta, tb) in TYPE_COMPAT:
        return TYPE_COMPAT[(ta, tb)]
    if (tb, ta) in TYPE_COMPAT:
        return TYPE_COMPAT[(tb, ta)]
    return 0.3  # unknown pair default


# ── Node similarity functions ────────────────────────────────────────────────
_TOKEN_RE = re.compile(r"[a-zA-Z]+|\\[a-zA-Z]+|[0-9]+")


def tokenize(text):
    """Lowercase token set from text (words, LaTeX commands, numbers)."""
    if not text:
        return set()
    return set(t.lower() for t in _TOKEN_RE.findall(str(text)))


def node_text(n):
    """Concatenate all text content of a node (name, statement, assum, concl)."""
    parts = [n.get("name", ""), n.get("statement", "")]
    for fld in ("assumptions", "conclusions"):
        v = n.get(fld)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
        elif v:
            parts.append(str(v))
    return " ".join(parts)


def node_proof_text(n):
    """Proof-side text: proof_strategy field only (empty for non-proof nodes)."""
    v = n.get("proof_strategy")
    return str(v) if v else ""


def _raw_jaccard(ta, tb):
    if not ta and not tb:
        return 0.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


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


# ── Edge similarity ──────────────────────────────────────────────────────────
def edge_sim(e_a, e_b):
    """Edge similarity: 1 if same type, 0.5 if different, 0 if types incompatible."""
    ra = e_a.get("type", "uses")
    rb = e_b.get("type", "uses")
    if ra == rb:
        return 1.0
    # Both structural ("uses"/"proves"/etc.) get partial credit
    return 0.5


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


# ── CLI for testing ──────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph_a", help="Path to first paper JSON")
    parser.add_argument("graph_b", help="Path to second paper JSON")
    parser.add_argument("--n-perms", type=int, default=500,
                        help="Number of permutations for significance (default 500)")
    parser.add_argument("--alpha", type=float, default=0.5,
                        help="Edge-match weight (default 0.5)")
    parser.add_argument("--skip-significance", action="store_true")
    args = parser.parse_args()

    with open(args.graph_a) as f:
        g_a = json.load(f)
    with open(args.graph_b) as f:
        g_b = json.load(f)

    print(f"Graph A: {args.graph_a}")
    print(f"  {len(g_a['nodes'])} nodes, {len(g_a.get('edges', []))} edges")
    print(f"Graph B: {args.graph_b}")
    print(f"  {len(g_b['nodes'])} nodes, {len(g_b.get('edges', []))} edges")

    print("\n=== Alignment ===")
    result = align_graphs(g_a, g_b, sigma_fn=jaccard_sim, alpha=args.alpha)
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
        sim = jaccard_sim(a, b)
        print(f"  {aid} ({a.get('type','')}) <-> {bid} ({b.get('type','')})  "
              f"sim={sim:.2f}")
        print(f"    A: {a.get('name','')[:70]}")
        print(f"    B: {b.get('name','')[:70]}")

    if not args.skip_significance:
        print(f"\n=== Significance (n_perms={args.n_perms}) ===")
        sig = significance_test(g_a, g_b, result["score"],
                                 sigma_fn=jaccard_sim, alpha=args.alpha,
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
