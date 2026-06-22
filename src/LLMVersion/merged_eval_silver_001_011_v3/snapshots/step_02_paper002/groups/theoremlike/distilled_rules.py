import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: Named theorem-like environments not already caught by the base
# parser's BASE_ENV_KIND_MAP.  We target aliases / starred variants / alternate
# capitalisation that the base map is missing.
EXTRA_THEOREM_ENV_PATTERN = re.compile(
    r'\\begin{('
    r'theorem\*|Theorem\*|thm\*|'
    r'lemma\*|Lemma\*|lem\*|'
    r'proposition\*|Proposition\*|prop\*|'
    r'corollary\*|Corollary\*|cor\*|'
    r'claim\*|Claim\*|'
    r'conjecture\*|Conjecture\*|conj|Conj|'
    r'problem\*|Problem\*|prob|Prob|'
    r'openproblem\*|openProblem\*|openquestion\*|open\*|'
    r'maintheorem|MainTheorem|main_theorem|'
    r'mainthm|mainThm|'
    r'theoremA|theoremB|theoremC|theoremD|'
    r'thmA|thmB|thmC|thmD'
    r')}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1}',
    flags=re.DOTALL | re.IGNORECASE,
)

# Pattern 2: Optimization / mathematical programming problems stated inside
# equation or align environments whose body begins with a problem-label like
# (P_0), (P_1), (Q), (LP), (OPT), (SDP), (IP), (NLP), (QCQP), etc.
PROBLEM_EQ_PATTERN = re.compile(
    r'\\begin{(equation|align|eqnarray)\*?}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1}',
    flags=re.DOTALL | re.IGNORECASE,
)

PROBLEM_BODY_START_RE = re.compile(
    r'^\s*(?:\\label\{[^}]*\}\s*)?'
    r'\((?:P|Q|LP|IP|SDP|NLP|QP|QCQP|OPT|PRIMAL|DUAL|MIP|MILP|MINLP)'
    r'(?:[_^]\{?[^\)\}]{0,15}\}?)?\)',
    flags=re.IGNORECASE,
)

