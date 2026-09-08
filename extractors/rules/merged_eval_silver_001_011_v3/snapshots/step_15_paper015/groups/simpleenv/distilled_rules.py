import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup to produce a plain-text approximation."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # Remove \ref, \eqref, \cite variants
    text = re.sub(r'\\(?:ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Unwrap \textbf, \textit, \emph, \text, \mathrm, \mathbf, \mathit, \mathcal, \mathbb
    for cmd in ('textbf', 'textit', 'emph', 'text', 'mathrm', 'mathbf',
                'mathit', 'mathcal', 'mathbb', 'textrm', 'textsf', 'texttt',
                'underline', 'overline'):
        text = re.sub(r'\\' + cmd + r'\{([^}]*)\}', r'\1', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?'
                  r'\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}',
                  '', text, flags=re.DOTALL)
    # Remove inline math (simplified)
    text = re.sub(r'\$\$.*?\$\$', '', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', '', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*', '', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the span [start, end) is inside an excluded environment
    (proof, theorem, lemma, proposition, corollary, definition, figure, table).
    """
    excluded = (
        'proof', 'theorem', 'thm', 'lemma', 'lem', 'proposition', 'prop',
        'corollary', 'cor', 'definition', 'defn', 'figure', 'table',
        'algorithm', 'lstlisting', 'verbatim',
    )
    pattern = re.compile(
        r'\\begin\{(' + '|'.join(map(re.escape, excluded)) + r')\*?\}',
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        env_name = m.group(1)
        env_start = m.start()
        if env_start >= end:
            break
        # find matching \end
        end_pattern = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\*?\}',
            re.IGNORECASE,
        )
        em = end_pattern.search(text, m.end())
        if em is None:
            continue
        env_end = em.end()
        if env_start <= start and end <= env_end:
            return True
    return False


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex span overlaps with an earlier result."""
    seen_spans = []
    out = []
    for r in results:
        start = r.get('_start', 0)
        end = r.get('_end', start + len(r['raw_latex']))
        overlaps = any(not (end <= s or start >= e) for s, e in seen_spans)
        if not overlaps:
            seen_spans.append((start, end))
            out.append(r)
    return out


def _make_result(raw_latex: str, clean_text: str, name, env_name: str,
                 rule_name: str, structure_type: str,
                 start: int = 0, end: int = 0) -> dict:
    return {
        'raw_latex': raw_latex,
        'clean_text': clean_text,
        'name': name,
        'env_name': env_name,
        'rule_name': rule_name,
        'structure_type': structure_type,
        '_start': start,
        '_end': end,
    }


# ---------------------------------------------------------------------------
# Subtype detection helper
# ---------------------------------------------------------------------------

def _detect_subtype(env_or_keyword: str) -> str:
    """
    Map an environment name or inline keyword to a subtype.
    Covers remark, example, assumption; defaults to 'theorem'.
    """
    normed = env_or_keyword.lower().rstrip('*').strip()
    if normed in ('remark', 'rem', 'note', 'observation', 'remarks',
                  'sc_remark', 'sc_remarks_list_item', 'textbf_remark',
                  'inline_remark', 'prose_remark'):
        return 'remark'
    if normed in ('example', 'exam', 'ex', 'exmp', 'exmpl',
                  'illustration', 'paragraph_example', 'section_example',
                  'inline_example', 'prose_example'):
        return 'example'
    if normed in ('assumption', 'assumptions', 'description_item',
                  'noindent_bf', 'prose_assumption'):
        return 'assumption'
    return 'theorem'


# ---------------------------------------------------------------------------
# Pattern 1 – \textbf{Remark[...]} inline (paper011 style)
# Catches: \textbf{Remark:} or \textbf{Remark.} not in \begin/\end
# ---------------------------------------------------------------------------

TEXTBF_REMARK_PAT = re.compile(
    r'\\textbf\{Remark[^}]*\}\s*:?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\end\{|\\section|\\subsection|\\subsubsection|\\paragraph).)+)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Pattern 2 – {\bf Keyword.} or \textbf{Keyword.} inline bold keyword
# Catches: {\bf Remark.} body... (paper002 style)
# ---------------------------------------------------------------------------

# PRUNED — FP on paper004, paper006 | also 1 TP — review before uncommenting
# BOLD_BRACE_KEYWORD_PAT = re.compile(
#     r'(?:\{\\bf\s+'
#     r'|\\textbf\{)'
#     r'(?P<keyword>Remark|Note|Observation|Example|Assumption)s?[.:]?\}?'
#     r'[.:\s]*'
#     r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b).)+)',
#     re.DOTALL,
# )


# ---------------------------------------------------------------------------
# Pattern 3 – \noindent{\sc Remark[s]?.} freestanding (paper004 style)
# ---------------------------------------------------------------------------

SC_REMARK_PAT = re.compile(
    r'\\noindent\s*'
    r'\{\\sc\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\begin\{list\}|\\noindent|\\section|\\subsection|\\subsubsection|\\appendix).)+)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pattern 4 – \noindent{\sc Remarks.} followed by \begin{list}...\end{list}
# Each \item is a separate remark (paper004 style)
# ---------------------------------------------------------------------------

SC_REMARKS_LIST_PAT = re.compile(
    r'\\noindent\s*'
    r'\{\\sc\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL | re.IGNORECASE,
)

LIST_ITEM_PAT = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item|\Z)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Pattern 5 – \begin{description} with \item[Assumption ...] labels
# (paper004 style)
# ---------------------------------------------------------------------------

DESCRIPTION_ENV_PAT = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE,
)

DESCRIPTION_ITEM_PAT = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|\Z)',
    re.DOTALL,
)

