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
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_EXTRACTION = REPO_ROOT / "scripts" / "silver_gold" / "run_extraction.py"
VIZ_TOOL = REPO_ROOT / "src" / "visualize_annotation.py"
LINK_TOOL = REPO_ROOT / "src" / "link_to_foundation.py"


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

    # --- Stage 3 + 4: link + visualize per (paper, model)
    do_link = args.link_foundation
    do_viz = args.visualize or args.html_only
    if not (do_link or do_viz):
        print("\n[DONE] (no --link-foundation, --visualize, or --html-only requested)")
        return 0

    print(f"\n{'='*70}")
    print(f"  STAGE 3+4: downstream over (papers × models)")
    print(f"  link={do_link}  visualize={do_viz}")
    print(f"{'='*70}\n")

    summary = {"links_done": 0, "viz_done": 0, "skipped_missing_json": 0}
    for r in available:
        pid = r["paper_id"]
        for m in models:
            suffix = m.get("suffix", f"_{m['name']}")
            jpath = args.base_dir / "papers" / pid / f"gold{suffix}.json"
            if not jpath.exists():
                summary["skipped_missing_json"] += 1
                continue
            ops = []
            if do_link:
                if run_link_foundation(jpath):
                    ops.append("link")
                    summary["links_done"] += 1
            if do_viz:
                if run_visualize(jpath, html_only=args.html_only):
                    ops.append("viz")
                    summary["viz_done"] += 1
            print(f"  {pid} / {m['name']}: {' + '.join(ops) if ops else '(no ops)'}")

    print(f"\n[DONE] downstream: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
