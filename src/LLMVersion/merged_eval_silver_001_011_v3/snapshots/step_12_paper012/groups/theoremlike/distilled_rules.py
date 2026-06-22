import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Excluded environments – matches inside these are suppressed
# ---------------------------------------------------------------------------
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|figure|table|lstlisting|verbatim)\*?\}',
    re.IGNORECASE,
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    for m in _EXCLUDED_ENVS.finditer(text, 0, start):
        env = m.group(1)
        close = re.search(
            r'\\end\{' + re.escape(env) + r'\*?\}',
            text[m.end():],
            re.IGNORECASE,
        )
        if close:
            close_abs = m.end() + close.end()
            if m.start() < start and close_abs > end:
                return True
    return False


# ---------------------------------------------------------------------------
# Minimal LaTeX cleaner
# ---------------------------------------------------------------------------
def _clean_latex(text: str) -> str:
    """Strip common LaTeX commands, leaving readable text."""
    # Remove \label{...}, \cite{...}, \ref{...}, \eqref{...}
    text = re.sub(r'\\(?:label|cite|ref|eqref|cref|citep|citet)\{[^}]*\}', '', text)
    # Remove display math environments (keep nothing)
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}',
                  ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*?\$', ' [MATH] ', text)
    # Remove common formatting commands
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove remaining \command{...}
    text = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', text)
    # Remove remaining \command
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ---------------------------------------------------------------------------
# Subtype resolver
# ---------------------------------------------------------------------------
_SUBTYPE_MAP = {
    'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
    'lemma': 'lemma', 'lem': 'lemma',
    'proposition': 'proposition', 'prop': 'proposition',
    'property': 'proposition',
    'corollary': 'corollary', 'cor': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'problem': 'problem',
    'open_problem': 'open_problem', 'openproblem': 'open_problem',
    'openquestion': 'open_problem',
}

def _resolve_subtype(token: str) -> str:
    key = token.lower().rstrip('*')
    return _SUBTYPE_MAP.get(key, 'theorem')


