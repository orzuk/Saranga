import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Helpers
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|exercise|figure|table|lstlisting|verbatim)\*?\}',
    re.IGNORECASE,
)

_CLEAN_STRIP_RE = re.compile(
    r'\\(?:label|ref|eqref|cite|cref|citep|citet|labelcref)\{[^}]*\}'
    r'|\\(?:textbf|textit|emph|textrm|mathbf|mathit|mathrm|text)\{([^}]*)\}'
    r'|\\(?:left|right|big|Big|bigg|Bigg)\b'
    r'|\\[a-zA-Z]+\*?\s*'
    r'|[{}]'
    r'|\$',
    re.DOTALL,
)

_WHITESPACE_RE = re.compile(r'\s+')


def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain text conversion."""
    # preserve text in \text{...} by capturing group 1 in _CLEAN_STRIP_RE
    def _replace(m):
        g = m.group(1)
        return (' ' + g + ' ') if g is not None else ' '
    result = _CLEAN_STRIP_RE.sub(_replace, text)
    return _WHITESPACE_RE.sub(' ', result).strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside a proof/example/remark etc."""
    # Look for any excluded-env \begin before start; check if its matching \end
    # comes after start.
    for m in _EXCLUDED_ENV_RE.finditer(text, 0, start):
        env = m.group(1)
        end_pat = re.compile(
            r'\\end\{' + re.escape(env) + r'\*?\}',
            re.IGNORECASE,
        )
        em = end_pat.search(text, m.end())
        if em and em.start() >= start:
            return True
    return False


# ---------------------------------------------------------------------------
# Pattern 1 – \begin{restatable}{<kind>}{<macro>} ... \end{restatable}
# ---------------------------------------------------------------------------
RESTATABLE_PATTERN = re.compile(
    r'\\begin\{restatable\}'
    r'\{(?P<kind>[^}]+)\}'
    r'\{(?P<macro>[^}]*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{restatable\}',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 2 – \begin{property}[opt] ... \end{property}  -> proposition
# ---------------------------------------------------------------------------
PROPERTY_ENV_PATTERN = re.compile(
    r'\\begin\{(property)\*?\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{property\*?\}',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 3 – optimization problems in equation/align/gather whose body
#             contains \min or \max AND a constraint marker (s.t. / subject to)
# ---------------------------------------------------------------------------
OPT_MATH_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<envname>align|gather|equation)\*?\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\*?\}',
    re.DOTALL | re.IGNORECASE,
)

_OPT_OBJ_RE = re.compile(r'\\(?:max|min|argmax|argmin|sup|inf)\b', re.IGNORECASE)
_OPT_ST_RE = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}'
    r'|\\text\s*\{\s*subject\s+to\s*\}'
    r'|\bsubject\s+to\b'
    r'|\\mathrm\s*\{\s*s\.?\s*t\.?\s*\}',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 4 – inline open-problem paragraphs (prose, no env wrapper)
