"""T-OPEN O4 — LLM-as-judge for a single problem→theorem candidate.

Reuses common.llm_judge.LLMJudge (cached). Given two node handles
(paper_id::node_id), pulls their full text (raw LaTeX preferred, so masked
[MATH] tokens don't hide the distinguishing math) and asks the model whether the
theorem actually RESOLVES the open problem / conjecture.

    python discovery_suite/open_problems/o4_judge.py \
        --problem 1107.1630::Cj2 --theorem 1105.2040::T4 --model opus
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]   # open_problems -> discovery_suite -> repo root
for _p in (_REPO / "src", _REPO / "src" / "discovery", _REPO / "discovery_suite"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _load_dotenv() -> None:
    env = _REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _node(papers, handle):
    pid, nid = handle.split("::", 1)
    for p in papers:
        if p.paper_id == pid:
            for n in p.nodes:
                if str(n.get("id")) == nid:
                    return p, n
    raise SystemExit(f"node {handle} not found in loaded corpus")


def _node_text(n) -> str:
    raw = (n.get("raw_latex") or "").strip()
    stmt = (n.get("statement") or n.get("clean_text") or "").strip()
    # Prefer raw LaTeX (keeps the real math); fall back to the masked statement.
    return raw or stmt


_PROMPT = (
    "Open problem / conjecture stated in paper {a_pid}:\n"
    "  {a_text}\n\n"
    "Candidate theorem from a different paper {b_pid}:\n"
    "  {b_text}\n\n"
    "Does the theorem RESOLVE the conjecture/open problem — i.e. does it prove, "
    "disprove, or directly settle the SAME mathematical claim about the SAME "
    "object/quantity? Note that \\-macros (e.g. \\CR, \\SymSubMP) are paper-"
    "specific; judge whether the objects truly coincide, not just the wording.\n\n"
    "Answer in exactly this format:\n"
    "VERDICT: YES | NO | PARTIAL\n"
    "SAME_OBJECT: YES | NO\n"
    "JUSTIFICATION: <1-3 sentences>"
)


def _parse(raw: str) -> dict:
    out = {"verdict": "", "same_object": "", "justification": "", "raw": raw}
    for line in raw.splitlines():
        u = line.upper()
        if u.startswith("VERDICT:"):
            out["verdict"] = line.split(":", 1)[1].strip()
        elif u.startswith("SAME_OBJECT:"):
            out["same_object"] = line.split(":", 1)[1].strip()
        elif u.startswith("JUSTIFICATION:"):
            out["justification"] = line.split(":", 1)[1].strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problem", required=True, help="paper_id::node_id")
    ap.add_argument("--theorem", required=True, help="paper_id::node_id")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--limit", type=int, default=600)
    args = ap.parse_args()

    _load_dotenv()
    from shared.corpus import load_papers
    from common.llm_judge import LLMJudge

    papers = load_papers(limit=args.limit)
    pa, na = _node(papers, args.problem)
    pb, nb = _node(papers, args.theorem)

    print(f"PROBLEM {args.problem}: {_node_text(na)[:200]}")
    print(f"THEOREM {args.theorem}: {_node_text(nb)[:200]}\n")

    judge = LLMJudge(
        model=args.model,
        cache_path=_HERE.parent / "eval_harness" / "runs" / "o4_judge_cache.sqlite",
        prompt_template=_PROMPT,
        prompt_version="o4_resolution_v1",
        response_parser=_parse,
        max_tokens=400,
        system="You are an expert mathematician judging whether one paper's "
               "theorem resolves another paper's open problem.",
    )
    res = judge.judge(a_pid=pa.paper_id, a_text=_node_text(na),
                      b_pid=pb.paper_id, b_text=_node_text(nb))
    p = res.parsed
    print("=== O4 JUDGE ===")
    print("VERDICT     :", p.get("verdict"))
    print("SAME OBJECT :", p.get("same_object"))
    print("JUSTIFY     :", p.get("justification"))
    print("(cached)" if res.cached else "(fresh LLM call)")


if __name__ == "__main__":
    main()
