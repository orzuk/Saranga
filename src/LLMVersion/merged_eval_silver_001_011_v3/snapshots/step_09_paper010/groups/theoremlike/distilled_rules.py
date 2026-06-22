import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX commands to produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \citep{...}, \citet{...}
    text = re.sub(r'\\(?:label|ref|eqref|cite[tp]?)\{[^}]*\}', '', text)
    # Remove \textbf{...}, \textit{...}, \emph{...}, \text{...} – keep content
    text = re.sub(r'\\(?:textbf|textit|textrm|text|emph|mathrm|mathbf|mathit|mathcal)\{([^}]*)\}', r'\1', text)
    # Remove display math environments markers
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove \[ \] \( \)
    text = re.sub(r'\\\[|\\\]|\\\(|\\\)', '', text)
    # Remove standalone LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', text)
    # Clean up leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Environments whose content should be excluded from extraction
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note|figure|table|lstlisting|verbatim)\}',
    re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is nested inside an excluded environment."""
    prefix = text[:start]
    for m in _EXCLUDED_ENV_RE.finditer(prefix):
        env = m.group(1)
        close = re.search(re.escape(r'\end{' + env + '}'), text[m.start():], re.IGNORECASE)
        if close and (m.start() + close.start() + len(close.group(0))) > start:
            return True
    return False


def _dedup(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the first (earliest start)."""
    results.sort(key=lambda d: d.get('_start', 0))
    out: List[dict] = []
    last_end = -1
    for r in results:
        s = r.get('_start', 0)
        e = r.get('_end', s + len(r['raw_latex']))
        if s >= last_end:
            out.append(r)
            last_end = e
    return out


def _subtype_from_env(env_name: str) -> str:
    """Map an environment name to a subtype string."""
    name = env_name.lower().rstrip('*')
    _MAP = {
        'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
        'lemma': 'lemma', 'lem': 'lemma',
        'proposition': 'proposition', 'prop': 'proposition', 'property': 'proposition',
        'corollary': 'corollary', 'cor': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem',
        'openproblem': 'open_problem', 'openquestion': 'open_problem', 'open': 'open_problem',
    }
    return _MAP.get(name, 'theorem')


# ---------------------------------------------------------------------------
# Rule 1 – Custom / non-standard theorem-like environments
# Catches \begin{property}, \begin{fact}, \begin{observation}, \begin{result},
# \begin{notation}, \begin{criterion}, \begin{question} and similar non-base envs.
# ---------------------------------------------------------------------------

CUSTOM_THRMLIKE_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>'
    r'property|Property|'
    r'fact|Fact|'
    r'observation|Observation|obs|'
    r'result|Result|'
    r'criterion|Criterion|'
    r'question|Question|'
    r'statement|Statement|'
    r'theorem\*|Theorem\*|'
    r'lemma\*|Lemma\*|'
    r'proposition\*|Proposition\*|'
    r'corollary\*|Corollary\*|'
    r'claim\*|Claim\*|'
    r'conjecture\*|Conjecture\*'
    r')\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)

_CUSTOM_ENV_SUBTYPE: Dict[str, str] = {
    'property': 'proposition', 'fact': 'theorem', 'observation': 'theorem',
    'result': 'theorem', 'criterion': 'theorem', 'question': 'open_problem',
    'statement': 'theorem',
    'theorem*': 'theorem', 'lemma*': 'lemma', 'proposition*': 'proposition',
    'corollary*': 'corollary', 'claim*': 'claim', 'conjecture*': 'conjecture',
}


def _extract_custom_env(text: str) -> List[dict]:
    results = []
    for m in CUSTOM_THRMLIKE_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        env = m.group('env')
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        stype = _CUSTOM_ENV_SUBTYPE.get(env.lower().rstrip('*'),
                _subtype_from_env(env))
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'CUSTOM_THRMLIKE_ENV_PATTERN',
            'structure_type': stype,
            '_start': m.start(),
            '_end': m.end(),
        })
    return results


# ---------------------------------------------------------------------------
# Rule 2 – Optimization problems inside equation/align environments whose body
# contains an objective function marker (\max or \min) and a constraint marker
# (\text{s.t.}, subject to, \text{subject to}, s.t.).
# ---------------------------------------------------------------------------

