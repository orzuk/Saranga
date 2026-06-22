import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return plain text."""
    # Remove \begin{...}...\end{...} display environments
    text = re.sub(r'\\begin\{[^}]+\}.*?\\end\{[^}]+\}', ' ', text, flags=re.DOTALL)
    # Remove display math $$ ... $$
    text = re.sub(r'\$\$.*?\$\$', ' MATH ', text, flags=re.DOTALL)
    # Remove \[ ... \]
    text = re.sub(r'\\\[.*?\\\]', ' MATH ', text, flags=re.DOTALL)
    # Remove inline math $ ... $
    text = re.sub(r'\$[^$]+\$', ' MATH ', text)
    # Remove \emph{...}, \textit{...}, \textbf{...}, \text{...}
    text = re.sub(r'\\(?:emph|textit|textbf|texttt|text|mathrm|mathit|mathbf)\{([^}]*)\}', r'\1', text)
    # Remove {\em ...}, {\it ...}, {\bf ...}
    text = re.sub(r'\{\\(?:em|it|bf|rm|sc|tt)\s+([^}]*)\}', r'\1', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \citeA{...}
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove \section{...}, \subsection{...}, etc.
    text = re.sub(r'\\(?:sub)*section\*?\{[^}]*\}', '', text)
    # Remove remaining LaTeX commands \cmd
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\{[^}]*\})*', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments to exclude from inline pattern matching
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{('
    r'theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop|'
    r'corollary|Corollary|cor|claim|Claim|conjecture|Conjecture|'
    r'proof|Proof|algorithm|algorithm\*|algorithmic|algorithmics|algorithm2e|'
    r'verbatim|lstlisting|minted|figure|figure\*|table|table\*|'
    r'remark|Remark|example|Example|exercise|Exercise|problem|Problem'
    r')\}',
    flags=re.IGNORECASE,
)

_EXCLUDED_ENV_END = re.compile(
    r'\\end\{('
    r'theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop|'
    r'corollary|Corollary|cor|claim|Claim|conjecture|Conjecture|'
    r'proof|Proof|algorithm|algorithm\*|algorithmic|algorithmics|algorithm2e|'
    r'verbatim|lstlisting|minted|figure|figure\*|table|table\*|'
    r'remark|Remark|example|Example|exercise|Exercise|problem|Problem'
    r')\}',
    flags=re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) ranges that are inside excluded environments."""
    ranges = []
    for begin_m in _EXCLUDED_ENV_PATTERN.finditer(text):
        env_name = begin_m.group(1)
        end_pat = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\}',
            flags=re.IGNORECASE,
        )
        end_m = end_pat.search(text, begin_m.end())
        if end_m:
            ranges.append((begin_m.start(), end_m.end()))
    return ranges


def _inside_excluded_env(excluded_ranges, start: int, end: int) -> bool:
    """Return True if the interval [start, end) overlaps any excluded range."""
    for (rs, re_) in excluded_ranges:
        if start < re_ and end > rs:
            return True
    return False


# ---------------------------------------------------------------------------
# Negative / referential filters
# ---------------------------------------------------------------------------

_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|'
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
# Sentence boundary helper
# ---------------------------------------------------------------------------

_SENT_BOUNDARY = re.compile(r'[.!?]\s+|\n\s*\n', flags=re.DOTALL)
_STRUCTURAL_BOUNDARY = re.compile(
    r'\n\s*\n|\\section\b|\\subsection\b|\\begin\{|\\end\{document\}',
)


def _find_sentence_start(text: str, pos: int) -> int:
    """Find the start of the sentence containing position pos."""
    candidates = []
    for m in _SENT_BOUNDARY.finditer(text, 0, pos):
        candidates.append(m.end())
    if candidates:
        return candidates[-1]
    # Also check structural boundaries
    for m in re.finditer(r'\n\s*\n|\\section\b|\\subsection\b|\\begin\{', text[:pos]):
        candidates.append(m.end())
    if candidates:
        return max(candidates)
    return max(0, pos - 300)


