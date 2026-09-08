import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return readable text."""
    t = text
    # Remove display math environments
    t = re.sub(r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}', ' [MATH] ', t, flags=re.DOTALL)
    # Remove inline math
    t = re.sub(r'\$\$.*?\$\$', ' [MATH] ', t, flags=re.DOTALL)
    t = re.sub(r'\\\[.*?\\\]', ' [MATH] ', t, flags=re.DOTALL)
    t = re.sub(r'\$[^$]+\$', '[MATH]', t)
    # Remove common commands keeping their argument
    t = re.sub(r'\\(?:emph|textit|textbf|texttt|text|mathrm|mathbf|mathit|mathcal|mathbb)\{([^}]*)\}', r'\1', t)
    t = re.sub(r'\{\\(?:em|it|bf|tt)\s+([^}]*)\}', r'\1', t)
    t = re.sub(r'\\(?:cite|ref|label|eqref)\{[^}]*\}', '', t)
    t = re.sub(r'\\(?:left|right)[.()\[\]|]', '', t)
    t = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', t)
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    t = re.sub(r'[{}]', ' ', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{2,}', '\n', t)
    return t.strip()


# Environments that should be excluded (we do NOT want to fire inside these)
_EXCLUDED_ENV_NAMES = [
    'proof', 'Proof',
    'theorem', 'Theorem', 'thm', 'theo',
    'lemma', 'Lemma', 'lem',
    'proposition', 'Proposition', 'prop',
    'corollary', 'Corollary', 'cor',
    'claim', 'Claim',
    'conjecture', 'Conjecture',
    'problem', 'Problem',
    'example', 'Example', 'exam', 'ex',
    'exercise', 'Exercise',
    'remark', 'Remark', 'rem',
    'note',
]

_excluded_env_pattern = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\}.*?\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if [start, end) falls entirely within an excluded environment."""
    for m in _excluded_env_pattern.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _build_excluded_mask(text: str) -> List[bool]:
    """Build a boolean mask: mask[i] == True means position i is inside an excluded env."""
    mask = [False] * len(text)
    for m in _excluded_env_pattern.finditer(text):
        for i in range(m.start(), min(m.end(), len(text))):
            mask[i] = True
    return mask


# ---------------------------------------------------------------------------
# Shared negative / referential filters
# ---------------------------------------------------------------------------

_NEGATIVE_FILTER = re.compile(
    r'\b(?:in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    flags=re.IGNORECASE,
)

_REFERENTIAL_FILTER = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    flags=re.IGNORECASE,
)

def _is_filtered(text: str) -> bool:
    return bool(_NEGATIVE_FILTER.search(text)) or bool(_REFERENTIAL_FILTER.search(text))


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# R1 – {\bf Term:} blocks  (bold-term-colon introduction)
# Catches: {\bf The $k$-nearest neighbor graph:} Here ...
# PRUNED — FP on paper001, paper002, paper003 +2 more | also 3 TP — review before uncommenting
# P_BF_TERM = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}:]{1,120}?)\s*:?\s*\}'
#     r':?\s*'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,1000}?)'
#     r'(?=\\\\\s*(?:\n|$)|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# R2 – \textbf{Term:} blocks
# PRUNED — FP on paper002, paper003, paper004 +1 more
# P_TEXTBF_TERM = re.compile(
#     r'(?P<full>'
#     r'\\textbf\{(?P<name>[^}:]{1,120}?)\s*:?\s*\}'
#     r':?\s*'
#     r'(?P<prose>(?:(?!\\textbf\{).){10,1000}?)'
#     r'(?=\\\\\s*(?:\n|$)|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# R3 – "are defined as" (plural complement to the base "is defined as")
# Two-phase: anchor then look-back/forward
P_ARE_DEFINED_AS_ANCHOR = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)

# R4 – "X (also called Y)" or "(also known as Y)" parenthetical definition
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# P_ALSO_CALLED = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,200}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,400}?\.)',
#     flags=re.DOTALL,
# )

# R5 – "X stands for ..."
P_STANDS_FOR = re.compile(
    r'(?P<full>'
    r'(?P<name>(?:\$[^$]{1,60}\$|[A-Za-z][A-Za-z0-9\\_{} ,.]{0,60}?))'
    r'\s+(?:stands\s+for|refers\s+to)\s+'
    r'(?:the\s+|a\s+|an\s+)?'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){1,400}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R6 – "Let X denote ..."
