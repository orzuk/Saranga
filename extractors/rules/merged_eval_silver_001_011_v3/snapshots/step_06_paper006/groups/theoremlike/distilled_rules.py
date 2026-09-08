import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Excluded environments – matches inside these are suppressed
# ---------------------------------------------------------------------------
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin{(proof|Proof|example|Example|remark|Remark|rem|note)}'
    r'.*?'
    r'\\end{\1}',
    re.DOTALL | re.IGNORECASE,
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Minimal LaTeX → plain-text cleaner
# ---------------------------------------------------------------------------
_LATEX_CMD_RE = re.compile(r'\\[a-zA-Z]+\*?\s*(?:\{[^}]*\})*')
_BRACES_RE    = re.compile(r'[{}]')
_MULTI_WS_RE  = re.compile(r'\s+')

def _clean_latex(text: str) -> str:
    t = re.sub(r'\\label\{[^}]*\}', '', text)
    t = re.sub(r'\\(?:cite|ref|eqref)\{[^}]*\}', '', t)
    t = _LATEX_CMD_RE.sub(' ', t)
    t = _BRACES_RE.sub('', t)
    t = _MULTI_WS_RE.sub(' ', t)
    return t.strip()


# ---------------------------------------------------------------------------
# Helper: determine structure_type from environment name or keyword
# ---------------------------------------------------------------------------
_SUBTYPE_MAP = {
    'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
    'lemma': 'lemma', 'lem': 'lemma',
    'proposition': 'proposition', 'prop': 'proposition', 'property': 'proposition',
    'corollary': 'corollary', 'cor': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'problem': 'problem',
    'open_problem': 'open_problem', 'openproblem': 'open_problem',
    'openquestion': 'open_problem',
}

_KEYWORD_SUBTYPE_RE = re.compile(
    r'\b(theorem|lemma|proposition|corollary|claim|conjecture|'
    r'open\s+problem|open\s+question|problem)\b',
    re.IGNORECASE,
)

def _subtype_from_env(env_name: str) -> str:
    key = env_name.rstrip('*').lower()
    return _SUBTYPE_MAP.get(key, 'theorem')

def _subtype_from_text(text: str, default: str = 'theorem') -> str:
    m = _KEYWORD_SUBTYPE_RE.search(text)
    if not m:
        return default
    kw = m.group(1).lower().replace(' ', '_')
    return _SUBTYPE_MAP.get(kw, default)


