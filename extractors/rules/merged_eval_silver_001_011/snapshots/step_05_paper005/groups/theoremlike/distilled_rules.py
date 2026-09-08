import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text cleaner."""
    # Remove labels, refs, cites
    text = re.sub(r'\\(label|ref|eqref|cite[A-Za-z]*)\{[^}]*\}', '', text)
    # Remove common LaTeX commands but keep their argument text
    text = re.sub(r'\\(?:text|mathrm|mathbf|mathit|emph|textbf|textit|texttt)\{([^}]*)\}', r'\1', text)
    # Remove display-math environment wrappers
    text = re.sub(r'\\(begin|end)\{[^}]*\}', '', text)
    # Remove \nonumber, \quad, \qquad, \hspace, \vspace etc.
    text = re.sub(r'\\(nonumber|quad|qquad|left|right|Big|big|Bigg|bigg)\b', '', text)
    text = re.sub(r'\\(hspace|vspace)\{[^}]*\}', '', text)
    # Remove % comments
    text = re.sub(r'%[^\n]*', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments whose content we want to exclude from free-text scanning
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note|figure|table|tabular|lstlisting|verbatim)\}',
    re.IGNORECASE
)

_EXCLUDED_ENV_BLOCK = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note|figure|table|tabular|lstlisting|verbatim)\}.*?'
    r'\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_BLOCK.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _deduplicate(matches: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the one with more raw_latex content."""
    if not matches:
        return matches
    matches_sorted = sorted(matches, key=lambda d: (d.get('_start', 0), -len(d['raw_latex'])))
    result = []
    last_end = -1
    for m in matches_sorted:
        s = m.get('_start', 0)
        e = m.get('_end', s + len(m['raw_latex']))
        if s >= last_end:
            result.append(m)
            last_end = e
    return result


def _make_dict(raw_latex: str, name, env_name: str, rule_name: str,
               structure_type: str, start: int = 0, end: int = 0) -> dict:
    return {
        'raw_latex': raw_latex,
        'clean_text': _clean_latex(raw_latex),
        'name': name,
        'env_name': env_name,
        'rule_name': rule_name,
        'structure_type': structure_type,
        '_start': start,
        '_end': end,
    }


