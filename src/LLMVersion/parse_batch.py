#!/usr/bin/env python3
"""
Batch parse: library module for running math_paper_parser across many arXiv
papers, with optional LLM support.

This file is the INTERNAL extraction-engine module. The recommended
user-facing CLI is `src/run_pipeline.py --operations parse ...`, which
invokes this module via subprocess. Direct invocation is still supported
for specialized workflows (evaluation_pipeline.sh, prompt_optimizer.py,
standalone debugging).

Public functions:
    run_batch(...)           - main filter + fetch + parse + save loop
    compute_date_range(...)  - date range helper
    _find_local_tex(...)     - local cache lookup helper

Example direct invocations (legacy, still supported):

  python LLMVersion/parse_batch.py --regex-id "^2501\\.00685" --out-dir .

  python LLMVersion/parse_batch.py \
      --regex-id "^2501\\.00685" \
      --out-dir . \
      --extraction-mode llm

  python LLMVersion/parse_batch.py \
      --regex-id "^2501\\.00685" \
      --out-dir . \
      --extraction-mode both

  python LLMVersion/parse_batch.py \
      --category math.PR \
      --days 30 \
      --top-k 20 \
      --out-dir parsed_math_pr_30d \
      --extraction-mode both

Preferred (unified pipeline):

  python src/run_pipeline.py --operations parse \
      --category math.PR --days 30 --top-k 20 \
      --out-dir parsed_math_pr_30d --extraction-mode both
"""

import argparse
import json
import csv
import glob as globmod
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from config import FULL_PAPERS_DIR

# Import from your parser module
from math_paper_parser import PaperParser
from paper_plot_utils import paper_to_network

# Your arXiv infra
from extract_arxiv_funcs import (
    fetch_arxiv_batch,
    resolve_source_to_tex_local_first,
)


