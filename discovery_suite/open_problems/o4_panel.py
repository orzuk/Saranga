#!/usr/bin/env python3
"""Compare O4 judges against each other, and against Claude where that is fair.

Unlike the FP judge, agreement here is a near-useless number: the great
majority of pairs are UNRELATED, so a judge that answered NO to everything
would score in the nineties. What matters is the positives -- how many a judge
raises, and whether the ones Claude found are among them.

Claude's verdicts predate the relationship taxonomy, so a local model
disagreeing with them may be reacting to the prompt rather than judging
differently. Claude columns are therefore reported only for the pairs it called
non-NO, as a recall check, and never as an accuracy score.

Usage:
    python discovery_suite/open_problems/o4_panel.py runs/o4_verdicts_*.csv
"""

import argparse
import csv
import itertools
from collections import Counter
from pathlib import Path

POSITIVE = {"YES", "PARTIAL"}


def load(path):
    rows = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        rows[(r["problem_key"], r["theorem_key"])] = r
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--names", default=None)
    ap.add_argument("--sets", action="store_true",
                    help="print which models called each item positive, counted "
                         "per pattern -- the input to an intersection plot")
    ap.add_argument("--claude", default=None,
                    help="Claude verdicts CSV; reported as a recall check only")
    args = ap.parse_args()

    tables = [load(p) for p in args.csvs]
    names = (args.names.split(",") if args.names else
             [Path(p).stem.replace("o4_verdicts_", "") for p in args.csvs])

    keys = set(tables[0])
    for t in tables[1:]:
        keys &= set(t)
    keys = sorted(keys)
    print(f"{len(keys)} pairs judged by all {len(names)} models\n")

    def verdict(t, k):
        return (t[k].get("verdict") or "").strip().upper()

    def rel(t, k):
        return (t[k].get("relationship") or "").strip().upper() or "-"

    # ---- what each model raises ----
    print(f"{'judge':<18}{'YES':>6}{'PARTIAL':>9}{'NO':>6}{'positives':>11}")
    for nm, t in zip(names, tables):
        c = Counter(verdict(t, k) for k in keys)
        pos = sum(c[v] for v in POSITIVE)
        print(f"{nm:<18}{c['YES']:>6}{c['PARTIAL']:>9}{c['NO']:>6}"
              f"{pos:>8} {pos/len(keys):>5.0%}")

    if any("relationship" in t[keys[0]] for t in tables):
        print("\nrelationship labels")
        labels = sorted({rel(t, k) for t in tables for k in keys})
        print(f"{'judge':<18}" + "".join(f"{l[:13]:>15}" for l in labels))
        for nm, t in zip(names, tables):
            c = Counter(rel(t, k) for k in keys)
            print(f"{nm:<18}" + "".join(f"{c[l]:>15}" for l in labels))

    # ---- do they agree with each other? ----
    print("\npairwise agreement (verdict)")
    for (a, ta), (b, tb) in itertools.combinations(zip(names, tables), 2):
        n = sum(1 for k in keys if verdict(ta, k) == verdict(tb, k))
        print(f"  {a:<18} vs {b:<18} {n:>4}/{len(keys)}  {n/len(keys):>6.1%}")

    # ---- the panel ----
    unan_pos, unan_neg, split = [], [], []
    for k in keys:
        vs = {verdict(t, k) for t in tables}
        if len(vs) == 1:
            (unan_pos if vs.pop() in POSITIVE else unan_neg).append(k)
        else:
            split.append(k)
    print(f"\npanel of {len(names)}")
    print(f"  unanimous positive {len(unan_pos):>5}")
    print(f"  unanimous NO       {len(unan_neg):>5}")
    print(f"  split              {len(split):>5}  {len(split)/len(keys):>6.1%}")
    print(f"  -> escalating only the splits costs {len(split)}/{len(keys)} calls "
          f"({1 - len(split)/len(keys):.0%} fewer)")

    # ---- intersections ----
    # Which models called an item positive, as a set. Four judges give sixteen
    # possible patterns, so this is reported as counts per pattern rather than
    # drawn as circles -- a four-set Venn needs ellipses and stops being
    # readable well before it stops being drawable.
    if args.sets:
        pat = Counter()
        for k in keys:
            who = tuple(nm for nm, t in zip(names, tables)
                        if verdict(t, k) in POSITIVE)
            pat[who] += 1
        print("\nintersections — models calling an item POSITIVE")
        print(f"{'pattern':<40}{'n':>6}")
        for who, n in sorted(pat.items(), key=lambda kv: (-len(kv[0]), -kv[1])):
            label = "+".join(who) if who else "(none — all four said NO)"
            print(f"{label:<40}{n:>6}")
        print(f"{'TOTAL':<40}{sum(pat.values()):>6}")

    # ---- recall against Claude, with the caveat attached ----
    if args.claude:
        cl = load(args.claude)
        gold = [k for k in keys if k in cl
                and (cl[k].get("verdict") or "").strip().upper() in POSITIVE]
        print(f"\nClaude called {len(gold)} of these non-NO "
              "(OLD prompt -- recall check only, not an accuracy score)")
        print(f"{'judge':<18}{'recovered':>11}")
        for nm, t in zip(names, tables):
            got = sum(1 for k in gold if verdict(t, k) in POSITIVE)
            print(f"{nm:<18}{got:>7}/{len(gold)}")
        pan = sum(1 for k in gold
                  if sum(verdict(t, k) in POSITIVE for t in tables) > len(tables) / 2)
        print(f"{'majority':<18}{pan:>7}/{len(gold)}")
        print("\nthe pairs Claude found, per judge")
        hdr = f"{'problem -> theorem':<46}{'claude':>8}"
        print(hdr + "".join(f"{n[:10]:>12}" for n in names))
        for k in gold:
            row = f"{k[0] + ' -> ' + k[1]:<46}{cl[k]['verdict']:>8}"
            print(row + "".join(f"{verdict(t, k):>12}" for t in tables))


if __name__ == "__main__":
    main()