def _resolve_structure_type(env_name: str) -> str:
    """Map an environment name to a structure_type subtype."""
    env_lower = env_name.lower().rstrip('*')
    mapping = {
        'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
        'lemma': 'lemma', 'lem': 'lemma',
        'proposition': 'proposition', 'prop': 'proposition', 'property': 'proposition',
        'corollary': 'corollary', 'cor': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem',
    }
    return mapping.get(env_lower, 'theorem')


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule A: \begin{property}...\end{property} environments (custom env, -> proposition)
PATTERN_PROPERTY_ENV = re.compile(
    r'\\begin\{([Pp]roperty)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# Rule B: \begin{equation}...\end{equation} or \begin{equation*}...\end{equation*}
# that contain a (P_N) or (P0)/(P1) problem label -> problem
PATTERN_EQUATION_PROBLEM = re.compile(
    r'\\begin\{(equation\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?\(P[_0-9A-Za-z]*\).*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# Rule C: \begin{align}...\end{align} or \begin{align*}...\end{align*}
# that contain BOTH \max or \min AND \text{s.t.} -> problem
PATTERN_ALIGN_OPTIMIZATION = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)
_OPT_VERB = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_ST_VERB = re.compile(r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|\\text\s*\{\s*subject\s+to\s*\}', re.IGNORECASE)

# Rule D: Bare \ba...\ea blocks preceded by a meaningful preamble sentence -> problem
# \ba and \ea are shorthand display-math delimiters in some latex styles
PATTERN_BA_EA_PROBLEM = re.compile(
    r'(?:^|(?<=\n\n)|(?<=\n))(?P<preamble>[^\n%]{30,600}?)\n?\s*\\ba\s*(?P<body>.*?)\\ea',
    re.DOTALL
)
_PROBLEM_SIGNAL = re.compile(
    r'(mincut|RatioCut|Ratiocut|Ncut|MinmaxCut|cut\s*objective|partition|'
    r'objective\s*function|criterion|definitions?\s*are|minimize|maximiz)',
    re.IGNORECASE
)

# Rule E: align/align* environment containing (P_N) problem label -> problem
PATTERN_ALIGN_PROBLEM = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?\(P[_0-9A-Za-z]*\).*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# Rule F: Prose paragraph containing \argmin or \argmax that defines a named estimator -> problem
# Looks for a sentence containing "Define" or "Introduce" followed by equation blocks
PATTERN_PROSE_ARGMIN = re.compile(
    r'(?:(?:^|\n\n)[ \t]*)(?P<body>'
    r'(?:Define|Introduce)\s[^\n]{10,200}'   # opening sentence with signal word
    r'(?:[\s\S]*?)'                           # body
    r'\\(?:argmin|argmax)\b'                  # must contain \argmin or \argmax
    r'[\s\S]{10,2000}?'                       # continuation
    r')'
    r'(?=\n\n|\Z)',
    re.DOTALL
)

# Rule G: Subsection-body implicit theorem:
# text between \subsection{Computing...} header and the following \begin{algorithm}
PATTERN_SUBSECTION_IMPLICIT_THEOREM = re.compile(
    r'\\subsection\*?\{[^}]*Computing[^}]*\}'
    r'\s*(?P<body>(?:(?!\\begin\{(?:algorithm|theorem|lemma|proposition|corollary|proof)).)+?)'
    r'(?=\\begin\{)',
    re.DOTALL
)

# Rule H: \begin{align*} containing eigenvalue / spectral results preceded by citation
# (catches the Marchenko-Pastur / Geman / Silverstein theorem stated inline in align*)
PATTERN_ALIGN_STAR_THEOREM = re.compile(
    r'(?P<preamble>(?:proved?|shown?|establishes?|states?)[^%\n]{0,300}?\n?)'
    r'\\begin\{align\*\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{align\*\}',
    re.DOTALL
)
_EIGEN_SIGNAL = re.compile(r'\\lambda_?\s*[{(]?\s*(\\min|\\max|min|max)', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \begin{property}...\end{property} -> proposition
    # ------------------------------------------------------------------
    for m in PATTERN_PROPERTY_ENV.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        env = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        name = opt.strip() if opt else None
        results.append(_make_dict(
            raw_latex=body,
            name=name,
            env_name='distilled',
            rule_name='PATTERN_PROPERTY_ENV',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule B: equation environments with (P_N) label -> problem
    # ------------------------------------------------------------------
    for m in PATTERN_EQUATION_PROBLEM.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        results.append(_make_dict(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='PATTERN_EQUATION_PROBLEM',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule C: align/align* with \max/\min + s.t. -> problem
    # ------------------------------------------------------------------
    for m in PATTERN_ALIGN_OPTIMIZATION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if _OPT_VERB.search(body) and _ST_VERB.search(body):
            results.append(_make_dict(
                raw_latex=body,
                name=None,
                env_name='distilled',
                rule_name='PATTERN_ALIGN_OPTIMIZATION',
                structure_type='problem',
                start=m.start(),
                end=m.end(),
            ))

    # ------------------------------------------------------------------
    # Rule D: \ba...\ea blocks with problem-signal preamble -> problem
    # ------------------------------------------------------------------
    for m in PATTERN_BA_EA_PROBLEM.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        preamble = m.group('preamble')
        body = m.group('body')
        if not _PROBLEM_SIGNAL.search(preamble):
            continue
        combined = preamble.strip() + '\n' + body.strip()
        results.append(_make_dict(
            raw_latex=combined,
            name=None,
            env_name='distilled',
            rule_name='PATTERN_BA_EA_PROBLEM',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule E: align/align* with (P_N) label -> problem
    # ------------------------------------------------------------------
    for m in PATTERN_ALIGN_PROBLEM.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        # Skip if already caught by Rule C (optimization pattern)
        if _OPT_VERB.search(body) and _ST_VERB.search(body):
            continue
        results.append(_make_dict(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='PATTERN_ALIGN_PROBLEM',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule F: Prose paragraphs with \argmin/\argmax -> problem
    # ------------------------------------------------------------------
    for m in PATTERN_PROSE_ARGMIN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append(_make_dict(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='PATTERN_PROSE_ARGMIN',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule G: Subsection-body implicit theorem (before \begin{algorithm})
    # ------------------------------------------------------------------
    for m in PATTERN_SUBSECTION_IMPLICIT_THEOREM.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append(_make_dict(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='PATTERN_SUBSECTION_IMPLICIT_THEOREM',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Rule H: align* with eigenvalue content following a citation -> theorem
    # ------------------------------------------------------------------
    for m in PATTERN_ALIGN_STAR_THEOREM.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if not _EIGEN_SIGNAL.search(body):
            continue
        results.append(_make_dict(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='PATTERN_ALIGN_STAR_THEOREM',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        ))

    # ------------------------------------------------------------------
    # Deduplicate and clean internal keys
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
