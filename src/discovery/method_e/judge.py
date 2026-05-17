"""Method E LLM-as-judge pass over the retrieval candidates.

Thin binding: loads the method_e_judge_v1 prompt, runs each candidate row
through common.llm_judge.LLMJudge, writes a judged_candidates.jsonl that
augments retrieve_pairs.py output with {relationship, verdict, justification}.

Cost-control levers (set via MethodEConfig in run.py):
  - score_threshold pre-filter at retrieve time
  - top_k_per_problem cap
  - judge_dry_run = True to skip API calls (returns NO verdicts; useful for
    smoke testing the full pipeline without spend)
  - tier-2 confirmation pass on YES survivors with a stronger model
    (handled in run.py orchestrator, not here)
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


# ── Response parser ─────────────────────────────────────────────────────────

_RE_RELATIONSHIP = re.compile(r"RELATIONSHIP:\s*([A-Z_]+)", re.IGNORECASE)
_RE_VERDICT = re.compile(r"VERDICT:\s*(YES|MAYBE|NO)", re.IGNORECASE)
_RE_JUSTIFICATION = re.compile(r"JUSTIFICATION:\s*(.+?)\s*$",
                                re.IGNORECASE | re.MULTILINE | re.DOTALL)

_VALID_RELATIONS = {"DIRECT", "GENERALIZES", "SPECIAL_HARD",
                    "SPECIAL_CORNER", "COUNTER", "UNRELATED"}


def parse_judge_response(raw: str) -> dict:
    """Parse the three-line judge response into a dict. Defaults to NO/UNRELATED
    on parse failure so the pipeline keeps running."""
    rel_m = _RE_RELATIONSHIP.search(raw or "")
    verd_m = _RE_VERDICT.search(raw or "")
    just_m = _RE_JUSTIFICATION.search(raw or "")
    rel = (rel_m.group(1).upper() if rel_m else "UNRELATED")
    if rel not in _VALID_RELATIONS:
        rel = "UNRELATED"
    verd = (verd_m.group(1).upper() if verd_m else "NO")
    just = (just_m.group(1).strip() if just_m else "")[:500]
    return {"relationship": rel, "verdict": verd, "justification": just}


# ── Prompt loader ──────────────────────────────────────────────────────────

def load_prompt(prompt_version: str = "method_e_judge_v1") -> str:
    p = _HERE / "prompts" / f"{prompt_version}.txt"
    if not p.exists():
        raise FileNotFoundError(f"Prompt not found: {p}")
    return p.read_text(encoding="utf-8")


# ── Main driver ────────────────────────────────────────────────────────────

def judge_candidates(
    candidates_path: Path,
    out_path: Path,
    *,
    cache_path: Path,
    model: str = "sonnet",
    prompt_version: str = "method_e_judge_v1",
    dry_run: bool = False,
    max_candidates: Optional[int] = None,
    progress_every: int = 50,
) -> dict:
    template = load_prompt(prompt_version)
    judge = LLMJudge(
        model=model,
        cache_path=cache_path,
        prompt_template=template,
        prompt_version=prompt_version,
        response_parser=parse_judge_response,
        max_tokens=256,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_in = 0
    n_judged = 0
    n_cached = 0
    counts = {"YES": 0, "MAYBE": 0, "NO": 0}
    with candidates_path.open(encoding="utf-8") as fin, \
         out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            n_in += 1
            if max_candidates is not None and n_in > max_candidates:
                break
            cand = json.loads(line)
            try:
                result = judge.judge(
                    dry_run=dry_run,
                    year_O=cand["problem_year"],
                    paper_O=cand["problem_paper"],
                    problem_clean_text=cand["problem_text"],
                    year_T=cand["candidate_year"],
                    paper_T=cand["candidate_paper"],
                    candidate_clean_text=cand["candidate_text"],
                )
            except Exception as e:
                result = type("R", (), {})()
                result.parsed = {"relationship": "PARSE_ERROR",
                                 "verdict": "NO",
                                 "justification": f"judge error: {e}"}
                result.cached = False
            row = dict(cand)
            row["judge"] = {
                **result.parsed,
                "model": judge.model,
                "prompt_version": prompt_version,
                "cached": getattr(result, "cached", False),
            }
            v = result.parsed.get("verdict", "NO")
            if v in counts:
                counts[v] += 1
            n_judged += 1
            if getattr(result, "cached", False):
                n_cached += 1
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            if n_judged % progress_every == 0:
                print(f"[judge] {n_judged} judged "
                      f"(cached {n_cached}; YES={counts['YES']} "
                      f"MAYBE={counts['MAYBE']} NO={counts['NO']})",
                      file=sys.stderr)

    judge.close()
    print(f"[judge] DONE in={n_in} judged={n_judged} cached={n_cached} "
          f"YES={counts['YES']} MAYBE={counts['MAYBE']} NO={counts['NO']} "
          f"-> {out_path}", file=sys.stderr)
    return {"in": n_in, "judged": n_judged, "cached": n_cached, **counts}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--model", default="sonnet",
                    help="Short key from config.SOURCES or full model ID")
    ap.add_argument("--prompt-version", default="method_e_judge_v1")
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip LLM API calls; assign NO/UNRELATED to all "
                         "candidates. Useful for smoke testing.")
    ap.add_argument("--max-candidates", type=int, default=None,
                    help="Cap on candidates processed (debug/smoke)")
    args = ap.parse_args()
    judge_candidates(
        candidates_path=Path(args.candidates),
        out_path=Path(args.out),
        cache_path=Path(args.cache),
        model=args.model,
        prompt_version=args.prompt_version,
        dry_run=args.dry_run,
        max_candidates=args.max_candidates,
    )


if __name__ == "__main__":
    main()
