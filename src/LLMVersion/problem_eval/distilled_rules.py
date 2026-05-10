import re
from typing import List, Dict
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from latex_clean import clean_latex_to_text as _clean_latex


# Check if a match position is inside an excluded environment
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|theorem|lemma|remark|example|corollary|proposition)\}'
    r'(.*?)'
    r'\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ============================================================
# Pattern 1: equation-like environments with \label containing 'prob'
# ============================================================
_EQ_ENV_NAMES = r'(?:equation\*?|align\*?|gather\*?|multline\*?)'

_LABELED_PROB_PATTERN = re.compile(
    r'(\\begin\{(' + _EQ_ENV_NAMES + r')\}'
    r'(.*?)'
    r'\\end\{\2\})',
    re.DOTALL
)

_LABEL_PATTERN = re.compile(r'\\label\{([^}]*)\}')


# ============================================================
# Pattern 2: prose mentioning 'problem' shortly before an equation environment
# We allow up to ~200 chars of prose (including the word 'problem') before \begin{equation...}
# But we only capture the equation environment itself.
# ============================================================
_CONTEXT_PROBLEM_PATTERN = re.compile(
    r'(?:problem|Problem)\s{0,200}?'
    r'(\\begin\{(' + _EQ_ENV_NAMES + r')\}'
    r'(.*?)'
    r'\\end\{\2\})',
    re.DOTALL
)


def extract_distilled_problem(text: str) -> List[dict]:
    results = []
    seen_spans = []  # list of (start, end) to deduplicate

    def _overlaps(start: int, end: int) -> bool:
        for s, e in seen_spans:
            # Check substantial overlap
            overlap_start = max(s, start)
            overlap_end = min(e, end)
            if overlap_end > overlap_start:
                overlap_len = overlap_end - overlap_start
                min_len = min(e - s, end - start)
                if min_len > 0 and overlap_len / min_len > 0.5:
                    return True
        return False

    def _add_result(match_start: int, match_end: int, raw_latex: str, name: str = None):
        if _overlaps(match_start, match_end):
            return
        if _inside_excluded_env(text, match_start, match_end):
            return
        seen_spans.append((match_start, match_end))
        clean = _clean_latex(raw_latex)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
        })

    # Strategy 1: equation-like envs with \label containing 'prob'
    for m in _LABELED_PROB_PATTERN.finditer(text):
        full_match = m.group(1)
        body = m.group(3)
        label_m = _LABEL_PATTERN.search(body)
        if label_m and 'prob' in label_m.group(1).lower():
            name = label_m.group(1)
            _add_result(m.start(), m.end(), full_match, name=name)

    # Strategy 2: prose-contextual problems - 'problem' word before equation env
    for m in _CONTEXT_PROBLEM_PATTERN.finditer(text):
        eq_text = m.group(1)
        # Find the actual start of the equation in the original text
        eq_start = m.start() + m.group(0).index(eq_text)
        eq_end = m.end()

        # Extract label for name if present
        body = m.group(3)
        label_m = _LABEL_PATTERN.search(body)
        name = label_m.group(1) if label_m else None

        _add_result(eq_start, eq_end, eq_text, name=name)

    return results