def compute_date_range(
        start: Optional[str],
        end: Optional[str],
        days: Optional[int],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Decide start_date / end_date strings in 'YYYY-MM-DD' format for fetch_arxiv_batch.

    Priority:
      - If start/end explicitly given, use them as-is.
      - Else if days is given, use [today - days, today].
      - Else no date filter.
    """
    if start or end:
        return start, end

    if days is None:
        return None, None

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days)
    end_date = today
    return start_date.isoformat(), end_date.isoformat()


def _find_local_tex(paper_id: str) -> Optional[Tuple[str, str]]:
    """Search for an already-cached .tex file matching paper_id.

    Looks in multiple locations:
      1. FULL_PAPERS_DIR (main data cache, from config.py)
      2. LLMVersion/full_papers/ (gold-standard tex files committed to git)

    Returns (tex_path, versioned_id) or None.
    """
    import os
    search_dirs = [FULL_PAPERS_DIR]
    # Also search the git-committed gold-standard tex files in LLMVersion/
    _llmv_papers = os.path.join(os.path.dirname(os.path.abspath(__file__)), "full_papers")
    if os.path.isdir(_llmv_papers) and _llmv_papers != FULL_PAPERS_DIR:
        search_dirs.append(_llmv_papers)

    for search_dir in search_dirs:
        pattern = os.path.join(search_dir, "**", f"{paper_id}*.tex")
        matches = globmod.glob(pattern, recursive=True)
        if matches:
            tex_path = matches[0]
            versioned_id = Path(tex_path).stem
            return tex_path, versioned_id
    return None


def run_batch(
        start_date: Optional[str],
        end_date: Optional[str],
        category: Optional[str],
        regex_id: Optional[str],
        top_k: Optional[int],
        out_dir: Path,
        draw_graphs: bool,
        verbose: bool,
        extraction_mode: str = "manual",
        llm_model: str = "claude-sonnet-4-20250514",
        llm_chunk_chars: int = 30000,
        llm_provider: str = "anthropic",
        prompt_file: Optional[str] = None,
        structure_types: Optional[list] = None,
) -> None:
    print(
        f"[INFO] Fetching arXiv IDs via fetch_arxiv_batch "
        f"(start={start_date}, end={end_date}, category={category}, regex_id={regex_id})"
    )

    if extraction_mode in ("llm", "both"):
        print(f"[INFO] LLM extraction enabled (mode={extraction_mode}, model={llm_model})")

    # ------------------------------------------------------------
    # 1. TRY LOCAL .TEX FILES FIRST (avoids arXiv API entirely)
    # ------------------------------------------------------------
    # If regex_id looks like a specific paper ID (e.g. "^1210.4634"),
    # check if we already have the .tex file locally.
    local_items = []
    if regex_id:
        import re
        # Strip regex anchors to extract plain paper ID
        plain_id = regex_id.lstrip('^').rstrip('$')
        # Check if it's a simple paper ID (not a complex regex)
        if re.fullmatch(r'[\d.]+(?:v\d+)?', plain_id):
            local = _find_local_tex(plain_id)
            if local:
                tex_path, versioned_id = local
                base_id = versioned_id.split("v")[0]
                local_items = [(base_id, tex_path, versioned_id)]
                print(f"[INFO] Found local .tex for {plain_id}: {tex_path}")

    if local_items:
        # Skip arXiv API — process local files directly
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Will process {len(local_items)} papers from local .tex files.")

        for i, (base_id, tex_path, versioned_id) in enumerate(local_items, start=1):
            print(f"\n[INFO] ({i}/{len(local_items)}) Processing {base_id}")
            print(f"[INFO]   Resolved source -> {tex_path}")

            try:
                parser = PaperParser(
                    paper_id=versioned_id,
                    extraction_mode=extraction_mode,
                    llm_model=llm_model,
                    llm_chunk_chars=llm_chunk_chars,
                    llm_provider=llm_provider,
                    custom_prompt_file=prompt_file,
                    structure_types=structure_types,
                )
                graph = parser.parse_file(tex_path)
            except Exception as e:
                print(f"[WARN]   parse_file failed for {base_id}: {e}")
                continue

            # Save JSON into json/ subdir so definitions_from_json_to_csv.py glob finds it
            if extraction_mode == "manual":
                suffix = "manual"
            elif extraction_mode == "llm":
                suffix = llm_provider
            else:
                suffix = f"{llm_provider}+manual"
            json_dir = out_dir / "json"
            json_dir.mkdir(parents=True, exist_ok=True)
            json_name = f"{versioned_id}_{suffix}.json"
            json_path = json_dir / json_name
            json_path.write_text(json.dumps(graph.to_unified_dict(), indent=2), encoding="utf-8")
            print(f"[OK]   Saved {json_path}")

            if draw_graphs:
                try:
                    png_path = out_dir / f"{versioned_id}_graph.png"
                    paper_to_network(graph, save_to_file=str(png_path))
                    print(f"[INFO]   Wrote {png_path}")
                except Exception as e:
                    print(f"[WARN]   Graph failed for {base_id}: {e}")
        return

    # ------------------------------------------------------------
    # 1b. FETCH METADATA via arXiv API (fallback)
    # ------------------------------------------------------------
    # Pass top_k with a small headroom factor so the downstream sort-by-date
    # in run_batch has some wiggle room. Sorting by ID (done inside
    # fetch_arxiv_batch) is a close approximation of "newest first" but not
    # identical to sorting by the official 'published' date, so we pull
    # ~3x top_k candidates here and let run_batch pick the true top_k
    # after it has real metadata.
    _prefetch_k = (top_k * 3) if (top_k and top_k > 0) else None
    data = fetch_arxiv_batch(
        regex_id=regex_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        formats="metadata",
        output_dir=None,
        verbose=verbose,
        top_k=_prefetch_k,
    )

    if verbose:
        print(f"[DEBUG] fetch_arxiv_batch returned {len(data)} versioned IDs")

    if not data:
        print("[WARN] No papers matched the filters. Nothing to do.")
        return

    # ------------------------------------------------------------
    # 2. COLLAPSE VERSIONED → BASE IDs (latest metadata kept)
    # ------------------------------------------------------------
    base_to_meta: Dict[str, Dict[str, Any]] = {}
    for vid, entry in data.items():
        base_id = vid.split("v")[0]
        md = entry.get("metadata", entry)
        base_to_meta[base_id] = md

    print(f"[INFO] Collapsed to {len(base_to_meta)} unique base IDs.")

    # ------------------------------------------------------------
    # 3. SORT BY DATE (published / created)
    # ------------------------------------------------------------
    def extract_date(md: dict) -> datetime:
        for key in ("published", "created"):
            if md.get(key):
                try:
                    return datetime.strptime(str(md[key])[:10], "%Y-%m-%d")
                except Exception:
                    pass
        return datetime(1970, 1, 1)

    items = list(base_to_meta.items())
    items.sort(key=lambda kv: extract_date(kv[1]), reverse=True)

    if top_k and top_k > 0:
        items = items[:top_k]

    print(f"[INFO] Will process {len(items)} base IDs after top_k filter.")

    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # 4. MAIN LOOP: resolve tex → parse → save JSON/PNG
    # ------------------------------------------------------------
    for i, (base_id, md) in enumerate(items, start=1):
        print(f"\n[INFO] ({i}/{len(items)}) Processing {base_id}")

        # ---------- STEP 1: GET LOCAL OR FETCHED TEX ----------
        try:
            tex_path, versioned_id = resolve_source_to_tex_local_first(
                base_id=base_id,
                meta=md,
                full_papers_dir=out_dir,
                verbose=verbose,
            )
            print(f"[INFO]   Resolved source -> {tex_path}")
        except Exception as e:
            status = f"FETCH_ERROR: {e}"
            print(f"[WARN]   Failed to fetch/resolve source for {base_id}: {e}")
            # log fetch failure and continue to next paper
            with open(out_dir / "status_log.csv", "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([base_id, "", status])
            continue

        # ---------- STEP 2: PARSE WITH LLM OPTIONS ----------
        try:
            parser = PaperParser(
                paper_id=versioned_id,
                extraction_mode=extraction_mode,
                llm_model=llm_model,
                llm_chunk_chars=llm_chunk_chars,
                llm_provider=llm_provider,
                custom_prompt_file=prompt_file,
                structure_types=structure_types,
            )
            graph = parser.parse_file(tex_path)
            status = "OK"
        except Exception as e:
            status = f"PARSE_ERROR: {e}"
            print(f"[WARN]   Failed to parse {base_id}: {e}")
            with open(out_dir / "status_log.csv", "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([base_id, versioned_id, status])
            continue

        # If we got here, both fetch + parse succeeded, log success
        with open(out_dir / "status_log.csv", "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([base_id, versioned_id, status])

        # ---------- STEP 3: DETERMINE OUTPUT DIR (same YYYY/MM/DD as metadata) ----------
        pub_raw = md.get("published") or md.get("created")
        if pub_raw:
            date_str = str(pub_raw)[:10]
            try:
                year, month, day = date_str.split("-")
            except Exception:
                year, month, day = ("unknown", "unknown", "unknown")
        else:
            year, month, day = ("unknown", "unknown", "unknown")

        base_day_dir = out_dir / year / month / day

        # ---------- STEP 4: WRITE JSON ----------
        json_dir = base_day_dir / "json"
        json_dir.mkdir(parents=True, exist_ok=True)

        # Determine JSON suffix
        if extraction_mode == "manual":
            suffix = "manual"
        elif extraction_mode == "llm":
            suffix = llm_model.replace('/', '-')  # sanitize slashes for filename
        elif extraction_mode == "both":
            suffix = f"{llm_model}+manual"

        json_filename = f"{versioned_id}_{suffix}.json"
        json_path = json_dir / json_filename

        json_path.write_text(json.dumps(graph.to_unified_dict(), indent=2), encoding="utf-8")
        print(f"[OK]   Saved graph for {base_id} -> {json_path}")

        # ---------- STEP 5: DRAW PNG ----------
        if draw_graphs:
            png_dir = base_day_dir / "png"
            png_dir.mkdir(parents=True, exist_ok=True)
            out_png = png_dir / f"{versioned_id}.png"

            try:
                paper_to_network(
                    paper=graph,
                    out_png=str(out_png),
                    node_label_attr="label",  # or "id" / "name"
                    include_kinds=[
                        "theorem",
                        "lemma",
                        "proposition",
                        "corollary",
                        "definition",
                        "proof",
                        "proposition",
                        "conjecture",
                        "claim",
                        "problem",
                    ],
                    figsize=(16, 10),
                    include_relation_types=None,
                )
                print(f"[OK]   Saved PNG for {base_id} -> {out_png}")
            except Exception as e:
                print(f"[WARN] Could not draw network for {base_id}: {e}")

    print("[INFO] Done.")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Batch-run math_paper_parser on many arXiv papers with optional LLM support."
        )
    )

    parser.add_argument(
        "--start",
        dest="start_date",
        type=str,
        default=None,
        help="Start date YYYY-MM-DD (submission date).",
    )
    parser.add_argument(
        "--end",
        dest="end_date",
        type=str,
        default=None,
        help="End date YYYY-MM-DD (submission date).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=(
            "If start/end not given: use last N days as [today-N, today]. "
            "Ignored if --start or --end is provided."
        ),
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="ArXiv category, e.g. math.PR, math.DG. If omitted, no category filter.",
    )
    parser.add_argument(
        "--regex-id",
        type=str,
        default=None,
        help='Optional regex filter on base IDs, e.g. "^2501\\\\.00685".',
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Process at most this many base IDs after filtering. Use <=0 for no limit.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=FULL_PAPERS_DIR,
        help=(
            "Root directory for outputs. "
            "Defaults to FULL_PAPERS_DIR from config.py."
        ),
    )
    parser.add_argument(
        "--draw-graphs",
        action="store_true",
        help="If set, also draw a network PNG for each parsed paper.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose prints from fetch_arxiv_batch and ID filtering.",
    )

    # LLM-related options
    parser.add_argument(
        "--extraction-mode",
        type=str,
        default="manual",
        choices=["manual", "llm", "both"],
        help=(
            "Extraction mode for all structure types: "
            "'manual' (pattern-based, default), "
            "'llm' (LLM API), "
            "'both' (combines both methods)."
        ),
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Anthropic model to use for LLM extraction (if enabled).",
    )
    parser.add_argument(
        "--llm-provider",
        type=str,
        default="anthropic",
        choices=["anthropic", "openai", "huggingface"],
        help="LLM provider: 'anthropic' (Claude) or 'openai' (GPT) or huggingface",
    )
    parser.add_argument(
        "--llm-chunk-chars",
        type=int,
        default=30000,
        help="Max characters per chunk when using LLM extraction.",
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        default=None,
        help="Path to custom prompt template file (use {latex_chunk} as placeholder)",
    )
    parser.add_argument(
        "--structure-types",
        type=str,
        default="definition",
        help="Comma-separated structure types to extract via LLM (default: definition)",
    )

    args = parser.parse_args()
    print(f"[DEBUG] Parsed args: {args}")

    start_date, end_date = compute_date_range(
        args.start_date,
        args.end_date,
        args.days,
    )

    top_k = args.top_k if args.top_k and args.top_k > 0 else None

    structure_types = [s.strip() for s in args.structure_types.split(",")]

    run_batch(
        start_date=start_date,
        end_date=end_date,
        category=args.category,
        regex_id=args.regex_id,
        top_k=top_k,
        out_dir=Path(args.out_dir),
        draw_graphs=args.draw_graphs,
        verbose=args.verbose,
        extraction_mode=args.extraction_mode,
        llm_model=args.llm_model,
        llm_chunk_chars=args.llm_chunk_chars,
        llm_provider=args.llm_provider,
        prompt_file=args.prompt_file,
        structure_types=structure_types,
    )

    print("[INFO] Done.")


if __name__ == "__main__":
    main()
