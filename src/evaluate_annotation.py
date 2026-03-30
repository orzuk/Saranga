#!/usr/bin/env python3
"""Evaluate an extracted annotation JSON against a gold-standard annotation.

Usage:
    python evaluate_annotation.py --extracted output.json --gold gold.json [--threshold 0.7]

Computes precision/recall/F1 for node detection (using Jaccard similarity
on statement text), broken down by node type. Optionally evaluates edges.

Reuses the Jaccard tokenizer from LLMVersion/evaluate_definitions.py.
"""
import json
import sys
import argparse
import csv
from collections import defaultdict
from pathlib import Path

# Reuse existing tokenizer
sys.path.insert(0, str(Path(__file__).parent / "LLMVersion"))
from evaluate_definitions import jaccard_similarity  # type: ignore


def load_annotation(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_nodes(extracted_nodes, gold_nodes, threshold=0.7):
    """Match extracted nodes to gold nodes using Jaccard on statement text.

    Returns per-type and overall precision/recall/F1.
    """
    # Group by type
    gold_by_type = defaultdict(list)
    for n in gold_nodes:
        gold_by_type[n["type"]].append(n)

    ext_by_type = defaultdict(list)
    for n in extracted_nodes:
        ext_by_type[n["type"]].append(n)

    all_types = sorted(set(list(gold_by_type.keys()) + list(ext_by_type.keys())))
    results = {}
    total_tp, total_fp, total_fn = 0, 0, 0

    for ntype in all_types:
        golds = gold_by_type.get(ntype, [])
        exts = ext_by_type.get(ntype, [])
        matched_gold = set()
        tp = 0

        for ext_node in exts:
            ext_text = ext_node.get("statement", "") or ext_node.get("clean_text", "")
            best_sim, best_idx = 0.0, None
            for i, g in enumerate(golds):
                if i in matched_gold:
                    continue
                g_text = g.get("statement", "") or g.get("clean_text", "")
                sim = jaccard_similarity(ext_text, g_text)
                if sim > best_sim:
                    best_sim = sim
                    best_idx = i
            if best_sim >= threshold and best_idx is not None:
                tp += 1
                matched_gold.add(best_idx)

        fp = len(exts) - tp
        fn = len(golds) - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        results[ntype] = {
            "gold": len(golds), "extracted": len(exts),
            "TP": tp, "FP": fp, "FN": fn,
            "precision": round(prec, 3), "recall": round(rec, 3), "F1": round(f1, 3),
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn

    # Overall
    prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    results["OVERALL"] = {
        "gold": sum(r["gold"] for r in results.values()),
        "extracted": sum(r["extracted"] for r in results.values()),
        "TP": total_tp, "FP": total_fp, "FN": total_fn,
        "precision": round(prec, 3), "recall": round(rec, 3), "F1": round(f1, 3),
    }
    return results


def match_nodes(extracted_nodes, gold_nodes, threshold=0.7):
    """Build a mapping from extracted node ID -> gold node ID via Jaccard matching.

    Also returns the reverse mapping gold_id -> ext_id.
    """
    ext_to_gold = {}
    gold_to_ext = {}
    matched_gold = set()

    for ext_node in extracted_nodes:
        ext_text = ext_node.get("statement", "") or ext_node.get("clean_text", "")
        ext_id = ext_node.get("id", "")
        best_sim, best_gold = 0.0, None
        for g in gold_nodes:
            g_id = g.get("id", "")
            if g_id in matched_gold:
                continue
            g_text = g.get("statement", "") or g.get("clean_text", "")
            sim = jaccard_similarity(ext_text, g_text)
            if sim > best_sim:
                best_sim = sim
                best_gold = g
        if best_sim >= threshold and best_gold is not None:
            gold_id = best_gold["id"]
            ext_to_gold[ext_id] = gold_id
            gold_to_ext[gold_id] = ext_id
            matched_gold.add(gold_id)

    return ext_to_gold, gold_to_ext


def normalize_edges(data):
    """Extract edges from a JSON annotation, handling both formats.

    Format 1 (extracted chapters): {"edges": [{"source": ..., "target": ..., "type": ...}]}
    Format 2 (gold): {"relations": [{"source_id": ..., "target_id": ..., "relation_type"|"type": ...}]}
    Also handles gold format where nodes are in "objects" dict instead of "nodes" list.
    """
    edges = data.get("edges", [])
    if not edges:
        edges = data.get("relations", [])
    normalized = []
    for e in edges:
        src = e.get("source") or e.get("source_id", "")
        tgt = e.get("target") or e.get("target_id", "")
        etype = e.get("type") or e.get("relation_type", "unknown")
        normalized.append({"source": src, "target": tgt, "type": etype})
    return normalized


def normalize_nodes(data):
    """Extract nodes list from a JSON annotation, handling both formats.

    Format 1: {"nodes": [...]}
    Format 2: {"objects": {"id": {...}, ...}}
    """
    nodes = data.get("nodes", [])
    if nodes:
        return nodes
    objects = data.get("objects", {})
    if objects:
        return list({**obj, "id": obj.get("id", obj_id),
                          "type": obj.get("type", obj.get("kind", "unknown"))}
                         for obj_id, obj in objects.items())
    return []


def evaluate_edges(ext_edges, gold_edges, ext_to_gold, reverse_weight=0.5):
    """Evaluate extracted edges against gold edges.

    An extracted edge (s, t, type) is:
    - Full match (score 1.0) if (mapped_s, mapped_t) matches a gold edge
    - Partial match (score reverse_weight) if (mapped_t, mapped_s) matches a gold edge (wrong direction)
    - No match (score 0) otherwise

    Both source and target must have been matched to gold nodes for the edge to be evaluable.

    Returns per-type and overall results with weighted scores.
    """
    # Build gold edge lookup: (source, target) -> type
    gold_edge_set = set()
    gold_by_type = defaultdict(int)
    for e in gold_edges:
        gold_edge_set.add((e["source"], e["target"]))
        gold_by_type[e["type"]] += 1

    ext_by_type = defaultdict(list)
    for e in ext_edges:
        ext_by_type[e["type"]].append(e)

    all_types = sorted(set(list(gold_by_type.keys()) + list(ext_by_type.keys())))
    results = {}
    total_score, total_ext, total_gold = 0.0, 0, 0
    total_full, total_reversed, total_unmappable = 0, 0, 0

    for etype in all_types:
        exts = ext_by_type.get(etype, [])
        n_gold = gold_by_type.get(etype, 0)

        type_score = 0.0
        full_matches = 0
        reversed_matches = 0
        unmappable = 0

        for e in exts:
            mapped_src = ext_to_gold.get(e["source"])
            mapped_tgt = ext_to_gold.get(e["target"])

            if mapped_src is None or mapped_tgt is None:
                unmappable += 1
                continue

            if (mapped_src, mapped_tgt) in gold_edge_set:
                type_score += 1.0
                full_matches += 1
            elif (mapped_tgt, mapped_src) in gold_edge_set:
                type_score += reverse_weight
                reversed_matches += 1

        n_evaluable = len(exts) - unmappable
        prec = type_score / n_evaluable if n_evaluable > 0 else 0.0
        rec = type_score / n_gold if n_gold > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

        results[etype] = {
            "gold": n_gold, "extracted": len(exts), "evaluable": n_evaluable,
            "full_match": full_matches, "reversed": reversed_matches,
            "unmappable": unmappable,
            "score": round(type_score, 2),
            "precision": round(prec, 3), "recall": round(rec, 3), "F1": round(f1, 3),
        }

        total_score += type_score
        total_ext += len(exts)
        total_gold += n_gold
        total_full += full_matches
        total_reversed += reversed_matches
        total_unmappable += unmappable

    total_evaluable = total_ext - total_unmappable
    prec = total_score / total_evaluable if total_evaluable > 0 else 0.0
    rec = total_score / total_gold if total_gold > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    results["OVERALL"] = {
        "gold": total_gold, "extracted": total_ext, "evaluable": total_evaluable,
        "full_match": total_full, "reversed": total_reversed,
        "unmappable": total_unmappable,
        "score": round(total_score, 2),
        "precision": round(prec, 3), "recall": round(rec, 3), "F1": round(f1, 3),
    }
    return results


def print_edge_results(results):
    header = f"{'Type':<15} {'Gold':>5} {'Extr':>5} {'Eval':>5} {'Full':>5} {'Rev':>4} {'Unmap':>5} {'Score':>6} {'Prec':>6} {'Rec':>6} {'F1':>6}"
    print(header)
    print("-" * len(header))
    for etype in sorted(results.keys()):
        if etype == "OVERALL":
            continue
        r = results[etype]
        print(f"{etype:<15} {r['gold']:>5} {r['extracted']:>5} {r['evaluable']:>5} {r['full_match']:>5} {r['reversed']:>4} {r['unmappable']:>5} {r['score']:>6.2f} {r['precision']:>6.3f} {r['recall']:>6.3f} {r['F1']:>6.3f}")
    print("-" * len(header))
    r = results["OVERALL"]
    print(f"{'OVERALL':<15} {r['gold']:>5} {r['extracted']:>5} {r['evaluable']:>5} {r['full_match']:>5} {r['reversed']:>4} {r['unmappable']:>5} {r['score']:>6.2f} {r['precision']:>6.3f} {r['recall']:>6.3f} {r['F1']:>6.3f}")


def save_edge_csv(results, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["type", "gold", "extracted", "evaluable", "full_match", "reversed",
                     "unmappable", "score", "precision", "recall", "F1"])
        for etype in sorted(results.keys()):
            r = results[etype]
            w.writerow([etype, r["gold"], r["extracted"], r["evaluable"], r["full_match"],
                        r["reversed"], r["unmappable"], r["score"], r["precision"],
                        r["recall"], r["F1"]])


def print_results(results):
    header = f"{'Type':<15} {'Gold':>5} {'Extr':>5} {'TP':>4} {'FP':>4} {'FN':>4} {'Prec':>6} {'Rec':>6} {'F1':>6}"
    print(header)
    print("-" * len(header))
    for ntype in sorted(results.keys()):
        if ntype == "OVERALL":
            continue
        r = results[ntype]
        print(f"{ntype:<15} {r['gold']:>5} {r['extracted']:>5} {r['TP']:>4} {r['FP']:>4} {r['FN']:>4} {r['precision']:>6.3f} {r['recall']:>6.3f} {r['F1']:>6.3f}")
    print("-" * len(header))
    r = results["OVERALL"]
    print(f"{'OVERALL':<15} {r['gold']:>5} {r['extracted']:>5} {r['TP']:>4} {r['FP']:>4} {r['FN']:>4} {r['precision']:>6.3f} {r['recall']:>6.3f} {r['F1']:>6.3f}")


def save_csv(results, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["type", "gold", "extracted", "TP", "FP", "FN", "precision", "recall", "F1"])
        for ntype in sorted(results.keys()):
            r = results[ntype]
            w.writerow([ntype, r["gold"], r["extracted"], r["TP"], r["FP"], r["FN"],
                        r["precision"], r["recall"], r["F1"]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extracted", required=True, help="Extracted annotation JSON")
    parser.add_argument("--gold", required=True, help="Gold standard annotation JSON")
    parser.add_argument("--threshold", type=float, default=0.7, help="Jaccard threshold (default 0.7)")
    parser.add_argument("--reverse-weight", type=float, default=0.5,
                        help="Partial score for reversed-direction edges (default 0.5)")
    parser.add_argument("--output-csv", default=None, help="Save node results to CSV")
    parser.add_argument("--output-edge-csv", default=None, help="Save edge results to CSV")
    parser.add_argument("--no-edges", action="store_true", help="Skip edge evaluation")
    args = parser.parse_args()

    ext_data = load_annotation(args.extracted)
    gold_data = load_annotation(args.gold)

    ext_nodes = normalize_nodes(ext_data)
    gold_nodes = normalize_nodes(gold_data)

    print("=== NODE EVALUATION ===")
    results = evaluate_nodes(ext_nodes, gold_nodes, args.threshold)
    print_results(results)

    if args.output_csv:
        save_csv(results, args.output_csv)
        print(f"\nNode results saved to {args.output_csv}")

    if not args.no_edges:
        ext_edges = normalize_edges(ext_data)
        gold_edges = normalize_edges(gold_data)

        if ext_edges or gold_edges:
            ext_to_gold, _ = match_nodes(ext_nodes, gold_nodes, args.threshold)
            print(f"\n=== EDGE EVALUATION (reverse_weight={args.reverse_weight}) ===")
            print(f"Node mapping: {len(ext_to_gold)} extracted nodes matched to gold")
            edge_results = evaluate_edges(ext_edges, gold_edges, ext_to_gold, args.reverse_weight)
            print_edge_results(edge_results)

            if args.output_edge_csv:
                save_edge_csv(edge_results, args.output_edge_csv)
                print(f"\nEdge results saved to {args.output_edge_csv}")
        else:
            print("\nNo edges found in either file — skipping edge evaluation.")


if __name__ == "__main__":
    main()
