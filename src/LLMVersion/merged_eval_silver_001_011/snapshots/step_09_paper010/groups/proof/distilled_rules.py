import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section or \subsection whose title begins with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:(?:sub){0,2}section)\*?\s*\{(Proof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(.*?)'
    r'(?=\\(?:(?:sub){0,2}section)|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 2: {\sc Proof ...}. style informal proof headers
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+(Proof[^}]*)\}\.?\s*'
    r'(.*?)'
    r'(?=\{\\sc\s+Proof|\{\\textsc\s+Proof|\\(?:(?:sub){0,2}section)|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3: \emph{Proof ...}. style inline proofs terminated by \blacksquare/\qed/\square
BLACKSQUARE_PROOF_PATTERN = re.compile(
    r'(\\emph\{Proof[^}]*\}\.?\s*'
    r'.*?'
    r'(?:\\blacksquare|\\qed|\\square))'
    r'(?=\s*\n\s*\n|\s*\\begin\{|\s*\\(?:(?:sub){0,2}section)|\s*\\end\{document\}|%%%%|\Z)',
    re.DOTALL
)

# Excluded environments – content inside these should not be re-extracted
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|theorem|lemma|proposition|corollary|example|remark)\}.*?'
    r'\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)

# For stripping latex commands in clean_text
_LATEX_CMD_PATTERN = re.compile(
    r'\\(?:begin|end)\{[^}]*\}'
    r'|\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*'
    r'|[{}$]'
    r'|\\\\'
    r'|\\[^a-zA-Z]'
)

_MULTI_SPACE = re.compile(r'\s{2,}')

# Header \ref pattern
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very simple LaTeX -> plain text cleaner."""
    result = _LATEX_CMD_PATTERN.sub(' ', text)
    result = _MULTI_SPACE.sub(' ', result)
    return result.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is fully inside an excluded environment."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _overlaps(spans: List[tuple], new_start: int, new_end: int) -> bool:
    """Return True if [new_start, new_end) overlaps any existing span."""
    for (s, e) in spans:
        if new_start < e and new_end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures NOT already caught by the base parser.
    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    used_spans: List[tuple] = []

    # ------------------------------------------------------------------
    # Rule 1 – \section/\subsection{Proof of ...}
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        section_title = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue
        span_start = m.start()
        span_end = m.end()
        if _inside_excluded_env(text, span_start, span_end):
            continue
        if _overlaps(used_spans, span_start, span_end):
            continue
        used_spans.append((span_start, span_end))
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': section_title,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 2 – {\sc Proof of ...}. style
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        header_title = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue
        span_start = m.start()
        span_end = m.end()
        if _inside_excluded_env(text, span_start, span_end):
            continue
        if _overlaps(used_spans, span_start, span_end):
            continue
        used_spans.append((span_start, span_end))
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': header_title,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 3 – \emph{Proof ...}. ... \blacksquare/\qed/\square
    # ------------------------------------------------------------------
    for m in BLACKSQUARE_PROOF_PATTERN.finditer(text):
        full_match = m.group(1).strip()
        if not full_match:
            continue
        span_start = m.start()
        span_end = m.end()
        if _inside_excluded_env(text, span_start, span_end):
            continue
        if _overlaps(used_spans, span_start, span_end):
            continue
        # Extract name from the \emph{...} header
        emph_m = re.match(r'\\emph\{([^}]*)\}', full_match)
        name = emph_m.group(1).strip() if emph_m else None
        # The body is the full match (header + content)
        # For raw_latex we include everything; clean_text strips commands
        used_spans.append((span_start, span_end))
        results.append({
            'raw_latex': full_match,
            'clean_text': _clean_latex(full_match),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'BLACKSQUARE_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    return results
