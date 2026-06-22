import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{equation\*?\}.*?\\end\{equation\*?\}', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\\begin\{align\*?\}.*?\\end\{align\*?\}', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\\begin\{eqnarray\*?\}.*?\\end\{eqnarray\*?\}', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', ' ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$[^$]*\$', ' ', text)
    # Remove common formatting commands
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|textsc|textsf|texttt|text)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|it|rm|sc|sf|tt|em)\s+([^}]*)\}', r'\1', text)
    # Remove \ref, \cite, \eqref etc.
    text = re.sub(r'\\(?:ref|eqref|cite[a-zA-Z]*|label)\{[^}]*\}', '', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose content should be excluded from our extraction
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|figure|table|lstlisting|verbatim|tikzpicture)\}.*?\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Subtype detection
# ---------------------------------------------------------------------------

def _detect_subtype(env_indicator: str, body: str = '') -> str:
    """Determine the structure_type from the environment/keyword indicator."""
    s = env_indicator.strip().rstrip('*').lower()
    if re.search(r'\bremark|\\bremark|note|observation', s, re.IGNORECASE):
        return 'remark'
    if re.search(r'\bexample|illustration', s, re.IGNORECASE):
        return 'example'
    if re.search(r'\bassumption', s, re.IGNORECASE):
        return 'assumption'
    return 'theorem'


# ---------------------------------------------------------------------------
# Pattern 1: \begin{remark/example/assumption} ... \end{...}
# (Catches variants NOT already in the base env_kind_map, e.g. starred forms,
#  and ensures structure_type is set correctly.)
# ---------------------------------------------------------------------------

_SIMPLE_ENV_PATTERN = re.compile(
    r'\\begin\{(remark\*?|Remark\*?|example\*?|Example\*?|assumption\*?|Assumption\*?|'
    r'assumptions\*?|Assumptions\*?|exam\*?|ex\*?|rem\*?|note\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Pattern 2: {\bf Remark/Example/Assumption.} ... (bold keyword inline)
# ---------------------------------------------------------------------------

_BOLD_KEYWORD_PATTERN = re.compile(
    r'(?:(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<kw>Remark|Note|Observation|Example|Illustration|Assumption)s?\.?'
    r'\}?)'
    r'[\s.]*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b|\{\\bf\s+|\\textbf\{).)+)',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Pattern 3: \noindent{\sc Remark[s]?.} ... (small-caps keyword inline)
# Also handles single remarks (not just lists).
# ---------------------------------------------------------------------------

_SC_REMARK_SINGLE_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<kw>Remark|Note|Observation|Example|Assumption)s?\.?\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\begin\{list\}).)+?)(?=\n\s*\n|\Z|\\(?:section|subsection|subsubsection|chapter|appendix)|\\noindent\s*\{\\sc)',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Pattern 4: \noindent{\sc Remark[s]?.} followed by \begin{list}...\end{list}
# Each \item is an individual remark.
# ---------------------------------------------------------------------------

# PRUNED — FP on paper004
# _SC_KEYWORD_LIST_PATTERN = re.compile(
#     r'\\noindent\s*\{\\sc\s+(?P<kw>Remark|Note|Observation|Example|Assumption)s?\.?\}'
#     r'[.\s]*'
#     r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
#     re.DOTALL | re.IGNORECASE
# )

_LIST_ITEM_SPLIT_PATTERN = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item|\Z)',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Pattern 5: \begin{description}\item[Assumption/Remark/Example ...]...
# \end{description}
# ---------------------------------------------------------------------------

_DESCRIPTION_ENV_PATTERN = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)

_DESCRIPTION_ITEM_PATTERN = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|\Z)',
    re.DOTALL
)

_DESCRIPTION_LABEL_KIND = [
    (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
    (re.compile(r'\bNotes?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bObservations?\b', re.IGNORECASE), 'remark'),
]


# ---------------------------------------------------------------------------
# Pattern 6: \noindent {\bf Assumption N.} {\it body} or {\bf Remark N.} ...
# ---------------------------------------------------------------------------

_NOINDENT_BF_KEYWORD_PATTERN = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>(?:Assumption|Remark|Note|Example|Observation)s?[^.}]*)'
    r'[.}]\}?'
    r'\s*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>.*?)'
    r'(?=\\noindent|\n\s*\n\s*\n|\\begin\{|\\section|\\subsection|\\subsubsection|\\chapter|\\appendix|\Z)',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Pattern 7: Line-level inline keyword at start of paragraph
# e.g. "Remark." or "Example 1." or "Assumption 2:" at paragraph start
# ---------------------------------------------------------------------------

