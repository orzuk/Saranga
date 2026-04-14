#!/usr/bin/env python3
"""Evaluate graph alignment against a gold-standard manual alignment.

Computes:
  - Score(Hungarian) vs Score(manual)  --> how well sigma ranks true matches
  - Precision/Recall/F1 on matched pairs
  - Z-score vs null for both matchings

Usage:
  python graph_alignment_eval.py paper_A.json paper_B.json alignment.json
"""
import json
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_alignment import (
    align_graphs, significance_test, jaccard_sim,
    build_cost_matrix, edge_sim,
)


def score_matching(matching, graph_a, graph_b, sigma_fn=jaccard_sim, alpha=0.5):
    """Compute score of a given matching under sigma_fn."""
    a_by_id = {n["id"]: n for n in graph_a.get("nodes", [])}
    b_by_id = {n["id"]: n for n in graph_b.get("nodes", [])}

    node_score = 0.0
    for aid, bid in matching.items():
        if aid in a_by_id and bid in b_by_id:
            node_score += sigma_fn(a_by_id[aid], b_by_id[bid])

    # Edge score
    edge_score = 0.0
    for e1 in graph_a.get("edges", []):
        s1 = matching.get(e1["source"])
        t1 = matching.get(e1["target"])
        if s1 and t1:
            for e2 in graph_b.get("edges", []):
                if e2["source"] == s1 and e2["target"] == t1:
                    edge_score += alpha * edge_sim(e1, e2)
                    break

    return {"node_score": node_score, "edge_score": edge_score,
            "total": node_score + edge_score}


def parse_alignment(alignment_json):
    """Parse the cs_alignment.json format into a gold matching dict.

    Returns: dict mapping node_a_id -> node_b_id (one-to-one for strong matches).
    Many-to-many matches are expanded as multiple pairs.
    """
    gold_pairs = set()  # set of (a_id, b_id)
    for m in alignment_json.get("matches", []):
        mtype = m.get("match_type", "").lower()
        # Only consider strong matches for precision/recall
        if mtype not in ("exact", "analogous"):
            continue
        for a_id in m.get("paper2_nodes", []):  # paper 2 is CT in this alignment
            for b_id in m.get("paper21_nodes", []):  # paper 21 is Donoho
                gold_pairs.add((a_id, b_id))
    return gold_pairs


def precision_recall(pred_matching, gold_pairs):
    """Compute P/R/F1 treating matching as a set of (a, b) pairs."""
    pred_pairs = set((a, b) for a, b in pred_matching.items())
    tp = pred_pairs & gold_pairs
    fp = pred_pairs - gold_pairs
    fn = gold_pairs - pred_pairs
    precision = len(tp) / len(pred_pairs) if pred_pairs else 0.0
    recall = len(tp) / len(gold_pairs) if gold_pairs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph_a")
    parser.add_argument("graph_b")
    parser.add_argument("alignment",
                        help="Gold alignment JSON (e.g., cs_alignment.json)")
    parser.add_argument("--n-perms", type=int, default=500)
    parser.add_argument("--alpha", type=float, default=0.5)
    args = parser.parse_args()

    with open(args.graph_a) as f:
        g_a = json.load(f)
    with open(args.graph_b) as f:
        g_b = json.load(f)
    with open(args.alignment) as f:
        gold_json = json.load(f)

    gold_pairs = parse_alignment(gold_json)
    # Convert to a matching dict (a -> b) for scoring
    # If many-to-many, pick one b per a (first)
    gold_matching = {}
    for a, b in gold_pairs:
        if a not in gold_matching:
            gold_matching[a] = b

    print(f"Paper A: {args.graph_a}")
    print(f"  {len(g_a['nodes'])} nodes")
    print(f"Paper B: {args.graph_b}")
    print(f"  {len(g_b['nodes'])} nodes")
    print(f"Gold alignment: {len(gold_pairs)} strong pairs (exact/analogous)")

    # --- Run Hungarian
    print("\n=== Running Hungarian alignment (Jaccard sigma) ===")
    hung_result = align_graphs(g_a, g_b, sigma_fn=jaccard_sim, alpha=args.alpha)
    print(f"Hungarian: {hung_result['n_matches']} matches, "
          f"score {hung_result['score']:.3f}")

    # --- Compute gold score under same sigma
    gold_score = score_matching(gold_matching, g_a, g_b,
                                 sigma_fn=jaccard_sim, alpha=args.alpha)
    print(f"Gold matching (under Jaccard sigma): "
          f"score {gold_score['total']:.3f}")

    delta = hung_result["score"] - gold_score["total"]
    print(f"\n{'='*60}")
    print(f"SCORE GAP Delta = Score(Hungarian) - Score(Gold) = {delta:.3f}")
    if delta > 0.1:
        print("  -> Hungarian found HIGHER-scoring matching than gold.")
        print("  -> sigma is actively MISLEADING (prefers wrong matches).")
    elif abs(delta) <= 0.1:
        print("  -> Gold and Hungarian score similarly.")
        print("  -> sigma is flat/ambiguous (can't distinguish right from wrong).")
    else:
        print("  -> Hungarian scored lower than gold (unusual — check sigma).")

    # --- Precision/recall
    print(f"\n{'='*60}")
    print("PRECISION / RECALL vs GOLD")
    pr_hung = precision_recall(hung_result["matching"], gold_pairs)
    print(f"Hungarian: P={pr_hung['precision']:.2f}, "
          f"R={pr_hung['recall']:.2f}, F1={pr_hung['f1']:.2f}")
    print(f"  TP ({len(pr_hung['tp'])}): {pr_hung['tp']}")
    print(f"  FP ({len(pr_hung['fp'])}): {pr_hung['fp'][:5]}...")
    print(f"  FN ({len(pr_hung['fn'])}): {pr_hung['fn']}")

    # --- Z-score for both
    print(f"\n{'='*60}")
    print(f"STATISTICAL SIGNIFICANCE (n_perms={args.n_perms})")
    print("Computing null distribution for Hungarian...")
    sig_hung = significance_test(g_a, g_b, hung_result["score"],
                                  sigma_fn=jaccard_sim, alpha=args.alpha,
                                  n_perms=args.n_perms)
    print(f"  Hungarian Z={sig_hung['z_score']:.2f}, "
          f"p={sig_hung['p_value']:.4f}")

    # For the manual/gold: we already have the score; use same null
    null_mean, null_std = sig_hung["null_mean"], sig_hung["null_std"]
    z_gold = (gold_score["total"] - null_mean) / null_std
    from numpy import array
    null_arr = array(sig_hung["null_scores"])
    p_gold = (1 + int((null_arr >= gold_score["total"]).sum())) / (1 + args.n_perms)
    print(f"  Gold      Z={z_gold:.2f}, p={p_gold:.4f}")

    print(f"\n{'='*60}")
    print("BASELINE ROW (Jaccard sigma):")
    print(f"  Score(Hungarian) = {hung_result['score']:.2f}")
    print(f"  Score(Gold)      = {gold_score['total']:.2f}")
    print(f"  Delta            = {delta:.2f}")
    print(f"  Precision        = {pr_hung['precision']:.2f}")
    print(f"  Recall           = {pr_hung['recall']:.2f}")
    print(f"  F1               = {pr_hung['f1']:.2f}")
    print(f"  Z(Hungarian)     = {sig_hung['z_score']:.2f}")
    print(f"  Z(Gold)          = {z_gold:.2f}")


if __name__ == "__main__":
    main()
