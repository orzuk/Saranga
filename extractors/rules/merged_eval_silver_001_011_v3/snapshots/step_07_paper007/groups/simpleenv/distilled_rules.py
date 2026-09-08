import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Basic LaTeX -> plain-text cleaning."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common formatting commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|text|mathrm|mathit|mathbf|mathcal|mathbb)\{([^}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite variants
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*|citeA|citeNP)\{[^}]*\}', '', text)
    # Remove display math environments (rough)
    text = re.sub(r'\$\$.*?\$\$', '[MATH]', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', '[MATH]', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$[^$]*\$', '[MATH]', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})*', ' ', text)
    text = re.sub(r'[{}]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Environments whose interior we want to ignore for false-positive suppression
_EXCLUDED_ENV_NAMES = [
    'proof', 'figure', 'table', 'tabular', 'align', 'equation',
    'eqnarray', 'array', 'lstlisting', 'verbatim', 'tikzpicture',
    'algorithm', 'algorithmic',
]
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\*?\}',
    re.IGNORECASE,
)
_END_ENV_RE = re.compile(r'\\end\{([^}]+)\}')


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) sits inside an excluded environment."""
    prefix = text[:start]
    # Count unmatched \begin{excl_env} before our span
    depth_map: Dict[str, int] = {}
    for m in _EXCLUDED_ENV_RE.finditer(prefix):
        env = m.group(1).rstrip('*').lower()
        depth_map[env] = depth_map.get(env, 0) + 1
    for m in _END_ENV_RE.finditer(prefix):
        env = m.group(1).rstrip('*').lower()
        if env in depth_map and depth_map[env] > 0:
            depth_map[env] -= 1
    return any(v > 0 for v in depth_map.values())


def _subtype_from_env_or_keyword(keyword: str) -> str:
    """Map a matched keyword/env name to the correct subtype."""
    kw = keyword.rstrip('*').lower()
    if kw in ('remark', 'rem', 'note', 'observation', 'remarks'):
        return 'remark'
    if kw in ('example', 'exam', 'ex', 'illustration', 'examples'):
        return 'example'
    if kw in ('assumption', 'assumptions', 'assump'):
        return 'assumption'
    return 'theorem'


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# 1. Standard \begin{remark/example/assumption}...\end{...}
#    (catches variants the base parser may miss due to different spellings)
PATTERN_BEGIN_END_ENV = re.compile(
    r'\\begin\{'
    r'(?P<env>remarks?|examples?|exam|illustration|assumptions?|assump|observation|note)'
    r'\*?\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?:remarks?|examples?|exam|illustration|assumptions?|assump|observation|note)\*?\}',
    re.DOTALL | re.IGNORECASE,
)

# 2. {\bf Keyword.} ... paragraph-level bold inline marker
#    e.g. {\bf Remark.}  body text until blank line or section command
PATTERN_BF_KEYWORD = re.compile(
    r'\{\\bf\s+(?P<keyword>Remarks?|Examples?|Assumptions?|Note|Observation)s?'
    r'\.?\}\s*'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:section|subsection|subsubsection|chapter|paragraph|appendix|noindent\s*\{\\(?:sc|bf)|begin\{)).)+)',
    re.DOTALL,
)

# 3. \textbf{Keyword.} / \textit{Keyword.} / \emph{Keyword.} inline label
PATTERN_INLINE_LABEL = re.compile(
    r'\\(?:textbf|textit|emph)\{'
    r'(?P<keyword>Remarks?|Examples?|Assumptions?|Note|Observation)s?'
    r'\.?\}'
    r'[\s~]*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph)\b|\n\s*\n).)+)',
    re.DOTALL,
)

# 4. {\sc Remark[s].} paragraph style (small-caps)
PATTERN_SC_KEYWORD = re.compile(
    r'\{\\sc\s+(?P<keyword>Remarks?|Examples?|Assumptions?|Note|Observation)s?'
    r'\.?\}\s*'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:section|subsection|subsubsection|chapter|paragraph|appendix|begin\{|noindent\s*\{\\(?:sc|bf))).)+)',
    re.DOTALL,
)

# 5. \noindent{\sc Keyword[s].} style  (common in older LaTeX papers)
PATTERN_NOINDENT_SC = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<keyword>Remarks?|Examples?|Assumptions?|Note|Observation)s?'
    r'\.?\}[.\s]*'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:section|subsection|subsubsection|chapter|paragraph|appendix|noindent\s*\{\\(?:sc|bf)|begin\{|end\{document\})).)+)',
    re.DOTALL | re.IGNORECASE,
)

# 6. \noindent{\sc Keyword[s].} followed by \begin{list}...\end{list}
#    — captures the entire list body; items split separately in code
PATTERN_NOINDENT_SC_LIST = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<keyword>Remarks?|Examples?|Assumptions?)s?'
    r'\.?\}[.\s]*'
    r'(?P<list_env>\\begin\{(?:list|enumerate|itemize)\}.*?\\end\{(?:list|enumerate|itemize)\})',
    re.DOTALL | re.IGNORECASE,
)

_LIST_ITEM_SPLIT = re.compile(r'\\item\b', re.DOTALL)

# 7. \noindent {\bf Assumption N.} {\it body} or {\bf Assumption N.} body
PATTERN_NOINDENT_BF_ASSUMPTION = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>(?:Assumption|Remark|Example)s?[^.}]*)'
    r'(?:\}|\.)'
    r'[^{\\]*'
    r'(?:'
        r'(?:\{\\it\s+|\\textit\{|\\emph\{)'
        r'(?P<itbody>.*?)'
        r'\}'
        r'|'
        r'(?P<plainbody>.*?)'
        r'(?=\\noindent|\n\s*\n|\n\\(?:section|subsection|subsubsection|chapter|paragraph)|\\begin\{|$)'
    r')',
    re.DOTALL,
)

# 8. \begin{description}...\item[Assumption/Remark/Example ...]...\end{description}
PATTERN_DESCRIPTION_ENV = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE,
)

_DESCRIPTION_ITEM_RE = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|$)',
    re.DOTALL,
)

_DESCRIPTION_LABEL_KIND = [
    (re.compile(r'\bassumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bremarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bexamples?\b', re.IGNORECASE), 'example'),
    (re.compile(r'\bnotes?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bobservations?\b', re.IGNORECASE), 'remark'),
]

# 9. Standalone line starting with "Remark." / "Example." / "Assumption."
#    (plain text, no LaTeX command)
PATTERN_PLAIN_KEYWORD_LINE = re.compile(
    r'(?:^|\n)\s*'
    r'(?P<keyword>Remark|Example|Assumption|Note|Observation)s?'
    r'\s*[.:][ \t]+'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:section|subsection|subsubsection|chapter|paragraph|begin\{)).)+)',
    re.DOTALL | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _overlaps(spans: List[tuple], start: int, end: int) -> bool:
    for s, e in spans:
        if start < e and end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []
    used_spans: List[tuple] = []

    def add(raw: str, opt_name, env_name_str: str, rule: str,
            subtype: str, start: int, end: int):
        if not raw.strip():
            return
        if _overlaps(used_spans, start, end):
            return
        if _inside_excluded_env(text, start, end):
            return
        used_spans.append((start, end))
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': opt_name.strip() if opt_name else None,
            'env_name': 'distilled',
            'rule_name': rule,
            'structure_type': subtype,
        })

    # ------------------------------------------------------------------
    # Rule: PATTERN_BEGIN_END_ENV
    # ------------------------------------------------------------------
    for m in PATTERN_BEGIN_END_ENV.finditer(text):
        env = m.group('env')
        opt = m.group('opt')
        body = m.group('body')
        subtype = _subtype_from_env_or_keyword(env)
        add(body, opt, 'distilled', 'PATTERN_BEGIN_END_ENV', subtype,
            m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule: PATTERN_NOINDENT_SC_LIST  (must come before SC_KEYWORD
    #        so the list block is consumed first)
    # ------------------------------------------------------------------
    for m in PATTERN_NOINDENT_SC_LIST.finditer(text):
        keyword = m.group('keyword')
        subtype = _subtype_from_env_or_keyword(keyword)
        list_body = m.group('list_env')
        # Split on \item
        parts = _LIST_ITEM_SPLIT.split(list_body)
        for part in parts[1:]:  # first part is before any \item
            part = part.strip()
            if not part:
                continue
            # Remove leading list option [...] if present
            part = re.sub(r'^\[[^\]]*\]\s*', '', part)
            add(part, None, 'distilled', 'PATTERN_NOINDENT_SC_LIST', subtype,
                m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule: PATTERN_NOINDENT_SC
    # ------------------------------------------------------------------
    for m in PATTERN_NOINDENT_SC.finditer(text):
        keyword = m.group('keyword')
        body = m.group('body')
        subtype = _subtype_from_env_or_keyword(keyword)
        add(body, None, 'distilled', 'PATTERN_NOINDENT_SC', subtype,
            m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule: PATTERN_SC_KEYWORD
    # ------------------------------------------------------------------
    for m in PATTERN_SC_KEYWORD.finditer(text):
        keyword = m.group('keyword')
        body = m.group('body')
        subtype = _subtype_from_env_or_keyword(keyword)
        add(body, None, 'distilled', 'PATTERN_SC_KEYWORD', subtype,
            m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule: PATTERN_BF_KEYWORD
    # ------------------------------------------------------------------
    for m in PATTERN_BF_KEYWORD.finditer(text):
        keyword = m.group('keyword')
        body = m.group('body')
        subtype = _subtype_from_env_or_keyword(keyword)
        add(body, None, 'distilled', 'PATTERN_BF_KEYWORD', subtype,
            m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule: PATTERN_INLINE_LABEL
    # ------------------------------------------------------------------
    for m in PATTERN_INLINE_LABEL.finditer(text):
        keyword = m.group('keyword')
        body = m.group('body')
        subtype = _subtype_from_env_or_keyword(keyword)
        add(body, None, 'distilled', 'PATTERN_INLINE_LABEL', subtype,
            m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule: PATTERN_NOINDENT_BF_ASSUMPTION
    # ------------------------------------------------------------------
    for m in PATTERN_NOINDENT_BF_ASSUMPTION.finditer(text):
        label_text = m.group('label')
        subtype = _subtype_from_env_or_keyword(label_text)
        body = m.group('itbody') or m.group('plainbody') or ''
        body = body.strip()
        add(body, label_text, 'distilled', 'PATTERN_NOINDENT_BF_ASSUMPTION',
            subtype, m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule: PATTERN_DESCRIPTION_ENV
    # ------------------------------------------------------------------
    for desc_m in PATTERN_DESCRIPTION_ENV.finditer(text):
        block = desc_m.group('body')
        for item_m in _DESCRIPTION_ITEM_RE.finditer(block):
            item_label = item_m.group('label')
            item_body = item_m.group('body').strip()
            if not item_body:
                continue
            kind = None
            for pat, k in _DESCRIPTION_LABEL_KIND:
                if pat.search(item_label):
                    kind = k
                    break
            if kind is None:
                continue
            add(item_body, item_label, 'distilled', 'PATTERN_DESCRIPTION_ENV',
                kind, desc_m.start(), desc_m.end())

    # ------------------------------------------------------------------
    # Rule: PATTERN_PLAIN_KEYWORD_LINE
    # ------------------------------------------------------------------
    for m in PATTERN_PLAIN_KEYWORD_LINE.finditer(text):
        keyword = m.group('keyword')
        body = m.group('body')
        subtype = _subtype_from_env_or_keyword(keyword)
        add(body, None, 'distilled', 'PATTERN_PLAIN_KEYWORD_LINE', subtype,
            m.start(), m.end())

    return results
