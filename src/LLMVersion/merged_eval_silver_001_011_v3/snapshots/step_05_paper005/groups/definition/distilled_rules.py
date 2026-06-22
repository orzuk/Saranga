import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return plain text."""
    t = text
    # Remove display math environments
    t = re.sub(r'\\begin\{[a-zA-Z*]+\}.*?\\end\{[a-zA-Z*]+\}', ' ', t, flags=re.DOTALL)
    # Remove inline math
    t = re.sub(r'\$\$.*?\$\$', ' ', t, flags=re.DOTALL)
    t = re.sub(r'\\\[.*?\\\]', ' ', t, flags=re.DOTALL)
    t = re.sub(r'\$[^$]*\$', ' ', t, flags=re.DOTALL)
    # Remove common commands but keep argument
    t = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb|operatorname)\{([^}]*)\}', r'\1', t)
    t = re.sub(r'\{\\(?:em|bf|it|rm|tt)\s+([^}]*)\}', r'\1', t)
    # Remove remaining commands
    t = re.sub(r'\\[a-zA-Z]+\*?(?:\{[^}]*\}|\[[^\]]*\])*', ' ', t)
    t = re.sub(r'[{}]', ' ', t)
    # Collapse whitespace
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


# Environments to exclude (theorem-like, proof, example, remark)
_EXCLUDED_ENV_NAMES = [
    'theorem', 'Theorem', 'thm', 'lemma', 'Lemma', 'lem',
    'proposition', 'Proposition', 'prop', 'corollary', 'Corollary', 'cor',
    'claim', 'Claim', 'conjecture', 'Conjecture',
    'proof', 'Proof',
    'example', 'Example', 'exam',
    'remark', 'Remark', 'rem', 'note',
    'exercise', 'Exercise',
    'problem', 'Problem',
]

_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\}'
    r'.*?'
    r'\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _build_excluded_mask(text: str) -> List[bool]:
    """Build a boolean mask; True positions are inside excluded environments."""
    mask = [False] * len(text)
    for m in _EXCLUDED_ENV_RE.finditer(text):
        for i in range(m.start(), min(m.end(), len(text))):
            mask[i] = True
    return mask


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

# ---- C6: {\bf Term:} or {\bf Term} definitional bold-header blocks ----------
# Matches {\bf <name>} or {\bf <name>:} followed by definitional prose
# Ends at \\ newline, double blank line, \begin{, \section, \subsection
# PRUNED — FP on paper001, paper002, paper003 +1 more | also 4 TP — review before uncommenting
# BF_TERM_PATTERN = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}]{1,120}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,1200}?)'
#     r'(?=\\\\\s*(?:\n|$)|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# ---- C6_PLURAL: 'are defined as' (plural form of C2) -----------------------
C2_ANCHOR_PLURAL = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)

_C2_TAIL = re.compile(
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.',
    flags=re.DOTALL,
)

# ---- C7: (also called ...) / (known as ...) parenthetical ------------------
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# ALSO_CALLED_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,180}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,400}?\.)',
#     flags=re.DOTALL,
# )

# ---- C5_EMPH_SEMI: \emph{term}; ... is/are ... ------------------------------
EMPH_SEMI_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,160}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.]{0,400}\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- DENOTE_BY: 'We (will) denote by X ...' --------------------------------
# PRUNED — FP on paper002, paper003, paper004 | also 1 TP — review before uncommenting
# DENOTE_BY_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:will\s+)?|[Ll]et\s+us\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,.|\s]{1,80}?))'
#     r'\s+(?:the\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---- LET_DENOTE: 'Let X denote ...' ----------------------------------------
# PRUNED — FP on paper004
# LET_DENOTE_PATTERN = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.|()\[\]]{1,80}?))'
#     r'\s+denote\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.DOTALL,
# )

# ---- STANDS_FOR: 'X stands for ...' ----------------------------------------
STANDS_FOR_PATTERN = re.compile(
    r'(?P<full>'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{}\s,.|()\[\]]{1,80}?))'
    r'\s+(?:stands\s+for|refers\s+to)\s+'
    r'(?:the\s+|a\s+|an\s+)?'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- IMPERATIVE_INTRODUCE: 'Introduce X' / 'Set X = ' at sentence start ----
IMPERATIVE_INTRODUCE_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:(?:^|\n)[ \t]*|(?<=[.!?])\s+)'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^.\$\n]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|(?:\\begin\{[a-zA-Z*]+\}.*?\\end\{[a-zA-Z*]+\})|[^.])*\.)',
    flags=re.DOTALL | re.MULTILINE,
)

# ---- INTRODUCE_CALL: 'we introduce ... call {\it NAME}:' -------------------
INTRODUCE_CALL_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.]{1,160}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?call\s+'
    r'(?:\{\\it\s+|\{\\textit\{|\\textit\{|\\emph\{)?[^{}]{1,80}(?:\}\}?|\})?\s*'
    r':'
    r'(?:\s*\\begin\{(?P<envn>[a-zA-Z*]+)\}.*?\\end\{(?P=envn)\}'
    r'|\s*\$\$.*?\$\$'
    r'|\s*\\\[.*?\\\])'
    r')',
    flags=re.DOTALL,
)

# ---- OBEYS_IF: '{\em term} obeys/satisfies ... if ...' ---------------------
OBEYS_IF_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.]{0,160}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{(?P<en>[a-zA-Z*]+)\}.*?\\end\{(?P=en)\}|[^.]){0,600}?'
    r'\bif\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- WE_WRITE: 'we write X for Y, namely ...' ------------------------------
WE_WRITE_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9_\\(),.\s]{1,80}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin|\\section|\\subsection).){1,400}?'
    r'\bnamely\b'
    r'(?:(?!\\begin|\\section|\\subsection).){0,800}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- DEFINE_ENV: 'We define X as \begin{env}...\end{env}' ------------------
DEFINE_ENV_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,80}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?:[^\\]|\\(?!begin))*?'
    r'(?P<envbody>\\begin\{(?P<envn>[a-zA-Z*]+)\}.*?\\end\{(?P=envn)\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- INTRODUCE_AS_MATH: 'we (can) introduce X as $$ ... $$' ----------------
INTRODUCE_AS_MATH_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'\s+as\s+'
    r'(?:[^$]|\$(?!\$))*?'
    r'(?P<math>\$\$.*?\$\$)'
    r'(?:[^.]*\.)?'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- EM_SECTION_PARA: paragraph after section heading with {\em ...} -------
_SECTION_HEADING_RE = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*\}',
    flags=re.DOTALL,
)
_EM_TERM_RE = re.compile(
    r'(?:\{\\em\s+(?P<name>[^}]{2,80})\}|\\textit\{(?P<name2>[^}]{2,80})\}'
    r'|\\emph\{(?P<name3>[^}]{2,80})\})',
)
_NEXT_BLOCK_RE = re.compile(
    r'\n[ \t]*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}',
)

# ---- WE_CONSIDER: 'we consider X ... and let Y denote ...' -----------------
WE_CONSIDER_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+consider\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'\s*(?:[,.]|\s)\s*'
    r'(?:and\s+)?let\s+[^.]{1,120}?\s+denote\s+'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Name extraction helper
# ---------------------------------------------------------------------------

def _extract_name(raw: str) -> str:
    """Extract a clean name hint from raw LaTeX."""
    if raw is None:
        return ''
    raw = raw.strip()
    # Try to get the math symbol
    m = re.search(r'\$(.+?)\$', raw)
    if m:
        inner = m.group(1)
        inner = re.sub(r'\\[a-zA-Z]+', '', inner)
        inner = re.sub(r'[{}]', '', inner)
        return inner.strip()[:80]
    # Remove LaTeX commands
    t = re.sub(r'\\(?:textbf|textit|emph|text)\{([^}]*)\}', r'\1', raw)
    t = re.sub(r'\{\\(?:em|bf|it|rm)\s+([^}]*)\}', r'\1', t)
    t = re.sub(r'\\[a-zA-Z]+', '', t)
    t = re.sub(r'[{}]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()[:80]


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _dedup(results: List[dict]) -> List[dict]:
    """Remove overlapping / duplicate matches keeping the first encountered."""
    out: List[dict] = []
    seen_spans: List[tuple] = []  # (start, end)
    seen_texts: List[str] = []

    for r in results:
        s = r.get('_start', 0)
        e = r.get('_end', 0)
        ct = (r.get('clean_text') or '').strip().lower()

        # Check span overlap
        overlaps = False
        for ps, pe in seen_spans:
            if s < pe and e > ps:
                overlaps = True
                break

        # Check text near-duplicate
        if not overlaps and ct and len(ct) > 20:
            for prev in seen_texts:
                if ct in prev or prev in ct:
                    overlaps = True
                    break
                min_len = min(len(ct), len(prev))
                if min_len > 30 and ct[:30] == prev[:30]:
                    overlaps = True
                    break

        if not overlaps:
            out.append(r)
            seen_spans.append((s, e))
            if ct:
                seen_texts.append(ct)

    return out


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX text using supplementary rules.
    Returns a list of dicts with keys: raw_latex, clean_text, name, env_name,
    rule_name, structure_type.
    """
    results: List[dict] = []

    # Build excluded-env mask once
    excluded_mask = _build_excluded_mask(text)

    def _is_excluded(start: int, end: int) -> bool:
        # Fast check: if start is masked, skip
        if start < len(excluded_mask) and excluded_mask[start]:
            return True
        return False

    def _make_result(full_text: str, name_raw: str, rule_name: str,
                     start: int, end: int) -> dict:
        ct = _clean_latex(full_text)
        name_hint = _extract_name(name_raw) if name_raw else None
        return {
            'raw_latex': full_text,
            'clean_text': ct,
            'name': name_hint or None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_start': start,
            '_end': end,
        }

    # ------------------------------------------------------------------
    # Rule BF_TERM_PATTERN: {\bf Term:} definitional bold-header blocks
