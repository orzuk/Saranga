"""Build a compact id -> normalized-authors index from the arXiv metadata snapshot
(the official CC0 Cornell/Kaggle dump), for the same-author / self-reuse gate.

Restricting to the ids referenced by a sweep/triage CSV keeps the index tiny (a
few MB for the 100k pairs) and instant to load in triage_plag.py. Authors are
normalized to `surname|first-initial` tokens so matching is robust to formatting
(the brittle full-string matching was a documented failure of the old pipeline).

    python discovery_suite/plagiarism/build_author_index.py \
        --snapshot /sci/.../arxiv_data/arxiv-metadata-oai-snapshot.json \
        --ids-csv  discovery_suite/plagiarism/runs/plag_sweep_100k.csv \
        --out      discovery_suite/plagiarism/runs/author_index.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _norm_authors(rec: dict) -> list[str]:
    """authors_parsed = [[surname, firstnames, suffix], ...] -> {surname|initial}."""
    toks = set()
    for a in (rec.get("authors_parsed") or []):
        if not a:
            continue
        surname = (a[0] or "").strip().lower()
        if not surname:
            continue
        first = (a[1] or "").strip().lower()
        toks.add(f"{surname}|{first[:1]}")
    return sorted(toks)


def _wanted_ids(ids_csv: str) -> set[str]:
    # dtype=str: arXiv ids like 1002.1960 would otherwise be read as floats.
    df = pd.read_csv(ids_csv, dtype=str)
    ids: set[str] = set()
    for col in ("source_paper", "target_paper"):
        if col in df.columns:
            ids.update(x for x in df[col].dropna())
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True, help="arxiv-metadata-oai-snapshot.json")
    ap.add_argument("--ids-csv", default=None,
                    help="restrict to ids in this sweep/triage CSV (source_paper + "
                         "target_paper). Omit to index ALL papers.")
    ap.add_argument("--out", required=True, help="output author index JSON")
    args = ap.parse_args()

    wanted = _wanted_ids(args.ids_csv) if args.ids_csv else None
    print(f"[authors] wanted ids: {len(wanted) if wanted is not None else 'ALL'}", flush=True)

    index: dict[str, list[str]] = {}
    n = 0
    with open(args.snapshot, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n += 1
            if n % 500000 == 0:
                print(f"[authors] scanned {n:,} records, matched {len(index):,}", flush=True)
            rec = json.loads(line)
            pid = rec.get("id")
            if pid is None:
                continue
            if wanted is not None and pid not in wanted:
                continue
            index[pid] = _norm_authors(rec)
            if wanted is not None and len(index) == len(wanted):
                break

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(index, fh)
    print(f"[authors] wrote {len(index):,} ids -> {args.out}", flush=True)
    if wanted is not None:
        miss = len(wanted) - len(index)
        print(f"[authors] coverage: {len(index):,}/{len(wanted):,} wanted ids found "
              f"({miss:,} missing — post-snapshot or old-style-id mismatch)", flush=True)


if __name__ == "__main__":
    main()
