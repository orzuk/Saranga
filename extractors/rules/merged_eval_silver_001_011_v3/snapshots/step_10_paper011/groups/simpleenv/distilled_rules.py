import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# 1. \begin{remark/example/assumption} ... \end{...} variants not in base map
#    (starred variants, capitalised, etc.)
# PRUNED — FP on paper009 | also 15 TP — review before uncommenting
# PATTERN_STD_ENV = re.compile(
#     r'\\begin\{(remark\*?|Remark\*?|example\*?|Example\*?|assumption\*?|Assumption\*?'
#     r'|assumptions\*?|Assumptions\*?|rem\*?|exam\*?|ex\*?)\}'
#     r'(?:\[(?P<opt>[^\]]*)\])?'
#     r'(?P<body>.*?)'
#     r'\\end\{\1\}',
#     re.DOTALL | re.IGNORECASE,
# )

# 2. \textbf{Remark:} / \textbf{Remark.} / \textbf{Note:} inline (no env)
#    terminated by next \begin{...}, \section, \subsection, \paragraph, or end
PATTERN_TEXTBF_REMARK = re.compile(
    r'\\textbf\{'
    r'(?P<kw>Remark|Note|Observation)'
    r'[^}]*\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\(?:sub)*section\b|\\paragraph\b).)+)',
    re.DOTALL,
)

# 3. \textbf{Example:} / \textbf{Example.} inline (no env)
# PRUNED — FP on paper006
# PATTERN_TEXTBF_EXAMPLE = re.compile(
#     r'\\textbf\{'
#     r'(?P<kw>Example|Illustration)'
#     r'[^}]*\}'
#     r'\s*:?\s*'
#     r'(?P<body>(?:(?!\\begin\{|\\(?:sub)*section\b|\\paragraph\b).)+)',
#     re.DOTALL,
# )

# 4. \textbf{Assumption:} / \textbf{Assumption.} inline (no env)
PATTERN_TEXTBF_ASSUMPTION = re.compile(
    r'\\textbf\{'
    r'(?P<kw>Assumption)'
    r'[^}]*\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\(?:sub)*section\b|\\paragraph\b).)+)',
    re.DOTALL,
)

# 5. {\bf Remark.} or {\bf Remark} inline (curly-brace old-style)
PATTERN_BF_REMARK = re.compile(
    r'\{\\bf\s+'
    r'(?P<kw>Remark|Note|Observation)'
    r'[^}]*\}'
    r'\.?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\(?:sub)*section\b|\\paragraph\b|\{\\bf\s+).)+)',
    re.DOTALL,
)

# 6. {\bf Assumption ...} inline (curly-brace old-style)
PATTERN_BF_ASSUMPTION = re.compile(
    r'\{\\bf\s+'
    r'(?P<kw>Assumption)'
    r'[^}]*\}'
    r'\.?\s*'
    r'(?:(?:\{\\it\s+|\{\\em\s+|\\textit\{|\\emph\{)'
    r'(?P<body_it>(?:(?!\}).)+)\}|'
    r'(?P<body>(?:(?!\\begin\{|\\(?:sub)*section\b|\\paragraph\b|\{\\bf\s+).)+))',
    re.DOTALL,
)

# 7. \noindent{\sc Remark[s]?.} ... (small-caps style)
PATTERN_SC_REMARK = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\(?:sub)*section\b|\\noindent\s*\{\\sc|\\appendix|\\end\{document\}).)+)',
    re.DOTALL | re.IGNORECASE,
)

# 8. \noindent{\sc Remark[s]?.} followed by \begin{list}...\end{list}
#    — extract the list block as a whole (items parsed separately)
PATTERN_SC_REMARKS_LIST = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL | re.IGNORECASE,
)

# sub-pattern: individual \item within a list
_LIST_ITEM_RE = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item|\\end\{list\})',
    re.DOTALL,
)

# 9. \begin{description} \item[Assumption ...] body \end{description}
PATTERN_DESCRIPTION_ENV = re.compile(
    r'\\begin\{description\}'
    r'(?P<block>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE,
)
_DESC_ITEM_RE = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|$)',
    re.DOTALL,
)

# 10. \noindent {\bf Assumption N.} {\it body} or plain body
PATTERN_NOINDENT_BF_ASSUMPTION = re.compile(
    r'\\noindent\s*'
    r'\{\\bf\s+(?P<label>Assumption[^}]*)\}'
    r'[.\s]*'
    r'(?:'
    r'\{\\it\s+(?P<body_it>.*?)\}'
    r'|'
    r'(?P<body>(?:(?!\\noindent|\\begin\{|\\(?:sub)*section\b|\n\s*\n\s*\n).)+)'
    r')',
    re.DOTALL,
)

# 11. \emph{Remark.} / \textit{Remark.} inline label (no env)
PATTERN_EMPH_REMARK = re.compile(
    r'(?:\\emph|\\textit)\{'
    r'(?P<kw>Remark|Note|Observation)'
    r'[^}]*\}'
    r'\.?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\(?:sub)*section\b|\\paragraph\b|\n\s*\n\s*\n).)+)',
    re.DOTALL,
)

