#!/usr/bin/env python3
"""Full silver-gold benchmark pipeline.

Orchestrates four stages over alignment_benchmark/papers/:

  1. SOURCES:  verify each paper's .tex is in place;
               (TODO) download from arxiv if missing.
  2. EXTRACT:  for each (paper, model) in config × papers, extract a JSON
               KG via scripts/silver_gold/run_extraction.py if the output
               doesn't already exist.
  3. LINK:     for each extracted JSON, link to the 298K foundation graph
               via src/link_to_foundation.py.
  4. RENDER:   for each extracted JSON, produce PNG + interactive HTML
               via src/visualize_annotation.py.

Reuses run_extraction.py — does not reimplement LLM extraction. Each
model in the config is dispatched as one subprocess invocation that
internally iterates over papers (with --resume so already-extracted
papers are skipped).

Config format — YAML or JSON — example:

  models:
    - name: opus_4_7         # arbitrary friendly name
      suffix: ""             # gold.json is the existing Opus extraction
      provider: anthropic
      model: claude-opus-4-7
      api_key_env: ANTHROPIC_API_KEY
      skip_extraction: true  # already extracted, just downstream

    - name: deepseek_r
      suffix: _deepseek_r
      provider: openai
      model: deepseek-reasoner
      base_url: https://api.deepseek.com/v1
      api_key_env: OPENAI_API_KEY
      max_tokens: 32768

    - name: gemini_pro
      suffix: _gemini
      provider: google
      model: gemini-2.5-pro
      api_key_env: GOOGLE_API_KEY
      max_tokens: 32768

Usage:

  export OPENAI_API_KEY=sk-...           # one per provider in your config
  export GOOGLE_API_KEY=AIza...

  python3 scripts/silver_gold/run_full_pipeline.py \\
      --config scripts/silver_gold/example_config.yaml \\
      --registry /path/alignment_benchmark/paper_registry.csv \\
      --base-dir /path/alignment_benchmark \\
      --prompt-file scripts/paper_extraction_prompt.txt \\
      --visualize --link-foundation \\
      --limit 5
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_EXTRACTION = REPO_ROOT / "scripts" / "silver_gold" / "run_extraction.py"
VIZ_TOOL = REPO_ROOT / "src" / "visualize_annotation.py"
LINK_TOOL = REPO_ROOT / "src" / "link_to_foundation.py"
VALIDATE_TOOL = REPO_ROOT / "src" / "validate_annotation.py"
ANOMALY_TOOL = REPO_ROOT / "src" / "anomaly_detection.py"
CONSENSUS_TOOL = REPO_ROOT / "scripts" / "silver_gold" / "consensus_intersect.py"


# =============================================================================
# Config loading
# =============================================================================

def load_config(path: Path) -> Dict:
    text = Path(path).read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            sys.exit("[ERROR] PyYAML not installed. Either pip install pyyaml "
                     "or convert your config to .json.")
        return yaml.safe_load(text)
    return json.loads(text)


# =============================================================================
# Stage 1 — verify .tex sources
# =============================================================================

def find_paper_tex(paper_row: Dict, base_dir: Path) -> Optional[Path]:
    tex_rel = (paper_row.get("tex_path") or "").strip()
    if tex_rel:
        p = base_dir / tex_rel
        if p.exists():
            return p
    pid = paper_row["paper_id"]
    src_dir = base_dir / "papers" / pid / "source"
    if not src_dir.exists():
        return None
    for cand in ("main.tex", f"{pid}.tex"):
        if (src_dir / cand).exists():
            return src_dir / cand
    texs = sorted(src_dir.glob("*.tex"))
    return texs[0] if texs else None


def verify_sources(rows: List[Dict], base_dir: Path,
                   download_missing: bool = False) -> List[Dict]:
    """Return only rows whose .tex source is on disk. Logs missing ones."""
    available, missing = [], []
    for r in rows:
        pid = r["paper_id"]
        if find_paper_tex(r, base_dir):
            available.append(r)
        else:
            missing.append(pid)
            if download_missing:
                # TODO: arxiv fetch via src/extract_arxiv_funcs.fetch_arxiv_source
                # Most registry rows have empty arxiv_id, so this is non-trivial
                # for the current dataset. Skipping for now.
                print(f"  [WARN] {pid}: .tex missing; download not implemented yet")
    if missing:
        sample = ", ".join(missing[:5]) + (", ..." if len(missing) > 5 else "")
        print(f"[STAGE 1] {len(missing)} papers missing .tex (skipped): {sample}")
    print(f"[STAGE 1] {len(available)} papers with .tex available\n")
    return available


# =============================================================================
# Stage 2 — extraction per model (delegated to run_extraction.py)
# =============================================================================

def run_extraction_for_model(model_cfg: Dict, args, paper_ids: List[str]) -> int:
    """Invoke run_extraction.py once for this model. Returns exit code."""
    suffix = model_cfg.get("suffix", f"_{model_cfg['name']}")

    cmd = [
        sys.executable, str(RUN_EXTRACTION),
        "--provider", model_cfg["provider"],
        "--model", model_cfg["model"],
        "--prompt-file", str(args.prompt_file),
        "--registry", str(args.registry),
        "--base-dir", str(args.base_dir),
        "--out-suffix", suffix,
        "--max-tokens", str(model_cfg.get("max_tokens", 16384)),
        "--max-input-chars", str(model_cfg.get("max_input_chars", 200000)),
        "--resume",
        "--log", f"silver_pipeline_log_{model_cfg['name']}.csv",
    ]
    if paper_ids:
        cmd.extend(["--paper-ids", ",".join(paper_ids)])
    if args.limit > 0:
        cmd.extend(["--limit", str(args.limit)])
    if args.sleep > 0:
        cmd.extend(["--sleep", str(args.sleep)])

    # env: model-specific overrides
    env = os.environ.copy()
    if model_cfg.get("base_url"):
        env["OPENAI_BASE_URL"] = model_cfg["base_url"]
    else:
        env.pop("OPENAI_BASE_URL", None)

    key_var = model_cfg.get("api_key_env")
    if key_var and not env.get(key_var):
        print(f"[STAGE 2] {model_cfg['name']}: env {key_var} not set — SKIPPING")
        return -1

    print(f"\n{'='*70}")
    print(f"  STAGE 2 EXTRACTION: model='{model_cfg['name']}' "
          f"(provider={model_cfg['provider']}, model={model_cfg['model']})")
    print(f"  output suffix: '{suffix}'")
    print(f"{'='*70}")

    return subprocess.run(cmd, env=env).returncode


# =============================================================================
# Stage 3 + 4 — link + render per JSON
# =============================================================================

def run_link_foundation(json_path: Path, timeout: int = 180) -> bool:
    if not LINK_TOOL.exists():
        return False
    linked = json_path.with_suffix(".linked.json")
    cmd = [sys.executable, str(LINK_TOOL),
           "--paper-json", str(json_path), "--output", str(linked)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        return linked.exists()
    except Exception:
        return False


def run_visualize(json_path: Path, html_only: bool = False, timeout: int = 300) -> bool:
    if not VIZ_TOOL.exists():
        return False
    cmd = [sys.executable, str(VIZ_TOOL), str(json_path)]
    cmd.append("--html-only" if html_only else "--html")
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        return True
    except Exception:
        return False


def run_validate(json_path: Path, timeout: int = 120) -> bool:
    """Run src/validate_annotation.py on a single JSON. Returns True on PASS.

    The validator exits 0 when no errors are found, non-zero on schema /
    DAG-acyclicity violations.
    """
    if not VALIDATE_TOOL.exists():
        return False
    cmd = [sys.executable, str(VALIDATE_TOOL), str(json_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        return True
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode(errors="replace")[:200]
        stdout = (e.stdout or b"").decode(errors="replace")[:200]
        msg = stderr or stdout
        if msg:
            print(f"  [WARN] validate failed for {json_path.name}: {msg.strip()}")
        return False
    except Exception as e:
        print(f"  [WARN] validate error on {json_path.name}: {e}")
        return False


def run_anomaly_detect(json_path: Path, timeout: int = 120) -> bool:
    """Run src/anomaly_detection.py scoped to a single JSON.

    The detector's CLI takes --out-dir and recurses for *.json. To scope it
    to one paper-graph file, we stage it (via copy) into a tempdir and point
    the tool at that. The resulting anomalies_report.csv is copied next to
    the source JSON as anomalies_<stem>.csv. Failures are logged, not raised.
    """
    if not ANOMALY_TOOL.exists():
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="anom_") as td:
            staged = Path(td) / json_path.name
            shutil.copyfile(json_path, staged)
            report = Path(td) / "anomalies_report.csv"
            cmd = [sys.executable, str(ANOMALY_TOOL),
                   "--out-dir", td,
                   "--report-path", str(report)]
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
            # Copy report next to the original JSON for inspection.
            if report.exists():
                dest = json_path.with_name(f"anomalies_{json_path.stem}.csv")
                shutil.copyfile(report, dest)
            detail = Path(td) / "anomalies_detail.json"
            if detail.exists():
                dest_detail = json_path.with_name(f"anomalies_{json_path.stem}.detail.json")
                shutil.copyfile(detail, dest_detail)
        return True
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode(errors="replace")[:200]
        print(f"  [WARN] anomaly detect failed for {json_path.name}: {stderr.strip()}")
        return False
    except Exception as e:
        print(f"  [WARN] anomaly detect error on {json_path.name}: {e}")
        return False


def run_consensus(model_configs: List[Dict], base_dir: Path,
                  paper_ids: Optional[List[str]] = None,
                  timeout: int = 600) -> Dict[str, int]:
    """For each non-reference model, call consensus_intersect.py vs model[0].

    Reference is model_configs[0] (typically Opus, suffix=""). For every
    other model with a non-empty (and non-duplicate) suffix, runs a pairwise
    consensus comparison; writes:
      - per-comparison CSV: <base_dir>/agreement_<modelB>_vs_ref.csv
      - per-paper consensus JSON: gold_consensus_<modelB>.json

    Returns a small summary dict.
    """
    summary = {"comparisons_run": 0, "comparisons_failed": 0, "skipped": 0}
    if not CONSENSUS_TOOL.exists():
        print(f"[CONSENSUS] tool not found at {CONSENSUS_TOOL}; skipping")
        return summary
    if len(model_configs) < 2:
        print("[CONSENSUS] config has <2 models; nothing to compare")
        return summary

    ref = model_configs[0]
    ref_suffix = ref.get("suffix", "")
    ref_name = ref.get("name", "ref")
    print(f"[CONSENSUS] reference model = '{ref_name}' (suffix='{ref_suffix}')")

    seen_suffixes = {ref_suffix}
    for m in model_configs[1:]:
        suffix_b = m.get("suffix", f"_{m['name']}")
        name_b = m["name"]
        if not suffix_b or suffix_b == ref_suffix or suffix_b in seen_suffixes:
            print(f"[CONSENSUS] skipping {name_b}: duplicate or empty suffix '{suffix_b}'")
            summary["skipped"] += 1
            continue
        seen_suffixes.add(suffix_b)

        out_csv = base_dir / f"agreement_{name_b}_vs_{ref_name}.csv"
        cmd = [sys.executable, str(CONSENSUS_TOOL),
               "--base-dir", str(base_dir),
               "--suffix-a", ref_suffix,
               "--suffix-b", suffix_b,
               "--out-suffix", f"_consensus_{name_b}",
               "--report-csv", str(out_csv)]
        if paper_ids:
            cmd.extend(["--paper-ids", ",".join(paper_ids)])
        print(f"[CONSENSUS] {name_b} vs {ref_name}: writing {out_csv.name}")
        try:
            subprocess.run(cmd, check=True, timeout=timeout)
            summary["comparisons_run"] += 1
        except subprocess.CalledProcessError as e:
            print(f"  [WARN] consensus failed for {name_b}: rc={e.returncode}")
            summary["comparisons_failed"] += 1
        except Exception as e:
            print(f"  [WARN] consensus error for {name_b}: {e}")
            summary["comparisons_failed"] += 1

    return summary


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Silver-gold benchmark full pipeline driver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--config", type=Path, required=True,
                    help="YAML or JSON config listing models to extract with")
    ap.add_argument("--registry", type=Path, required=True,
                    help="paper_registry.csv path")
    ap.add_argument("--base-dir", type=Path, required=True,
                    help="alignment_benchmark dir (parent of papers/)")
    ap.add_argument("--prompt-file", type=Path, required=True,
                    help="extraction prompt template; passed to all models")
    ap.add_argument("--paper-ids", default="",
                    help="comma-separated paper_id subset (default: all extracted)")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap papers to first N (0 = all)")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="sleep N seconds between LLM calls within a model run")
    # Stage skips
    ap.add_argument("--no-extraction", action="store_true",
                    help="skip stage 2 entirely; only run downstream on existing JSONs")
    ap.add_argument("--download-missing-tex", action="store_true",
                    help="(TODO) try to fetch missing .tex from arxiv")
    # Downstream toggles
    ap.add_argument("--link-foundation", action="store_true",
                    help="stage 3: link each output JSON to the foundation graph")
    ap.add_argument("--visualize", action="store_true",
                    help="stage 4: render PNG + interactive HTML for each JSON")
    ap.add_argument("--html-only", action="store_true",
                    help="stage 4: HTML only (faster than --visualize)")
    ap.add_argument("--validate", action="store_true",
                    help="run src/validate_annotation.py on each output JSON "
                         "(DAG acyclicity + schema checks); failures are "
                         "logged but do not abort the pipeline")
    ap.add_argument("--anomalies", action="store_true",
                    help="run src/anomaly_detection.py per output JSON; "
                         "writes anomalies_<stem>.csv next to each JSON. "
                         "Failures are logged but do not abort the pipeline")
    ap.add_argument("--consensus", action="store_true",
                    help="after all extractions, run consensus_intersect.py "
                         "pairwise against the FIRST model in the config "
                         "(reference, typically Opus). Writes "
                         "gold_consensus_<model>.json per paper and "
                         "agreement_<model>_vs_<ref>.csv at base-dir")
    args = ap.parse_args()

    # --- Load config
    cfg = load_config(args.config)
    models = cfg.get("models", [])
    if not models:
        sys.exit("[ERROR] config has empty 'models' list")
    print(f"[CONFIG] {len(models)} models from {args.config}:")
    for m in models:
        suf = m.get("suffix", f"_{m['name']}")
        flag = " [skip_extraction]" if m.get("skip_extraction") else ""
        print(f"  - {m['name']}: {m['provider']}/{m['model']} -> 'gold{suf}.json'{flag}")
    print()

    # --- Stage 1: verify sources
    with open(args.registry, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if args.paper_ids:
        wanted = {s.strip() for s in args.paper_ids.split(",") if s.strip()}
        rows = [r for r in rows if r["paper_id"] in wanted]
    else:
        rows = [r for r in rows if r.get("json_status") == "extracted"]
    if args.limit > 0:
        rows = rows[:args.limit]

    print(f"[STAGE 1] checking .tex sources for {len(rows)} papers...")
    available = verify_sources(rows, args.base_dir, args.download_missing_tex)
    if not available:
        sys.exit("[ERROR] no papers have .tex available")

    # --- Stage 2: extraction per model
    if args.no_extraction:
        print("[STAGE 2] skipped (--no-extraction)")
    else:
        avail_ids = [r["paper_id"] for r in available]
        for m in models:
            if m.get("skip_extraction"):
                print(f"\n[STAGE 2] {m['name']}: skip_extraction=true, "
                      f"will only run downstream on existing 'gold{m.get('suffix', '_'+m['name'])}.json'")
                continue
            run_extraction_for_model(m, args, avail_ids)

    # --- Stage 3 + 4: per-(paper, model) downstream ops
    do_link = args.link_foundation
    do_viz = args.visualize or args.html_only
    do_validate = args.validate
    do_anomalies = args.anomalies
    do_consensus = args.consensus
    any_per_paper = do_link or do_viz or do_validate or do_anomalies
    if not (any_per_paper or do_consensus):
        print("\n[DONE] (no downstream stages requested: "
              "--link-foundation / --visualize / --html-only / --validate / "
              "--anomalies / --consensus)")
        return 0

    summary = {"links_done": 0, "viz_done": 0,
               "validate_pass": 0, "validate_fail": 0,
               "anomaly_done": 0, "anomaly_fail": 0,
               "skipped_missing_json": 0}

    if any_per_paper:
        print(f"\n{'='*70}")
        print(f"  STAGE 3+: per-(paper, model) downstream")
        print(f"  validate={do_validate}  anomalies={do_anomalies}  "
              f"link={do_link}  visualize={do_viz}")
        print(f"{'='*70}\n")

        for r in available:
            pid = r["paper_id"]
            for m in models:
                suffix = m.get("suffix", f"_{m['name']}")
                jpath = args.base_dir / "papers" / pid / f"gold{suffix}.json"
                if not jpath.exists():
                    summary["skipped_missing_json"] += 1
                    continue
                ops = []
                if do_validate:
                    if run_validate(jpath):
                        ops.append("validate ok")
                        summary["validate_pass"] += 1
                    else:
                        ops.append("validate FAIL")
                        summary["validate_fail"] += 1
                if do_anomalies:
                    if run_anomaly_detect(jpath):
                        ops.append("anomalies ok")
                        summary["anomaly_done"] += 1
                    else:
                        ops.append("anomalies FAIL")
                        summary["anomaly_fail"] += 1
                if do_link:
                    if run_link_foundation(jpath):
                        ops.append("link ok")
                        summary["links_done"] += 1
                if do_viz:
                    if run_visualize(jpath, html_only=args.html_only):
                        ops.append("viz ok")
                        summary["viz_done"] += 1
                print(f"  {pid} / {m['name']}: {' + '.join(ops) if ops else '(no ops)'}")

    # --- Stage 5: cross-model consensus (post-loop, runs once)
    if do_consensus:
        print(f"\n{'='*70}")
        print(f"  STAGE 5: pairwise consensus vs reference model")
        print(f"{'='*70}\n")
        paper_id_list = [r["paper_id"] for r in available] if args.paper_ids else None
        cons_summary = run_consensus(models, args.base_dir, paper_id_list)
        summary["consensus"] = cons_summary

    print(f"\n[DONE] downstream: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