# ---------------------------------------------------------------------------
# Rule 1 – \begin{property}...\end{property}  →  proposition
# (the base parser does not list 'property' in BASE_ENV_KIND_MAP)
# ---------------------------------------------------------------------------
PROPERTY_ENV_RE = re.compile(
    r'\\begin{([Pp]roperty)}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1}',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Rule 2 – custom / alias theorem-like environments not in the base map
# Covers:  fact, Fact, observation, Observation, result, Result,
#          notation, Notation, condition, Condition, criterion, Criterion,
#          hypothesis, Hypothesis, law, Law, principle, Principle,
#          question, Question, task, Task, objective, Objective,
#          restriction, Restriction, maintheorem, MainTheorem,
#          mainlemma, MainLemma, mainclaim, MainClaim
# ---------------------------------------------------------------------------
_EXTRA_ENV_NAMES = [
    'fact', 'Fact',
    'observation', 'Observation',
    'result', 'Result',
    'condition', 'Condition',
    'criterion', 'Criterion',
    'hypothesis', 'Hypothesis',
    'question', 'Question',
    'task', 'Task',
    'objective', 'Objective',
    'maintheorem', 'MainTheorem',
    'mainlemma', 'MainLemma',
    'mainclaim', 'MainClaim',
]

EXTRA_NAMED_ENV_RE = re.compile(
    r'\\begin{(' + '|'.join(map(re.escape, _EXTRA_ENV_NAMES)) + r')}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1}',
    re.DOTALL | re.IGNORECASE,
)

_EXTRA_ENV_SUBTYPE: Dict[str, str] = {
    'fact': 'theorem', 'observation': 'theorem', 'result': 'theorem',
    'condition': 'theorem', 'criterion': 'theorem', 'hypothesis': 'theorem',
    'question': 'open_problem', 'task': 'problem', 'objective': 'problem',
    'maintheorem': 'theorem', 'mainlemma': 'lemma', 'mainclaim': 'claim',
}

def _extra_env_subtype(env_name: str) -> str:
    key = env_name.rstrip('*').lower()
    return _EXTRA_ENV_SUBTYPE.get(key, 'theorem')


# ---------------------------------------------------------------------------
# Rule 3 – starred variants of standard environments not caught by base regex
# e.g. \begin{theorem*} ... \end{theorem*}
# ---------------------------------------------------------------------------
_STARRED_BASE = [
    'theorem', 'lemma', 'proposition', 'corollary', 'claim',
    'conjecture', 'problem',
]

STARRED_ENV_RE = re.compile(
    r'\\begin{(' + '|'.join(re.escape(e) + r'\*' for e in _STARRED_BASE) + r')}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1}',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule 4 – inline/unnumbered theorem-like blocks introduced by
#   \textbf{Theorem/Lemma/...} or \noindent\textbf{...}
#   followed by body text up to the next blank line or section command
# ---------------------------------------------------------------------------
TEXTBF_INLINE_RE = re.compile(
    r'(?:^|(?<=\n))'
    r'(?:\\noindent\s*)?'
    r'\\textbf\s*\{(?P<kw>'
    r'Theorem|Lemma|Proposition|Corollary|Claim|Conjecture|Problem|'
    r'Open\s+Problem|Open\s+Question'
    r')(?:[^}]*)?\}'
    r'[^\S\n]*'
    r'(?:\((?P<opt>[^)]{0,120})\))?'
    r'[^\S\n]*'
    r'(?P<body>(?:(?!\n\n|\\(?:sub)*section|\\begin\{(?:theorem|lemma|proposition|corollary|claim|proof)\}).)+)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule 5 – \emph{Theorem} / \textit{Theorem} inline introductions
# ---------------------------------------------------------------------------
EMPH_INLINE_RE = re.compile(
    r'(?:^|(?<=\n))'
    r'(?:\\noindent\s*)?'
    r'\\(?:emph|textit)\s*\{(?P<kw>'
    r'Theorem|Lemma|Proposition|Corollary|Claim|Conjecture|Problem|'
    r'Open\s+Problem|Open\s+Question'
    r')(?:[^}]*)?\}'
    r'[^\S\n]*'
    r'(?:\((?P<opt>[^)]{0,120})\))?'
    r'[^\S\n]*'
    r'(?P<body>(?:(?!\n\n|\\(?:sub)*section|\\begin\{(?:theorem|lemma|proposition|corollary|claim|proof)\}).)+)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule 6 – optimization problems inside equation/align/gather environments
#   whose body contains \max or \min together with s.t. / subject to
# ---------------------------------------------------------------------------
OPT_PROBLEM_ENV_RE = re.compile(
    r'\\begin{(?P<envname>align\*?|equation\*?|gather\*?|alignat\*?)}'
    r'(?P<body>.*?)'
    r'\\end{(?P=envname)}',
    re.DOTALL | re.IGNORECASE,
)
_OPT_OBJ_RE = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_OPT_ST_RE  = re.compile(
    r'\\text\s*\{[^}]*s\.?\s*t\.?[^}]*\}|subject\s+to|\\mathrm\s*\{s\.?t\.?\}',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule 7 – prose open-problem paragraphs
#   Triggers: 'We leave ... open question(s)/problem(s)',
#             'remain(s) open', 'open question', 'future work/research'
# ---------------------------------------------------------------------------
PROSE_OPEN_PROBLEM_RE = re.compile(
    r'(?:(?<=\n\n)|(?<=\.\s\s)|(?:^))'
    r'(?P<body>'
    r'(?:'
    r'(?:We\s+leave\b.{0,400}?(?:open\s+(?:questions?|problems?)|future\s+(?:work|research)))'
    r'|(?:(?:An?|The|Several|Some|Many|These)\s+(?:interesting\s+)?open\s+(?:questions?|problems?)\b.{0,400}?)'
    r'|(?:remain(?:s)?\s+open\b.{0,400}?)'
    r'|(?:It\s+(?:is\s+still|remains)\s+(?:an?\s+)?open\b.{0,400}?)'
    r')'
    r'(?:[^\n]|\n(?!\n)){0,600}'
    r')',
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Rule 8 – open-problem phrases: 'leave ... to/for future work'
# ---------------------------------------------------------------------------
FUTURE_WORK_RE = re.compile(
    r'(?:(?<=\n\n)|(?:^))'
    r'(?P<body>'
    r'[A-Z][^\n]{0,600}?'
    r'(?:leave\b.{0,300}?(?:to|for)\s+future\s+(?:work|research)'
    r'|for\s+future\s+(?:work|research|study|investigation)'
    r')'
    r'[^\n]{0,200}'
    r')',
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------
def _dedup(results: List[dict]) -> List[dict]:
    """Remove results whose character spans overlap with an earlier result."""
    out: List[dict] = []
    spans: List[tuple] = []
    for r in sorted(results, key=lambda x: x.get('_start', 0)):
        s = r.get('_start', 0)
        e = r.get('_end', s + len(r['raw_latex']))
        overlapping = any(not (e <= ps or s >= pe) for ps, pe in spans)
        if not overlapping:
            spans.append((s, e))
            out.append(r)
    # strip internal position keys
    for r in out:
        r.pop('_start', None)
        r.pop('_end', None)
    return out


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------
def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule 1: \begin{property} ---
    for m in PROPERTY_ENV_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        opt  = m.group('opt')
        raw  = m.group(0)
        results.append({
            'raw_latex':      raw,
            'clean_text':     _clean_latex(body),
            'name':           opt.strip() if opt else None,
            'env_name':       'distilled',
            'rule_name':      'PROPERTY_ENV_RE',
            'structure_type': 'proposition',
            '_start':         m.start(),
            '_end':           m.end(),
        })

    # --- Rule 2: extra named environments ---
    for m in EXTRA_NAMED_ENV_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        opt  = m.group('opt')
        raw  = m.group(0)
        env  = m.group(1)
        results.append({
            'raw_latex':      raw,
            'clean_text':     _clean_latex(body),
            'name':           opt.strip() if opt else None,
            'env_name':       'distilled',
            'rule_name':      'EXTRA_NAMED_ENV_RE',
            'structure_type': _extra_env_subtype(env),
            '_start':         m.start(),
            '_end':           m.end(),
        })

    # --- Rule 3: starred standard environments ---
    for m in STARRED_ENV_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        opt  = m.group('opt')
        raw  = m.group(0)
        env  = m.group(1)  # e.g. 'theorem*'
        results.append({
            'raw_latex':      raw,
            'clean_text':     _clean_latex(body),
            'name':           opt.strip() if opt else None,
            'env_name':       'distilled',
            'rule_name':      'STARRED_ENV_RE',
            'structure_type': _subtype_from_env(env),
            '_start':         m.start(),
            '_end':           m.end(),
        })

    # --- Rule 4: \textbf{Theorem/...} inline ---
    for m in TEXTBF_INLINE_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw   = m.group('kw')
        opt  = m.group('opt')
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        raw = m.group(0)
        results.append({
            'raw_latex':      raw,
            'clean_text':     _clean_latex(body),
            'name':           opt.strip() if opt else None,
            'env_name':       'distilled',
            'rule_name':      'TEXTBF_INLINE_RE',
            'structure_type': _subtype_from_text(kw),
            '_start':         m.start(),
            '_end':           m.end(),
        })

    # --- Rule 5: \emph{Theorem/...} inline ---
    for m in EMPH_INLINE_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw   = m.group('kw')
        opt  = m.group('opt')
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        raw = m.group(0)
        results.append({
            'raw_latex':      raw,
            'clean_text':     _clean_latex(body),
            'name':           opt.strip() if opt else None,
            'env_name':       'distilled',
            'rule_name':      'EMPH_INLINE_RE',
            'structure_type': _subtype_from_text(kw),
            '_start':         m.start(),
            '_end':           m.end(),
        })

    # --- Rule 6: optimization problems in equation/align/gather ---
    for m in OPT_PROBLEM_ENV_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if not (_OPT_OBJ_RE.search(body) and _OPT_ST_RE.search(body)):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex':      raw,
            'clean_text':     _clean_latex(body),
            'name':           None,
            'env_name':       'distilled',
            'rule_name':      'OPT_PROBLEM_ENV_RE',
            'structure_type': 'problem',
            '_start':         m.start(),
            '_end':           m.end(),
        })

    # --- Rule 7: prose open-problem paragraphs ---
    for m in PROSE_OPEN_PROBLEM_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append({
            'raw_latex':      body,
            'clean_text':     _clean_latex(body),
            'name':           None,
            'env_name':       'distilled',
            'rule_name':      'PROSE_OPEN_PROBLEM_RE',
            'structure_type': 'open_problem',
            '_start':         m.start(),
            '_end':           m.end(),
        })

    # --- Rule 8: 'leave ... to/for future work' prose ---
    for m in FUTURE_WORK_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append({
            'raw_latex':      body,
            'clean_text':     _clean_latex(body),
            'name':           None,
            'env_name':       'distilled',
            'rule_name':      'FUTURE_WORK_RE',
            'structure_type': 'open_problem',
            '_start':         m.start(),
            '_end':           m.end(),
        })

    return _dedup(results)