# ---------------------------------------------------------------------------
# Rule 1: \begin{property}...\end{property}  ->  proposition
# (not in base extractor)
# ---------------------------------------------------------------------------
PATTERN_PROPERTY_ENV = re.compile(
    r'\\begin\{(property)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{property\}',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule 2: Custom named envs not in base map that appear in the wild
# Covers: \begin{fact}, \begin{observation}, \begin{criterion},
#         \begin{hypothesis}, \begin{question}, \begin{result},
#         \begin{assertion}, \begin{notation}
# These are frequently used as theorem-like environments
# ---------------------------------------------------------------------------
PATTERN_EXTRA_THEOREM_ENVS = re.compile(
    r'\\begin\{(fact|observation|criterion|hypothesis|question|result|assertion)\*?\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1\*?\}',
    re.DOTALL | re.IGNORECASE,
)

# Fix the backreference properly
PATTERN_EXTRA_THEOREM_ENVS = re.compile(
    r'\\begin\{(fact|observation|criterion|hypothesis|question|result|assertion)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1}',
    re.DOTALL | re.IGNORECASE,
)

_EXTRA_ENV_SUBTYPE = {
    'fact': 'theorem',
    'observation': 'theorem',
    'criterion': 'theorem',
    'hypothesis': 'theorem',
    'question': 'open_problem',
    'result': 'theorem',
    'assertion': 'claim',
}


# ---------------------------------------------------------------------------
# Rule 3: Optimization problems in equation/align envs starting with (P...) style label
# Catches \begin{equation}(P_0)... or \begin{align}...(P_k)... patterns
# ---------------------------------------------------------------------------
PATTERN_OPT_PROBLEM_ENV = re.compile(
    r'\\begin\{(?P<envname>equation|align|gather)\*?\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\*?\}',
    re.DOTALL | re.IGNORECASE,
)

_OPT_LABEL_RE = re.compile(
    r'^\s*(?:\\label\{[^}]*\}\s*)?'
    r'\((?:P|Q|LP|IP|SDP|OPT)(?:[_^]\{?[^\)\}]{0,15}\}?)?\)',
    re.IGNORECASE,
)

_OPT_OBJECTIVE_RE = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_OPT_CONSTRAINT_RE = re.compile(
    r'\\text\s*\{\s*s(?:ubject)?\s*\.?\s*t\.?\s*\}|'
    r'\\textit\s*\{\s*s\.t\.\s*\}|'
    r'\bsubject\s+to\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule 4: Open problem / open question in prose paragraphs
# Triggered by recognized open-problem phrases at paragraph start
# ---------------------------------------------------------------------------
PATTERN_OPEN_PROBLEM_PROSE = re.compile(
    r'(?:(?:^|\n{2,}))'
    r'(?P<body>'
    r'(?:'
    r'(?:It\s+(?:remains?|is\s+still)\s+(?:an?\s+)?open)'
    r'|(?:We\s+leave\b[^.]{0,250}?(?:open\s+(?:question|problem)|future\s+work))'
    r'|(?:An?\s+(?:interesting|important|natural|outstanding)\s+open\s+(?:problem|question))'
    r'|(?:The\s+following\s+(?:problem|question)\s+remains?\s+open)'
    r'|(?:(?:Several|Many|Some|Two|One|A\s+few)\s+(?:interesting\s+)?open\s+(?:questions?|problems?))'
    r'|(?:remain(?:s)?\s+open\s+(?:after|following|from)\s+this)'
    r')'
    r'[^\n]{10,}'
    r'(?:\n(?!\n)[^\n]+)*'
    r')',
    re.MULTILINE | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule 5: Open problem paragraphs in Discussion/Conclusion/Future-Work sections
# that contain interrogative sentences
# ---------------------------------------------------------------------------
PATTERN_OPEN_SECTION_HEADING = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*'
    r'(?:open\s*(?:problem|question)s?|discussion|conclusion|future\s*work|open\s*issue)'
    r'[^}]*\}',
    re.IGNORECASE,
)

PATTERN_SECTION_ANY = re.compile(
    r'\\(?:sub)*section\*?\{',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Rule 6: "We leave ... to future work" / "leave ... open" prose sentences
# ---------------------------------------------------------------------------
PATTERN_FUTURE_WORK_PROSE = re.compile(
    r'(?:(?:^|\n{2,}))'
    r'(?P<body>'
    r'(?:[A-Z][^.]{0,400}?'
    r'(?:We\s+leave\b[^.]{0,300}?(?:to|for)\s+future\s+(?:work|research))'
    r'[^.]*\.)'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedup(results: List[dict]) -> List[dict]:
    """Remove overlapping matches; prefer longer spans."""
    if not results:
        return results
    results.sort(key=lambda x: (x['_start'], -x['_end']))
    deduped = []
    last_end = -1
    for r in results:
        if r['_start'] >= last_end:
            deduped.append(r)
            last_end = r['_end']
    for r in deduped:
        r.pop('_start', None)

    return deduped


def _make_result(raw_latex: str, env_name: str, rule_name: str,
                 structure_type: str, name=None,
                 start: int = 0, end: int = 0) -> dict:
    return {
        'raw_latex': raw_latex,
        'clean_text': _clean_latex(raw_latex),
        'name': name,
        'env_name': 'distilled',
        'rule_name': rule_name,
        'structure_type': structure_type,
        '_start': start,
        '_end': end,
    }


def _strip_internal(d: dict) -> dict:
    d.pop('_start', None)
    d.pop('_end', None)
    return d


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule 1: \begin{property}...\end{property}
    # ------------------------------------------------------------------
    for m in PATTERN_PROPERTY_ENV.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        body = m.group('body')
        results.append(_make_result(
            raw_latex=m.group(0),
            env_name='distilled',
            rule_name='PATTERN_PROPERTY_ENV',
            structure_type='proposition',
            name=opt.strip() if opt else None,
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule 2: Extra theorem-like environments not in base map
    # ------------------------------------------------------------------
    for m in PATTERN_EXTRA_THEOREM_ENVS.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        env = m.group(1).lower()
        opt = m.group('opt')
        body = m.group('body')
        subtype = _EXTRA_ENV_SUBTYPE.get(env, 'theorem')
        results.append(_make_result(
            raw_latex=m.group(0),
            env_name='distilled',
            rule_name='PATTERN_EXTRA_THEOREM_ENVS',
            structure_type=subtype,
            name=opt.strip() if opt else None,
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule 3: Optimization problems in display math envs with (P...) label
    # ------------------------------------------------------------------
    for m in PATTERN_OPT_PROBLEM_ENV.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        stripped_body = re.sub(r'^\s*\\label\{[^}]*\}\s*', '', body, count=1)
        has_label = bool(_OPT_LABEL_RE.match(stripped_body))
        has_obj = bool(_OPT_OBJECTIVE_RE.search(body))
        has_con = bool(_OPT_CONSTRAINT_RE.search(body))
        if has_label or (has_obj and has_con):
            results.append(_make_result(
                raw_latex=m.group(0),
                env_name='distilled',
                rule_name='PATTERN_OPT_PROBLEM_ENV',
                structure_type='problem',
                name=None,
                start=m.start(),
                end=m.end(),
            ))

    # ------------------------------------------------------------------
    # Rule 4: Open problem in prose paragraphs (recognized phrases)
    # ------------------------------------------------------------------
    for m in PATTERN_OPEN_PROBLEM_PROSE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 60:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        results.append(_make_result(
            raw_latex=body,
            env_name='distilled',
            rule_name='PATTERN_OPEN_PROBLEM_PROSE',
            structure_type='open_problem',
            name=None,
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule 5: Interrogative paragraphs in open-problem/discussion sections
    # ------------------------------------------------------------------
    for sec_m in PATTERN_OPEN_SECTION_HEADING.finditer(text):
        sec_start = sec_m.end()
        # Find next section heading to bound content
        next_sec = PATTERN_SECTION_ANY.search(text, sec_start)
        sec_end = next_sec.start() if next_sec else len(text)
        section_text = text[sec_start:sec_end]

        paragraphs = re.split(r'\n{2,}', section_text)
        para_pos = sec_start
        for para in paragraphs:
            stripped = para.strip()
            # Must have '?' and enough content
            if '?' in stripped and len(stripped) > 80:
                abs_start = para_pos
                abs_end = para_pos + len(para)
                if _inside_excluded_env(text, abs_start, abs_end):
                    para_pos += len(para) + 2
                    continue
                results.append(_make_result(
                    raw_latex=stripped,
                    env_name='distilled',
                    rule_name='PATTERN_OPEN_SECTION_HEADING',
                    structure_type='open_problem',
                    name=None,
                    start=abs_start,
                    end=abs_end,
                ))
            para_pos += len(para) + 2  # +2 for the split separator

    # ------------------------------------------------------------------
    # Rule 6: "We leave ... to future work" sentences
    # ------------------------------------------------------------------
    for m in PATTERN_FUTURE_WORK_PROSE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Avoid duplicating what Rule 4 already caught
        already = any(
            r['_start'] <= m.start() <= r['_end']
            for r in results
            if r['structure_type'] == 'open_problem'
        )
        if already:
            continue
        results.append(_make_result(
            raw_latex=body,
            env_name='distilled',
            rule_name='PATTERN_FUTURE_WORK_PROSE',
            structure_type='open_problem',
            name=None,
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Deduplicate and strip internal keys
    # ------------------------------------------------------------------
    results = _dedup(results)
    return [_strip_internal(r) for r in results]
