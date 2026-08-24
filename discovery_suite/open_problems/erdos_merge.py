"""T-OPEN — merge sharded Erdős-coverage runs into one result.

Why sharding works here
-----------------------
`erdos_coverage.py` reports, per Erdős problem, the **max** Jaccard over all
corpus nodes. Max is associative, so the corpus can be partitioned arbitrarily:
each shard computes its own best match per problem, and the merge is just an
argmax across shards. Nothing is approximated — the sharded result is bit-for-bit
what a single whole-corpus run would produce.

Shard on the CORPUS, never on the problem list. The bottleneck is walking and
parsing ~100k JSONs over NFS; sharding by category dir splits that walk N ways,
whereas sharding by Erdős problem would make every worker re-read the whole
corpus (strictly worse).

Usage
-----
    # one array task per category dir (see erdos_array.sh), each with --threshold 0
    python3 erdos_merge.py \
        --shards 'discovery_suite/open_problems/runs/shards/erdos_shard_*.csv' \
        --threshold 0.15 \
        --out discovery_suite/open_problems/runs/erdos_coverage_100k.csv

Thresholding, the T-OPEN resolving-theorem cross-reference, the summary and the
score histogram all happen HERE, not in the shards — so you can re-threshold the
whole 100k run in seconds without recomputing anything.
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from erdos_coverage import (  # noqa: E402
    OPEN_STATUSES,
    RESOLVED_STATUSES,
    load_run_index,
    print_histogram,
)

COLS = ["number", "status", "resolved", "score", "covered", "match_key",
        "match_type", "resolving_theorem", "resolution_verdict",
        "resolution_relationship", "erdos_stmt", "match_snip"]


def load_shards(patterns: list[str]) -> tuple[dict[str, dict], int]:
    """Argmax across shards, keyed by Erdős problem number.

    A shard row with score 0 means "this shard's corpus slice had nothing" —
    it still carries the problem's status/statement, so problems absent from
    every shard survive the merge with score 0 and are counted in the
    denominator (they are genuine misses, not missing data)."""
    best: dict[str, dict] = {}
    files: list[str] = []
    for pat in patterns:
        files.extend(sorted(glob.glob(pat)))
    if not files:
        sys.exit(f"[merge] no shard CSVs matched: {patterns}")

    for fp in files:
        with open(fp, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            print(f"[merge] WARNING empty shard: {fp}", flush=True)
            continue
        for r in rows:
            num = r["number"]
            try:
                r["score"] = float(r["score"] or 0)
            except ValueError:
                r["score"] = 0.0
            cur = best.get(num)
            if cur is None or r["score"] > cur["score"]:
                best[num] = r
        print(f"[merge] {Path(fp).name}: {len(rows)} rows", flush=True)
    return best, len(files)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shards", nargs="+", required=True,
                    help="glob(s) for the per-shard coverage CSVs")
    ap.add_argument("--threshold", type=float, default=0.15,
                    help="min Jaccard to count as covered; applied HERE, so "
                         "re-thresholding needs no recompute")
    ap.add_argument("--out", type=Path,
                    default=_HERE / "runs" / "erdos_coverage_merged.csv")
    ap.add_argument("--runs-dir", type=Path, default=_HERE / "runs",
                    help="T-OPEN outputs to cross-reference for resolutions")
    ap.add_argument("--show", type=int, default=40)
    args = ap.parse_args()

    best, n_shards = load_shards(args.shards)
    results = list(best.values())
    if not results:
        sys.exit("[merge] shards contained no rows")

    # T-OPEN cross-reference (shards can't do this reliably — a problem's best
    # match may live in another shard, so it is resolved once, here).
    run_idx: dict = {}
    ri = load_run_index(args.runs_dir)
    if isinstance(ri, tuple):
        run_idx, run_src = ri
        if run_idx:
            print(f"[merge] cross-referencing {len(run_idx)} problem_keys "
                  f"from {run_src}", flush=True)

    n_res = n_open = n_other = 0
    for r in results:
        st = (r.get("status") or "").strip().lower()
        if st in RESOLVED_STATUSES:
            n_res += 1
        elif st in OPEN_STATUSES:
            n_open += 1
        else:
            n_other += 1
        r["resolved"] = st in RESOLVED_STATUSES
        r["covered"] = r["score"] >= args.threshold
        r["resolving_theorem"] = r.get("resolving_theorem") or ""
        r["resolution_verdict"] = r.get("resolution_verdict") or ""
        # shards predating the taxonomy port have no such column; default it here
        # so the merged CSV always carries the full schema.
        r["resolution_relationship"] = r.get("resolution_relationship") or ""
        if r["covered"] and r.get("match_key") in run_idx:
            v = run_idx[r["match_key"]]
            r["resolving_theorem"] = v["theorem_key"]
            r["resolution_verdict"] = v.get("verdict", "") or "(triage only)"
            r["resolution_relationship"] = v.get("relationship", "")

    results.sort(key=lambda r: -r["score"])
    covered = [r for r in results if r["covered"]]
    cov_res = sum(1 for r in covered if r["resolved"])
    with_resolution = [r for r in covered if r["resolving_theorem"]]

    print(f"\n===== ERDŐS COVERAGE SUMMARY (merged from {n_shards} shards) =====",
          flush=True)
    print(f"threshold (Jaccard) : {args.threshold}", flush=True)
    print(f"Erdős problems       : {len(results)}  "
          f"(resolved {n_res} / open {n_open} / other {n_other})", flush=True)
    print(f"COVERED in corpus    : {len(covered)}  "
          f"(resolved {cov_res} / open {len(covered) - cov_res})", flush=True)
    print(f"coverage rate        : {len(covered)/len(results):.1%}", flush=True)
    print(f"covered + resolving  : {len(with_resolution)}", flush=True)

    print_histogram([r["score"] for r in results], args.threshold)

    print(f"\n--- top {args.show} matches ---", flush=True)
    for r in results[:args.show]:
        tag = "COVERED" if r["covered"] else "       "
        res = (f"  ->RESOLVE {r['resolving_theorem']} "
               f"[{r['resolution_relationship'] or r['resolution_verdict']}]"
               if r["resolving_theorem"] else "")
        print(f"{tag} s={r['score']:.3f} #{r['number']:<6} "
              f"[{r['status'] or '?'}] {r.get('match_key') or '-'}{res}",
              flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow({c: r.get(c, "") for c in COLS})
    print(f"\n[merge] wrote {len(results)} rows -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