OPTIM_ENV_OUTER_PATTERN = re.compile(
    r'\\begin\{(?P<env>align\*?|equation\*?|gather\*?|alignat\*?|eqnarray\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)
_OPTIM_OBJ_RE = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_OPTIM_ST_RE = re.compile(
    r'(?:\\text\s*\{[^}]*s\.?\s*t\.?[^}]*\}'
    r'|\\mathrm\s*\{[^}]*s\.?\s*t\.?[^}]*\}'
    r'|subject\s+to'
    r'|\bst\b)',
    re.IGNORECASE
)


def _extract_optim_env(text: str) -> List[dict]:
    results = []
    for m in OPTIM_ENV_OUTER_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if not (_OPTIM_OBJ_RE.search(body) and _OPTIM_ST_RE.search(body)):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPTIM_ENV_OUTER_PATTERN',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })
    return results


# ---------------------------------------------------------------------------
# Rule 3 – Open-problem prose paragraphs (no environment wrapper).
# Anchors on strong open-problem lead phrases at the start of a paragraph or
# sentence. Captures up to the next blank line.
# ---------------------------------------------------------------------------

OPEN_PROBLEM_PROSE_PATTERN = re.compile(
    r'(?:(?<=\n\n)|(?<=\n)|(?:^))'   # paragraph/line boundary
    r'(?P<body>'
    r'(?:'
    r'(?:It\s+(?:remains?|is\s+still|is\s+an\s+open))'
    r'|(?:We\s+(?:leave|pose|conjecture|raise)(?:[^.]{0,60}?)(?:open\s+(?:question|problem)|future\s+work|to\s+future))'
    r'|(?:(?:An?|The\s+following|Several|Some)\s+(?:interesting|natural|important|intriguing)?\s*open\s+(?:question|problem))'
    r'|(?:(?:The|A)\s+(?:following|above)\s+(?:question|problem)\s+remains?\s+open)'
    r'|(?:We\s+leave\s+(?:this|these|the\s+following|as\s+(?:an?|intriguing)))'
    r')'
    r'[^\n]{20,}'        # rest of first line (min 20 chars of content)
    r'(?:\n(?!\n)[^\n]+)*'  # continuation lines until blank line
    r')',
    re.MULTILINE | re.IGNORECASE,
)


def _extract_open_problem_prose(text: str) -> List[dict]:
    results = []
    for m in OPEN_PROBLEM_PROSE_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPEN_PROBLEM_PROSE_PATTERN',
            'structure_type': 'open_problem',
            '_start': m.start(),
            '_end': m.end(),
        })
    return results


# ---------------------------------------------------------------------------
# Rule 4 – "Remain open" and "leave to future work" prose signals anywhere in text.
# ---------------------------------------------------------------------------

REMAIN_OPEN_PROSE_PATTERN = re.compile(
    r'(?P<body>'
    r'[A-Z][^.]{0,600}?'
    r'(?:'
    r'remain(?:s)?\s+open\b'
    r'|leave\s+(?:this|these|it|them|the\s+\w+)\s+(?:question\s+)?(?:to|for)\s+future\s+(?:work|research|study)'
    r'|open\s+(?:question|problem)s?\s+(?:remain|include|are)\b'
    r')'
    r'[^.]{0,400}\.(?:[^.]{0,200}\.){0,3}'
    r')',
    re.DOTALL | re.IGNORECASE,
)


def _extract_remain_open_prose(text: str) -> List[dict]:
    results = []
    for m in REMAIN_OPEN_PROSE_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        # Avoid duplicating if entirely inside a named open_problem environment
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'REMAIN_OPEN_PROSE_PATTERN',
            'structure_type': 'open_problem',
            '_start': m.start(),
            '_end': m.end(),
        })
    return results


# ---------------------------------------------------------------------------
# Rule 5 – Non-environment theorem-like statements introduced by a bold or
# emph keyword at the start of a paragraph, e.g.:
#   \textbf{Theorem.} ..., \textbf{Lemma X.} ..., \emph{Proposition 3.} ...
# ---------------------------------------------------------------------------

BOLD_EMPH_THRMLIKE_PATTERN = re.compile(
    r'(?:^|(?<=\n\n)|(?<=\n))'
    r'(?P<marker>'
    r'\\(?:textbf|textit|emph)\s*\{'
    r'\s*(?P<kw>theorem|lemma|proposition|corollary|claim|conjecture|problem|open\s*problem|fact|result|observation)'
    r'(?:\s+[\w\d.]+)?\s*[.:]?\s*\}'
    r')'
    r'(?P<body>'
    r'[^\n]{10,}'
    r'(?:\n(?!\n)[^\n]+)*'
    r')',
    re.MULTILINE | re.IGNORECASE,
)

_BOLD_KW_SUBTYPE: Dict[str, str] = {
    'theorem': 'theorem', 'lemma': 'lemma', 'proposition': 'proposition',
    'corollary': 'corollary', 'claim': 'claim', 'conjecture': 'conjecture',
    'problem': 'problem', 'open problem': 'open_problem',
    'fact': 'theorem', 'result': 'theorem', 'observation': 'theorem',
}


