"""T-OPEN O4 — LLM-as-judge for a single problem→theorem candidate.

Reuses common.llm_judge.LLMJudge (cached). Given two node handles
(paper_id::node_id), pulls their full text (raw LaTeX preferred, so masked
[MATH] tokens don't hide the distinguishing math) and asks the model how the
theorem relates to the open problem / conjecture, on the seven-way
resolution_taxonomy RELATIONSHIP axis plus its YES/PARTIAL/NO roll-up.

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
for _p in (_HERE, _REPO / "src", _REPO / "src" / "discovery",
           _REPO / "discovery_suite"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import resolution_taxonomy as T  # noqa: E402
from resolution_taxonomy import parse_response as _parse  # noqa: E402


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


# Same taxonomy, format and parser as the batch judge (batch_o4.py) — imported
# rather than restated so a single-pair spot check is directly comparable to the
# batch run's verdict for that pair.
_PROMPT = (
    "Open problem / conjecture (O) stated in paper {a_pid}:\n"
    "  {a_text}\n\n"
    "Candidate theorem (T) from a different paper {b_pid}:\n"
    "  {b_text}\n\n"
    "How does T relate to O?\n\n"
    + T.classification_block() + "\n\n"
    + T.RESPONSE_FORMAT
)


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
        prompt_version="o4_resolution_v2",
        response_parser=_parse,
        max_tokens=400,
        system="You are an expert mathematician judging whether one paper's "
               "theorem resolves another paper's open problem.",
    )
    res = judge.judge(a_pid=pa.paper_id, a_text=_node_text(na),
                      b_pid=pb.paper_id, b_text=_node_text(nb))
    p = res.parsed
    print("=== O4 JUDGE ===")
    print("RELATIONSHIP:", p.get("relationship"))
    print("VERDICT     :", p.get("verdict"),
          "(rolled up from the relationship)")
    print("SAME OBJECT :", p.get("same_object"))
    print("JUSTIFY     :", p.get("justification"))
    if p.get("mismatch"):
        print("NOTE        : the reply's own VERDICT line contradicted its "
              "RELATIONSHIP; the relationship was used.")
    print("(cached)" if res.cached else "(fresh LLM call)")


if __name__ == "__main__":
    main()
