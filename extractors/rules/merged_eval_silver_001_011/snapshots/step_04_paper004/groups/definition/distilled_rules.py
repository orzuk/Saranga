import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very small LaTeX -> plain text cleaner (no project imports)."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their arguments
    text = re.sub(r'\\(?:emph|textbf|textit|text|mathrm|mathbf|mathit|mathcal|mathbb|mathsf|mathtt|operatorname)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|it|em|rm|tt|sf)\s+([^}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite, \eqref
    text = re.sub(r'\\(?:label|ref|eqref|cite[A-Za-z]*)\{[^}]*\}', '', text)
    # Remove \begin{...} \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Replace display math environments with placeholder
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[A-Za-z]+\*?(?:\{[^}]*\}|\[[^\]]*\])*', ' ', text)
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose interiors we should not re-match
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop|'
    r'corollary|Corollary|cor|claim|Claim|conjecture|Conjecture|proof|Proof|'
    r'example|Example|exam|remark|Remark|rem|note|exercise|Exercise)\*?\}'
    r'.*?'
    r'\\end\{\1\*?\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) ranges that are inside excluded environments."""
    ranges = []
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    for (es, ee) in excluded_ranges:
        if start >= es and end <= ee:
            return True
        if start < ee and end > es:
            return True
    return False


def _overlaps(start: int, end: int, used: list) -> bool:
    for (us, ue) in used:
        if start < ue and end > us:
            return True
    return False


# ---------------------------------------------------------------------------
# Referential / negative guards (shared)
# ---------------------------------------------------------------------------

_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    flags=re.IGNORECASE,
)

_C1_NEGATIVE = re.compile(
    r'\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# R1: {\bf Name:} / \textbf{Name:} bold-labeled definition blocks
# Matches bold-header style: {\bf label:} body ... until next \bf or break
# PRUNED — FP on paper001, paper002, paper003 +1 more | also 1 TP — review before uncommenting
# INLINE_BF_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:\{\\bf\s+|\$\{\\bf\s+)(?P<name>[^}$]{1,120})(?:\}\$|\})'
#     r'(?::[ \t]*)?' 
#     r'(?:\\\\[ \t]*\n?)?'
#     r'[ \t]*'
#     r'(?P<body>(?:[^\\]|\\(?![Nn]ewcommand|[Rr]enewcommand|bf\b|textbf\{|section|subsection|begin\{|end\{))'
#     r'{20,800}?)'
#     r')'
#     r'(?=\n\s*\n|\{\\bf\s|\$\{\\bf\s|\\textbf\{|\\\\\s*\n\s*\n|'
#     r'\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

# R2: \textbf{Name:} bold-labeled definition blocks
# PRUNED — FP on paper002, paper003, paper004
# INLINE_TEXTBF_PATTERN = re.compile(
#     r'(?P<full>'
#     r'\\textbf\{(?P<name>[^}:]{1,100})\}:?'
#     r'(?:\\\\[ \t]*\n?)?'
#     r'[ \t]*'
#     r'(?P<body>(?:[^\\]|\\(?!textbf\{|section|subsection|begin\{|end\{)){20,800}?)'
#     r')'
#     r'(?=\n\s*\n|\\textbf\{|\\\\\s*\n\s*\n|'
#     r'\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

# R3: "X is called Y" definitional sentences
_C6_ANCHOR = re.compile(
    r'\bis\s+called\b',
    flags=re.IGNORECASE,
)
_C6_TAIL = re.compile(
    r'(?:[^.]|\.[^A-Z\s]){0,400}\.',
    flags=re.DOTALL,
)

# R4: "are defined as/to be" (extends base C2 to plural + display math)
_C2_EXT_ANCHOR = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)
_DISPLAY_MATH_TAIL = re.compile(
    r'(?:'
    r'\\ba\b.*?\\ea\b'
    r'|\\begin\{(?:align|equation|gather|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|eqnarray)\*?\}'
    r'|\\\[.*?\\\]'
    r'|\$\$.*?\$\$'
    r'|[^.]*'
    r')'
    r'[^.]*\.',
    flags=re.DOTALL,
)

# R5: "We (will) denote by X ..." inline definition
# PRUNED — FP on paper002, paper004 | also 2 TP — review before uncommenting
# INLINE_DENOTE_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:We\s+)?(?:will\s+)?(?:also\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|\$\$[^$]+\$\$|[A-Za-z0-9\\{}_^]+))'
#     r'(?:[^.]|\.[^A-Z\s]){0,400}'
#     r'\.)',
#     flags=re.DOTALL,
# )

