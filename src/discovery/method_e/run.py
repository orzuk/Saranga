"""Method E orchestrator CLI.

Chains the phases:

    Phase 1L: build problems index (open_problem + conjecture)
    Phase 1R: build theorems index (theorem/lemma/prop/corollary)
    Phase 1.5: dedup theorems (cluster restatements; canonical = earliest)
    Phase 2a: fetch S2 citation graph (skip if --no-citations)
    Phase 2b: retrieve candidate pairs (enforces theorem.year >= problem.year)
    Phase 2c: LLM-as-judge pass (Sonnet by default; --dry-run for no spend)
    Phase 3: export triage CSV

Year handling: with default `cutoff_year=2018`, problems are indexed at
year <= 2017 and theorems at year >= 2018 (hard cutoff). Pass `--no-cutoff`
to index all years and let Phase 2b alone enforce theorem.year >= problem.year
(catches e.g. a 2014 theorem resolving a 2012 problem, which the hard
cutoff misses).

Each phase is idempotent: outputs are checked; if present, skipped unless
--force. Frozen config.yaml is written first.

Typical invocations:

    # smoke test (no LLM, no S2)
    python -m method_e.run all --categories math_CO,cs_CC --dry-run \\
        --no-citations --run-dir /tmp/runs/smoke

    # full local run on a sample with S2 + Sonnet judge
    python -m method_e.run all --categories math_CO --run-dir RUN \\
        --s2-api-key $S2_API_KEY

    # individual phases
    python -m method_e.run index   --run-dir RUN --categories math_CO
    python -m method_e.run dedup   --run-dir RUN
    python -m method_e.run cite    --run-dir RUN --s2-api-key $S2_API_KEY
    python -m method_e.run retrieve --run-dir RUN
    python -m method_e.run judge    --run-dir RUN --model sonnet
    python -m method_e.run export   --run-dir RUN
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMON = _HERE.parent / "common"
_SRC = _HERE.parent.parent
# Insert order matters: each insert(0,...) prepends, so the final search
# order is the REVERSE of the iteration order. We want _SRC at the FRONT so
# `import config` resolves to saranga src/config.py (not to a method_e-local
# module).
for _p in (_HERE, _COMMON, _SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from config import DATA_DIR  # noqa: E402 — saranga src/config.py
from me_config import MethodEConfig  # noqa: E402 — local method_e config
from build_node_index import build_node_index  # noqa: E402
from node_dedup import cluster_index  # noqa: E402
from retrieve_pairs import retrieve  # noqa: E402
from judge import judge_candidates  # noqa: E402
from export_triage import export  # noqa: E402
from export_candidates import export as export_candidates_csv  # noqa: E402


_DEFAULT_RUNS_ROOT = DATA_DIR / "discovery" / "method_e" / "runs"


def _default_run_dir() -> Path:
    return _DEFAULT_RUNS_ROOT / datetime.now().strftime("%Y-%m-%d_%H%M")


def _paths(run_dir: Path) -> dict:
    return {
        "config":          run_dir / "config.yaml",
        "problems":        run_dir / "problems.jsonl",
        "theorems":        run_dir / "theorems.jsonl",
        "dedup":           run_dir / "dedup_clusters.jsonl",
        "citations":       run_dir / "s2_citations.sqlite",
        "candidates":      run_dir / "candidates.jsonl",
        "candidates_csv":  run_dir / "candidates_ranked.csv",
        "judged":          run_dir / "judged_candidates.jsonl",
        "judge_cache":     run_dir / "judge_cache.sqlite",
        "triage":          run_dir / "triage_cases.csv",
        "triage_all":      run_dir / "triage_all.csv",
        "stats":           run_dir / "stats.json",
    }


def _exists_nonempty(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 0


def _write_config(cfg: MethodEConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cfg.to_yaml(), encoding="utf-8")


# ── Per-phase wrappers ───────────────────────────────────────────────────────

def phase_index(cfg: MethodEConfig, P: dict, force: bool) -> None:
    # When cutoff_year is None we index all years (Option B); when it's an
    # integer we apply the hard cutoff at index build time (Option A). Either
    # way, retrieve_pairs enforces theorem.year >= problem.year at scoring
    # time, so Option B doesn't lose the temporal-direction guarantee.
    problems_year_max = (cfg.cutoff_year - 1) if cfg.cutoff_year is not None else None
    theorems_year_min = cfg.cutoff_year if cfg.cutoff_year is not None else None

    if force or not _exists_nonempty(P["problems"]):
        print(f"\n=== Phase 1L: build problems index "
              f"(year_max={problems_year_max}) ===")
        build_node_index(
            types=cfg.problem_types,
            year_max=problems_year_max,
            categories_in=cfg.categories,
            out=P["problems"],
        )
    else:
        print(f"[skip] problems.jsonl exists")
    if force or not _exists_nonempty(P["theorems"]):
        print(f"\n=== Phase 1R: build theorems index "
              f"(year_min={theorems_year_min}) ===")
        build_node_index(
            types=cfg.theorem_types,
            year_min=theorems_year_min,
            categories_in=cfg.categories,
            out=P["theorems"],
        )
    else:
        print(f"[skip] theorems.jsonl exists")


def phase_dedup(cfg: MethodEConfig, P: dict, force: bool) -> None:
    if not force and _exists_nonempty(P["dedup"]):
        print(f"[skip] dedup_clusters.jsonl exists"); return
    print(f"\n=== Phase 1.5: dedup theorems ===")
    cluster_index(
        index_path=P["theorems"],
        out_path=P["dedup"],
        statement_threshold=cfg.dedup_statement_threshold,
        foundation_threshold=cfg.dedup_foundation_threshold,
    )


def phase_cite(P: dict, *, api_key: str | None, delay: float | None,
               force: bool) -> None:
    if not force and _exists_nonempty(P["citations"]):
        print(f"[skip] s2_citations.sqlite exists"); return
    print(f"\n=== Phase 2a: fetch S2 citation graph ===")
    from citation_graph import S2CitationGraph  # noqa: E402
    g = S2CitationGraph(P["citations"], api_key=api_key, delay=delay)
    ids: list[str] = []
    seen = set()
    for src in (P["problems"], P["theorems"]):
        if not src.exists():
            continue
        with src.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                pid = row.get("paper_id")
                if pid and pid not in seen:
                    ids.append(pid); seen.add(pid)
    print(f"[cite] fetching {len(ids)} unique papers")
    g.fetch_batch(ids)
    print(f"[cite] cache stats: {g.stats()}")
    g.close()


def phase_retrieve(cfg: MethodEConfig, P: dict, *,
                   use_citations: bool, force: bool) -> None:
    if force or not _exists_nonempty(P["candidates"]):
        print(f"\n=== Phase 2b: retrieve candidate pairs ===")
        retrieve(
            problems_path=P["problems"],
            theorems_path=P["theorems"],
            out_path=P["candidates"],
            dedup_path=P["dedup"] if P["dedup"].exists() else None,
            citations_sqlite=P["citations"] if use_citations and P["citations"].exists() else None,
            config=cfg,
        )
    else:
        print(f"[skip] candidates.jsonl exists")
    # Always (re)emit the ranked CSV — even if candidates.jsonl was skipped,
    # the CSV may be missing from older runs. Idempotent.
    if force or not _exists_nonempty(P["candidates_csv"]):
        print(f"=== Phase 2b.5: export candidates_ranked.csv ===")
        export_candidates_csv(
            candidates_path=P["candidates"],
            out_csv=P["candidates_csv"],
        )
    else:
        print(f"[skip] candidates_ranked.csv exists")


def phase_judge(cfg: MethodEConfig, P: dict, *,
                model: str, dry_run: bool, max_candidates: int | None,
                force: bool) -> None:
    if not force and _exists_nonempty(P["judged"]):
        print(f"[skip] judged_candidates.jsonl exists"); return
    print(f"\n=== Phase 2c: LLM-as-judge ===")
    judge_candidates(
        candidates_path=P["candidates"],
        out_path=P["judged"],
        cache_path=P["judge_cache"],
        model=model,
        prompt_version=cfg.judge_prompt_version,
        dry_run=dry_run,
        max_candidates=max_candidates,
    )


def phase_export(P: dict, force: bool) -> None:
    print(f"\n=== Phase 3: export judge CSVs ===")
    if force or not _exists_nonempty(P["triage"]):
        export(judged_path=P["judged"], out_csv=P["triage"],
               include_verdicts=["YES", "MAYBE"])
    else:
        print(f"[skip] triage_cases.csv exists")
    if force or not _exists_nonempty(P["triage_all"]):
        export(judged_path=P["judged"], out_csv=P["triage_all"],
               include_verdicts=["YES", "MAYBE", "NO"])
    else:
        print(f"[skip] triage_all.csv exists")


# ── CLI ─────────────────────────────────────────────────────────────────────

def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["all", "index", "dedup", "cite",
                                       "retrieve", "judge", "export"])
    ap.add_argument("--run-dir", default=None,
                    help="Run directory (default: $DATA/discovery/method_e/runs/$DATE)")
    ap.add_argument("--force", action="store_true",
                    help="Recompute even if output exists")

    # Corpus / config knobs
    ap.add_argument("--categories", default=None,
                    help="Comma-sep categories (e.g. math_CO,cs_CC)")
    ap.add_argument("--cutoff-year", type=int, default=None,
                    help="Problems posed pre-cutoff; theorems published cutoff+ "
                         "(hard cutoff at index build time). Default 2018 from "
                         "MethodEConfig.")
    ap.add_argument("--no-cutoff", action="store_true",
                    help="Disable hard year cutoff at index build time. All "
                         "problems and theorems are indexed regardless of year; "
                         "the temporal constraint theorem.year >= problem.year "
                         "is enforced only at retrieval time (Option B / "
                         "year-as-attribute design).")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--score-threshold", type=float, default=None)

    # Citation graph
    ap.add_argument("--s2-api-key", default=None,
                    help="Semantic Scholar API key (or set S2_API_KEY env var)")
    ap.add_argument("--s2-delay", type=float, default=None,
                    help="Per-request delay; default 0.15 (with key) / 2.0 (no key)")
    ap.add_argument("--no-citations", action="store_true",
                    help="Skip the S2 fetch + don't use citation filter")

    # Judge
    ap.add_argument("--model", default=None,
                    help="Override judge_model (e.g. sonnet, opus, gpt4o)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't actually call the LLM judge")
    ap.add_argument("--max-candidates", type=int, default=None,
                    help="Cap on candidates passed to judge (debug/smoke)")
    return ap


def main():
    args = _parser().parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else _default_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)

    # Build / refresh config
    cfg = MethodEConfig()
    if args.categories:
        cfg.categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    if args.no_cutoff:
        cfg.cutoff_year = None
    elif args.cutoff_year is not None:
        cfg.cutoff_year = args.cutoff_year
    if args.top_k is not None:
        cfg.top_k_per_problem = args.top_k
    if args.score_threshold is not None:
        cfg.score_threshold = args.score_threshold
    if args.model:
        cfg.judge_model = args.model
    if args.dry_run:
        cfg.judge_dry_run = True
    cfg.run_dir = str(run_dir)

    P = _paths(run_dir)
    _write_config(cfg, P["config"])
    print(f"=== Method E run @ {run_dir} ===")
    print(f"config:\n{cfg.to_yaml().rstrip()}")

    use_citations = not args.no_citations

    import os
    api_key = args.s2_api_key or os.environ.get("S2_API_KEY")

    phases = ["index", "dedup", "cite", "retrieve", "judge", "export"]
    if args.phase != "all":
        phases = [args.phase]

    stats: dict = {}
    if "index" in phases:
        phase_index(cfg, P, args.force)
    if "dedup" in phases:
        phase_dedup(cfg, P, args.force)
    if "cite" in phases and use_citations:
        phase_cite(P, api_key=api_key, delay=args.s2_delay, force=args.force)
    if "retrieve" in phases:
        phase_retrieve(cfg, P, use_citations=use_citations, force=args.force)
    if "judge" in phases:
        phase_judge(cfg, P,
                    model=cfg.judge_model,
                    dry_run=cfg.judge_dry_run,
                    max_candidates=args.max_candidates,
                    force=args.force)
    if "export" in phases:
        phase_export(P, args.force)

    # Counts summary
    counts = {}
    for k in ("problems", "theorems", "dedup", "candidates",
              "judged", "triage"):
        p = P[k]
        if p.exists():
            counts[k] = sum(1 for _ in p.open(encoding="utf-8")) if p.suffix in (".jsonl",) \
                        else p.stat().st_size
    stats["counts"] = counts
    P["stats"].write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"\n=== DONE @ {run_dir} ===")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
