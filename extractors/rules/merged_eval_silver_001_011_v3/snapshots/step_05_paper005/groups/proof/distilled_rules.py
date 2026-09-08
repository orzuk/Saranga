import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section or \subsection (any depth) whose title begins with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:(?:sub)*section)\s*\*?\s*\{([^}]*\bProof\b[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(.*?)'
    r'(?=\\(?:(?:sub)*section)\s*\*?\s*\{|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule 2: {\sc Proof ...} or \textsc{Proof ...} informal proof header
SC_PROOF_PATTERN = re.compile(
    r'(?:'
        r'\{\\sc\s+Proof[^}]*\}'
        r'|\\textsc\{Proof[^}]*\}'
    r')'
    r'[.:]?\s*'
    r'(.*?)'
    r'(?='
        r'\\section|\\subsection|\\appendix'
        r'|\\begin\{'
        r'|\{\\sc\s+Proof'
        r'|\\textsc\{Proof'
        r'|\\end\{document\}'
        r'|\Z'
    r')',
    re.DOTALL
)

# Rule 3: standalone \emph{Proof ...} at paragraph start
STANDALONE_EMPH_PROOF_PATTERN = re.compile(
    r'(?:(?:^|\n\n|\r\n\r\n)[ \t]*)'
    r'\\emph\{Proof[^}]*\}'
    r'[.:]?\s*'
    r'(.*?)'
    r'(?:'
        r'\\(?:blacksquare|square|qed)\b'
        r'|\\end\{(?:aligned|equation\*?|align\*?|gather\*?)\}\s*\$\$'
        r'|\\begin\{'
        r'|\\(?:section|subsection|subsubsection)\b'
        r'|\\end\{document\}'
        r'|\Z'
    r')',
    re.DOTALL
)

# Pattern to detect excluded environments (proof, example, remark already handled by base)
_EXCL_ENV_BEGIN = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}',
    re.IGNORECASE
)
_EXCL_ENV_END = re.compile(
    r'\\end\{(proof|Proof|example|Example|remark|Remark)\}',
    re.IGNORECASE
)

# Reference pattern in headers
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Minimal LaTeX -> plain text conversion."""
    # Remove comments
    result = re.sub(r'%[^\n]*\n', '\n', text)
    # Remove display math environments
    result = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}',
                    ' [formula] ', result, flags=re.DOTALL)
    # Remove inline math
    result = re.sub(r'\$\$.*?\$\$', ' [formula] ', result, flags=re.DOTALL)
    result = re.sub(r'\$[^$]*\$', ' [formula] ', result, flags=re.DOTALL)
    # Remove common macros
    result = re.sub(r'\\(?:label|ref|eqref|cite|autoref)\{[^}]*\}', '', result)
    result = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb)\{([^}]*)\}', r'\1', result)
    result = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', result)
    result = re.sub(r'[{}]', '', result)
    result = re.sub(r'\s+', ' ', result)
    return result.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the span [start, end) is inside a proof/example/remark
    environment (those are already captured by the base extractor).
    """
    before = text[:start]
    opens = len(_EXCL_ENV_BEGIN.findall(before))
    closes = len(_EXCL_ENV_END.findall(before))
    # If there are more opens than closes, we're inside an excluded env
    return opens > closes


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or b_end <= a_start)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    results: List[dict] = []
    seen_spans: List[tuple] = []  # (start, end)

    def _add(raw_latex: str, name, rule_name: str, span_start: int, span_end: int):
        """Validate, deduplicate, and append a result dict."""
        raw_latex = raw_latex.strip()
        if not raw_latex:
            return
        # Skip if inside an already-handled environment
        if _inside_excluded_env(text, span_start, span_end):
            return
        # Deduplicate overlapping spans
        for (s, e) in seen_spans:
            if _spans_overlap(span_start, span_end, s, e):
                return
        seen_spans.append((span_start, span_end))
        results.append({
            'raw_latex': raw_latex,
            'clean_text': _clean_latex(raw_latex),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 1: \(sub)section{Proof of ...} bodies
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        section_title = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue
        span_start = m.start()
        span_end = m.end()
        _add(body, section_title, 'SUBSECTION_PROOF_PATTERN', span_start, span_end)

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof ...}. body  (small-caps informal proof headers)
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        body = m.group(1).strip()
        if not body:
            continue
        span_start = m.start()
        span_end = m.end()
        _add(body, None, 'SC_PROOF_PATTERN', span_start, span_end)

    # ------------------------------------------------------------------
    # Rule 3: \emph{Proof of ...} at paragraph start
    # ------------------------------------------------------------------
    for m in STANDALONE_EMPH_PROOF_PATTERN.finditer(text):
        body = m.group(1).strip()
        if not body:
            continue
        span_start = m.start()
        span_end = m.end()
        # Extract optional name from the \emph{...} header
        header_text = m.group(0)
        header_end = m.start(1) - m.start()
        header_part = header_text[:header_end]
        emph_match = re.search(r'\\emph\{([^}]*)\}', header_part)
        name = emph_match.group(1).strip() if emph_match else None
        _add(body, name, 'STANDALONE_EMPH_PROOF_PATTERN', span_start, span_end)

    return results
