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

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from latex_clean import clean_latex_to_text as _clean_latex


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
