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
    # Remove common formatting commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|textsf|texttt|mathrm|mathit|mathbf|mathsf|mathbb|mathcal|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove \ref, \cite, \eqref etc.
    text = re.sub(r'\\(?:ref|eqref|cite[a-zA-Z]*|citeA|citeNP|label)\{[^}]*\}', '', text)
    # Remove display math environments (replace with placeholder)
    text = re.sub(r'\$\$.*?\$\$', '[MATH]', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', '[MATH]', text, flags=re.DOTALL)
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}', '[MATH]', text, flags=re.DOTALL)
    # Inline math
    text = re.sub(r'\$[^$]*\$', '[MATH]', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})*', ' ', text)
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose interior we do NOT want to mine for inline markers
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|figure|table|algorithm|lstlisting|verbatim|tikzpicture)\}',
    re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    prefix = text[:start]
    for m in _EXCLUDED_ENV_RE.finditer(text):
        env_name = m.group(1)
        env_start = m.start()
        if env_start >= start:
            break
        close_re = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\}',
            re.IGNORECASE
        )
        close_m = close_re.search(text, env_start)
        if close_m and close_m.end() > start:
            return True
    return False


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex span overlaps with a higher-priority result."""
    # Sort by start position; keep first (longest) non-overlapping spans
    # We store (start, end, dict)
    tagged = []
    for r in results:
        s = r.get('_start', 0)
        e = r.get('_end', s + len(r['raw_latex']))
        tagged.append((s, e, r))
    tagged.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out = []
    covered_ranges = []
    for s, e, r in tagged:
        overlap = any(s < ce and e > cs for cs, ce in covered_ranges)
        if not overlap:
            covered_ranges.append((s, e))
            d = dict(r)
            d.pop('_start', None)
            d.pop('_end', None)
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Subtype detection
# ---------------------------------------------------------------------------

_SUBTYPE_KEYWORD_MAP = [
    (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bNotes?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bObservations?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
    (re.compile(r'\bIllustrations?\b', re.IGNORECASE), 'example'),
]

def _detect_subtype(keyword_text: str) -> str:
    """Determine structure_type from a keyword string."""
    for pat, kind in _SUBTYPE_KEYWORD_MAP:
        if pat.search(keyword_text):
            return kind
    return 'theorem'


# ---------------------------------------------------------------------------
# Pattern 1: \begin{remark|example|assumption}...\end{...}  (starred variants
#             and capitalised variants not already in BASE_ENV_KIND_MAP)
# ---------------------------------------------------------------------------

_EXTRA_ENV_NAMES = [
    'remark*', 'Remark*',
    'example*', 'Example*',
    'assumption*', 'Assumption*',
    'assumptions*', 'Assumptions*',
    'remarkenv', 'exampleenv', 'assumptionenv',
    'rmk', 'rmrk',
    'exa', 'exm',
    'hyp', 'hypothesis', 'Hypothesis',
]

_EXTRA_ENV_KIND_MAP = {
    'remark*': 'remark', 'Remark*': 'remark',
    'example*': 'example', 'Example*': 'example',
    'assumption*': 'assumption', 'Assumption*': 'assumption',
    'assumptions*': 'assumption', 'Assumptions*': 'assumption',
    'remarkenv': 'remark', 'exampleenv': 'example', 'assumptionenv': 'assumption',
    'rmk': 'remark', 'rmrk': 'remark',
    'exa': 'example', 'exm': 'example',
    'hyp': 'assumption', 'hypothesis': 'assumption', 'Hypothesis': 'assumption',
}

_EXTRA_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>' + '|'.join(map(re.escape, _EXTRA_ENV_NAMES)) + r')\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Pattern 2: {\bf Remark[s]?.} or \textbf{Remark[s]?.} inline paragraph leader
# ---------------------------------------------------------------------------

# PRUNED — FP on paper004, paper006 | also 1 TP — review before uncommenting
# _BF_KEYWORD_PATTERN = re.compile(
#     r'(?:'
#     r'\{\\bf\s+(?P<kw1>Remarks?|Notes?|Observations?|Examples?|Assumptions?)'
#     r'[.\s}]|'
#     r'\\textbf\{(?P<kw2>Remarks?|Notes?|Observations?|Examples?|Assumptions?)'
#     r'\.?\}'
#     r')'
#     r'[\s.~]*'
#     r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b|\n\s*\n\s*\n).)+)',
#     re.DOTALL
# )


# ---------------------------------------------------------------------------
# Pattern 3: \noindent{\sc Remark[s]?.} free paragraph (not followed by list)
# ---------------------------------------------------------------------------

_SC_REMARK_SOLO_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<kw>Remarks?|Notes?|Observations?|Examples?|Assumptions?)\.?\}'
    r'[\s.~]*'
    r'(?P<body>(?:(?!\\begin\{list\}|\\noindent|\\(?:sub)*section|\\chapter|\\appendix|\\end\{document\}).)+)',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Pattern 4: \noindent{\sc Remarks?.} followed by \begin{list}...\end{list}
#             — extract each \item as a separate remark
# ---------------------------------------------------------------------------

_SC_REMARKS_LIST_OUTER = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<kw>Remarks?|Notes?|Observations?|Examples?|Assumptions?)\.?\}'
    r'\s*(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL | re.IGNORECASE
)

_LIST_ITEM_SPLIT = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item|\\end\{list\})',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Pattern 5: \begin{description}\item[Assumption/Remark/Example ...] body
#             \end{description}
# ---------------------------------------------------------------------------

_DESCRIPTION_OUTER = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)

_DESCRIPTION_ITEM_RE = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|\Z)',
    re.DOTALL
)

_DESC_LABEL_SUBTYPE = [
    (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
]


# ---------------------------------------------------------------------------
# Pattern 6: \noindent {\bf Assumption N.} {\it body...}
# ---------------------------------------------------------------------------

_NOINDENT_BF_ASSUMPTION = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>(?:Assumption|Remark|Example)[^.}]*)'
    r'(?:\.|\})\s*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>.*?)'
    r'(?=\\noindent|\n{2,}|\\begin\{|\\(?:sub)*section|\\chapter|$)',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Pattern 7: \emph{Keyword.} or \textit{Keyword.} inline labeled
# ---------------------------------------------------------------------------

_INLINE_CMD_KEYWORDS = (
    'Remark', 'remark', 'Note', 'note', 'Observation', 'observation',
    'Example', 'example', 'Assumption', 'assumption',
)

_INLINE_LABEL_PATTERN = re.compile(
    r'\\(?:emph|textit|textbf)\{'
    r'(?P<keyword>' + '|'.join(map(re.escape, _INLINE_CMD_KEYWORDS)) + r')'
    r'\.?\}'
    r'[\s~]*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b|\n\s*\n\s*\n).)+)',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Pattern 8: Plain paragraph leader "Remark." / "Example." / "Assumption."
#             at start of line (not inside any env)
# ---------------------------------------------------------------------------

_PLAIN_KEYWORD_LEADER = re.compile(
    r'(?:^|\n)[ \t]*'
    r'(?P<keyword>Remark|Remarks|Note|Observation|Example|Assumption)'
    r'\.'
    r'[ \t]+'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:begin|end|section|subsection|subsubsection|chapter|paragraph)\b).)+)',
    re.DOTALL | re.MULTILINE
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule 1: extra \begin/\end environment names ---
    for m in _EXTRA_ENV_PATTERN.finditer(text):
        env = m.group('env').rstrip('*')
        kind = _EXTRA_ENV_KIND_MAP.get(m.group('env'), _EXTRA_ENV_KIND_MAP.get(env, 'remark'))
        opt = m.group('opt')
        body = m.group('body')
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': '_EXTRA_ENV_PATTERN',
            'structure_type': kind,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule 2: {\bf Keyword.} or \textbf{Keyword.} paragraph leaders ---
#     for m in _BF_KEYWORD_PATTERN.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         kw = m.group('kw1') or m.group('kw2') or ''
#         kind = _detect_subtype(kw)
#         body = m.group('body').strip()
#         if not body:
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': '_BF_KEYWORD_PATTERN',
#             'structure_type': kind,
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # --- Rule 3: \noindent{\sc Keyword.} solo paragraph ---
    for m in _SC_REMARK_SOLO_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Only use this rule if NOT followed by a list env (Pattern 4 handles that)
        body_text = m.group('body').strip()
        if not body_text:
            continue
        kw = m.group('kw')
        kind = _detect_subtype(kw)
        results.append({
            'raw_latex': body_text,
            'clean_text': _clean_latex(body_text),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_SC_REMARK_SOLO_PATTERN',
            'structure_type': kind,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule 4: \noindent{\sc Remarks?.} + \begin{list}...\end{list} ---
    for outer_m in _SC_REMARKS_LIST_OUTER.finditer(text):
        if _inside_excluded_env(text, outer_m.start(), outer_m.end()):
            continue
        kw = outer_m.group('kw')
        kind = _detect_subtype(kw)
        list_body = outer_m.group('list_env')
        list_start = text.find(list_body, outer_m.start())
        for item_m in _LIST_ITEM_SPLIT.finditer(list_body):
            body = item_m.group('body').strip()
            if not body:
                continue
            item_abs_start = list_start + item_m.start()
            item_abs_end = list_start + item_m.end()
            results.append({
                'raw_latex': body,
                'clean_text': _clean_latex(body),
                'name': None,
                'env_name': 'distilled',
                'rule_name': '_SC_REMARKS_LIST_OUTER',
                'structure_type': kind,
                '_start': item_abs_start,
                '_end': item_abs_end,
            })

    # --- Rule 5: \begin{description}\item[Assumption/Remark/Example...] ---
    for desc_m in _DESCRIPTION_OUTER.finditer(text):
        if _inside_excluded_env(text, desc_m.start(), desc_m.end()):
            continue
        desc_body = desc_m.group('body')
        desc_start = text.find(desc_body, desc_m.start())
        for item_m in _DESCRIPTION_ITEM_RE.finditer(desc_body):
            item_label = item_m.group('label')
            item_body = item_m.group('body').strip()
            if not item_body:
                continue
            kind = None
            for pat, k in _DESC_LABEL_SUBTYPE:
                if pat.search(item_label):
                    kind = k
                    break
            if kind is None:
                continue
            item_abs_start = desc_start + item_m.start()
            item_abs_end = desc_start + item_m.end()
            results.append({
                'raw_latex': item_body,
                'clean_text': _clean_latex(item_body),
                'name': item_label.strip() if item_label.strip() else None,
                'env_name': 'distilled',
                'rule_name': '_DESCRIPTION_OUTER',
                'structure_type': kind,
                '_start': item_abs_start,
                '_end': item_abs_end,
            })

    # --- Rule 6: \noindent {\bf Assumption/Remark/Example N.} {\it body} ---
    for m in _NOINDENT_BF_ASSUMPTION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        label_text = m.group('label').strip()
        kind = _detect_subtype(label_text)
        body_raw = m.group('body').strip()
        # Strip trailing closing brace from \it{...} if present
        body_raw = re.sub(r'\}\s*$', '', body_raw).strip()
        if not body_raw:
            continue
        results.append({
            'raw_latex': body_raw,
            'clean_text': _clean_latex(body_raw),
            'name': label_text if label_text else None,
            'env_name': 'distilled',
            'rule_name': '_NOINDENT_BF_ASSUMPTION',
            'structure_type': kind,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule 7: \emph{Keyword.} or \textit{Keyword.} inline labeled ---
    for m in _INLINE_LABEL_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('keyword')
        kind = _detect_subtype(kw)
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_INLINE_LABEL_PATTERN',
            'structure_type': kind,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule 8: Plain paragraph leader "Remark." / "Example." / "Assumption." ---
    for m in _PLAIN_KEYWORD_LEADER.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('keyword')
        kind = _detect_subtype(kw)
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_PLAIN_KEYWORD_LEADER',
            'structure_type': kind,
            '_start': m.start(),
            '_end': m.end(),
        })

    return _deduplicate(results)
