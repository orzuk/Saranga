import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Inline bold/italic keyword markers for remark-family
INLINE_REMARK_PATTERN = re.compile(
    r'(?:^|\n)[ \t]*'
    r'(?:'
    r'\\textbf\{(?:Remark|Note|Observation|Remark\*)\}'
    r'|\\textit\{(?:Remark|Note|Observation|Remark\*)\}'
    r'|\\emph\{(?:Remark|Note|Observation|Remark\*)\}'
    r')'
    r'[.:~\s]*'
    r'(?P<body>.+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:sub)*section\b|\\begin\{(?!remark|note))',
    re.DOTALL | re.IGNORECASE,
)

# Inline bold/italic keyword markers for example-family
INLINE_EXAMPLE_PATTERN = re.compile(
    r'(?:^|\n)[ \t]*'
    r'(?:'
    r'\\textbf\{(?:Example|Illustration|Example\*)\}'
    r'|\\textit\{(?:Example|Illustration|Example\*)\}'
    r'|\\emph\{(?:Example|Illustration|Example\*)\}'
    r'|(?:Example|Illustration)\s+\d+\s*[.:]'
    r')'
    r'[.:~\s]*'
    r'(?P<body>.+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:sub)*section\b|\\begin\{(?!example|illustration))',
    re.DOTALL | re.IGNORECASE,
)

# Inline bold/italic keyword markers for assumption-family
INLINE_ASSUMPTION_PATTERN = re.compile(
    r'(?:^|\n)[ \t]*'
    r'(?:'
    r'\\textbf\{(?:Assumption|Assumptions|Assumption\*)\}'
    r'|\\textit\{(?:Assumption|Assumptions|Assumption\*)\}'
    r'|\\emph\{(?:Assumption|Assumptions|Assumption\*)\}'
    r'|(?:Assumption|Assumptions)\s+\d+\s*[.:]'
    r')'
    r'[.:~\s]*'
    r'(?P<body>.+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:sub)*section\b|\\begin\{(?!assumption))',
    re.DOTALL | re.IGNORECASE,
)

# Paragraph-level pattern: lines beginning with "Remark." or "Remark N." etc.
PARA_REMARK_PATTERN = re.compile(
    r'(?:^|\n\n)[ \t]*'
    r'(?P<leader>(?:Remark|Note|Observation)\.?(?:\s+\d+\.)?)\s+'
    r'(?P<body>.+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:sub)*section\b|\\begin\{)',
    re.DOTALL | re.IGNORECASE,
)

# Paragraph-level pattern: lines beginning with "Example." or "Example N." etc.
PARA_EXAMPLE_PATTERN = re.compile(
    r'(?:^|\n\n)[ \t]*'
    r'(?P<leader>(?:Example|Illustration)\.?(?:\s+\d+\.)?)\s+'
    r'(?P<body>.+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:sub)*section\b|\\begin\{)',
    re.DOTALL | re.IGNORECASE,
)

# Paragraph-level pattern: lines beginning with "Assumption." or "Assumption N." etc.
PARA_ASSUMPTION_PATTERN = re.compile(
    r'(?:^|\n\n)[ \t]*'
    r'(?P<leader>(?:Assumption|Assumptions)\.?(?:\s+\d+\.)?)\s+'
    r'(?P<body>.+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:sub)*section\b|\\begin\{)',
    re.DOTALL | re.IGNORECASE,
)

# Environments that may contain simpleenv text but should be excluded as containers
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|theorem|lemma|proposition|corollary|thm|lem|prop|cor|Theorem|Lemma)\}',
    re.IGNORECASE,
)

