#!/usr/bin/env python3
"""Aggregate per-student score CSVs into a ranked LEADERBOARD.md.

Reads, for each student, the AVERAGE row of:
    results/<id>/train/summary.csv
    results/<id>/test/summary.csv      (if present)
(falls back to results/<id>/summary.csv for a single-split run), and writes a
markdown table ranked by combined F1 (test if available, else train).

Examples:
    python3 make_leaderboard.py --results results --out LEADERBOARD.md
    python3 make_leaderboard.py --results results --rank-by test --anonymize
"""

import argparse
import csv
import glob
import hashlib
import os


def read_avg(summary_path):
    """Return the AVERAGE row metrics from a run_all summary.csv, or None."""
    if not os.path.exists(summary_path):
        return None
    with open(summary_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("document") == "AVERAGE":
                def g(k):
                    try:
                        return float(row[k])
                    except (KeyError, ValueError, TypeError):
                        return None
                def trip(p, r, f):
                    return {"P": g(p), "R": g(r), "F1": g(f)}
                def avg2(a, b):
                    return (a + b) / 2 if (a is not None and b is not None) else None
                # node, edge, and combined (avg of the two; F1 is the brief's combined_F1,
                # the ranked metric).
                return {"node": trip("node_P", "node_R", "node_F1"),
                        "edge": trip("edge_P", "edge_R", "edge_F1"),
                        "combined": {"P": avg2(g("node_P"), g("edge_P")),
                                     "R": avg2(g("node_R"), g("edge_R")),
                                     "F1": g("combined_F1")}}
    return None


def main():
    ap = argparse.ArgumentParser(description="Build LEADERBOARD.md from per-student score CSVs.")
    ap.add_argument("--results", default="results", help="Directory with results/<id>/<split>/summary.csv")
    ap.add_argument("--out", default="LEADERBOARD.md")
    ap.add_argument("--rank-by", choices=["test", "train"], default="test",
                    help="Which split's combined F1 to rank by (falls back to train if test missing)")
    ap.add_argument("--anonymize", action="store_true",
                    help="Replace ids with a stable pseudonym (student-<hash>)")
    ap.add_argument("--title", default="Big Data Project 52017 Leaderboard")
    ap.add_argument("--note", default="",
                    help="Optional explanatory line printed under the title (student-facing framing)")
    args = ap.parse_args()

    students = sorted(d for d in glob.glob(os.path.join(args.results, "*")) if os.path.isdir(d))
    rows = []
    for sd in students:
        sid = os.path.basename(sd)
        tr = read_avg(os.path.join(sd, "train", "summary.csv"))
        te = read_avg(os.path.join(sd, "test", "summary.csv"))
        if tr is None and te is None:
            tr = read_avg(os.path.join(sd, "summary.csv"))  # single-split fallback
        rows.append({"id": sid, "train": tr, "test": te})

    def rank_key(r):
        primary = r["test"] if (args.rank_by == "test" and r["test"]) else r["train"]
        return primary["combined"]["F1"] if primary and primary["combined"]["F1"] is not None else -1.0

    rows.sort(key=rank_key, reverse=True)

    def cell(split, typ):
        """One 'P/R/F1' cell (F1 bold) for split['node'|'edge'|'combined'], or '-'."""
        m = split.get(typ) if split else None
        if not m or m.get("F1") is None:
            return "-"
        p = "-" if m["P"] is None else f"{m['P']:.3f}"
        r = "-" if m["R"] is None else f"{m['R']:.3f}"
        return f"{p}/{r}/**{m['F1']:.3f}**"

    def label(sid):
        if not args.anonymize:
            return sid
        return "student-" + hashlib.sha1(sid.encode()).hexdigest()[:6]

    rank_desc = ("Ranked by **combined F1** on the test set (train shown when no test score yet)."
                 if args.rank_by == "test" else "Ranked by **combined F1** on the train set.")
    lines = [f"# {args.title}", ""]
    if args.note:
        lines += [args.note, ""]
    lines += [f"{rank_desc} Each cell is **P/R/F1** (F1 in bold); 'combined' is the average of nodes and edges. "
              f"{len(rows)} submissions.", "",
             "| Rank | Submission | Train node | Train edge | Train combined | Test node | Test edge | Test combined |",
             "|---:|---|---:|---:|---:|---:|---:|---:|"]
    for rank, r in enumerate(rows, 1):
        tr, te = r["train"], r["test"]
        lines.append(
            f"| {rank} | {label(r['id'])} | {cell(tr,'node')} | {cell(tr,'edge')} | {cell(tr,'combined')} "
            f"| {cell(te,'node')} | {cell(te,'edge')} | {cell(te,'combined')} |")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {args.out} ({len(rows)} submissions)")


if __name__ == "__main__":
    main()
