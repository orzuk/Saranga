import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \subsection{Proof of ...} or \section{Proof of ...} headings
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{(Proof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(.*?)'
    r'(?=\\(?:sub)*section|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 2: {\sc Proof of ...}. headed proofs
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+(Proof[^}]*)\}\.?\s*'
    r'(.*?)'
    r'(?=\\begin\{|\{\\sc\s+Proof|\\section|\\subsection|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3: \emph{Proof of ...} followed by content ending in \blacksquare/\qed/\square
BLACKSQUARE_PROOF_PATTERN = re.compile(
    r'(\\emph\{Proof[^}]*\}\.?\s*)'
    r'(.*?'
    r'(?:\\blacksquare|\\qed|\\square)'
    r'.*?)'
    r'(?=\n\s*\n|\\begin\{(?:section|subsection)|\\(?:sub)*section|\\end\{document\}|%%%%|\Z)',
    re.DOTALL
)

# Rule 4: Standard proof environment without IGNORECASE (exact backreference)
PROOF_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# Excluded environments pattern for overlap detection
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}.*?\\end\{\1\}',
    re.DOTALL
)

# Pattern to strip LaTeX commands for clean text
_LATEX_CMD_PATTERN = re.compile(
    r'\\(?:begin|end)\{[^}]*\}|\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})*|\\[^a-zA-Z]|\$\$.*?\$\$|\$.*?\$',
    re.DOTALL
)

_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very lightweight LaTeX -> plain text cleaner."""
    # Remove display math
    t = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    t = re.sub(r'\\\[.*?\\\]', ' ', t, flags=re.DOTALL)
    # Remove inline math
    t = re.sub(r'\$[^$]*\$', ' ', t)
    # Remove common LaTeX commands but keep their arguments
    t = re.sub(r'\\(?:emph|textbf|textit|mathrm|mathbf|text|mbox)\{([^}]*)\}', r'\1', t)
    # Remove environments
    t = re.sub(r'\\(?:begin|end)\{[^}]*\}', ' ', t)
    # Remove other commands
    t = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*', ' ', t)
    t = re.sub(r'\\[^a-zA-Z\s]', ' ', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is entirely inside an excluded environment."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and m.end() >= end:
            return True
    return False


def _overlaps(spans: List[tuple], start: int, end: int) -> bool:
    """Return True if [start, end) overlaps with any already-recorded span."""
    for s, e in spans:
        if start < e and end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures NOT already caught by the base _extract_proofs method.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    used_spans: List[tuple] = []

    # ------------------------------------------------------------------
    # Rule 4: Standard proof environments (exact case match, no IGNORECASE)
    # This fills the gap where IGNORECASE + backreference may fail.
    # ------------------------------------------------------------------
    for m in PROOF_ENV_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        body = m.group('body')
        opt = m.group('opt')
        if not body.strip():
            continue
        if _overlaps(used_spans, start, end):
            continue
        # This is a standard env — the base already handles it, but we include
        # it here only for the case where the base regex (with IGNORECASE) misses
        # an exact-case match. We tag it and deduplicate later.
        raw_latex = body
        clean = _clean_latex(body)
        name = opt.strip() if opt else None
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'PROOF_ENV_PATTERN',
            'structure_type': 'proof',
            '_span': (start, end),
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 1: Section/subsection headed proofs
    # e.g. \subsection{Proof of Theorem \ref{recover-better}}
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        section_title = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue
        if _overlaps(used_spans, start, end):
            continue
        if _inside_excluded_env(text, start, end):
            continue
        raw_latex = body
        clean = _clean_latex(body)
        # Try to extract \ref label from section title
        name = section_title
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
            '_span': (start, end),
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof of ...}. headed proofs
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        sc_title = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue
        if _overlaps(used_spans, start, end):
            continue
        if _inside_excluded_env(text, start, end):
            continue
        raw_latex = body
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': sc_title,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
            '_span': (start, end),
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 3: \emph{Proof ...} ... \blacksquare/\qed/\square
    # ------------------------------------------------------------------
    for m in BLACKSQUARE_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        header = m.group(1).strip()
        inner = m.group(2).strip()
        if not inner:
            continue
        if _overlaps(used_spans, start, end):
            continue
        if _inside_excluded_env(text, start, end):
            continue
        # The full raw_latex includes the header + body
        raw_latex = header + ' ' + inner
        clean = _clean_latex(inner)
        # Extract ref from header if present
        ref_m = _REF_PATTERN.search(header)
        name = ref_m.group(1) if ref_m else None
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'BLACKSQUARE_PROOF_PATTERN',
            'structure_type': 'proof',
            '_span': (start, end),
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Strip internal _span key before returning
    # ------------------------------------------------------------------
    for r in results:
        r.pop('_span', None)

    return results