# 12. \emph{Example.} / \textit{Example.} inline label (no env)
PATTERN_EMPH_EXAMPLE = re.compile(
    r'(?:\\emph|\\textit)\{'
    r'(?P<kw>Example|Illustration)'
    r'[^}]*\}'
    r'\.?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\(?:sub)*section\b|\\paragraph\b|\n\s*\n\s*\n).)+)',
    re.DOTALL,
)

# 13. Plain paragraph starting with "Remark." or "Note." at line start
PATTERN_INLINE_REMARK_PARA = re.compile(
    r'^(?P<kw>Remark|Note|Observation)\.\s+'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:sub)*section\b|\\begin\{|\\paragraph\b).)+)',
    re.DOTALL | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Excluded environment names (don't extract from inside these)
# ---------------------------------------------------------------------------
_EXCL_ENVS = [
    'proof', 'Proof',
    'figure', 'Figure',
    'table', 'Table',
    'tikzpicture',
    'align', 'align*', 'equation', 'equation*',
    'gather', 'gather*', 'multline', 'multline*',
    'array', 'matrix', 'pmatrix', 'bmatrix',
    'verbatim', 'lstlisting',
    'comment',
    'caption',
]

_EXCL_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCL_ENVS)) + r')\}',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain text conversion."""
    # Remove comments
    t = re.sub(r'%[^\n]*', '', text)
    # Remove common display math environments
    t = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}', ' ', t, flags=re.DOTALL)
    # Inline math: keep content roughly
    t = re.sub(r'\$\$.*?\$\$', ' ', t, flags=re.DOTALL)
    t = re.sub(r'\$.*?\$', ' ', t, flags=re.DOTALL)
    # Remove common commands but keep their arguments
    t = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb)\{([^}]*)\}', r'\1', t)
    # Remove labels, refs, cites
    t = re.sub(r'\\(?:label|ref|eqref|cite|citeA|citeNP|citealt)\{[^}]*\}', '', t)
    # Remove remaining commands
    t = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', t)
    # Remove braces
    t = re.sub(r'[{}]', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    # Find all \begin{excl_env} before start
    for m in _EXCL_ENV_RE.finditer(text, 0, start):
        env_name = m.group(1)
        end_pat = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\}',
            re.IGNORECASE,
        )
        em = end_pat.search(text, m.end())
        if em and em.start() > start:
            # The excluded env straddles our match start
            return True
    return False


def _subtype_from_env(env_name_raw: str) -> str:
    """Determine structure_type from raw environment/keyword name."""
    s = env_name_raw.lower().rstrip('*')
    if s in ('remark', 'rem', 'note', 'observation'):
        return 'remark'
    if s in ('example', 'exam', 'ex', 'illustration'):
        return 'example'
    if s in ('assumption', 'assumptions'):
        return 'assumption'
    return 'remark'


def _subtype_from_kw(kw: str) -> str:
    k = kw.lower()
    if k in ('remark', 'note', 'observation'):
        return 'remark'
    if k in ('example', 'illustration'):
        return 'example'
    if k in ('assumption', 'assumptions'):
        return 'assumption'
    return 'remark'


def _make_result(
    raw_latex: str,
    rule_name: str,
    structure_type: str,
    name: str = None,
    env_nm: str = 'distilled',
) -> dict:
    return {
        'raw_latex': raw_latex.strip(),
        'clean_text': _clean_latex(raw_latex),
        'name': name,
        'env_name': env_nm,
        'rule_name': rule_name,
        'structure_type': structure_type,
    }


def _dedup(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another (keep longer), deduplicate exact duplicates."""
    if not results:
        return results
    # Sort by length descending
    seen_spans: List[tuple] = []
    out = []
    # Simple dedup by raw_latex identity first
    seen_texts = set()
    for r in results:
        key = r['raw_latex'][:120]
        if key in seen_texts:
            continue
        seen_texts.add(key)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule: PATTERN_STD_ENV
    # Starred / capitalised variants of remark, example, assumption envs
