import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: optimization problems in equation/align environments
# whose body begins with a (P_...), (Q_...), (LP), (SDP), (OPT) label
OPTIMIZATION_EQ_PATTERN = re.compile(
    r'\\begin{(?P<envname>equation\*?|align\*?|gather\*?)}'
    r'(?P<body>.*?)'
    r'\\end{(?P=envname)}',
    flags=re.DOTALL
)

# Pattern 2: optimization problems in prose + align/equation blocks
# The align/equation body must contain \max or \min AND a constraint marker
INLINE_OPT_PROBLEM_PATTERN = re.compile(
    r'(?P<leadin>(?:(?!\\begin\{)[\s\S]){10,800}?)'
    r'(?P<env>\\begin{(?P<envname>align\*?|equation\*?|gather\*?)}'
    r'(?P<body>.*?)'
    r'\\end{(?P=envname)})',
    re.DOTALL
)

# Pattern 3: open problem statements in running prose paragraphs
OPEN_PROBLEM_PROSE_PATTERN = re.compile(
    r'(?:(?:^|\n\n))'
    r'(?P<body>'
    r'(?:'
    r'(?:It\s+(?:remains|is\s+still)\s+(?:an?\s+)?open)|'
    r'(?:We\s+(?:leave|pose|state|present)\s+(?:(?:the\s+)?following\s+)?(?:as\s+)?(?:an?\s+)?(?:open\s+)?(?:problem|question|conjecture))|'
    r'(?:An?\s+(?:open|interesting|natural|fundamental|important)\s+(?:problem|question|conjecture))|'
    r'(?:The\s+following\s+(?:problem|question|conjecture)\s+(?:remains|is\s+open))|'
    r'(?:We\s+hope\s+to)|'
    r'(?:We\s+conjecture\s+that)|'
    r'(?:It\s+would\s+be\s+(?:interesting|desirable|useful)\s+to)'
    r')'
    r'[^\n]{10,}'
    r'(?:\n(?!\n).+)*'
    r')',
    flags=re.MULTILINE | re.IGNORECASE
)

# Pattern 4: environments that should be excluded from matching inside them
EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin{(?:proof|Proof|example|Example|remark|Remark|rem|note|figure|table)[^}]*}'
    r'.*?'
    r'\\end{(?:proof|Proof|example|Example|remark|Remark|rem|note|figure|table)[^}]*}',
    flags=re.DOTALL
)

# ---------------------------------------------------------------------------
# Objective and constraint markers for optimization problems
# ---------------------------------------------------------------------------
_OBJ_RE = re.compile(r'\\(?:max|min)(?:imize|imum)?\b', re.IGNORECASE)
_ST_RE = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}'
    r'|\\text\s*\{\s*subject\s+to\s*\}'
    r'|subject\s+to',
    re.IGNORECASE
)
_PROBLEM_LABEL_RE = re.compile(
    r'^\s*(?:\\label\{[^}]*\}\s*)?'
    r'\((?:P|Q|LP|IP|SDP|OPT|NP|QP|QCQP)(?:[_^]\{?[^)]{0,20}\})?\)',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup, returning approximate plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...} etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite|citealt|citet|citep)\{[^}]*\}', '', text)
    # Remove display math environments but keep content
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}(.*?)\\end\{(?:equation|align|gather|multline)\*?\}',
                  r' \1 ', text, flags=re.DOTALL)
    # Remove \begin{...} \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove common text commands but keep argument
    text = re.sub(r'\\(?:text|textbf|textit|emph|mathrm|mathbf|mathit|mathbb|mathcal|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove other commands with one argument
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _determine_structure_type(env_name: str, body: str) -> str:
    """Determine the structure subtype from environment name or body content."""
    name = env_name.lower().rstrip('*')
    mapping = {
        'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
        'lemma': 'lemma', 'lem': 'lemma',
        'proposition': 'proposition', 'prop': 'proposition',
        'corollary': 'corollary', 'cor': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem',
        'open_problem': 'open_problem', 'openproblem': 'open_problem',
        'openquestion': 'open_problem',
    }
    if name in mapping:
        return mapping[name]
    # Try to infer from body text
    body_lower = body.lower()
    if 'conjecture' in body_lower:
        return 'conjecture'
    if 'open problem' in body_lower or 'open question' in body_lower:
        return 'open_problem'
    if 'problem' in body_lower:
        return 'problem'
    return 'theorem'


def _overlaps(span: tuple, used: List[tuple]) -> bool:
    """Check if span overlaps with any span in used list."""
    s, e = span
    for us, ue in used:
        if s < ue and e > us:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    """
    Extract theorem-like structures NOT already caught by the base environment
    extractor. Focuses on:
      1. Optimization problems in equation/align envs with (P_...) labels
      2. Prose + align blocks describing optimization problems (\max/\min + s.t.)
      3. Open-problem statements in running prose
    """
    results: List[dict] = []
    used_spans: List[tuple] = []

    # ------------------------------------------------------------------
    # Rule 1: equation/align/gather blocks starting with optimization labels
    # e.g. (P_0), (Q_1), (LP), (SDP) etc.
    # ------------------------------------------------------------------
    for m in OPTIMIZATION_EQ_PATTERN.finditer(text):
        span = (m.start(), m.end())
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        # Remove leading \label{...} if present, then check for problem label
        stripped = re.sub(r'^\s*\\label\{[^}]*\}\s*', '', body, count=1)
        if not _PROBLEM_LABEL_RE.match(stripped):
            continue
        if _overlaps(span, used_spans):
            continue
        used_spans.append(span)
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPTIMIZATION_EQ_PATTERN',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule 2: prose lead-in + align/equation block with \max/\min + s.t.
    # ------------------------------------------------------------------
    for m in INLINE_OPT_PROBLEM_PATTERN.finditer(text):
        body = m.group('body')
        if not (_OBJ_RE.search(body) and _ST_RE.search(body)):
            continue
        # We anchor on the env block for span purposes to avoid massive overlaps
        env_match_start = m.start('env')
        env_match_end = m.end('env')
        span = (env_match_start, env_match_end)
        if _inside_excluded_env(text, env_match_start, env_match_end):
            continue
        if _overlaps(span, used_spans):
            continue
        # Also skip if this env was already caught by Rule 1
        already = False
        for us, ue in used_spans:
            if us <= env_match_start and env_match_end <= ue:
                already = True
                break
        if already:
            continue
        used_spans.append(span)
        leadin = m.group('leadin') or ''
        raw = leadin.strip() + '\n' + m.group('env')
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'INLINE_OPT_PROBLEM_PATTERN',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule 3: open-problem prose paragraphs (no \begin/\end wrapper)
    # ------------------------------------------------------------------
    for m in OPEN_PROBLEM_PROSE_PATTERN.finditer(text):
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        span = (m.start(), m.end())
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if _overlaps(span, used_spans):
            continue
        used_spans.append(span)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPEN_PROBLEM_PROSE_PATTERN',
            'structure_type': 'open_problem',
        })

    return results
