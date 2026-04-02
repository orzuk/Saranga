#!/usr/bin/env python3
"""
Batch evaluation: run extractors from multiple sources and compare results.

Evaluates:
  1. Instructor extractors (baseline + solution)
  2. All student submissions found in a StudentsSolutions/ directory

Each student directory should be named like: firstname_lastname_ID/
  and contain an extractor script (default: annotate_chapter_student.py).

Output: a combined CSV with all results + a leaderboard summary.

Usage:
    # Evaluate baseline + solution
    python run_all_evaluations.py --extractors baseline:../cluster_package/scripts/annotate_chapter.py solution:annotate_chapter_solution.py

    # Add all students
    python run_all_evaluations.py --extractors baseline:../cluster_package/scripts/annotate_chapter.py --students-dir ../StudentsSolutions

    # Only students, papers only, test split
    python run_all_evaluations.py --students-dir ../StudentsSolutions --doc-type papers --split test
"""

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_STUDENT_SCRIPT = "annotate_chapter_student.py"


def run_evaluation(extractor_path, label, outdir, extra_args):
    """Run run_evaluation.py for a single extractor. Returns path to results CSV."""
    results_dir = os.path.join(outdir, label)
    cmd = [
        sys.executable, os.path.join(SCRIPT_DIR, "run_evaluation.py"),
        "--extractor", extractor_path,
        "--outdir", results_dir,
    ] + extra_args

    print(f"\n{'='*80}")
    print(f"  Running: {label}")
    print(f"  Extractor: {extractor_path}")
    print(f"  Output: {results_dir}")
    print(f"{'='*80}\n")

    result = subprocess.run(cmd, timeout=7200)
    csv_path = os.path.join(results_dir, "results.csv")
    if result.returncode == 0 and os.path.exists(csv_path):
        return csv_path
    else:
        print(f"  WARNING: evaluation failed for {label} (exit code {result.returncode})")
        return None


