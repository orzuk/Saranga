"""Generic typed-node index builder used by every discovery method.

Method E uses two calls:
    problems = build_node_index(types=["open_problem","conjecture"], year_max=2017)
    theorems = build_node_index(types=["theorem","lemma","proposition","corollary"],
                                year_min=2018)

Method H reuses the second call. Method B uses different category filters.
Method A uses a broader type set with no year bound.

Output: JSONL, one row per node:
    {paper_id, year, category, node_id, node_type, name, subclass,
     raw_latex (truncated), clean_text (truncated),
     sig_foundation_ids, sig_operators, sig_statement_tokens, conclusion_type}

JSONL was chosen over Parquet for the POC: pandas/pyarrow are not always
installed on the cluster venv, and the per-row append model lets us stream
through 100k papers without holding everything in memory. A converter can
be added later when we need columnar reads.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent
for _p in (_SRC, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from node_types import normalize_node_type  # noqa: E402

from corpus_io import iter_papers  # noqa: E402
from signature import signature_of  # noqa: E402


_RAW_TRUNC = 4000
_TEXT_TRUNC = 4000


def build_node_index(
    types: Sequence[str],
    out: Path,
    *,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    categories_in: Optional[Sequence[str]] = None,
    compute_signature: bool = True,
    progress_every: int = 1000,
) -> int:
    """Stream-write a node index JSONL. Returns the number of rows written.

    Args:
        types: list of node-type strings (`open_problem`, `theorem`, ...).
               Passed through `normalize_node_type` before matching, so
               legacy aliases are accepted.
        out: output path (a JSONL file).
        year_min, year_max: inclusive year bounds for the parent paper.
        categories_in: top-level subdirs under TIER3_DIR (e.g. ["math_CO"]).
        compute_signature: when False, emits raw rows without the per-node
                           Signature fields. Useful for cheap counts.
    """
    type_set = {normalize_node_type(t) for t in types}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    n_rows = 0
    n_papers = 0
    with out.open("w", encoding="utf-8") as f:
        for paper in iter_papers(categories=categories_in,
                                 year_min=year_min, year_max=year_max):
            n_papers += 1
            for node in paper.nodes:
                if not isinstance(node, dict):
                    continue
                ntype = normalize_node_type(node.get("type"))
                if ntype not in type_set:
                    continue
                row = {
                    "paper_id": paper.paper_id,
                    "year": paper.year,
                    "category": paper.category,
                    "node_id": node.get("id"),
                    "node_type": ntype,
                    "name": node.get("name"),
                    "subclass": node.get("subclass"),
                    "raw_latex": (node.get("raw_latex") or "")[:_RAW_TRUNC],
                    "clean_text": (node.get("clean_text") or "")[:_TEXT_TRUNC],
                }
                if compute_signature:
                    sig = signature_of(node, paper.edges)
                    row["sig_foundation_ids"] = sorted(sig.foundation_ids)
                    row["sig_operators"] = sorted(sig.operators)
                    row["sig_statement_tokens"] = sorted(sig.statement_tokens)
                    row["conclusion_type"] = sig.conclusion_type
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_rows += 1
            if n_papers % progress_every == 0:
                print(f"[build_node_index] papers={n_papers:>6} "
                      f"rows={n_rows:>7}", file=sys.stderr)
    print(f"[build_node_index] DONE papers={n_papers} rows={n_rows} -> {out}",
          file=sys.stderr)
    return n_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--types", required=True,
                    help="Comma-sep node types (e.g. open_problem,conjecture)")
    ap.add_argument("--year-min", type=int, default=None)
    ap.add_argument("--year-max", type=int, default=None)
    ap.add_argument("--categories", default=None,
                    help="Comma-sep categories (e.g. math_CO,math_PR)")
    ap.add_argument("--no-signature", action="store_true",
                    help="Skip per-node Signature computation")
    ap.add_argument("--out", required=True, help="Output JSONL path")
    args = ap.parse_args()
    build_node_index(
        types=[t.strip() for t in args.types.split(",") if t.strip()],
        out=Path(args.out),
        year_min=args.year_min,
        year_max=args.year_max,
        categories_in=[c.strip() for c in args.categories.split(",")]
                      if args.categories else None,
        compute_signature=not args.no_signature,
    )


if __name__ == "__main__":
    main()