# ---------------------------------------------------------------------------
# Pattern: C6 — {\bf Term:} or {\bf Term} definitional prose blocks
# ---------------------------------------------------------------------------

# PRUNED — FP on paper001, paper002, paper003 +4 more | also 4 TP — review before uncommenting
# BF_TERM_PATTERN = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}:]{1,100}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,1000}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern: C2 plural — 'are defined as/to be'
# ---------------------------------------------------------------------------

C2_ANCHOR_PLURAL = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)

C2_TAIL = re.compile(
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: C7 — (also called X) / (known as X) parenthetical definitions
# ---------------------------------------------------------------------------

# PRUNED — FP on paper001, paper010 | also 2 TP — review before uncommenting
# ALSO_CALLED_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,120}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,400}?\.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern: C5 emph+semi — '\emph{term}; ... is/are ...'
# ---------------------------------------------------------------------------

EMPH_SEMI_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,120}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.]{0,400}\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: denote by — 'We denote by X ...' / 'Denote by X ...'
# ---------------------------------------------------------------------------

# PRUNED — FP on paper002, paper003, paper004 +1 more | also 2 TP — review before uncommenting
# DENOTE_BY_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:will\s+)?|[Ll]et\s+us\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,\s]{1,60}?))'
#     r'\s+(?:the\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern: stands for / denotes / refers to
# ---------------------------------------------------------------------------

# PRUNED — FP on paper005, paper011
# STANDS_FOR_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z][A-Za-z0-9\\_{} ,.]{0,60}?))'
#     r'\s+(?:stands\s+for|refers\s+to)\s+'
#     r'(?:the\s+|a\s+|an\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern: let ... denote
# ---------------------------------------------------------------------------

# PRUNED — FP on paper004, paper006, paper008
# LET_DENOTE_PATTERN = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]+?))'
#     r'\s+denote\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern: imperative sentence — 'Introduce ...' / 'Set ...' at sentence start
# ---------------------------------------------------------------------------

IMPERATIVE_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=[.\n]))\s*'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^.\$\\]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    flags=re.DOTALL | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Pattern: we introduce ... call ... : equation
# ---------------------------------------------------------------------------

INTRODUCE_CALL_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?call\s+'
    r'(?:\{\\it\s+|\{\\emph\{|\\textit\{|\\emph\{)?[^{}]{1,80}(?:\}\}?)?\s*'
    r'(?::'
    r'(?:\s*\\begin\{(?:[a-zA-Z*]+)\}.*?\\end\{(?:[a-zA-Z*]+)\}|\s*\$\$.*?\$\$|\s*\\\[.*?\\\]))?'
    r')',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: is given by / is defined by + equation env
# ---------------------------------------------------------------------------

# PRUNED — FP on paper002, paper004 | also 1 TP — review before uncommenting
# IS_GIVEN_BY_PATTERN = re.compile(
#     r'(?P<preamble>[^.]{0,200}?\b(?:is\s+given|is\s+defined)\s+by\s*)'
#     r'(?P<body>\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\})',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern: define X + equation env (with connector or direct)
# ---------------------------------------------------------------------------

DEFINE_EQN_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:we\s+(?:can\s+)?)?define\s+'
    r'(?P<name>(?:the\s+)?[A-Za-z][^\\\n]{2,120}?)'
    r'\s*(?:as|by|to\s+be|:=|=|via)?\s*'
    r'(?:\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: 'A/An X is [property] if ... equation'
# ---------------------------------------------------------------------------

A_IS_IF_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:A|An)\s+'
    r'(?P<name>[A-Za-z][^.\n]{2,100}?)\s+is\s+[^.\n]{2,120}?\s+if\s+'
    r'[^.\n]{0,200}?'
    r'(?:\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}'
    r'|[^.]*\.)'
    r')',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: \emph{term} if/when <condition>
# ---------------------------------------------------------------------------