# Pattern 3: Open-problem statements in running prose (no \begin/\end).
# Anchored on common structural phrases that introduce open problems.
OPEN_PROBLEM_PROSE_RE = re.compile(
    r'(?:(?:^|\n\n)[ \t]*)'
    r'(?P<body>'
    r'(?:'
    r'It\s+(?:remains|is\s+still)\s+(?:an?\s+)?open|'
    r'(?:An?|The\s+following)\s+open\s+(?:problem|question|conjecture)|'
    r'(?:An?|The\s+following)\s+(?:interesting|important|natural)\s+(?:open\s+)?'
    r'(?:problem|question)|'
    r'We\s+(?:leave|pose|state|formulate)\s+(?:the\s+following\s+)?'
    r'(?:as\s+an?\s+)?open|'
    r'We\s+(?:conjecture|believe|expect|hope|note)\s+that|'
    r'The\s+following\s+(?:problem|question)\s+(?:remains|is)\s+open|'
    r'It\s+would\s+be\s+(?:interesting|desirable|natural|important)\s+to'
    r')'
    r'[^\n]{10,}'
    r'(?:\n(?!\n)[ \t]*[^\n]+)*'
    r')',
    flags=re.MULTILINE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Excluded environments (results inside these are skipped)
# ---------------------------------------------------------------------------
_EXCLUDED_ENVS = [
    'proof', 'Proof',
    'example', 'Example',
    'remark', 'Remark',
    'figure', 'Figure',
    'table', 'Table',
    'abstract',
    'verbatim',
    'lstlisting',
    'comment',
]

_EXCLUDED_ENV_RE = re.compile(
    r'\\begin{(' + '|'.join(map(re.escape, _EXCLUDED_ENVS)) + r')}',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Subtype classification
# ---------------------------------------------------------------------------
_ENV_TO_SUBTYPE: Dict[str, str] = {
    'theorem': 'theorem',
    'thm': 'theorem',
    'maintheorem': 'theorem',
    'mainthm': 'theorem',
    'main_theorem': 'theorem',
    'theorema': 'theorem',
    'theoremb': 'theorem',
    'theoremc': 'theorem',
    'theoremd': 'theorem',
    'thma': 'theorem',
    'thmb': 'theorem',
    'thmc': 'theorem',
    'thmd': 'theorem',
    'lemma': 'lemma',
    'lem': 'lemma',
    'proposition': 'proposition',
    'prop': 'proposition',
    'corollary': 'corollary',
    'cor': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'conj': 'conjecture',
    'problem': 'problem',
    'prob': 'problem',
    'openproblem': 'open_problem',
    'openproblem': 'open_problem',
    'openquestion': 'open_problem',
    'open': 'open_problem',
}


def _env_to_subtype(env_name: str) -> str:
    """Map an environment name (possibly starred) to a structure subtype."""
    key = env_name.rstrip('*').lower()
    return _ENV_TO_SUBTYPE.get(key, 'theorem')


# ---------------------------------------------------------------------------
# Helper: detect whether a span falls inside an excluded environment
# ---------------------------------------------------------------------------
def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is nested inside an excluded env."""
    prefix = text[:start]
    for m in _EXCLUDED_ENV_RE.finditer(prefix):
        env = m.group(1)
        close_re = re.compile(
            r'\\end\{' + re.escape(env) + r'\}',
            flags=re.IGNORECASE,
        )
        close_m = close_re.search(text, m.end())
        if close_m and close_m.start() > end:
            return True
    return False


# ---------------------------------------------------------------------------
# Helper: minimal LaTeX -> plain text cleaning
# ---------------------------------------------------------------------------
def _clean_latex(text: str) -> str:
    """Very light stripping of LaTeX markup for clean_text field."""
    # Remove \label{...}
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # Remove display math environments, keep content
    text = re.sub(r'\\begin\{(?:equation|align|eqnarray|gather|multline)\*?\}(.*?)\\end\{[^}]+\}',
                  r' \1 ', text, flags=re.DOTALL)
    # Remove other \begin/\end wrappers
    text = re.sub(r'\\(?:begin|end)\{[^}]+\}', '', text)
    # Inline math: keep as-is (just unwrap $...$)
    text = re.sub(r'\$\$(.+?)\$\$', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\$(.+?)\$', r'\1', text, flags=re.DOTALL)
    # Remove common LaTeX commands but keep their argument text
    text = re.sub(r'\\(?:text|mathrm|mathbf|mathit|emph|textbf|textit|textsc)\{([^}]*)\}',
                  r'\1', text)
    # Remove remaining single-arg commands
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove bare commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------
def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result's raw_latex,
    or whose source positions overlap."""
    # Sort by length of raw_latex descending so larger matches win
    results.sort(key=lambda d: len(d.get('raw_latex', '')), reverse=True)
    kept: List[dict] = []
    kept_spans: List[tuple] = []
    for r in results:
        s = r.get('_start', -1)
        e = r.get('_end', -1)
        overlap = False
        if s >= 0 and e >= 0:
            for (ks, ke) in kept_spans:
                # Check for overlap
                if s < ke and e > ks:
                    overlap = True
                    break
        if not overlap:
            kept.append(r)
            if s >= 0 and e >= 0:
                kept_spans.append((s, e))
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------
def extract_distilled_theoremlike(text: str) -> List[dict]:
    """
    Extract theorem-like structures NOT already caught by the base parser.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: Starred / aliased / alternate-capitalisation theorem envs
    # ------------------------------------------------------------------
    for m in EXTRA_THEOREM_ENV_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env_name = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'EXTRA_THEOREM_ENV_PATTERN',
            'structure_type': _env_to_subtype(env_name),
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule B: Optimization problems in equation/align environments
    # ------------------------------------------------------------------
    for m in PROBLEM_EQ_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        # Check that the body begins with an optimization-problem label
        if not PROBLEM_BODY_START_RE.match(body):
            continue
        opt = m.group('opt')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PROBLEM_EQ_PATTERN',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule C: Open-problem statements in running prose
    # ------------------------------------------------------------------
    for m in OPEN_PROBLEM_PROSE_RE.finditer(text):
        start = m.start('body')
        end = m.end('body')
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPEN_PROBLEM_PROSE_RE',
            'structure_type': 'open_problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Deduplicate and strip internal position keys
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
