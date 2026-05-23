"""Formalize a SARANGA-extracted open problem into a rigid,
machine-graderable prompt in the style of OpenAI's Erdős unit-distance
benchmark prompt (May 2026 disproof writeup, page 3).

Pipeline stage 1 of the open-problem-solve POC:
    open_problem node + same-paper context
      -> rigid Prompt (Definitions / Question / Affirmative-vs-Negative /
                       Conventions / no-partial-credit)

Stage 2 (solver call) and stage 3 (grader) are separate scripts; this
module just produces the prompt artifact.

CLI:
    # one problem
    python -m discovery.open_problem_solve.formalizer \\
        --paper-json /path/to/paperXYZ.json \\
        --open-problem-id OpenP1.1 \\
        --model opus \\
        --out /path/to/formalized_OpenP1.1.json

    # every open_problem in the paper
    python -m discovery.open_problem_solve.formalizer \\
        --paper-json /path/to/paperXYZ.json --all \\
        --model opus \\
        --out-dir /path/to/formalized/

    # render-only mode: print the prompt that WOULD be sent, no LLM call
    python -m discovery.open_problem_solve.formalizer \\
        --paper-json /path/to/paperXYZ.json \\
        --open-problem-id OpenP1.1 --render-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_COMMON = _HERE.parent / "common"
_SRC = _HERE.parent.parent
for _p in (_SRC, _COMMON, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from llm_judge import LLMJudge  # noqa: E402


CONTEXT_TYPES = ("definition", "theorem", "lemma", "proposition",
                 "corollary", "claim", "equation", "remark")


def load_prompt(prompt_name: str = "open_problem_formalize") -> str:
    p = _HERE.parent.parent.parent / "prompts" / f"{prompt_name}.txt"
    if not p.exists():
        raise FileNotFoundError(f"Prompt not found: {p}")
    return p.read_text(encoding="utf-8")


def parse_formalize_response(raw: str) -> dict:
    """LLM returns JSON. Strip markdown fencing if present and json.loads."""
    s = (raw or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    try:
        d = json.loads(s)
    except json.JSONDecodeError as e:
        return {"_parse_error": f"json.loads failed: {e}",
                "_raw_response_head": s[:600],
                "rigid_prompt": "", "issues": [f"parse error: {e}"]}
    d.setdefault("issues", [])
    d.setdefault("notation_defined", [])
    d.setdefault("context_nodes_used", [])
    d.setdefault("confidence", "low")
    return d


def build_context_block(nodes: list[dict], max_chars: int = 8000) -> str:
    """Render same-paper context nodes for the formalizer prompt.

    Includes definition/theorem/lemma/proposition/corollary/claim/equation/
    remark nodes. Truncates if total length exceeds max_chars.
    """
    keep = [n for n in nodes if n.get("type") in CONTEXT_TYPES]
    lines = []
    total = 0
    for n in keep:
        body = (n.get("raw_latex") or n.get("statement_clean") or n.get("statement") or "").strip()
        if not body:
            continue
        name = n.get("name", "")
        head = f"[{n.get('id','?')}] {n.get('type','?')}: {name}".rstrip()
        chunk = f"{head}\n  {body}\n"
        if total + len(chunk) > max_chars:
            lines.append(f"... (truncated; {len(keep) - len(lines)} more context "
                         f"nodes omitted) ...\n")
            break
        lines.append(chunk)
        total += len(chunk)
    return "\n".join(lines) if lines else "(no same-paper context nodes available)"


def find_open_problems(paper: dict) -> list[dict]:
    nodes = paper.get("nodes", [])
    return [n for n in nodes if n.get("type") in ("open_problem", "conjecture")]


def format_one(paper: dict, op: dict, *,
               model: str = "opus",
               cache_path: Optional[Path] = None,
               render_only: bool = False) -> dict:
    """Run the formalizer on a single open_problem node.

    Returns the parsed JSON output plus bookkeeping fields. When
    render_only=True, no LLM is called; the rendered prompt is returned
    under key 'rendered_prompt_only' for inspection.
    """
    meta = paper.get("metadata", {}) or {}
    paper_id = (meta.get("arxiv_id") or meta.get("paper_id")
                or meta.get("paper_num") or meta.get("bid") or meta.get("id", "?"))
    year = meta.get("year") or meta.get("published_year") or "?"

    context_block = build_context_block(paper.get("nodes", []))

    template_vars = dict(
        paper_id=paper_id,
        year=year,
        open_problem_id=op.get("id", "?"),
        section=op.get("section", "?"),
        name=op.get("name", "(unnamed)"),
        statement=op.get("raw_latex") or op.get("statement_clean") or op.get("statement", ""),
        context_block=context_block,
    )

    template = load_prompt("open_problem_formalize")

    if render_only:
        rendered = template.format(**template_vars)
        return {"open_problem_id": op.get("id"),
                "source_paper": f"arXiv:{paper_id}",
                "rendered_prompt_only": rendered,
                "issues": ["render-only mode; no LLM call made"]}

    cache = cache_path or (Path.home() / ".cache" / "saranga"
                            / "open_problem_formalize.sqlite")
    judge = LLMJudge(
        model=model,
        cache_path=cache,
        prompt_template=template,
        prompt_version="open_problem_formalize_v1",
        response_parser=parse_formalize_response,
        max_tokens=2048,
    )
    result = judge.judge(**template_vars)
    judge.close()

    out = dict(result.parsed)
    out["source_paper"] = f"arXiv:{paper_id}"
    out["year"] = year
    out["model"] = model
    out["cached"] = result.cached
    return out


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paper-json", required=True, type=Path,
                    help="Path to a SARANGA-extracted paper JSON "
                         "(with nodes[type=open_problem])")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--open-problem-id", help="Run on a single open_problem id")
    g.add_argument("--all", action="store_true",
                   help="Run on every open_problem / conjecture in the paper")
    ap.add_argument("--model", default="opus",
                    help="LLM model key (sonnet/opus/gpt4o/qwen/...) or full id")
    ap.add_argument("--out", type=Path,
                    help="Output JSON path (only with --open-problem-id)")
    ap.add_argument("--out-dir", type=Path,
                    help="Output dir (only with --all); one file per problem")
    ap.add_argument("--render-only", action="store_true",
                    help="Render the prompt but do NOT call the LLM. "
                         "Useful for sanity-checking before spend.")
    ap.add_argument("--cache", type=Path, default=None,
                    help="Override LLM cache sqlite path")
    args = ap.parse_args()

    paper = json.loads(args.paper_json.read_text(encoding="utf-8"))
    ops = find_open_problems(paper)
    if not ops:
        print(f"[formalizer] No open_problem/conjecture nodes in "
              f"{args.paper_json}", file=sys.stderr)
        sys.exit(1)

    if args.open_problem_id:
        target = next((n for n in ops if n.get("id") == args.open_problem_id), None)
        if not target:
            print(f"[formalizer] id {args.open_problem_id!r} not found. "
                  f"Available: {[n.get('id') for n in ops]}", file=sys.stderr)
            sys.exit(2)
        out = format_one(paper, target, model=args.model,
                         cache_path=args.cache, render_only=args.render_only)
        text = json.dumps(out, ensure_ascii=False, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
            print(f"[formalizer] wrote {args.out}", file=sys.stderr)
        else:
            print(text)
    else:
        if not args.out_dir and not args.render_only:
            print("[formalizer] --all requires --out-dir (or --render-only)",
                  file=sys.stderr)
            sys.exit(3)
        if args.out_dir:
            args.out_dir.mkdir(parents=True, exist_ok=True)
        for op in ops:
            out = format_one(paper, op, model=args.model,
                             cache_path=args.cache,
                             render_only=args.render_only)
            text = json.dumps(out, ensure_ascii=False, indent=2)
            if args.out_dir:
                fp = args.out_dir / f"formalized_{op.get('id','unknown')}.json"
                fp.write_text(text, encoding="utf-8")
                print(f"[formalizer] wrote {fp}  "
                      f"(binary_form={out.get('binary_form','?')}, "
                      f"confidence={out.get('confidence','?')})",
                      file=sys.stderr)
            else:
                print(f"--- {op.get('id')} ---")
                print(text)


if __name__ == "__main__":
    main()
