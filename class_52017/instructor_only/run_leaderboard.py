#!/usr/bin/env python3
"""
Batch runner and leaderboard generator for the Big Data Project (52017).
NOT for distribution to students.

Runs one or more extractors on a set of documents × models, evaluates against
gold standards, and produces a leaderboard CSV.

Usage:
    # Run solution on chapter 2 with all 3 models:
    python run_leaderboard.py \
        --extractor scripts/annotate_chapter_solution.py \
        --docs chapters/chapter2.tex \
        --golds examples/gold_standard_chapter2.json \
        --outdir results/solution

    # Run on multiple docs (must match golds 1:1):
    python run_leaderboard.py \
        --extractor scripts/annotate_chapter_solution.py \
        --docs chapters/chapter3.tex chapters/chapter4.tex \
        --golds golds/gold_chapter3.json golds/gold_chapter4.json \
        --outdir results/solution

    # Run baseline too and compare:
    python run_leaderboard.py \
        --extractor scripts/annotate_chapter.py \
        --docs chapters/chapter2.tex \
        --golds examples/gold_standard_chapter2.json \
        --outdir results/baseline

    # Just evaluate pre-existing outputs (skip extraction):
    python run_leaderboard.py \
        --eval-only \
        --outdir results/solution \
        --golds examples/gold_standard_chapter2.json

    # Generate leaderboard from multiple result dirs:
    python run_leaderboard.py \
        --leaderboard results/baseline results/solution
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

# Import from cluster_package/scripts/
_scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "cluster_package", "scripts")
sys.path.insert(0, _scripts_dir)
from call_llm import APPROVED_MODELS
from evaluate_extraction import (
    load_annotation, match_nodes, match_edges, compute_metrics
)

DEFAULT_THRESHOLD = 0.5


def run_extractor(extractor_path, doc_path, output_path, model):
    """Run an extractor script on a document with a given model."""
    cmd = [
        sys.executable, extractor_path,
        doc_path, "-o", output_path, "--model", model
    ]
    print(f"\n{'='*60}")
    print(f"Running: {os.path.basename(extractor_path)}")
    print(f"  Doc:   {doc_path}")
    print(f"  Model: {model}")
    print(f"  Out:   {output_path}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr[:500]}")
        return result.returncode == 0 and os.path.exists(output_path)
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after 600s")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def evaluate_one(extracted_path, gold_path, threshold=DEFAULT_THRESHOLD):
    """Evaluate one extracted file against gold. Returns dict of metrics."""
    try:
        ext_nodes, ext_edges = load_annotation(extracted_path)
        gold_nodes, gold_edges = load_annotation(gold_path)
    except Exception as e:
        print(f"  Load error: {e}")
        return None

    node_matches, unmatched_ext, unmatched_gld, id_map = match_nodes(
        ext_nodes, gold_nodes, threshold)
    node_m = compute_metrics(len(node_matches), len(unmatched_ext), len(unmatched_gld))

    matched_edges, unmatched_ext_e, unmatched_gld_e = match_edges(
        ext_edges, gold_edges, id_map)
    edge_m = compute_metrics(len(matched_edges), len(unmatched_ext_e), len(unmatched_gld_e))

    combined = (node_m["f1"] + edge_m["f1"]) / 2

    return {
        "ext_nodes": len(ext_nodes), "ext_edges": len(ext_edges),
        "gold_nodes": len(gold_nodes), "gold_edges": len(gold_edges),
        "node_P": node_m["precision"], "node_R": node_m["recall"], "node_F1": node_m["f1"],
        "edge_P": edge_m["precision"], "edge_R": edge_m["recall"], "edge_F1": edge_m["f1"],
        "combined_F1": combined,
    }


def doc_label(doc_path):
    """Short label for a document path."""
    name = os.path.basename(doc_path).replace(".tex", "")
    return name


def run_batch(extractor_path, docs, golds, outdir, models=None):
    """Run extractor on all docs × models, evaluate, return results table."""
    if models is None:
        models = APPROVED_MODELS

    os.makedirs(outdir, exist_ok=True)
    results = []

    for doc_path, gold_path in zip(docs, golds):
        label = doc_label(doc_path)
        for model in models:
            model_short = model.split("/")[-1]
            out_name = f"{label}_{model_short}.json"
            out_path = os.path.join(outdir, out_name)

            # Run extraction
            success = run_extractor(extractor_path, doc_path, out_path, model)

            if success:
                metrics = evaluate_one(out_path, gold_path)
                if metrics:
                    row = {
                        "document": label,
                        "model": model_short,
                        **metrics,
                    }
                    results.append(row)
                    print(f"\n  >> node_F1={metrics['node_F1']:.3f}  "
                          f"edge_F1={metrics['edge_F1']:.3f}  "
                          f"combined={metrics['combined_F1']:.3f}")
                else:
                    print(f"  >> Evaluation failed")
            else:
                print(f"  >> Extraction failed")

    return results


def eval_only(outdir, golds):
    """Evaluate pre-existing outputs in outdir against golds."""
    results = []
    for gold_path in golds:
        gold_label = doc_label(gold_path).replace("gold_standard_", "").replace("_gold", "")
        # Find matching outputs
        for fname in sorted(os.listdir(outdir)):
            if not fname.endswith(".json"):
                continue
            # Match by chapter/paper name prefix
            if gold_label in fname or fname.startswith(gold_label):
                out_path = os.path.join(outdir, fname)
                # Extract model name from filename
                parts = fname.replace(".json", "").split("_")
                model_short = parts[-1] if len(parts) > 1 else "unknown"

                metrics = evaluate_one(out_path, gold_path)
                if metrics:
                    results.append({
                        "document": gold_label,
                        "model": model_short,
                        **metrics,
                    })
    return results


def save_results(results, outdir):
    """Save detailed results CSV."""
    if not results:
        print("No results to save.")
        return

    csv_path = os.path.join(outdir, "results.csv")
    fields = list(results[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            # Round floats
            rounded = {}
            for k, v in row.items():
                rounded[k] = f"{v:.4f}" if isinstance(v, float) else v
            writer.writerow(rounded)

    print(f"\nDetailed results saved to: {csv_path}")


def print_summary(results):
    """Print summary table."""
    if not results:
        return

    print(f"\n{'='*80}")
    print("RESULTS SUMMARY")
    print(f"{'='*80}")
    print(f"{'Document':<20} {'Model':<30} {'Node F1':>8} {'Edge F1':>8} {'Combined':>9}")
    print("-" * 80)
    for r in results:
        print(f"{r['document']:<20} {r['model']:<30} "
              f"{r['node_F1']:>8.3f} {r['edge_F1']:>8.3f} {r['combined_F1']:>9.3f}")

    # Average across all
    if len(results) > 1:
        avg_node = sum(r["node_F1"] for r in results) / len(results)
        avg_edge = sum(r["edge_F1"] for r in results) / len(results)
        avg_comb = sum(r["combined_F1"] for r in results) / len(results)
        print("-" * 80)
        print(f"{'AVERAGE':<20} {'all':<30} {avg_node:>8.3f} {avg_edge:>8.3f} {avg_comb:>9.3f}")

    # Per-model averages
    models = sorted(set(r["model"] for r in results))
    if len(models) > 1:
        print(f"\nPer-model averages:")
        for model in models:
            mr = [r for r in results if r["model"] == model]
            avg_c = sum(r["combined_F1"] for r in mr) / len(mr)
            print(f"  {model:<35} combined_F1 = {avg_c:.3f}")


def generate_leaderboard(result_dirs):
    """Generate leaderboard from multiple result directories."""
    print(f"\n{'='*80}")
    print("LEADERBOARD")
    print(f"{'='*80}")

    entries = []
    for d in result_dirs:
        csv_path = os.path.join(d, "results.csv")
        if not os.path.exists(csv_path):
            print(f"  Skipping {d} (no results.csv)")
            continue

        team_name = os.path.basename(d)
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            continue

        avg_combined = sum(float(r["combined_F1"]) for r in rows) / len(rows)
        avg_node = sum(float(r["node_F1"]) for r in rows) / len(rows)
        avg_edge = sum(float(r["edge_F1"]) for r in rows) / len(rows)
        entries.append({
            "team": team_name,
            "combined_F1": avg_combined,
            "node_F1": avg_node,
            "edge_F1": avg_edge,
            "n_evals": len(rows),
        })

    entries.sort(key=lambda x: x["combined_F1"], reverse=True)

    print(f"\n{'Rank':<5} {'Team':<25} {'Combined F1':>12} {'Node F1':>9} {'Edge F1':>9} {'Evals':>6}")
    print("-" * 70)
    for i, e in enumerate(entries, 1):
        print(f"{i:<5} {e['team']:<25} {e['combined_F1']:>12.3f} "
              f"{e['node_F1']:>9.3f} {e['edge_F1']:>9.3f} {e['n_evals']:>6}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch runner and leaderboard for extraction competition.")
    parser.add_argument("--extractor", help="Path to extractor script")
    parser.add_argument("--docs", nargs="+", help="LaTeX document paths")
    parser.add_argument("--golds", nargs="+", help="Gold standard JSON paths (same order as --docs)")
    parser.add_argument("--outdir", help="Output directory for results")
    parser.add_argument("--models", nargs="+", default=None,
                        help=f"Models to use (default: all approved)")
    parser.add_argument("--eval-only", action="store_true",
                        help="Only evaluate existing outputs in --outdir")
    parser.add_argument("--leaderboard", nargs="+", metavar="DIR",
                        help="Generate leaderboard from result directories")
    args = parser.parse_args()

    if args.leaderboard:
        generate_leaderboard(args.leaderboard)
        return

    if args.eval_only:
        if not args.outdir or not args.golds:
            parser.error("--eval-only requires --outdir and --golds")
        results = eval_only(args.outdir, args.golds)
        print_summary(results)
        save_results(results, args.outdir)
        return

    if not args.extractor or not args.docs or not args.golds or not args.outdir:
        parser.error("Need --extractor, --docs, --golds, and --outdir")

    if len(args.docs) != len(args.golds):
        parser.error(f"Number of docs ({len(args.docs)}) must match golds ({len(args.golds)})")

    results = run_batch(args.extractor, args.docs, args.golds, args.outdir, args.models)
    print_summary(results)
    save_results(results, args.outdir)


if __name__ == "__main__":
    main()
