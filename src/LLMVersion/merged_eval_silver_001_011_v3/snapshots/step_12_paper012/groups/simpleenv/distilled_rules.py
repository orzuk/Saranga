import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX markup to produce plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|textsf|texttt|text)\{([^}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite, \citeA etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[A-Za-z]*)\{[^}]*\}', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|eqnarray|gather|multline)\*?\}.*?\\end\{(?:equation|align|eqnarray|gather|multline)\*?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math (simple pass)
    text = re.sub(r'\$[^$]*\$', ' ', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*', ' ', text)
    # Clean up braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments whose interiors should suppress extraction
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|theorem|lemma|proposition|corollary|definition|algorithm|figure|table)\*?\}',
    re.IGNORECASE
)
_EXCLUDED_ENV_CLOSE_RE = re.compile(
    r'\\end\{(proof|theorem|lemma|proposition|corollary|definition|algorithm|figure|table)\*?\}',
    re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start,end) is inside a proof/theorem/etc. environment."""
    prefix = text[:start]
    opens = len(_EXCLUDED_ENV_RE.findall(prefix))
    closes = len(_EXCLUDED_ENV_CLOSE_RE.findall(prefix))
    return opens > closes


def _determine_subtype(env_or_keyword: str) -> str:
    """Map an environment name or keyword to a subtype."""
    s = env_or_keyword.strip().rstrip('*').lower()
    if s in ('remark', 'rem', 'note', 'observation', 'remarks'):
        return 'remark'
    if s in ('example', 'exam', 'ex', 'illustration', 'exmp', 'exmpl'):
        return 'example'
    if s in ('assumption', 'assumptions', 'assume'):
        return 'assumption'
    return 'theorem'


def _make_result(raw_latex: str, name, env_name: str, rule_name: str, structure_type: str) -> dict:
    return {
        'raw_latex': raw_latex,
        'clean_text': _clean_latex(raw_latex),
        'name': name,
        'env_name': env_name,
        'rule_name': rule_name,
        'structure_type': structure_type,
    }


# ---------------------------------------------------------------------------
# Pattern 1: \textbf{Remark[:/.]?} inline (not in an environment)
# Catches: \textbf{Remark:}, \textbf{Remark.}, \textbf{Remark}
# ---------------------------------------------------------------------------
TEXTBF_REMARK_RE = re.compile(
    r'\\textbf\{(Remark|Note|Observation)[s]?[.:}]?\}[\s:]*'
    r'(?P<body>(?:(?!\\begin\{|\\section|\\subsection|\\subsubsection|\\paragraph|\\chapter).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 2: {\bf Remark.} or {\bf Remarks.} bold-group inline
# ---------------------------------------------------------------------------
BF_GROUP_REMARK_RE = re.compile(
    r'\{\\bf\s+(Remark|Note|Observation)[s]?\.?\}[\s.]*'
    r'(?P<body>(?:(?!\\begin\{|\\section|\\subsection|\\subsubsection|\\paragraph|\\chapter).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 3: \noindent{\sc Remark[s]?.} free paragraph (not list)
# ---------------------------------------------------------------------------
SC_REMARK_FREE_RE = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}\s*'
    r'(?P<body>(?:(?!\\begin\{list\}|\\begin\{itemize\}|\\begin\{enumerate\}|\\noindent|\\section|\\subsection|\\subsubsection|\\paragraph|\\chapter|\\appendix).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 4: \noindent{\sc Remark[s]?.} + \begin{list}...\end{list} -> each \item
# ---------------------------------------------------------------------------
# PRUNED — FP on paper004
# SC_REMARK_LIST_OUTER_RE = re.compile(
#     r'\\noindent\s*\{\\sc\s+Remarks?\.?\}\s*'
#     r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
#     re.DOTALL | re.IGNORECASE
# )
LIST_ITEM_RE = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item|\Z)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 5: \emph{Remark.} / \textit{Remark.} inline label
# ---------------------------------------------------------------------------
EMPH_KEYWORD_RE = re.compile(
    r'\\(?:emph|textit)\{(?P<kw>Remark|Note|Observation|Example|Assumption)[s]?\.?\}'
    r'[\s~]*'
    r'(?P<body>(?:(?!\\begin\{|\\section|\\subsection|\\subsubsection|\\paragraph|\\chapter|\n\s*\n).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 6: \begin{description} with \item[Assumption ...] items
# ---------------------------------------------------------------------------
DESCRIPTION_ENV_RE = re.compile(
    r'\\begin\{description\}'
    r'(?P<content>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)
DESCRIPTION_ITEM_RE = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|\Z)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 7: \noindent {\bf Assumption N.} {\it body} or \noindent \textbf{Assumption N.} body
# ---------------------------------------------------------------------------
NOINDENT_BF_ASSUMPTION_RE = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>Assumptions?\s*[^.}]*)'
    r'[}.]\}?'
    r'[^{\\]*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>.*?)'
    r'(?=\\noindent|\n\s*\n\s*\n|\\begin\{|\\section|\\subsection|\\subsubsection|\Z)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 8: Standalone \textbf{Remark[]:} with multi-paragraph body
# (terminated by next structural marker)
# ---------------------------------------------------------------------------
TEXTBF_REMARK_MULTI_RE = re.compile(
    r'\\textbf\{(Remark|Note|Observation)[s]?[.:}]?\}[\s:]*'
    r'(?P<body>(?:(?!\\begin\{(?:theorem|lemma|proposition|corollary|definition|proof)\*?\}|'
    r'\\section|\\subsection|\\subsubsection|\\paragraph|\\chapter).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 9: Inline \textbf{Example[.:]} (not environment)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper006
# TEXTBF_EXAMPLE_RE = re.compile(
#     r'\\textbf\{Example[s]?[.:}]?\}[\s:]*'
#     r'(?P<body>(?:(?!\\begin\{|\\section|\\subsection|\\subsubsection|\\paragraph|\\chapter).)+)',
#     re.DOTALL
# )

# ---------------------------------------------------------------------------
# Pattern 10: Inline \textbf{Assumption[.:]} (not environment)
# ---------------------------------------------------------------------------
TEXTBF_ASSUMPTION_RE = re.compile(
    r'\\textbf\{Assumptions?[.:}]?\}[\s:]*'
    r'(?P<body>(?:(?!\\begin\{|\\section|\\subsection|\\subsubsection|\\paragraph|\\chapter).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 11: \noindent{\sc Remark[s]?.} + \begin{enumerate/itemize} -> each \item
# ---------------------------------------------------------------------------
SC_REMARK_ENUMERATE_OUTER_RE = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}\s*'
    r'(?P<list_env>\\begin\{(?:enumerate|itemize)\}.*?\\end\{(?:enumerate|itemize)\})',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _spans_overlap(spans: List[tuple], start: int, end: int) -> bool:
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

    def _add(raw: str, name, rule_name: str, structure_type: str, start: int, end: int):
        raw = raw.strip()
        if not raw:
            return
        if _spans_overlap(used_spans, start, end):
            return
        if _inside_excluded_env(text, start, end):
            return
        used_spans.append((start, end))
        results.append(_make_result(raw, name, 'distilled', rule_name, structure_type))

    # --- Rule: TEXTBF_REMARK_RE ---
    for m in TEXTBF_REMARK_RE.finditer(text):
        kw = m.group(1)
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, None, 'TEXTBF_REMARK_RE', _determine_subtype(kw), m.start(), m.end())

    # --- Rule: BF_GROUP_REMARK_RE ---
    for m in BF_GROUP_REMARK_RE.finditer(text):
        kw = m.group(1)
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, None, 'BF_GROUP_REMARK_RE', _determine_subtype(kw), m.start(), m.end())

    # --- Rule: SC_REMARK_FREE_RE ---
    for m in SC_REMARK_FREE_RE.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, None, 'SC_REMARK_FREE_RE', 'remark', m.start(), m.end())

    # --- Rule: SC_REMARK_LIST_OUTER_RE (each \item as separate remark) ---
#     for outer in SC_REMARK_LIST_OUTER_RE.finditer(text):
#         list_body = outer.group('list_env')
#         list_start = outer.start()
#         for item_m in LIST_ITEM_RE.finditer(list_body):
#             body = item_m.group('body').strip()
#             if not body:
#                 continue
#             # Use outer span for dedup
#             _add(body, None, 'SC_REMARK_LIST_OUTER_RE', 'remark', list_start, outer.end())

    # --- Rule: SC_REMARK_ENUMERATE_OUTER_RE (each \item) ---
    for outer in SC_REMARK_ENUMERATE_OUTER_RE.finditer(text):
        list_body = outer.group('list_env')
        list_start = outer.start()
        for item_m in LIST_ITEM_RE.finditer(list_body):
            body = item_m.group('body').strip()
            if not body:
                continue
            _add(body, None, 'SC_REMARK_ENUMERATE_OUTER_RE', 'remark', list_start, outer.end())

    # --- Rule: EMPH_KEYWORD_RE ---
    for m in EMPH_KEYWORD_RE.finditer(text):
        kw = m.group('kw')
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, None, 'EMPH_KEYWORD_RE', _determine_subtype(kw), m.start(), m.end())

    # --- Rule: DESCRIPTION_ENV_RE with DESCRIPTION_ITEM_RE ---
    _desc_label_kind = [
        (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
        (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
        (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
        (re.compile(r'\bDefinitions?\b', re.IGNORECASE), 'definition'),
        (re.compile(r'\bTheorems?\b', re.IGNORECASE), 'theorem'),
        (re.compile(r'\bLemmas?\b', re.IGNORECASE), 'lemma'),
    ]
    for desc_m in DESCRIPTION_ENV_RE.finditer(text):
        content = desc_m.group('content')
        for item_m in DESCRIPTION_ITEM_RE.finditer(content):
            label_text = item_m.group('label').strip()
            body = item_m.group('body').strip()
            if not body:
                continue
            kind = 'theorem'
            for pat, k in _desc_label_kind:
                if pat.search(label_text):
                    kind = k
                    break
            if kind not in ('assumption', 'remark', 'example'):
                continue
            _add(body, label_text if label_text else None,
                 'DESCRIPTION_ENV_RE', kind, desc_m.start(), desc_m.end())

    # --- Rule: NOINDENT_BF_ASSUMPTION_RE ---
    for m in NOINDENT_BF_ASSUMPTION_RE.finditer(text):
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        # Strip trailing closing brace that may belong to \it{...}
        body = re.sub(r'\}\s*$', '', body).strip()
        if not body:
            continue
        _add(body, label_text if label_text else None,
             'NOINDENT_BF_ASSUMPTION_RE', 'assumption', m.start(), m.end())

    # --- Rule: TEXTBF_REMARK_MULTI_RE (multi-paragraph, higher priority terminator) ---
    # Only run if we haven't already captured the same span via TEXTBF_REMARK_RE
    for m in TEXTBF_REMARK_MULTI_RE.finditer(text):
        kw = m.group(1)
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, None, 'TEXTBF_REMARK_MULTI_RE', _determine_subtype(kw), m.start(), m.end())

    # --- Rule: TEXTBF_EXAMPLE_RE ---
#     for m in TEXTBF_EXAMPLE_RE.finditer(text):
#         body = m.group('body').strip()
#         if not body:
#             continue
#         _add(body, None, 'TEXTBF_EXAMPLE_RE', 'example', m.start(), m.end())

    # --- Rule: TEXTBF_ASSUMPTION_RE ---
    for m in TEXTBF_ASSUMPTION_RE.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, None, 'TEXTBF_ASSUMPTION_RE', 'assumption', m.start(), m.end())

    return results
