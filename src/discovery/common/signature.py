"""Per-node typed signature used for cross-paper retrieval matching.

A Signature captures the structural features used to score a candidate
problem-theorem pair:

    foundation_ids    set of canonical concept IDs the node grounds to
                      (from `grounded_to` edges in the paper JSON).
    operators         LaTeX command tokens in the statement (\\sum, \\int, ...).
    statement_tokens  math-aware tokens via math_tokenize.
    conclusion_type   shallow heuristic from the node text
                      (existence | inequality | equivalence | bound | other).

Pair scoring is `soft_jaccard` on statement_tokens (handles notation variants)
combined with Jaccard on foundation_ids and operators. The operator + token
features are also the fallback signal when foundation_linker recall is weak
(see foundation_audit.py for the gate condition).

Reuse:
  scripts/canonicalize/math_tokenizer.py
    math_tokenize, soft_jaccard, hard_jaccard, token_sim (Jaro-Winkler).
  src/foundation_linker.py
    not called here — we read `grounded_to` edges that the linker already
    wrote into tier3 JSONs. Edge schema (per cross_paper_analysis.py):
      {"source": "<foundation name>", "target": "<paper node id>",
       "type": "grounded_to", "idf": float, "generic": bool, ...}
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent  # .../Saranga/src
_CODE = _SRC.parent          # .../Saranga
_TOKENIZER = _CODE / "scripts" / "canonicalize"
for _p in (_SRC, _HERE, _TOKENIZER):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from math_tokenizer import math_tokenize, soft_jaccard  # noqa: E402

_INEQ_RE = re.compile(r"\\le[qg]|\\geq|\\leq|<|>")
_EQUIV_RE = re.compile(r"\\iff|\\Leftrightarrow|if and only if|equivalent", re.I)
_EXIST_RE = re.compile(r"\\exists|there (?:exists|is)|admits a", re.I)
_BOUND_KW_RE = re.compile(r"\bbound(?:ed)?\b|\bat most\b|\bat least\b", re.I)


def conclusion_type_of(text: str) -> str:
    if not text:
        return "other"
    if _EQUIV_RE.search(text):
        return "equivalence"
    if _EXIST_RE.search(text):
        return "existence"
    if _BOUND_KW_RE.search(text):
        return "bound"
    if _INEQ_RE.search(text):
        return "inequality"
    return "other"


@dataclass(frozen=True)
class Signature:
    foundation_ids: frozenset = field(default_factory=frozenset)
    operators: frozenset = field(default_factory=frozenset)
    statement_tokens: frozenset = field(default_factory=frozenset)
    conclusion_type: str = "other"


def grounded_target_set(node_id, edges: Iterable[dict],
                        include_generic: bool = False) -> set:
    """Return foundation entry names (`edge.source`) that ground a node.

    Schema from cross_paper_analysis.py::load_foundation_edges:
      edge = {"source": str, "target": str, "type": "grounded_to",
              "idf": float, "generic": bool}
    """
    out: set = set()
    if node_id is None:
        return out
    for e in edges:
        if not isinstance(e, dict):
            continue
        if e.get("type") != "grounded_to":
            continue
        if e.get("target") != node_id:
            continue
        if (not include_generic) and e.get("generic"):
            continue
        src = e.get("source")
        if src:
            out.add(src)
    return out


def signature_of(
    node: dict,
    paper_edges: Iterable[dict],
    *,
    include_generic_links: bool = False,
) -> Signature:
    """Compute a Signature for a single node from a paper JSON.

    `raw_latex` is preferred over `clean_text` for tokenization. The tier3
    extractor strips every math expression in `clean_text` to a literal
    `[MATH]` placeholder, which collapses semantically distinct theorems
    to identical token sets. Example: a Method-E dry run on the 97K-paper
    cluster corpus surfaced six top-scoring (combined=0.8) candidates that
    all matched "The functor [MATH] is an equivalence of categories" —
    pure boilerplate noise, no actual math overlap.

    Using `raw_latex` preserves \\command tokens, mathbb / mathcal / set
    notation, sup/sub symbols, and named operators, which math_tokenize
    can convert to discriminating tokens (\\sum, \\mathbb, struct_norm_2,
    rel_leq, etc.). `operators` (LaTeX backslash commands) only fire when
    raw LaTeX is available; previously they were always empty.

    `conclusion_type` heuristics work on either source — the patterns
    (\\exists, "there exists", "if and only if") appear in both — but we
    use clean_text when available for cleaner natural-language matching.
    """
    nid = node.get("id")
    # Token source: raw_latex preferred (preserves math), fall back to clean_text.
    token_text = (node.get("raw_latex")
                  or node.get("statement")
                  or node.get("clean_text")
                  or "")
    # Conclusion-type source: clean_text preferred (natural-language regex).
    ct_text = (node.get("clean_text")
               or node.get("statement")
               or node.get("raw_latex")
               or "")
    f_ids = grounded_target_set(nid, paper_edges,
                                include_generic=include_generic_links)
    tokens = math_tokenize(token_text)
    operators = {t for t in tokens if t.startswith("\\")}
    return Signature(
        foundation_ids=frozenset(f_ids),
        operators=frozenset(operators),
        statement_tokens=frozenset(tokens),
        conclusion_type=conclusion_type_of(ct_text),
    )


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 0.0
    u = a | b
    return len(a & b) / len(u) if u else 0.0


@dataclass
class SignatureScore:
    foundation_overlap: float
    operator_overlap: float
    statement_jaccard: float
    conclusion_compat: float    # 1.0 match, 0.8 either side "other", 0.5 otherwise
    combined: float


def score_pair(
    a: Signature,
    b: Signature,
    *,
    w_foundation: float = 0.5,
    w_operator: float = 0.2,
    w_statement: float = 0.3,
) -> SignatureScore:
    fj = jaccard(a.foundation_ids, b.foundation_ids)
    oj = jaccard(a.operators, b.operators)
    sj = soft_jaccard(set(a.statement_tokens), set(b.statement_tokens))
    if a.conclusion_type == b.conclusion_type:
        cc = 1.0
    elif a.conclusion_type == "other" or b.conclusion_type == "other":
        cc = 0.8
    else:
        cc = 0.5
    combined = (w_foundation * fj + w_operator * oj + w_statement * sj) * cc
    return SignatureScore(
        foundation_overlap=fj,
        operator_overlap=oj,
        statement_jaccard=sj,
        conclusion_compat=cc,
        combined=combined,
    )