_ENV_SPAN_PATTERN = re.compile(
    r'\\begin\{(?P<envname>[a-zA-Z*]+)\}.*?\\end\{(?P=envname)\}',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LATEX_CMD_RE = re.compile(r'\\[a-zA-Z]+\*?\{([^}]*)\}|\\[a-zA-Z]+\*?|\{|\}')
_WHITESPACE_RE = re.compile(r'\s+')
_COMMENT_RE = re.compile(r'%[^\n]*')


def _clean_latex(text: str) -> str:
    """Strip LaTeX commands and comments, collapse whitespace."""
    text = _COMMENT_RE.sub('', text)
    text = _LATEX_CMD_RE.sub(lambda m: m.group(1) if m.group(1) else '', text)
    text = _WHITESPACE_RE.sub(' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if [start, end) is nested inside an excluded environment."""
    for m in _ENV_SPAN_PATTERN.finditer(text):
        env_name = m.group('envname').lower().rstrip('*')
        if env_name in {'proof', 'theorem', 'lemma', 'proposition', 'corollary',
                        'thm', 'lem', 'prop', 'cor'}:
            if m.start() <= start and end <= m.end():
                return True
    return False


def _already_covered_by_base(text: str, start: int, end: int) -> bool:
    """
    Return True if [start, end) is inside a \begin{env}...\end{env} block
    for environments already handled by the base parser (remark, example, assumption,
    and their variants).
    """
    base_envs = re.compile(
        r'\\begin\{(remark|Remark|rem|note|example|Example|exam|ex|'
        r'assumption|Assumption|assumptions|Assumptions)\}.*?'
        r'\\end\{\1\}',
        re.DOTALL | re.IGNORECASE,
    )
    for m in base_envs.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _determine_subtype(marker_text: str) -> str:
    """Determine the structure subtype from matched keyword/env name."""
    normalized = marker_text.lower().rstrip('*').strip()
    if normalized in ('remark', 'note', 'observation'):
        return 'remark'
    if normalized in ('example', 'illustration'):
        return 'example'
    if normalized in ('assumption', 'assumptions'):
        return 'assumption'
    return 'theorem'


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    """
    Extract remark, example, and assumption structures not already caught by
    the base \begin/\end environment parser.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # (pattern_variable_name, compiled_pattern, subtype_source)
    pattern_specs = [
        ('INLINE_REMARK_PATTERN',     INLINE_REMARK_PATTERN,     'remark'),
        ('INLINE_EXAMPLE_PATTERN',    INLINE_EXAMPLE_PATTERN,    'example'),
        ('INLINE_ASSUMPTION_PATTERN', INLINE_ASSUMPTION_PATTERN, 'assumption'),
        ('PARA_REMARK_PATTERN',       PARA_REMARK_PATTERN,       'remark'),
        ('PARA_EXAMPLE_PATTERN',      PARA_EXAMPLE_PATTERN,      'example'),
        ('PARA_ASSUMPTION_PATTERN',   PARA_ASSUMPTION_PATTERN,   'assumption'),
    ]

    seen_spans: List[tuple] = []  # list of (start, end)

    def _overlaps(start: int, end: int) -> bool:
        for s, e in seen_spans:
            if start < e and end > s:
                return True
        return False

    for rule_name, pattern, default_subtype in pattern_specs:
        for m in pattern.finditer(text):
            start = m.start()
            end = m.end()

            # Skip if already handled by base parser
            if _already_covered_by_base(text, start, end):
                continue

            # Skip if inside an excluded environment
            if _inside_excluded_env(text, start, end):
                continue

            # Skip if overlaps with an already-recorded span
            if _overlaps(start, end):
                continue

            raw_body = m.group('body') if 'body' in m.groupdict() else m.group(0)

            # Try to read the leader/keyword to determine subtype
            leader = ''
            for group_name in ('leader',):
                try:
                    leader = m.group(group_name) or ''
                    break
                except IndexError:
                    pass

            if not leader:
                # For inline patterns the keyword is in the full match prefix
                full_match = m.group(0)
                keyword_m = re.search(
                    r'(?:Remark|Note|Observation|Example|Illustration|Assumption|Assumptions)',
                    full_match,
                    re.IGNORECASE,
                )
                leader = keyword_m.group(0) if keyword_m else ''

            subtype = _determine_subtype(leader) if leader else default_subtype

            clean = _clean_latex(raw_body)
            if not clean:
                continue

            seen_spans.append((start, end))
            results.append({
                'raw_latex': raw_body.strip(),
                'clean_text': clean,
                'name': None,
                'env_name': 'distilled',
                'rule_name': rule_name,
                'structure_type': subtype,
            })

    return results
