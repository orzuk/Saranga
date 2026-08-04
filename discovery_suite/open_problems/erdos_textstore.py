"""T-OPEN — inject the Erdős problem set into the embedding text store.

Why
---
The lexical Erdős probe (`erdos_coverage.py`) matches by shared words, and its
own failure mode is written on the tin: Erdős statements are natural-language
prose, corpus nodes are LaTeX-derived, so the same problem phrased differently
is missed. On the 100k run this showed up exactly as predicted — the score
distribution was one smooth hump with no gap, a handful of long generic nodes
became the "best match" for dozens of unrelated problems, and only the top of
the ranking held a verifiable hit (Erdős–Gallai, #184).

Meaning-based retrieval is the intended fix, and the engine already exists
(`discovery_suite/embed/`, driven by `o1b_dense_sweep.py` / `o5_rerank.py`).
It was built after the Erdős probe and the two were never connected. This
script is the connector.

How
---
The engine keys everything off a per-row ``role``: the search side selects
queries with ``--query-roles`` and documents with ``--doc-roles``. So the Erdős
problems only need to become text-store rows carrying a role of their own, and
every downstream stage — encode, index, fuse, rerank — works unchanged.

Rows are written as one extra shard appended to an existing store, with:

    role       "erdos"   (distinct, so the corpus's own question nodes are not
                          pulled in as queries; encode.QUERY_LIKE_ROLES wraps it
                          with the query-side instruction of asymmetric models)
    paper_id   "erdos"   (shared, so the engine's same-paper mask suppresses
                          Erdős-vs-Erdős pairs for free)
    year/yymm  0         (no temporal gate: an Erdős problem predates every
                          arXiv paper, and coverage asks WHERE it is stated,
                          not what came first — pass --no-temporal downstream)
    ntype      "conjecture"
    text_raw   the statement, with erdosproblems.com's status banner stripped
               by the same `_strip_erdos_boilerplate` the lexical arm uses

There is no context and no canonical form for an external statement, so
``ctx_*`` are empty and ``text_canon`` mirrors ``text_raw``. That restricts the
Erdős side to the ``node`` view — ``ctx-concat`` / ``ctx-late`` describe a node's
neighbours in a paper, which an Erdős problem does not have.

Usage
-----
    # after the corpus store exists (embed/textstore.py build ...)
    python3 discovery_suite/open_problems/erdos_textstore.py \
        --store /path/to/textstore \
        --erdos-csv discovery_suite/open_problems/erdos_problems.csv

Then encode and search — note the doc side is the corpus's QUESTION nodes,
because coverage asks "is this problem stated in our corpus", not "is it
resolved":

    python3 -m embed.encode --store <store> --out <vectors> --model minilm
    python3 discovery_suite/open_problems/o1b_dense_sweep.py all \
        --vectors <vectors> --view node --canon raw --no-temporal \
        --query-roles erdos --doc-roles query \
        --top-k 20 --out runs/erdos_dense_100k.csv
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from embed import textstore as TS  # noqa: E402
from embed.views import ROW_COLUMNS  # noqa: E402
from erdos_coverage import load_erdos  # noqa: E402

ROLE = "erdos"
PAPER_ID = "erdos"


def erdos_rows(csv_path: Path) -> list[dict]:
    """Erdős problems as text-store rows.

    Reuses `load_erdos` so the row set is exactly the one the lexical arm
    matched (same boilerplate stripping, same minimum-length filter) — the two
    arms must be comparable on the same 1,063 problems, otherwise a coverage
    difference could just be a different denominator.
    """
    rows: list[dict] = []
    for e in load_erdos(csv_path):
        text = e["statement"]
        rows.append({
            "key": f"erdos::{e['number']}",
            "paper_id": PAPER_ID,
            "year": 0,
            "yymm": 0,
            "category": "erdos",
            "ntype": "conjecture",
            "role": ROLE,
            "text_raw": text,
            # No canonical form exists for an external statement; mirroring
            # text_raw keeps --canon canon runnable instead of silently empty.
            "text_canon": text,
            "ctx_raw": "",
            "ctx_canon": "",
            "concepts": "",
            "ctx_keys": "[]",
            "ctx_weights": "[]",
            "n_words": len(text.split()),
            "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True, type=Path,
                    help="existing text-store dir (embed/textstore.py --out)")
    ap.add_argument("--erdos-csv", type=Path,
                    default=_HERE / "erdos_problems.csv")
    ap.add_argument("--shard-id", type=int, default=None,
                    help="shard to write (default: one past the highest existing)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written and exit")
    args = ap.parse_args()

    rows = erdos_rows(args.erdos_csv)
    if not rows:
        sys.exit("[erdos-ts] no usable Erdős statements — check --erdos-csv")

    missing = [c for c in ROW_COLUMNS if c not in rows[0]]
    if missing:  # guards against a schema change in views.ROW_COLUMNS
        sys.exit(f"[erdos-ts] row schema drift, missing: {missing}")

    existing = TS.list_shards(args.store) if args.store.exists() else []
    shard_id = args.shard_id if args.shard_id is not None else (
        max(existing) + 1 if existing else 0)
    if shard_id in existing:
        print(f"[erdos-ts] WARNING overwriting existing shard {shard_id}",
              flush=True)

    words = sorted(r["n_words"] for r in rows)
    print(f"[erdos-ts] {len(rows)} Erdős problems -> shard {shard_id} of "
          f"{args.store}  (existing shards: {len(existing)})", flush=True)
    print(f"[erdos-ts] words per statement: min {words[0]}  "
          f"median {words[len(words)//2]}  max {words[-1]}", flush=True)
    print(f"[erdos-ts] role={ROLE!r} paper_id={PAPER_ID!r} year=0 "
          f"(pass --no-temporal downstream)", flush=True)

    if args.dry_run:
        print("[erdos-ts] dry run — nothing written", flush=True)
        return

    path = TS.write_shard(args.store, shard_id, rows)
    print(f"[erdos-ts] wrote {path}", flush=True)
    print(f"[erdos-ts] next: re-run embed.encode over the store, then "
          f"o1b_dense_sweep.py with --query-roles {ROLE} --doc-roles query",
          flush=True)


if __name__ == "__main__":
    main()