# R6: "The notation X stands for ..." / "X stands for ..."
INLINE_STANDS_FOR_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:[Tt]he\s+notation\s+)?'
    r'(?P<name>(?:\$[^$]+\$|\$\$[^$]+\$\$|[A-Za-z0-9\\_ ]{1,60}?))\s+'
    r'stands\s+for\b'
    r'(?:[^.]|\.[^A-Z\s]){0,400}'
    r'\.)',
    flags=re.DOTALL,
)

# R7: "Let $$ ... $$ denote ..." or "Let $ ... $ denote ..."
INLINE_LET_DENOTE_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ll]et\s+'
    r'(?P<name>(?:\$\$[^$]+\$\$|\$[^$]+\$))'
    r'(?:[^.]|\.[^A-Z\s]){0,300}'
    r'\bdenote\b'
    r'(?:[^.]|\.[^A-Z\s]){0,300}'
    r'\.)',
    flags=re.DOTALL,
)

# R8: "Introduce X ..." definitional imperative with display math
INLINE_INTRODUCE_PATTERN = re.compile(
    r'(?P<full>'
    r'\bIntroduce\b\s+'
    r'(?P<name>[^.$\n\\]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{equation\*?\}.*?\\end\{equation\*?\})'
    r'(?:[^.]|\.[^A-Z\s]){0,300}'
    r'\.)',
    flags=re.DOTALL,
)

# R9: "we consider <name> $$ ... $$" definitional
INLINE_WE_CONSIDER_PATTERN = re.compile(
    r'(?P<full>'
    r'\bwe\s+consider\b\s+'
    r'(?P<name>[^.$\n\\]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{equation\*?\}.*?\\end\{equation\*?\})'
    r'(?:[^.]|\.[^A-Z\s]){0,300}'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R10: "we introduce ... call(ed) <name>: \begin{equation*}...\end{equation*}"
INLINE_INTRODUCE_CALLED_PATTERN = re.compile(
    r'(?P<full>'
    r'\bwe\s+introduce\b[^.\\]{0,150}'
    r'(?:call(?:ed)?)\s+'
    r'(?:\{\\it\s+|\{\\em\s+)?(?P<name>[^}.:\n]{1,80})(?:\})?\s*:?\s*'
    r'(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\\\[.*?\\\]'
    r'|\$\$.*?\$\$)'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R11: "Denote by X ... (called <name>) ... \begin{equation*}...\end{equation*}"
INLINE_DENOTE_BY_PATTERN = re.compile(
    r'(?P<full>'
    r'\bDenote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{}\s]{1,60}))'
    r'[^\\]{0,400}'
    r'(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\])'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R12: "the set \begin{equation} <name> = ... \end{equation} is non-empty"
INLINE_SET_EQUATION_PATTERN = re.compile(
    r'(?P<full>'
    r'\bthe\s+set\b[^\\]{0,150}'
    r'\\begin\{equation[^}]*\}[^\\]*?'
    r'(?P<name>\\?[A-Za-z][A-Za-z0-9_{}^\\]*\s*=)'
    r'.*?'
    r'\\end\{equation[^}]*\}'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R13: "a {\em term}; term is a/an <collection type> ..." (semicolon-intro definition)
INLINE_IS_A_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:\{\\em\s+(?P<em_name>[^}]+)\}|\\emph\{(?P<emph_name>[^}]+)\})'
    r'[^.;]{0,80}[;,]\s*'
    r'(?P<name>[A-Za-z][A-Za-z0-9 \-]{1,60}?)'
    r'\s+is\s+(?:a|an|the)\s+(?:given\s+)?'
    r'(?:collection|set|sequence|map|mapping|function|family|class|space|'
    r'operator|matrix|vector|graph|code|measure|distribution|process|'
    r'transform|pair|triple|tuple|list|array|structure|object|element|'
    r'member|subset|subspace|subgroup|ring|field|group|algebra|category)'
    r'\b'
    r'(?:[^.]|\.[^A-Z\s]){0,400}'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R14: "{\em term} obeys/satisfies ..." definitional
INLINE_OBEYS_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:a\s+)?(?:\{\\em\s+(?P<em_name>[^}]+)\}|\\emph\{(?P<emph_name>[^}]+)\})'
    r'[^.]{0,150}'
    r'\bobeys\b'
    r'(?:[^.]|\.[^A-Z\s]){0,400}'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R15: "X is a/the <term>" after section heading (paragraph-level definition)
