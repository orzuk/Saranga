"""T-PLAG P4 — LLM-as-judge over the triage shortlist.

For each top paper pair from triage_plag.py, pull the two reused nodes' full text
(raw LaTeX preferred, so [MATH]-masking doesn't hide the distinguishing math) and
ask the model to CLASSIFY the reuse:

  VERBATIM | PARAPHRASE | CONCEPTUAL_REUSE | LEGITIMATE_CITATION | INDEPENDENT

This is the expensive rung, run only on candidates. It reuses common.llm_judge
(cached) exactly like open_problems/o4_judge. Only the papers referenced by the
judged rows are loaded from --root (one targeted corpus walk), so it runs against
the full 100k/3M corpus without loading everything.

    python discovery_suite/plagiarism/p4_judge.py \
        --triage discovery_suite/plagiarism/runs/plag_triage_top.csv \
        --root $ROOT --top 50 --model sonnet

NOTE: the roadmap wants a citation-graph gate so legitimate quotation-with-
citation isn't flagged as reuse. That's a follow-up (common/citation_graph.py);
here LEGITIMATE_CITATION is inferred from text only.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
for _p in (_REPO / "src", _REPO / "src" / "discovery", _REPO / "discovery_suite"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import _lazy_walk, _build_paper, DEFAULT_ROOT  # noqa: E402


def _load_dotenv() -> None:
    env = _REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _load_needed(root: Path, pids: set[str]) -> dict[str, object]:
    """One corpus walk, loading only papers whose id is in `pids`. Stops early
    once all are found so it doesn't traverse the whole 100k/3M tree."""
    found: dict[str, object] = {}
    for path in _lazy_walk(root):
        p = _build_paper(path, root)
        if p is None or p.paper_id not in pids or p.paper_id in found:
            continue
        found[p.paper_id] = p
        if len(found) == len(pids):
            break
    return found


def _node_text(papers: dict, handle: str) -> str:
    pid, nid = handle.split("::", 1)
    p = papers.get(pid)
    if p is None:
        return ""
    for n in p.nodes:
        if str(n.get("id")) == nid:
            raw = (n.get("raw_latex") or "").strip()
            return raw or (n.get("statement") or n.get("clean_text") or "").strip()
    return ""


_PROMPT = (
    "Two mathematical statements from DIFFERENT papers were flagged as lexically "
    "near-identical. Classify their relationship.\n\n"
    "Statement A — older paper {a_pid} (the presumed source):\n  {a_text}\n\n"
    "Statement B — newer paper {b_pid}:\n  {b_text}\n\n"
    "\\-macros are paper-specific; judge the underlying math, not just wording. "
    "Classify as:\n"
    "  VERBATIM            — copied essentially word-for-word\n"
    "  PARAPHRASE          — same claim, reworded\n"
    "  CONCEPTUAL_REUSE    — same idea/result, independently expressed\n"
    "  LEGITIMATE_CITATION — standard/textbook statement or explicitly attributed\n"
    "  INDEPENDENT         — coincidental lexical overlap, not actual reuse\n\n"
    "Answer in exactly this format:\n"
    "CLASSIFICATION: <one label>\n"
    "SAME_CLAIM: YES | NO\n"
    "JUSTIFICATION: <1-3 sentences>"
)


def _parse(raw: str) -> dict:
    out = {"classification": "", "same_claim": "", "justification": "", "raw": raw}
    for line in raw.splitlines():
        u = line.upper()
        if u.startswith("CLASSIFICATION:"):
            out["classification"] = line.split(":", 1)[1].strip()
        elif u.startswith("SAME_CLAIM:"):
            out["same_claim"] = line.split(":", 1)[1].strip()
        elif u.startswith("JUSTIFICATION:"):
            out["justification"] = line.split(":", 1)[1].strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triage", required=True, help="triage_plag.py output CSV")
    ap.add_argument("--root", default=None, help="corpus root (default: local portal)")
    ap.add_argument("--out", default=None, help="judged CSV (default: <triage>_judged.csv)")
    ap.add_argument("--top", type=int, default=50, help="judge the top N triage rows")
    ap.add_argument("--model", default="sonnet", help="haiku | sonnet | opus")
    args = ap.parse_args()

    _load_dotenv()
    from common.llm_judge import LLMJudge

    # force string dtype: arXiv ids like 1002.1960 would otherwise be read as
    # floats (-> 1002.196) and never match a loaded paper.
    df = pd.read_csv(args.triage, dtype={
        "source_paper": str, "target_paper": str, "source_cat": str,
        "target_cat": str, "best_source_key": str, "best_target_key": str}).head(args.top)
    if df.empty:
        raise SystemExit("triage CSV is empty — nothing to judge")

    root = Path(args.root) if args.root else DEFAULT_ROOT
    pids = set(df.source_paper.astype(str)) | set(df.target_paper.astype(str))
    print(f"[p4] loading {len(pids)} papers referenced by top {len(df)} pairs from {root} …",
          flush=True)
    papers = _load_needed(root, pids)
    print(f"[p4] loaded {len(papers)}/{len(pids)} papers", flush=True)

    judge = LLMJudge(
        model=args.model,
        cache_path=_HERE.parent / "eval_harness" / "runs" / "p4_judge_cache.sqlite",
        prompt_template=_PROMPT,
        prompt_version="p4_reuse_v1",
        response_parser=_parse,
        max_tokens=400,
        system="You are an expert mathematician auditing whether one paper reused "
               "another paper's statement, and how.",
    )

    out_path = Path(args.out) if args.out else Path(args.triage).with_name(
        Path(args.triage).stem + "_judged.csv")
    n_fresh = 0
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["score_max", "n_shared_nodes", "source_paper", "target_paper",
                    "source_cat", "target_cat", "cross_category", "same_year",
                    "classification", "same_claim", "justification",
                    "best_source_key", "best_target_key"])
        for _, r in df.iterrows():
            a_text = _node_text(papers, str(r.best_source_key))
            b_text = _node_text(papers, str(r.best_target_key))
            if not a_text or not b_text:
                verdict = {"classification": "UNAVAILABLE", "same_claim": "",
                           "justification": "node text not found in corpus"}
                cached = True
            else:
                res = judge.judge(a_pid=str(r.source_paper), a_text=a_text,
                                  b_pid=str(r.target_paper), b_text=b_text)
                verdict, cached = res.parsed, res.cached
                n_fresh += 0 if cached else 1
            w.writerow([r.score_max, r.n_shared_nodes, r.source_paper, r.target_paper,
                        r.source_cat, r.target_cat, r.cross_category, r.same_year,
                        verdict.get("classification"), verdict.get("same_claim"),
                        verdict.get("justification"),
                        r.best_source_key, r.best_target_key])
            print(f"  {r.score_max:.2f} {r.source_paper}->{r.target_paper}: "
                  f"{verdict.get('classification')}"
                  f"{'' if cached else '  (fresh)'}", flush=True)

    print(f"\n[p4] judged {len(df)} pairs ({n_fresh} fresh LLM calls) -> {out_path}",
          flush=True)


if __name__ == "__main__":
    main()
