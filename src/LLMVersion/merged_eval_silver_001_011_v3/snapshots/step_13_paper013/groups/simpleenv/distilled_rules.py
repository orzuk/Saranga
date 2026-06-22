import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Minimal LaTeX -> plain text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common LaTeX commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathit|mathbf|mathbb|mathcal)\{([^}]*)\}', r'\1', text)
    # Remove display math delimiters
    text = re.sub(r'\$\$.*?\$\$', '[math]', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', '[math]', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$[^$]*\$', '[math]', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Normalise whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments whose interior we want to EXCLUDE from prose-level extraction
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|theorem|lemma|proposition|corollary|definition|algorithm|figure|table|thm|lem|prop|cor|defn)\*?\}',
    re.IGNORECASE,
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is enclosed in an excluded env."""
    prefix = text[:start]
    for m in _EXCLUDED_ENV_RE.finditer(prefix):
        env = m.group(1)
        close_pat = re.compile(
            r'\\end\{' + re.escape(env) + r'\*?\}',
            re.IGNORECASE,
        )
        close_m = close_pat.search(text, m.end())
        if close_m and close_m.start() >= end:
            return True
    return False


# ---------------------------------------------------------------------------
# Determine subtype from env name or leading keyword
# ---------------------------------------------------------------------------

def _determine_subtype(env_hint: str, body: str) -> str:
    """Return one of 'remark', 'example', 'assumption', defaulting to 'theorem'."""
    h = env_hint.lower().rstrip('*')
    if h in ('remark', 'rem', 'note', 'observation', 'sc_remark',
             'textbf_remark', 'inline_remark', 'bold_remark',
             'sc_remarks_list_item', 'prose_note'):
        return 'remark'
    if h in ('example', 'exam', 'ex', 'exmp', 'exmpl', 'illustration',
             'paragraph_example', 'prose_example', 'inline_example'):
        return 'example'
    if h in ('assumption', 'assumptions', 'noindent_bf', 'description_item',
             'prose_assumption'):
        return 'assumption'
    # Fallback: scan the first ~120 chars of body for a leading keyword
    snippet = body[:120].lower()
    if re.search(r'\b(remark|note|observation)\b', snippet):
        return 'remark'
    if re.search(r'\bexample\b', snippet):
        return 'example'
    if re.search(r'\bassumption\b', snippet):
        return 'assumption'
    return 'theorem'


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# 1. \textbf{Remark...} inline (not in \begin/\end)
TEXTBF_REMARK_PATTERN = re.compile(
    r'\\textbf\{Remark[^}]*\}\s*:?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\section\b|\\subsection\b|\\subsubsection\b|\\paragraph\b).)+)',
    re.DOTALL,
)

# 2. \textbf{Example...} inline
# PRUNED — FP on paper006
# TEXTBF_EXAMPLE_PATTERN = re.compile(
#     r'\\textbf\{Example[^}]*\}\s*:?\s*'
#     r'(?P<body>(?:(?!\\begin\{|\\section\b|\\subsection\b|\\subsubsection\b|\\paragraph\b).)+)',
#     re.DOTALL,
# )

# 3. \textbf{Assumption...} inline
TEXTBF_ASSUMPTION_PATTERN = re.compile(
    r'\\textbf\{Assumption[^}]*\}\s*:?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\section\b|\\subsection\b|\\subsubsection\b|\\paragraph\b).)+)',
    re.DOTALL,
)

# 4. {\bf Remark.} ... or {\bf Remark} ...  (old LaTeX style)
BFGROUP_REMARK_PATTERN = re.compile(
    r'\{\\bf\s+Remark[^}]*\}\.?\s*'
    r'(?P<body>(?:(?!\\(?:section|subsection|subsubsection|paragraph|chapter)\b|\\begin\{|\\end\{document\}).)+)',
    re.DOTALL,
)

# 5. {\bf Example...}
BFGROUP_EXAMPLE_PATTERN = re.compile(
    r'\{\\bf\s+Example[^}]*\}\.?\s*'
    r'(?P<body>(?:(?!\\(?:section|subsection|subsubsection|paragraph|chapter)\b|\\begin\{|\\end\{document\}).)+)',
    re.DOTALL,
)

# 6. {\bf Assumption N.} {\it body} or plain body
BFGROUP_ASSUMPTION_PATTERN = re.compile(
    r'\{\\bf\s+Assumption[^}]*\}\.?\s*'
    r'(?:\{\\it\s+)?'
    r'(?P<body>(?:(?!\\noindent\b|\\(?:section|subsection|subsubsection|paragraph|chapter)\b|\\begin\{|\\end\{document\}).)+)',
    re.DOTALL,
)

# 7. \noindent{\sc Remark[s]?.} ... up to next major boundary
SC_REMARK_SINGLE_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}\s*'
    r'(?P<body>(?:(?!\\begin\{list\}|\\(?:section|subsection|subsubsection|chapter)\b|\\noindent\s*\{\\sc|\\end\{document\}).)+)',
    re.DOTALL | re.IGNORECASE,
)

# 8. \noindent{\sc Remarks?.} followed by \begin{list}...\end{list}
#    → each \item is a separate remark
SC_REMARKS_LIST_OUTER_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}\s*'
    r'(?P<listenv>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL | re.IGNORECASE,
)
LIST_ITEM_SPLIT_PATTERN = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item\b|\\end\{list\})',
    re.DOTALL,
)

# 9. \noindent{\sc Remark.} (variant with period outside braces)
SC_REMARK_OUTER_DOT_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\}\.\s*'
    r'(?P<body>(?:(?!\\begin\{list\}|\\(?:section|subsection|subsubsection|chapter)\b|\\noindent\s*\{\\sc|\\end\{document\}).)+)',
    re.DOTALL | re.IGNORECASE,
)

# 10. \begin{description} ... \item[Assumption ...] body \end{description}
DESCRIPTION_ENV_PATTERN = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE,
)
DESCRIPTION_ITEM_PATTERN = re.compile(
    r'\\item\[(?P<label>[^\]]+)\]\s*(?P<body>.*?)(?=\\item\[|\\end\{description\}|\Z)',
    re.DOTALL,
)

# 11. \noindent {\bf Assumption N.} {\it body}
NOINDENT_BF_ASSUMPTION_PATTERN = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>Assumption[^.}]*)'
    r'(?:\}|\.)\s*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>(?:(?!\\noindent\b|\\(?:section|subsection|subsubsection|chapter)\b|\\begin\{).)+)',
    re.DOTALL,
)

# 12. \emph{Remark.} or \textit{Remark.} inline
EMPH_REMARK_PATTERN = re.compile(
    r'\\(?:emph|textit)\{Remark\.?\}\s*'
    r'(?P<body>(?:(?!\\begin\{|\\section\b|\\subsection\b|\\paragraph\b|\n\s*\n\s*\n).)+)',
    re.DOTALL,
)

# 13. \emph{Example.} or \textit{Example.} inline
EMPH_EXAMPLE_PATTERN = re.compile(
    r'\\(?:emph|textit)\{Example\.?\}\s*'
    r'(?P<body>(?:(?!\\begin\{|\\section\b|\\subsection\b|\\paragraph\b|\n\s*\n\s*\n).)+)',
    re.DOTALL,
)

# 14. \emph{Assumption.} or \textit{Assumption.} inline
EMPH_ASSUMPTION_PATTERN = re.compile(
    r'\\(?:emph|textit)\{Assumption\.?\}\s*'
    r'(?P<body>(?:(?!\\begin\{|\\section\b|\\subsection\b|\\paragraph\b|\n\s*\n\s*\n).)+)',
    re.DOTALL,
)

# 15. \paragraph{Example ...} ... up to next \paragraph/\subsection/\section
PARAGRAPH_EXAMPLE_PATTERN = re.compile(
    r'\\paragraph\{(Example[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\*?\{|\\subsection\*?\{|\\section\*?\{|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# 16. \paragraph{Remark ...} ... up to next \paragraph/\subsection/\section
PARAGRAPH_REMARK_PATTERN = re.compile(
    r'\\paragraph\{(Remark[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\*?\{|\\subsection\*?\{|\\section\*?\{|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# 17. \paragraph{Assumption ...}
PARAGRAPH_ASSUMPTION_PATTERN = re.compile(
    r'\\paragraph\{(Assumption[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\*?\{|\\subsection\*?\{|\\section\*?\{|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# 18. Bare keyword at start of line: "Remark." or "Remark:" followed by body
BARE_REMARK_LINE_PATTERN = re.compile(
    r'^(?P<kw>Remark|Note|Observation)\s*[.:]\s*(?P<body>(?:(?!\n\s*\n).)+)',
    re.DOTALL | re.MULTILINE,
)

# 19. Bare keyword at start of line: "Example." or "Example N."
BARE_EXAMPLE_LINE_PATTERN = re.compile(
    r'^(?P<kw>Example)\s*(?:\d+\s*)?[.:]\s*(?P<body>(?:(?!\n\s*\n).)+)',
    re.DOTALL | re.MULTILINE,
)

# 20. Bare keyword: "Assumption N." or "Assumption:"
BARE_ASSUMPTION_LINE_PATTERN = re.compile(
    r'^(?P<kw>Assumption)\s*(?:\d+\s*)?[.:]\s*(?P<body>(?:(?!\n\s*\n).)+)',
    re.DOTALL | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[Dict]:
    results: List[Dict] = []

    def _add(raw: str, env_hint: str, rule: str, name=None):
        raw = raw.strip()
        if not raw:
            return
        clean = _clean_latex(raw)
        stype = _determine_subtype(env_hint, raw)
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule,
            'structure_type': stype,
        })

    # --- 1. \textbf{Remark...} inline ---
    for m in TEXTBF_REMARK_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'remark', 'TEXTBF_REMARK_PATTERN')

    # --- 2. \textbf{Example...} inline ---
#     for m in TEXTBF_EXAMPLE_PATTERN.finditer(text):
#         if not _inside_excluded_env(text, m.start(), m.end()):
#             _add(m.group('body'), 'example', 'TEXTBF_EXAMPLE_PATTERN')

    # --- 3. \textbf{Assumption...} inline ---
    for m in TEXTBF_ASSUMPTION_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'assumption', 'TEXTBF_ASSUMPTION_PATTERN')

    # --- 4. {\bf Remark...} ---
    for m in BFGROUP_REMARK_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'remark', 'BFGROUP_REMARK_PATTERN')

    # --- 5. {\bf Example...} ---
    for m in BFGROUP_EXAMPLE_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'example', 'BFGROUP_EXAMPLE_PATTERN')

    # --- 6. {\bf Assumption...} ---
    for m in BFGROUP_ASSUMPTION_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            body = m.group('body').strip()
            body = re.sub(r'\}\s*$', '', body).strip()
            _add(body, 'assumption', 'BFGROUP_ASSUMPTION_PATTERN')

    # --- 7. \noindent{\sc Remark[s]?.} single paragraph ---
    for m in SC_REMARK_SINGLE_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'remark', 'SC_REMARK_SINGLE_PATTERN')

    # --- 8. \noindent{\sc Remarks?.} + \begin{list} items ---
    for outer_m in SC_REMARKS_LIST_OUTER_PATTERN.finditer(text):
        list_body = outer_m.group('listenv')
        for item_m in LIST_ITEM_SPLIT_PATTERN.finditer(list_body):
            body = item_m.group('body').strip()
            if body:
                _add(body, 'remark', 'SC_REMARKS_LIST_OUTER_PATTERN')

    # --- 9. \noindent{\sc Remark}.  (dot outside brace) ---
    for m in SC_REMARK_OUTER_DOT_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'remark', 'SC_REMARK_OUTER_DOT_PATTERN')

    # --- 10. \begin{description} \item[Assumption/Remark/Example ...] ---
    for desc_m in DESCRIPTION_ENV_PATTERN.finditer(text):
        desc_body = desc_m.group('body')
        for item_m in DESCRIPTION_ITEM_PATTERN.finditer(desc_body):
            label_text = item_m.group('label').strip()
            item_body = item_m.group('body').strip()
            if not item_body:
                continue
            # Determine kind from label
            lc = label_text.lower()
            if re.search(r'\bassumption\b', lc):
                hint = 'assumption'
            elif re.search(r'\bremark\b|\bnote\b', lc):
                hint = 'remark'
            elif re.search(r'\bexample\b', lc):
                hint = 'example'
            else:
                continue  # skip non-target labels
            _add(item_body, hint, 'DESCRIPTION_ENV_PATTERN', name=label_text)

    # --- 11. \noindent {\bf Assumption N.} {\it body} ---
    for m in NOINDENT_BF_ASSUMPTION_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            body = m.group('body').strip()
            body = re.sub(r'\}\s*$', '', body).strip()
            name = m.group('label').strip()
            _add(body, 'assumption', 'NOINDENT_BF_ASSUMPTION_PATTERN', name=name)

    # --- 12. \emph{Remark.} inline ---
    for m in EMPH_REMARK_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'remark', 'EMPH_REMARK_PATTERN')

    # --- 13. \emph{Example.} inline ---
    for m in EMPH_EXAMPLE_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'example', 'EMPH_EXAMPLE_PATTERN')

    # --- 14. \emph{Assumption.} inline ---
    for m in EMPH_ASSUMPTION_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'assumption', 'EMPH_ASSUMPTION_PATTERN')

    # --- 15. \paragraph{Example ...} ---
    for m in PARAGRAPH_EXAMPLE_PATTERN.finditer(text):
        title = m.group(1).strip()
        _add(m.group('body'), 'example', 'PARAGRAPH_EXAMPLE_PATTERN', name=title)

    # --- 16. \paragraph{Remark ...} ---
    for m in PARAGRAPH_REMARK_PATTERN.finditer(text):
        title = m.group(1).strip()
        _add(m.group('body'), 'remark', 'PARAGRAPH_REMARK_PATTERN', name=title)

    # --- 17. \paragraph{Assumption ...} ---
    for m in PARAGRAPH_ASSUMPTION_PATTERN.finditer(text):
        title = m.group(1).strip()
        _add(m.group('body'), 'assumption', 'PARAGRAPH_ASSUMPTION_PATTERN', name=title)

    # --- 18. Bare "Remark:" / "Note:" at start of line ---
    for m in BARE_REMARK_LINE_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'remark', 'BARE_REMARK_LINE_PATTERN')

    # --- 19. Bare "Example N:" at start of line ---
    for m in BARE_EXAMPLE_LINE_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'example', 'BARE_EXAMPLE_LINE_PATTERN')

    # --- 20. Bare "Assumption N:" at start of line ---
    for m in BARE_ASSUMPTION_LINE_PATTERN.finditer(text):
        if not _inside_excluded_env(text, m.start(), m.end()):
            _add(m.group('body'), 'assumption', 'BARE_ASSUMPTION_LINE_PATTERN')

    # --- Deduplication: remove entries whose raw_latex is a substring of another ---
    # and strict overlaps (keep longest per overlapping group based on raw_latex)
    if not results:
        return results

    # Simple dedup: remove exact duplicates first
    seen_raw: Dict[str, bool] = {}
    deduped = []
    for r in results:
        key = r['raw_latex']
        if key not in seen_raw:
            seen_raw[key] = True
            deduped.append(r)

    # Remove items whose raw_latex is a near-duplicate (one contains the other)
    # Keep the longer one
    final = []
    for i, r in enumerate(deduped):
        dominated = False
        for j, s in enumerate(deduped):
            if i == j:
                continue
            # If r's raw_latex is a substring of s's raw_latex, drop r
            if r['raw_latex'] in s['raw_latex'] and len(r['raw_latex']) < len(s['raw_latex']):
                dominated = True
                break
        if not dominated:
            final.append(r)

    return final