# Captures definitional paragraphs immediately following section commands
# PRUNED — FP on paper001, paper003 | also 3 TP — review before uncommenting
# _SECTION_DEF_BLOCK = re.compile(
#     r'(?:\\(?:sub)*section\*?\{[^}]*\})'
#     r'(?:\s*(?:%[^\n]*)?\n)*'
#     r'\s*'
#     r'(?:\\label\{[^}]*\}\s*)?'
#     r'(?P<full>'
#     r'(?P<name>[^\n.]{10,150}?)'
#     r'(?:(?!\\(?:sub)*section|\\begin\{|\\end\{document\}).){100,2000}?'
#     r')'
#     r'(?=\n\s*\n|\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

_SECTION_DEF_KEYWORDS = re.compile(
    r'\b(define[sd]?|definition|notation|denote[sd]?|call|refer\s+to|'
    r'known\s+as|represent[s]?|consists?\s+of|form\s+of\s+the|'
    r'we\s+(?:say|use|write)|similar(?:ity)?\s+graph|clustering)\b',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX text using supplementary rules.
    Returns list of dicts with keys: raw_latex, clean_text, name, env_name,
    rule_name, structure_type.
    """
    results = []
    excluded_ranges = _build_excluded_ranges(text)
    used_spans = []  # list of (start, end) already claimed

    def _make_result(raw: str, name_raw, rule_name: str, start: int) -> dict:
        name_hint = None
        if name_raw:
            nr = str(name_raw).strip()
            m_math = re.search(r'\$(.+?)\$', nr)
            if m_math:
                name_hint = re.sub(r'\s+', ' ', m_math.group(1))[:80]
            else:
                cleaned = _clean_latex(nr)
                name_hint = cleaned[:80] if cleaned else None
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name_hint,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
        }

    def _try_add(raw: str, name_raw, rule_name: str, start: int, end: int):
        if not raw or len(raw.strip()) < 15:
            return
        if _inside_excluded_env(start, end, excluded_ranges):
            return
        if _REFERENTIAL.search(raw):
            return
        if _overlaps(start, end, used_spans):
            return
        used_spans.append((start, end))
        results.append(_make_result(raw, name_raw, rule_name, start))

    # ------------------------------------------------------------------
    # R1: {\bf Name:} bold-labeled blocks
#     # ------------------------------------------------------------------
#     for m in INLINE_BF_PATTERN.finditer(text):
#         raw = m.group('full').strip()
#         name_raw = m.group('name')
#         _try_add(raw, name_raw, 'INLINE_BF_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R2: \textbf{Name:} bold-labeled blocks
#     # ------------------------------------------------------------------
#     for m in INLINE_TEXTBF_PATTERN.finditer(text):
#         raw = m.group('full').strip()
#         name_raw = m.group('name')
#         _try_add(raw, name_raw, 'INLINE_TEXTBF_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R3: "X is called Y"
    # ------------------------------------------------------------------
    for anchor_m in _C6_ANCHOR.finditer(text):
        if _inside_excluded_env(anchor_m.start(), anchor_m.end(), excluded_ranges):
            continue
        start_search = max(0, anchor_m.start() - 150)
        prefix = text[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        nl_pos = prefix.rfind('\n\n')
        boundary = max(dot_pos, nl_pos)
        if boundary >= 0:
            name_start = start_search + boundary + 1
        else:
            name_start = start_search
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 150:
            continue
        tail_m = _C6_TAIL.match(text, anchor_m.end())
        if not tail_m:
            continue
        end_pos = tail_m.end()
        full_text = text[name_start:end_pos]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text.strip()) < 30:
            continue
        _try_add(full_text, name_text, '_C6_ANCHOR', name_start, end_pos)

    # ------------------------------------------------------------------
    # R4: "are defined as/to be" (plural extension of C2)
    # ------------------------------------------------------------------
    for anchor_m in _C2_EXT_ANCHOR.finditer(text):
        if _inside_excluded_env(anchor_m.start(), anchor_m.end(), excluded_ranges):
            continue
        start_search = max(0, anchor_m.start() - 150)
        prefix = text[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        nl_pos = prefix.rfind('\n\n')
        boundary = max(dot_pos, nl_pos)
        if boundary >= 0:
            name_start = start_search + boundary + 1
        else:
            name_start = start_search
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 150:
            continue
        search_end = min(len(text), anchor_m.end() + 800)
        tail_region = text[anchor_m.end():search_end]
        tail_m = _DISPLAY_MATH_TAIL.match(tail_region)
        if not tail_m:
            continue
        end_pos = anchor_m.end() + tail_m.end()
        full_text = text[name_start:end_pos]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text.strip()) < 20:
            continue
        _try_add(full_text, name_text, '_C2_EXT_ANCHOR', name_start, end_pos)

    # ------------------------------------------------------------------
    # R5: "We (will) denote by X ..."
#     # ------------------------------------------------------------------
#     for m in INLINE_DENOTE_PATTERN.finditer(text):
#         raw = m.group('full')
#         name_raw = m.group('name')
#         if _C1_NEGATIVE.search(raw):
#             continue
#         _try_add(raw, name_raw, 'INLINE_DENOTE_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R6: "X stands for ..."
    # ------------------------------------------------------------------
    for m in INLINE_STANDS_FOR_PATTERN.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name')
        _try_add(raw, name_raw, 'INLINE_STANDS_FOR_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R7: "Let $ ... $ denote ..."
    # ------------------------------------------------------------------
    for m in INLINE_LET_DENOTE_PATTERN.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name')
        _try_add(raw, name_raw, 'INLINE_LET_DENOTE_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R8: "Introduce X <display_math> ..."
    # ------------------------------------------------------------------
    for m in INLINE_INTRODUCE_PATTERN.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name')
        _try_add(raw, name_raw, 'INLINE_INTRODUCE_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R9: "we consider X <display_math> ..."
    # ------------------------------------------------------------------
    for m in INLINE_WE_CONSIDER_PATTERN.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name')
        _try_add(raw, name_raw, 'INLINE_WE_CONSIDER_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R10: "we introduce ... called <name>: <equation>"
    # ------------------------------------------------------------------
    for m in INLINE_INTRODUCE_CALLED_PATTERN.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name')
        _try_add(raw, name_raw, 'INLINE_INTRODUCE_CALLED_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R11: "Denote by X ... <equation>"
    # ------------------------------------------------------------------
    for m in INLINE_DENOTE_BY_PATTERN.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name')
        _try_add(raw, name_raw, 'INLINE_DENOTE_BY_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R12: "the set \begin{equation} <name> = ... \end{equation}"
    # ------------------------------------------------------------------
    # For this rule we want a wider context: grab surrounding sentences too
    _SET_EQ_CONTEXT = re.compile(
        r'(?P<full>'
        r'(?:we\s+\w+\s+that\s+)?[^.\\]{0,200}'
        r'\bthe\s+set\b[^\\]{0,150}'
        r'\\begin\{equation[^}]*\}.*?\\end\{equation[^}]*\}'
        r'(?:[^.]|\.[^A-Z\s]){0,150}'
        r'\.?)',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for m in _SET_EQ_CONTEXT.finditer(text):
        raw = m.group('full').strip()
        if len(raw) < 30:
            continue
        # extract equation content as name hint
        eq_m = re.search(
            r'\\begin\{equation[^}]*\}\s*(?:\\label\{[^}]*\}\s*)?'
            r'(?:%[^\n]*)?\s*(?P<lhs>\\?[A-Za-z][A-Za-z0-9_{}^\\]*)\s*=',
            raw, flags=re.DOTALL
        )
        name_raw = eq_m.group('lhs') if eq_m else None
        _try_add(raw, name_raw, 'INLINE_SET_EQUATION_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R13: "a {\em term}; term is a/an <type> ..."
    # ------------------------------------------------------------------
    for m in INLINE_IS_A_PATTERN.finditer(text):
        raw = m.group('full')
        em = m.group('em_name') or m.group('emph_name')
        name_raw = em if em else m.group('name')
        _try_add(raw, name_raw, 'INLINE_IS_A_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R14: "{\em term} obeys ..."
    # ------------------------------------------------------------------
    for m in INLINE_OBEYS_PATTERN.finditer(text):
        raw = m.group('full')
        em = m.group('em_name') or m.group('emph_name')
        _try_add(raw, em, 'INLINE_OBEYS_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # R15: Paragraph-level definition after \section heading
#     # ------------------------------------------------------------------
#     for m in _SECTION_DEF_BLOCK.finditer(text):
#         raw = m.group('full').strip()
#         if not raw or len(raw) < 80:
#             continue
#         if not _SECTION_DEF_KEYWORDS.search(raw):
#             continue
#         if _REFERENTIAL.search(raw):
#             continue
#         name_raw = m.group('name').strip() if m.group('name') else None
#         _try_add(raw, name_raw, '_SECTION_DEF_BLOCK', m.start('full'), m.end('full'))

    # ------------------------------------------------------------------
    # Final deduplication: remove strict substring matches, keep longer
    # ------------------------------------------------------------------
    results.sort(key=lambda r: -len(r['raw_latex']))
    deduped = []
    seen_spans = []
    for r in results:
        raw = r['raw_latex']
        is_sub = False
        for kept in deduped:
            if raw in kept['raw_latex'] or kept['raw_latex'] in raw:
                is_sub = True
                break
        if not is_sub:
            deduped.append(r)

    for r in deduped:
        r.pop('_start', None)

    return deduped
