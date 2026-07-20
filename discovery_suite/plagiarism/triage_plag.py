"""T-PLAG triage — turn the raw P1 paper-pair sweep into a reviewable shortlist.

P1 runs at high recall (min_jaccard 0.2), so the corpus sweep emits ~750k paper
pairs at 100k — far too many to read. This filters to the strong reuse signal
(high max node-Jaccard, several shared nodes) and prints the score distribution
so thresholds are chosen from data, not guesswork. Sibling of the open-problems
triage step; read-only consumer of the sweep CSV.

    python discovery_suite/plagiarism/triage_plag.py \
        --in  discovery_suite/plagiarism/runs/plag_sweep_100k.csv \
        --out discovery_suite/plagiarism/runs/plag_triage_top.csv \
        --min-score-max 0.8 --min-nodes 2
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd


def _reaggregate(nodes_csv, paper_df, max_node_papers):
    """Re-build paper-pair rows from the node-evidence CSV, dropping *promiscuous*
    nodes (a node matching more than max_node_papers distinct papers is generic
    boilerplate — 'the proof is analogous to that of theorem', standard lemmas —
    an IDF/document-frequency filter). Categories are joined back from paper_df.
    Returns (paper_pair_df, n_generic_nodes)."""
    nd = pd.read_csv(nodes_csv, dtype={
        "source_key": str, "target_key": str, "source_paper": str,
        "target_paper": str, "source_snippet": str, "target_snippet": str})
    n_generic = 0
    if max_node_papers and max_node_papers > 0:
        seen: dict[str, set] = defaultdict(set)
        for sk, tk, sp, tp in zip(nd.source_key, nd.target_key,
                                  nd.source_paper, nd.target_paper):
            seen[sk].add(tp)
            seen[tk].add(sp)
        generic = {k for k, v in seen.items() if len(v) > max_node_papers}
        n_generic = len(generic)
        nd = nd[~(nd.source_key.isin(generic) | nd.target_key.isin(generic))]

    catmap = {(str(r.source_paper), str(r.target_paper)): (r.source_cat, r.target_cat)
              for r in paper_df.itertuples(index=False)}
    rows = []
    for (sp, tp), g in nd.groupby(["source_paper", "target_paper"], sort=False):
        best = g.loc[g["est_jaccard"].idxmax()]
        scat, tcat = catmap.get((sp, tp), ("", ""))
        rows.append({
            "score_max": g.est_jaccard.max(), "score_sum": g.est_jaccard.sum(),
            "n_shared_nodes": len(g),
            "source_paper": sp, "source_year": int(best.source_year), "source_cat": scat,
            "target_paper": tp, "target_year": int(best.target_year), "target_cat": tcat,
            "cross_category": int(best.cross_category), "same_year": int(best.same_year),
            "best_source_key": best.source_key, "best_target_key": best.target_key,
            "best_source_snippet": best.source_snippet,
            "best_target_snippet": best.target_snippet,
        })
    return pd.DataFrame(rows), n_generic


def _authorize(hot, index_path):
    """Add shared_authors + self_reuse columns via the author index. Unknown (id
    missing from the index) -> -1, so those pairs are neither cleared nor dropped.
    Returns (annotated_df, n_pairs_with_both_authors_known)."""
    with open(index_path, encoding="utf-8") as fh:
        idx = json.load(fh)
    shared, self_r, known = [], [], 0
    for _, r in hot.iterrows():
        a = idx.get(str(r.source_paper))
        b = idx.get(str(r.target_paper))
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
                    default="discovery_suite/plagiarism/runs/plag_sweep_100k.csv")
    ap.add_argument("--out",
                    default="discovery_suite/plagiarism/runs/plag_triage_top.csv")
    ap.add_argument("--min-score-max", type=float, default=0.8,
                    help="keep paper pairs with at least one node this similar")
    ap.add_argument("--min-nodes", type=int, default=2,
                    help="keep pairs sharing at least this many reused nodes")
    ap.add_argument("--cross-category", action="store_true",
                    help="keep ONLY cross-category pairs (default: keep all — "
                         "intra-field reuse is common in plagiarism)")
    ap.add_argument("--exclude-same-year", action="store_true",
                    help="drop same-year pairs (keep only reuse across years, where "
                         "the older-source direction is unambiguous)")
    ap.add_argument("--author-index", default=None,
                    help="author index JSON (build_author_index.py). Adds "
                         "shared_authors + self_reuse columns.")
    ap.add_argument("--exclude-self-reuse", action="store_true",
                    help="drop same-author pairs (needs --author-index); surfaces "
                         "the cross-author reuse that is the real plagiarism target. "
                         "Author-unknown pairs are KEPT.")
    ap.add_argument("--nodes-csv", default=None,
                    help="node-evidence CSV (<sweep>_nodes.csv). Enables the "
                         "promiscuity filter: re-aggregate paper pairs after dropping "
                         "generic nodes. No sweep re-run needed.")
    ap.add_argument("--max-node-papers", type=int, default=0,
                    help="with --nodes-csv: drop nodes matching more than this many "
                         "distinct papers (generic boilerplate / standard statements). "
                         "0 = off. Try 10-30.")
    ap.add_argument("--top", type=int, default=0, help="cap output rows (0 = all)")
    args = ap.parse_args()

    # arXiv ids like 1002.1960 look numeric — pandas would read them as floats and
    # drop the trailing zero (1002.196), breaking paper lookup. Force string dtype.
    df = pd.read_csv(args.inp, dtype={
        "source_paper": str, "target_paper": str, "source_cat": str,
        "target_cat": str, "best_source_key": str, "best_target_key": str,
        "best_source_snippet": str, "best_target_snippet": str})

    if args.nodes_csv:
        df, n_generic = _reaggregate(args.nodes_csv, df, args.max_node_papers)
        print(f"re-aggregated from {args.nodes_csv}: dropped {n_generic:,} promiscuous "
              f"nodes (>{args.max_node_papers} papers) -> {len(df):,} paper pairs")
    elif args.max_node_papers:
        raise SystemExit("--max-node-papers requires --nodes-csv")

    print(f"{len(df):,} paper pairs in {args.inp}")
    print("score_max distribution:")
    print(df["score_max"].describe()[["min", "25%", "50%", "75%", "max"]].to_string())
    print(f"cross-category pairs : {int(df.cross_category.sum()):,}")
    print(f"same-year pairs      : {int(df.same_year.sum()):,}")

    hot = df[(df.score_max >= args.min_score_max) & (df.n_shared_nodes >= args.min_nodes)]
    if args.cross_category:
        hot = hot[hot.cross_category == 1]
    if args.exclude_same_year:
        hot = hot[hot.same_year == 0]

    if args.author_index:
        hot, known = _authorize(hot, args.author_index)
        n_self = int((hot.self_reuse == 1).sum())
        n_unk = int((hot.self_reuse == -1).sum())
        print(f"\nauthor gate: {known:,}/{len(hot):,} pairs have both authors known; "
              f"{n_self:,} same-author (self-reuse), {n_unk:,} author-unknown")
        if args.exclude_self_reuse:
            hot = hot[hot.self_reuse != 1]
            print(f"  excluded self-reuse -> {len(hot):,} pairs remain")
    elif args.exclude_self_reuse:
        raise SystemExit("--exclude-self-reuse requires --author-index")

    hot = hot.sort_values(["score_max", "n_shared_nodes", "score_sum"],
                          ascending=False)
    if args.top:
        hot = hot.head(args.top)

    print(f"\n{len(hot):,} pairs pass the filter "
          f"(score_max>={args.min_score_max}, n_shared_nodes>={args.min_nodes}"
          f"{', cross-category' if args.cross_category else ''}"
          f"{', cross-year' if args.exclude_same_year else ''})\n")
    has_auth = "self_reuse" in hot.columns
    for _, r in hot.head(20).iterrows():
        tag = "XCAT" if r.cross_category else "    "
        auth = ""
        if has_auth:
            auth = ("SELF" if r.self_reuse == 1 else
                    "?   " if r.self_reuse == -1 else "XAUT")
        print(f"  {r.score_max:.2f} x{int(r.n_shared_nodes):<4} {tag} {auth} "
              f"{r.source_paper}({r.source_cat}) -> {r.target_paper}({r.target_cat})")
        print(f"        {str(r.best_source_snippet)[:88]}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    hot.to_csv(args.out, index=False)
    print(f"\nwrote {len(hot):,} rows -> {args.out}")
    print("[next] adjudicate the top rows with the P4 judge:")
    print("  python3 discovery_suite/plagiarism/p4_judge.py --triage "
          f"{args.out} --root $ROOT --top 50 --model sonnet")


if __name__ == "__main__":
    main()