EMPH_IF_PATTERN = re.compile(
    r'(?P<full>'
    r'[A-Z][^.]{0,120}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'[^.]{0,200}?'
    r'\b(?:if|when|provided|whenever)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: \emph{term} (ABBR) + display math
# ---------------------------------------------------------------------------

EMPH_DISPLAY_PATTERN = re.compile(
    r'(?P<full>'
    r'[^\n.]{0,150}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'(?:\s*\([A-Z][A-Za-z0-9*]{0,10}\))?'
    r'\s*'
    r'(?:'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:align|equation|gather|multline|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|multline|eqnarray)\*?\}'
    r')'
    r')',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: 'The <noun> is [given by/defined as] display-math'
# ---------------------------------------------------------------------------

# PRUNED — FP on paper002, paper004, paper008 | also 1 TP — review before uncommenting
# NOUN_DISPLAY_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:Given[^,]{0,100},\s*)?'
#     r'(?:the|The)\s+'
#     r'(?P<name>[A-Za-z][^$\\]{1,80}?)'
#     r'\s+is(?:\s+(?:given\s+by|defined\s+as|defined\s+by))?\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|multline|eqnarray)\*?\}'
#     r')'
#     r')',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern: display math + where clause (defines named quantity)
# ---------------------------------------------------------------------------

# PRUNED — FP on paper004, paper006, paper009 +1 more | also 3 TP — review before uncommenting
# DISPLAY_WHERE_PATTERN = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,200}?'
#     r'(?P<name>'
#     r'(?:the\s+)?[a-z][a-z\s]{2,60}?'
#     r'(?:norm|measure|metric|distance|kernel|cost|function|map|operator|'
#     r'space|matrix|bound|rate|set|distribution|density|estimator|'
#     r'criterion|objective|loss|risk|error|penalty)'
#     r')'
#     r'[^$\\]{0,30}?'
#     r'[:\s]'
#     r'\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|multline|eqnarray)\*?\}'
#     r')'
#     r'[^.]{0,300}?'
#     r'\bwhere\b'
#     r'[^.]{0,200}?\.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Pattern: we write X for Y, namely ...
# ---------------------------------------------------------------------------

WE_WRITE_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9_\\(),.\s]{1,60}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin|\\section|\\subsection).){1,400}?'
    r'(?:'
    r'\bnamely\b(?:(?!\\begin|\\section|\\subsection).){0,600}?\.'
    r'|\.)'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: we (can) introduce X as $$ ... $$
# ---------------------------------------------------------------------------

INTRODUCE_AS_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.]{1,80}?)'
    r'\s+as\s+'
    r'(?:[^$]|\$(?!\$))*?'
    r'(?P<math>\$\$.*?\$\$)'
    r'(?:[^.]*\.)?'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern: section/subsection heading followed by paragraph with {\em ...}
# ---------------------------------------------------------------------------

_SECTION_HEADING = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*\}',
    flags=re.DOTALL,
)

_EM_TERM = re.compile(
    r'(?:\{\\em\s+(?P<name>[^}]{2,80})\}|\\textit\{(?P<name2>[^}]{2,80})\})',
)

_NEXT_BLOCK = re.compile(
    r'\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}',
)

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX source that are NOT already
    captured by the base _extract_definitions_manual method.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # Build excluded ranges once
    excluded_ranges = _build_excluded_ranges(text)

    def _skip(start: int, end: int, full_text: str) -> bool:
        if _inside_excluded_env(excluded_ranges, start, end):
            return True
        if _REFERENTIAL.search(full_text):
            return True
        return False

    def _make_result(raw: str, name_raw, rule_name: str, start: int) -> dict:
        name_hint = _extract_name_hint(name_raw or '')
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name_hint or None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_source_pos': start,
        }

    def _extract_name_hint(raw: str) -> str:
        raw = raw.strip()
        # prefer math content
        m = re.search(r'\$(.+?)\$', raw)
        if m:
            inner = m.group(1)
            inner = re.sub(r'\\[a-zA-Z]+\*?', '', inner)
            return inner.strip()[:80]
        # strip latex commands
        cleaned = _clean_latex(raw)
        return cleaned.strip()[:80]

    # -----------------------------------------------------------------------
    # BF_TERM_PATTERN: {\bf Term:} definitional blocks