def _extract_bold_emph_thrmlike(text: str) -> List[dict]:
    results = []
    for m in BOLD_EMPH_THRMLIKE_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('kw').lower().strip()
        stype = _BOLD_KW_SUBTYPE.get(kw, 'theorem')
        raw = m.group(0)
        body = m.group('marker') + m.group('body')
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BOLD_EMPH_THRMLIKE_PATTERN',
            'structure_type': stype,
            '_start': m.start(),
            '_end': m.end(),
        })
    return results


# ---------------------------------------------------------------------------
# Rule 6 – Boxed display equations as problem formulations.
# \boxed{...} inside equation/align environments is a strong signal that the
# author is highlighting a key problem/result definition.
# ---------------------------------------------------------------------------

BOXED_EQUATION_PATTERN = re.compile(
    r'\\begin\{(?P<env>equation\*?|align\*?|gather\*?)\}'
    r'(?P<body>(?:(?!\\end\{(?:equation|align|gather)).)*?\\boxed\{(?:(?!\\end\{(?:equation|align|gather)).)*?\}(?:(?!\\end\{(?:equation|align|gather)).)*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)


def _extract_boxed_equation(text: str) -> List[dict]:
    results = []
    for m in BOXED_EQUATION_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BOXED_EQUATION_PATTERN',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })
    return results


# ---------------------------------------------------------------------------
# Rule 7 – Starred theorem-like environments that are NOT in the base map.
# e.g. \begin{theorem*}...\end{theorem*} etc.
# (The base extractor uses exact name matching; starred variants may be missed
# if not explicitly listed.)
# ---------------------------------------------------------------------------

STARRED_THRMLIKE_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>'
    r'(?:theorem|thm|lemma|lem|proposition|prop|corollary|cor|claim|conjecture|problem)\*'
    r')\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)


def _extract_starred_envs(text: str) -> List[dict]:
    results = []
    for m in STARRED_THRMLIKE_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        env = m.group('env')
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        base = env.rstrip('*').lower()
        stype = _subtype_from_env(base)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'STARRED_THRMLIKE_ENV_PATTERN',
            'structure_type': stype,
            '_start': m.start(),
            '_end': m.end(),
        })
    return results


# ---------------------------------------------------------------------------
# Rule 8 – Inline optimization problem paragraphs.
# A prose sentence ending with a colon or the word "following"/"maximize"/
# "minimize" immediately before a display math block (\[ or equation/align)
# that contains objective + constraint.
# ---------------------------------------------------------------------------

INLINE_OPTIM_PROSE_PATTERN = re.compile(
    r'(?:^|(?<=\n\n)|(?<=\n))'
    r'(?P<leadin>'
    r'(?:(?!\\begin\{(?:theorem|lemma|prop|cor|claim|conjecture|proof))[\s\S]){10,600}?'
    r'(?:following|maximize|minimiz(?:e|ing)|optimize|below|as\s+follows)\s*[:\.]?'
    r')\s*\n?'
    r'(?P<mathenv>'
    r'(?:\\begin\{(?P<env2>align\*?|equation\*?|gather\*?)\}(?P<body2>.*?)\\end\{(?P=env2)\})'
    r'|(?:\\\[(?P<body3>.*?)\\\])'
    r')',
    re.DOTALL | re.IGNORECASE,
)


def _extract_inline_optim_prose(text: str) -> List[dict]:
    results = []
    for m in INLINE_OPTIM_PROSE_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body2') or m.group('body3') or ''
        if not (_OPTIM_OBJ_RE.search(body) and _OPTIM_ST_RE.search(body)):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'INLINE_OPTIM_PROSE_PATTERN',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })
    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    """
    Run all supplementary extraction rules and return a deduplicated list of
    theorem-like structure dicts. Each dict has keys:
      raw_latex, clean_text, name, env_name, rule_name, structure_type.
    """
    all_results: List[dict] = []

    all_results.extend(_extract_custom_env(text))
    all_results.extend(_extract_starred_envs(text))
    all_results.extend(_extract_optim_env(text))
    all_results.extend(_extract_boxed_equation(text))
    all_results.extend(_extract_inline_optim_prose(text))
    all_results.extend(_extract_bold_emph_thrmlike(text))
    all_results.extend(_extract_open_problem_prose(text))
    all_results.extend(_extract_remain_open_prose(text))

    deduped = _dedup(all_results)

    # Strip internal position keys before returning
    for d in deduped:
        d.pop('_start', None)
        d.pop('_end', None)

    for r in deduped:
        r.pop('_start', None)

    return deduped
