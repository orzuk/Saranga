#!/usr/bin/env python3
"""
Evaluate an automatically extracted JSON annotation against a gold standard.

Computes precision, recall, and F1 for both node detection and edge detection.
Node matching is based on Jaccard similarity of statement text.
Edge matching is based on whether both endpoints were matched to connected gold nodes.

Usage:
    python evaluate_extraction.py --extracted output.json --gold gold.json
    python evaluate_extraction.py --extracted output.json --gold gold.json --threshold 0.5
    python evaluate_extraction.py --extracted output.json --gold gold.json --csv results.csv
"""

import argparse
import json
import sys
import csv
from collections import defaultdict


def load_annotation(path):
    """Load nodes and edges from a JSON annotation file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes", data.get("objects", []))
    edges = data.get("edges", data.get("relations", []))
    return nodes, edges


def tokenize(text):
    """Simple whitespace + punctuation tokenizer for Jaccard computation."""
    if not text:
        return set()
    text = text.lower()
    for ch in ".,;:!?()[]{}\"'`\\/|<>=+-*^~#@$%&_":
        text = text.replace(ch, " ")
    return set(text.split())


def jaccard(text_a, text_b):
    """Jaccard similarity between two text strings."""
    tokens_a = tokenize(text_a)
    tokens_b = tokenize(text_b)
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def node_text(node):
    """Extract the primary text content of a node for matching."""
    parts = []
    if node.get("statement"):
        parts.append(node["statement"])
    if node.get("assumptions"):
        parts.extend(node["assumptions"])
    if node.get("conclusions"):
        parts.extend(node["conclusions"])
    return " ".join(parts)


def node_id_parts(node):
    """Extract (type_letter, chapter, seq) from a node ID like 'T2.1'."""
    nid = node.get("id", "")
    import re
    m = re.match(r'^([A-Z])(\d+)\.(\d+)$', nid)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None, None, None


def match_nodes(extracted, gold, threshold):
    """
    Match extracted nodes to gold nodes using greedy best-match.
    Uses text Jaccard similarity, boosted by matching node IDs.
    Returns (matches, unmatched_extracted, unmatched_gold).
    Each match is (extracted_node, gold_node, similarity, type_match).
    Also returns the ID mapping: ext_id -> gold_id.
    """
    ID_BOOST = 0.3  # bonus for matching node IDs (same type letter + sequence)

    sims = []
    for i, ext in enumerate(extracted):
        for j, gld in enumerate(gold):
            # Proof nodes: match by "proves" field instead of statement text
            if ext.get("type") == "proof" and gld.get("type") == "proof":
                ext_proves = ext.get("proves", "")
                gld_proves = gld.get("proves", "")
                if ext_proves and gld_proves and ext_proves == gld_proves:
                    sim = 1.0  # exact match on proves field
                else:
                    sim = 0.0  # no match if proves fields differ
            else:
                sim = jaccard(node_text(ext), node_text(gld))
            # Boost if node IDs match (e.g., both are T2.1)
            ext_parts = node_id_parts(ext)
            gld_parts = node_id_parts(gld)
            if ext_parts[0] and gld_parts[0]:
                if ext_parts == gld_parts:
                    sim = min(1.0, sim + ID_BOOST)
                elif ext_parts[0] == gld_parts[0] and ext_parts[2] == gld_parts[2]:
                    # Same type and sequence, different chapter (unlikely but possible)
                    sim = min(1.0, sim + ID_BOOST * 0.5)
            if sim >= threshold:
                sims.append((sim, i, j))

    sims.sort(reverse=True)
    used_ext = set()
    used_gld = set()
    matches = []
    id_map = {}  # ext_id -> gold_id

    for sim, i, j in sims:
        if i in used_ext or j in used_gld:
            continue
        used_ext.add(i)
        used_gld.add(j)
        type_match = extracted[i].get("type") == gold[j].get("type")
        matches.append((extracted[i], gold[j], sim, type_match))
        ext_id = extracted[i].get("id")
        gld_id = gold[j].get("id")
        if ext_id and gld_id:
            id_map[ext_id] = gld_id

    unmatched_ext = [extracted[i] for i in range(len(extracted)) if i not in used_ext]
    unmatched_gld = [gold[j] for j in range(len(gold)) if j not in used_gld]

    return matches, unmatched_ext, unmatched_gld, id_map


def match_edges(ext_edges, gold_edges, id_map, flipped_credit=0.5):
    """
    Match extracted edges to gold edges based on node ID mapping.
    An extracted edge (s, t) is correct if id_map[s] -> id_map[t] exists in gold.
    A flipped edge (t, s) where (s, t) is in gold gets partial credit.

    Returns (matched_ext, flipped_ext, unmatched_ext, unmatched_gold).
    matched_ext: exact direction matches (count as 1.0 each)
    flipped_ext: correct endpoints but wrong direction (count as flipped_credit each)
    """
    # Build set of gold edges (as pairs of gold IDs)
    gold_edge_set = set()
    for e in gold_edges:
        src = e.get("source")
        tgt = e.get("target")
        if src and tgt:
            gold_edge_set.add((src, tgt))

    matched_ext = []
    flipped_ext = []
    unmatched_ext = []
    matched_gold = set()
    flipped_gold = set()

    for e in ext_edges:
        ext_src = e.get("source")
        ext_tgt = e.get("target")
        if not ext_src or not ext_tgt:
            unmatched_ext.append(e)
            continue

        # Map extracted node IDs to gold node IDs
        gold_src = id_map.get(ext_src)
        gold_tgt = id_map.get(ext_tgt)

        if gold_src and gold_tgt and (gold_src, gold_tgt) in gold_edge_set:
            matched_ext.append(e)
            matched_gold.add((gold_src, gold_tgt))
        elif gold_src and gold_tgt and (gold_tgt, gold_src) in gold_edge_set:
            flipped_ext.append(e)
            flipped_gold.add((gold_tgt, gold_src))
        else:
            unmatched_ext.append(e)

    unmatched_gold = [e for e in gold_edges
                      if (e.get("source"), e.get("target")) not in matched_gold
                      and (e.get("source"), e.get("target")) not in flipped_gold]

    return matched_ext, flipped_ext, unmatched_ext, unmatched_gold


def compute_metrics(tp, fp, fn, partial_tp=0, partial_weight=0.5):
    """Compute precision, recall, F1 from counts, with optional partial credit.

    partial_tp: number of partial matches (e.g., flipped edges)
    partial_weight: credit per partial match (default 0.5)
    """
    effective_tp = tp + partial_tp * partial_weight
    total_pred = tp + partial_tp + fp
    total_gold = tp + partial_tp + fn
    precision = effective_tp / total_pred if total_pred > 0 else 0.0
    recall = effective_tp / total_gold if total_gold > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"tp": tp, "partial_tp": partial_tp, "fp": fp, "fn": fn,
            "effective_tp": effective_tp,
            "precision": precision, "recall": recall, "f1": f1}


def per_type_metrics(matches, unmatched_ext, unmatched_gld, extracted, gold):
    """Compute node metrics broken down by node type."""
    all_types = set()
    for n in extracted + gold:
        all_types.add(n.get("type", "unknown"))

    results = {}
    for ntype in sorted(all_types):
        type_matches = [(e, g, s, tm) for e, g, s, tm in matches
                        if g.get("type") == ntype]
        type_fp = [n for n in unmatched_ext if n.get("type") == ntype]
        type_fn = [n for n in unmatched_gld if n.get("type") == ntype]
        results[ntype] = compute_metrics(len(type_matches), len(type_fp), len(type_fn))
    return results


def print_results(node_overall, node_per_type, node_matches,
                  unmatched_ext, unmatched_gld,
                  edge_overall):
    """Print evaluation results to stdout."""
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)

    # --- Node results ---
    print("\n--- NODES ---")
    print(f"Overall:  P={node_overall['precision']:.3f}  R={node_overall['recall']:.3f}  "
          f"F1={node_overall['f1']:.3f}  "
          f"(TP={node_overall['tp']} FP={node_overall['fp']} FN={node_overall['fn']})")

    print(f"\n{'Type':<15} {'Prec':>6} {'Rec':>6} {'F1':>6} {'TP':>4} {'FP':>4} {'FN':>4}")
    print("-" * 50)
    for ntype, m in node_per_type.items():
        print(f"{ntype:<15} {m['precision']:>6.3f} {m['recall']:>6.3f} {m['f1']:>6.3f} "
              f"{m['tp']:>4d} {m['fp']:>4d} {m['fn']:>4d}")

    # Type accuracy among matched nodes
    type_correct = sum(1 for _, _, _, tm in node_matches if tm)
    if node_matches:
        print(f"\nType accuracy (among matched nodes): "
              f"{type_correct}/{len(node_matches)} = {type_correct/len(node_matches):.3f}")

    # Average similarity of matches
    if node_matches:
        avg_sim = sum(s for _, _, s, _ in node_matches) / len(node_matches)
        print(f"Average Jaccard similarity of matches: {avg_sim:.3f}")

    # --- Edge results ---
    print("\n--- EDGES ---")
    partial = edge_overall.get('partial_tp', 0)
    partial_str = f" Flipped={partial}" if partial else ""
    print(f"Overall:  P={edge_overall['precision']:.3f}  R={edge_overall['recall']:.3f}  "
          f"F1={edge_overall['f1']:.3f}  "
          f"(TP={edge_overall['tp']}{partial_str} FP={edge_overall['fp']} FN={edge_overall['fn']})")
    if partial:
        print(f"  (Flipped edges get 0.5 credit: effective TP = {edge_overall['effective_tp']:.1f})")

    # --- Combined score ---
    combined_f1 = (node_overall["f1"] + edge_overall["f1"]) / 2
    print(f"\n--- COMBINED SCORE ---")
    print(f"Average(node_F1, edge_F1) = ({node_overall['f1']:.3f} + "
          f"{edge_overall['f1']:.3f}) / 2 = {combined_f1:.3f}")

    # --- Error samples ---
    if unmatched_ext:
        print(f"\nFalse positive nodes (extracted but not in gold): {len(unmatched_ext)}")
        for n in unmatched_ext[:5]:
            stmt = (n.get("statement") or "")[:80]
            print(f"  [{n.get('type','?'):>10}] {n.get('id','?')}: {stmt}")
        if len(unmatched_ext) > 5:
            print(f"  ... and {len(unmatched_ext) - 5} more")

    if unmatched_gld:
        print(f"\nFalse negative nodes (in gold but not extracted): {len(unmatched_gld)}")
        for n in unmatched_gld[:5]:
            stmt = (n.get("statement") or "")[:80]
            print(f"  [{n.get('type','?'):>10}] {n.get('id','?')}: {stmt}")
        if len(unmatched_gld) > 5:
            print(f"  ... and {len(unmatched_gld) - 5} more")

    print()


def save_csv(node_overall, node_per_type, edge_overall, csv_path):
    """Save metrics to CSV."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "type", "precision", "recall", "f1", "tp", "fp", "fn"])
        writer.writerow(["nodes", "OVERALL", f"{node_overall['precision']:.4f}",
                         f"{node_overall['recall']:.4f}", f"{node_overall['f1']:.4f}",
                         node_overall["tp"], node_overall["fp"], node_overall["fn"]])
        for ntype, m in node_per_type.items():
            writer.writerow(["nodes", ntype, f"{m['precision']:.4f}", f"{m['recall']:.4f}",
                             f"{m['f1']:.4f}", m["tp"], m["fp"], m["fn"]])
        writer.writerow(["edges", "OVERALL", f"{edge_overall['precision']:.4f}",
                         f"{edge_overall['recall']:.4f}", f"{edge_overall['f1']:.4f}",
                         edge_overall["tp"], edge_overall["fp"], edge_overall["fn"]])
        combined = (node_overall["f1"] + edge_overall["f1"]) / 2
        writer.writerow(["combined", "avg(node_F1,edge_F1)", f"{combined:.4f}",
                         "", "", "", "", ""])
    print(f"Results saved to {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate extracted annotation against gold standard.")
    parser.add_argument("--extracted", required=True, help="Path to extracted JSON")
    parser.add_argument("--gold", required=True, help="Path to gold standard JSON")
    parser.add_argument("--node-sim-threshold", type=float, default=0.5,
                        help="Minimum Jaccard similarity between node texts to count as a match (default: 0.5)")
    parser.add_argument("--flipped-edge-credit", type=float, default=0.5,
                        help="Partial credit for edges with correct endpoints but reversed direction (default: 0.5)")
    parser.add_argument("--csv", help="Save summary metrics to CSV file")
    args = parser.parse_args()

    ext_nodes, ext_edges = load_annotation(args.extracted)
    gold_nodes, gold_edges = load_annotation(args.gold)

    print(f"Extracted: {len(ext_nodes)} nodes, {len(ext_edges)} edges from {args.extracted}")
    print(f"Gold:      {len(gold_nodes)} nodes, {len(gold_edges)} edges from {args.gold}")
    print(f"Node similarity threshold: {args.node_sim_threshold}")
    print(f"Flipped edge credit: {args.flipped_edge_credit}")

    # --- Node evaluation ---
    node_matches, unmatched_ext, unmatched_gld, id_map = match_nodes(
        ext_nodes, gold_nodes, args.node_sim_threshold)
    node_overall = compute_metrics(len(node_matches), len(unmatched_ext), len(unmatched_gld))
    node_per_type = per_type_metrics(node_matches, unmatched_ext, unmatched_gld,
                                     ext_nodes, gold_nodes)

    # --- Edge evaluation ---
    matched_edges, flipped_edges, unmatched_ext_edges, unmatched_gld_edges = match_edges(
        ext_edges, gold_edges, id_map, flipped_credit=args.flipped_edge_credit)
    edge_overall = compute_metrics(len(matched_edges), len(unmatched_ext_edges),
                                   len(unmatched_gld_edges),
                                   partial_tp=len(flipped_edges),
                                   partial_weight=args.flipped_edge_credit)

    print_results(node_overall, node_per_type, node_matches,
                  unmatched_ext, unmatched_gld,
                  edge_overall)

    if args.csv:
        save_csv(node_overall, node_per_type, edge_overall, args.csv)


if __name__ == "__main__":
    main()