#             anchored on recognised phrases
# ---------------------------------------------------------------------------
OPEN_PROBLEM_PHRASE_PATTERN = re.compile(
    r'(?:(?<=\n\n)|(?<=\n)|(?:^))'
    r'(?P<body>'
    r'(?:'
    r'(?:We\s+leave\b[^.]{0,500}?(?:open\s+(?:questions?|problems?)|future\s+work))'
    r'|(?:(?:It\s+)?(?:remains?|is(?:\s+still)?)\s+(?:an?\s+)?open\s+(?:question|problem)\b)'
    r'|(?:open\s+(?:questions?|problems?)\s+(?:remain|include|are)\b)'
    r'|(?:We\s+(?:pose|raise|note|highlight)\s+(?:the\s+following\s+)?open\b)'
    r'|(?:Several\s+(?:interesting\s+)?(?:questions?|problems?)\s+remain)'
    r')'
    r'[^\n]{0,600}'
    r'(?:\n(?!\n)[^\n]{0,300}){0,8}'
    r')',
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Pattern 5 – "We leave … to future work" prose sentences
# ---------------------------------------------------------------------------
# PRUNED — FP on paper005, paper012
# FUTURE_WORK_PATTERN = re.compile(
#     r'(?P<body>'
#     r'[A-Z][^.]{0,500}?'
#     r'[Ww]e\s+leave\b[^.]{0,300}?'
#     r'(?:to|for)\s+future\s+work'
#     r'[^.]*\.'
#     r')',
#     re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern 6 – \textbf{Theorem/Lemma/…} … inline bold-keyword theorem-like
# ---------------------------------------------------------------------------
_KIND_WORD_MAP: Dict[str, str] = {
    'theorem': 'theorem',
    'lemma': 'lemma',
    'proposition': 'proposition',
    'corollary': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'problem': 'problem',
    'open problem': 'open_problem',
    'open_problem': 'open_problem',
}

_KIND_WORDS_RE_SRC = '|'.join(
    re.escape(k) for k in sorted(_KIND_WORD_MAP.keys(), key=len, reverse=True)
)

BOLD_KEYWORD_PATTERN = re.compile(
    r'(?:\\textbf\{(?P<kw1>' + _KIND_WORDS_RE_SRC + r')\s*(?:[^}]*)?\}'
    r'|\\emph\{(?P<kw2>' + _KIND_WORDS_RE_SRC + r')\s*(?:[^}]*)?\}'
    r'|\{\\bf\s+(?P<kw3>' + _KIND_WORDS_RE_SRC + r')[^}]*\}'
    r')'
    r'(?P<body>[^\n]{0,50}'
    r'(?:\n(?!\n)[^\n]{0,300}){0,12})',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 7 – \begin{<custom>} … \end{<custom>} for additional known aliases
#             that aren't in the base map but are structurally theorem-like
# ---------------------------------------------------------------------------
_EXTRA_ENV_MAP: Dict[str, str] = {
    'thm': 'theorem',
    'lem': 'lemma',
    'prop': 'proposition',
    'cor': 'corollary',
    'coro': 'corollary',
    'clm': 'claim',
    'conj': 'conjecture',
    'theo': 'theorem',
    'maintheorem': 'theorem',
    'mainlemma': 'lemma',
    'mainthm': 'theorem',
    'sublemma': 'lemma',
    'fact': 'proposition',
    'observation': 'proposition',
    'obs': 'proposition',
    'notation': 'remark',
    'property': 'proposition',
}

_EXTRA_ENV_NAMES = list(_EXTRA_ENV_MAP.keys())
_EXTRA_ENV_PAT_SRC = '|'.join(re.escape(e) for e in _EXTRA_ENV_NAMES)

EXTRA_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>' + _EXTRA_ENV_PAT_SRC + r')\*?\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\*?\}',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# internal: map raw env/keyword to canonical structure_type
# ---------------------------------------------------------------------------
_BASE_ENV_KIND_MAP: Dict[str, str] = {
    'theorem': 'theorem', 'Theorem': 'theorem', 'thm': 'theorem',
    'lemma': 'lemma', 'Lemma': 'lemma', 'lem': 'lemma',
    'proposition': 'proposition', 'Proposition': 'proposition', 'prop': 'proposition',
    'corollary': 'corollary', 'Corollary': 'corollary', 'cor': 'corollary',
    'claim': 'claim', 'Claim': 'claim',
    'conjecture': 'conjecture', 'Conjecture': 'conjecture',
    'problem': 'problem', 'Problem': 'problem',
    'openproblem': 'open_problem', 'openProblem': 'open_problem',
    'openquestion': 'open_problem', 'open': 'open_problem',
    'property': 'proposition', 'Property': 'proposition',
    'theo': 'theorem',
    'maintheorem': 'theorem', 'mainthm': 'theorem', 'mainlemma': 'lemma',
    'sublemma': 'lemma',
    'fact': 'proposition', 'observation': 'proposition', 'obs': 'proposition',
    'cor': 'corollary', 'coro': 'corollary',
    'clm': 'claim', 'conj': 'conjecture',
}


