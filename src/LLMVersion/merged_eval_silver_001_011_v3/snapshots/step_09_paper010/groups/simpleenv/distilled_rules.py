import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup to produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...} etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|eqnarray|gather|multline)[*]?\}.*?\\end\{(?:equation|align|eqnarray|gather|multline)[*]?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math (simple)
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*?\$', ' ', text, flags=re.DOTALL)
    # Remove common formatting commands
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|mathrm|mathbf|mathit|text|bf|it|sc|rm)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|it|sc|rm|tt)\s+([^}]*)\}', r'\1', text)
    # Remove \noindent, \medskip etc.
    text = re.sub(r'\\(?:noindent|medskip|bigskip|smallskip|quad|qquad|hspace\*?\{[^}]*\}|vspace\*?\{[^}]*\})', ' ', text)
    # Remove remaining commands with one argument
    text = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', ' ', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments that inner content should be skipped (we don't want to
# extract remarks/examples/assumptions that are already inside these)
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|figure|table|tikzpicture|lstlisting|verbatim)\}.*?\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _keyword_to_structure_type(keyword: str) -> str:
    """Map a matched keyword to a canonical structure_type."""
    kw = keyword.strip().lower().rstrip('*').rstrip('.')
    if kw in ('remark', 'note', 'observation', 'remarks', 'notes'):
        return 'remark'
    if kw in ('example', 'examples', 'illustration'):
        return 'example'
    if kw in ('assumption', 'assumptions'):
        return 'assumption'
    return 'remark'


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: \begin{remark/example/assumption}[opt] ... \end{...}
# (catches variants not in the base env_kind_map, e.g. remarks*, examples*)
# PRUNED — FP on paper009 | also 9 TP — review before uncommenting
# P_STANDARD_ENV = re.compile(
#     r'\\begin\{(remark[s*]*|example[s*]*|assumption[s*]*|Remark[s*]*|Example[s*]*|Assumption[s*]*)\}'
#     r'(?:\[(?P<opt>[^\]]*)\])?'
#     r'(?P<body>.*?)'
#     r'\\end\{\1\}',
#     re.DOTALL | re.IGNORECASE
# )

# Pattern 2: {\bf Keyword.} prose (bold keyword with braces notation)
P_BF_KEYWORD = re.compile(
    r'\{\\bf\s+(?P<keyword>Remark[s.]?|Note[s.]?|Observation[s.]?|Example[s.]?|Assumption[s.]?)\s*[.:]?\}'
    r'[ \t]*'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:section|subsection|subsubsection|chapter|paragraph)\b|\\begin\{|\\noindent\s*\{\\(?:bf|sc)|\\noindent\s*\\(?:textbf|textsc)).)+)',
    re.DOTALL
)

# Pattern 3: \textbf{Keyword.} or \textbf{Keyword} prose
# PRUNED — FP on paper006
# P_TEXTBF_KEYWORD = re.compile(
#     r'\\textbf\{(?P<keyword>Remark[s.]?|Note[s.]?|Observation[s.]?|Example[s.]?|Assumption[s.]?)[.]?\}'
#     r'[ \t]*'
#     r'(?P<body>(?:(?!\n\s*\n|\\(?:section|subsection|subsubsection|chapter|paragraph)\b|\\begin\{).)+)',
#     re.DOTALL
# )

# Pattern 4: \emph{Keyword.} or \textit{Keyword.} prose (inline italic label)
P_EMPH_KEYWORD = re.compile(
    r'\\(?:emph|textit)\{(?P<keyword>Remark[s.]?|Note[s.]?|Observation[s.]?|Example[s.]?|Assumption[s.]?)[.]?\}'
    r'[ \t]*'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:section|subsection|subsubsection|chapter|paragraph)\b|\\begin\{).)+)',
    re.DOTALL
)

# Pattern 5: \noindent{\sc Keyword[s]?.} ... (small-caps inline label)
P_SC_KEYWORD = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<keyword>Remarks?|Notes?|Observations?|Examples?|Assumptions?)[.]?\}[ \t]*'
    r'(?P<body>(?:(?!\\noindent\s*\{\\sc|\\(?:section|subsection|subsubsection|chapter|paragraph)\b|\\begin\{).)+)',
    re.DOTALL | re.IGNORECASE
)

# Pattern 6: \noindent{\sc Keyword[s]?.} followed by a list environment
# — extract each \item separately
# PRUNED — FP on paper004
# P_SC_KEYWORD_LIST_HEADER = re.compile(
#     r'\\noindent\s*\{\\sc\s+(?P<keyword>Remarks?|Notes?|Observations?|Examples?|Assumptions?)[.]?\}'
#     r'[ \t\n]*'
#     r'(?P<list_env>\\begin\{(?:list|enumerate|itemize)\}.*?\\end\{(?:list|enumerate|itemize)\})',
#     re.DOTALL | re.IGNORECASE
# )

