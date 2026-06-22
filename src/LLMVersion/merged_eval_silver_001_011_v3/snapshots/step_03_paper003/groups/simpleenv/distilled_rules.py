import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: \begin{remark/example/assumption}...\end{...}
# Covers env names NOT already in the base map (and also covers base ones as
# a safety net — deduplication is handled downstream).
_SIMPLE_ENV_NAMES = [
    "remark", "Remark", "rem",
    "example", "Example", "exam", "ex",
    "assumption", "Assumption", "assumptions", "Assumptions",
    "note", "Note",
    "observation", "Observation",
    "illustration", "Illustration",
]

SIMPLE_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _SIMPLE_ENV_NAMES)) + r')\*?\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\*?\}',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 2: {\bf Keyword.} or {\bf Keyword} prose paragraph
# e.g.  {\bf Remark.}  text...
BOLD_BRACE_KW_RE = re.compile(
    r'\{\\bf\s+(?P<kw>Remark|Note|Observation|Example|Assumption|Illustration)\.?\}'
    r'\.?\s*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b)).+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b)',
    re.DOTALL,
)

# Pattern 3: \textbf{Keyword} or \textit{Keyword} lead-in paragraph
TEXTBF_KW_RE = re.compile(
    r'\\(?:textbf|textit|emph)\{(?P<kw>Remark|Note|Observation|Example|Assumption|Illustration)\.?\}'
    r'\.?\s*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b)).+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b)',
    re.DOTALL,
)

# Pattern 4: Inline keyword at start of line/paragraph (no braces)
# e.g.  "Remark. text..."  or  "Remark: text..."
INLINE_KW_RE = re.compile(
    r'(?:^|\n)[ \t]*(?P<kw>Remark|Note|Observation|Example|Assumption|Illustration)[.:]\s+'
    r'(?P<body>(?:(?!\n[ \t]*\n|\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b)).+?)'
    r'(?=\n[ \t]*\n|\Z|\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b)',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Excluded environments (we skip matches inside these)
# ---------------------------------------------------------------------------
_EXCLUDED_ENVS = [
    "proof", "figure", "table", "tikzpicture", "algorithm", "lstlisting",
    "verbatim", "comment",
]
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENVS)) + r')\*?\}.*?\\end\{\1\*?\}',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX commands and return readable plain text."""
    # Remove labels, refs, cites
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?'
                  r'\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}',
                  ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*?\$', '[MATH]', text)
    # Remove common formatting commands
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|'
                  r'mathcal|mathbb|mathsf|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove \bf, \it etc in braces
    text = re.sub(r'\{\\(?:bf|it|rm|sc|sl|sf|tt)\s+([^}]*)\}', r'\1', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\{[^}]*\}|\[[^\]]*\])*', ' ', text)
    # Remove leftover braces and percent comments
    text = re.sub(r'%[^\n]*', '', text)
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _subtype_from_keyword(kw: str) -> str:
    """Map a keyword string to a structure subtype."""
    kw_lower = kw.lower().rstrip('*').rstrip('.')
    if kw_lower in ('remark', 'note', 'observation'):
        return 'remark'
    if kw_lower in ('example', 'illustration'):
        return 'example'
    if kw_lower in ('assumption', 'assumptions'):
        return 'assumption'
    return 'theorem'  # ambiguous fallback


def _subtype_from_env(env_name: str) -> str:
    """Map an environment name to a structure subtype."""
    return _subtype_from_keyword(env_name)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _overlaps(a_start: int, a_end: int, spans: List[tuple]) -> bool:
    for s, e in spans:
        if a_start < e and a_end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    """
    Extract remark / example / assumption structures from LaTeX source.
    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    used_spans: List[tuple] = []  # (start, end) of already-claimed text spans

    # ------------------------------------------------------------------
    # Rule A: formal \begin{env}...\end{env} environments
    # ------------------------------------------------------------------
    for m in SIMPLE_ENV_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, used_spans):
            continue
        env_name_raw = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        structure_type = _subtype_from_env(env_name_raw)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'SIMPLE_ENV_RE',
            'structure_type': structure_type,
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule B: {\bf Keyword.} paragraph
    # ------------------------------------------------------------------
    for m in BOLD_BRACE_KW_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, used_spans):
            continue
        kw = m.group('kw')
        body = m.group('body')
        structure_type = _subtype_from_keyword(kw)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BOLD_BRACE_KW_RE',
            'structure_type': structure_type,
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule C: \textbf{Keyword} / \textit{Keyword} paragraph
    # ------------------------------------------------------------------
    for m in TEXTBF_KW_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, used_spans):
            continue
        kw = m.group('kw')
        body = m.group('body')
        structure_type = _subtype_from_keyword(kw)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'TEXTBF_KW_RE',
            'structure_type': structure_type,
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule D: Inline "Keyword. text..." at paragraph start
    # ------------------------------------------------------------------
    for m in INLINE_KW_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, used_spans):
            continue
        kw = m.group('kw')
        body = m.group('body')
        structure_type = _subtype_from_keyword(kw)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'INLINE_KW_RE',
            'structure_type': structure_type,
        })
        used_spans.append((start, end))

    return results
