import re
from typing import List, Dict

# Pattern to match proposition environments with optional arguments and labels
# Handles whitespace between \begin{...} and optional [...]
_PROPOSITION_ENV_NAMES = [
    'proposition', 'Proposition', 'prop', 'Prop',
]

_env_names_pattern = "|".join(re.escape(n) for n in _PROPOSITION_ENV_NAMES)

# Main pattern for proposition environments
# Allows optional whitespace before optional arguments [...]
# Uses DOTALL so .*? matches across newlines
_PROPOSITION_ENV_RE = re.compile(
    r"\\begin\{(" + _env_names_pattern + r")\}"
    r"\s*(?:\[([^\]]*)\])?"
    r"(.*?)"
    r"\\end\{\1\}",
    re.DOTALL | re.IGNORECASE
)

# Patterns for excluded environments (we should not extract from inside these)
_EXCLUDED_ENV_NAMES = [
    'proof', 'example', 'remark', 'note', 'exercise',
]
_EXCLUDED_ENV_RE = re.compile(
    r"\\begin\{(" + "|".join(re.escape(n) for n in _EXCLUDED_ENV_NAMES) + r")\}"
    r".*?"
    r"\\end\{\1\}",
    re.DOTALL | re.IGNORECASE
)

# LaTeX command stripping patterns
_LATEX_CMD_RE = re.compile(r"\\(?:emph|textbf|textit|textsf|textrm|texttt|mathrm|mathbf|mathit|mathcal|mathbb|operatorname)\{([^}]*)\}")
_LATEX_LABEL_RE = re.compile(r"\\label\{[^}]*\}")
_LATEX_REF_RE = re.compile(r"\\(?:ref|eqref|cite)\{[^}]*\}")
_LATEX_SIMPLE_CMD_RE = re.compile(r"\\(?:newline|noindent|par|smallskip|medskip|bigskip|\\)\b\s*")
_LATEX_BEGIN_END_RE = re.compile(r"\\(?:begin|end)\{[^}]*\}")
_LATEX_GENERIC_CMD_RE = re.compile(r"\\([a-zA-Z]+)")
_LATEX_BRACES_RE = re.compile(r"[{}]")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _clean_latex(text: str) -> str:
    """Strip LaTeX commands to produce a simplified plain-text version."""
    s = text.strip()
    # Remove \label{...}
    s = _LATEX_LABEL_RE.sub("", s)
    # Remove \ref, \eqref, \cite
    s = _LATEX_REF_RE.sub("", s)
    # Remove \begin{...} and \end{...}
    s = _LATEX_BEGIN_END_RE.sub("", s)
    # Unwrap formatting commands like \emph{...}, \textbf{...}
    for _ in range(3):  # multiple passes for nested commands
        s = _LATEX_CMD_RE.sub(r"\1", s)
    # Remove simple commands
    s = _LATEX_SIMPLE_CMD_RE.sub(" ", s)
    # Replace remaining \command with the command name (heuristic)
    s = _LATEX_GENERIC_CMD_RE.sub(r"\1", s)
    # Remove stray braces
    s = _LATEX_BRACES_RE.sub("", s)
    # Collapse whitespace
    s = _MULTI_SPACE_RE.sub(" ", s)
    return s.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Check if a span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        exc_start = m.start()
        exc_end = m.end()
        # If the match is strictly contained within an excluded env
        if exc_start < start and end <= exc_end:
            return True
    return False


def _overlaps(intervals: List[tuple], start: int, end: int) -> bool:
    """Check if [start, end) overlaps with any interval in the list."""
    for s, e in intervals:
        if start < e and end > s:
            return True
    return False


def extract_distilled_proposition(text: str) -> List[Dict]:
    """
    Extract proposition structures from LaTeX source text.

    Standard \\begin{proposition}...\\end{proposition} environments are already
    handled by _extract_theorem_like in math_paper_parser.py.
    This function only adds novel patterns not covered by the base parser.

    Returns a list of dicts with keys:
        - raw_latex: the raw matched LaTeX text
        - clean_text: simplified plain text version
        - name: optional name/title (from [...] argument), or None
        - env_name: always "distilled"
    """
    # No novel patterns beyond what _extract_theorem_like already handles.
    return []
