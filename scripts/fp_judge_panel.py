#!/usr/bin/env python3
"""Compare several local judges against Claude, and against each other.

Each replay CSV holds one judge's verdict beside Claude's on the same 151
snippets, so the panel question can be answered from the files alone: when the
local judges agree with one another, is the agreed verdict right?

Two numbers decide whether a panel is worth building. The first is how often
they agree at all -- unanimity on every row would mean the judges are
interchangeable and a panel buys nothing. The second is precision *given*
unanimity: if agreement does not predict correctness, the split rows are not
the hard ones, they are just noise.

Reports the forgiveness rate throughout rather than row agreement, because
that is the quantity the FP-judge step actually feeds into precision, and a
judge can agree on few rows while reproducing it exactly.

Usage:
    python scripts/fp_judge_panel.py <eval-dir>/fp_judge_{qwen,gemma,mistral}.csv
"""

import argparse
import csv
import itertools
from collections import Counter
from pathlib import Path


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+", help="fp_judge_<model>.csv replay outputs")
    ap.add_argument("--names", default=None,
                    help="comma list overriding the names taken from filenames")
    args = ap.parse_args()

    tables = [load(p) for p in args.csvs]
    names = (args.names.split(",") if args.names else
             [Path(p).stem.replace("fp_judge_", "") for p in args.csvs])

    n = len(tables[0])
    for nm, t in zip(names, tables):
        if len(t) != n:
            raise SystemExit(f"{nm}: {len(t)} rows, expected {n} -- "
                             "all replays must come from the same fp_judge.csv")
    # Row order is inherited from the source CSV, but verify rather than trust:
    # a mismatched join would quietly compare different snippets.
    for i in range(n):
        keys = {(t[i]["type"], t[i]["paper_id"]) for t in tables}
        if len(keys) != 1:
            raise SystemExit(f"row {i}: files disagree on identity {keys}")

    claude = [tables[0][i]["claude_verdict"] for i in range(n)]
    votes = {nm: [t[i]["local_verdict"] for i in range(n)]
             for nm, t in zip(names, tables)}

    def forgive(v):
        return sum(1 for x in v if x == "GENUINE") / len(v)

    print(f"{n} rows\n")
    print(f"{'judge':<16}{'agree w/ Claude':>17}{'forgiveness':>14}{'gap':>8}")
    print(f"{'claude':<16}{'':>17}{forgive(claude):>13.1%}{'':>8}")
    for nm in names:
        a = sum(1 for i in range(n) if votes[nm][i] == claude[i])
        f = forgive(votes[nm])
        print(f"{nm:<16}{a:>10}/{n:<6}{f:>13.1%}{f - forgive(claude):>+8.1%}")

    # ---- do the judges actually differ? ----
    print("\npairwise agreement between local judges")
    for a, b in itertools.combinations(names, 2):
        k = sum(1 for i in range(n) if votes[a][i] == votes[b][i])
        print(f"  {a:<16} vs {b:<16} {k:>4}/{n}  {k/n:>6.1%}")

    # ---- the panel ----
    unanimous = [i for i in range(n)
                 if len({votes[nm][i] for nm in names}) == 1]
    split = [i for i in range(n) if i not in set(unanimous)]

    maj = []
    for i in range(n):
        c = Counter(votes[nm][i] for nm in names)
        maj.append(c.most_common(1)[0][0])

    maj_ok = sum(1 for i in range(n) if maj[i] == claude[i])
    uni_ok = sum(1 for i in unanimous if maj[i] == claude[i])

    print(f"\npanel of {len(names)}")
    print(f"  unanimous            {len(unanimous):>4}/{n}  {len(unanimous)/n:>6.1%}")
    print(f"  split                {len(split):>4}/{n}  {len(split)/n:>6.1%}")
    print(f"  majority = Claude    {maj_ok:>4}/{n}  {maj_ok/n:>6.1%}")
    if unanimous:
        print(f"  correct WHEN unanimous {uni_ok:>2}/{len(unanimous)}  {uni_ok/len(unanimous):>6.1%}"
              "   <- the number that justifies a panel")
    print(f"  majority forgiveness {forgive(maj):>12.1%}   "
          f"(Claude {forgive(claude):.1%})")

    # Escalating only the splits is only cheap if the splits are few, and only
    # useful if what survives is reliable. Both halves are reported.
    if split:
        rest = [i for i in range(n) if i not in set(split)]
        kept_ok = sum(1 for i in rest if maj[i] == claude[i])
        print(f"\nescalate the {len(split)} split rows to Claude, keep the rest:")
        print(f"  API calls        {len(split)}/{n}  ({1 - len(split)/n:.0%} fewer)")
        print(f"  kept rows right  {kept_ok}/{len(rest)}  {kept_ok/len(rest):.1%}")


if __name__ == "__main__":
    main()