P_LIST_ITEM = re.compile(
    r'\\item(?:\[[^\]]*\])?\s*(?P<body>.*?)(?=\\item(?:\[[^\]]*\])?|\\end\{(?:list|enumerate|itemize)\})',
    re.DOTALL
)

# Pattern 7: \noindent {\bf Assumption N.} {\it body} (bold label, italic body)
P_NOINDENT_BF_ASSUMPTION = re.compile(
    r'\\noindent\s*'
    r'\{\\bf\s+(?P<label>Assumption[s]?\s*[^.}]*)[.]?\}'
    r'[ \t]*'
    r'(?:\{\\it\s+(?P<italic_body>.*?)\}|(?P<plain_body>(?:(?!\n\n|\\noindent|\\begin\{|\\(?:section|subsection|subsubsection|chapter|paragraph)\b).)+))',
    re.DOTALL
)

# Pattern 8: \begin{description} with \item[Assumption...] labels
P_DESCRIPTION_ENV = re.compile(
    r'\\begin\{description\}'
    r'(?P<desc_body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)

P_DESCRIPTION_ITEM = re.compile(
    r'\\item\[(?P<label>[^\]]+)\]\s*(?P<body>.*?)(?=\\item\[|$)',
    re.DOTALL
)

_DESCRIPTION_LABEL_KIND = [
    (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
]

# Pattern 9: \noindent {\bf Keyword.} {\it ...} for remark/example
P_NOINDENT_BF_GENERIC = re.compile(
    r'\\noindent\s*'
    r'\{\\bf\s+(?P<label>(?:Remark|Note|Example|Observation)[s]?\s*[^.}]*)[.]?\}'
    r'[ \t]*'
    r'(?:\{\\it\s+(?P<italic_body>.*?)\}|(?P<plain_body>(?:(?!\n\n|\\noindent|\\begin\{|\\(?:section|subsection|subsubsection|chapter|paragraph)\b).)+))',
    re.DOTALL
)

# Pattern 10: Plain paragraph starting with 'Remark.' or 'Example.' or 'Assumption.'
# at beginning of line (after blank line), no LaTeX command prefix
P_PLAIN_KEYWORD_PARA = re.compile(
    r'(?:(?<=\n\n)|(?<=\r\n\r\n))'
    r'(?P<keyword>Remark[s.]?|Note[s.]?|Example[s.]?|Assumption[s.]?)\.\s+'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:section|subsection|subsubsection|chapter|paragraph)\b|\\begin\{).)+)',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _dedup(results: List[dict]) -> List[dict]:
    """Remove results whose spans overlap, keeping the first found."""
    out = []
    used_spans = []
    for r in results:
        s, e = r.get('_start', 0), r.get('_end', 0)
        overlap = False
        for us, ue in used_spans:
            if s < ue and e > us:
                overlap = True
                break
        if not overlap:
            out.append(r)
            used_spans.append((s, e))
    return out


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule P_STANDARD_ENV ---
#     for m in P_STANDARD_ENV.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         env_name_raw = m.group(1)
#         opt = m.group('opt')
#         body = m.group('body')
#         clean = _clean_latex(body)
#         if not clean.strip():
#             continue
#         structure_type = _keyword_to_structure_type(env_name_raw)
#         results.append({
#             'raw_latex': body.strip(),
#             'clean_text': clean,
#             'name': opt.strip() if opt else None,
#             'env_name': 'distilled',
#             'rule_name': 'P_STANDARD_ENV',
#             'structure_type': structure_type,
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # --- Rule P_BF_KEYWORD ---
    for m in P_BF_KEYWORD.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        keyword = m.group('keyword')
        body = m.group('body')
        clean = _clean_latex(body)
        if not clean.strip():
            continue
        structure_type = _keyword_to_structure_type(keyword)
        results.append({
            'raw_latex': body.strip(),
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'P_BF_KEYWORD',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule P_TEXTBF_KEYWORD ---
#     for m in P_TEXTBF_KEYWORD.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         keyword = m.group('keyword')
#         body = m.group('body')
#         clean = _clean_latex(body)
#         if not clean.strip():
#             continue
#         structure_type = _keyword_to_structure_type(keyword)
#         results.append({
#             'raw_latex': body.strip(),
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'P_TEXTBF_KEYWORD',
#             'structure_type': structure_type,
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # --- Rule P_EMPH_KEYWORD ---
    for m in P_EMPH_KEYWORD.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        keyword = m.group('keyword')
        body = m.group('body')
        clean = _clean_latex(body)
        if not clean.strip():
            continue
        structure_type = _keyword_to_structure_type(keyword)
        results.append({
            'raw_latex': body.strip(),
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'P_EMPH_KEYWORD',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule P_SC_KEYWORD (single-paragraph, not followed by list) ---
    for m in P_SC_KEYWORD.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        keyword = m.group('keyword')
        body = m.group('body')
        # Skip if body starts with a list environment (handled by P_SC_KEYWORD_LIST_HEADER)
        body_stripped = body.strip()
        if body_stripped.startswith(r'\begin{list}') or \
           body_stripped.startswith(r'\begin{enumerate}') or \
           body_stripped.startswith(r'\begin{itemize}'):
            continue
        clean = _clean_latex(body)
        if not clean.strip():
            continue
        structure_type = _keyword_to_structure_type(keyword)
        results.append({
            'raw_latex': body_stripped,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'P_SC_KEYWORD',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule P_SC_KEYWORD_LIST_HEADER: each \item becomes a separate result ---
#     for list_m in P_SC_KEYWORD_LIST_HEADER.finditer(text):
#         if _inside_excluded_env(text, list_m.start(), list_m.end()):
#             continue
#         keyword = list_m.group('keyword')
#         structure_type = _keyword_to_structure_type(keyword)
#         list_env_text = list_m.group('list_env')
#         for item_m in P_LIST_ITEM.finditer(list_env_text):
#             body = item_m.group('body').strip()
#             if not body:
#                 continue
#             clean = _clean_latex(body)
#             if not clean.strip():
#                 continue
#             results.append({
#                 'raw_latex': body,
#                 'clean_text': clean,
#                 'name': None,
#                 'env_name': 'distilled',
#                 'rule_name': 'P_SC_KEYWORD_LIST_HEADER',
#                 'structure_type': structure_type,
#                 '_start': list_m.start(),
#                 '_end': list_m.end(),
#             })

    # --- Rule P_NOINDENT_BF_ASSUMPTION ---
    for m in P_NOINDENT_BF_ASSUMPTION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        italic_body = m.group('italic_body')
        plain_body = m.group('plain_body')
        body = (italic_body or plain_body or '').strip()
        if not body:
            continue
        clean = _clean_latex(body)
        if not clean.strip():
            continue
        label_text = m.group('label').strip()
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': label_text if label_text else None,
            'env_name': 'distilled',
            'rule_name': 'P_NOINDENT_BF_ASSUMPTION',
            'structure_type': 'assumption',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule P_DESCRIPTION_ENV: items with Assumption/Remark/Example labels ---
    for desc_m in P_DESCRIPTION_ENV.finditer(text):
        if _inside_excluded_env(text, desc_m.start(), desc_m.end()):
            continue
        desc_body = desc_m.group('desc_body')
        for item_m in P_DESCRIPTION_ITEM.finditer(desc_body):
            item_label = item_m.group('label').strip()
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
            clean = _clean_latex(item_body)
            if not clean.strip():
                continue
            results.append({
                'raw_latex': item_body,
                'clean_text': clean,
                'name': item_label if item_label else None,
                'env_name': 'distilled',
                'rule_name': 'P_DESCRIPTION_ENV',
                'structure_type': kind,
                '_start': desc_m.start(),
                '_end': desc_m.end(),
            })

    # --- Rule P_NOINDENT_BF_GENERIC: remark/note/example inline bold label ---
    for m in P_NOINDENT_BF_GENERIC.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        italic_body = m.group('italic_body')
        plain_body = m.group('plain_body')
        body = (italic_body or plain_body or '').strip()
        if not body:
            continue
        clean = _clean_latex(body)
        if not clean.strip():
            continue
        label_text = m.group('label').strip()
        structure_type = _keyword_to_structure_type(label_text)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': label_text if label_text else None,
            'env_name': 'distilled',
            'rule_name': 'P_NOINDENT_BF_GENERIC',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule P_PLAIN_KEYWORD_PARA ---
    for m in P_PLAIN_KEYWORD_PARA.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        keyword = m.group('keyword')
        body = m.group('body')
        clean = _clean_latex(body)
        if not clean.strip():
            continue
        structure_type = _keyword_to_structure_type(keyword)
        results.append({
            'raw_latex': body.strip(),
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'P_PLAIN_KEYWORD_PARA',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # Sort by start position for deterministic ordering before dedup
    results.sort(key=lambda r: r['_start'])

    # Deduplicate overlapping matches
    results = _dedup(results)

    # Remove internal span keys
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
