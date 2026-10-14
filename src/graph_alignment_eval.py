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
    build_cost_matrix, edge_sim, soft_metrics,
)
from node_similarity import prf


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


def load_json(p):
    with open(p) as f:
        return json.load(f)


def resolve_path(name: str, paths: dict, config_dir: Path) -> Path:
    """Resolve a path reference of a benchmark config.

    Accepts these forms:
      "course:paper1_gold.json"    -> paths['course_papers_dir'] / name
      "bench:paper101_gold.json"   -> paths['bench_papers_dir'] / name
      "/abs/path.json"             -> as-is
      "./rel/path.json"            -> config_dir / path
      "rel/path.json"              -> config_dir / path
    """
    if ":" in name and not name.startswith(("/", ".", "\\")):
        prefix, _, rest = name.partition(":")
        # Try {prefix}_papers_dir, {prefix}_dir, then "alignments_dir"
        # for prefix=="align".
        keys_to_try = [f"{prefix}_papers_dir", f"{prefix}_dir"]
        if prefix == "align":
            keys_to_try.append("alignments_dir")
        for key in keys_to_try:
            if key in paths:
                base = Path(paths[key])
                if not base.is_absolute():
                    base = (config_dir / base).resolve()
                return base / rest
        # fallback
        return config_dir / rest
    p = Path(name)
    if p.is_absolute():
        return p
    return (config_dir / p).resolve()


def parse_gold_pairs(alignment_json, key_a, key_b):
    """Strong (exact/analogous) gold pairs (a_id, b_id) of an alignment JSON;
    many-to-many matches are expanded as multiple pairs. `key_a`/`key_b` name
    the node lists (cs_alignment.json: paper2_nodes, paper21_nodes)."""
    pairs = set()
    for m in alignment_json.get("matches", []):
        if (m.get("match_type") or "").lower() not in ("exact", "analogous"):
            continue
        for a in m.get(key_a) or []:
            for b in m.get(key_b) or []:
                pairs.add((a, b))
    return pairs


def gold_matching(gold_pairs):
    """The gold pairs as a matching dict a -> b, for scoring: the first b per a."""
    out = {}
    for a, b in gold_pairs:
        out.setdefault(a, b)
    return out


def precision_recall(pred_matching, gold_pairs):
    """Strict P/R/F1 treating matching as a set of (a, b) pairs; tp/fp/fn are
    the sorted pairs. Soft (threshold-free) variants: precision_recall_soft()."""
    pred_pairs = set(pred_matching.items())
    tp, fp, fn = pred_pairs & gold_pairs, pred_pairs - gold_pairs, gold_pairs - pred_pairs
    precision, recall, f1 = prf(len(tp), len(tp), len(fp), len(fn))
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn)}


def precision_recall_soft(pred_matching, graph_a, graph_b,
                          sigma_fn=jaccard_sim, alpha=0.5):
    """Soft (threshold-free) P/R/F1 using continuous sigma scores.

    Thin wrapper around graph_alignment.soft_metrics() so callers that already
    work in the (matching, graph_a, graph_b) idiom can get soft node + edge
    metrics in one call. ADDED — does not replace precision_recall().
    """
    return soft_metrics(pred_matching, graph_a, graph_b,
                        sigma_fn=sigma_fn, alpha=alpha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph_a")
    parser.add_argument("graph_b")
    parser.add_argument("alignment",
                        help="Gold alignment JSON (e.g., cs_alignment.json)")
    parser.add_argument("--n-perms", type=int, default=500)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--key-a", default="paper2_nodes", help="node list of paper A in the alignment JSON")
    parser.add_argument("--key-b", default="paper21_nodes", help="node list of paper B in the alignment JSON")
    args = parser.parse_args()

    g_a, g_b = load_json(args.graph_a), load_json(args.graph_b)
    gold_pairs = parse_gold_pairs(load_json(args.alignment), args.key_a, args.key_b)

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
    gold_score = score_matching(gold_matching(gold_pairs), g_a, g_b,
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
    print(f"Hungarian (strict): P={pr_hung['precision']:.2f}, "
          f"R={pr_hung['recall']:.2f}, F1={pr_hung['f1']:.2f}")
    print(f"  TP ({len(pr_hung['tp'])}): {pr_hung['tp']}")
    print(f"  FP ({len(pr_hung['fp'])}): {pr_hung['fp'][:5]}...")
    print(f"  FN ({len(pr_hung['fn'])}): {pr_hung['fn']}")

    # Soft (threshold-free) metrics — additive, do not replace strict above
    pr_soft = precision_recall_soft(hung_result["matching"], g_a, g_b,
                                    sigma_fn=jaccard_sim, alpha=args.alpha)
    print(f"Hungarian (soft):   P={pr_soft['precision_soft']:.2f}, "
          f"R={pr_soft['recall_soft']:.2f}, F1={pr_soft['f1_soft']:.2f}")
    print(f"  edge soft:        P={pr_soft['edge_precision_soft']:.2f}, "
          f"R={pr_soft['edge_recall_soft']:.2f}, F1={pr_soft['edge_f1_soft']:.2f}")

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