#     # ------------------------------------------------------------------
#     for m in BF_TERM_PATTERN.finditer(text):
#         if _is_excluded(m.start(), m.end()):
#             continue
#         full_text = m.group('full')
#         name_raw = m.group('name')
#         if not name_raw or len(name_raw.strip()) < 1:
#             continue
#         if _REFERENTIAL.search(full_text):
#             continue
#         results.append(_make_result(full_text, name_raw, 'BF_TERM_PATTERN',
#                                     m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule C2_ANCHOR_PLURAL: 'are defined as/to be' (plural C2)
    # ------------------------------------------------------------------
    for anchor_m in C2_ANCHOR_PLURAL.finditer(text):
        if _is_excluded(anchor_m.start(), anchor_m.end()):
            continue
        start_search = max(0, anchor_m.start() - 80)
        prefix = text[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        name_start = (start_search + dot_pos + 1) if dot_pos >= 0 else start_search
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 80:
            continue
        tail_m = _C2_TAIL.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_text, 'C2_ANCHOR_PLURAL',
                                    name_start, tail_m.end()))

    # ------------------------------------------------------------------
    # Rule ALSO_CALLED_PATTERN: (also called X) / (known as X)
#     # ------------------------------------------------------------------
#     for m in ALSO_CALLED_PATTERN.finditer(text):
#         if _is_excluded(m.start(), m.end()):
#             continue
#         full_text = m.group('full')
#         name_raw = m.group('name')
#         if not name_raw or len(name_raw.strip()) < 2:
#             continue
#         if _REFERENTIAL.search(full_text):
#             continue
#         results.append(_make_result(full_text, name_raw, 'ALSO_CALLED_PATTERN',
#                                     m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule EMPH_SEMI_PATTERN: \emph{term}; ... is/are ...
    # ------------------------------------------------------------------
    for m in EMPH_SEMI_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name') or m.group('name2') or ''
        # Must have 'is' or 'are' after the semicolon
        semi_pos = full_text.find(';')
        if semi_pos < 0:
            continue
        after_semi = full_text[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw, 'EMPH_SEMI_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule DENOTE_BY_PATTERN: 'We (will) denote by X ...'
#     # ------------------------------------------------------------------
#     for m in DENOTE_BY_PATTERN.finditer(text):
#         if _is_excluded(m.start(), m.end()):
#             continue
#         full_text = m.group('full')
#         name_raw = m.group('name')
#         if _REFERENTIAL.search(full_text):
#             continue
#         if _C1_NEGATIVE.search(full_text):
#             continue
#         results.append(_make_result(full_text, name_raw, 'DENOTE_BY_PATTERN',
#                                     m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule LET_DENOTE_PATTERN: 'Let X denote ...'
#     # ------------------------------------------------------------------
#     for m in LET_DENOTE_PATTERN.finditer(text):
#         if _is_excluded(m.start(), m.end()):
#             continue
#         full_text = m.group('full')
#         name_raw = m.group('name')
#         if _REFERENTIAL.search(full_text):
#             continue
#         results.append(_make_result(full_text, name_raw, 'LET_DENOTE_PATTERN',
#                                     m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule STANDS_FOR_PATTERN: 'X stands for ...'
    # ------------------------------------------------------------------
    for m in STANDS_FOR_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name')
        if not name_raw or len(name_raw.strip()) < 1:
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw, 'STANDS_FOR_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule IMPERATIVE_INTRODUCE_PATTERN: 'Introduce X' / 'Set X =' at start
    # ------------------------------------------------------------------
    for m in IMPERATIVE_INTRODUCE_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name')
        if not name_raw or len(name_raw.strip()) < 2:
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw,
                                    'IMPERATIVE_INTRODUCE_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule INTRODUCE_CALL_PATTERN: 'we introduce ... call {\it NAME}:'
    # ------------------------------------------------------------------
    for m in INTRODUCE_CALL_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name')
        if not name_raw or len(name_raw.strip()) < 2:
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw,
                                    'INTRODUCE_CALL_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule OBEYS_IF_PATTERN: '{\em term} obeys/satisfies ... if ...'
    # ------------------------------------------------------------------
    for m in OBEYS_IF_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name') or m.group('name2') or ''
        if not name_raw.strip():
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw, 'OBEYS_IF_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule WE_WRITE_PATTERN: 'we write X for Y, namely ...'
    # ------------------------------------------------------------------
    for m in WE_WRITE_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw, 'WE_WRITE_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule DEFINE_ENV_PATTERN: 'We define X as \begin{env}...\end{env}'
    # ------------------------------------------------------------------
    for m in DEFINE_ENV_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name')
        if not name_raw or len(name_raw.strip()) < 1:
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw, 'DEFINE_ENV_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule INTRODUCE_AS_MATH_PATTERN: 'we (can) introduce X as $$ ... $$'
    # ------------------------------------------------------------------
    for m in INTRODUCE_AS_MATH_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name')
        if not name_raw or len(name_raw.strip()) < 2:
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw,
                                    'INTRODUCE_AS_MATH_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule WE_CONSIDER_PATTERN: 'we consider X ... and let Y denote ...'
    # ------------------------------------------------------------------
    for m in WE_CONSIDER_PATTERN.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        full_text = m.group('full')
        name_raw = m.group('name')
        if not name_raw or len(name_raw.strip()) < 2:
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_raw, 'WE_CONSIDER_PATTERN',
                                    m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule EM_SECTION_PARA: paragraph after section heading with {\em ...}
    # ------------------------------------------------------------------
    for sec_m in _SECTION_HEADING_RE.finditer(text):
        para_start = sec_m.end()
        if _is_excluded(para_start, para_start + 1):
            continue
        nb = _NEXT_BLOCK_RE.search(text, para_start)
        para_end = nb.start() if nb else len(text)
        para_text = text[para_start:para_end].strip()
        if not para_text or len(para_text) < 40:
            continue
        em_m = _EM_TERM_RE.search(para_text)
        if not em_m:
            continue
        if _REFERENTIAL.search(para_text):
            continue
        name_raw = (em_m.group('name') or em_m.group('name2') or
                    em_m.group('name3') or '')
        ct = _clean_latex(para_text)
        results.append({
            'raw_latex': para_text,
            'clean_text': ct,
            'name': _extract_name(name_raw) or None,
            'env_name': 'distilled',
            'rule_name': 'EM_SECTION_PARA',
            'structure_type': 'definition',
            '_start': para_start,
            '_end': para_end,
        })

    # ------------------------------------------------------------------
    # Sort by start position, then deduplicate
    # ------------------------------------------------------------------
    results.sort(key=lambda r: r.get('_start', 0))
    results = _dedup(results)

    # Strip internal position keys
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
