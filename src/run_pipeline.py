#!/usr/bin/env python3
"""
Unified pipeline orchestrator for Authomathics.

Filters arXiv papers by metadata (ID, date, category, regex), then runs one
or more operations on each matching paper. Operations can be chained.

Operations:
  download     : fetch LaTeX source / PDF / metadata from arXiv (wraps
                 extract_arxiv_data.py logic in src/)
  parse        : tex -> JSON (mid-level knowledge graph)
                 Delegates via subprocess to LLMVersion/parse_batch.py.
                 Subprocess isolation is intentional: LLMVersion/ has its
                 own copies of config.py, paper_plot_utils.py, and
                 extract_arxiv_funcs.py that differ from the src/ versions.
                 Running the extractor as a subprocess with cwd=LLMVersion/
                 ensures it resolves its own local modules, not the src/
                 ones, and keeps its module cache isolated from this
                 orchestrator process.
  validate     : JSON -> DAG acyclicity + schema validation report
                 Uses src/validate_annotation.py.
  visualize    : JSON -> PNG + interactive HTML
                 Uses src/visualize_annotation.py.
  link         : JSON -> JSON augmented with foundation-graph links
                 Uses src/link_to_foundation.py.
  evaluate     : JSON -> precision/recall/F1 against a gold standard
                 Uses src/evaluate_annotation.py / evaluate_extraction.py.
  anomalies    : JSON -> anomalies_report.csv flagging structural / content
                 weirdness for manual review (uses src/anomaly_detection.py).
                 Useful for catching extraction failures and feeding them
                 back to the regex-tuning / distillation loop.
  cross_paper  : (future, Phase 3) cross-paper relationship detection

Examples:

  # Parse 500 math.CO papers with manual extraction:
  python src/run_pipeline.py \\
      --operations parse \\
      --category math.CO \\
      --start 2024-01-01 \\
      --end 2026-04-01 \\
      --top-k 500 \\
      --out-dir /path/to/out \\
      --extraction-mode manual

  # Parse + validate + visualize a single paper:
  python src/run_pipeline.py \\
      --operations parse,validate,visualize \\
      --regex-id '^2501\\.00685' \\
      --out-dir /path/to/out \\
      --extraction-mode both \\
      --html

  # Visualize existing JSONs (no re-extraction needed):
  python src/run_pipeline.py \\
      --operations visualize \\
      --out-dir /path/to/out \\
      --html

Design notes:
  * The `parse` operation runs Yaron's extractor (LLMVersion/parse_batch.py)
    as a subprocess. This isolates LLMVersion's `math_classes` namespace from
    src/'s `math_classes` namespace, which prevents field-name conflicts.
  * All other operations import directly from src/ tools, which all share the
    src/math_classes data model and the unified JSON schema (annotation_schema.md).
  * The shared interface between `parse` (LLMVersion) and all other operations
    (src/) is the JSON file on disk, not a Python object in memory.
"""

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import List, Optional

# src/ is this script's directory, so it is implicitly on sys.path when run
# via `python src/run_pipeline.py`. Add it explicitly as well, for safety.
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_LLMVERSION_DIR = _SRC_DIR / "LLMVersion"
_REPO_ROOT = _SRC_DIR.parent


# =============================================================================
# KNOWN OPERATIONS
# =============================================================================

KNOWN_OPERATIONS = [
    "download",
    "parse",
    "validate",
    "visualize",
    "link",
    "evaluate",
    "anomalies",
    "stats",
    "consensus",
    "eval",
    "cross_paper",
]


def _parse_operations(ops_arg: str) -> List[str]:
    """Parse comma-separated --operations and validate."""
    ops = [o.strip() for o in ops_arg.split(",") if o.strip()]
    unknown = [o for o in ops if o not in KNOWN_OPERATIONS]
    if unknown:
        raise ValueError(
            f"Unknown operations: {unknown}. "
            f"Known: {KNOWN_OPERATIONS}"
        )
    return ops


# =============================================================================
# HELPERS
# =============================================================================

