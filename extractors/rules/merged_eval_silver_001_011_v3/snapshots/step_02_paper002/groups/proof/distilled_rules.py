import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Matches \section, \subsection, \subsubsection (with optional *) whose
# title begins with "Proof" (case-insensitive), then captures the body
# until the next sectioning command or \end{document} or end-of-string.
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub{0,2})section\s*\*?\s*\{(?P<title>[Pp]roof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:sub{0,2})section|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Helper: excluded environments (we don't want to fire inside these)
# ---------------------------------------------------------------------------

_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}.*?\\end\{\1\}',
    re.DOTALL
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) sits inside an excluded environment."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Helper: naive LaTeX cleaner
# ---------------------------------------------------------------------------

_COMMAND_RE = re.compile(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})*')
_MATH_INLINE = re.compile(r'\$[^$]*\$')
_MATH_DISPLAY = re.compile(r'\$\$.*?\$\$', re.DOTALL)
_WHITESPACE = re.compile(r'\s+')


def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain text conversion."""
    t = _MATH_DISPLAY.sub(' [MATH] ', text)
    t = _MATH_INLINE.sub(' [MATH] ', t)
    t = _COMMAND_RE.sub(' ', t)
    t = t.replace('{', '').replace('}', '')
    t = _WHITESPACE.sub(' ', t)
    return t.strip()


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result's raw_latex."""
    if not results:
        return results
    # Sort by length descending so we keep the longest unique spans
    sorted_results = sorted(results, key=lambda r: len(r['raw_latex']), reverse=True)
    kept: List[dict] = []
    seen_bodies: List[str] = []
    for r in sorted_results:
        body = r['raw_latex'].strip()
        # Skip if body is empty
        if not body:
            continue
        # Skip if this body is already covered by a kept result
        duplicate = False
        for kept_body in seen_bodies:
            if body in kept_body or kept_body in body:
                duplicate = True
                break
        if not duplicate:
            kept.append(r)
            seen_bodies.append(body)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures that the base parser misses:
      - Proofs written as subsections/sections whose title begins with 'Proof'
        (e.g. \\subsection{Proof of Theorem~\\ref{thm:main}})

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule: section/subsection/subsubsection whose title starts with Proof
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        start = m.start()
        end = m.end()

        if _inside_excluded_env(text, start, end):
            continue

        body = m.group('body').strip()
        if not body:
            continue

        title = m.group('title').strip()

        clean = _clean_latex(body)

        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    return _deduplicate(results)
