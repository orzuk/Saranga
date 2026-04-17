"""
Improved sigma: α-rename + split-field comparison.

Uses:
  - α-rename via canonical fields (reads statement_canonical_local etc.)
  - Split-field: assumptions and conclusions compared separately with
    weighted average (0.2 assum + 0.7 concl + 0.1 name)
  - Hard Jaccard on natural tokens (proven to work, ratio 2.46)

Does NOT use (kept in math_tokenizer.py for future experiments):
  - Constructed tokens (operator/structure tokens — inflate negatives)
  - Soft Jaccard / Monge-Elkan (partial credit drowns signal)

Usage:
    python scripts/run_alignment_benchmark.py \
        --sigma-import scripts.canonicalize.improved_sigma.sigma ...
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_REPO_SCRIPTS))

from graph_alignment import type_compat  # type: ignore

# ── Weights for field splitting (tune as needed) ─────────────────────────
W_NAME = 0.1
W_ASSUMPTIONS = 0.2
W_CONCLUSIONS = 0.7

# ── English stop words (always removed from token bag) ───────────────────
ENGLISH_STOP_WORDS = {
    # Articles / determiners
    "the", "a", "an", "this", "that", "these", "those",
    # Prepositions
    "of", "in", "to", "for", "with", "on", "at", "from", "by", "as",
    "into", "through", "between", "under", "over", "above", "below",
    "about", "after", "before", "during", "without", "within",
    # Conjunctions
    "and", "or", "but", "nor", "so", "yet",
    # Pronouns
    "we", "it", "its", "one", "they", "their", "our",
    # Common verbs / auxiliaries
    "is", "are", "be", "was", "were", "been", "being",
    "has", "have", "had", "do", "does", "did",
    "can", "may", "will", "shall", "should", "would", "could", "must",
    # Math-prose function words
    "if", "then", "such", "where", "when", "not", "no", "than",
    "there", "each", "every", "any", "all", "some",
    "also", "hence", "thus", "therefore", "moreover", "furthermore",
    "respectively", "similarly", "conversely", "otherwise",
    "denote", "denoted", "denotes", "called", "say", "said",
    "let", "given", "suppose", "assume", "consider",
    "holds", "satisfies", "follows", "implies", "yields", "gives",
    "note", "observe", "recall", "see", "show", "write",
    # Very short words that are noise
    "at", "so", "up",
}

# ── Leading type-label stripping ─────────────────────────────────────────
# Remove "Proof of ...", "Theorem 3.1:", "Definition:" etc. at the START
# of a statement when the label word matches the node type. Does NOT
# remove these words from the middle of text (e.g., "by definition" stays).

_TYPE_LABELS = {
    "theorem":     ["theorem", "thm"],
    "lemma":       ["lemma", "lem"],
    "proposition": ["proposition", "prop"],
    "corollary":   ["corollary", "cor"],
    "proof":       ["proof", "pf"],
    "definition":  ["definition", "def"],
    "claim":       ["claim"],
    "conjecture":  ["conjecture", "conj"],
    "remark":      ["remark", "rem"],
    "example":     ["example", "ex"],
    "exercise":    ["exercise"],
    "algorithm":   ["algorithm", "alg"],
}

# Pattern: label word + optional numbering + optional punctuation at start
# Matches: "Proof of Theorem 3.1:", "Theorem 2.5.", "Definition (Norm):", etc.
_LEADING_LABEL_RE_CACHE = {}


def _strip_leading_label(text: str, node_type: str) -> str:
    """Remove the leading type label from text if it matches node_type.

    'Proof of Theorem 3.1: We show...' (node_type=proof) → 'We show...'
    'Theorem 3.1. For every...'       (node_type=theorem) → 'For every...'

    Does NOT affect labels in the middle of text.
    """
    if not text or not node_type:
        return text
    labels = _TYPE_LABELS.get(node_type.lower(), [])
    if not labels:
        return text

    for label in labels:
        if label not in _LEADING_LABEL_RE_CACHE:
            # Match: label + optional " of" + optional number/punct + colon/period/space
            _LEADING_LABEL_RE_CACHE[label] = re.compile(
                r"^\s*" + re.escape(label)
                + r"(?:\s+of)?"                     # optional " of"
                + r"(?:\s+\w+)?"                    # optional "Theorem" after "Proof of"
                + r"(?:\s*[\d.]+)*"                 # optional numbering "3.1"
                + r"\s*[:.;,\-)\]]*\s*",            # optional punctuation
                re.IGNORECASE,
            )
        pat = _LEADING_LABEL_RE_CACHE[label]
        if pat.match(text):
            text = pat.sub("", text, count=1)
            break
    return text


# ── Tokenizer (natural tokens, stop-word filtered) ───────────────────────
_TOKEN_RE = re.compile(r"[a-zA-Z]+|\\[a-zA-Z]+|[0-9]+")


def _tokenize(text: str, node_type: str = "") -> set[str]:
    """Tokenize text with stop-word removal and leading-label stripping."""
    if not text:
        return set()
    # Strip leading type label
    text = _strip_leading_label(text, node_type)
    # Tokenize
    raw = set(t.lower() for t in _TOKEN_RE.findall(str(text)))
    # Remove stop words
    return raw - ENGLISH_STOP_WORDS


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


# ── Field access helpers ─────────────────────────────────────────────────

def _get_text(node: dict, field: str) -> str:
    """Read canonical version of a field if available, else original."""
    canonical = f"{field}_canonical_local"
    val = node.get(canonical) or node.get(field, "")
    if isinstance(val, list):
        return " ".join(str(x) for x in val)
    return str(val) if val else ""


def _get_list_text(node: dict, field: str) -> str:
    """Read canonical list field, concatenate to string."""
    canonical = f"{field}_canonical_local"
    items = node.get(canonical) or node.get(field, [])
    if isinstance(items, list):
        return " ".join(str(x) for x in items)
    return str(items) if items else ""


def _full_text(node: dict) -> str:
    """All text fields concatenated (fallback for nodes without split fields)."""
    parts = [
        _get_text(node, "name"),
        _get_text(node, "statement"),
        _get_list_text(node, "assumptions"),
        _get_list_text(node, "conclusions"),
    ]
    return " ".join(p for p in parts if p)


# ── Main sigma ───────────────────────────────────────────────────────────

def sigma(node_a: dict, node_b: dict) -> float:
    """Improved sigma: α-rename (via canonical fields) + split-field + hard Jaccard.

    Reads *_canonical_local fields when present (from canonicalize_paper),
    falls back to original fields otherwise.
    """
    assum_a = _get_list_text(node_a, "assumptions")
    assum_b = _get_list_text(node_b, "assumptions")
    concl_a = _get_list_text(node_a, "conclusions")
    concl_b = _get_list_text(node_b, "conclusions")

    has_split_a = bool(assum_a.strip()) or bool(concl_a.strip())
    has_split_b = bool(assum_b.strip()) or bool(concl_b.strip())

    ta = node_a.get("type", node_a.get("kind", ""))
    tb = node_b.get("type", node_b.get("kind", ""))

    if has_split_a and has_split_b:
        s = (W_NAME * _jaccard(_tokenize(_get_text(node_a, "name"), ta),
                                _tokenize(_get_text(node_b, "name"), tb))
             + W_ASSUMPTIONS * _jaccard(_tokenize(assum_a, ta), _tokenize(assum_b, tb))
             + W_CONCLUSIONS * _jaccard(_tokenize(concl_a, ta), _tokenize(concl_b, tb)))
    else:
        s = _jaccard(_tokenize(_full_text(node_a), ta), _tokenize(_full_text(node_b), tb))

    # ta, tb already extracted above (before split logic)
    return s * type_compat(ta, tb)
