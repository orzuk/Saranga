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

# Rule 2: {\sc Proof of ...}. style smallcaps-headed proofs
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+(Proof[^}]*)\}\.?\s*'
    r'(.*?)'
    r'(?=\\begin\{|\{\\sc\s+Proof|\\section|\\subsection|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3: \emph{Proof of ...}. ... \blacksquare/\qed/\square style inline proofs
BLACKSQUARE_PROOF_PATTERN = re.compile(
    r'(\\emph\{Proof[^}]*\}\.?\s*'
    r'.*?'
    r'(?:\\blacksquare|\\qed|\\square)'
    r'.*?)'
    r'(?=\n\s*\n|\\begin\{|\\section|\\subsection|\\end\{document\}|%%%%|\Z)',
    re.DOTALL
)

# Helper: header \ref pattern
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')

# Excluded environments (proof bodies that the base already handles)
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof)\}.*?\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain text conversion."""
    # Remove comments
    t = re.sub(r'%[^\n]*', '', text)
    # Remove common commands, keep argument
    t = re.sub(r'\\(?:emph|textbf|textit|text|mathrm|mathbf|mathit|operatorname)\{([^}]*)\}', r'\1', t)
    # Remove \label, \ref, etc.
    t = re.sub(r'\\(?:label|ref|eqref|autoref|cite)\{[^}]*\}', '', t)
    # Remove display math environments (rough)
    t = re.sub(r'\\begin\{(?:equation|align|aligned|gather|multline)\*?\}.*?\\end\{(?:equation|align|aligned|gather|multline)\*?\}', ' [MATH] ', t, flags=re.DOTALL)
    # Remove $...$ inline math
    t = re.sub(r'\$\$.*?\$\$', ' [MATH] ', t, flags=re.DOTALL)
    t = re.sub(r'\$[^$]*\$', '[MATH]', t)
    # Remove remaining commands
    t = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', '', t)
    t = re.sub(r'\\[a-zA-Z]+\*?', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside a proof environment."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _spans_overlap(spans: List[tuple], start: int, end: int) -> bool:
    """Return True if [start, end) overlaps with any span in spans."""
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
    used_spans: List[tuple] = []  # (start, end) of already-added matches

    # ------------------------------------------------------------------
    # Rule 1: \subsection{Proof of ...} / \section{Proof of ...}
    # ------------------------------------------------------------------
    for match in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = match.span()
        if _inside_excluded_env(text, start, end):
            continue
        if _spans_overlap(used_spans, start, end):
            continue

        section_title = match.group(1).strip()
        body = match.group(2).strip()
        if not body:
            continue

        clean = _clean_latex(body)
        name = section_title if section_title else None

        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof of ...}. style
    # ------------------------------------------------------------------
    for match in SC_PROOF_PATTERN.finditer(text):
        start, end = match.span()
        if _inside_excluded_env(text, start, end):
            continue
        if _spans_overlap(used_spans, start, end):
            continue

        sc_title = match.group(1).strip()
        body = match.group(2).strip()
        if not body:
            continue

        # The raw_latex should include the header for context
        full_raw = match.group(0).strip()
        clean = _clean_latex(body)

        results.append({
            'raw_latex': full_raw,
            'clean_text': clean,
            'name': sc_title if sc_title else None,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 3: \emph{Proof of ...}. ... \blacksquare/\qed/\square
    # ------------------------------------------------------------------
    for match in BLACKSQUARE_PROOF_PATTERN.finditer(text):
        start, end = match.span()
        if _inside_excluded_env(text, start, end):
            continue
        if _spans_overlap(used_spans, start, end):
            continue

        full_body = match.group(1).strip()
        if not full_body:
            continue

        # Check overlap with rule-1 or rule-2 results by content
        already = any(
            full_body in r['raw_latex'] or r['raw_latex'] in full_body
            for r in results
        )
        if already:
            continue

        clean = _clean_latex(full_body)

        # Try to extract name from \emph{Proof of ...} header
        emph_header_match = re.match(r'\\emph\{(Proof[^}]*)\}', full_body)
        name = emph_header_match.group(1).strip() if emph_header_match else None

        results.append({
            'raw_latex': full_body,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'BLACKSQUARE_PROOF_PATTERN',
            'structure_type': 'proof',
        })
        used_spans.append((start, end))

    return results
