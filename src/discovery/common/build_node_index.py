"""Generic typed-node index builder used by every discovery method.

Method E uses two calls:
    problems = build_node_index(types=["open_problem","conjecture"], year_max=2017)
    theorems = build_node_index(types=["theorem","lemma","proposition","corollary"],
                                year_min=2018)

Method H reuses the second call. Method B uses different category filters.
Method A uses a broader type set with no year bound.

Output formats (one of two):

  Legacy single-file (default — current behavior):
    out=theorems.jsonl
    Each row carries raw_latex + clean_text inline. ~1.5KB/row at
    v2 scale (1.24M rows = 1.8GB total). Retrieve loads everything
    into RAM — needs ~2.1GB, requires 64GB+ SLURM allocation.

  Split format (opt-in via --text-store / text_store= arg):
    out=theorems_sig.jsonl       slim: sig + metadata only (~430MB total)
    text_store=theorems_text.sqlite  random-access text store (~370MB)
    Retrieve loads only sig into RAM (~750MB total); raw_latex /
    clean_text are lazy-fetched only for the top-K candidates per
    problem. Runs on the gateway, no SLURM needed.

retrieve_pairs.py auto-detects: if `<run_dir>/theorems_sig.jsonl`
exists alongside `<run_dir>/theorems_text.sqlite`, the split format
is used; else it falls back to legacy `theorems.jsonl`.

JSONL was chosen over Parquet for the POC: pandas/pyarrow are not always
installed on the cluster venv, and the per-row append model lets us stream
through 100k papers without holding everything in memory.
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


def _has_substantive_text(node: dict, min_alpha: int) -> bool:
    """Reject nodes whose extracted text is mostly LaTeX artifact / brace junk.

    A cluster dry-run (2026-05-18) surfaced ~9 candidates at combined=0.80
    where both problem and candidate `clean_text` were literally "{ :} } {"
    — extraction-failure residue, ~0 alphabetic characters. They matched each
    other trivially and crowded out real signal at the top of triage. We
    filter such nodes here so they never enter any discovery method's index.

    Threshold is intentionally generous (15 letters); a real theorem
    statement has hundreds. This only catches the empty-extraction failure
    mode, not legitimately terse statements.
    """
    if min_alpha <= 0:
        return True
    text = node.get("clean_text") or ""
    return sum(1 for c in text if c.isalpha()) >= min_alpha


def build_node_index(
    types: Sequence[str],
    out: Path,
    *,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    categories_in: Optional[Sequence[str]] = None,
    compute_signature: bool = True,
    min_clean_text_chars: int = 15,
    progress_every: int = 1000,
    text_store: Optional[Path] = None,
) -> int:
    """Stream-write a node index. Returns the number of rows written.

    Args:
        types: list of node-type strings (`open_problem`, `theorem`, ...).
               Passed through `normalize_node_type` before matching, so
               legacy aliases are accepted.
        out: output path. In LEGACY mode (text_store=None), a single
             JSONL file with text fields inline. In SPLIT mode
             (text_store set), the slim sig-only JSONL.
        year_min, year_max: inclusive year bounds for the parent paper.
        categories_in: top-level subdirs under TIER3_DIR (e.g. ["math_CO"]).
        compute_signature: when False, emits raw rows without the per-node
                           Signature fields. Useful for cheap counts.
        min_clean_text_chars: minimum alphabetic-character count required in
                              the node's `clean_text` for it to be indexed.
                              Default 15 filters extraction-failure nodes
                              whose text collapsed to brace artifacts.
                              Set to 0 to disable.
        text_store: optional sqlite path. When set, the row's raw_latex /
                    clean_text fields are written to this sqlite instead
                    of inline in the JSONL row (split format). Used by
                    Method E's retrieve_pairs.py auto-detect — the
                    canonical layout is:
                        <run>/theorems_sig.jsonl   (this function's `out`)
                        <run>/theorems_text.sqlite (text_store)
                    Use sibling helper from method_e.text_store.TextStore.
    """
    type_set = {normalize_node_type(t) for t in types}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Optional split-format text store
    store = None
    if text_store is not None:
        text_store = Path(text_store)
        text_store.parent.mkdir(parents=True, exist_ok=True)
        # Wipe any existing sqlite — partial state from a prior run would
        # leak into the new index.
        if text_store.exists():
            text_store.unlink()
        # Import lazily so the legacy code path doesn't require TextStore.
        sys.path.insert(0, str(_SRC / "discovery" / "method_e"))
        from text_store import TextStore  # noqa: E402
        store = TextStore(text_store)

    n_rows = 0
    n_skipped_text = 0
    n_papers = 0
    text_batch: list[tuple] = []
    _BATCH = 2000  # sqlite insert batch size

    try:
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
                    if not _has_substantive_text(node, min_clean_text_chars):
                        n_skipped_text += 1
                        continue
                    raw = (node.get("raw_latex") or "")[:_RAW_TRUNC]
                    clean = (node.get("clean_text") or "")[:_TEXT_TRUNC]
                    row = {
                        "paper_id": paper.paper_id,
                        "year": paper.year,
                        "category": paper.category,
                        "node_id": node.get("id"),
                        "node_type": ntype,
                        "name": node.get("name"),
                        "subclass": node.get("subclass"),
                    }
                    if store is None:
                        # Legacy: text inline in JSONL row
                        row["raw_latex"] = raw
                        row["clean_text"] = clean
                    else:
                        # Split: text goes to sqlite, JSONL row stays slim
                        text_batch.append((paper.paper_id,
                                           node.get("id") or "",
                                           raw, clean))
                        if len(text_batch) >= _BATCH:
                            store.put_many(text_batch)
                            text_batch = []
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
        # Flush remaining text rows
        if store is not None and text_batch:
            store.put_many(text_batch)
    finally:
        if store is not None:
            store.close()

    mode = "split" if text_store is not None else "legacy"
    extra = f"  text_store={text_store}" if text_store is not None else ""
    print(f"[build_node_index] DONE ({mode}) papers={n_papers} rows={n_rows} "
          f"(filtered_short_text={n_skipped_text}) -> {out}{extra}",
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
    ap.add_argument("--min-text-chars", type=int, default=15,
                    help="Min alphabetic char count in clean_text to index a "
                         "node (default 15; 0 disables). Filters extraction-"
                         "failure nodes like '{ :} } {'.")
    ap.add_argument("--out", required=True, help="Output JSONL path "
                    "(sig-only when --text-store is given; full row inline otherwise)")
    ap.add_argument("--text-store", default=None,
                    help="Optional sqlite path; enables split-format output. "
                         "Text fields go here (random-access) instead of "
                         "inline in the JSONL row. Drops retrieve-time RAM "
                         "from ~2GB to ~750MB at v2 scale. Recommended "
                         "naming: theorems_text.sqlite alongside "
                         "theorems_sig.jsonl in the same run dir.")
    args = ap.parse_args()
    build_node_index(
        types=[t.strip() for t in args.types.split(",") if t.strip()],
        out=Path(args.out),
        year_min=args.year_min,
        year_max=args.year_max,
        categories_in=[c.strip() for c in args.categories.split(",")]
                      if args.categories else None,
        compute_signature=not args.no_signature,
        min_clean_text_chars=args.min_text_chars,
        text_store=Path(args.text_store) if args.text_store else None,
    )


if __name__ == "__main__":
    main()
