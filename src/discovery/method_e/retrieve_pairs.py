"""Method E retrieval: pair open problems with candidate later theorems.

Inputs (all produced by Layer 1):
  problems.jsonl           — open_problem + conjecture nodes, pre-cutoff
  theorems.jsonl           — theorem/lemma/prop/corollary nodes, post-cutoff
  dedup_clusters.jsonl     — optional; collapses near-identical theorem
                             restatements to the canonical (earliest) member
  s2_citations.sqlite      — optional; powers citation-novelty flagging

Output:
  candidates.jsonl  — one row per (problem, candidate_theorem) pair, with
                      scores and metadata. Sorted across problems by
                      combined score within each problem.

Per-row schema (see Match dataclass below):
  problem_id, candidate_id, signature_score, foundation_overlap,
  operator_overlap, statement_jaccard, conclusion_compat, combined,
  cites_problem_paper, same_author, years_apart, canonical_substituted,
  problem_paper, candidate_paper, problem_text, candidate_text,
  problem_year, candidate_year

The headline retrieval for Method E is the subset where cites_problem_paper
is False — those candidates are *structurally* matched without the later
author knowing about O. K_structural vs K_citation framing.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_COMMON = _HERE.parent / "common"
_SRC = _HERE.parent.parent
for _p in (_SRC, _COMMON, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from signature import Signature, score_pair  # noqa: E402

# Lazy import for citation graph (so retrieval works without S2 in a dry run)


@dataclass
class _IndexRow:
    paper_id: str
    year: int
    category: str
    node_id: str
    node_type: str
    raw_latex: str
    clean_text: str
    name: Optional[str]
    sig: Signature

    @property
    def key(self) -> str:
        return f"{self.paper_id}::{self.node_id}"


def _row_from_dict(d: dict) -> _IndexRow:
    sig = Signature(
        foundation_ids=frozenset(d.get("sig_foundation_ids") or []),
        operators=frozenset(d.get("sig_operators") or []),
        statement_tokens=frozenset(d.get("sig_statement_tokens") or []),
        conclusion_type=d.get("conclusion_type") or "other",
    )
    return _IndexRow(
        paper_id=d["paper_id"],
        year=int(d.get("year") or 0),
        category=d.get("category") or "",
        node_id=d.get("node_id") or "",
        node_type=d.get("node_type") or "",
        raw_latex=d.get("raw_latex") or "",
        clean_text=d.get("clean_text") or "",
        name=d.get("name"),
        sig=sig,
    )


def _load_jsonl_rows(path: Path) -> list[_IndexRow]:
    out: list[_IndexRow] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(_row_from_dict(json.loads(line)))
    return out


def _load_dedup_canonical_map(path: Optional[Path]) -> dict:
    """Returns {member_key: canonical_key} mapping built from dedup clusters."""
    out: dict[str, str] = {}
    if not path or not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            canon = c.get("canonical") or {}
            canon_key = f"{canon.get('paper_id')}::{canon.get('node_id')}"
            for m in c.get("members") or []:
                k = f"{m.get('paper_id')}::{m.get('node_id')}"
                if k != canon_key:
                    out[k] = canon_key
    return out


def _build_inverted_index(theorems: list[_IndexRow]) -> dict:
    """foundation_id -> list of row indices, plus operator -> list when
    foundation_ids is empty. Operators are a fallback so query nodes with
    no foundation_ids can still retrieve candidates."""
    by_fid: dict[str, list[int]] = defaultdict(list)
    by_op: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(theorems):
        for f in r.sig.foundation_ids:
            by_fid[f].append(i)
        for o in r.sig.operators:
            by_op[o].append(i)
    return {"by_fid": dict(by_fid), "by_op": dict(by_op)}


def _candidate_indices(problem: _IndexRow, idx: dict,
                       max_per_feature: int = 5000) -> set[int]:
    """Pull row indices for any theorem sharing a foundation_id or operator
    with the problem. Hard cap per-feature so a single common feature
    (e.g. \\sum) doesn't blow up the candidate set."""
    cands: set[int] = set()
    for f in problem.sig.foundation_ids:
        bucket = idx["by_fid"].get(f) or []
        if len(bucket) > max_per_feature:
            continue
        cands.update(bucket)
    if not problem.sig.foundation_ids:
        # Fallback path: query via operators
        for o in problem.sig.operators:
            bucket = idx["by_op"].get(o) or []
            if len(bucket) > max_per_feature:
                continue
            cands.update(bucket)
    return cands


@dataclass
class Match:
    problem_id: str
    candidate_id: str
    problem_paper: str
    candidate_paper: str
    problem_year: int
    candidate_year: int
    years_apart: int
    foundation_overlap: float
    operator_overlap: float
    statement_jaccard: float
    conclusion_compat: float
    combined: float
    cites_problem_paper: Optional[bool]    # None when no citation graph loaded
    same_author: Optional[bool]
    canonical_substituted: bool
    problem_text: str
    candidate_text: str


def _rebalance_weights(problem: _IndexRow, cfg) -> tuple[float, float, float]:
    wf = cfg.sig_weight_foundation
    wo = cfg.sig_weight_operator
    ws = cfg.sig_weight_statement
    if cfg.rebalance_on_empty_foundation and not problem.sig.foundation_ids:
        ws += wf
        wf = 0.0
    return wf, wo, ws


