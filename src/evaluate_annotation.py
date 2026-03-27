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
    parser.add_argument("--output-csv", default=None, help="Save results to CSV")
    args = parser.parse_args()

    ext_data = load_annotation(args.extracted)
    gold_data = load_annotation(args.gold)

    ext_nodes = ext_data.get("nodes", [])
    gold_nodes = gold_data.get("nodes", [])

    results = evaluate_nodes(ext_nodes, gold_nodes, args.threshold)
    print_results(results)

    if args.output_csv:
        save_csv(results, args.output_csv)
        print(f"\nResults saved to {args.output_csv}")


if __name__ == "__main__":
    main()