def load_csv(csv_path, submitter_label):
    """Load a results CSV and add a 'submitter' column."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["submitter"] = submitter_label
            rows.append(row)
    return rows


def find_student_dirs(students_dir, student_script):
    """Find all student directories containing the expected extractor script."""
    found = []
    students_path = Path(students_dir)
    if not students_path.is_dir():
        print(f"WARNING: Students directory not found: {students_dir}")
        return found

    for d in sorted(students_path.iterdir()):
        if not d.is_dir():
            continue
        extractor = d / student_script
        if extractor.exists():
            # Parse label from directory name (e.g., "john_doe_02345134")
            found.append((d.name, str(extractor)))
        else:
            print(f"  WARNING: No {student_script} in {d.name}, skipping.")
    return found


def print_leaderboard(all_rows):
    """Print a leaderboard sorted by combined F1."""
    # Group by submitter
    from collections import defaultdict
    by_submitter = defaultdict(list)
    for row in all_rows:
        by_submitter[row["submitter"]].append(row)

    # Compute average combined_F1 per submitter
    scores = []
    for submitter, rows in by_submitter.items():
        vals = []
        for r in rows:
            try:
                vals.append(float(r["combined_F1"]))
            except (ValueError, KeyError):
                pass
        avg_combined = sum(vals) / len(vals) if vals else 0.0

        # Also compute per-split averages
        train_vals = [float(r["combined_F1"]) for r in rows
                      if r.get("split") == "train" and r.get("combined_F1")]
        test_vals = [float(r["combined_F1"]) for r in rows
                     if r.get("split") == "test" and r.get("combined_F1")]
        avg_train = sum(train_vals) / len(train_vals) if train_vals else 0.0
        avg_test = sum(test_vals) / len(test_vals) if test_vals else 0.0

        scores.append((submitter, avg_combined, avg_train, avg_test, len(rows)))

    scores.sort(key=lambda x: x[1], reverse=True)

    print(f"\n{'='*90}")
    print("LEADERBOARD")
    print(f"{'='*90}")
    print(f"{'Rank':>4}  {'Submitter':<35} {'Avg F1':>7} {'Train':>7} {'Test':>7} {'Evals':>6}")
    print("-" * 90)
    for rank, (submitter, avg, train, test, n) in enumerate(scores, 1):
        print(f"{rank:>4}  {submitter:<35} {avg:>7.3f} {train:>7.3f} {test:>7.3f} {n:>6}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Batch evaluation: compare baseline, solution, and student extractors.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Baseline + solution
  python run_all_evaluations.py --extractors baseline:../cluster_package/scripts/annotate_chapter.py solution:annotate_chapter_solution.py

  # Baseline + all students
  python run_all_evaluations.py --extractors baseline:../cluster_package/scripts/annotate_chapter.py --students-dir ../StudentsSolutions

  # Only students, test split, papers only
  python run_all_evaluations.py --students-dir ../StudentsSolutions --doc-type papers --split test
        """)

    parser.add_argument("--extractors", nargs="+", metavar="LABEL:PATH", default=[],
                        help="Extractor(s) as label:path pairs, e.g. baseline:scripts/annotate_chapter.py solution:my_solution.py")
    parser.add_argument("--students-dir", default=None,
                        help="Directory containing student submission folders (e.g., ../StudentsSolutions)")
    parser.add_argument("--student-script", default=DEFAULT_STUDENT_SCRIPT,
                        help=f"Name of the extractor script inside each student dir (default: {DEFAULT_STUDENT_SCRIPT})")
    parser.add_argument("--outdir", default=os.path.join(SCRIPT_DIR, "..", "evaluation_results"),
                        help="Root output directory for all results")

    # Pass-through args for run_evaluation.py
    parser.add_argument("--split", choices=["train", "test", "both"], default="both",
                        help="Which split to evaluate (default: both)")
    parser.add_argument("--doc-type", choices=["chapters", "papers", "both"], default="both",
                        help="Document types to include (default: both)")
    parser.add_argument("--models", nargs="+", default=None,
                        help="Models to use (default: all approved)")
    parser.add_argument("--node-sim-threshold", type=float, default=0.5,
                        help="Minimum Jaccard similarity for node matching (default: 0.5)")
    parser.add_argument("--flipped-edge-credit", type=float, default=0.5,
                        help="Partial credit for reversed edges (default: 0.5)")
    parser.add_argument("--force-extract", action="store_true",
                        help="Re-extract even if output already exists")

    args = parser.parse_args()

    # Build pass-through args
    extra = ["--split", args.split, "--doc-type", args.doc_type,
             "--node-sim-threshold", str(args.node_sim_threshold),
             "--flipped-edge-credit", str(args.flipped_edge_credit)]
    if args.models:
        extra += ["--models"] + args.models
    if args.force_extract:
        extra.append("--force-extract")

    os.makedirs(args.outdir, exist_ok=True)

    # Collect all extractors to run
    jobs = []  # (label, extractor_path)

    for spec in args.extractors:
        if ":" in spec:
            label, path = spec.split(":", 1)
        else:
            # Use filename (without extension) as label
            label = Path(spec).stem
            path = spec
        if os.path.exists(path):
            jobs.append((label, path))
        else:
            print(f"WARNING: Extractor not found: {path}")

    if args.students_dir:
        students = find_student_dirs(args.students_dir, args.student_script)
        print(f"\nFound {len(students)} student submissions in {args.students_dir}")
        for name, path in students:
            jobs.append((f"student_{name}", path))

    if not jobs:
        print("No extractors to run. Use --extractors and/or --students-dir.")
        print("Example: python run_all_evaluations.py --extractors baseline:scripts/annotate_chapter.py")
        sys.exit(1)

    print(f"\nWill evaluate {len(jobs)} extractor(s):")
    for label, path in jobs:
        print(f"  {label}: {path}")

    # Run evaluations
    all_rows = []
    csv_paths = []
    for label, extractor_path in jobs:
        csv_path = run_evaluation(extractor_path, label, args.outdir, extra)
        if csv_path:
            csv_paths.append(csv_path)
            rows = load_csv(csv_path, label)
            all_rows.extend(rows)

    if not all_rows:
        print("\nNo results produced.")
        sys.exit(1)

    # Save combined CSV
    combined_csv = os.path.join(args.outdir, "all_results.csv")
    fields = ["submitter"] + [k for k in all_rows[0] if k != "submitter"]
    with open(combined_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nCombined results saved to: {combined_csv}")

    # Print leaderboard
    print_leaderboard(all_rows)


if __name__ == "__main__":
    main()
