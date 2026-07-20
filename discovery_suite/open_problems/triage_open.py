"""T-OPEN triage — turn the raw O1 problem->theorem sweep into a reviewable shortlist.

sweep_open.py runs at high recall (min_score 0.10) and emits top-k theorems per
problem, so the corpus sweep produces far more pairs than anyone can read. This is
a read-only consumer of that CSV (like plagiarism/triage_plag.py): it prints the
score distribution, applies data-driven filters, and writes a ranked shortlist for
the O4 judge.

    python discovery_suite/open_problems/triage_open.py \
        --in  discovery_suite/open_problems/runs/open_sweep_100k_raw.csv \
        --out discovery_suite/open_problems/runs/triage_top.csv \
        --min-score 0.5 --cross-category --per-problem 3

Design decisions worth knowing:
  * SHORT snippets are ROUTED, not deleted. A statement like "the map psi is a
    bijection" is uninformative in isolation but its meaning lives in neighbouring
    nodes/edges, so short pairs get a needs_context=1 flag (feed the node's graph
    neighbourhood to O4) rather than being dropped. --drop-degenerate is opt-in for
    the truly tiny ones (< --min-words tokens) that survive no context.
  * TEMPORAL direction is a hard requirement (a solution can't predate its problem).
    The sweep enforces it at YEAR granularity; here we tighten to YYMM (arXiv id
    month), dropping theorems that predate their problem within the same year. The
    ghost-number pair (theorem 1301 vs conjecture 1310) is exactly this case.
  * The AUTHOR gate ("neither side aware") reuses the plagiarism author index.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _yymm(key: str) -> int | None:
    """arXiv YYMM (as int) from a 'paperid::nodeid' key, or None if unparseable.

    New-style ids look like '1310.5682' -> 1310. Old-style ('math/0501001') and
    anything else return None so the pair is KEPT (never dropped on a guess)."""
    pid = str(key).split("::", 1)[0]
    head = pid.split(".", 1)[0]
    return int(head) if head.isdigit() and len(head) == 4 else None


def _authorize(hot: pd.DataFrame, index_path: str) -> tuple[pd.DataFrame, int]:
    """Add shared_authors + self_reuse via the author index (paper_id -> [authors]).
    Unknown ids -> -1 (neither cleared nor dropped). Returns (df, n_both_known)."""
    with open(index_path, encoding="utf-8") as fh:
        idx = json.load(fh)
    shared, self_r, known = [], [], 0
    for _, r in hot.iterrows():
        a = idx.get(str(r.problem_key).split("::", 1)[0])
        b = idx.get(str(r.theorem_key).split("::", 1)[0])
        if a is None or b is None:
            shared.append(-1)
            self_r.append(-1)
        else:
            known += 1
            n = len(set(a) & set(b))
            shared.append(n)
            self_r.append(1 if n > 0 else 0)
    hot = hot.copy()
    hot["shared_authors"] = shared
    hot["self_reuse"] = self_r
    return hot, known


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp",
                    default="discovery_suite/open_problems/runs/open_sweep_100k_raw.csv")
    ap.add_argument("--out",
                    default="discovery_suite/open_problems/runs/triage_top.csv")
    ap.add_argument("--min-score", type=float, default=0.5,
                    help="keep problem->theorem pairs at least this similar (Jaccard)")
    ap.add_argument("--cross-category", action="store_true",
                    help="keep ONLY cross-category pairs (the strongest 'neither side "
                         "aware' signal). Default: keep all.")
    ap.add_argument("--per-problem", type=int, default=0,
                    help="cap theorems kept per problem (0 = all). A problem repeats "
                         "across its top-k theorems; 3 keeps the shortlist readable.")
    ap.add_argument("--short-words", type=int, default=10,
                    help="either snippet below this many tokens -> needs_context=1 "
                         "(route to O4 with the node's graph neighbourhood, not drop).")
    ap.add_argument("--min-words", type=int, default=6,
                    help="with --drop-degenerate: hard-drop pairs whose snippet is "
                         "below this (too little content to judge even with context).")
    ap.add_argument("--drop-degenerate", action="store_true",
                    help="drop pairs with a snippet under --min-words tokens.")
    ap.add_argument("--allow-month-precedence", action="store_true",
                    help="keep theorems that predate their problem within the same "
                         "year. Default: drop them (YYMM temporal direction).")
    ap.add_argument("--author-index", default=None,
                    help="author index JSON (plagiarism/build_author_index.py). Adds "
                         "shared_authors + self_reuse columns.")
    ap.add_argument("--exclude-self-reuse", action="store_true",
                    help="drop same-author pairs (needs --author-index); surfaces the "
                         "cross-author resolutions that are the real target. "
                         "Author-unknown pairs are KEPT.")
    ap.add_argument("--top", type=int, default=0, help="cap output rows (0 = all)")
    args = ap.parse_args()

    # arXiv ids look numeric; force str so 1002.1960 doesn't become 1002.196.
    df = pd.read_csv(args.inp, dtype=str)
    df["score"] = df["score"].astype(float)
    df["cross_category"] = df["cross_category"].astype(int)

    print(f"{len(df):,} problem->theorem pairs in {args.inp}")
    print("score distribution:")
    print(df["score"].describe()[["min", "25%", "50%", "75%", "max"]].to_string())
    print(f"cross-category pairs : {int((df.cross_category == 1).sum()):,}")
    print(f"distinct problems     : {df.problem_key.nunique():,}")

    hot = df[df.score >= args.min_score].copy()
    if args.cross_category:
        hot = hot[hot.cross_category == 1]

    # temporal tighten: drop theorem that predates its problem by month (same year
    # slips through the sweep's year-only check). Unparseable ids are kept.
    if not args.allow_month_precedence:
        def _ok(r):
            pm, tm = _yymm(r.problem_key), _yymm(r.theorem_key)
            return pm is None or tm is None or tm >= pm
        before = len(hot)
        hot = hot[hot.apply(_ok, axis=1)]
        print(f"\nmonth temporal gate: dropped {before - len(hot):,} theorem-predates-"
              f"problem pairs -> {len(hot):,} remain")

    # short-snippet routing (flag, don't delete) + optional degenerate hard-drop
    pw = hot.problem_snippet.fillna("").str.split().str.len()
    tw = hot.theorem_snippet.fillna("").str.split().str.len()
    hot["needs_context"] = ((pw < args.short_words) | (tw < args.short_words)).astype(int)
    print(f"needs_context (short snippet, route to O4 w/ neighbourhood): "
          f"{int(hot.needs_context.sum()):,}/{len(hot):,}")
    if args.drop_degenerate:
        before = len(hot)
        hot = hot[(pw >= args.min_words) & (tw >= args.min_words)]
        print(f"dropped degenerate (< {args.min_words} tokens): "
              f"{before - len(hot):,} -> {len(hot):,} remain")

    if args.author_index:
        hot, known = _authorize(hot, args.author_index)
        n_self = int((hot.self_reuse == 1).sum())
        n_unk = int((hot.self_reuse == -1).sum())
        print(f"\nauthor gate: {known:,}/{len(hot):,} pairs have both authors known; "
              f"{n_self:,} same-author (self-resolution), {n_unk:,} author-unknown")
        if args.exclude_self_reuse:
            hot = hot[hot.self_reuse != 1]
            print(f"  excluded self-resolution -> {len(hot):,} pairs remain")
    elif args.exclude_self_reuse:
        raise SystemExit("--exclude-self-reuse requires --author-index")

    hot = hot.sort_values(["score", "problem_key", "theorem_key"],
                          ascending=[False, True, True])
    if args.per_problem:
        hot = hot.groupby("problem_key", sort=False).head(args.per_problem)
        hot = hot.sort_values(["score", "problem_key", "theorem_key"],
                              ascending=[False, True, True])
    if args.top:
        hot = hot.head(args.top)

    print(f"\n{len(hot):,} pairs pass the filter (score>={args.min_score}"
          f"{', cross-category' if args.cross_category else ''}"
          f"{f', <={args.per_problem}/problem' if args.per_problem else ''}) "
          f"across {hot.problem_key.nunique():,} problems\n")
    has_auth = "self_reuse" in hot.columns
    for _, r in hot.head(20).iterrows():
        tag = "XCAT" if r.cross_category else "    "
        ctx = "CTX!" if r.needs_context else "    "
        auth = ""
        if has_auth:
            auth = ("SELF" if r.self_reuse == 1 else
                    "?   " if r.self_reuse == -1 else "XAUT")
        print(f"  {r.score:.3f} {tag} {ctx} {auth} "
              f"{r.problem_key}({r.problem_cat}) -> {r.theorem_key}({r.theorem_cat})")
        print(f"        Q: {str(r.problem_snippet)[:84]}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    hot.to_csv(args.out, index=False)
    print(f"\nwrote {len(hot):,} rows -> {args.out}")
    print("[next] adjudicate the top rows with the O4 judge:")
    print("  python3 discovery_suite/open_problems/o4_judge.py "
          "--problem <problem_key> --theorem <theorem_key> --model opus")


if __name__ == "__main__":
    main()