# PRUNED — FP on paper006 | also 1 TP — review before uncommenting
# P_LET_DENOTE = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]{1,60}\$|[A-Za-z0-9\\_{} ,.]{1,60}?))'
#     r'\s+denote\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){1,400}?\.)',
#     flags=re.DOTALL,
# )

# R7 – "We denote by X ..." / "Denote by X ..."
# PRUNED — FP on paper002, paper003, paper004
# P_DENOTE_BY = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]{1,60}\$|[A-Za-z0-9\\_{} ,.]{1,60}?))'
#     r'\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){1,400}?\.)',
#     flags=re.DOTALL,
# )

# R8 – "We will denote by X ..." / "We will write X for ..."
P_WILL_DENOTE_BY = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+will\s+denote\s+by\s+'
    r'(?P<name>(?:\$[^$]{1,60}\$|[A-Za-z0-9\\_{} ,.]{1,60}?))'
    r'\s+'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){1,400}?\.)',
    flags=re.DOTALL,
)

# R9 – "we write X for ..., namely ..."
P_WE_WRITE_FOR = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]{1,60}\$|[A-Za-z0-9\\_{} ,.]{1,60}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin\{|\\section\b|\\subsection\b).){1,300}?'
    r'\bnamely\b'
    r'(?:(?!\\begin\{|\\section\b|\\subsection\b).){0,600}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R10 – Imperative "Introduce X ..." or "Set X = ..." at sentence start
P_IMPERATIVE_INTRO = re.compile(
    r'(?P<full>'
    r'(?:(?<=\n)|(?<=\.\s)|^)\s*'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^.\$\\]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.]){0,400}?\.)',
    flags=re.DOTALL | re.MULTILINE,
)

# R11 – "we introduce ... call ... :" followed by display equation
P_INTRODUCE_CALL = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.]{1,200}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?call\s+'
    r'(?:\{\\it\s+|\{\\emph\{|\\textit\{|\\emph\{)?[^{}]{1,80}(?:\}\}?)?\s*:'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\s*\$\$.*?\$\$'
    r'|\s*\\\[.*?\\\])'
    r')',
    flags=re.DOTALL,
)

# R12 – "we (can) introduce X as $$ ... $$"
P_INTRODUCE_AS_DISPLAY = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'\s+as\s+'
    r'(?:[^$]|\$(?!\$)){0,200}?'
    r'(?P<math>\$\$.*?\$\$|\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})'
    r'(?:[^.]*\.)?'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R13 – "define X as/by/via \begin{equation}...\end{equation}"
P_DEFINE_WITH_EQN = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+(?:can\s+)?)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,150}?)'
    r'\s*(?:as|by|to\s+be|:=|=|via)\s*'
    r'(?:[^\\]|\\(?!begin)){0,200}?'
    r'(?P<envbody>\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R14 – "define [the] NAME \begin{equation}" (no explicit connector)
P_DEFINE_DIRECT_EQN = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+(?:can\s+)?)?define\s+'
    r'(?P<name>(?:the\s+)?[A-Za-z][^\\\n]{2,120}?)'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R15 – "X is given by \begin{equation}..."
P_IS_GIVEN_BY = re.compile(
    r'(?P<preamble>[^.!?\n]{0,250}?\b(?:is|are)\s+given\s+by\s*)'
    r'(?P<envbody>\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\})',
    flags=re.DOTALL,
)

# R16 – "A/An X is [property] if ... \begin{equation}..."
P_IS_PROPERTY_IF_EQN = re.compile(
    r'(?P<full>'
    r'(?:A|An)\s+'
    r'(?P<name>[A-Za-z][^.\n]{2,120}?)\s+is\s+[^.\n]{2,180}?\s+if\s+'
    r'[^.\n]{0,300}?'
    r'(?:\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})'
    r')',
    flags=re.DOTALL,
)

# R17 – emph/em term followed by semicolon then definitional clause
P_EMPH_SEMI = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,200}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.]{0,400}?'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R18 – "{\em term} obeys/satisfies ... if ..."
P_EMPH_OBEYS_IF = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.]{0,200}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{(?:equation|align)\*?\}.*?\\end\{(?:equation|align)\*?\}|[^.]){0,400}?'
    r'\bif\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{(?:equation|align)\*?\}.*?\\end\{(?:equation|align)\*?\}|[^.]){0,400}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R19 – paragraph after \section/\subsection containing emphasized term