#     # -----------------------------------------------------------------------
#     for m in BF_TERM_PATTERN.finditer(text):
#         full_text = m.group('full')
#         if _skip(m.start(), m.end(), full_text):
#             continue
#         name_raw = m.group('name') or ''
#         if len(name_raw.strip()) < 1:
#             continue
#         results.append(_make_result(full_text, name_raw, 'BF_TERM_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # C2_ANCHOR_PLURAL: 'are defined as/to be'
    # -----------------------------------------------------------------------
    for anchor_m in C2_ANCHOR_PLURAL.finditer(text):
        if _inside_excluded_env(excluded_ranges, anchor_m.start(), anchor_m.end()):
            continue
        start_search = max(0, anchor_m.start() - 80)
        prefix = text[start_search:anchor_m.start()]
        # Find best sentence boundary
        cuts = [prefix.rfind('.')]
        for mk in ('\n\n', '\\section', '\\subsection', '\\maketitle',
                   '\\begin', '\\end', '\\item', '\\par', '}'):
            p = prefix.rfind(mk)
            if p >= 0:
                cuts.append(p + len(mk) - 1)
        best = max(cuts)
        name_start = start_search + (best + 1 if best >= 0 else 0)
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 80:
            continue
        tail_m = C2_TAIL.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        results.append(_make_result(full_text, name_text, 'C2_ANCHOR_PLURAL', name_start))

    # -----------------------------------------------------------------------
    # ALSO_CALLED_PATTERN: (also called X) / (known as X)
