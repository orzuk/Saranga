#!/usr/bin/env python3
"""Silver-gold multi-provider, prompt-configurable extraction runner.

Reads papers from alignment_benchmark/paper_registry.csv, sends each paper's
.tex source through a chosen LLM with a chosen prompt, writes JSON outputs
in the unified {metadata, nodes, edges} schema next to the existing gold.json.

Swap prompts by changing --prompt-file. Swap models by changing --provider
and --model. Same output schema regardless, so downstream consensus_intersect
can diff any pair of outputs.

Providers supported (all use OpenAI-compatible HTTP except 'google'):
  huggingface — HuggingFace Inference Providers router (bills your HF account,
                routes to Fireworks / Together / Novita / Hyperbolic / etc.)
  openrouter  — OpenRouter.ai (hosts Qwen, Gemini, DeepSeek, Mistral, ...)
  alibaba     — Alibaba Cloud DashScope / Bailian (direct, cheapest for Qwen)
  google      — Google Generative AI SDK (Gemini native, free tier available)
  anthropic   — Anthropic Claude
  openai      — OpenAI GPT-5 / GPT-4

Quick example (5-paper test, Qwen3.6-35B-A3B via OpenRouter):

  export OPENROUTER_API_KEY=sk-or-...
  python run_extraction.py \\
      --provider openrouter \\
      --model qwen/qwen3.6-35b-a3b \\
      --prompt-file ../paper_extraction_prompt.txt \\
      --out-suffix _qwen \\
      --limit 5

Scale to all 270 papers:

  python run_extraction.py \\
      --provider openrouter \\
      --model qwen/qwen3.6-35b-a3b \\
      --prompt-file ../paper_extraction_prompt.txt \\
      --out-suffix _qwen \\
      --resume

The --resume flag skips papers whose output JSON already exists, so you can
interrupt and restart freely.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional


# =============================================================================
# Prompt loading and placeholder substitution
# =============================================================================

_PROMPT_MARKER = (
    "================================================================================\n"
    "PROMPT\n"
    "================================================================================\n"
)


def load_prompt_template(path: Path) -> str:
    """Read a prompt file; if it has the 'PROMPT' marker (per
    paper_extraction_prompt.txt convention), return only the text after it;
    otherwise return the whole file verbatim."""
    text = Path(path).read_text(encoding="utf-8")
    idx = text.find(_PROMPT_MARKER)
    if idx != -1:
        return text[idx + len(_PROMPT_MARKER):].strip()
    return text.strip()


def substitute(template: str, subs: Dict[str, str]) -> str:
    """Replace {KEY} tokens with subs[KEY]. Unknown {tokens} pass through."""
    out = template
    for key, val in subs.items():
        out = out.replace("{" + key + "}", str(val))
    return out


# =============================================================================
# Provider clients — each returns a call_llm(prompt, model, max_tokens) -> str
# =============================================================================

def make_openai_compat_client(base_url: str, api_key: str) -> Callable:
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=api_key)

    def call(prompt: str, model: str, max_tokens: int = 16384) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    return call


def make_google_client() -> Callable:
    import google.generativeai as genai
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("[ERROR] GOOGLE_API_KEY or GEMINI_API_KEY not set.")
    genai.configure(api_key=key)

    def call(prompt: str, model: str, max_tokens: int = 16384) -> str:
        m = genai.GenerativeModel(model)
        resp = m.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": max_tokens,
                "response_mime_type": "application/json",
            },
        )
        return resp.text

    return call


def make_anthropic_client() -> Callable:
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("[ERROR] ANTHROPIC_API_KEY not set.")
    client = anthropic.Anthropic(api_key=key)

    def call(prompt: str, model: str, max_tokens: int = 16384) -> str:
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    return call


def make_client(provider: str) -> Callable:
    if provider == "huggingface":
        # HF Inference Providers router — OpenAI-compatible, bills the HF
        # account attached to HF_TOKEN. Routes to third-party GPUs (Fireworks,
        # Together, Novita, Hyperbolic, Cerebras, ...). Model strings use the
        # HF repo id, optionally with a provider suffix, e.g.
        #   Qwen/Qwen3.6-35B-A3B                       (auto-route)
        #   Qwen/Qwen3.6-35B-A3B:fireworks-ai          (force Fireworks)
        #   Qwen/Qwen3.6-35B-A3B:novita                (force Novita)
        key = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
        if not key:
            sys.exit("[ERROR] HF_TOKEN (or HUGGINGFACE_API_KEY) not set.")
        return make_openai_compat_client("https://router.huggingface.co/v1", key)

    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            sys.exit("[ERROR] OPENROUTER_API_KEY not set.")
        return make_openai_compat_client("https://openrouter.ai/api/v1", key)

    if provider == "alibaba":
        key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("ALIBABA_API_KEY")
        if not key:
            sys.exit("[ERROR] DASHSCOPE_API_KEY (or ALIBABA_API_KEY) not set.")
        base = os.environ.get(
            "DASHSCOPE_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
        return make_openai_compat_client(base, key)

    if provider == "google":
        return make_google_client()

    if provider == "anthropic":
        return make_anthropic_client()

    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            sys.exit("[ERROR] OPENAI_API_KEY not set.")
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return make_openai_compat_client(base, key)

    sys.exit(f"[ERROR] Unknown provider: {provider}")


# =============================================================================
# Paper registry + .tex resolution
# =============================================================================

def load_registry(csv_path: Path) -> List[Dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_tex(row: Dict[str, str], base_dir: Path) -> Optional[Path]:
    """Resolve paper .tex. Prefer registry tex_path; fall back to
    papers/{id}/source/main.tex, then papers/{id}/source/{id}.tex, then any .tex."""
    tex_rel = (row.get("tex_path") or "").strip()
    if tex_rel:
        p = base_dir / tex_rel
        if p.exists():
            return p
    pid = row["paper_id"]
    src = base_dir / "papers" / pid / "source"
    if not src.exists():
        return None
    for name in ("main.tex", f"{pid}.tex"):
        p = src / name
        if p.exists():
            return p
    candidates = sorted(src.glob("*.tex"))
    return candidates[0] if candidates else None


def read_tex(path: Path, max_chars: int) -> str:
    txt = path.read_text(encoding="utf-8", errors="replace")
    if max_chars > 0 and len(txt) > max_chars:
        print(f"  [WARN] truncating {path.name} {len(txt)} -> {max_chars} chars")
        txt = txt[:max_chars]
    return txt


# =============================================================================
# JSON extraction from LLM response
# =============================================================================

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(response_text: str) -> dict:
    """Parse JSON out of an LLM response. Tries a ```json ...``` fence first,
    then any ``` ... ``` fence, then the outermost {...} span."""
    if not response_text:
        raise ValueError("empty response")

    m = _FENCE_RE.search(response_text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    first = response_text.find("{")
    last = response_text.rfind("}")
    if first != -1 and last > first:
        return json.loads(response_text[first:last + 1])

    raise ValueError("no JSON object found in response")


# =============================================================================
# Downstream operations: visualize + link to foundation
# =============================================================================

_REPO_ROOT_FOR_TOOLS = Path(__file__).resolve().parent.parent.parent


def run_visualize(json_path: Path, html_only: bool = False, timeout: int = 300) -> bool:
    """Call src/visualize_annotation.py on a single JSON. Returns success."""
    script = _REPO_ROOT_FOR_TOOLS / "src" / "visualize_annotation.py"
    if not script.exists():
        print(f"    [WARN] visualize: {script} not found")
        return False
    args = ["python3", str(script), str(json_path)]
    args.append("--html-only" if html_only else "--html")
    try:
        subprocess.run(args, check=True, capture_output=True, timeout=timeout)
        out_html = json_path.with_suffix(".html")
        if out_html.exists():
            print(f"    -> viz: {out_html.name}")
        return True
    except subprocess.TimeoutExpired:
        print(f"    [WARN] visualize timed out after {timeout}s")
        return False
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or b"").decode(errors="replace")[:200]
        print(f"    [WARN] visualize failed: {msg}")
        return False
    except Exception as e:
        print(f"    [WARN] visualize error: {type(e).__name__}: {e}")
        return False


def run_link_foundation(json_path: Path, timeout: int = 180) -> bool:
    """Call src/link_to_foundation.py to augment a JSON with foundation-graph
    edges. Writes <stem>.linked.json next to the input."""
    script = _REPO_ROOT_FOR_TOOLS / "src" / "link_to_foundation.py"
    if not script.exists():
        print(f"    [WARN] link: {script} not found")
        return False
    linked_path = json_path.with_suffix(".linked.json")
    args = ["python3", str(script),
            "--paper-json", str(json_path),
            "--output", str(linked_path)]
    try:
        subprocess.run(args, check=True, capture_output=True, timeout=timeout)
        if linked_path.exists():
            print(f"    -> linked: {linked_path.name}")
        return True
    except subprocess.TimeoutExpired:
        print(f"    [WARN] link timed out after {timeout}s")
        return False
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or b"").decode(errors="replace")[:200]
        print(f"    [WARN] link failed: {msg}")
        return False
    except Exception as e:
        print(f"    [WARN] link error: {type(e).__name__}: {e}")
        return False


def run_downstream(json_path: Path, args: argparse.Namespace) -> None:
    """Run any requested post-extraction operations on a single JSON."""
    if args.link_foundation:
        run_link_foundation(json_path)
    if args.visualize or args.html_only:
        run_visualize(json_path, html_only=args.html_only)


# =============================================================================
# Main
# =============================================================================

DEFAULT_REGISTRY = Path(
    "/mnt/g/My Drive/Research/Automath/alignment_benchmark/paper_registry.csv"
)
DEFAULT_BASE_DIR = Path(
    "/mnt/g/My Drive/Research/Automath/alignment_benchmark"
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Silver-gold multi-provider prompt-configurable extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    ap.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR,
                    help="root of alignment_benchmark (parent of papers/)")
    ap.add_argument("--prompt-file", type=Path, required=True,
                    help="prompt template; SWAP THIS to change extraction strategy")
    ap.add_argument("--provider", default=None,
                    choices=["huggingface", "openrouter", "alibaba",
                             "google", "anthropic", "openai"],
                    help="LLM provider (required unless --viz-only)")
    ap.add_argument("--model", default=None,
                    help="provider-specific model string "
                         "(e.g. 'qwen/qwen3.6-35b-a3b', 'gemini-2.5-pro', "
                         "'claude-opus-4-7'). Required unless --viz-only.")
    ap.add_argument("--out-suffix", default=None,
                    help="suffix for output file, e.g. _qwen -> gold_qwen.json. "
                         "Required for extraction mode. Ignored in --viz-only "
                         "mode (which auto-discovers ALL gold*.json files in "
                         "each paper directory).")
    ap.add_argument("--source-type", default="paper",
                    choices=["paper", "textbook"])
    ap.add_argument("--limit", type=int, default=0,
                    help="process only first N papers (0 = all eligible)")
    ap.add_argument("--paper-ids", type=str, default="",
                    help="comma-separated paper_ids (overrides --limit filter)")
    ap.add_argument("--resume", action="store_true",
                    help="skip papers whose output file already exists")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="seconds to sleep between calls (rate limits)")
    ap.add_argument("--max-tokens", type=int, default=16384,
                    help="max output tokens from the LLM")
    ap.add_argument("--max-input-chars", type=int, default=200000,
                    help="truncate .tex larger than this (0 = no cap)")
    ap.add_argument("--log", type=Path, default=Path("silver_gold_log.csv"))
    ap.add_argument("--only-extracted", action="store_true", default=True,
                    help="only run on papers whose json_status=extracted (default)")
    ap.add_argument("--all-papers", dest="only_extracted", action="store_false",
                    help="run on all papers in registry, not just extracted ones")
    # Downstream operations after extraction (chain like a pipeline)
    ap.add_argument("--visualize", action="store_true",
                    help="render PNG + HTML for each successful (or skipped) JSON "
                         "via src/visualize_annotation.py")
    ap.add_argument("--html-only", action="store_true",
                    help="render only HTML (faster than --visualize, no PNG)")
    ap.add_argument("--link-foundation", action="store_true",
                    help="link each output JSON to the 298K foundation graph "
                         "via src/link_to_foundation.py; writes <stem>.linked.json")
    ap.add_argument("--viz-only", action="store_true",
                    help="skip extraction entirely; only run downstream "
                         "(--visualize and/or --link-foundation) on existing JSONs")
    args = ap.parse_args()

    # --- load prompt template
    template = load_prompt_template(args.prompt_file)
    print(f"[INFO] prompt template: {len(template):,} chars "
          f"from {args.prompt_file.name}")

    # --- load registry and filter
    rows = load_registry(args.registry)
    print(f"[INFO] registry: {len(rows)} total papers")

    if args.paper_ids:
        wanted = {s.strip() for s in args.paper_ids.split(",") if s.strip()}
        rows = [r for r in rows if r["paper_id"] in wanted]
        print(f"[INFO] filtered by --paper-ids: {len(rows)} papers")
    elif args.only_extracted:
        rows = [r for r in rows if r.get("json_status") == "extracted"]
        print(f"[INFO] with json_status=extracted: {len(rows)} papers")

    if args.limit > 0:
        rows = rows[:args.limit]
        print(f"[INFO] --limit {args.limit}: {len(rows)} papers will be processed")

    if not rows:
        print("[ERROR] no papers to process")
        return 1

    # --- create LLM client (skip if downstream-only)
    if args.viz_only:
        call_llm = None
        print("[INFO] --viz-only mode: no LLM client, auto-discovering gold*.json")
    else:
        if not args.provider or not args.model:
            sys.exit("[ERROR] --provider and --model are required unless --viz-only")
        if args.out_suffix is None:
            sys.exit("[ERROR] --out-suffix is required (unless --viz-only)")
        call_llm = make_client(args.provider)
        print(f"[INFO] provider={args.provider}  model={args.model}")

    # --- process
    log_rows: List[Dict[str, str]] = []
    ok = fail = skip = 0
    t_start = time.time()

    # Pre-flight: if any downstream is requested, ensure tools exist
    if (args.visualize or args.html_only or args.link_foundation):
        for tool, flag in [
            ("src/visualize_annotation.py", args.visualize or args.html_only),
            ("src/link_to_foundation.py", args.link_foundation),
        ]:
            if flag and not (_REPO_ROOT_FOR_TOOLS / tool).exists():
                print(f"[WARN] requested downstream tool not found: {tool}")

    for i, row in enumerate(rows, 1):
        pid = row["paper_id"]
        out_dir = args.base_dir / "papers" / pid

        # --viz-only mode: skip LLM, auto-discover ALL extraction JSONs in the
        # paper folder (gold.json, gold_<model>.json, etc.) and run downstream
        # on each one. Excludes .linked.json files (those are downstream outputs).
        if args.viz_only:
            if not out_dir.exists():
                print(f"[{i}/{len(rows)}] {pid}: SKIP (folder missing)")
                skip += 1
                continue
            candidates = sorted(out_dir.glob("gold*.json"))
            candidates = [p for p in candidates if not p.name.endswith(".linked.json")]
            if not candidates:
                print(f"[{i}/{len(rows)}] {pid}: SKIP (no gold*.json found)")
                skip += 1
                continue
            print(f"[{i}/{len(rows)}] {pid}: viz-only on {len(candidates)} extraction(s)")
            for cand in candidates:
                print(f"  -> {cand.name}")
                run_downstream(cand, args)
            ok += 1
            continue

        # Extraction mode: single output path determined by --out-suffix
        out_path = out_dir / f"gold{args.out_suffix}.json"

        if args.resume and out_path.exists():
            print(f"[{i}/{len(rows)}] {pid}: SKIP extraction (exists)")
            skip += 1
            # Still run downstream on the existing JSON if requested
            if args.visualize or args.html_only or args.link_foundation:
                run_downstream(out_path, args)
            continue

        tex_path = find_tex(row, args.base_dir)
        if tex_path is None:
            print(f"[{i}/{len(rows)}] {pid}: FAIL no .tex")
            log_rows.append({"paper_id": pid, "status": "no_tex", "error": ""})
            fail += 1
            continue

        tex = read_tex(tex_path, args.max_input_chars)
        subs = {
            "SOURCE_TYPE": args.source_type,
            "CHAPTER_TEXT": tex,
            "PAPER_TEXT": tex,                       # alternative key some prompts use
            "BOOK_ID": pid,
            "PAPER_ID": pid,
            "BID": pid,
            "SLUG": pid,
            "CHAPTER_NUM": "1",
            "CHAPTER_TITLE": row.get("full_title") or row.get("short_name") or pid,
            "TITLE": row.get("full_title") or pid,
            "AUTHORS": row.get("authors", ""),
            "YEAR": row.get("year", ""),
        }
        prompt = substitute(template, subs)

        print(f"[{i}/{len(rows)}] {pid}: tex={tex_path.name} "
              f"prompt={len(prompt):,} chars -> calling LLM")
        t0 = time.time()
        try:
            response = call_llm(prompt, args.model, max_tokens=args.max_tokens)
            data = extract_json(response)
        except Exception as e:
            dt = time.time() - t0
            err = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"    FAIL ({dt:.1f}s) {err}")
            log_rows.append({
                "paper_id": pid, "status": "error",
                "error": err, "elapsed_s": f"{dt:.1f}",
            })
            fail += 1
            if args.sleep > 0:
                time.sleep(args.sleep)
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        dt = time.time() - t0
        n_nodes = len(data.get("nodes", []))
        n_edges = len(data.get("edges", []))
        print(f"    OK  ({dt:.1f}s) nodes={n_nodes} edges={n_edges} -> {out_path.name}")
        log_rows.append({
            "paper_id": pid, "status": "ok",
            "n_nodes": str(n_nodes), "n_edges": str(n_edges),
            "elapsed_s": f"{dt:.1f}",
        })
        ok += 1

        # Pipeline: run requested downstream operations on the new JSON.
        if args.visualize or args.html_only or args.link_foundation:
            run_downstream(out_path, args)

        if args.sleep > 0:
            time.sleep(args.sleep)

    # --- write log
    if log_rows:
        cols = sorted({k for r in log_rows for k in r.keys()})
        with open(args.log, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(log_rows)
        print(f"[INFO] log -> {args.log}")

    total_min = (time.time() - t_start) / 60.0
    print(f"\n[DONE] ok={ok}  fail={fail}  skip={skip}  "
          f"elapsed={total_min:.1f} min")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
