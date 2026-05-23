"""Export Method E retrieval candidates (PRE-judge) as a ranked CSV.

Sibling of export_triage.py. That module reads judged_candidates.jsonl
and groups by verdict; this one reads the raw candidates.jsonl emitted
by Phase 2b (retrieve_pairs.py) and produces a tractability-ranked CSV
without requiring a judge pass to have run.

Use this when:
  - Phase 2c (judge) hasn't run yet, or
  - You want the unfiltered ranked candidate list before any LLM verdict.

Sort key (descending priority):
  1. cites_problem_paper == False FIRST (structural cases first; the
     "candidate paper doesn't cite the problem paper" pairs are the
     interesting discovery candidates).
  2. cites_problem_paper == True SECOND (still useful but less novel).
  3. cites_problem_paper unknown LAST.
  4. Within each cite-bucket, sort by combined score DESC.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _sort_key(row: dict) -> tuple:
    cites = row.get("cites_problem_paper")
    rank_cite = 0 if cites is False else (1 if cites is True else 2)
    return (rank_cite, -float(row.get("combined") or 0.0))


def export(
    candidates_path: Path,
    out_csv: Path,
    *,
    top_n: int | None = None,
    min_score: float | None = None,
) -> dict:
    rows: list[dict] = []
    with candidates_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if min_score is not None and float(r.get("combined") or 0.0) < min_score:
                continue
            rows.append(r)

    rows.sort(key=_sort_key)
    if top_n is not None:
        rows = rows[:top_n]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "rank",
        "cites_problem_paper",
        "same_author",
        "combined",
        "foundation_overlap",
        "operator_overlap",
        "statement_jaccard",
        "conclusion_compat",
        "years_apart",
        "problem_paper",
        "problem_year",
        "problem_id",
        "candidate_paper",
        "candidate_year",
        "candidate_id",
        "canonical_substituted",
        "problem_text",
        "candidate_text",
        "problem_url",
        "candidate_url",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, r in enumerate(rows, 1):
            w.writerow([
                i,
                r.get("cites_problem_paper") if r.get("cites_problem_paper") is not None else "",
                r.get("same_author") if r.get("same_author") is not None else "",
                round(float(r.get("combined") or 0.0), 4),
                round(float(r.get("foundation_overlap") or 0.0), 4),
                round(float(r.get("operator_overlap") or 0.0), 4),
                round(float(r.get("statement_jaccard") or 0.0), 4),
                round(float(r.get("conclusion_compat") or 0.0), 4),
                r.get("years_apart") or "",
                r.get("problem_paper") or "",
                r.get("problem_year") or "",
                r.get("problem_id") or "",
                r.get("candidate_paper") or "",
                r.get("candidate_year") or "",
                r.get("candidate_id") or "",
                bool(r.get("canonical_substituted")),
                (r.get("problem_text") or "")[:600].replace("\n", " "),
                (r.get("candidate_text") or "")[:600].replace("\n", " "),
                f"https://arxiv.org/abs/{r.get('problem_paper')}" if r.get("problem_paper") else "",
                f"https://arxiv.org/abs/{r.get('candidate_paper')}" if r.get("candidate_paper") else "",
            ])

    print(f"[export_candidates] wrote {len(rows)} rows -> {out_csv}",
          file=sys.stderr)
    return {"rows_in": len(rows), "rows_out": len(rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", required=True,
                    help="Path to candidates.jsonl from Phase 2b")
    ap.add_argument("--out", required=True,
                    help="Output CSV path")
    ap.add_argument("--top-n", type=int, default=None,
                    help="Cap rows in output (default: all)")
    ap.add_argument("--min-score", type=float, default=None,
                    help="Drop rows with combined < this (default: no filter)")
    args = ap.parse_args()
    export(
        candidates_path=Path(args.candidates),
        out_csv=Path(args.out),
        top_n=args.top_n,
        min_score=args.min_score,
    )


if __name__ == "__main__":
    main()
