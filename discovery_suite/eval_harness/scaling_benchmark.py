"""Scaling benchmark: wall-clock + candidate counts vs corpus size.

Runs the light detectors (P1 shingling, O1 retrieval) over increasing numbers of
papers and records timing/throughput, so we can (a) confirm near-linear scaling
and (b) extrapolate to the full 100k. Cluster-ready: point --root at the v4 100k
tier3 tree and pass larger --sizes.

    python discovery_suite/eval_harness/scaling_benchmark.py \
        --sizes 500,1000,2000,4000,8000,16000 --out runs/scaling_local.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _SUITE / "plagiarism", _SUITE / "open_problems"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import load_papers  # noqa: E402
from p1_shingle import detect_reuse  # noqa: E402
from o1_retrieve import retrieve  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--sizes", default="500,1000,2000,4000,8000,16000")
    ap.add_argument("--out", default=str(_HERE / "runs" / "scaling_local.json"))
    args = ap.parse_args()
    # Accept comma, colon, or whitespace separators. Colon is useful with
    # `sbatch --export=SIZES=a:b:c` since --export splits its list on commas.
    import re as _re
    sizes = [int(x) for x in _re.split(r"[,:\s]+", args.sizes.strip()) if x]

    t0 = time.time()
    papers_all = load_papers(root=args.root, limit=max(sizes))
    load_t = time.time() - t0
    print(f"loaded {len(papers_all)} papers in {load_t:.1f}s")

    rows = []
    for n in sizes:
        if n > len(papers_all):
            break
        sub = papers_all[:n]
        n_nodes = sum(len(p.nodes) for p in sub)

        t = time.time()
        p1 = detect_reuse(sub, min_jaccard=0.3)
        t_p1 = time.time() - t

        t = time.time()
        o1 = retrieve(sub, top_k=20)
        t_o1 = time.time() - t

        row = {"papers": n, "nodes": n_nodes,
               "t_p1_s": round(t_p1, 3), "p1_pairs": len(p1),
               "t_o1_s": round(t_o1, 3), "o1_pairs": len(o1),
               "nodes_per_s_p1": round(n_nodes / t_p1) if t_p1 else 0}
        rows.append(row)
        print(f"  N={n:>6}  nodes={n_nodes:>8}  "
              f"P1={t_p1:6.2f}s ({row['nodes_per_s_p1']:>6}/s, {len(p1)} pairs)  "
              f"O1={t_o1:6.2f}s ({len(o1)} pairs)", flush=True)
        # Write incrementally so partial results survive a timeout.
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"load_time_s": load_t, "rows": rows}, indent=2))

    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
