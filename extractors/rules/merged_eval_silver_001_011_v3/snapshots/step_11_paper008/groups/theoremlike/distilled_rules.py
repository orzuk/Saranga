import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Matches \begin{property}...\end{property} (maps to proposition)
PATTERN_PROPERTY_ENV = re.compile(
    r'\\begin\{([Pp]roperty)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1}',
    re.DOTALL
)

# Matches optimization problems in equation/align environments whose body
# contains an objective (\max or \min) AND a constraint marker (s.t./subject to)
PATTERN_OPTIMIZATION_ENV = re.compile(
    r'\\begin\{(?P<envname>align\*?|equation\*?|gather\*?|alignat\*?|flalign\*?)\}'
    r'(?P<body>.*?)'
    r'\\end{(?P=envname)}',
    re.DOTALL
)

# Matches open-problem statements in prose paragraphs (open question / leave ... future work)
PATTERN_OPEN_PROBLEM_PROSE = re.compile(
    r'(?:(?:^|\n\n)'
    r'(?P<body>'
    r'(?:'
    r'(?:We\s+leave\b[^\n]{0,500}?(?:open\s+question|future\s+work))'
    r'|(?:remain(?:s)?\s+open\b[^\n]{0,500})'
    r'|(?:open\s+(?:question|problem)s?\s+(?:remain|is|are)\b[^\n]{0,500})'
    r'|(?:(?:interesting|important|natural)\s+open\s+(?:question|problem)\b[^\n]{0,500})'
    r')'
    r'(?:\n(?!\n)[^\n]{0,300}){0,6}'
    r')'
    r')',
    re.MULTILINE | re.IGNORECASE | re.DOTALL
)

# Matches paragraphs with interrogative sentences in discussion/open-problems sections
PATTERN_OPEN_SECTION_HEADING = re.compile(
    r'\\(?:sub)*section\*?\s*\{[^}]*(?:open\s*(?:problem|question)s?|'
    r'discussion|conclusion|future\s*work)[^}]*\}',
    re.IGNORECASE
)

# Matches \begin{open_problem}/\begin{openProblem}/\begin{openquestion} etc.
# (supplements base map which may not have all variants)
PATTERN_OPEN_PROBLEM_ENV = re.compile(
    r'\\begin\{(?P<envname>open[_\s]?[Pp]roblem\*?|open[Qq]uestion\*?|open[_\s]?[Pp]roblems\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{(?P=envname)}',
    re.DOTALL
)

# Excluded environments: do not extract from inside these
EXCLUDED_ENVS = re.compile(
    r'\\begin\{(?:proof|Proof|example|Example|remark|Remark|verbatim|lstlisting|comment)\}',
    re.DOTALL
)

EXCLUDED_ENV_FULL = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|verbatim|lstlisting|comment)\}'
    r'.*?'
    r'\\end{\1}',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup to produce approximate plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \eqref{...}
    text = re.sub(r'\\(?:label|ref|eqref|cite|citep|citet|pageref)\{[^}]*\}', '', text)
    # Remove \begin{...} and \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove common formatting commands preserving content
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathbf|mathit|mathrm|mathcal|mathbb|mathsf)\{([^}]*)\}', r'\1', text)
    # Remove remaining simple commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in EXCLUDED_ENV_FULL.finditer(text):
        if m.start() <= start and m.end() >= end:
            return True
    return False


def _overlaps(new_start: int, new_end: int, existing: List[dict]) -> bool:
    """Return True if [new_start, new_end) overlaps any existing match span."""
    for e in existing:
        es = e.get('_start', -1)
        ee = e.get('_end', -1)
        if es < new_end and ee > new_start:
            return True
    return False


def _determine_structure_type_from_env(env_name: str) -> str:
    """Map an environment name to a structure_type string."""
    lower = env_name.lower().rstrip('*')
    if lower in ('theorem', 'thm', 'theo'):
        return 'theorem'
    if lower in ('lemma', 'lem'):
        return 'lemma'
    if lower in ('proposition', 'prop'):
        return 'proposition'
    if lower in ('corollary', 'cor'):
        return 'corollary'
    if lower in ('claim',):
        return 'claim'
    if lower in ('conjecture',):
        return 'conjecture'
    if lower in ('problem',):
        return 'problem'
    if lower in ('property',):
        return 'proposition'
    if 'open' in lower:
        return 'open_problem'
    return 'theorem'


# ---------------------------------------------------------------------------
# Sub-extractors
# ---------------------------------------------------------------------------

