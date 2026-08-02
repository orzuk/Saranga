"""Stage 4 — combine rankings from different arms.

Three distinct fusions matter here, and they are the same operation:

  raw + canonical   Or's suggestion: rather than choosing between notation-
                    canonicalized and as-written embeddings, score both and
                    combine. Score-level, never vector concatenation — two
                    500-dim halves with different scales produce a similarity
                    dominated by whichever half has the larger norm.
  dense + lexical   the hybrid arm. Consistently the largest single win in
                    retrieval: the lexical sweep nails shared notation and exact
                    symbols, the embedder nails paraphrase. They fail differently.
  model + model     ensembling two backbones.

RRF is the default because it needs no calibration. A cosine of 0.83 from
bge-m3 and 0.61 from qwen3 may be the same quality of match; their RANKS are
directly comparable, their scores are not. Linear blending is offered for when
the arms genuinely share a scale (raw vs canonical of the SAME model), with
per-query z-normalization to make that assumption survivable.

Everything operates on the sweep-schema CSVs, so fusion is cheap, offline, and
re-sweepable without touching a GPU.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

PAIR_KEYS = ["problem_key", "theorem_key"]
#: Columns carried through from whichever input row wins, so fused output stays
#: a drop-in for triage_open.py.
CARRY = ["problem_cat", "problem_type", "theorem_cat", "cross_category",
         "problem_snippet", "theorem_snippet"]


def _load(path: Path, label: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in PAIR_KEYS + ["score"] if c not in df.columns]
    if missing:
        raise SystemExit(f"{path}: missing required column(s) {missing}")
    df = df.copy()
    df["arm"] = label
    # Rank within each problem, best first. Recomputed rather than trusted from
    # the file: a CSV may have been re-sorted, filtered or concatenated.
    df["rank"] = (df.groupby("problem_key")["score"]
                    .rank(method="first", ascending=False).astype(int))
    return df


def _znorm(df: pd.DataFrame) -> pd.Series:
    """Per-problem z-score. Per-problem, not global: some problems are simply in
    denser neighbourhoods than others, and a global z would let a crowded topic
    dominate the shortlist regardless of match quality."""
    g = df.groupby("problem_key")["score"]
    mu, sd = g.transform("mean"), g.transform("std")
    return (df["score"] - mu) / sd.replace(0, 1).fillna(1)


def fuse(
    frames: Sequence[pd.DataFrame],
    *,
    method: str = "rrf",
    weights: Optional[Sequence[float]] = None,
    rrf_k: int = 60,
    top_per_problem: Optional[int] = None,
    rescale: bool = True,
) -> pd.DataFrame:
    """Combine per-arm rankings into one ranked table.

    A pair missing from an arm is not treated as scoring zero — under RRF it
    simply contributes nothing from that arm, and under the score methods it is
    filled with that arm's per-problem minimum. Treating "not in this arm's
    top-k" as "similarity 0" would punish exactly the pairs the other arm was
    added to find.
    """
    if not frames:
        raise ValueError("nothing to fuse")
    w = list(weights) if weights else [1.0] * len(frames)
    if len(w) != len(frames):
        raise ValueError(f"{len(w)} weights for {len(frames)} inputs")

    prepared = []
    for df, wi in zip(frames, w):
        d = df.copy()
        if method == "rrf":
            d["contrib"] = wi / (rrf_k + d["rank"])
        elif method == "znorm":
            d["contrib"] = wi * _znorm(d)
        elif method in ("linear", "max"):
            d["contrib"] = wi * d["score"]
        else:
            raise ValueError(f"unknown fusion method {method!r}")
        prepared.append(d)

    allrows = pd.concat(prepared, ignore_index=True)
    agg = "max" if method == "max" else "sum"
    fused = (allrows.groupby(PAIR_KEYS, as_index=False)
                    .agg(score=("contrib", agg),
                         n_arms=("arm", "nunique"),
                         best_rank=("rank", "min")))

    # Carry metadata from the best-ranked source row for each pair.
    meta_cols = [c for c in CARRY if c in allrows.columns]
    best = (allrows.sort_values("rank", kind="mergesort")
                   .drop_duplicates(PAIR_KEYS)[PAIR_KEYS + meta_cols])
    fused = fused.merge(best, on=PAIR_KEYS, how="left")

    if rescale:
        # Map onto [0, 1]. RRF scores live around 1/(60+rank) ~ 0.016, so an
        # unrescaled fused CSV silently fails triage_open.py's `--min-score 0.5`
        # default and yields an empty shortlist. Min-max is monotone, so the
        # ranking is untouched — only the axis the human threshold reads.
        lo, hi = float(fused["score"].min()), float(fused["score"].max())
        fused["score_fused"] = fused["score"]
        fused["score"] = ((fused["score"] - lo) / (hi - lo)) if hi > lo else 1.0

    fused = fused.sort_values(["score"] + PAIR_KEYS,
                              ascending=[False, True, True], kind="mergesort")
    if top_per_problem:
        fused = fused.groupby("problem_key", group_keys=False).head(top_per_problem)
        fused = fused.sort_values(["score"] + PAIR_KEYS,
                                  ascending=[False, True, True], kind="mergesort")
    fused["rank"] = (fused.groupby("problem_key")["score"]
                          .rank(method="first", ascending=False).astype(int))
    fused["method"] = f"fuse-{method}"
    return fused.reset_index(drop=True)


def fuse_files(paths: Sequence[Path], labels: Optional[Sequence[str]] = None,
               **kw) -> pd.DataFrame:
    labels = labels or [Path(p).stem for p in paths]
    return fuse([_load(Path(p), lab) for p, lab in zip(paths, labels)], **kw)


def overlap_report(frames: Sequence[pd.DataFrame], labels: Sequence[str]) -> str:
    """How much do two arms actually disagree?

    The number that says whether fusion can help at all: if the dense and
    lexical shortlists are 95% the same pairs, the semantic arm is not buying
    new recall and the honest thing is to report that.
    """
    sets = [set(map(tuple, f[PAIR_KEYS].itertuples(index=False, name=None)))
            for f in frames]
    lines = [f"pairs per arm: " + ", ".join(f"{l}={len(s):,}" for l, s in zip(labels, sets))]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            inter = len(sets[i] & sets[j])
            union = len(sets[i] | sets[j])
            lines.append(
                f"  {labels[i]} ∩ {labels[j]} = {inter:,}  "
                f"(jaccard {inter/max(union,1):.3f}; "
                f"{len(sets[j]-sets[i]):,} pairs only {labels[j]} found)")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--in", dest="inputs", nargs="+", required=True,
                    help="two or more sweep-schema CSVs")
    ap.add_argument("--labels", nargs="*", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--method", choices=("rrf", "znorm", "linear", "max"), default="rrf")
    ap.add_argument("--weights", nargs="*", type=float, default=None,
                    help="per-input weight; for two arms this is the λ sweep")
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--top-per-problem", type=int, default=None)
    ap.add_argument("--no-rescale", action="store_true",
                    help="keep raw fused scores instead of min-max to [0,1] "
                         "(ranking is identical either way)")
    ap.add_argument("--report", action="store_true", help="print arm overlap stats")
    args = ap.parse_args()

    labels = args.labels or [Path(p).stem for p in args.inputs]
    frames = [_load(Path(p), lab) for p, lab in zip(args.inputs, labels)]
    if args.report:
        print(overlap_report(frames, labels), file=sys.stderr)

    fused = fuse(frames, method=args.method, weights=args.weights,
                 rrf_k=args.rrf_k, top_per_problem=args.top_per_problem,
                 rescale=not args.no_rescale)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fused.to_csv(out, index=False)
    print(f"[fuse] {args.method} over {len(frames)} arms -> {len(fused):,} pairs "
          f"-> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