def _resolve_structure_type(raw: str) -> str:
    raw_stripped = raw.rstrip('*').strip()
    lower = raw_stripped.lower()
    if lower in _BASE_ENV_KIND_MAP:
        return _BASE_ENV_KIND_MAP[lower]
    if raw_stripped in _BASE_ENV_KIND_MAP:
        return _BASE_ENV_KIND_MAP[raw_stripped]
    for k, v in _KIND_WORD_MAP.items():
        if k.lower() == lower:
            return v
    return 'theorem'


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _dedup(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another, or near-duplicate spans."""
    if not results:
        return results
    # Sort by length descending so we prefer longer matches
    results.sort(key=lambda d: len(d['raw_latex']), reverse=True)
    kept: List[dict] = []
    seen_spans = []  # (start, end) in original text – use _src_pos if available
    for r in results:
        raw = r['raw_latex']
        pos = r.get('_src_pos', -1)
        length = len(raw)
        # Check if this raw is nearly identical to an already-kept result
        duplicate = False
        for k in kept:
            k_raw = k['raw_latex']
            # near-exact match
            if raw in k_raw or k_raw in raw:
                duplicate = True
                break
            # positional overlap
            if pos >= 0:
                k_pos = k.get('_src_pos', -1)
                if k_pos >= 0:
                    k_len = len(k_raw)
                    # overlapping spans
                    if not (pos + length <= k_pos or k_pos + k_len <= pos):
                        duplicate = True
                        break
        if not duplicate:
            kept.append(r)
    # Remove internal bookkeeping key before returning
    for r in kept:
        r.pop('_src_pos', None)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \begin{restatable}{kind}{macro} ... \end{restatable}
    # ------------------------------------------------------------------
    for m in RESTATABLE_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        kind_raw = m.group('kind').strip()
        structure_type = _resolve_structure_type(kind_raw)
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'RESTATABLE_PATTERN',
            'structure_type': structure_type,
            '_src_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule B: \begin{property} ... \end{property} -> proposition
    # ------------------------------------------------------------------
    for m in PROPERTY_ENV_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PROPERTY_ENV_PATTERN',
            'structure_type': 'proposition',
            '_src_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule C: equation/align/gather with \min/\max + s.t. -> problem
    # ------------------------------------------------------------------
    for m in OPT_MATH_ENV_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        if not (_OPT_OBJ_RE.search(body) and _OPT_ST_RE.search(body)):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPT_MATH_ENV_PATTERN',
            'structure_type': 'problem',
            '_src_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule D: open-problem prose paragraphs (phrase-anchored)
    # ------------------------------------------------------------------
    for m in OPEN_PROBLEM_PHRASE_PATTERN.finditer(text):
        start = m.start()
        body = m.group('body').strip()
        if len(body) < 60:
            continue
        if _inside_excluded_env(text, start, start + len(body)):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPEN_PROBLEM_PHRASE_PATTERN',
            'structure_type': 'open_problem',
            '_src_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule E: "We leave … to/for future work" sentences -> open_problem
#     # ------------------------------------------------------------------
#     for m in FUTURE_WORK_PATTERN.finditer(text):
#         start = m.start()
#         body = m.group('body').strip()
#         if len(body) < 40:
#             continue
#         if _inside_excluded_env(text, start, start + len(body)):
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'FUTURE_WORK_PATTERN',
#             'structure_type': 'open_problem',
#             '_src_pos': start,
#         })

    # ------------------------------------------------------------------
    # Rule F: extra env aliases (property already handled above)
    # ------------------------------------------------------------------
    for m in EXTRA_ENV_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env_raw = m.group('env').rstrip('*').strip()
        # Skip property – already handled by PROPERTY_ENV_PATTERN
        if env_raw.lower() == 'property':
            continue
        structure_type = _EXTRA_ENV_MAP.get(env_raw.lower(), 'theorem')
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'EXTRA_ENV_PATTERN',
            'structure_type': structure_type,
            '_src_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule G: \textbf{Theorem/Lemma/…} inline bold-keyword blocks
    # ------------------------------------------------------------------
    for m in BOLD_KEYWORD_PATTERN.finditer(text):
        start = m.start()
        kw = m.group('kw1') or m.group('kw2') or m.group('kw3') or ''
        kw = kw.strip().lower()
        structure_type = _KIND_WORD_MAP.get(kw, 'theorem')
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, start, start + len(body)):
            continue
        results.append({
            'raw_latex': m.group(0),
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BOLD_KEYWORD_PATTERN',
            'structure_type': structure_type,
            '_src_pos': start,
        })

    return _dedup(results)
