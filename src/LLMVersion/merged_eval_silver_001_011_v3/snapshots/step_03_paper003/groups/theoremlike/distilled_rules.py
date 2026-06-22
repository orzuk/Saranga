import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern A: equation/align environments whose body starts with an
# optimization-problem label like (P_0), (P_1), (Q_k), (OPT), (LP), (SDP).
PROBLEM_EQ_ENV_PATTERN = re.compile(
    r'\\begin{(?P<envname>equation|align|gather)\*?}'
    r'(?:\[(?:[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{(?P=envname)\*?}',
    flags=re.DOTALL | re.IGNORECASE,
)

# Pattern B: free-standing optimization problems expressed as prose lead-in
# followed by align/equation/gather block containing \max or \min + s.t. marker.
INLINE_OPT_PROBLEM_PATTERN = re.compile(
    r'(?P<leadin>(?:(?!\\begin\{)[\s\S]){10,600}?)'
    r'(?P<env>\\begin{(?P<envname>align\*?|equation\*?|gather\*?)}'
    r'(?P<body>.*?)'
    r'\\end{(?P=envname)})',
    flags=re.DOTALL,
)

# Pattern C: open-problem statements in running prose paragraphs.
# Anchored on recognized open-problem lead-in phrases.
# PRUNED — FP on paper002
# PROSE_OPEN_PROBLEM_PATTERN = re.compile(
#     r'(?:(?:\n\n|\A))'
#     r'(?P<body>'
#     r'(?:'
#     r'(?:It\s+(?:remains|is\s+still)\s+(?:open|unknown|an\s+open))|'
#     r'(?:We\s+(?:leave|pose|raise|state|highlight)\s+(?:as\s+)?(?:an?\s+)?(?:open|the\s+following))|'
#     r'(?:An?\s+(?:open|interesting|natural|important)\s+(?:problem|question|conjecture))|'
#     r'(?:The\s+following\s+(?:problem|question)\s+(?:remains|is\s+open))|'
#     r'(?:We\s+hope\s+to\s+report)|'
#     r'(?:It\s+would\s+be\s+(?:interesting|desirable|useful|of\s+interest))'
#     r')'
#     r'(?:(?!\n\n)[\s\S]){20,800}'
#     r')',
#     flags=re.IGNORECASE,
# )

# Excluded environments: matches inside these should be suppressed.
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin{(proof|example|remark|rem|note|figure|table|verbatim|lstlisting)}',
    flags=re.IGNORECASE,
)

# Objective / constraint markers for optimization problems.
_OBJ_PATTERN = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_ST_PATTERN = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|subject\s+to|\\mathrm\s*\{\s*s\.?\s*t\.?\s*\}',
    re.IGNORECASE,
)

# Optimization problem label at body start: (P_0), (P1), (Q_k), (OPT), (LP), (SDP), (IP).
_PROBLEM_LABEL_RE = re.compile(
    r'^\s*(?:\\label\{[^}]*\}\s*)?'
    r'\('
    r'(?:P|Q|OPT|LP|IP|SDP|NLP|QP|MIP)'
    r'(?:[_^]\{?[^\)\}]{0,15}\}?)?'
    r'\)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands, leaving readable text."""
    # Remove \begin{...}...\end{...} for display math inner content
    t = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove inline math delimiters
    t = re.sub(r'\$\$.*?\$\$', ' ', t, flags=re.DOTALL)
    t = re.sub(r'\$.*?\$', ' ', t, flags=re.DOTALL)
    t = re.sub(r'\\\[.*?\\\]', ' ', t, flags=re.DOTALL)
    t = re.sub(r'\\\(.*?\\\)', ' ', t, flags=re.DOTALL)
    # Remove common LaTeX commands
    t = re.sub(r'\\(?:label|ref|cite|eqref|textbf|textit|emph|text|mathrm|mathbf)\{[^}]*\}', '', t)
    t = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', t)
    t = re.sub(r'[{}]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    # Check all excluded env opens before `start`
    for m in _EXCLUDED_ENV_RE.finditer(text):
        env_open_pos = m.start()
        if env_open_pos >= start:
            break
        env_name = m.group(1)
        close_tag = r'\\end{' + re.escape(env_name) + r'}'
        close_m = re.search(close_tag, text[env_open_pos:], re.IGNORECASE)
        if close_m:
            env_close_pos = env_open_pos + close_m.end()
            if env_close_pos > start:
                return True
    return False


def _dedup(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the one appearing first."""
    if not results:
        return results
    results = sorted(results, key=lambda d: d.get('_start', 0))
    out = [results[0]]
    for r in results[1:]:
        prev = out[-1]
        prev_end = prev.get('_end', prev.get('_start', 0))
        if r.get('_start', 0) >= prev_end:
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Sub-extractors
# ---------------------------------------------------------------------------

def _extract_equation_problems(text: str) -> List[dict]:
    """
    Finds equation/align/gather environments whose body starts with an
    optimization-problem label like (P_0), (P_1), (Q_k), (OPT), etc.
    """
    results = []
    for m in PROBLEM_EQ_ENV_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        # Strip leading \label{...} if present, then check for (P...) pattern
        stripped = re.sub(r'^\s*\\label\{[^}]*\}\s*', '', body, count=1)
        if not _PROBLEM_LABEL_RE.match(stripped):
            continue
        env_name_raw = m.group('envname')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROBLEM_EQ_ENV_PATTERN',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })
    return results


def _extract_inline_optimization_problems(text: str) -> List[dict]:
    """
    Catches free-standing optimization problems expressed as prose + align/equation
    environments containing \\max or \\min together with s.t. / subject to.
    """
    results = []
    for m in INLINE_OPT_PROBLEM_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        body = m.group('body')
        if not (_OBJ_PATTERN.search(body) and _ST_PATTERN.search(body)):
            continue
        if _inside_excluded_env(text, start, end):
            continue
        leadin = m.group('leadin').strip()
        env_block = m.group('env')
        full_raw = leadin + '\n' + env_block if leadin else env_block
        results.append({
            'raw_latex': full_raw,
            'clean_text': _clean_latex(full_raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'INLINE_OPT_PROBLEM_PATTERN',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })
    return results


def _extract_prose_open_problems(text: str) -> List[dict]:
    """
    Finds open-problem statements in running prose paragraphs (no \\begin/\\end).
    """
    results = []
#     for m in PROSE_OPEN_PROBLEM_PATTERN.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         body = m.group('body').strip()
#         if len(body) < 40:
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'PROSE_OPEN_PROBLEM_PATTERN',
#             'structure_type': 'open_problem',
#             '_start': start,
#             '_end': end,
#         })
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    """
    Extracts theorem-like structures not already caught by the base environment
    extractor. Covers:
      - Optimization problems in equation/align environments with (P_...) labels
      - Free-standing optimization problems (prose + align with max/min + s.t.)
      - Open-problem statements in running prose
    Returns a list of dicts with keys:
      raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    all_results: List[dict] = []

    all_results.extend(_extract_equation_problems(text))
    all_results.extend(_extract_inline_optimization_problems(text))
    all_results.extend(_extract_prose_open_problems(text))

    # Deduplicate overlapping spans
    deduped = _dedup(all_results)

    # Remove internal tracking keys before returning
    for d in deduped:
        d.pop('_start', None)
        d.pop('_end', None)

    for r in deduped:
        r.pop('_start', None)

    return deduped
