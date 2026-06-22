import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return approximate plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*?\$', ' ', text, flags=re.DOTALL)
    # Remove common commands keeping their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite, \citeA etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[A-Za-z]*)\{[^}]*\}', '', text)
    # Remove remaining commands with optional/mandatory args
    text = re.sub(r'\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments to treat as "excluded" (we skip matches fully inside these)
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|figure|table|lstlisting|verbatim|tikzpicture)\}.*?\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is fully inside an excluded environment."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Pattern 1: \begin{remark/example/assumption}...\end{...} NOT caught by base
# (star variants + extra aliases)
# ---------------------------------------------------------------------------

_PATTERN_STAR_ENV = re.compile(
    r'\\begin\{(?P<env>remark\*|example\*|assumption\*|Remark\*?|Example\*?|Assumption\*?'
    r'|rem\*|exam\*|ex\*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

_ENV_KIND_RE = re.compile(r'remark|rem\b|note', re.IGNORECASE)
_ENV_EXAMPLE_RE = re.compile(r'example|exam\b|ex\b', re.IGNORECASE)
_ENV_ASSUMPTION_RE = re.compile(r'assumption', re.IGNORECASE)


def _env_to_kind(env_name: str) -> str:
    n = env_name.rstrip('*')
    if _ENV_ASSUMPTION_RE.match(n):
        return 'assumption'
    if _ENV_EXAMPLE_RE.match(n):
        return 'example'
    if _ENV_KIND_RE.match(n):
        return 'remark'
    return 'remark'


# ---------------------------------------------------------------------------
# Pattern 2: {\bf Remark.} or {\bf Remarks.} — bold-text inline keyword
# ---------------------------------------------------------------------------

_PATTERN_BF_KEYWORD = re.compile(
    r'\{\\bf\s+(?P<kw>Remark|Remarks|Note|Observation|Example|Assumption)s?\.?\}'
    r'[\s~.]*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\{\\bf\s+(?:Remark|Note|Observation|Example|Assumption|Theorem|Lemma|Proof|Corollary|Proposition|Definition)\b|\\(?:section|subsection|subsubsection|chapter|paragraph|appendix)\b|\n\s*\n\s*\n).)*)',
    re.DOTALL
)

_BF_KIND_MAP = {
    'remark': 'remark', 'remarks': 'remark', 'note': 'remark',
    'observation': 'remark', 'example': 'example', 'assumption': 'assumption',
}


def _bf_to_kind(kw: str) -> str:
    return _BF_KIND_MAP.get(kw.lower().rstrip('s'), 'remark')


# ---------------------------------------------------------------------------
# Pattern 3: \textbf{Remark} / \textbf{Example} / \textbf{Assumption} inline
# ---------------------------------------------------------------------------

# PRUNED — FP on paper006
# _PATTERN_TEXTBF_KEYWORD = re.compile(
#     r'\\textbf\{(?P<kw>Remark|Remarks|Note|Observation|Example|Assumption)s?\.?\}'
#     r'[\s~.]*'
#     r'(?P<body>(?:(?!\\(?:begin|end)\{|\\textbf\{(?:Remark|Note|Observation|Example|Assumption|Theorem|Lemma|Proof|Corollary|Proposition|Definition)\}|\\(?:section|subsection|subsubsection|chapter|paragraph|appendix)\b|\n\s*\n\s*\n).)*)',
#     re.DOTALL
# )


# ---------------------------------------------------------------------------
# Pattern 4: \emph{Remark.} / \textit{Remark.} inline label
# ---------------------------------------------------------------------------

_INLINE_LABEL_KEYWORDS = (
    'Remark', 'Remarks', 'Note', 'Observation',
    'Example', 'Assumption', 'Assumptions',
)
_INLINE_LABEL_KW_PAT = '|'.join(map(re.escape, _INLINE_LABEL_KEYWORDS))

_PATTERN_EMPH_KEYWORD = re.compile(
    r'(?P<cmd>\\(?:emph|textit))\{(?P<kw>' + _INLINE_LABEL_KW_PAT + r')s?\.?\}'
    r'[\s~]*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:emph|textit)\{(?:' + _INLINE_LABEL_KW_PAT + r')|\\(?:section|subsection|subsubsection|chapter|paragraph|appendix)\b|\n\s*\n\s*\n).)*)',
    re.DOTALL
)

_EMPH_KIND_MAP = {
    'remark': 'remark', 'remarks': 'remark', 'note': 'remark',
    'observation': 'remark', 'example': 'example',
    'assumption': 'assumption', 'assumptions': 'assumption',
}


def _emph_to_kind(kw: str) -> str:
    return _EMPH_KIND_MAP.get(kw.lower().rstrip('s'), 'remark')


# ---------------------------------------------------------------------------
# Pattern 5: \noindent{\sc Remark[s]?.} ... (sc-style header, no list)
# ---------------------------------------------------------------------------

_PATTERN_SC_REMARK = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<kw>Remark|Remarks|Note|Example|Assumption)s?\.?\}'
    r'[\s.]*'
    r'(?P<body>(?:(?!\\(?:noindent|section|subsection|subsubsection|chapter|paragraph|appendix)\b|\\begin\{|$).)*)',
    re.DOTALL | re.IGNORECASE
)