# PRUNED — FP on paper001, paper002, paper003 +1 more
# _PARAGRAPH_KEYWORD_PATTERN = re.compile(
#     r'(?:^|\n\n)\s*'
#     r'(?P<kw>Remark|Note|Observation|Example|Illustration|Assumption)s?'
#     r'(?:\s+\d+)?'
#     r'[.:\s]+'
#     r'(?P<body>(?:(?!\n\n).)+)',
#     re.DOTALL
# )


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _overlaps(span1, span2):
    """Return True if two (start, end) spans overlap."""
    return span1[0] < span2[1] and span2[0] < span1[1]


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping longer ones first."""
    results_sorted = sorted(results, key=lambda x: (x['_start'], -(x['_end'] - x['_start'])))
    kept = []
    for r in results_sorted:
        dominated = False
        for k in kept:
            if _overlaps((r['_start'], r['_end']), (k['_start'], k['_end'])):
                dominated = True
                break
        if not dominated:
            kept.append(r)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results = []

    # --- Rule: _SIMPLE_ENV_PATTERN ---
    for m in _SIMPLE_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        env_name_raw = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        if not body.strip():
            continue
        structure_type = _detect_subtype(env_name_raw)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': '_SIMPLE_ENV_PATTERN',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule: _BOLD_KEYWORD_PATTERN ---
    for m in _BOLD_KEYWORD_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('kw')
        body = m.group('body').strip()
        if not body:
            continue
        structure_type = _detect_subtype(kw)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_BOLD_KEYWORD_PATTERN',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule: _SC_REMARK_SINGLE_PATTERN ---
    for m in _SC_REMARK_SINGLE_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('kw')
        body = m.group('body').strip()
        if not body:
            continue
        structure_type = _detect_subtype(kw)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_SC_REMARK_SINGLE_PATTERN',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule: _SC_KEYWORD_LIST_PATTERN ---
#     for list_m in _SC_KEYWORD_LIST_PATTERN.finditer(text):
#         if _inside_excluded_env(text, list_m.start(), list_m.end()):
#             continue
#         kw = list_m.group('kw')
#         list_body = list_m.group('list_env')
#         structure_type = _detect_subtype(kw)
#         # Strip leading \begin{list}...first \item header
#         inner = re.sub(r'^\\begin\{list\}[^\\]*', '', list_body, count=1, flags=re.DOTALL)
#         inner = re.sub(r'\\end\{list\}\s*$', '', inner, flags=re.DOTALL)
#         for item_m in _LIST_ITEM_SPLIT_PATTERN.finditer(inner):
#             body = item_m.group('body').strip()
#             # Remove \renewcommand and \setlength preamble lines
#             body = re.sub(r'\\(?:renewcommand|setlength|setcounter)\{[^}]*\}\{[^}]*\}', '', body)
#             body = body.strip()
#             if not body:
#                 continue
#             abs_start = list_m.start()
#             abs_end = list_m.end()
#             results.append({
#                 'raw_latex': body,
#                 'clean_text': _clean_latex(body),
#                 'name': None,
#                 'env_name': 'distilled',
#                 'rule_name': '_SC_KEYWORD_LIST_PATTERN',
#                 'structure_type': structure_type,
#                 '_start': abs_start,
#                 '_end': abs_end,
#             })

    # --- Rule: _DESCRIPTION_ENV_PATTERN ---
    for desc_m in _DESCRIPTION_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, desc_m.start(), desc_m.end()):
            continue
        desc_body = desc_m.group('body')
        for item_m in _DESCRIPTION_ITEM_PATTERN.finditer(desc_body):
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
            results.append({
                'raw_latex': item_body,
                'clean_text': _clean_latex(item_body),
                'name': item_label if item_label else None,
                'env_name': 'distilled',
                'rule_name': '_DESCRIPTION_ENV_PATTERN',
                'structure_type': kind,
                '_start': desc_m.start(),
                '_end': desc_m.end(),
            })

    # --- Rule: _NOINDENT_BF_KEYWORD_PATTERN ---
    for m in _NOINDENT_BF_KEYWORD_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        # Strip trailing closing brace from \it{...} wrapper if present
        body = re.sub(r'\}\s*$', '', body).strip()
        if not body:
            continue
        structure_type = _detect_subtype(label_text)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': label_text if label_text else None,
            'env_name': 'distilled',
            'rule_name': '_NOINDENT_BF_KEYWORD_PATTERN',
            'structure_type': structure_type,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule: _PARAGRAPH_KEYWORD_PATTERN ---
#     for m in _PARAGRAPH_KEYWORD_PATTERN.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         kw = m.group('kw')
#         body = m.group('body').strip()
#         if not body:
#             continue
#         structure_type = _detect_subtype(kw)
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': '_PARAGRAPH_KEYWORD_PATTERN',
#             'structure_type': structure_type,
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # Deduplicate
    results = _deduplicate(results)

    # Remove internal span keys
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
