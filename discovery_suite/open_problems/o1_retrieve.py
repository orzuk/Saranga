"""T-OPEN O1 — typed, temporal-directed retrieval of problem→theorem candidates.

Light rung: index open_problem/conjecture nodes (queries) and theorem-like nodes
(candidates); for each problem, return the top-k theorem nodes by token-overlap
(Jaccard on normalized node text), enforcing:
  * different paper (a paper resolving its own problem is not the target case),
  * candidate.year >= problem.year (a solution can't predate the problem).

This mirrors the retrieval stage of src/discovery/method_e (which additionally
does foundation-signature scoring, dedup, S2 citation-novelty, and an LLM judge).
O3/O4 reuse that module; O1 is the cheap, dependency-free entry point + the hook
the eval harness scores against.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import node_norm_text  # noqa: E402

PROBLEM_TYPES = {"open_problem", "conjecture", "problem"}
THEOREM_TYPES = {"theorem", "lemma", "proposition", "corollary", "claim"}


def _tokset(node: dict) -> set[str]:
    return set(node_norm_text(node).split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def retrieve(
    papers: Sequence,
    *,
    top_k: int = 20,
    min_score: float = 0.05,
    min_words: int = 6,
    on_progress=None,
) -> list[tuple[str, str, float]]:
    """Return ranked (problem_key, theorem_key, score) across the corpus.

    ``on_progress(done, total)`` (optional) fires every 100 problems so the
    O(#problems x #theorems) scan reports progress on big corpora.
    """
    problems, theorems = [], []
    for p in papers:
        for n in p.nodes:
            t = (n.get("type") or "").lower()
            toks = _tokset(n)
            if len(toks) < min_words:
                continue
            rec = (f"{p.paper_id}::{n.get('id')}", p.paper_id, p.year, toks)
            if t in PROBLEM_TYPES:
                problems.append(rec)
            elif t in THEOREM_TYPES:
                theorems.append(rec)

    out: list[tuple[str, str, float]] = []
    n_prob = len(problems)
    for i, (pk, ppid, pyear, ptoks) in enumerate(problems):
        if on_progress is not None and i and i % 100 == 0:
            on_progress(i, n_prob)
        scored = []
        for tk, tpid, tyear, ttoks in theorems:
            if tpid == ppid or tyear < pyear:
                continue
            s = _jaccard(ptoks, ttoks)
            if s >= min_score:
                scored.append((tk, s))
        scored.sort(key=lambda x: -x[1])
        for tk, s in scored[:top_k]:
            out.append((pk, tk, s))
    out.sort(key=lambda x: -x[2])
    return out