def _extract_property_envs(text: str, results: List[dict]) -> None:
    """Extract \\begin{property}...\\end{property} as proposition."""
    for m in PATTERN_PROPERTY_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, results):
            continue
        env_name = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PROPERTY_ENV',
            'structure_type': 'proposition',
            '_start': start,
            '_end': end,
        })


def _extract_open_problem_envs(text: str, results: List[dict]) -> None:
    """Extract custom open-problem environments not in the base map."""
    for m in PATTERN_OPEN_PROBLEM_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, results):
            continue
        env_name = m.group('envname')
        opt = m.group('opt')
        body = m.group('body')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_OPEN_PROBLEM_ENV',
            'structure_type': 'open_problem',
            '_start': start,
            '_end': end,
        })


_OBJ_RE = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_ST_RE = re.compile(r'(?:\\text\s*\{[^}]{0,30}?s\.?\s*t\.?[^}]{0,10}?\}|subject\s+to)', re.IGNORECASE)


def _extract_optimization_envs(text: str, results: List[dict]) -> None:
    """
    Extract align/equation environments whose body contains both an
    objective (\\max or \\min) and a constraint marker (s.t. / subject to).
    Tagged as 'problem'.
    """
    for m in PATTERN_OPTIMIZATION_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, results):
            continue
        body = m.group('body')
        if not (_OBJ_RE.search(body) and _ST_RE.search(body)):
            continue
        env_name = m.group('envname')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_OPTIMIZATION_ENV',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })


def _extract_open_problem_prose(text: str, results: List[dict]) -> None:
    """
    Extract open-problem statements from running prose paragraphs.
    Looks for paragraphs containing 'leave ... open question/future work',
    'remain open', etc.
    """
    for m in PATTERN_OPEN_PROBLEM_PROSE.finditer(text):
        start = m.start()
        body = m.group('body').strip()
        if len(body) < 60:
            continue
        end = start + len(body)
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, results):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_OPEN_PROBLEM_PROSE',
            'structure_type': 'open_problem',
            '_start': start,
            '_end': end,
        })


def _extract_interrogative_open_problems(text: str, results: List[dict]) -> None:
    """
    Extract paragraphs with question sentences that appear inside
    discussion/conclusion/future-work/open-problems sections.
    Tagged as 'open_problem'.
    """
    for sec_m in PATTERN_OPEN_SECTION_HEADING.finditer(text):
        sec_start = sec_m.end()
        # bound by next section heading
        next_sec = re.search(r'\\(?:sub)*section\*?\s*\{', text[sec_start:])
        sec_end = sec_start + next_sec.start() if next_sec else len(text)
        section_text = text[sec_start:sec_end]

        # split into paragraphs
        paragraphs = re.split(r'\n{2,}', section_text)
        offset = sec_start
        for para in paragraphs:
            stripped = para.strip()
            # must contain at least one '?' and be substantial
            if '?' in stripped and len(stripped) >= 80:
                # avoid matching short headings or pure-math blocks
                word_count = len(re.findall(r'[a-zA-Z]{3,}', stripped))
                if word_count < 10:
                    offset += len(para) + 2
                    continue
                start = offset
                end = offset + len(para)
                if _inside_excluded_env(text, start, end):
                    offset += len(para) + 2
                    continue
                if _overlaps(start, end, results):
                    offset += len(para) + 2
                    continue
                results.append({
                    'raw_latex': stripped,
                    'clean_text': _clean_latex(stripped),
                    'name': None,
                    'env_name': 'distilled',
                    'rule_name': 'PATTERN_OPEN_SECTION_HEADING',
                    'structure_type': 'open_problem',
                    '_start': start,
                    '_end': end,
                })
            offset += len(para) + 2  # +2 for the \n\n separator


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    """
    Supplementary extractor for theorem-like structures not caught by the
    base environment extractor.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # 1. \begin{property}...\end{property}  -> proposition
    _extract_property_envs(text, results)

    # 2. Custom open-problem environments not in base map
    _extract_open_problem_envs(text, results)

    # 3. Optimization problems inside align/equation with \max/\min + s.t.
    _extract_optimization_envs(text, results)

    # 4. Prose open-problem paragraphs (leave ... open question / future work)
    _extract_open_problem_prose(text, results)

    # 5. Interrogative paragraphs inside discussion/conclusion/open-problems sections
    _extract_interrogative_open_problems(text, results)

    # Strip internal tracking keys before returning
    clean_results = []
    for r in results:
        clean_results.append({
            'raw_latex': r['raw_latex'],
            'clean_text': r['clean_text'],
            'name': r['name'],
            'env_name': r['env_name'],
            'rule_name': r['rule_name'],
            'structure_type': r['structure_type'],
        })

    return clean_results