_SC_KIND_MAP = {
    'remark': 'remark', 'remarks': 'remark', 'note': 'remark',
    'example': 'example', 'assumption': 'assumption',
}


def _sc_to_kind(kw: str) -> str:
    return _SC_KIND_MAP.get(kw.lower().rstrip('s'), 'remark')


# ---------------------------------------------------------------------------
# Pattern 6: \noindent{\sc Remarks.} followed by \begin{list}...\end{list}
#            Each \item is a separate remark
# ---------------------------------------------------------------------------

_PATTERN_SC_REMARKS_LIST = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<kw>Remark|Remarks|Note|Example|Assumption)s?\.?\}'
    r'[\s.]*'
    r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL | re.IGNORECASE
)

_LIST_ITEM_RE = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item\b|\\end\{list\})',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Pattern 7: \begin{description} with \item[Assumption ...] labels
# ---------------------------------------------------------------------------

_PATTERN_DESCRIPTION_ENV = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)

_DESC_ITEM_RE = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|\\end\{description\}|$)',
    re.DOTALL
)

_DESC_ASSUMPTION_RE = re.compile(r'\bAssumptions?\b', re.IGNORECASE)
_DESC_REMARK_RE = re.compile(r'\bRemarks?\b|\bNotes?\b', re.IGNORECASE)
_DESC_EXAMPLE_RE = re.compile(r'\bExamples?\b', re.IGNORECASE)


def _desc_label_to_kind(label: str) -> str:
    if _DESC_ASSUMPTION_RE.search(label):
        return 'assumption'
    if _DESC_EXAMPLE_RE.search(label):
        return 'example'
    if _DESC_REMARK_RE.search(label):
        return 'remark'
    return None


# ---------------------------------------------------------------------------
# Pattern 8: \noindent {\bf Assumption N.} {\it body} style
# ---------------------------------------------------------------------------

_PATTERN_NOINDENT_BF_ASSUMPTION = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>Assumption[^.}\]]*)'
    r'[.}\]]*\}?'
    r'[\s.]*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>(?:(?!\\noindent|\n\s*\n\s*\n|\\begin\{|\\end\{|\\(?:section|subsection|subsubsection|chapter|appendix)\b).)*)',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Pattern 9: Paragraph-level "Remark N." or "Example N." or "Assumption N."
#            at the start of a line (number optional)
# ---------------------------------------------------------------------------

_PATTERN_PARA_KEYWORD = re.compile(
    r'(?:^|\n)(?P<kw>Remark|Example|Assumption)s?\s*(?P<num>\d+)?[.:]\s+'
    r'(?P<body>(?:(?!\n\s*\n\s*\n|\\(?:section|subsection|subsubsection|chapter|appendix)\b|\\begin\{).)*)',
    re.DOTALL | re.MULTILINE
)

_PARA_KIND_MAP = {
    'remark': 'remark', 'example': 'example', 'assumption': 'assumption',
}


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[Dict]:
    results: List[Dict] = []
    # Each entry: (start, end, dict)
    spans: List[tuple] = []

    def add(start: int, end: int, raw: str, kind: str, name_val, env_n: str, rule_n: str):
        if not raw.strip():
            return
        if _inside_excluded_env(text, start, end):
            return
        # Check overlap
        for s, e, _ in spans:
            if _spans_overlap(start, end, s, e):
                return
        clean = _clean_latex(raw)
        if not clean.strip():
            return
        spans.append((start, end, None))
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': name_val,
            'env_name': 'distilled',
            'rule_name': rule_n,
            'structure_type': kind,
        })

    # --- Rule: star/alias environments not in base ---
    for m in _PATTERN_STAR_ENV.finditer(text):
        env = m.group('env')
        opt = m.group('opt')
        body = m.group('body')
        kind = _env_to_kind(env)
        add(m.start(), m.end(), body, kind,
            opt.strip() if opt else None,
            'distilled', '_PATTERN_STAR_ENV')

    # --- Rule: {\bf Keyword.} inline ---
    for m in _PATTERN_BF_KEYWORD.finditer(text):
        kw = m.group('kw')
        body = m.group('body')
        kind = _bf_to_kind(kw)
        add(m.start(), m.end(), body, kind, None,
            'distilled', '_PATTERN_BF_KEYWORD')

    # --- Rule: \textbf{Keyword.} inline ---
