"""Export Method E judged candidates as a hand-triage CSV.

Sort by (verdict==YES) DESC, (cites_problem_paper==False) DESC, combined DESC.
Headline rows are YES verdicts on candidates that do NOT cite the problem
paper — those are the K_structural cases.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _sort_key(row: dict) -> tuple:
    j = row.get("judge") or {}
    verdict = (j.get("verdict") or "NO").upper()
    rank_verdict = {"YES": 0, "MAYBE": 1, "NO": 2, "PARSE_ERROR": 3}.get(verdict, 4)
    cites = row.get("cites_problem_paper")
    # Headline first: not-cites > cites > unknown
    rank_cite = 0 if cites is False else (1 if cites is True else 2)
    return (rank_verdict, rank_cite, -float(row.get("combined") or 0.0))


def export(
    judged_path: Path,
    out_csv: Path,
    *,
    include_verdicts: list[str] = None,
) -> dict:
    include = set(include_verdicts) if include_verdicts else {"YES", "MAYBE"}
    rows: list[dict] = []
    with judged_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    rows.sort(key=_sort_key)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "rank",
            "verdict",
            "relationship",
            "cites_problem_paper",
            "same_author",
            "combined",
            "foundation_overlap",
            "operator_overlap",
            "statement_jaccard",
            "years_apart",
            "problem_paper",
            "problem_year",
            "problem_node",
            "candidate_paper",
            "candidate_year",
            "candidate_node",
            "canonical_substituted",
            "justification",
            "problem_text",
            "candidate_text",
            "problem_url",
            "candidate_url",
        ])
        for i, r in enumerate(rows, 1):
            j = r.get("judge") or {}
            v = (j.get("verdict") or "NO").upper()
            if v not in include:
                continue
            n_written += 1
            w.writerow([
                i,
                v,
                j.get("relationship") or "",
                r.get("cites_problem_paper") if r.get("cites_problem_paper") is not None else "",
                r.get("same_author") if r.get("same_author") is not None else "",
                round(float(r.get("combined") or 0.0), 4),
                round(float(r.get("foundation_overlap") or 0.0), 4),
                round(float(r.get("operator_overlap") or 0.0), 4),
                round(float(r.get("statement_jaccard") or 0.0), 4),
                r.get("years_apart") or "",
                r.get("problem_paper") or "",
                r.get("problem_year") or "",
                r.get("problem_id") or "",
                r.get("candidate_paper") or "",
                r.get("candidate_year") or "",
                r.get("candidate_id") or "",
                bool(r.get("canonical_substituted")),
                j.get("justification") or "",
                (r.get("problem_text") or "")[:600].replace("\n", " "),
                (r.get("candidate_text") or "")[:600].replace("\n", " "),
                f"https://arxiv.org/abs/{r.get('problem_paper')}" if r.get('problem_paper') else "",
                f"https://arxiv.org/abs/{r.get('candidate_paper')}" if r.get('candidate_paper') else "",
            ])
    print(f"[export] wrote {n_written} triage rows -> {out_csv}", file=sys.stderr)
    return {"rows_in": len(rows), "rows_out": n_written}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judged", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--include", default="YES,MAYBE",
                    help="Comma-sep verdicts to include (default: YES,MAYBE)")
    args = ap.parse_args()
    export(
        judged_path=Path(args.judged),
        out_csv=Path(args.out),
        include_verdicts=[v.strip().upper() for v in args.include.split(",") if v.strip()],
    )


if __name__ == "__main__":
    main()
