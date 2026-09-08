import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section or \subsection heading whose title starts with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{(Proof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.DOTALL
)

# Rule 2: {\sc Proof ...}. style informal proof headers
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+(Proof[^}]*)\}\.?\s*'
    r'(.*?)'
    r'(?=\\begin\{|\{\\sc\s+Proof|\\section|\\subsection|\Z)',
    re.DOTALL
)

# Helper: already-handled \begin{proof}...\end{proof} environments (to deduplicate)
_ENV_PROOF_PATTERN = re.compile(
    r'\\begin\{[Pp]roof\}.*?\\end\{[Pp]roof\}',
    re.DOTALL
)

# Environments to treat as "excluded" (we skip matches fully inside these)
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|lemma|Lemma|proposition|Proposition'
    r'|corollary|Corollary|example|Example|remark|Remark)\}.*?'
    r'\\end\{\1\}',
    re.DOTALL
)

# For extracting \ref targets from section titles
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')

# For stripping \label{...} from body
_LABEL_PATTERN = re.compile(r'\\label\{[^}]*\}')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very small LaTeX -> plain-text cleaner (no project imports)."""
    # Remove display math environments
    t = re.sub(r'\\begin\{(equation|align|gather|multline)\*?\}.*?\\end\{\1\*?\}',
               ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    t = re.sub(r'\$\$.*?\$\$', ' [MATH] ', t, flags=re.DOTALL)
    t = re.sub(r'\$[^$]*\$', ' [MATH] ', t)
    # Remove common LaTeX commands but keep their arguments
    t = re.sub(r'\\(?:emph|textbf|textit|text|mathrm|mathbf|mathit|operatorname)\{([^}]*)\}',
               r'\1', t)
    # Remove remaining commands
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    # Remove braces
    t = re.sub(r'[{}]', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) sits fully inside an excluded environment."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _collect_env_proof_bodies(text: str):
    """Collect raw bodies already captured by the base \begin{proof}...\end{proof} extractor."""
    bodies = set()
    for m in _ENV_PROOF_PATTERN.finditer(text):
        bodies.add(m.group(0))
    return bodies


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Supplement the base proof extractor with two additional patterns:

    1. SUBSECTION_PROOF_PATTERN – section/subsection headings like
       ``\\subsection{Proof of Theorem X}`` followed by free-form text.

    2. SC_PROOF_PATTERN – informal smallcaps headers like
       ``{\\sc Proof of Lemma 1}.`` followed by free-form text.

    Returns a list of dicts (one per match) that do NOT overlap with
    matches already captured by the base extractor.
    """
    results: List[dict] = []
    seen_spans: List[tuple] = []  # list of (start, end) for deduplication

    # Bodies already handled by base extractor – used for rough dedup
    env_bodies: set = _collect_env_proof_bodies(text)

    def _is_duplicate(start: int, end: int, body: str) -> bool:
        if body in env_bodies:
            return True
        for s, e in seen_spans:
            # Overlapping spans → duplicate
            if not (end <= s or start >= e):
                return True
        return False

    # ------------------------------------------------------------------
    # Rule 1: subsection / section headings "Proof of ..."
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

        if _is_duplicate(span_start, span_end, body):
            continue

        clean = _clean_latex(body)

        result = {
            "raw_latex": body,
            "clean_text": clean,
            "name": section_title,
            "env_name": "distilled",
            "rule_name": "SUBSECTION_PROOF_PATTERN",
            "structure_type": "proof",
        }
        results.append(result)
        seen_spans.append((span_start, span_end))
        env_bodies.add(body)

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof of ...}. informal headers
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        sc_title = m.group(1).strip()
        body = m.group(2).strip()

        if not body:
            continue

        span_start = m.start()
        span_end = m.end()

        if _inside_excluded_env(text, span_start, span_end):
            continue

        if _is_duplicate(span_start, span_end, body):
            continue

        clean = _clean_latex(body)

        result = {
            "raw_latex": body,
            "clean_text": clean,
            "name": sc_title if sc_title else None,
            "env_name": "distilled",
            "rule_name": "SC_PROOF_PATTERN",
            "structure_type": "proof",
        }
        results.append(result)
        seen_spans.append((span_start, span_end))
        env_bodies.add(body)

    return results