#     for m in _PATTERN_TEXTBF_KEYWORD.finditer(text):
#         kw = m.group('kw')
#         body = m.group('body')
#         kind = _bf_to_kind(kw)
#         add(m.start(), m.end(), body, kind, None,
#             'distilled', '_PATTERN_TEXTBF_KEYWORD')

    # --- Rule: \emph{Keyword.} / \textit{Keyword.} inline ---
    for m in _PATTERN_EMPH_KEYWORD.finditer(text):
        kw = m.group('kw')
        body = m.group('body')
        kind = _emph_to_kind(kw)
        add(m.start(), m.end(), body, kind, None,
            'distilled', '_PATTERN_EMPH_KEYWORD')

    # --- Rule: \noindent{\sc Keyword.} plain paragraph ---
    for m in _PATTERN_SC_REMARK.finditer(text):
        kw = m.group('kw')
        body = m.group('body')
        # Skip if body is mostly a list environment (handled separately)
        if re.search(r'\\begin\{list\}', body):
            continue
        kind = _sc_to_kind(kw)
        add(m.start(), m.end(), body, kind, None,
            'distilled', '_PATTERN_SC_REMARK')

    # --- Rule: \noindent{\sc Remarks.} + \begin{list} — each \item ---
    for list_m in _PATTERN_SC_REMARKS_LIST.finditer(text):
        kw = list_m.group('kw')
        kind = _sc_to_kind(kw)
        list_body = list_m.group('list_env')
        list_start = text.find(list_body, list_m.start())
        for item_m in _LIST_ITEM_RE.finditer(list_body):
            body = item_m.group('body').strip()
            # Approximate span in original text
            i_start = list_start + item_m.start()
            i_end = list_start + item_m.end()
            add(i_start, i_end, body, kind, None,
                'distilled', '_PATTERN_SC_REMARKS_LIST')

    # --- Rule: \begin{description} with typed \item[...] labels ---
    for desc_m in _PATTERN_DESCRIPTION_ENV.finditer(text):
        desc_body = desc_m.group('body')
        desc_start = text.find(desc_body, desc_m.start())
        for item_m in _DESC_ITEM_RE.finditer(desc_body):
            label_txt = item_m.group('label')
            item_body = item_m.group('body').strip()
            kind = _desc_label_to_kind(label_txt)
            if kind is None:
                continue
            i_start = desc_start + item_m.start() if desc_start >= 0 else desc_m.start()
            i_end = i_start + (item_m.end() - item_m.start())
            add(i_start, i_end, item_body, kind,
                label_txt.strip() if label_txt.strip() else None,
                'distilled', '_PATTERN_DESCRIPTION_ENV')

    # --- Rule: \noindent {\bf Assumption N.} {\it body} ---
    for m in _PATTERN_NOINDENT_BF_ASSUMPTION.finditer(text):
        label_txt = m.group('label').strip()
        body = m.group('body')
        # Strip trailing closing brace from \it{...}
        body = re.sub(r'\}\s*$', '', body).strip()
        add(m.start(), m.end(), body, 'assumption', label_txt,
            'distilled', '_PATTERN_NOINDENT_BF_ASSUMPTION')

    # --- Rule: paragraph starting with "Remark/Example/Assumption N:" ---
    for m in _PATTERN_PARA_KEYWORD.finditer(text):
        kw = m.group('kw').lower()
        body = m.group('body').strip()
        num = m.group('num')
        kind = _PARA_KIND_MAP.get(kw, 'remark')
        name_val = (kw.capitalize() + ' ' + num) if num else kw.capitalize()
        add(m.start(), m.end(), body, kind, name_val,
            'distilled', '_PATTERN_PARA_KEYWORD')

    return results