#     # -----------------------------------------------------------------------
#     for m in ALSO_CALLED_PATTERN.finditer(text):
#         full_text = m.group('full')
#         if _skip(m.start(), m.end(), full_text):
#             continue
#         name_raw = m.group('name') or ''
#         if len(name_raw.strip()) < 2:
#             continue
#         results.append(_make_result(full_text, name_raw, 'ALSO_CALLED_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # EMPH_SEMI_PATTERN: \emph{term}; ... is/are ...
    # -----------------------------------------------------------------------
    for m in EMPH_SEMI_PATTERN.finditer(text):
        full_text = m.group('full')
        if _skip(m.start(), m.end(), full_text):
            continue
        semi_pos = full_text.find(';')
        if semi_pos < 0:
            continue
        after_semi = full_text[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        name_raw = m.group('name') or m.group('name2') or ''
        results.append(_make_result(full_text, name_raw, 'EMPH_SEMI_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # DENOTE_BY_PATTERN: 'We denote by X ...' / 'Denote by X ...'
#     # -----------------------------------------------------------------------
#     for m in DENOTE_BY_PATTERN.finditer(text):
#         full_text = m.group('full')
#         if _skip(m.start(), m.end(), full_text):
#             continue
#         if _C1_NEGATIVE.search(full_text):
#             continue
#         name_raw = m.group('name') or ''
#         results.append(_make_result(full_text, name_raw, 'DENOTE_BY_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # STANDS_FOR_PATTERN: 'X stands for ...' / 'X refers to ...'
#     # -----------------------------------------------------------------------
#     for m in STANDS_FOR_PATTERN.finditer(text):
#         full_text = m.group('full')
#         if _skip(m.start(), m.end(), full_text):
#             continue
#         name_raw = m.group('name') or ''
#         results.append(_make_result(full_text, name_raw, 'STANDS_FOR_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # LET_DENOTE_PATTERN: 'Let X denote ...'
#     # -----------------------------------------------------------------------
#     for m in LET_DENOTE_PATTERN.finditer(text):
#         full_text = m.group('full')
#         if _skip(m.start(), m.end(), full_text):
#             continue
#         if _REFERENTIAL.search(full_text):
#             continue
#         name_raw = m.group('name') or ''
#         results.append(_make_result(full_text, name_raw, 'LET_DENOTE_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # IMPERATIVE_PATTERN: 'Introduce ...' / 'Set ...' at sentence start
    # -----------------------------------------------------------------------
    for m in IMPERATIVE_PATTERN.finditer(text):
        full_text = m.group('full').strip()
        if not full_text:
            continue
        start = text.find(full_text, max(0, m.start() - 2))
        if start < 0:
            start = m.start()
        if _skip(start, start + len(full_text), full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group('name') or ''
        results.append(_make_result(full_text, name_raw, 'IMPERATIVE_PATTERN', start))

    # -----------------------------------------------------------------------
    # INTRODUCE_CALL_PATTERN: 'we introduce ... call ... : equation'
    # -----------------------------------------------------------------------
    for m in INTRODUCE_CALL_PATTERN.finditer(text):
        full_text = m.group('full')
        if not full_text or len(full_text) < 20:
            continue
        if _skip(m.start(), m.end(), full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group('name') or ''
        results.append(_make_result(full_text, name_raw, 'INTRODUCE_CALL_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # IS_GIVEN_BY_PATTERN: 'X is given/defined by \begin{equation}...'
#     # -----------------------------------------------------------------------
#     for m in IS_GIVEN_BY_PATTERN.finditer(text):
#         body = m.group('body')
#         # find sentence start
#         sent_start = _find_sentence_start(text, m.start())
#         full_text = text[sent_start: m.end()].strip()
#         if not full_text:
#             continue
#         if _skip(sent_start, m.end(), full_text):
#             continue
#         if _REFERENTIAL.search(full_text):
#             continue
#         # extract name hint from emphasis in preamble
#         name_raw = text[sent_start: m.start()].strip()
#         emph_m = re.search(
#             r'\\(?:emph|textbf|textit)\{([^}]+)\}|\{\\em\s+([^}]+)\}',
#             name_raw,
#         )
#         if emph_m:
#             name_raw = emph_m.group(1) or emph_m.group(2) or name_raw
#         results.append(_make_result(full_text, name_raw, 'IS_GIVEN_BY_PATTERN', sent_start))

    # -----------------------------------------------------------------------
    # DEFINE_EQN_PATTERN: 'define X [as/by] \begin{equation}...'
    # -----------------------------------------------------------------------
    for m in DEFINE_EQN_PATTERN.finditer(text):
        full_text = m.group('full')
        if _skip(m.start(), m.end(), full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group('name') or ''
        results.append(_make_result(full_text, name_raw, 'DEFINE_EQN_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # A_IS_IF_PATTERN: 'A X is [property] if ... equation'
    # -----------------------------------------------------------------------
    for m in A_IS_IF_PATTERN.finditer(text):
        full_text = m.group('full')
        if _skip(m.start(), m.end(), full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group('name') or ''
        if len(name_raw.strip()) < 3:
            continue
        results.append(_make_result(full_text, name_raw, 'A_IS_IF_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # EMPH_IF_PATTERN: '\emph{property} if <condition>'
    # -----------------------------------------------------------------------
    for m in EMPH_IF_PATTERN.finditer(text):
        full_text = m.group('full')
        if _skip(m.start(), m.end(), full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group('name') or ''
        if len(name_raw.strip()) < 3:
            continue
        results.append(_make_result(full_text, name_raw, 'EMPH_IF_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # EMPH_DISPLAY_PATTERN: '\emph{term} (ABBR) display-math'
    # -----------------------------------------------------------------------
    for m in EMPH_DISPLAY_PATTERN.finditer(text):
        full_text = m.group('full')
        if _skip(m.start(), m.end(), full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group('name') or ''
        if len(name_raw.strip()) < 3:
            continue
        results.append(_make_result(full_text, name_raw, 'EMPH_DISPLAY_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # NOUN_DISPLAY_PATTERN: 'The <noun> is [given by] display-math'
    # -----------------------------------------------------------------------
    _NOUN_GENERIC = re.compile(
        r'^(?:following|above|below|result|fact|situation|case|observation|'
        r'key|main|new|same|standard|usual|natural|general|simple|'
        r'latter|former)$',
        re.IGNORECASE,
    )
#     for m in NOUN_DISPLAY_PATTERN.finditer(text):
#         full_text = m.group('full')
#         if _skip(m.start(), m.end(), full_text):
#             continue
#         if _REFERENTIAL.search(full_text):
#             continue
#         name_raw = m.group('name') or ''
#         name_stripped = name_raw.strip()
#         if len(name_stripped) < 3 or len(name_stripped) > 80:
#             continue
#         if _NOUN_GENERIC.match(name_stripped):
#             continue
#         results.append(_make_result(full_text, name_raw, 'NOUN_DISPLAY_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # DISPLAY_WHERE_PATTERN: display math + where clause
#     # -----------------------------------------------------------------------
#     for m in DISPLAY_WHERE_PATTERN.finditer(text):
#         full_text = m.group('full')
#         if _skip(m.start(), m.end(), full_text):
#             continue
#         if _REFERENTIAL.search(full_text):
#             continue
#         name_raw = m.group('name') or ''
#         if len(name_raw.strip()) < 3:
#             continue
#         results.append(_make_result(full_text, name_raw, 'DISPLAY_WHERE_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # WE_WRITE_PATTERN: 'we write X for Y, namely ...'
    # -----------------------------------------------------------------------
    for m in WE_WRITE_PATTERN.finditer(text):
        full_text = m.group('full')
        if _skip(m.start(), m.end(), full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group('name') or ''
        results.append(_make_result(full_text, name_raw, 'WE_WRITE_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # INTRODUCE_AS_PATTERN: 'we (can) introduce X as $$ ... $$'
    # -----------------------------------------------------------------------
    for m in INTRODUCE_AS_PATTERN.finditer(text):
        full_text = m.group('full')
        if _skip(m.start(), m.end(), full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group('name') or ''
        results.append(_make_result(full_text, name_raw, 'INTRODUCE_AS_PATTERN', m.start()))

    # -----------------------------------------------------------------------
    # Section + emphasized term pattern (C5 from Rule 1)
    # -----------------------------------------------------------------------
    for sec_m in _SECTION_HEADING.finditer(text):
        para_start = sec_m.end()
        nb = _NEXT_BLOCK.search(text, para_start)
        para_end = nb.start() if nb else min(len(text), para_start + 2000)
        para_text = text[para_start:para_end].strip()
        if not para_text or len(para_text) < 40:
            continue
        if _inside_excluded_env(excluded_ranges, para_start, para_end):
            continue
        em_m = _EM_TERM.search(para_text)
        if not em_m:
            continue
        name_raw = em_m.group('name') or em_m.group('name2') or ''
        if not name_raw.strip():
            continue
        if _REFERENTIAL.search(para_text):
            continue
        results.append(_make_result(para_text, name_raw, '_SECTION_HEADING', para_start))

    # -----------------------------------------------------------------------
    # Deduplication: remove overlapping matches, prefer longer/earlier
    # -----------------------------------------------------------------------
    results.sort(key=lambda r: (r['_source_pos'], -len(r['raw_latex'])))

    deduped: List[dict] = []
    used_ranges: List[tuple] = []

    for r in results:
        pos = r['_source_pos']
        end = pos + len(r['raw_latex'])
        # Check overlap with already-kept results
        overlap = False
        for (us, ue) in used_ranges:
            if pos < ue and end > us:
                # Overlapping — keep if this one is substantially larger
                # (otherwise skip)
                overlap = True
                break
        if not overlap:
            used_ranges.append((pos, end))
            deduped.append(r)

    # Remove internal _source_pos key before returning
    for r in deduped:
        r.pop('_source_pos', None)

    for r in deduped:
        r.pop('_start', None)

    return deduped
