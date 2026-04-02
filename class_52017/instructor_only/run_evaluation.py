#!/usr/bin/env python3
"""
Full evaluation pipeline for the Big Data Project (52017).
Runs extraction (if needed) and evaluation across chapters/papers × models.
Produces detailed per-document and summary tables.

Can be used for:
  - Testing the instructor's solution
  - Evaluating student submissions
  - Generating leaderboard data

Usage examples:
    # Evaluate solution on all train chapters (extract only if JSON missing):
    python run_evaluation.py --extractor ../instructor_only/annotate_chapter_solution.py

    # Force re-extract on train chapters:
    python run_evaluation.py --extractor annotate_chapter.py --force-extract

    # Evaluate on test set only:
    python run_evaluation.py --extractor annotate_chapter.py --split test

    # Evaluate on everything, one specific model:
    python run_evaluation.py --extractor annotate_chapter.py --split both --models Qwen/Qwen3-8B

    # Evaluate existing JSONs (no extraction, e.g. student submission):
    python run_evaluation.py --results-dir students/pair03/results/

    # Only chapters, no papers:
    python run_evaluation.py --extractor annotate_chapter.py --doc-type chapters
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

# --- Default paths (relative to cluster_package/) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLUSTER_PKG = os.path.join(SCRIPT_DIR, "..", "cluster_package")

DEFAULT_CHAPTERS_DIR = os.path.join(CLUSTER_PKG, "chapters")
DEFAULT_PAPERS_DIR = os.path.join(CLUSTER_PKG, "papers")
DEFAULT_GOLDS_DIR = os.path.join(SCRIPT_DIR, "..", "extracted_chapters", "json")
DEFAULT_RESULTS_DIR = os.path.join(CLUSTER_PKG, "results", "evaluation")
DEFAULT_MANUAL_GOLD_DIR = os.path.join(CLUSTER_PKG, "examples")

# Chapter splits
TRAIN_CHAPTERS = [2, 3, 4, 5, 6, 7, 8, 9, 10]
TEST_CHAPTERS = [11, 12]

# Paper splits
TRAIN_PAPERS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
TEST_PAPERS = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

# Add scripts dir to path for imports
sys.path.insert(0, os.path.join(CLUSTER_PKG, "scripts"))
from call_llm import APPROVED_MODELS, DEFAULT_MODEL
from evaluate_extraction import (
    load_annotation, match_nodes, match_edges, compute_metrics
)

DEFAULT_THRESHOLD = 0.5


def find_gold(chapter_num, golds_dir, manual_gold_dir):
    """Find gold standard JSON for a chapter. Prefer manual gold if available."""
    # Check for manual gold first (e.g. gold_standard_chapter2.json)
    manual = os.path.join(manual_gold_dir, f"gold_standard_chapter{chapter_num}.json")
    if os.path.exists(manual):
        return manual
    # Fall back to Opus-extracted gold
    extracted = os.path.join(golds_dir, f"chapter{chapter_num}_extracted.json")
    if os.path.exists(extracted):
        return extracted
    return None


def find_paper_gold(paper_num, papers_dir):
    """Find gold standard JSON for a paper. Checks gold/ subdir first, then root."""
    for subdir in ["gold", ""]:
        for pattern in [f"paper{paper_num}_gold.json", f"paper{paper_num}.json"]:
            path = os.path.join(papers_dir, subdir, pattern)
            if os.path.exists(path):
                return path
    return None


def find_paper_tex(paper_num, papers_dir):
    """Find LaTeX source for a paper."""
    path = os.path.join(papers_dir, f"paper{paper_num}.tex")
    return path if os.path.exists(path) else None


def run_extractor(extractor_path, input_path, output_path, model):
    """Run an extractor script and return success status. Prints progress line."""
    print(f"    Extracting with {model.split('/')[-1]}...", end=" ", flush=True)
    return run_extractor_inner(extractor_path, input_path, output_path, model)


def run_extractor_inner(extractor_path, input_path, output_path, model):
    """Run an extractor script and return success status (no progress prefix)."""
    import time
    cmd = [sys.executable, extractor_path, input_path, "-o", output_path, "--model", model]
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        elapsed = time.time() - t0
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"OK ({elapsed:.0f}s)")
            return True
        else:
            print(f"FAILED ({elapsed:.0f}s)")
            if result.stderr:
                print(f"      stderr: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        print(f"TIMEOUT ({elapsed:.0f}s)")
        return False


def evaluate_one(extracted_path, gold_path, threshold=DEFAULT_THRESHOLD,
                 flipped_credit=0.5):
    """Evaluate one extracted file against gold. Returns dict of metrics or None."""
    try:
        ext_nodes, ext_edges = load_annotation(extracted_path)
        gold_nodes, gold_edges = load_annotation(gold_path)
    except Exception as e:
        print(f"      Load error: {e}")
        return None

    node_matches, unmatched_ext, unmatched_gld, id_map = match_nodes(
        ext_nodes, gold_nodes, threshold)
    node_m = compute_metrics(len(node_matches), len(unmatched_ext), len(unmatched_gld))

    matched_edges, flipped_edges, unmatched_ext_e, unmatched_gld_e = match_edges(
        ext_edges, gold_edges, id_map, flipped_credit=flipped_credit)
    edge_m = compute_metrics(len(matched_edges), len(unmatched_ext_e), len(unmatched_gld_e),
                             partial_tp=len(flipped_edges),
                             partial_weight=flipped_credit)

    combined = (node_m["f1"] + edge_m["f1"]) / 2

    return {
        "ext_nodes": len(ext_nodes), "ext_edges": len(ext_edges),
        "gold_nodes": len(gold_nodes), "gold_edges": len(gold_edges),
        "node_P": node_m["precision"], "node_R": node_m["recall"], "node_F1": node_m["f1"],
        "node_TP": node_m["tp"], "node_FP": node_m["fp"], "node_FN": node_m["fn"],
        "edge_P": edge_m["precision"], "edge_R": edge_m["recall"], "edge_F1": edge_m["f1"],
        "edge_TP": edge_m["tp"], "edge_FP": edge_m["fp"], "edge_FN": edge_m["fn"],
        "combined_F1": combined,
    }


def print_detailed_table(results):
    """Print detailed results table."""
    print(f"\n{'='*110}")
    print("DETAILED RESULTS")
    print(f"{'='*110}")
    print(f"{'Document':<18} {'Model':<26} {'Nodes':>5} {'Gold':>5} "
          f"{'Node_P':>7} {'Node_R':>7} {'Node_F1':>8} "
          f"{'Edge_P':>7} {'Edge_R':>7} {'Edge_F1':>8} {'Combined':>9}")
    print("-" * 110)

    for r in results:
        print(f"{r['document']:<18} {r['model']:<26} "
              f"{r['ext_nodes']:>5} {r['gold_nodes']:>5} "
              f"{r['node_P']:>7.3f} {r['node_R']:>7.3f} {r['node_F1']:>8.3f} "
              f"{r['edge_P']:>7.3f} {r['edge_R']:>7.3f} {r['edge_F1']:>8.3f} "
              f"{r['combined_F1']:>9.3f}")


def print_summary_table(results):
    """Print summary table: per-model averages, per-doc-type averages."""
    print(f"\n{'='*90}")
    print("SUMMARY")
    print(f"{'='*90}")

    # Per-model averages
    models = sorted(set(r["model"] for r in results))
    print(f"\n{'Model':<28} {'Docs':>5} {'Node_P':>7} {'Node_R':>7} {'Node_F1':>8} "
          f"{'Edge_P':>7} {'Edge_R':>7} {'Edge_F1':>8} {'Combined':>9}")
    print("-" * 90)
    for model in models:
        mr = [r for r in results if r["model"] == model]
        n = len(mr)
        avg = lambda key: sum(r[key] for r in mr) / n
        print(f"{model:<28} {n:>5} "
              f"{avg('node_P'):>7.3f} {avg('node_R'):>7.3f} {avg('node_F1'):>8.3f} "
              f"{avg('edge_P'):>7.3f} {avg('edge_R'):>7.3f} {avg('edge_F1'):>8.3f} "
              f"{avg('combined_F1'):>9.3f}")

    # Overall average
    if len(models) > 1:
        n = len(results)
        avg = lambda key: sum(r[key] for r in results) / n
        print("-" * 90)
        print(f"{'OVERALL':<28} {n:>5} "
              f"{avg('node_P'):>7.3f} {avg('node_R'):>7.3f} {avg('node_F1'):>8.3f} "
              f"{avg('edge_P'):>7.3f} {avg('edge_R'):>7.3f} {avg('edge_F1'):>8.3f} "
              f"{avg('combined_F1'):>9.3f}")

    # Per document type (chapters vs papers)
    doc_types = set()
    for r in results:
        doc_types.add("chapter" if r["document"].startswith("ch") else "paper")

    if len(doc_types) > 1:
        print(f"\n{'Doc type':<28} {'Docs':>5} {'Node_F1':>8} {'Edge_F1':>8} {'Combined':>9}")
        print("-" * 60)
        for dtype in sorted(doc_types):
            dr = [r for r in results if r["document"].startswith("ch" if dtype == "chapter" else "pa")]
            n = len(dr)
            avg = lambda key: sum(r[key] for r in dr) / n
            print(f"{dtype:<28} {n:>5} {avg('node_F1'):>8.3f} {avg('edge_F1'):>8.3f} "
                  f"{avg('combined_F1'):>9.3f}")

    # Per split (train vs test)
    splits = set(r.get("split", "?") for r in results)
    if len(splits) > 1:
        print(f"\n{'Split':<28} {'Docs':>5} {'Node_F1':>8} {'Edge_F1':>8} {'Combined':>9}")
        print("-" * 60)
        for split in sorted(splits):
            sr = [r for r in results if r.get("split") == split]
            n = len(sr)
            avg = lambda key: sum(r[key] for r in sr) / n
            print(f"{split:<28} {n:>5} {avg('node_F1'):>8.3f} {avg('edge_F1'):>8.3f} "
                  f"{avg('combined_F1'):>9.3f}")


def save_csv(results, csv_path):
    """Save all results to CSV."""
    if not results:
        return
    fields = ["document", "split", "model"] + [k for k in results[0] if k not in ("document", "split", "model")]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            rounded = {}
            for k, v in row.items():
                rounded[k] = f"{v:.4f}" if isinstance(v, float) else v
            writer.writerow(rounded)
    print(f"\nResults saved to: {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Full evaluation pipeline: extract + evaluate across documents × models.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_evaluation.py --extractor scripts/annotate_chapter.py
  python run_evaluation.py --extractor scripts/annotate_chapter.py --split test --force-extract
  python run_evaluation.py --results-dir students/pair03/results/
  python run_evaluation.py --extractor scripts/annotate_chapter.py --models Qwen/Qwen3-8B
        """)

    # What to run
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--extractor", help="Path to extractor script (e.g., annotate_chapter.py)")
    group.add_argument("--results-dir", help="Path to pre-existing results directory (skip extraction)")

    # Scope
    parser.add_argument("--split", choices=["train", "test", "both"], default="train",
                        help="Which split to evaluate (default: train)")
    parser.add_argument("--doc-type", choices=["chapters", "papers", "both"], default="both",
                        help="Document types to include (default: both)")
    parser.add_argument("--models", nargs="+", default=APPROVED_MODELS,
                        help=f"Models to use (default: all 3 approved)")

    # Behavior
    parser.add_argument("--force-extract", action="store_true",
                        help="Re-extract even if output JSON already exists")
    parser.add_argument("--node-sim-threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Minimum Jaccard similarity between node texts to count as a match (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--flipped-edge-credit", type=float, default=0.5,
                        help="Partial credit for edges with correct endpoints but reversed direction (default: 0.5)")

    # Paths
    parser.add_argument("--chapters-dir", default=DEFAULT_CHAPTERS_DIR,
                        help="Directory containing chapter .tex files")
    parser.add_argument("--papers-dir", default=DEFAULT_PAPERS_DIR,
                        help="Directory containing paper .tex and gold .json files")
    parser.add_argument("--golds-dir", default=DEFAULT_GOLDS_DIR,
                        help="Directory containing gold standard JSONs for chapters")
    parser.add_argument("--manual-gold-dir", default=DEFAULT_MANUAL_GOLD_DIR,
                        help="Directory with manual gold standards (preferred over extracted)")
    parser.add_argument("--outdir", default=DEFAULT_RESULTS_DIR,
                        help="Output directory for extracted JSONs and results CSV")

    args = parser.parse_args()

    # Build document list
    documents = []  # list of (label, split, tex_path, gold_path)

    if args.doc_type in ("chapters", "both"):
        if args.split in ("train", "both"):
            for ch in TRAIN_CHAPTERS:
                tex = os.path.join(args.chapters_dir, f"chapter{ch}.tex")
                gold = find_gold(ch, args.golds_dir, args.manual_gold_dir)
                if os.path.exists(tex) and gold:
                    documents.append((f"ch{ch}", "train", tex, gold))
                elif os.path.exists(tex):
                    print(f"  Warning: no gold standard for chapter {ch}, skipping")

        if args.split in ("test", "both"):
            for ch in TEST_CHAPTERS:
                tex = os.path.join(args.chapters_dir, f"chapter{ch}.tex")
                gold = find_gold(ch, args.golds_dir, args.manual_gold_dir)
                if os.path.exists(tex) and gold:
                    documents.append((f"ch{ch}", "test", tex, gold))
                elif os.path.exists(tex):
                    print(f"  Warning: no gold standard for chapter {ch}, skipping")

    if args.doc_type in ("papers", "both"):
        paper_nums = []
        if args.split in ("train", "both"):
            paper_nums += [(p, "train") for p in TRAIN_PAPERS]
        if args.split in ("test", "both"):
            paper_nums += [(p, "test") for p in TEST_PAPERS]

        for pnum, split in paper_nums:
            tex = find_paper_tex(pnum, args.papers_dir)
            gold = find_paper_gold(pnum, args.papers_dir)
            if tex and gold:
                documents.append((f"paper{pnum}", split, tex, gold))
            else:
                missing = []
                if not tex:
                    missing.append("tex")
                if not gold:
                    missing.append("gold")
                print(f"  Warning: paper {pnum} missing {' and '.join(missing)}, skipping")

    if not documents:
        print("No documents found to evaluate. Check paths and --split/--doc-type flags.")
        sys.exit(1)

    print(f"\nDocuments ({len(documents)}):")
    for i, (label, split, tex, gold) in enumerate(documents, 1):
        print(f"  {i:>2}. {label} ({split}) — {os.path.basename(tex)}")
    print(f"Models:    {len(args.models)}")
    print(f"Total runs: {len(documents) * len(args.models)}")
    print()

    # Determine output directory
    if args.results_dir:
        outdir = args.results_dir
    else:
        outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    # Run extraction + evaluation
    results = []
    total_docs = len(documents)
    total_runs = total_docs * len(args.models)
    run_num = 0
    for doc_idx, (doc_label, split, tex_path, gold_path) in enumerate(documents, 1):
        print(f"\n[{doc_idx}/{total_docs}] {doc_label} ({split}) — {os.path.basename(tex_path)}")
        for model in args.models:
            run_num += 1
            model_short = model.split("/")[-1]
            out_name = f"{doc_label}_{model_short}.json"
            out_path = os.path.join(outdir, out_name)

            # Extract if needed
            if args.extractor:
                if args.force_extract or not os.path.exists(out_path):
                    print(f"  [{run_num}/{total_runs}] Extracting with {model_short}...", end=" ", flush=True)
                    success = run_extractor_inner(args.extractor, tex_path, out_path, model)
                    if not success:
                        print(f"    Skipping evaluation (extraction failed)")
                        continue
                else:
                    print(f"  [{run_num}/{total_runs}] {model_short}: using existing {out_name}")

            # Evaluate
            if not os.path.exists(out_path):
                print(f"    No output found: {out_path}")
                continue

            metrics = evaluate_one(out_path, gold_path,
                                      threshold=args.node_sim_threshold,
                                      flipped_credit=args.flipped_edge_credit)
            if metrics:
                row = {
                    "document": doc_label,
                    "split": split,
                    "model": model_short,
                    **metrics,
                }
                results.append(row)
            else:
                print(f"    Evaluation failed for {out_name}")

    if not results:
        print("\nNo results produced.")
        sys.exit(1)

    # Print tables
    print_detailed_table(results)
    print_summary_table(results)

    # Save CSV
    csv_path = os.path.join(outdir, "results.csv")
    save_csv(results, csv_path)


if __name__ == "__main__":
    main()
