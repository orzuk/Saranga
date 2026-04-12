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
    """Run Yaron's extractor (LLMVersion/parse_batch.py) as a subprocess.

    Subprocess isolation keeps LLMVersion's math_classes namespace from
    colliding with src/'s math_classes namespace in the same Python process.
    """
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

            # Suppress noisy library output (e.g. "Index has N searchable terms")
            # by capturing stdout during draw_dag / generate_interactive_html calls
            png_path = jp.with_suffix(".png")
            if not args.html_only:
                with contextlib.redirect_stdout(io.StringIO()):
                    draw_dag(nodes, edges, str(png_path), metadata=metadata,
                             resolution=args.resolution)
                what.append("PNG")

            if args.html or args.html_only:
                svg_only = str(png_path).replace(".png", "_nolegend.svg")
                tmp_png = svg_only.replace(".svg", ".png")
                with contextlib.redirect_stdout(io.StringIO()):
                    draw_dag(nodes, edges, tmp_png, metadata=metadata,
                             resolution=args.resolution, show_legend=False)
                    html_path = jp.with_suffix(".html")
                    generate_interactive_html(data, svg_only, str(html_path))
                for tmp in [svg_only, tmp_png]:
                    if os.path.exists(tmp):
                        os.remove(tmp)
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
        from link_to_foundation import build_foundation_index, link_paper, _build_automaton
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
    n_linked = 0
    total_matches = 0

    for i, jp in enumerate(json_paths, start=1):
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)

            nodes = data.get("nodes", [])
            edges = data.get("edges", [])

            # Remove any previous foundation edges (re-linking is idempotent)
            edges = [e for e in edges
                     if e.get("type") not in ("grounded_to", "mentions_concept")]

            # Run foundation matching (Aho-Corasick if available, else regex)
            matches = link_paper(nodes, index, min_term_len=5,
                                 automaton=automaton, term_map=term_map)

            # Add matches as grounded_to edges
            seen = set()  # deduplicate (node_id, foundation_name)
            for m in matches:
                key = (m["node_id"], m["foundation_name"])
                if key in seen:
                    continue
                seen.add(key)
                edges.append({
                    "source": m["foundation_name"],
                    "target": m["node_id"],
                    "type": "grounded_to",
                    "note": f"matched term: {m['matched_term']}",
                })

            n_new = len(seen)
            if n_new > 0:
                n_linked += 1
                total_matches += n_new

            # Write back in-place
            data["edges"] = edges
            with open(jp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            if args.verbose:
                paper_id = jp.stem.replace("_manual", "").replace("_claude", "")
                print(f"[pipeline] link: {paper_id} [{i}/{n_total}] "
                      f"{n_new} foundation links added")

        except Exception as e:
            print(f"[pipeline] link: {jp.name}: FAILED: {e}")

    print(f"[pipeline] link: {n_linked}/{n_total} papers linked, "
          f"{total_matches} total foundation edges added")


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
                                "claim,conjecture,problem,proof,algorithm,equation",
                        help="Comma-separated structure types to extract.")
    parser.add_argument("--tex-dir", type=str, default=None,
                        help="Directory to search for local .tex files instead of "
                             "the default FULL_PAPERS_DIR from config. Useful when "
                             "tex sources live in a non-standard location.")

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


if __name__ == "__main__":
    main()