def retrieve(
    problems_path: Path,
    theorems_path: Path,
    out_path: Path,
    *,
    dedup_path: Optional[Path] = None,
    citations_sqlite: Optional[Path] = None,
    config=None,
    progress_every: int = 100,
) -> dict:
    """Run retrieval; write candidates.jsonl. Returns summary stats."""
    # Lazy config import to avoid Method E config dep when reusing module
    if config is None:
        from me_config import MethodEConfig  # noqa: E402
        config = MethodEConfig()

    problems = _load_jsonl_rows(Path(problems_path))
    theorems = _load_jsonl_rows(Path(theorems_path))
    if not problems or not theorems:
        print(f"[retrieve] empty input: problems={len(problems)} "
              f"theorems={len(theorems)}", file=sys.stderr)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text("", encoding="utf-8")
        return {"problems": len(problems), "theorems": len(theorems),
                "candidates": 0}

    canon_map = _load_dedup_canonical_map(dedup_path)
    by_key = {r.key: r for r in theorems}

    idx = _build_inverted_index(theorems)

    # Optional citation graph
    cgraph = None
    if citations_sqlite and Path(citations_sqlite).exists():
        from citation_graph import S2CitationGraph  # noqa: E402
        cgraph = S2CitationGraph(Path(citations_sqlite))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_pairs = 0
    n_kept = 0
    n_struct = 0   # candidates that do NOT cite the problem paper

    with out_path.open("w", encoding="utf-8") as f:
        for pi, p in enumerate(problems, 1):
            wf, wo, ws = _rebalance_weights(p, config)
            cand_idx = _candidate_indices(p, idx)
            scored: list[tuple[float, Match]] = []
            for ci in cand_idx:
                cand = theorems[ci]
                n_pairs += 1
                # Year sanity: candidate must publish strictly after the
                # problem paper (otherwise it can't be a "later resolution").
                if cand.year < p.year:
                    continue
                # If canonicalization maps the candidate to an earlier paper,
                # check the canonical's year instead.
                canon_substituted = False
                if cand.key in canon_map:
                    canon_key = canon_map[cand.key]
                    canon_row = by_key.get(canon_key)
                    if canon_row is not None:
                        if canon_row.year < p.year:
                            continue  # canonical predates the problem
                        cand = canon_row
                        canon_substituted = True

                sc = score_pair(p.sig, cand.sig,
                                w_foundation=wf, w_operator=wo, w_statement=ws)
                if sc.combined < config.score_threshold:
                    continue

                # Citation novelty
                cites = None
                same_author = None
                if cgraph is not None:
                    try:
                        cites = cgraph.cites(cand.paper_id, p.paper_id)
                    except Exception:
                        cites = None
                    if cites is not None:
                        # Same-author flag (cheap heuristic)
                        try:
                            a_set = set(cgraph.authors_of(p.paper_id) or [])
                            b_set = set(cgraph.authors_of(cand.paper_id) or [])
                            if a_set and b_set:
                                same_author = bool(a_set & b_set)
                        except Exception:
                            same_author = None

                m = Match(
                    problem_id=p.key,
                    candidate_id=cand.key,
                    problem_paper=p.paper_id,
                    candidate_paper=cand.paper_id,
                    problem_year=p.year,
                    candidate_year=cand.year,
                    years_apart=cand.year - p.year,
                    foundation_overlap=sc.foundation_overlap,
                    operator_overlap=sc.operator_overlap,
                    statement_jaccard=sc.statement_jaccard,
                    conclusion_compat=sc.conclusion_compat,
                    combined=sc.combined,
                    cites_problem_paper=cites,
                    same_author=same_author,
                    canonical_substituted=canon_substituted,
                    problem_text=p.clean_text[:1500],
                    candidate_text=cand.clean_text[:1500],
                )
                scored.append((sc.combined, m))

            # Keep top-K per problem
            scored.sort(key=lambda kv: -kv[0])
            for _s, m in scored[: config.top_k_per_problem]:
                f.write(json.dumps(asdict(m), ensure_ascii=False) + "\n")
                n_kept += 1
                if m.cites_problem_paper is False:
                    n_struct += 1

            if pi % progress_every == 0:
                print(f"[retrieve] problems={pi}/{len(problems)} "
                      f"pairs={n_pairs:,} kept={n_kept:,}",
                      file=sys.stderr)

    if cgraph is not None:
        cgraph.close()

    print(f"[retrieve] DONE problems={len(problems)} theorems={len(theorems)} "
          f"pairs_inspected={n_pairs:,} candidates_kept={n_kept:,} "
          f"K_structural~{n_struct:,} -> {out_path}", file=sys.stderr)
    return {
        "problems": len(problems),
        "theorems": len(theorems),
        "pairs_inspected": n_pairs,
        "candidates_kept": n_kept,
        "k_structural_proxy": n_struct,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problems", required=True)
    ap.add_argument("--theorems", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dedup", default=None)
    ap.add_argument("--citations-sqlite", default=None)
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--score-threshold", type=float, default=None)
    args = ap.parse_args()

    from me_config import MethodEConfig  # noqa: E402
    cfg = MethodEConfig()
    if args.top_k is not None:
        cfg.top_k_per_problem = args.top_k
    if args.score_threshold is not None:
        cfg.score_threshold = args.score_threshold

    retrieve(
        problems_path=Path(args.problems),
        theorems_path=Path(args.theorems),
        out_path=Path(args.out),
        dedup_path=Path(args.dedup) if args.dedup else None,
        citations_sqlite=Path(args.citations_sqlite) if args.citations_sqlite else None,
        config=cfg,
    )


if __name__ == "__main__":
    main()
