"""T-OPEN — lexical vs dense Erdős coverage, side by side.

The point of running both arms is not to pick a winner on a summary statistic.
Coverage has no ground truth (we know of exactly ONE verified match, Erdős–Gallai
= #184), so a "coverage rate" from either arm is unfalsifiable. What IS
measurable, and what this reports:

1. **Separation.** Word-matching's fatal property on the 100k run was that its
   score distribution had no gap — the true positive at 0.600 sat just above a
   p99 of 0.440, so no cut-off could split signal from noise. A method that
   ranks well should push its top scores clear of its own bulk. Reported as the
   distance from the top score to p99, in units of the bulk's spread.

2. **Disagreement.** If both arms return the same node for a problem, that is
   mutual corroboration. Where they disagree, one of them is wrong, and those
   rows are the shortlist worth judging — the same logic the semantic arm's
   overlap report uses for T-OPEN.

3. **The known case.** Where does #184 rank in each arm? An arm that loses the
   one match we have verified is disqualified regardless of its statistics.

Usage
-----
    python3 discovery_suite/open_problems/erdos_compare.py \
        --lexical discovery_suite/open_problems/runs/erdos_coverage_100k.csv \
        --dense   discovery_suite/open_problems/runs/erdos_dense_100k.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

#: The single Erdős problem whose match has been confirmed by hand.
KNOWN = {"184": "1310.0632::Cj1"}


def _read(path: Path, key_col: str, score_col: str, match_col: str) -> dict:
    """Best row per Erdős problem, tolerant of both arms' column names."""
    best: dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        cols = {c.lower(): c for c in (rdr.fieldnames or [])}

        def pick(*names):
            for n in names:
                if n in cols:
                    return cols[n]
            return None

        c_key = pick(key_col, "number", "problem_key", "query_key")
        c_score = pick(score_col, "score", "sim", "cosine")
        c_match = pick(match_col, "match_key", "theorem_key", "doc_key")
        if not (c_key and c_score and c_match):
            sys.exit(f"[compare] {path.name}: need key/score/match columns, "
                     f"saw {rdr.fieldnames}")

        for r in rdr:
            k = (r.get(c_key) or "").strip()
            # dense output keys queries as "erdos::184"; lexical uses "184"
            num = k.split("::")[-1]
            try:
                s = float(r.get(c_score) or 0)
            except ValueError:
                continue
            if num not in best or s > best[num]["score"]:
                best[num] = {"score": s, "match": (r.get(c_match) or "").strip()}
    return best


def _stats(rows: dict) -> dict:
    s = sorted(r["score"] for r in rows.values())
    n = len(s)
    if not n:
        return {}
    p = lambda q: s[min(n - 1, int(q * n))]  # noqa: E731
    p50, p90, p99, top = p(0.50), p(0.90), p(0.99), s[-1]
    spread = max(p90 - p50, 1e-9)
    return {"n": n, "p50": p50, "p90": p90, "p99": p99, "top": top,
            "separation": (top - p99) / spread}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lexical", required=True, type=Path)
    ap.add_argument("--dense", required=True, type=Path)
    ap.add_argument("--show", type=int, default=20)
    args = ap.parse_args()

    lex = _read(args.lexical, "number", "score", "match_key")
    den = _read(args.dense, "query_key", "score", "doc_key")
    ls, ds = _stats(lex), _stats(den)

    print("\n===== LEXICAL vs DENSE =====")
    print(f"{'':14}{'WORDS':>12}{'MEANING':>12}")
    for lbl, k in (("problems", "n"), ("median", "p50"), ("p90", "p90"),
                   ("p99", "p99"), ("top score", "top")):
        a, b = ls.get(k), ds.get(k)
        fmt = (lambda v: f"{v:>12}") if k == "n" else (lambda v: f"{v:>12.3f}")
        print(f"{lbl:14}{fmt(a) if a is not None else '':>12}"
              f"{fmt(b) if b is not None else '':>12}")
    print(f"\nSEPARATION (top - p99, in units of the bulk's own spread):")
    print(f"  words   {ls.get('separation', 0):.2f}")
    print(f"  meaning {ds.get('separation', 0):.2f}")
    print("  Higher is better: it means the top of the ranking stands clear of\n"
          "  the noise, so a cut-off can exist at all.")

    both = set(lex) & set(den)
    agree = [k for k in both if lex[k]["match"] and lex[k]["match"] == den[k]["match"]]
    print(f"\nAGREEMENT: {len(agree)} of {len(both)} problems got the same best "
          f"match from both arms ({len(agree)/max(len(both),1):.1%})")
    print("  Agreement is corroboration; disagreement is the shortlist to judge.")

    print("\nKNOWN CASE (the only match verified by hand):")
    for num, want in KNOWN.items():
        for label, d in (("words", lex), ("meaning", den)):
            got = d.get(num)
            if not got:
                print(f"  #{num} {label:8} MISSING from output")
                continue
            ok = "HIT " if got["match"] == want else "MISS"
            print(f"  #{num} {label:8} {ok} {got['match'] or '-':24} "
                  f"score {got['score']:.3f}")

    dis = sorted(((den[k]["score"], k) for k in both
                  if lex[k]["match"] != den[k]["match"]), reverse=True)
    print(f"\n--- top {min(args.show, len(dis))} disagreements (by dense score) ---")
    for s, k in dis[:args.show]:
        print(f"  #{k:<6} words -> {lex[k]['match'] or '-':24} {lex[k]['score']:.3f}"
              f"   |  meaning -> {den[k]['match'] or '-':24} {s:.3f}")


if __name__ == "__main__":
    main()
