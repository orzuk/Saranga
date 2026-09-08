import re
from typing import List, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands, leaving readable text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \citep{...}, \citet{...}
    text = re.sub(r'\\(?:label|ref|eqref|cite[tp]?)\{[^}]*\}', '', text)
    # Remove \footnote{...}
    text = re.sub(r'\\footnote\{[^}]*\}', '', text, flags=re.DOTALL)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:align|equation|gather|multline)\*?\}.*?\\end\{(?:align|equation|gather|multline)\*?\}', ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove \[ ... \]
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    # Remove common formatting commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove remaining \command{...}
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining \command
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|Example|Remark)\*?\}',
    re.IGNORECASE
)
_EXCLUDED_ENV_FULL = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|Example|Remark)\*?\}.*?'
    r'\\end\{\1\*?\}',
    re.DOTALL | re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside a proof/example/remark env."""
    for m in _EXCLUDED_ENV_FULL.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _determine_structure_type(env_name: str, body: str) -> str:
    """Map environment name to a structure_type subtype."""
    name = env_name.lower().rstrip('*')
    mapping = {
        'theorem': 'theorem',
        'thm': 'theorem',
        'theo': 'theorem',
        'lemma': 'lemma',
        'lem': 'lemma',
        'proposition': 'proposition',
        'prop': 'proposition',
        'property': 'proposition',
        'corollary': 'corollary',
        'cor': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem',
        'open_problem': 'open_problem',
        'openproblem': 'open_problem',
        'openquestion': 'open_problem',
        'definition': 'definition',
        'defn': 'definition',
        'dfn': 'definition',
    }
    return mapping.get(name, 'theorem')


# ---------------------------------------------------------------------------
# Rule 1: \begin{property}...\end{property}  ->  proposition
# These are NOT in the base env_kind_map.
# ---------------------------------------------------------------------------

RULE_PROPERTY_ENV = re.compile(
    r'\\begin\{(property)\*?\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{property\*?\}',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 2: Additional theorem-like env names not in base map
# (e.g. custom env names that alias theorem/lemma/corollary/claim/conjecture)
# ---------------------------------------------------------------------------

RULE_EXTRA_THEOREM_ENVS = re.compile(
    r'\\begin\{'
    r'(theorem\*?|thm\*?|theo\*?|lemma\*?|lem\*?|proposition\*?|prop\*?'
    r'|corollary\*?|cor\*?|claim\*?|conjecture\*?|conj\*?'
    r'|maintheorem\*?|mainlemma\*?|mainprop\*?|maincorollary\*?'
    r'|keytheorem\*?|keyclaim\*?'
    r')'
    r'\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\s*(?:maintheorem|mainlemma|mainprop|maincorollary'
    r'|keytheorem|keyclaim'
    r'|theorem|thm|theo|lemma|lem|proposition|prop'
    r'|corollary|cor|claim|conjecture|conj)\*?\s*\}',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 3: Optimization problems in equation/align blocks where body
# contains objective (\max or \min) AND constraint (\text{s.t.} or subject to)
# ---------------------------------------------------------------------------

RULE_OPT_PROBLEM_ENV = re.compile(
    r'\\begin\{(?P<envname>align|equation|gather)\*?\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\*?\}',
    re.DOTALL | re.IGNORECASE
)
_OPT_OBJ = re.compile(r'\\(?:max|min|maximize|minimize|argmin|argmax)\b', re.IGNORECASE)
_OPT_ST  = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|subject\s+to|\\mathrm\s*\{\s*s\.t\.\s*\}',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 4: Open-problem prose — paragraphs introduced by recognized phrases
# that signal an open problem/question/future work
# ---------------------------------------------------------------------------

# A paragraph is text between \n\n boundaries (or start/end of document)
RULE_OPEN_PROBLEM_PROSE = re.compile(
    r'(?:(?<=\n\n)|(?<=\r\n\r\n)|(?:^))'
    r'(?P<body>'
    r'(?:'
    # Lead phrase variants
    r'(?:We\s+leave\b[^.]{0,400}?(?:open\s+(?:questions?|problems?)|future\s+work))'
    r'|(?:(?:It|This)\s+(?:remains?|is\s+still)\s+(?:an?\s+)?open\b[^.]{0,400})'
    r'|(?:An?\s+(?:open|interesting|natural|important)\s+(?:question|problem)\b[^.]{0,400})'
    r'|(?:The\s+following\s+(?:question|problem)\s+remains?\s+open\b[^.]{0,400})'
    r'|(?:We\s+(?:pose|raise)\s+(?:the\s+following\s+)?(?:open\s+)?(?:question|problem)\b[^.]{0,400})'
    r'|(?:remain(?:s)?\s+open\s+(?:after|following)\s+this\b[^.]{0,400})'
    r')'
    r'[^\n]{0,800}'     # rest of paragraph, no blank line
    r'(?:\n(?!\n)[^\n]{0,200})*'  # continuation lines
    r')',
    re.MULTILINE | re.IGNORECASE | re.DOTALL
)

# ---------------------------------------------------------------------------
# Rule 5: Prose theorem-like blocks introduced by bold/emph keyword sentence
# Pattern: \textbf{Theorem/Lemma/...} (or \emph{...}) followed by display math
# These are unnumbered inline statements sometimes used in papers.
# ---------------------------------------------------------------------------

RULE_INLINE_BOLD_STATEMENT = re.compile(
    r'(?P<marker>\\(?:textbf|emph|textit)\s*\{'
    r'\s*(?P<kind>Theorem|Lemma|Proposition|Corollary|Claim|Conjecture)\b[^}]{0,80}'
    r'\})'
    r'(?P<body>(?:(?!\\(?:textbf|emph|textit)\s*\{(?:Theorem|Lemma|Proposition|Corollary|Claim|Conjecture)\b).){10,800})',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 6: Numbered inline statements — "Theorem X." / "Lemma X." in bold,
# followed by statement text, common in some older LaTeX styles.
# ---------------------------------------------------------------------------

RULE_NUMBERED_PROSE_STATEMENT = re.compile(
    r'(?:^|\n)'
    r'(?P<marker>\\(?:noindent|par)\s*)?'
    r'\\textbf\s*\{'
    r'(?P<kind>Theorem|Lemma|Proposition|Corollary|Claim|Conjecture)'
    r'\s*(?P<num>[\d\.]+)'
    r'(?:\s*\([^)]{0,80}\))?'
    r'\s*\.?\s*\}'
    r'(?P<body>(?:(?!\n\n).){20,600})',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex span overlaps with a previously seen one."""
    seen: List[Tuple[int, int]] = []
    out = []
    for r in sorted(results, key=lambda x: x.get('_start', 0)):
        s = r.get('_start', 0)
        e = r.get('_end', s + len(r['raw_latex']))
        overlap = False
        for ps, pe in seen:
            if s < pe and e > ps:
                overlap = True
                break
        if not overlap:
            seen.append((s, e))
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule 1: \begin{property} environments ---
    for m in RULE_PROPERTY_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'RULE_PROPERTY_ENV',
            'structure_type': 'proposition',
            '_start': start,
            '_end': end,
        })

    # --- Rule 2: Extra theorem-like env names not in base map ---
    for m in RULE_EXTRA_THEOREM_ENVS.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env = m.group(1).rstrip('*').lower()
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        stype = _determine_structure_type(env, body)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'RULE_EXTRA_THEOREM_ENVS',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 3: Optimization problems in align/equation with max/min + s.t. ---
    for m in RULE_OPT_PROBLEM_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        if not (_OPT_OBJ.search(body) and _OPT_ST.search(body)):
            continue
        envname = m.group('envname')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'RULE_OPT_PROBLEM_ENV',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # --- Rule 4: Open-problem prose paragraphs ---
    for m in RULE_OPEN_PROBLEM_PROSE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if len(body) < 50:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'RULE_OPEN_PROBLEM_PROSE',
            'structure_type': 'open_problem',
            '_start': start,
            '_end': end,
        })

    # --- Rule 5: \textbf{Theorem ...} / \emph{Lemma ...} inline bold statements ---
    for m in RULE_INLINE_BOLD_STATEMENT.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        kind = m.group('kind').lower()
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        raw = m.group(0)
        stype = _determine_structure_type(kind, body)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'RULE_INLINE_BOLD_STATEMENT',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 6: \textbf{Theorem X.} numbered prose statements ---
    for m in RULE_NUMBERED_PROSE_STATEMENT.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        kind = m.group('kind').lower()
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        raw = m.group(0)
        stype = _determine_structure_type(kind, body)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'RULE_NUMBERED_PROSE_STATEMENT',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # Deduplicate and clean up internal keys
    deduped = _deduplicate(results)
    for r in deduped:
        r.pop('_start', None)
        r.pop('_end', None)

    return deduped
