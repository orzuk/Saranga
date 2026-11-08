#!/usr/bin/env python3
"""
Batch parse: library module for running math_paper_parser across many arXiv
papers, with optional LLM support.

This file is the INTERNAL extraction-engine module. The recommended
user-facing CLI is `src/run_pipeline.py --operations parse ...`, which
invokes this module via subprocess. Direct invocation is still supported
for standalone debugging.

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

import re
import argparse
import os
import sys
import json
import csv
import glob as globmod
import signal
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple


class _ParseTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _ParseTimeout

from config import FULL_PAPERS_DIR
# src/provenance.py: src/ goes AFTER LLMVersion/ on the path, so LLMVersion's own modules
# (config, math_classes, ...) still win; run_pipeline runs this script with cwd=LLMVersion/.
sys.path.append(str(Path(__file__).resolve().parents[1]))
from provenance import stamp

# Import from your parser module
from math_paper_parser import PaperParser
from latex_facts import find_main_tex
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


def _find_local_tex(paper_id: str, tex_dir: str = None) -> Optional[Tuple[str, str]]:
    """Search for a cached .tex file matching paper_id in a single directory.

    Args:
        paper_id: arxiv paper ID (e.g. '1210.4634' or '1210.4634v1')
        tex_dir:  directory to search (default: FULL_PAPERS_DIR from config)

    Returns (tex_path, versioned_id) or None.
    """
    import os
    search_dir = tex_dir or FULL_PAPERS_DIR
    pattern = os.path.join(search_dir, "**", f"{paper_id}*.tex")
    matches = globmod.glob(pattern, recursive=True)
    if not matches:
        return None
    tex_path = matches[0]
    versioned_id = Path(tex_path).stem
    return tex_path, versioned_id


def run_batch(
        start_date: Optional[str],
        end_date: Optional[str],
        category: Optional[str],
        regex_id: Optional[str],
        top_k: Optional[int],
        out_dir: Path,
        draw_graphs: bool,
        verbose: bool,
        extraction_mode: str = "rules",
        llm_model: str = "claude-sonnet-4-6",
        llm_chunk_chars: int = 30000,
        llm_provider: str = "anthropic",
        tex_dir: Optional[str] = None,
        rules_dir: Optional[str] = None,
        prompt_file: Optional[str] = None,
        structure_types: Optional[list] = None,
        safeguard_timeout: Optional[int] = None,
        edge_model: Optional[str] = None,
) -> None:
    edges = None
    if edge_model:                                  # opt-in learned definition -> user edges (alg3/edges.py)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "alg3"))
        import edges as _edges                      # noqa: E402
        edges = (_edges, _edges.EdgeModel(edge_model))
        print(f"[INFO] Learned definition edges: {edge_model}")
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
            local = _find_local_tex(plain_id, tex_dir=tex_dir)
            if local:
                tex_path, versioned_id = local
                base_id = re.sub(r"v\d+$", "", versioned_id)
                local_items = [(base_id, tex_path, versioned_id)]
                print(f"[INFO] Found local .tex for {plain_id}: {tex_path}")

    # ------------------------------------------------------------
    # 1a. ENUMERATE ALL LOCAL .TEX FILES (batch local mode)
    # ------------------------------------------------------------
    # When --tex-dir is given without a specific regex_id, discover
    # all .tex files under tex_dir and parse them directly.
    if tex_dir and not local_items:
        import re as _re
        _ARXIV_RE = _re.compile(r'(\d{4}\.\d{4,5})(v\d+)?')
        tex_dir_path = Path(tex_dir)
        all_tex = sorted(tex_dir_path.rglob("*.tex"))
        # Group .tex files by paper directory.  The download layout is
        # .../YYYY/MM/DD/<paper_id>/... where <paper_id> is the arXiv id, but
        # a dir may hold companion .tex files (main.tex, intro.tex, ...).
        # Two things matter here:
        #   (1) pick the canonical MAIN .tex to parse (not a fragment like
        #       abstract.tex that happens to sort first), and
        #   (2) name the output by the arXiv id taken from the PARENT DIR,
        #       NOT the .tex filename.  Otherwise papers whose main file is
        #       generically named (main.tex, intro.tex, ...) all collapse to
        #       the same output name (main_rules.json, ...) and silently
        #       overwrite each other — the cause of the missing-paper gap in
        #       cs.* categories where main.tex naming is common.
        dir_to_texs: Dict[Path, list] = {}
        for tp in all_tex:
            dir_to_texs.setdefault(tp.parent, []).append(tp)

        for parent, texs in dir_to_texs.items():
            tp = find_main_tex(parent, texs)
            # Derive the arXiv id from the PARENT DIR name first (canonical
            # in the download layout); fall back to the file stem for
            # non-arXiv layouts (e.g. a lone paper1.tex under --tex-dir).
            m = _ARXIV_RE.match(parent.name) or _ARXIV_RE.match(tp.stem)
            if m:
                versioned_id = m.group(0)   # e.g. 1005.2714v2
                base_id = m.group(1)
            else:
                versioned_id = tp.stem
                base_id = tp.stem
            local_items.append((base_id, str(tp), versioned_id))
        # Deterministic processing order (by tex path), as before.
        local_items.sort(key=lambda it: it[1])
        print(f"[INFO] Local tex-dir mode: found {len(local_items)} .tex files under {tex_dir}")
        # SARANGA_SHARD=k/N: parse only every N-th paper, starting at k, so one
        # category can be split over N parallel cluster jobs (each paper's
        # JSON is its own file, so the shards never write the same output).
        _shard = os.environ.get("SARANGA_SHARD", "")
        if _shard:
            _k, _n = (int(x) for x in _shard.split("/"))
            local_items = local_items[_k::_n]
            print(f"[INFO] shard {_k}/{_n}: {len(local_items)} papers")
            if not local_items:
                print("[INFO] empty shard: nothing to parse")
                sys.exit(0)

    suffix = "rules" if extraction_mode == "rules" else \
        llm_model.replace("/", "-") + ("+rules" if extraction_mode == "both" else "")

    def process(base_id, versioned_id, tex_path, day_dir) -> None:
        """Parse one paper (under the safeguard timeout) into day_dir/json (and day_dir/png);
        one status row per paper in out_dir/status_log.csv."""
        try:
            if safeguard_timeout:
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(safeguard_timeout)
            graph = PaperParser(paper_id=versioned_id, extraction_mode=extraction_mode, llm_model=llm_model,
                                llm_chunk_chars=llm_chunk_chars, llm_provider=llm_provider,
                                custom_prompt_file=prompt_file, structure_types=structure_types,
                                rules_dir=rules_dir).parse_file(tex_path)
            d = graph.to_unified_dict()
            if edges:                                           # under the same timeout
                edges[0].add_edges(d, edges[1], tex=Path(tex_path).read_text(encoding="utf-8", errors="ignore"))
            try:                                                # what made this JSON, and the paper's references
                stamp(d, tex_path, extractor=extraction_mode, tool="parse_batch",
                      model=llm_model if extraction_mode != "rules" else None,
                      prompt_file=Path(prompt_file).name if prompt_file and extraction_mode != "rules" else None,
                      edge_model=Path(edge_model).name if edge_model else None, rules_dir=rules_dir)
            except Exception as e:                              # noqa: BLE001  (never fail a paper over metadata)
                d.setdefault("metadata", {})["provenance_error"] = str(e)
            status = "OK"
        except _ParseTimeout:
            graph, status = None, f"TIMEOUT: exceeded {safeguard_timeout}s"
        except Exception as e:                                  # noqa: BLE001  (one bad paper, not the batch)
            graph, status = None, f"PARSE_ERROR: {e}"
        finally:
            if safeguard_timeout:
                signal.alarm(0)
        with open(out_dir / "status_log.csv", "a", newline="") as f:
            csv.writer(f).writerow([base_id, versioned_id, status])
        if graph is None:
            print(f"[WARN]   {base_id}: {status}")
            return
        (day_dir / "json").mkdir(parents=True, exist_ok=True)
        json_path = day_dir / "json" / f"{versioned_id}_{suffix}.json"
        json_path.write_text(json.dumps(d, indent=2), encoding="utf-8")
        print(f"[OK]   Saved {json_path}")
        if draw_graphs:
            (day_dir / "png").mkdir(parents=True, exist_ok=True)
            try:
                paper_to_network(graph, out_png=str(day_dir / "png" / f"{versioned_id}.png"), figsize=(16, 10),
                                 include_kinds=["theorem", "lemma", "proposition", "corollary", "definition",
                                                "proof", "conjecture", "claim", "problem"])
            except Exception as e:                              # noqa: BLE001
                print(f"[WARN] Could not draw network for {base_id}: {e}")

    if local_items:
        # Skip arXiv API — process local files directly
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] Will process {len(local_items)} papers from local .tex files.")

        for i, (base_id, tex_path, versioned_id) in enumerate(local_items, start=1):
            print(f"\n[INFO] ({i}/{len(local_items)}) Processing {base_id} -> {tex_path}")
            process(base_id, versioned_id, tex_path, out_dir)
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
        base_id = re.sub(r"v\d+$", "", vid)
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

        day = (str(md.get("published") or md.get("created") or "")[:10].split("-") + ["unknown"] * 3)[:3]
        process(base_id, versioned_id, tex_path, out_dir.joinpath(*(d or "unknown" for d in day)))

    print("[INFO] Done.")


def main():
    # Deterministic output: fix str hashing, as src/config.py's
    # ensure_deterministic_hashing does (inlined: LLMVersion/config.py shadows it).
    import os, sys
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable] + sys.argv)
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
        default="rules",
        choices=["rules", "llm", "both"],
        help=(
            "Extraction mode for all structure types: "
            "'rules' (pattern-based rule extractor, default; output suffix _rules.json), "
            "'llm' (LLM API; output suffix _<provider>.json), "
            "'both' (combines both)."
        ),
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="claude-sonnet-4-6",
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
    parser.add_argument(
        "--rules-dir",
        type=str,
        default=None,
        help=(
            "Directory holding the distilled rule set to use. Point it at an "
            "extractor directory (e.g. extractors/rules/<id>) or any dir "
            "containing <type>_eval/distilled_rules.py. Default: src/LLMVersion/, "
            "i.e. whatever the production symlinks currently point at."
        ),
    )
    parser.add_argument(
        "--edge-model",
        type=str,
        default=None,
        help=(
            "Optional: a learned edge model (extractors/edges/<id>, trained by alg3/edges.py) "
            "applied after parsing: it may drop parser edges (its filter) and adds definition -> "
            "user edges. Default: off, i.e. only the parser's own edges."
        ),
    )
    parser.add_argument(
        "--tex-dir",
        type=str,
        default=None,
        help="Directory to search for local .tex files (default: FULL_PAPERS_DIR "
             "from config). Use this to point at a non-standard location, e.g. "
             "src/LLMVersion/full_papers/ for Author's gold-standard papers.",
    )
    parser.add_argument(
        "--safeguard",
        type=int,
        default=None,
        const=90,
        nargs="?",
        metavar="SECONDS",
        help="Per-paper parse timeout in seconds. Skips papers that exceed it. "
             "Defaults to 90s if flag is given without a value.",
    )

    parser.add_argument(
        "--no-regex-guard",
        action="store_true",
        help="Run a released rule set's regexes without rule_guard's per-match timer (about a third "
             "faster, same output); bound each paper with --safeguard instead.",
    )

    args = parser.parse_args()
    print(f"[DEBUG] Parsed args: {args}")
    if args.no_regex_guard:
        from math_paper_parser import PaperParser as _PP
        _PP.REGEX_GUARD = False

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
        tex_dir=args.tex_dir,
        rules_dir=args.rules_dir,
        safeguard_timeout=args.safeguard,
        edge_model=args.edge_model,
    )

    print("[INFO] Done.")


if __name__ == "__main__":
    main()