#     # ------------------------------------------------------------------
#     for m in PATTERN_STD_ENV.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         env_raw = m.group(1)
#         body = m.group('body') or ''
#         opt = m.group('opt')
#         stype = _subtype_from_env(env_raw)
#         results.append(_make_result(
#             body,
#             rule_name='PATTERN_STD_ENV',
#             structure_type=stype,
#             name=opt.strip() if opt else None,
#         ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_SC_REMARKS_LIST
    # \noindent{\sc Remark[s].} \begin{list}...\end{list}
    # Extract each \item separately
    # ------------------------------------------------------------------
    for m in PATTERN_SC_REMARKS_LIST.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        list_body = m.group('list_env')
        for item_m in _LIST_ITEM_RE.finditer(list_body):
            body = item_m.group('body').strip()
            if not body:
                continue
            results.append(_make_result(
                body,
                rule_name='PATTERN_SC_REMARKS_LIST',
                structure_type='remark',
            ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_SC_REMARK
    # \noindent{\sc Remark.} free-text body (non-list)
    # Only match if the body does NOT start with \begin{list}
    # ------------------------------------------------------------------
    for m in PATTERN_SC_REMARK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        # Skip if this is actually a list (handled above)
        if body.lstrip().startswith(r'\begin{list}'):
            continue
        results.append(_make_result(
            body,
            rule_name='PATTERN_SC_REMARK',
            structure_type='remark',
        ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_DESCRIPTION_ENV
    # \begin{description}\item[Assumption/Remark/Example ...] body \end{description}
    # ------------------------------------------------------------------
    _desc_kind_map = [
        (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
        (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
        (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
        (re.compile(r'\bDefinitions?\b', re.IGNORECASE), 'definition'),
    ]
    for m in PATTERN_DESCRIPTION_ENV.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        block = m.group('block')
        for item_m in _DESC_ITEM_RE.finditer(block):
            label = item_m.group('label')
            body = item_m.group('body').strip()
            if not body:
                continue
            kind = None
            for pat, k in _desc_kind_map:
                if pat.search(label):
                    kind = k
                    break
            if kind not in ('remark', 'example', 'assumption'):
                continue
            results.append(_make_result(
                body,
                rule_name='PATTERN_DESCRIPTION_ENV',
                structure_type=kind,
                name=label.strip() if label.strip() else None,
            ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_NOINDENT_BF_ASSUMPTION
    # \noindent {\bf Assumption ...} {\it body} or plain body
    # ------------------------------------------------------------------
    for m in PATTERN_NOINDENT_BF_ASSUMPTION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body_it') or m.group('body') or ''
        body = body.strip()
        if not body:
            continue
        label = m.group('label').strip()
        results.append(_make_result(
            body,
            rule_name='PATTERN_NOINDENT_BF_ASSUMPTION',
            structure_type='assumption',
            name=label if label else None,
        ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_BF_ASSUMPTION
    # {\bf Assumption ...} {\it body} or plain body
    # (old-style curly braces)
    # ------------------------------------------------------------------
    for m in PATTERN_BF_ASSUMPTION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body_it') or m.group('body') or ''
        body = body.strip()
        if not body:
            continue
        label = m.group('kw').strip() if m.group('kw') else ''
        results.append(_make_result(
            body,
            rule_name='PATTERN_BF_ASSUMPTION',
            structure_type='assumption',
            name=label if label else None,
        ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_TEXTBF_REMARK
    # \textbf{Remark:} / \textbf{Note:} inline (no env)
    # ------------------------------------------------------------------
    for m in PATTERN_TEXTBF_REMARK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        kw = m.group('kw')
        results.append(_make_result(
            body,
            rule_name='PATTERN_TEXTBF_REMARK',
            structure_type=_subtype_from_kw(kw),
        ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_TEXTBF_EXAMPLE
    # \textbf{Example:} inline (no env)
#     # ------------------------------------------------------------------
#     for m in PATTERN_TEXTBF_EXAMPLE.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         body = m.group('body').strip()
#         if not body:
#             continue
#         kw = m.group('kw')
#         results.append(_make_result(
#             body,
#             rule_name='PATTERN_TEXTBF_EXAMPLE',
#             structure_type=_subtype_from_kw(kw),
#         ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_TEXTBF_ASSUMPTION
    # \textbf{Assumption:} inline (no env)
    # ------------------------------------------------------------------
    for m in PATTERN_TEXTBF_ASSUMPTION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make_result(
            body,
            rule_name='PATTERN_TEXTBF_ASSUMPTION',
            structure_type='assumption',
        ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_BF_REMARK
    # {\bf Remark.} inline (old-style curly braces)
    # ------------------------------------------------------------------
    for m in PATTERN_BF_REMARK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        kw = m.group('kw')
        results.append(_make_result(
            body,
            rule_name='PATTERN_BF_REMARK',
            structure_type=_subtype_from_kw(kw),
        ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_EMPH_REMARK
    # \emph{Remark.} / \textit{Remark.} inline label (no env)
    # ------------------------------------------------------------------
    for m in PATTERN_EMPH_REMARK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        kw = m.group('kw')
        results.append(_make_result(
            body,
            rule_name='PATTERN_EMPH_REMARK',
            structure_type=_subtype_from_kw(kw),
        ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_EMPH_EXAMPLE
    # \emph{Example.} / \textit{Example.} inline label (no env)
    # ------------------------------------------------------------------
    for m in PATTERN_EMPH_EXAMPLE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        kw = m.group('kw')
        results.append(_make_result(
            body,
            rule_name='PATTERN_EMPH_EXAMPLE',
            structure_type=_subtype_from_kw(kw),
        ))

    # ------------------------------------------------------------------
    # Rule: PATTERN_INLINE_REMARK_PARA
    # Plain paragraph starting with "Remark." or "Note." at line start
    # ------------------------------------------------------------------
    for m in PATTERN_INLINE_REMARK_PARA.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        kw = m.group('kw')
        results.append(_make_result(
            body,
            rule_name='PATTERN_INLINE_REMARK_PARA',
            structure_type=_subtype_from_kw(kw),
        ))

    return _dedup(results)