def _looks_like_paper_graph(path: Path) -> bool:
    """Fast content check: does this JSON file look like a unified paper graph?

    Parsing tarball-extracted source trees picks up stray JSON files
    (author-included READMEs, metadata files, etc.) via rglob. We only want
    real paper graphs — ones that have a 'nodes' or 'objects' top-level key
    matching the unified schema (see annotation_schema.md).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return ("nodes" in data) or ("objects" in data)


def _list_jsons(out_dir: str) -> List[Path]:
    """Find all knowledge-graph JSON files under out_dir.

    Excludes:
    - Pipeline report files (anomalies_detail.json, etc.)
    - Stray JSONs from arXiv tarball extraction (00README.json in tex/ dirs)
    - Files that don't match the unified schema (no 'nodes' or 'objects' key)

    Only considers files inside json/ subdirectories OR at the top level
    of out_dir. Files in tex/ subdirectories are always skipped.
    """
    out_path = Path(out_dir)
    if not out_path.exists():
        return []
    all_jsons = sorted(out_path.rglob("*.json"))
    excluded_names = {
        "anomalies_report.csv",
        "anomalies_detail.json",
        "corpus_stats.csv",
        "validate_report.csv",
        "evaluation_results.csv",
        "status_log.csv",
    }
    return [
        p for p in all_jsons
        if p.name not in excluded_names
        and "/tex/" not in str(p)  # skip tarball-extracted stray files
        and _looks_like_paper_graph(p)
    ]


# =============================================================================
# OPERATION: download (arXiv -> local tex/pdf/metadata)
# =============================================================================

def op_download(args) -> None:
    """Download LaTeX source / PDF / metadata for matching papers from arXiv.

    Wraps extract_arxiv_funcs.fetch_arxiv_batch() in the existing src/ toolchain.
    """
    try:
        from extract_arxiv_funcs import fetch_arxiv_batch
    except ImportError as e:
        print(f"[pipeline] download: cannot import extract_arxiv_funcs: {e}")
        return

    print(f"[pipeline] download: fetching papers (category={args.category}, "
          f"start={args.start_date}, end={args.end_date}, regex_id={args.regex_id})")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    formats = args.download_formats.split(",") if args.download_formats else ["metadata", "source"]

    data = fetch_arxiv_batch(
        regex_id=args.regex_id,
        start_date=args.start_date,
        end_date=args.end_date,
        category=args.category,
        formats=formats,
        output_dir=str(out_dir),
        verbose=args.verbose,
    )
    print(f"[pipeline] download: fetched {len(data)} papers -> {out_dir}")


# =============================================================================
# OPERATION: parse (tex -> JSON)  -- SUBPROCESS to LLMVersion
# =============================================================================

def op_parse(args) -> None:
    """Run the parse backend selected by --extract-mode.

    Phase 3 dispatch:
      regex (default)        — Yaron's per-type / LLMVersion path (this body)
      holistic-multi         — multi-model holistic LLM (Tier B silver-gold)
      holistic-proof-steps   — holistic LLM with proof-step decomposition (Tier D)

    The legacy --extraction-mode {manual, llm, both} flag still works and is
    forwarded to LLMVersion/parse_batch.py unchanged in regex mode. NOTE the
    distinct semantics: --extract-mode (new) selects the BACKEND; the old
    --extraction-mode selects the manual/llm flavor WITHIN the regex backend.

    Subprocess isolation keeps LLMVersion's math_classes namespace from
    colliding with src/'s math_classes namespace in the same Python process.
    """
    mode = getattr(args, "extract_mode", "regex")
    if mode == "holistic-multi":
        return run_holistic_multi_parse(args)
    if mode == "holistic-proof-steps":
        return run_holistic_proof_steps_parse(args)
    if mode != "regex":
        sys.exit(f"[pipeline] parse: unknown --extract-mode: {mode}")

    script = _LLMVERSION_DIR / "parse_batch.py"
    if not script.exists():
        print(f"[pipeline] parse: ERROR: cannot find {script}")
        sys.exit(1)

    cmd = [sys.executable, str(script)]
    # filter args (shared CLI names between run_pipeline.py and parse_batch.py)
    if args.start_date:
        cmd += ["--start", args.start_date]
    if args.end_date:
        cmd += ["--end", args.end_date]
    if args.days is not None:
        cmd += ["--days", str(args.days)]
    if args.category:
        cmd += ["--category", args.category]
    if args.regex_id:
        cmd += ["--regex-id", args.regex_id]
    if args.top_k is not None:
        cmd += ["--top-k", str(args.top_k)]
    cmd += ["--out-dir", str(args.out_dir)]
    if args.verbose:
        cmd += ["--verbose"]

    # parse-specific args
    cmd += ["--extraction-mode", args.extraction_mode]
    cmd += ["--llm-provider", args.llm_provider]
    cmd += ["--llm-model", args.llm_model]
    cmd += ["--llm-chunk-chars", str(args.llm_chunk_chars)]
    if args.prompt_file:
        cmd += ["--prompt-file", args.prompt_file]
    cmd += ["--structure-types", args.structure_types]
    if args.tex_dir:
        cmd += ["--tex-dir", args.tex_dir]
    if args.safeguard is not None:
        cmd += ["--safeguard", str(args.safeguard)]

    print(f"[pipeline] parse: running LLMVersion extractor as subprocess")
    print(f"[pipeline] parse: cmd = {' '.join(cmd)}")

    # Run with LLMVersion directory as CWD so that unqualified
    # `from math_classes import X` inside that script resolves to
    # LLMVersion/math_classes.py, not src/math_classes.py.
    result = subprocess.run(cmd, cwd=str(_LLMVERSION_DIR))
    if result.returncode != 0:
        print(f"[pipeline] parse: LLMVersion extractor exited with code {result.returncode}")
        sys.exit(result.returncode)


# =============================================================================
# OPERATION: validate (JSON -> DAG + schema report)
# =============================================================================

def op_validate(args) -> None:
    """Validate all JSONs under out_dir via src/validate_annotation.py."""
    try:
        from validate_annotation import validate_file  # noqa
    except ImportError as e:
        print(f"[pipeline] validate: cannot import validate_annotation: {e}")
        return

    json_paths = _list_jsons(args.out_dir)
    if not json_paths:
        print(f"[pipeline] validate: no JSON files found under {args.out_dir}")
        return

    print(f"[pipeline] validate: checking {len(json_paths)} JSON files")

    n_ok = 0
    n_error = 0
    report_rows = []
    for jp in json_paths:
        try:
            n_obj, n_rel, n_err, n_warn = validate_file(jp, verbose=args.verbose)
            report_rows.append((str(jp), n_obj, n_rel, n_err, n_warn))
            if n_err == 0:
                n_ok += 1
            else:
                n_error += 1
        except Exception as e:
            if args.verbose:
                print(f"[pipeline] validate: {jp.name}: FAILED ({e})")
            n_error += 1
            report_rows.append((str(jp), 0, 0, -1, -1))

    import csv
    report_path = Path(args.out_dir) / "validate_report.csv"
    with open(report_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["json_path", "n_objects", "n_relations", "n_errors", "n_warnings"])
        writer.writerows(report_rows)
    print(f"[pipeline] validate: {n_ok} valid, {n_error} with errors")
    print(f"[pipeline] validate: summary -> {report_path}")


# =============================================================================
# OPERATION: visualize (JSON -> PNG + HTML)
# =============================================================================

def op_visualize(args) -> None:
    """Generate PNG and/or HTML visualizations for all JSONs under out_dir."""
    try:
        from visualize_annotation import draw_dag, generate_interactive_html  # noqa
    except ImportError as e:
        print(f"[pipeline] visualize: cannot import visualize_annotation: {e}")
        return

    json_paths = _list_jsons(args.out_dir)
    if not json_paths:
        print(f"[pipeline] visualize: no JSON files found under {args.out_dir}")
        return

    n_total = len(json_paths)
    print(f"[pipeline] visualize: drawing {n_total} graphs (resolution={args.resolution})")

    import os
    import io
    import contextlib

    n_ok = 0
    for i, jp in enumerate(json_paths, start=1):
        # Extract paper_id from filename for progress display
        paper_id = jp.stem.replace("_manual", "").replace("_anthropic", "") \
                          .replace("_openai", "").replace("_huggingface", "")

        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("nodes", [])
            edges = data.get("edges", [])
            if not nodes:
                print(f"[pipeline] visualize: {paper_id} [{i}/{n_total}] skipped (no nodes)")
                continue
            metadata = data.get("metadata", {})

            what = []  # track what we're generating

            # Output to sibling html/ or png/ dir if JSON is inside a json/ dir
            if jp.parent.name == "json":
                png_dir = jp.parent.parent / "png"
                html_dir = jp.parent.parent / "html"
            else:
                png_dir = jp.parent
                html_dir = jp.parent

            # Suppress noisy library output (e.g. "Index has N searchable terms")
            # by capturing stdout during draw_dag / generate_interactive_html calls
            png_path = png_dir / jp.with_suffix(".png").name
            if not args.html_only:
                png_dir.mkdir(parents=True, exist_ok=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    draw_dag(nodes, edges, str(png_path), metadata=metadata,
                             resolution=args.resolution)
                what.append("PNG")

            if args.html or args.html_only:
                import tempfile
                tmp_dir = tempfile.mkdtemp()
                tmp_png = os.path.join(tmp_dir, jp.stem + "_nolegend.png")
                svg_only = tmp_png.replace(".png", ".svg")
                html_dir.mkdir(parents=True, exist_ok=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    draw_dag(nodes, edges, tmp_png, metadata=metadata,
                             resolution=args.resolution, show_legend=False)
                    html_path = html_dir / jp.with_suffix(".html").name
                    generate_interactive_html(data, svg_only, str(html_path))
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
                what.append("HTML")

            n_ok += 1
            print(f"[pipeline] visualize: {paper_id} [{i}/{n_total}] "
                  f"{'+'.join(what)} ({len(nodes)} nodes, {len(edges)} edges)")
        except Exception as e:
            print(f"[pipeline] visualize: {paper_id} [{i}/{n_total}] FAILED: {e}")
            if args.verbose:
                traceback.print_exc()

    print(f"[pipeline] visualize: {n_ok}/{n_total} graphs rendered successfully")


# =============================================================================
# OPERATION: link (JSON -> JSON with foundation-graph links)
# =============================================================================

def op_link(args) -> None:
    """Augment JSONs IN-PLACE with foundation-graph links.

    Uses the same build_foundation_index + link_paper functions that the
    interactive HTML visualization uses (ghost nodes). Adds matched
    foundation entries as 'grounded_to' edges in the JSON, so that
    downstream operations (stats, anomalies) can count them.
    """
    try:
        from link_to_foundation import (build_foundation_index, link_paper,
                                          _build_automaton, compute_idf, filter_by_idf)
    except ImportError as e:
        print(f"[pipeline] link: cannot import link_to_foundation: {e}")
        return

    json_paths = _list_jsons(args.out_dir)
    if not json_paths:
        print(f"[pipeline] link: no JSON files found under {args.out_dir}")
        return

    # Auto-discover foundation files under DATA_DIR
    try:
        from config import DATA_DIR
        data_dir = Path(str(DATA_DIR))
    except ImportError:
        data_dir = None

    foundation_paths = []
    if data_dir and data_dir.exists():
        # Prefer clean_foundation.json (deduplicated, filtered) if available
        clean_path = data_dir / "naturalproofs" / "clean_foundation.json"
        if clean_path.exists():
            foundation_paths.append(str(clean_path))
            print(f"[pipeline] link: using clean foundation index: {clean_path}")
        else:
            # Fallback: raw NaturalProofs files
            np_dir = data_dir / "naturalproofs" / "raw"
            if np_dir.exists():
                for np_file in sorted(np_dir.glob("naturalproofs_*.json")):
                    foundation_paths.append(str(np_file))
    if not foundation_paths:
        print(f"[pipeline] link: no foundation files found under {data_dir}; "
              f"using built-in 53 well-known terms only")

    # Build the foundation index once (shared across all papers)
    print(f"[pipeline] link: building foundation index from {len(foundation_paths)} files...")
    try:
        index = build_foundation_index(foundation_paths or None)
    except Exception as e:
        print(f"[pipeline] link: failed to build foundation index: {e}")
        return

    # Build Aho-Corasick automaton for fast multi-pattern matching
    automaton, term_map = _build_automaton(index, min_term_len=5)
    if automaton:
        print(f"[pipeline] link: using Aho-Corasick (fast, single-pass)")
    else:
        print(f"[pipeline] link: pyahocorasick not installed, using slow regex fallback")

    n_total = len(json_paths)

    # ── Pass 1: match all papers, collect per-paper matches ──
    per_paper = []  # list of (json_path, data_dict, matches_list)
    all_matches_flat = []  # for IDF computation

    for i, jp in enumerate(json_paths, start=1):
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)

            nodes = data.get("nodes", [])

            # Remove any previous foundation edges (re-linking is idempotent)
            data["edges"] = [e for e in data.get("edges", [])
                             if e.get("type") not in ("grounded_to", "mentions_concept")]

            # Run foundation matching
            matches = link_paper(nodes, index, min_term_len=5,
                                 automaton=automaton, term_map=term_map)

            # Tag each match with paper index (for IDF computation)
            for m in matches:
                m["_paper_idx"] = i

            per_paper.append((jp, data, matches))
            all_matches_flat.extend(matches)

        except Exception as e:
            print(f"[pipeline] link: {jp.name}: FAILED reading: {e}")

    # ── Compute IDF across corpus ──
    idf_scores = compute_idf(all_matches_flat, n_total)
    high_df_terms = {term for term, s in idf_scores.items() if s["df_frac"] > 0.10}
    if high_df_terms:
        print(f"[pipeline] link: {len(high_df_terms)} high-frequency terms "
              f"(df>10%, tagged as generic):")
        for term in sorted(high_df_terms,
                           key=lambda t: -idf_scores[t]["df"])[:20]:
            s = idf_scores[term]
            print(f"    {s['df']:>4} papers ({s['df_frac']:.0%}): {term}")
        if len(high_df_terms) > 20:
            print(f"    ... and {len(high_df_terms) - 20} more")

    # ── Pass 2: write ALL edges with IDF tags ──
    n_linked = 0
    total_matches = 0
    n_specific = 0  # edges with df <= 10%

    for jp, data, matches in per_paper:
        try:
            edges = data["edges"]
            seen = set()
            for m in matches:
                key = (m["node_id"], m["foundation_name"])
                if key in seen:
                    continue
                seen.add(key)
                fname = m["foundation_name"]
                idf_info = idf_scores.get(fname, {})
                df_frac = idf_info.get("df_frac", 0)
                is_generic = fname in high_df_terms
                edges.append({
                    "source": fname,
                    "target": m["node_id"],
                    "type": "grounded_to",
                    "note": f"matched term: {m['matched_term']}",
                    "df": idf_info.get("df", 0),
                    "df_frac": round(df_frac, 4),
                    "idf": round(idf_info.get("idf", 0), 3),
                    "generic": is_generic,
                })
                if not is_generic:
                    n_specific += 1

            n_new = len(seen)
            if n_new > 0:
                n_linked += 1
                total_matches += n_new

            data["edges"] = edges
            with open(jp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            print(f"[pipeline] link: {jp.name}: FAILED writing: {e}")

    print(f"[pipeline] link: {n_linked}/{n_total} papers linked, "
          f"{total_matches} total foundation edges "
          f"({n_specific} specific + {total_matches - n_specific} generic)")


# =============================================================================
# OPERATION: evaluate (JSON -> P/R/F1 vs gold)
# =============================================================================

def op_evaluate(args) -> None:
    """Evaluate extracted JSONs against gold-standard annotations."""
    if not args.gold_dir:
        print(f"[pipeline] evaluate: --gold-dir is required for the evaluate operation")
        return

    gold_dir = Path(args.gold_dir)
    if not gold_dir.exists():
        print(f"[pipeline] evaluate: gold directory does not exist: {gold_dir}")
        return

    try:
        from evaluate_extraction import evaluate_pair  # noqa
    except ImportError:
        # Fall back to subprocess invocation
        print(f"[pipeline] evaluate: evaluate_extraction.evaluate_pair not importable;")
        print(f"[pipeline] evaluate: falling back to subprocess invocation")
        json_paths = _list_jsons(args.out_dir)
        for jp in json_paths:
            gold_candidate = gold_dir / jp.name
            if not gold_candidate.exists():
                if args.verbose:
                    print(f"[pipeline] evaluate: no gold for {jp.name}, skipping")
                continue
            cmd = [
                sys.executable,
                str(_SRC_DIR / "evaluate_extraction.py"),
                "--extracted", str(jp),
                "--gold", str(gold_candidate),
            ]
            subprocess.run(cmd, check=False)
        return

    json_paths = _list_jsons(args.out_dir)
    print(f"[pipeline] evaluate: comparing {len(json_paths)} extracted JSONs to gold")
    # ... in-process evaluation would go here if evaluate_pair is importable
    # (deferred: the current evaluate_extraction.py CLI is a reasonable fallback)


# =============================================================================
# OPERATION: anomalies (JSON -> anomalies_report.csv)
# =============================================================================

def op_anomalies(args) -> None:
    """Run anomaly detection on all JSONs under out_dir. Writes report CSV.

    Flags papers with structural / content-wise weirdness for manual review.
    Categories: A (extraction failed), B (structural oddity), C (content oddity).
    Category D (distribution-level) is planned for a future pass.
    """
    try:
        from anomaly_detection import (
            detect_anomalies_in_dir, write_anomalies_report, write_anomalies_detail,
        )
    except ImportError as e:
        print(f"[pipeline] anomalies: cannot import anomaly_detection: {e}")
        return

    records, detail_list, n_scanned, n_flagged = detect_anomalies_in_dir(
        args.out_dir, verbose=args.verbose
    )

    report_path = Path(args.out_dir) / "anomalies_report.csv"
    write_anomalies_report(records, str(report_path))

    detail_path = Path(args.out_dir) / "anomalies_detail.json"
    write_anomalies_detail(detail_list, str(detail_path))

    print(f"[pipeline] anomalies: scanned {n_scanned} papers, flagged {n_flagged} "
          f"({len(records)} total anomaly records)")
    print(f"[pipeline] anomalies: report  -> {report_path}")
    print(f"[pipeline] anomalies: details -> {detail_path} ({len(detail_list)} flagged papers)")

    # Severity breakdown for quick visibility
    from collections import Counter
    sev_counts = Counter(r[3] for r in records)
    if sev_counts:
        print(f"[pipeline] anomalies: severity breakdown — "
              f"high={sev_counts.get('high', 0)}, "
              f"medium={sev_counts.get('medium', 0)}, "
              f"low={sev_counts.get('low', 0)}")


# =============================================================================
# OPERATION: stats (JSON -> corpus_stats.csv)
# =============================================================================

def op_stats(args) -> None:
    """Compute per-paper statistics and write corpus_stats.csv."""
    try:
        from corpus_stats import compute_corpus_stats, write_corpus_stats, print_summary
    except ImportError as e:
        print(f"[pipeline] stats: cannot import corpus_stats: {e}")
        return

    stats_list, n_scanned = compute_corpus_stats(args.out_dir, verbose=args.verbose)

    report_path = Path(args.out_dir) / "corpus_stats.csv"
    write_corpus_stats(stats_list, str(report_path))

    print(f"[pipeline] stats: {n_scanned} papers -> {report_path}")
    print_summary(stats_list)


# =============================================================================
# OPERATION: cross_paper (future, Phase 3)
# =============================================================================

def op_cross_paper(args) -> None:
    print(f"[pipeline] cross_paper: not yet implemented (Phase 3 of the roadmap).")
    print(f"[pipeline] cross_paper: this is a placeholder for future cross-paper")
    print(f"[pipeline] cross_paper: relationship detection (generalizes, strengthens, contradicts).")


# =============================================================================
# MAIN CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Unified Authomathics pipeline: filter arXiv papers by metadata, "
            "then run one or more operations (download, parse, validate, "
            "visualize, link, evaluate, cross_paper). See __doc__ for examples."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # --- operations ---
    parser.add_argument(
        "--operations",
        type=str,
        default="parse",
        help=(
            "Comma-separated list of operations to run in order. "
            "Known: " + ", ".join(KNOWN_OPERATIONS) + ". "
            "Default: parse."
        ),
    )

    # --- filter args (shared with Yaron's parse_batch.py) ---
    parser.add_argument("--start", dest="start_date", type=str, default=None,
                        help="Start date YYYY-MM-DD (submission date).")
    parser.add_argument("--end", dest="end_date", type=str, default=None,
                        help="End date YYYY-MM-DD (submission date).")
    parser.add_argument("--days", type=int, default=None,
                        help="Alternative: fetch papers from last N days.")
    parser.add_argument("--category", type=str, default=None,
                        help="ArXiv category, e.g. math.CO, math.PR, cs.LG.")
    parser.add_argument("--regex-id", type=str, default=None,
                        help='Regex filter on base IDs, e.g. "^2501\\\\.00685".')
    parser.add_argument("--top-k", type=int, default=None,
                        help="Process at most this many base IDs after filtering. "
                             "Use <=0 for no limit.")
    parser.add_argument("--out-dir", type=str, required=True,
                        help="Root directory for outputs.")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose prints.")

    # --- download operation args ---
    parser.add_argument("--download-formats", type=str, default="metadata,source",
                        help="Comma-separated formats for download op: "
                             "metadata,source,pdf,html")

    # --- parse operation args (forwarded to LLMVersion subprocess) ---
    parser.add_argument("--extraction-mode", type=str, default="manual",
                        choices=["manual", "llm", "both"],
                        help="Extraction mode: manual (default), llm, or both.")
    parser.add_argument("--llm-model", type=str,
                        default="claude-sonnet-4-20250514",
                        help="LLM model name (when mode includes llm).")
    parser.add_argument("--llm-provider", type=str, default="anthropic",
                        choices=["anthropic", "openai", "huggingface"],
                        help="LLM provider.")
    parser.add_argument("--llm-chunk-chars", type=int, default=30000,
                        help="Max characters per chunk for LLM extraction.")
    parser.add_argument("--prompt-file", type=str, default=None,
                        help="Path to custom prompt template file.")
    parser.add_argument("--structure-types", type=str,
                        default="definition,theorem,lemma,proposition,corollary,"
                                "claim,conjecture,problem,open_problem,proof,"
                                "algorithm,assumption,example,exercise,remark,table",
                        help="Comma-separated structure types to extract.")
    parser.add_argument("--tex-dir", type=str, default=None,
                        help="Directory to search for local .tex files instead of "
                             "the default FULL_PAPERS_DIR from config. Useful when "
                             "tex sources live in a non-standard location.")
    parser.add_argument("--safeguard", type=int, default=None, const=90, nargs="?",
                        metavar="SECONDS",
                        help="Per-paper parse timeout in seconds. Papers exceeding "
                             "this are skipped. Defaults to 90s if given without a value.")

    # --- visualize operation args ---
    parser.add_argument("--resolution", choices=["standard", "full"], default="standard",
                        help="Visualization resolution: standard (collapse proofs, "
                             "hide equations) or full (show all nodes).")
    parser.add_argument("--html", action="store_true",
                        help="Also generate interactive HTML (for visualize op).")
    parser.add_argument("--html-only", action="store_true",
                        help="Generate only interactive HTML, no PNG (for visualize op).")

    # --- evaluate operation args ---
    parser.add_argument("--gold-dir", type=str, default=None,
                        help="Directory containing gold-standard JSONs "
                             "(for the evaluate operation).")

    # --- Phase 3: tier / extract-mode selection ---
    parser.add_argument("--extract-mode", type=str, default="regex",
                        choices=["regex", "holistic-multi", "holistic-proof-steps"],
                        help="Phase 3: parse backend. "
                             "'regex' (default) = per-type / LLMVersion (Tier A); "
                             "'holistic-multi' = multi-LLM holistic via "
                             "scripts/silver_gold/run_extraction.py (Tier B); "
                             "'holistic-proof-steps' = holistic with "
                             "proof-step decomposition (Tier D). NOTE: this is "
                             "DIFFERENT from --extraction-mode (which is "
                             "manual/llm/both inside the regex backend).")
    parser.add_argument("--models-config", type=str, default=None,
                        help="YAML or JSON listing models for "
                             "--extract-mode holistic-multi / holistic-proof-steps. "
                             "Same format as scripts/silver_gold/example_config.yaml.")
    parser.add_argument("--base-dir", type=str, default=None,
                        help="Tier B/D root: the alignment_benchmark dir "
                             "(parent of papers/). Used by holistic-multi mode "
                             "and by the consensus / eval operations.")
    parser.add_argument("--registry", type=str, default=None,
                        help="Tier B/D paper_registry.csv path. Used by "
                             "holistic-multi mode.")
    parser.add_argument("--paper-ids", type=str, default="",
                        help="Comma-separated subset of paper_ids (Tier B/C/D).")
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap papers to first N (0 = all). Used by "
                             "holistic modes and downstream tier ops.")
    parser.add_argument("--sleep", type=float, default=0.0,
                        help="Sleep seconds between LLM calls "
                             "(holistic modes).")
    parser.add_argument("--no-extraction", action="store_true",
                        help="In holistic modes, skip extraction; only run "
                             "downstream ops (validate / consensus / eval) on "
                             "existing JSONs.")
    parser.add_argument("--consensus-suffix-a", type=str, default="_opus_4_7",
                        help="Suffix of reference JSONs for the consensus op "
                             "(default: '_opus_4_7' = gold_opus_4_7.json).")
    parser.add_argument("--consensus-suffix-b", type=str, default=None,
                        help="Suffix of comparison JSONs for the consensus op. "
                             "If unset, run pairwise vs all suffixes in "
                             "--models-config.")

    args = parser.parse_args()

    # Normalize out_dir to an absolute path BEFORE dispatching to any operation.
    # Reason: op_parse runs parse_batch.py as a subprocess with cwd=LLMVersion/,
    # so a relative --out-dir would resolve relative to LLMVersion/ in the
    # subprocess but relative to src/ (or wherever the parent runs from) in
    # all other operations. Making it absolute means every operation sees the
    # same path regardless of cwd.
    args.out_dir = str(Path(args.out_dir).resolve())
    # Also ensure the directory exists so operations that only read (like
    # anomalies running standalone on a pre-existing output dir) don't crash
    # while writing their report files.
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    try:
        operations = _parse_operations(args.operations)
    except ValueError as e:
        print(f"[pipeline] {e}")
        sys.exit(1)

    print(f"[pipeline] operations to run (in order): {operations}")
    print(f"[pipeline] out-dir: {args.out_dir}")
    print(f"[pipeline] src/ = {_SRC_DIR}")
    print(f"[pipeline] LLMVersion/ = {_LLMVERSION_DIR}")

    dispatch = {
        "download": op_download,
        "parse": op_parse,
        "validate": op_validate,
        "visualize": op_visualize,
        "link": op_link,
        "evaluate": op_evaluate,
        "anomalies": op_anomalies,
        "stats": op_stats,
        "consensus": op_consensus,
        "eval": op_eval,
        "cross_paper": op_cross_paper,
    }

    for op_name in operations:
        print(f"\n[pipeline] ========== {op_name} ==========")
        try:
            dispatch[op_name](args)
        except Exception as e:
            print(f"[pipeline] {op_name}: FAILED with {type(e).__name__}: {e}")
            if args.verbose:
                traceback.print_exc()
            # Continue to next operation rather than aborting the whole pipeline
            continue

    print(f"\n[pipeline] Done.")


# =============================================================================
# Phase 3 — holistic-multi parse backend (Tier B)
# =============================================================================
# These live at the end of the file so the diff is purely additive.
# They mirror scripts/silver_gold/run_full_pipeline.py:run_extraction_for_model
# closely; future cleanup may consolidate.

_RUN_EXTRACTION_TOOL = _REPO_ROOT / "scripts" / "silver_gold" / "run_extraction.py"
_CONSENSUS_TOOL = _REPO_ROOT / "scripts" / "silver_gold" / "consensus_intersect.py"


def _load_models_config(path: str) -> dict:
    """Load a YAML or JSON models config. Same shape as
    scripts/silver_gold/example_config.yaml."""
    p = Path(path)
    if not p.exists():
        sys.exit(f"[pipeline] models config not found: {p}")
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:
            sys.exit("[pipeline] PyYAML not installed; convert config to .json "
                     "or `pip install pyyaml`.")
        return yaml.safe_load(text)
    return json.loads(text)


def _run_extraction_for_model(model_cfg: dict, args, paper_ids: List[str],
                              extra_flags: Optional[List[str]] = None) -> int:
    """Subprocess scripts/silver_gold/run_extraction.py for one model.

    Returns the subprocess exit code (or -1 if env API key missing).
    Mirrors run_full_pipeline.py:run_extraction_for_model.
    """
    import os
    suffix = model_cfg.get("suffix", f"_{model_cfg['name']}")

    cmd = [sys.executable, str(_RUN_EXTRACTION_TOOL),
           "--provider", model_cfg["provider"],
           "--model", model_cfg["model"],
           "--prompt-file", str(args.prompt_file),
           "--registry", str(args.registry),
           "--base-dir", str(args.base_dir),
           "--out-suffix", suffix,
           "--max-tokens", str(model_cfg.get("max_tokens", 16384)),
           "--max-input-chars", str(model_cfg.get("max_input_chars", 200000)),
           "--resume",
           "--log", f"silver_pipeline_log_{model_cfg['name']}.csv"]
    if paper_ids:
        cmd += ["--paper-ids", ",".join(paper_ids)]
    if getattr(args, "limit", 0) and args.limit > 0:
        cmd += ["--limit", str(args.limit)]
    if getattr(args, "sleep", 0.0) and args.sleep > 0:
        cmd += ["--sleep", str(args.sleep)]
    if extra_flags:
        cmd += extra_flags

    env = os.environ.copy()
    if model_cfg.get("base_url"):
        env["OPENAI_BASE_URL"] = model_cfg["base_url"]
    else:
        env.pop("OPENAI_BASE_URL", None)
    key_var = model_cfg.get("api_key_env")
    if key_var and not env.get(key_var):
        print(f"[pipeline] holistic: model '{model_cfg['name']}' env "
              f"{key_var} not set — SKIPPING")
        return -1

    print(f"\n[pipeline] holistic-multi: extracting with '{model_cfg['name']}' "
          f"(provider={model_cfg['provider']}, model={model_cfg['model']}, "
          f"suffix='{suffix}')")
    return subprocess.run(cmd, env=env).returncode


def _validate_holistic_args(args, mode_name: str) -> None:
    """Sanity-check that Tier B/D required flags are present."""
    missing = []
    if not getattr(args, "models_config", None):
        missing.append("--models-config")
    if not getattr(args, "base_dir", None):
        missing.append("--base-dir")
    if not getattr(args, "registry", None):
        missing.append("--registry")
    if not getattr(args, "prompt_file", None):
        missing.append("--prompt-file")
    if missing:
        sys.exit(f"[pipeline] {mode_name}: missing required flag(s): "
                 f"{', '.join(missing)}")


def run_holistic_multi_parse(args) -> None:
    """Tier B parse backend: holistic LLM extraction across multiple models.

    For each model in --models-config, subprocess run_extraction.py with
    the model's suffix; --resume on the inner script means already-extracted
    papers are skipped. Models with `skip_extraction: true` are skipped.
    """
    if getattr(args, "no_extraction", False):
        print("[pipeline] holistic-multi: --no-extraction set; skipping")
        return
    _validate_holistic_args(args, "holistic-multi")
    if not _RUN_EXTRACTION_TOOL.exists():
        sys.exit(f"[pipeline] holistic-multi: tool not found: "
                 f"{_RUN_EXTRACTION_TOOL}")

    cfg = _load_models_config(args.models_config)
    models = cfg.get("models", [])
    if not models:
        sys.exit("[pipeline] holistic-multi: config has empty 'models' list")

    paper_ids = [s.strip() for s in (args.paper_ids or "").split(",") if s.strip()]
    print(f"[pipeline] holistic-multi: {len(models)} model(s); "
          f"paper_ids={paper_ids or 'all'}")

    for m in models:
        if m.get("skip_extraction"):
            print(f"[pipeline] holistic-multi: skip_extraction=true for "
                  f"'{m['name']}' — leaving existing JSONs in place")
            continue
        rc = _run_extraction_for_model(m, args, paper_ids)
        if rc not in (0, -1):
            print(f"[pipeline] holistic-multi: '{m['name']}' returned rc={rc}")


def run_holistic_proof_steps_parse(args) -> None:
    """Tier D parse backend: holistic LLM with proof-step decomposition.

    Variant of run_holistic_multi_parse that adds a `--proof-steps` flag to
    the subprocess invocation. Once a dedicated proof-step prompt / schema
    lands, this function will switch to that prompt template.

    TODO(phase4): pick a tier-D-specific prompt-file by default if
    --prompt-file is unset, and validate the JSON output uses the
    proof-step schema variant.
    """
    if getattr(args, "no_extraction", False):
        print("[pipeline] holistic-proof-steps: --no-extraction set; skipping")
        return
    _validate_holistic_args(args, "holistic-proof-steps")
    if not _RUN_EXTRACTION_TOOL.exists():
        sys.exit(f"[pipeline] holistic-proof-steps: tool not found: "
                 f"{_RUN_EXTRACTION_TOOL}")

    cfg = _load_models_config(args.models_config)
    models = cfg.get("models", [])
    if not models:
        sys.exit("[pipeline] holistic-proof-steps: config has empty 'models' list")

    paper_ids = [s.strip() for s in (args.paper_ids or "").split(",") if s.strip()]
    extra = ["--proof-steps"]  # backend may currently ignore; harmless
    print(f"[pipeline] holistic-proof-steps: {len(models)} model(s); "
          f"paper_ids={paper_ids or 'all'} (proof-step variant)")

    for m in models:
        if m.get("skip_extraction"):
            print(f"[pipeline] holistic-proof-steps: skip_extraction=true for "
                  f"'{m['name']}'")
            continue
        rc = _run_extraction_for_model(m, args, paper_ids, extra_flags=extra)
        if rc not in (0, -1):
            print(f"[pipeline] holistic-proof-steps: '{m['name']}' returned "
                  f"rc={rc}")


# =============================================================================
# Phase 3 — consensus op (Tier B)
# =============================================================================

def op_consensus(args) -> None:
    """Run pairwise consensus_intersect.py vs the reference model.

    Reference model = first entry in --models-config (typically Opus,
    suffix=""). Comparison models = all subsequent entries. For each,
    writes:
      - <base_dir>/agreement_<modelB>_vs_<ref>.csv
      - papers/<pid>/gold_consensus_<modelB>.json
    """
    if not _CONSENSUS_TOOL.exists():
        print(f"[pipeline] consensus: tool not found: {_CONSENSUS_TOOL}")
        return
    if not getattr(args, "base_dir", None):
        print("[pipeline] consensus: --base-dir required")
        return
    if not getattr(args, "models_config", None):
        print("[pipeline] consensus: --models-config required")
        return

    cfg = _load_models_config(args.models_config)
    models = cfg.get("models", [])
    if len(models) < 2:
        print("[pipeline] consensus: need >= 2 models in config; skipping")
        return

    ref = models[0]
    ref_suffix = ref.get("suffix", "")
    ref_name = ref.get("name", "ref")
    print(f"[pipeline] consensus: reference model = '{ref_name}' "
          f"(suffix='{ref_suffix}')")

    base_dir = Path(args.base_dir)
    seen = {ref_suffix}
    for m in models[1:]:
        suffix_b = m.get("suffix", f"_{m['name']}")
        name_b = m["name"]
        if not suffix_b or suffix_b in seen:
            print(f"[pipeline] consensus: skip '{name_b}' (suffix='{suffix_b}')")
            continue
        seen.add(suffix_b)

        out_csv = base_dir / f"agreement_{name_b}_vs_{ref_name}.csv"
        cmd = [sys.executable, str(_CONSENSUS_TOOL),
               "--base-dir", str(base_dir),
               "--suffix-a", ref_suffix,
               "--suffix-b", suffix_b,
               "--out-suffix", f"_consensus_{name_b}",
               "--report-csv", str(out_csv)]
        if getattr(args, "paper_ids", ""):
            cmd += ["--paper-ids", args.paper_ids]
        print(f"[pipeline] consensus: {name_b} vs {ref_name} -> {out_csv.name}")
        try:
            subprocess.run(cmd, check=True, timeout=600)
        except subprocess.CalledProcessError as e:
            print(f"[pipeline] consensus: '{name_b}' failed rc={e.returncode}")
        except Exception as e:
            print(f"[pipeline] consensus: '{name_b}' error: {e}")


# =============================================================================
# Phase 3 — eval op (Tier C: T1 grading vs hand-gold)
# =============================================================================

def op_eval(args) -> None:
    """T1 evaluation: grade extracted JSONs against hand-gold JSONs.

    Delegates to existing src/evaluate_extraction.py CLI on a per-file basis.
    TODO(phase4): once `match_nodes` is lifted into src/graph_alignment.py
    as `match_same_paper` (per docs/graph_compare_design.md Phase 2), call
    that library function in-process and compute precision_recall_f1
    properly with bootstrap CI.
    """
    if not getattr(args, "gold_dir", None):
        print("[pipeline] eval: --gold-dir required")
        return

    print(f"[pipeline] eval: gold={args.gold_dir} pred={args.out_dir}")

    eval_tool = _SRC_DIR / "evaluate_extraction.py"
    if not eval_tool.exists():
        print(f"[pipeline] eval: {eval_tool} not found; nothing to do")
        return
    json_paths = _list_jsons(args.out_dir)
    gold_dir = Path(args.gold_dir)
    n_eval = 0
    for jp in json_paths:
        gold_candidate = gold_dir / jp.name
        if not gold_candidate.exists():
            continue
        cmd = [sys.executable, str(eval_tool),
               "--extracted", str(jp),
               "--gold", str(gold_candidate)]
        try:
            subprocess.run(cmd, check=False, timeout=120)
            n_eval += 1
        except Exception as e:
            print(f"[pipeline] eval: {jp.name} FAILED: {e}")
    print(f"[pipeline] eval: graded {n_eval} pairs")


if __name__ == "__main__":
    main()