_DESC_LABEL_KIND = [
    (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
    (re.compile(r'\bNotes?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bObservations?\b', re.IGNORECASE), 'remark'),
]


# ---------------------------------------------------------------------------
# Pattern 6 – \noindent {\bf Assumption N.} {\it body} (paper004 style)
# ---------------------------------------------------------------------------

NOINDENT_BF_ASSUMPTION_PAT = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>Assumption[^.}]*)'
    r'[.}]\s*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>(?:(?!\\noindent|\\begin\{|\\end\{|\\section|\\subsection|\n\n\n).)+)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Pattern 7 – \emph{Keyword.} or \textit{Keyword.} inline labeled
# (paper005 style: \emph{Remark.} body)
# ---------------------------------------------------------------------------

EMPH_KEYWORD_PAT = re.compile(
    r'(?P<cmd>\\(?:emph|textit))'
    r'\{(?P<keyword>Remark|Note|Observation|Example|Assumption)s?[.:]?\}'
    r'[\s~]*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph)\b|\n\s*\n).)+)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Pattern 8 – \paragraph{Example ...} body (paper013 style)
# ---------------------------------------------------------------------------

PARAGRAPH_EXAMPLE_PAT = re.compile(
    r'\\paragraph\*?\{(?P<title>(?:Example|Remark|Note|Assumption)[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\*?\{|\\subsubsection|\\subsection|\\section|\Z)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pattern 9 – \section or \subsection titled with keyword (paper014 style)
# \section{Example: ...} or \subsection{Example}
# ---------------------------------------------------------------------------

SECTION_KEYWORD_PAT = re.compile(
    r'\\(?:sub)*section\*?\{(?P<title>(?:Example|Remark|Note|Assumption)[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pattern 10 – standalone line beginning with "Remark." / "Note." / etc.
# (inline keyword at start of paragraph, no bold/italic wrapper)
# ---------------------------------------------------------------------------

# PRUNED — FP on paper001, paper002, paper003 +7 more | also 1 TP — review before uncommenting
# INLINE_PLAIN_KEYWORD_PAT = re.compile(
#     r'(?:^|\n\n)'
#     r'(?P<keyword>Remark|Note|Observation)[.:\s]+'
#     r'(?P<body>(?:(?!\n\n|\\begin\{|\\section|\\subsection|\\subsubsection).)+)',
#     re.DOTALL | re.MULTILINE,
# )


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule: TEXTBF_REMARK_PAT
    # ------------------------------------------------------------------
    for m in TEXTBF_REMARK_PAT.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make_result(
            raw_latex=body,
            clean_text=_clean_latex(body),
            name=None,
            env_name='distilled',
            rule_name='TEXTBF_REMARK_PAT',
            structure_type='remark',
            start=start,
            end=end,
        ))

    # ------------------------------------------------------------------
    # Rule: BOLD_BRACE_KEYWORD_PAT
#     # ------------------------------------------------------------------
#     for m in BOLD_BRACE_KEYWORD_PAT.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         keyword = m.group('keyword')
#         body = m.group('body').strip()
#         if not body:
#             continue
#         subtype = _detect_subtype(keyword)
#         results.append(_make_result(
#             raw_latex=body,
#             clean_text=_clean_latex(body),
#             name=None,
#             env_name='distilled',
#             rule_name='BOLD_BRACE_KEYWORD_PAT',
#             structure_type=subtype,
#             start=start,
#             end=end,
#         ))

    # ------------------------------------------------------------------
    # Rule: SC_REMARK_PAT
    # ------------------------------------------------------------------
    for m in SC_REMARK_PAT.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make_result(
            raw_latex=body,
            clean_text=_clean_latex(body),
            name=None,
            env_name='distilled',
            rule_name='SC_REMARK_PAT',
            structure_type='remark',
            start=start,
            end=end,
        ))

    # ------------------------------------------------------------------
    # Rule: SC_REMARKS_LIST_PAT (each \item is a separate remark)
    # ------------------------------------------------------------------
    for list_m in SC_REMARKS_LIST_PAT.finditer(text):
        list_start = list_m.start()
        list_env = list_m.group('list_env')
        for item_m in LIST_ITEM_PAT.finditer(list_env):
            body = item_m.group('body').strip()
            if not body:
                continue
            abs_start = list_start + item_m.start()
            abs_end = list_start + item_m.end()
            if _inside_excluded_env(text, abs_start, abs_end):
                continue
            results.append(_make_result(
                raw_latex=body,
                clean_text=_clean_latex(body),
                name=None,
                env_name='distilled',
                rule_name='SC_REMARKS_LIST_PAT',
                structure_type='remark',
                start=abs_start,
                end=abs_end,
            ))

    # ------------------------------------------------------------------
    # Rule: DESCRIPTION_ENV_PAT  (with \item[Assumption/Remark/Example])
    # ------------------------------------------------------------------
    for desc_m in DESCRIPTION_ENV_PAT.finditer(text):
        desc_start = desc_m.start()
        desc_body = desc_m.group('body')
        for item_m in DESCRIPTION_ITEM_PAT.finditer(desc_body):
            item_label = item_m.group('label')
            item_body = item_m.group('body').strip()
            if not item_body:
                continue
            abs_start = desc_start + item_m.start()
            abs_end = desc_start + item_m.end()
            if _inside_excluded_env(text, abs_start, abs_end):
                continue
            kind = None
            for pat, k in _DESC_LABEL_KIND:
                if pat.search(item_label):
                    kind = k
                    break
            if kind is None:
                continue
            results.append(_make_result(
                raw_latex=item_body,
                clean_text=_clean_latex(item_body),
                name=item_label.strip() or None,
                env_name='distilled',
                rule_name='DESCRIPTION_ENV_PAT',
                structure_type=kind,
                start=abs_start,
                end=abs_end,
            ))

    # ------------------------------------------------------------------
    # Rule: NOINDENT_BF_ASSUMPTION_PAT
    # ------------------------------------------------------------------
    for m in NOINDENT_BF_ASSUMPTION_PAT.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        # Strip trailing closing brace from {\it ...} wrapper if present
        body = re.sub(r'\}\s*$', '', body).strip()
        if not body:
            continue
        results.append(_make_result(
            raw_latex=body,
            clean_text=_clean_latex(body),
            name=label_text or None,
            env_name='distilled',
            rule_name='NOINDENT_BF_ASSUMPTION_PAT',
            structure_type='assumption',
            start=start,
            end=end,
        ))

    # ------------------------------------------------------------------
    # Rule: EMPH_KEYWORD_PAT
    # ------------------------------------------------------------------
    for m in EMPH_KEYWORD_PAT.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        keyword = m.group('keyword')
        body = m.group('body').strip()
        if not body:
            continue
        subtype = _detect_subtype(keyword)
        results.append(_make_result(
            raw_latex=body,
            clean_text=_clean_latex(body),
            name=None,
            env_name='distilled',
            rule_name='EMPH_KEYWORD_PAT',
            structure_type=subtype,
            start=start,
            end=end,
        ))

    # ------------------------------------------------------------------
    # Rule: PARAGRAPH_EXAMPLE_PAT
    # ------------------------------------------------------------------
    for m in PARAGRAPH_EXAMPLE_PAT.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        subtype = _detect_subtype(title.split()[0] if title else 'example')
        results.append(_make_result(
            raw_latex=body,
            clean_text=_clean_latex(body),
            name=title or None,
            env_name='distilled',
            rule_name='PARAGRAPH_EXAMPLE_PAT',
            structure_type=subtype,
            start=start,
            end=end,
        ))

    # ------------------------------------------------------------------
    # Rule: SECTION_KEYWORD_PAT
    # ------------------------------------------------------------------
    for m in SECTION_KEYWORD_PAT.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        first_word = re.split(r'[\s:,]', title)[0]
        subtype = _detect_subtype(first_word)
        results.append(_make_result(
            raw_latex=body,
            clean_text=_clean_latex(body),
            name=title or None,
            env_name='distilled',
            rule_name='SECTION_KEYWORD_PAT',
            structure_type=subtype,
            start=start,
            end=end,
        ))

    # ------------------------------------------------------------------
    # Rule: INLINE_PLAIN_KEYWORD_PAT
#     # ------------------------------------------------------------------
#     for m in INLINE_PLAIN_KEYWORD_PAT.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         keyword = m.group('keyword')
#         body = m.group('body').strip()
#         if not body:
#             continue
#         subtype = _detect_subtype(keyword)
#         results.append(_make_result(
#             raw_latex=body,
#             clean_text=_clean_latex(body),
#             name=None,
#             env_name='distilled',
#             rule_name='INLINE_PLAIN_KEYWORD_PAT',
#             structure_type=subtype,
#             start=start,
#             end=end,
#         ))

    # ------------------------------------------------------------------
    # Deduplicate and strip internal keys
    # ------------------------------------------------------------------
    results.sort(key=lambda r: r['_start'])
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