# PRUNED — FP on paper005 | also 1 TP — review before uncommenting
# _SECTION_HEADING_PAT = re.compile(
#     r'\\(?:sub)*section\*?\{[^}]*\}',
#     flags=re.DOTALL,
# )
_EM_TERM_PAT = re.compile(
    r'(?:\{\\em\s+(?P<name>[^}]{2,80})\}|\\(?:emph|textit)\{(?P<name2>[^}]{2,80})\})',
)
_NEXT_BLOCK_PAT = re.compile(
    r'\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}',
)

# R20 – "we consider X ... and let Y denote ..."
P_WE_CONSIDER_LET_DENOTE = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+consider\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'[,.]\s*'
    r'(?:and\s+)?let\s+[^.]{1,120}?\s+denote\s+'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.]){0,400}?\.)',
    flags=re.DOTALL,
)

# Sentence boundary detector used by R15 look-back
_SENT_BOUNDARY_PAT = re.compile(r'[.!?]\s+|\n\s*\n', flags=re.DOTALL)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX text using supplementary rules
    that fill gaps not covered by the base _extract_definitions_manual method.
    Returns list of dicts with keys: raw_latex, clean_text, name, env_name,
    rule_name, structure_type.
    """
    results: List[dict] = []

    # Build excluded-env mask once
    excluded_mask = _build_excluded_mask(text)

    def _masked(start: int, end: int) -> bool:
        """True if any position in [start,end) is inside excluded env."""
        return any(excluded_mask[i] for i in range(max(0, start), min(end, len(excluded_mask))))

    def _extract_name(raw: str) -> str:
        if not raw:
            return ''
        raw = raw.strip()
        m = re.search(r'\$(.+?)\$', raw)
        if m:
            inner = m.group(1)
            inner = re.sub(r'\\[a-zA-Z]+\*?', '', inner)
            inner = re.sub(r'[{}^_]', '', inner)
            return inner.strip()[:80]
        t = re.sub(r'\\(?:emph|textit|textbf|texttt)\{([^}]*)\}', r'\1', raw)
        t = re.sub(r'\{\\(?:em|it|bf)\s+([^}]*)\}', r'\1', t)
        t = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', t)
        t = re.sub(r'[\\{}]', ' ', t)
        t = re.sub(r'\s+', ' ', t)
        return t.strip()[:80]

    def _add(raw_latex: str, name_raw: str, rule_name: str, start: int):
        if not raw_latex or len(raw_latex.strip()) < 15:
            return
        results.append({
            'raw_latex': raw_latex,
            'clean_text': _clean_latex(raw_latex),
            'name': _extract_name(name_raw) or None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_start': start,
            '_end': start + len(raw_latex),
        })

    # ------------------------------------------------------------------
    # R1 – {\bf Term:} blocks
#     # ------------------------------------------------------------------
#     for m in P_BF_TERM.finditer(text):
#         if _masked(m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _is_filtered(full):
#             continue
#         if len(full.strip()) < 20:
#             continue
#         _add(full, name, 'P_BF_TERM', m.start())

    # ------------------------------------------------------------------
    # R2 – \textbf{Term:} blocks
#     # ------------------------------------------------------------------
#     for m in P_TEXTBF_TERM.finditer(text):
#         if _masked(m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _is_filtered(full):
#             continue
#         if len(full.strip()) < 20:
#             continue
#         _add(full, name, 'P_TEXTBF_TERM', m.start())

    # ------------------------------------------------------------------
    # R3 – "are defined as" (plural)
    # Two-phase: look-back for name, look-forward for tail
    # ------------------------------------------------------------------
    _c2_tail = re.compile(
        r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{(?:equation|align|gather|multline)\*?\}.*?'
        r'\\end\{(?:equation|align|gather|multline)\*?\}|[^.])*\.',
        flags=re.DOTALL,
    )
    for anchor_m in P_ARE_DEFINED_AS_ANCHOR.finditer(text):
        if _masked(anchor_m.start(), anchor_m.end()):
            continue
        start_search = max(0, anchor_m.start() - 120)
        prefix = text[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        if dot_pos >= 0:
            name_start = start_search + dot_pos + 1
        else:
            name_start = start_search
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _c2_tail.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _is_filtered(full_text):
            continue
        _add(full_text, name_text, 'P_ARE_DEFINED_AS_ANCHOR', name_start)

    # ------------------------------------------------------------------
    # R4 – "(also called Y)" parenthetical
#     # ------------------------------------------------------------------
#     for m in P_ALSO_CALLED.finditer(text):
#         if _masked(m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _is_filtered(full):
#             continue
#         _add(full, name, 'P_ALSO_CALLED', m.start())

    # ------------------------------------------------------------------
    # R5 – "X stands for ..."
    # ------------------------------------------------------------------
    for m in P_STANDS_FOR.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        _add(full, name, 'P_STANDS_FOR', m.start())

    # ------------------------------------------------------------------
    # R6 – "Let X denote ..."
#     # ------------------------------------------------------------------
#     for m in P_LET_DENOTE.finditer(text):
#         if _masked(m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _is_filtered(full):
#             continue
#         _add(full, name, 'P_LET_DENOTE', m.start())

    # ------------------------------------------------------------------
    # R7 – "Denote by X ..." / "We denote by X ..."
#     # ------------------------------------------------------------------
#     for m in P_DENOTE_BY.finditer(text):
#         if _masked(m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _is_filtered(full):
#             continue
#         _add(full, name, 'P_DENOTE_BY', m.start())

    # ------------------------------------------------------------------
    # R8 – "We will denote by X ..."
    # ------------------------------------------------------------------
    for m in P_WILL_DENOTE_BY.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        _add(full, name, 'P_WILL_DENOTE_BY', m.start())

    # ------------------------------------------------------------------
    # R9 – "we write X for ..., namely ..."
    # ------------------------------------------------------------------
    for m in P_WE_WRITE_FOR.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        _add(full, name, 'P_WE_WRITE_FOR', m.start())

    # ------------------------------------------------------------------
    # R10 – Imperative "Introduce X ..." / "Set X = ..." at sentence start
    # ------------------------------------------------------------------
    for m in P_IMPERATIVE_INTRO.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        if len(full.strip()) < 20:
            continue
        _add(full, name, 'P_IMPERATIVE_INTRO', m.start())

    # ------------------------------------------------------------------
    # R11 – "we introduce ... call ... :" + display equation
    # ------------------------------------------------------------------
    for m in P_INTRODUCE_CALL.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        _add(full, name, 'P_INTRODUCE_CALL', m.start())

    # ------------------------------------------------------------------
    # R12 – "we (can) introduce X as $$ ... $$"
    # ------------------------------------------------------------------
    for m in P_INTRODUCE_AS_DISPLAY.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        _add(full, name, 'P_INTRODUCE_AS_DISPLAY', m.start())

    # ------------------------------------------------------------------
    # R13 – "define X as/by/via \begin{equation}..."
    # ------------------------------------------------------------------
    for m in P_DEFINE_WITH_EQN.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        if bool(re.search(
            r'\b(?:in\s+terms\s+of|as\s+(?:before|above|below)|defined\s+(?:above|below|earlier|previously))\b',
            full, re.IGNORECASE,
        )):
            continue
        _add(full, name, 'P_DEFINE_WITH_EQN', m.start())

    # ------------------------------------------------------------------
    # R14 – "define [the] NAME \begin{equation}" (no connector)
    # ------------------------------------------------------------------
    for m in P_DEFINE_DIRECT_EQN.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        if bool(re.search(
            r'\b(?:in\s+terms\s+of|as\s+(?:before|above|below)|defined\s+(?:above|below|earlier|previously))\b',
            full, re.IGNORECASE,
        )):
            continue
        _add(full, name, 'P_DEFINE_DIRECT_EQN', m.start())

    # ------------------------------------------------------------------
    # R15 – "X is given by \begin{equation}..."
    # Two-phase: anchor + look-back for sentence start
    # ------------------------------------------------------------------
    for m in P_IS_GIVEN_BY.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        preamble = m.group('preamble')
        envbody = m.group('envbody')
        # Find sentence start by looking back for sentence boundary
        sent_boundaries = list(_SENT_BOUNDARY_PAT.finditer(text, 0, m.start()))
        if sent_boundaries:
            sent_start = sent_boundaries[-1].end()
        else:
            sent_start = max(0, m.start() - 300)
        full_text = text[sent_start:m.end()].strip()
        if not full_text or len(full_text) < 20:
            continue
        if _is_filtered(full_text):
            continue
        # Extract name from emphasis in preamble
        emph_m = re.search(
            r'\\(?:emph|textbf|textit)\{([^}]+)\}|\{\\(?:em|bf|it)\s+([^}]+)\}',
            text[sent_start:m.start()],
        )
        name_raw = (emph_m.group(1) or emph_m.group(2)) if emph_m else text[sent_start:m.start()][-80:]
        _add(full_text, name_raw, 'P_IS_GIVEN_BY', sent_start)

    # ------------------------------------------------------------------
    # R16 – "A/An X is [property] if ... \begin{equation}..."
    # ------------------------------------------------------------------
    for m in P_IS_PROPERTY_IF_EQN.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        _add(full, name, 'P_IS_PROPERTY_IF_EQN', m.start())

    # ------------------------------------------------------------------
    # R17 – \emph{term} or {\em term} followed by semicolon + definitional clause
    # ------------------------------------------------------------------
    for m in P_EMPH_SEMI.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or m.group('name2') or ''
        # Must have definitional verb after the semicolon
        semi_pos = full.find(';')
        if semi_pos < 0:
            continue
        after_semi = full[semi_pos:]
        if not re.search(r'\b(?:is|are|was|were|means?|denotes?|represents?)\b',
                         after_semi, re.IGNORECASE):
            continue
        if _is_filtered(full):
            continue
        _add(full, name, 'P_EMPH_SEMI', m.start())

    # ------------------------------------------------------------------
    # R18 – "{\em term} obeys/satisfies ... if ..."
    # ------------------------------------------------------------------
    for m in P_EMPH_OBEYS_IF.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or m.group('name2') or ''
        if not name.strip():
            continue
        if _is_filtered(full):
            continue
        _add(full, name, 'P_EMPH_OBEYS_IF', m.start())

    # ------------------------------------------------------------------
    # R19 – paragraph after \section/\subsection containing emphasized term
#     # ------------------------------------------------------------------
#     for sec_m in _SECTION_HEADING_PAT.finditer(text):
#         para_start = sec_m.end()
#         nb = _NEXT_BLOCK_PAT.search(text, para_start)
#         para_end = nb.start() if nb else len(text)
#         para_text = text[para_start:para_end].strip()
#         if not para_text or len(para_text) < 60:
#             continue
#         if _masked(para_start, para_end):
#             continue
#         em_m = _EM_TERM_PAT.search(para_text)
#         if not em_m:
#             continue
#         name_raw = em_m.group('name') or em_m.group('name2') or ''
#         if _is_filtered(para_text):
#             continue
#         # Must look like a proper paragraph (not just math)
#         plain = re.sub(r'\$[^$]+\$', '', para_text)
#         plain = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', plain)
#         word_count = len(plain.split())
#         if word_count < 10:
#             continue
#         _add(para_text, name_raw, '_SECTION_HEADING_PAT', para_start)

    # ------------------------------------------------------------------
    # R20 – "we consider X ... and let Y denote ..."
    # ------------------------------------------------------------------
    for m in P_WE_CONSIDER_LET_DENOTE.finditer(text):
        if _masked(m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _is_filtered(full):
            continue
        _add(full, name, 'P_WE_CONSIDER_LET_DENOTE', m.start())

    # ------------------------------------------------------------------
    # Deduplication: remove overlapping results keeping longer match
    # ------------------------------------------------------------------
    results.sort(key=lambda x: (x['_start'], -len(x['raw_latex'])))
    deduped: List[dict] = []
    last_end = -1
    for r in results:
        start = r['_start']
        end = r['_end']
        if start < last_end:
            # Check overlap with the last kept item
            if deduped:
                prev = deduped[-1]
                prev_start = prev['_start']
                prev_end = prev['_end']
                overlap = min(end, prev_end) - max(start, prev_start)
                total = max(end, prev_end) - min(start, prev_start)
                if total > 0 and overlap / total > 0.5:
                    # Keep the longer one
                    if len(r['raw_latex']) > len(prev['raw_latex']):
                        deduped[-1] = r
                        last_end = end
                    continue
        deduped.append(r)
        last_end = end

    # Clean up internal keys
    for r in deduped:
        r.pop('_start', None)
        r.pop('_end', None)

    return deduped
