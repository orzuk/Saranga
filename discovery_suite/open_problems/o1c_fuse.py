"""T-OPEN O1c — fuse the lexical and dense candidate sets into one shortlist.

``embed/fuse.py`` does the combining; this adds the T-OPEN question on top:
**what does the semantic arm actually buy?** It reports, before writing anything,
how much of the fused shortlist each arm contributed and — the number that decides
whether any of this was worth it — how many pairs the dense arm surfaced that the
lexical sweep never had in its candidate set at all.

If that number is near zero, embeddings are not fixing the recall gap diagnosed in
ROADMAP §7.1 and the honest report is that they didn't, at whatever depth was run.

    python discovery_suite/open_problems/o1c_fuse.py \
        --lexical runs/open_sweep_100k_raw.csv \
        --dense   runs/open_dense_qwen_ctx_raw.csv \
        --out     runs/open_fused.csv --method rrf

Output keeps the sweep schema, so the fused shortlist goes straight into
``triage_open.py`` (then the author gate, ``batch_o4.py``, and the S2 citation
gate) with no changes anywhere downstream.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from embed.fuse import PAIR_KEYS, _load, fuse, overlap_report  # noqa: E402


def contribution_report(frames, labels, fused: pd.DataFrame, *,
                        head: int = 200) -> str:
    """Who put each of the top pairs on the shortlist?"""
    sets = {lab: set(map(tuple, f[PAIR_KEYS].itertuples(index=False, name=None)))
            for lab, f in zip(labels, frames)}
    top = list(map(tuple, fused[PAIR_KEYS].head(head).itertuples(index=False, name=None)))
    lines = [f"top-{len(top)} fused shortlist composition:"]
    for lab, s in sets.items():
        n = sum(1 for p in top if p in s)
        lines.append(f"  {n:>5}/{len(top)} found by {lab}")
    both = sum(1 for p in top if all(p in s for s in sets.values()))
    lines.append(f"  {both:>5}/{len(top)} found by ALL arms")
    for lab, s in sets.items():
        others = set().union(*(v for k, v in sets.items() if k != lab))
        only = sum(1 for p in top if p in s and p not in others)
        lines.append(f"  {only:>5}/{len(top)} found ONLY by {lab}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lexical", default=None, help="sweep_open.py CSV")
    ap.add_argument("--dense", nargs="*", default=[], help="o1b_dense_sweep.py CSV(s)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--method", choices=("rrf", "znorm", "linear", "max"), default="rrf")
    ap.add_argument("--weights", nargs="*", type=float, default=None,
                    help="lexical first, then each dense CSV in order")
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--top-per-problem", type=int, default=20)
    ap.add_argument("--head", type=int, default=200,
                    help="shortlist depth used for the composition report")
    ap.add_argument("--emit-unique", default=None, metavar="LABEL",
                    help="also write the pairs found ONLY by this arm (e.g. "
                         "'dense'), ranked by that arm's own score, to "
                         "<out>.only-LABEL.csv. RRF ranks agreement highest, so "
                         "an arm's unique candidates never reach the top of the "
                         "fused list — but they are exactly what has to be judged "
                         "to know whether the new arm found anything real.")
    ap.add_argument("--cap-per-problem", type=int, default=0,
                    help="before fusing, keep only this many candidates per "
                         "problem from EACH arm. Use it to compare arms that were "
                         "swept at different depths (dense top-50 vs lexical "
                         "top-20 is not a like-for-like overlap).")
    args = ap.parse_args()

    paths, labels = [], []
    if args.lexical:
        paths.append(Path(args.lexical))
        labels.append("lexical")
    for i, d in enumerate(args.dense):
        paths.append(Path(d))
        labels.append(f"dense{i}" if len(args.dense) > 1 else "dense")
    if len(paths) < 2:
        sys.exit("[o1c] need at least two inputs (--lexical and/or several --dense)")

    frames = [_load(p, lab) for p, lab in zip(paths, labels)]
    if args.cap_per_problem:
        frames = [f.sort_values("score", ascending=False)
                   .groupby("problem_key", sort=False)
                   .head(args.cap_per_problem)
                   .reset_index(drop=True) for f in frames]
        print(f"[o1c] capped each arm to {args.cap_per_problem}/problem for a "
              f"like-for-like comparison", file=sys.stderr)
    print(overlap_report(frames, labels), file=sys.stderr)

    if args.emit_unique:
        if args.emit_unique not in labels:
            sys.exit(f"[o1c] --emit-unique {args.emit_unique!r} is not one of "
                     f"{labels}")
        mine = frames[labels.index(args.emit_unique)]
        others = set()
        for lab, f in zip(labels, frames):
            if lab != args.emit_unique:
                others |= set(map(tuple, f[PAIR_KEYS].itertuples(index=False, name=None)))
        mask = [tuple(r) not in others
                for r in mine[PAIR_KEYS].itertuples(index=False, name=None)]
        uniq = mine[mask].sort_values("score", ascending=False)
        up = Path(args.out).with_suffix(f".only-{args.emit_unique}.csv")
        uniq.to_csv(up, index=False)
        print(f"[o1c] {len(uniq):,} pairs found ONLY by '{args.emit_unique}' "
              f"across {uniq.problem_key.nunique():,} problems -> {up}",
              file=sys.stderr)

    fused = fuse(frames, method=args.method, weights=args.weights,
                 rrf_k=args.rrf_k, top_per_problem=args.top_per_problem)
    print("\n" + contribution_report(frames, labels, fused, head=args.head),
          file=sys.stderr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fused.to_csv(out, index=False)
    print(f"\n[o1c] {len(fused):,} fused pairs across "
          f"{fused.problem_key.nunique():,} problems -> {out}", file=sys.stderr)
    print("[next] python3 discovery_suite/open_problems/triage_open.py "
          f"--in {out} --out runs/triage_fused.csv --min-score 0.5 --per-problem 3",
          file=sys.stderr)


if __name__ == "__main__":
    main()
