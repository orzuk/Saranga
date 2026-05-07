#!/usr/bin/env python3
"""Evaluate T3 (rule-based) extractions against T2 (Opus silver) on the
250-paper overlap.

Usage:
    python scripts/eval_t3_vs_t2.py \
        --t2-dir portal/data/tier2 \
        --t3-dir <PATH_TO_100K_T3_OUTPUT> \
        --out eval_t3_vs_t2

Resolves the T3 file for each tier2 paper by matching its arxiv_id
(metadata.arxiv_id field). Runs src/evaluate_extraction.py per pair,
collects results into a CSV, and prints aggregate node-F1 / edge-F1.

Cluster paths to try for --t3-dir:
    /sci/labs/orzuk/orzuk/projects/Authomathics/100k_output
    /sci/labs/orzuk/orzuk/projects/Authomathics/output
    (whichever Yaron used; the 100K run output dir)
"""
import argparse
import csv
import json
import statistics
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVAL = REPO / "src" / "evaluate_extraction.py"


def find_t3_json(t3_dir: Path, paper_id: str) -> Path | None:
    """Find the T3 extraction file for a given tier2 paper id (e.g. 'paper001').

    The shell driver extracts each paper into <t3_dir>/<paper_id>/, with the
    actual JSON output landing inside that subdir (run_pipeline writes to
    `json/` subfolder when using --operations parse). We accept any JSON in
    the matching subdir, preferring those inside `json/`.
    """
    sub = t3_dir / paper_id
    if not sub.is_dir():
        # Try unpadded form (paper1 vs paper001) just in case
        unpadded = "paper" + paper_id.removeprefix("paper").lstrip("0")
        if (t3_dir / unpadded).is_dir():
            sub = t3_dir / unpadded
        else:
            return None
    # Prefer json/ subdirectory output
    json_dir = sub / "json"
    if json_dir.is_dir():
        candidates = sorted(json_dir.glob("*.json"))
        if candidates:
            return candidates[0]
    # Fall back to any non-report JSON in the subdir
    for f in sorted(sub.glob("*.json")):
        if f.name in ("anomalies_detail.json", "anomalies_report.csv",
                      "validate_report.csv", "corpus_stats.csv"):
            continue
        return f
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--t2-dir", default="portal/data/tier2",
                   help="Directory of tier2 silver Opus JSONs")
    p.add_argument("--t3-dir", required=True,
                   help="Directory tree containing T3 (rule-based) JSONs (100K run output)")
    p.add_argument("--out", default="eval_t3_vs_t2",
                   help="Output directory for per-paper eval CSVs and summary")
    p.add_argument("--limit", type=int, default=None,
                   help="Only process first N papers (for smoke testing)")
    args = p.parse_args()

    t2_dir = Path(args.t2_dir).resolve()
    t3_dir = Path(args.t3_dir).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    t2_files = sorted(t2_dir.glob("paper*.json"))
    if args.limit:
        t2_files = t2_files[:args.limit]
    print(f"[eval] {len(t2_files)} tier2 papers to evaluate")

    n_evaluated = n_skipped = 0
    for i, t2_path in enumerate(t2_files, 1):
        paper_id = t2_path.stem  # e.g. "paper005"
        # Skip PDF-fallback papers (they have a source_note and weren't extracted by T3)
        d = json.load(open(t2_path))
        md = d.get("metadata") or {}
        arxiv_id = md.get("arxiv_id") or md.get("arxiv") or ""
        if "source_note" in md:
            n_skipped += 1
            continue

        t3_path = find_t3_json(t3_dir, paper_id)
        if t3_path is None:
            print(f"  [{i:3d}/{len(t2_files)}] {paper_id}: T3 file not found, skip")
            n_skipped += 1
            continue

        result_csv = out / f"{t2_path.stem}_results.csv"
        cmd = [
            sys.executable, str(EVAL),
            "--extracted", str(t3_path),
            "--gold", str(t2_path),
            "--csv", str(result_csv),
            "--exclude-origin", "external",  # only evaluate paper-origin nodes
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            print(f"  [{i:3d}/{len(t2_files)}] {arxiv_id}: eval failed ({proc.returncode})")
            print(f"    stderr: {proc.stderr[-500:]}")
            n_skipped += 1
            continue

        # Parse the produced CSV
        try:
            rows = list(csv.DictReader(open(result_csv)))
        except OSError:
            n_skipped += 1
            continue
        metrics = {r["metric"]: float(r["value"]) for r in rows
                   if r.get("metric") and r.get("value", "").replace(".", "", 1).replace("-", "", 1).isdigit()}
        summary_rows.append({
            "paper_id": t2_path.stem,
            "arxiv_id": arxiv_id,
            "node_precision": metrics.get("node_precision", 0),
            "node_recall":    metrics.get("node_recall", 0),
            "node_f1":        metrics.get("node_f1", 0),
            "edge_precision": metrics.get("edge_precision", 0),
            "edge_recall":    metrics.get("edge_recall", 0),
            "edge_f1":        metrics.get("edge_f1", 0),
        })
        n_evaluated += 1
        if i % 25 == 0:
            print(f"  [{i:3d}/{len(t2_files)}] evaluated so far: {n_evaluated}")

    # Write summary CSV
    summary_csv = out / "summary.csv"
    if summary_rows:
        with open(summary_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            w.writeheader()
            w.writerows(summary_rows)

    print()
    print(f"[eval] done: {n_evaluated} evaluated, {n_skipped} skipped")
    if summary_rows:
        for metric in ("node_f1", "node_precision", "node_recall",
                       "edge_f1", "edge_precision", "edge_recall"):
            vals = [r[metric] for r in summary_rows if r[metric]]
            if vals:
                print(f"  mean {metric:18s}: {statistics.mean(vals):.3f}  "
                      f"median: {statistics.median(vals):.3f}  "
                      f"n={len(vals)}")
        print(f"\n  -> per-paper summary: {summary_csv}")
        print(f"  -> per-paper eval CSVs: {out}/paper*_results.csv")


if __name__ == "__main__":
    main()
