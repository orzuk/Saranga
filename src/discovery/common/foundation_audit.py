"""Foundation-linker audit (gate for downstream methods).

Method E's signature.foundation_ids relies on the `grounded_to` edges that
`foundation_linker.py` writes into tier3 JSONs. If those edges are too sparse,
the inverted index loses recall and we should fall back to operator + token
features.

This script has two modes:

  default (no --fresh-link):
    Read EXISTING grounded_to edges from tier3 JSONs. Reports coverage per
    node type. Cheap; reflects what's currently on disk.

  --fresh-link --unified-index <merged.json> (optional --mathlib-dir):
    Additionally load the foundation linker against the given index and
    compute what coverage WOULD be if the linker were re-run on the sample.
    Used to evaluate whether expanding the foundation graph (e.g. with
    add_books_to_foundation.py output) would materially improve coverage,
    without committing to a full corpus re-link.

Decision rule (from open_problem_analysis.md §10):
    grounded_to coverage on theorem-like nodes < 30% on the audit sample
      -> downgrade signature.foundation_ids; rely on operators + tokens.
"""
import argparse
import csv
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent
for _p in (_SRC, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from corpus_io import iter_papers  # noqa: E402


from node_types import PROVABLE as THEOREM_LIKE  # noqa: E402
QUESTION_LIKE = {"open_problem", "conjecture"}

# Common single-word stop terms suppressed regardless of source. These are
# words that, even when they appear as foundation entry names (in encyclopedia-
# style books like Tanton or in ML glossaries), are too document-frequent in
# the tier3 corpus to serve as a useful retrieval signal.
_SINGLE_WORD_STOPLIST = frozenset({
    # Quantities / cardinality
    "number", "numbers", "integer", "integers", "natural", "rational",
    "real", "complex", "positive", "negative", "value", "values",
    # Bounds / extrema
    "maximum", "minimum", "bound", "bounded", "upper", "lower",
    "infimum", "supremum", "least", "greatest",
    # Algebra / objects (generic)
    "function", "functions", "set", "sets", "subset", "element", "elements",
    "vector", "matrix", "matrices", "tensor", "scalar", "field", "group",
    "ring", "module", "space", "operator", "operation", "operations",
    "polynomial", "monomial", "term", "expression", "variable", "constant",
    "parameter", "coefficient", "exponent", "argument",
    # Logic / structure
    "proof", "proofs", "theorem", "theorems", "lemma", "corollary",
    "definition", "example", "examples", "claim", "claims", "remark",
    "axiom", "property", "condition", "assumption", "hypothesis",
    "statement", "result", "fact", "case", "form", "type",
    # CS / ML generic
    "algorithm", "algorithms", "approximation", "complexity", "input",
    "output", "feature", "features", "model", "data", "training",
    "learning", "network", "layer", "loss", "risk", "gradient",
    "generalization", "convolution", "logit", "kernel", "regression",
    "classification", "prediction",
    # Math operations / parts
    "addition", "subtraction", "multiplication", "division", "sum",
    "product", "difference", "ratio", "quotient", "average", "mean",
    "median", "variance", "covariance", "moment", "norm", "metric",
    "distance", "limit", "derivative", "integral", "series", "sequence",
    # Misc structural
    "graph", "tree", "node", "edge", "vertex", "vertices", "path",
    "cycle", "loop", "step", "level", "order", "rank", "size",
    "dimension", "degree", "index", "indices", "row", "column",
    "block", "table", "list", "array", "stack", "queue",
})


def _build_term_df(term_index: dict) -> dict:
    """Document frequency for each term, measured against the foundation
    index itself: count of distinct foundation entries that contain the
    term in their name. Used as an in-memory proxy for the tier3-corpus
    df_frac that the real linker computes at write time."""
    return {term: len(entries) for term, entries in term_index.items()}


def _is_generic_match(matched_term: str, foundation_name: str,
                      term_df: int = 0,
                      df_threshold: int = 10) -> bool:
    """Conservative generic filter for in-memory fresh-link evaluation.

    Returns True if the match should be SUPPRESSED. A match is generic if any:
      - matched term is a single word in the stoplist;
      - foundation entry name (lowercased) is a single word in the stoplist;
      - matched-term df in the foundation index exceeds df_threshold
        (i.e. this term names many foundation entries -> not specific).
    Multi-word terms (e.g. "partial order") are kept regardless of df.
    """
    t = (matched_term or "").strip().lower()
    f = (foundation_name or "").strip().lower()
    if not t:
        return True
    single_word_t = " " not in t and "-" not in t
    single_word_f = " " not in f and "-" not in f
    if single_word_t and t in _SINGLE_WORD_STOPLIST:
        return True
    if single_word_f and f in _SINGLE_WORD_STOPLIST:
        return True
    if single_word_t and term_df > df_threshold:
        return True
    return False


def _fresh_link_text(text: str, term_index: dict,
                     min_term_len: int = 6,
                     term_df: dict | None = None,
                     df_threshold: int = 10) -> list:
    """Return list of (matched_term, entry) hits for a text against term_index.

    `term_df` is the precomputed foundation-side df dict from _build_term_df.
    When provided, we suppress matches whose term has df > df_threshold (a
    proxy for the tier3-corpus df_frac generic flag used by the real linker).
    """
    if not text:
        return []
    t = text.lower()
    out = []
    for term, entries in term_index.items():
        if len(term) < min_term_len:
            continue
        if term in t:
            df = term_df.get(term, 0) if term_df else 0
            for e in entries:
                if _is_generic_match(term, e.get("name", ""),
                                     term_df=df, df_threshold=df_threshold):
                    continue
                out.append((term, e))
    return out


def _node_text(node: dict) -> str:
    return (node.get("clean_text")
            or node.get("statement")
            or node.get("raw_latex") or "")


def audit(
    out_csv: Path,
    *,
    sample_size: int = 50,
    categories=None,
    year_min=None,
    year_max=None,
    seed: int = 42,
    sample_rows_per_paper: int = 4,
    fresh_link: bool = False,
    unified_index_path=None,
    mathlib_dir=None,
):
    rng = random.Random(seed)
    print(f"[audit] walking corpus (categories={categories or 'all'}, "
          f"year_min={year_min}, year_max={year_max}) ...", flush=True)
    t0 = time.time()
    # Reservoir sampling: holds O(sample_size) papers in memory, not O(corpus).
    # Prevents OOM on the 96k-paper v2 corpus, particularly on login nodes.
    sample: list = []
    n_seen = 0
    t_last = t0
    for paper in iter_papers(categories=categories, year_min=year_min,
                             year_max=year_max):
        n_seen += 1
        if len(sample) < sample_size:
            sample.append(paper)
        else:
            j = rng.randrange(n_seen)
            if j < sample_size:
                sample[j] = paper
        now = time.time()
        if now - t_last >= 5.0:
            print(f"[audit]   walked {n_seen:,} papers "
                  f"({now-t0:.0f}s elapsed) ...", flush=True)
            t_last = now
    print(f"[audit]   walked {n_seen:,} papers total in "
          f"{time.time()-t0:.1f}s", flush=True)
    if n_seen == 0:
        print("No papers matched the filters.", file=sys.stderr)
        sys.exit(2)
    print(f"[audit] reservoir-sampled {len(sample)} papers (seed={seed})",
          flush=True)

    # Optionally load the foundation linker for in-memory fresh re-linking
    fresh_linker = None
    if fresh_link:
        print(f"[audit] loading foundation linker from "
              f"{unified_index_path} ...", flush=True)
        t0 = time.time()
        from foundation_linker import FoundationLinker  # noqa: E402
        fresh_linker = FoundationLinker()
        if unified_index_path:
            fresh_linker.load_unified_index(str(unified_index_path))
        if mathlib_dir:
            fresh_linker.load_mathlib_index(str(mathlib_dir))
        if not fresh_linker._entries:
            print("--fresh-link requested but no foundation index was loaded; "
                  "supply --unified-index and/or --mathlib-dir.", file=sys.stderr)
            sys.exit(2)
        print(f"[audit]   loaded {len(fresh_linker._entries):,} entries in "
              f"{time.time()-t0:.1f}s", flush=True)

    nodes_by_type: Counter = Counter()
    linked_by_type: Counter = Counter()
    fresh_linked_by_type: Counter = Counter()
    fresh_distinct_terms_by_type: defaultdict[str, set] = defaultdict(set)
    distinct_terms_by_type: defaultdict[str, set] = defaultdict(set)
    per_paper_link_counts = []

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fresh_term_index = fresh_linker._term_index if fresh_linker else None
    fresh_term_df = _build_term_df(fresh_term_index) if fresh_term_index else None

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cols = ["paper_id", "year", "category", "node_id", "node_type",
                "node_text_excerpt", "n_grounded_to",
                "n_grounded_to_specific", "sample_terms"]
        if fresh_linker is not None:
            cols += ["n_fresh_link", "fresh_sample_terms"]
        w.writerow(cols)

        print(f"[audit] linking {len(sample)} papers ...", flush=True)
        t_loop = time.time()
        for paper_idx, paper in enumerate(sample, start=1):
            if paper_idx == 1 or paper_idx % 5 == 0 or paper_idx == len(sample):
                elapsed = time.time() - t_loop
                rate = paper_idx / elapsed if elapsed > 0 else 0
                eta = (len(sample) - paper_idx) / rate if rate > 0 else 0
                print(f"[audit]   paper {paper_idx}/{len(sample)} "
                      f"({paper.paper_id}, {paper.category}, y={paper.year}) "
                      f"-- {elapsed:.0f}s elapsed, ETA {eta:.0f}s", flush=True)
            # Index grounded_to edges by target node
            grounded: defaultdict[str, list] = defaultdict(list)
            for e in paper.edges:
                if not isinstance(e, dict):
                    continue
                if e.get("type") != "grounded_to":
                    continue
                tgt = e.get("target")
                if tgt:
                    grounded[tgt].append(e)

            total_links_in_paper = sum(len(v) for v in grounded.values())
            per_paper_link_counts.append(total_links_in_paper)

            # Stats per node, plus CSV rows for a few sampled nodes per paper
            paper_node_rows = []
            for node in paper.nodes:
                if not isinstance(node, dict):
                    continue
                ntype = node.get("type") or ""
                nid = node.get("id")
                nodes_by_type[ntype] += 1
                links = grounded.get(nid, [])
                specific = [e for e in links if not e.get("generic")]
                if specific:
                    linked_by_type[ntype] += 1
                    for e in specific:
                        s = e.get("source")
                        if s:
                            distinct_terms_by_type[ntype].add(s)

                # Fresh-link pass (in-memory)
                fresh_hits = []
                if fresh_term_index is not None:
                    fresh_hits = _fresh_link_text(_node_text(node),
                                                  fresh_term_index,
                                                  term_df=fresh_term_df)
                    if fresh_hits:
                        fresh_linked_by_type[ntype] += 1
                        for _term, ent in fresh_hits:
                            nm = ent.get("name")
                            if nm:
                                fresh_distinct_terms_by_type[ntype].add(nm)

                paper_node_rows.append((node, links, specific, fresh_hits))

            # Sample some rows for the CSV (prefer theorem/open_problem types)
            preferred = [r for r in paper_node_rows
                         if r[0].get("type") in THEOREM_LIKE | QUESTION_LIKE]
            chosen = preferred[:sample_rows_per_paper] or \
                     paper_node_rows[:sample_rows_per_paper]
            for node, links, specific, fresh_hits in chosen:
                sample_terms = [e.get("source") for e in specific[:3]]
                row = [
                    paper.paper_id, paper.year, paper.category,
                    node.get("id"), node.get("type"),
                    _node_text(node)[:180].replace("\n", " "),
                    len(links), len(specific),
                    "; ".join(t for t in sample_terms if t),
                ]
                if fresh_linker is not None:
                    fresh_names = [e.get("name") for _t, e in fresh_hits[:3]]
                    row += [
                        len(fresh_hits),
                        "; ".join(n for n in fresh_names if n),
                    ]
                w.writerow(row)

    # Summary to stdout
    print(f"=== Foundation-linker audit ({len(sample)} papers) ===\n")
    if fresh_linker is not None:
        print(f"{'type':<22} {'nodes':>7} "
              f"{'exist':>7} {'cov%':>6}  "
              f"{'fresh':>7} {'cov%':>6}  "
              f"{'gain%':>6}")
    else:
        print(f"{'type':<22} {'nodes':>7} {'linked':>7} {'cov%':>6} "
              f"{'distinct_terms':>15}")
    all_types = sorted(set(nodes_by_type)
                       | set(linked_by_type)
                       | set(fresh_linked_by_type))
    for t in all_types:
        n = nodes_by_type[t]
        L = linked_by_type[t]
        cov = 100.0 * L / n if n else 0.0
        if fresh_linker is not None:
            Lf = fresh_linked_by_type[t]
            covf = 100.0 * Lf / n if n else 0.0
            gain = covf - cov
            flag = " <-- GATE" if t in THEOREM_LIKE and covf < 30.0 else ""
            print(f"{t:<22} {n:>7} {L:>7} {cov:>5.1f}%  "
                  f"{Lf:>7} {covf:>5.1f}%  {gain:>+5.1f}%{flag}")
        else:
            terms = len(distinct_terms_by_type[t])
            flag = " <-- GATE" if t in THEOREM_LIKE and cov < 30.0 else ""
            print(f"{t:<22} {n:>7} {L:>7} {cov:>5.1f}% {terms:>15}{flag}")
    print()
    th_n = sum(nodes_by_type[t] for t in THEOREM_LIKE)
    th_L = sum(linked_by_type[t] for t in THEOREM_LIKE)
    th_cov = 100.0 * th_L / th_n if th_n else 0.0
    qn = sum(nodes_by_type[t] for t in QUESTION_LIKE)
    qL = sum(linked_by_type[t] for t in QUESTION_LIKE)
    q_cov = 100.0 * qL / qn if qn else 0.0
    print(f"Theorem-like coverage (existing): {th_cov:.1f}%  ({th_L}/{th_n})")
    print(f"Question-like coverage (existing): {q_cov:.1f}%  ({qL}/{qn})")
    if fresh_linker is not None:
        th_Lf = sum(fresh_linked_by_type[t] for t in THEOREM_LIKE)
        th_covf = 100.0 * th_Lf / th_n if th_n else 0.0
        qLf = sum(fresh_linked_by_type[t] for t in QUESTION_LIKE)
        q_covf = 100.0 * qLf / qn if qn else 0.0
        print(f"Theorem-like coverage (fresh):    {th_covf:.1f}%  "
              f"({th_Lf}/{th_n})   gain {th_covf-th_cov:+.1f}%")
        print(f"Question-like coverage (fresh):   {q_covf:.1f}%  "
              f"({qLf}/{qn})   gain {q_covf-q_cov:+.1f}%")
        gate_cov = th_covf
    else:
        gate_cov = th_cov
    print(f"Mean grounded_to edges per paper: "
          f"{sum(per_paper_link_counts)/max(1,len(per_paper_link_counts)):.1f}")
    if gate_cov < 30.0:
        print("\nGATE: theorem-like coverage < 30%. Recommend downstream "
              "methods fall back to operator+token features.")
    else:
        print("\nGATE: theorem-like coverage >= 30%. Foundation_ids signal "
              "is usable.")
    print(f"\nSample CSV (for hand spot-check): {out_csv}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=50,
                    help="Number of papers to sample (default: 50)")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--categories", default=None,
                    help="Comma-sep categories (e.g. math_CO,math_PR)")
    ap.add_argument("--year-min", type=int, default=None)
    ap.add_argument("--year-max", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fresh-link", action="store_true",
                    help="Additionally run the foundation linker in-memory "
                         "on each sampled paper, to estimate the coverage "
                         "gain from a re-link without writing to disk.")
    ap.add_argument("--unified-index", default=None,
                    help="Merged foundation file used by --fresh-link. "
                         "Defaults to config.FOUNDATION_INDEX_PATH "
                         "(currently clean_foundation_with_books.json).")
    ap.add_argument("--mathlib-dir", default=None,
                    help="Mathlib midlevel/ directory used by --fresh-link.")
    args = ap.parse_args()
    if args.fresh_link and args.unified_index is None:
        try:
            from config import FOUNDATION_INDEX_PATH
            if Path(FOUNDATION_INDEX_PATH).exists():
                args.unified_index = str(FOUNDATION_INDEX_PATH)
                print(f"[audit] using foundation index from config: {args.unified_index}",
                      file=sys.stderr)
        except ImportError:
            pass
    audit(
        out_csv=Path(args.out),
        sample_size=args.sample,
        categories=args.categories.split(",") if args.categories else None,
        year_min=args.year_min,
        year_max=args.year_max,
        seed=args.seed,
        fresh_link=args.fresh_link,
        unified_index_path=args.unified_index,
        mathlib_dir=args.mathlib_dir,
    )


if __name__ == "__main__":
    main()
