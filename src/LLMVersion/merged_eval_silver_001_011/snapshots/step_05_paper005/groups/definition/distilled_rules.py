import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Minimal LaTeX -> plain text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their argument
    text = re.sub(r'\\(?:text(?:bf|it|rm|sf|tt|sc)|emph|mathrm|mathbf|mathit|mathbb|mathcal|math)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|it|rm|sf|tt|em)\s+([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:textbf|textit|emph)\{([^}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite, \eqref etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*|citeA|citeN)\{[^}]*\}', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|gather|eqnarray|multline)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray|multline)\*?\}', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove \ba...\ea style (common shorthand)
    text = re.sub(r'\\ba\b.*?\\ea\b', ' [MATH] ', text, flags=re.DOTALL)
    # Inline math: keep content
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*', ' ', text)
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments to exclude (proof, theorem, lemma, etc.)
_EXCLUDED_ENV_NAMES = [
    'proof', 'theorem', 'thm', 'lemma', 'lem', 'proposition', 'prop',
    'corollary', 'cor', 'claim', 'conjecture', 'example', 'exam', 'ex',
    'exercise', 'remark', 'rem', 'note',
]
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(' + '|'.join(re.escape(e) for e in _EXCLUDED_ENV_NAMES) + r')\}.*?\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)

def _build_excluded_ranges(text: str):
    """Return list of (start, end) ranges that are inside excluded environments."""
    ranges = []
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if the span [start, end) overlaps any excluded range."""
    for (es, ee) in excluded_ranges:
        if start < ee and end > es:
            return True
    return False


def _normalize_name(raw: str) -> str:
    """Extract a readable name hint from raw LaTeX."""
    raw = raw.strip()
    # Prefer inline math content
    m = re.search(r'\$(.+?)\$', raw)
    if m:
        inner = m.group(1)
        inner = re.sub(r'\\[a-zA-Z]+\*?', '', inner)
        inner = re.sub(r'[{}]', '', inner)
        inner = inner.strip()
        if inner:
            return inner[:80]
    # Strip LaTeX markup
    cleaned = _clean_latex(raw)
    cleaned = cleaned.strip()
    if cleaned:
        return cleaned[:80]
    return raw[:80]


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove overlapping matches; prefer longer/earlier matches."""
    if not results:
        return results
    # Sort by start position, then by length descending
    results_with_pos = []
    for r in results:
        rl = r.get('_start', 0)
        rlen = len(r.get('raw_latex', ''))
        results_with_pos.append((rl, -rlen, r))
    results_with_pos.sort(key=lambda x: (x[0], x[1]))

    kept = []
    kept_spans = []  # list of (start, end)
    for (start, neg_len, r) in results_with_pos:
        end = start + (-neg_len)
        # Check overlap with already-kept spans
        overlap = False
        for (ks, ke) in kept_spans:
            # Overlap if they share more than 20% of the smaller span
            overlap_len = max(0, min(end, ke) - max(start, ks))
            smaller = min(end - start, ke - ks)
            if smaller > 0 and overlap_len / smaller > 0.3:
                overlap = True
                break
        if not overlap:
            kept.append(r)
            kept_spans.append((start, end))
    return kept


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# R1: \section/\subsection paragraph definitions
# Captures first substantial paragraph after a section header that contains
# definitional keywords.
# PRUNED — FP on paper001, paper002, paper003 +1 more | also 3 TP — review before uncommenting
# R1_SECTION_PARAGRAPH = re.compile(
#     r'(?:\\(?:sub)*section\*?\{[^}]*\})'
#     r'(?:\s*(?:%[^\n]*)?\n)*'
#     r'\s*'
#     r'(?P<full>(?:[^\n]|\n(?!\s*\n)){60,2000}?)'
#     r'(?=\n\s*\n|\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

_R1_KEYWORDS = re.compile(
    r'\b(define[sd]?|definition|denote[sd]?|notation|call(?:ed)?|'
    r'known\s+as|represent[s]?|form\s+of\s+the|similarity\s+graph|'
    r'connected\s+component|partition)\b',
    flags=re.IGNORECASE,
)

# R2: "X is called Y" definitional sentences
# Two-phase: find anchor, then look back for subject and forward for sentence end
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# R2_IS_CALLED_ANCHOR = re.compile(
#     r'\bis\s+called\b',
#     flags=re.IGNORECASE,
# )

R2_SENTENCE_END = re.compile(
    r'(?:[^.]|\.[^A-Z\s])*\.',
    flags=re.DOTALL,
)

# R3: {\bf Name:} or \textbf{Name:} bold-labeled definition blocks
# PRUNED — FP on paper001, paper002, paper003 +1 more | also 3 TP — review before uncommenting
# R3_BF_LABEL = re.compile(
#     r'(?P<full>'
#     r'(?:\{\\bf\s+|\{\\textbf\s+|\\textbf\{)'
#     r'(?P<name>[^}:]{1,120}?)'
#     r'(?:\}:?|:?\})'
#     r'(?:\s*\\\\)?\s*'
#     r'(?P<body>(?:[^\n]|\n(?!\s*\n)){30,1200}?)'
#     r')'
#     r'(?=\n\s*\n|\{\\bf\b|\{\\textbf\b|\\textbf\{|\\\\[ \t]*\n\s*\n|'
#     r'\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

# R4: "are defined as" extended (C2 extension for plural subjects)
R4_ARE_DEFINED_ANCHOR = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)

# R5: "We (will) denote by X ..." style inline definition
# PRUNED — FP on paper003, paper004 | also 1 TP — review before uncommenting
# R5_DENOTE_BY = re.compile(
#     r'(?P<full>'
#     r'(?:We\s+)?(?:will\s+)?(?:also\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|\$\$[^$]+\$\$|[A-Za-z0-9\\{}_^ ]{1,60}))'
#     r'(?:[^.]|\.[^A-Z\n])*?\.)',
#     flags=re.DOTALL,
# )

# R6: "X obeys/satisfies PROPERTY if ..." with \emph or {\em term
R6_OBEYS = re.compile(
    r'(?P<full>'
    r'(?:a\s+)?(?:\\emph\{(?P<emph_name>[^}]+)\}|\{\\em\s+(?P<em_name>[^}]+)\})'
    r'[^.]{0,200}?'
    r'\bobeys\b'
    r'(?:[^.]|\.[^A-Z\n])*?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R7: "The notation X stands for ..."
R7_STANDS_FOR = re.compile(
    r'(?P<full>'
    r'(?:The\s+notation\s+)?'
    r'(?P<name>(?:\$[^$]+\$|\$\$[^$]+\$\$|\\?\w[\w\\{}^_]{0,60}))'
    r'\s+stands\s+for\b'
    r'(?:[^.]|\.[^A-Z\n])*?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R8: "Let $...$ denote ..." or "Let $...$$ denote ..."
R8_LET_DENOTE = re.compile(
    r'(?P<full>'
    r'[Ll]et\s+'
    r'(?P<name>(?:\$\$[^$]*\$\$|\$[^$]+\$))'
    r'(?:[^.\\]|\\[^b]|\\b(?!egin)){0,300}?'
    r'\bdenote\b'
    r'(?:[^.]|\.[^A-Z\n])*?\.)',
    flags=re.DOTALL,
)

# R9: "Introduce X ..." imperative definitional sentence with display math
R9_INTRODUCE = re.compile(
    r'(?P<full>'
    r'\bIntroduce\b\s+'
    r'(?P<name>[^.$\n\\]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{equation\*?\}.*?\\end\{equation\*?\})'
    r'(?:[^.\\]|\\[^e]|\\e(?!nd)){0,300}?'
    r'\.)',
    flags=re.DOTALL,
)

# R10: "we consider <name> $$...$$, and let X denote ..."
R10_WE_CONSIDER = re.compile(
    r'(?P<full>'
    r'\bwe\s+consider\b\s+'
    r'(?P<name>[^.$\n\\]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{equation\*?\}.*?\\end\{equation\*?\})'
    r'(?:[^.\\]|\\[^e]|\\e(?!nd)){0,400}?'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R11: "we introduce ... called <name>: \begin{equation*}...\end{equation*}"
R11_INTRODUCE_CALLED = re.compile(
    r'(?P<full>'
    r'\bwe\s+introduce\b[^.\\]{0,200}?'
    r'call(?:ed)?\s+'
    r'(?:\{\\it\s+)?(?:\{\\em\s+)?(?P<name>[^}.\n\\]{1,80})(?:\}){0,2}\s*:?\s*'
    r'(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\\begin\{eqnarray\*?\}.*?\\end\{eqnarray\*?\}'
    r'|\\\[.*?\\\]'
    r'|\$\$.*?\$\$))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R12: "Denote by X ... (called <name>) ... \begin{equation*}...\end{equation*}"
R12_DENOTE_BY_EQ = re.compile(
    r'(?P<full>'
    r'\bDenote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ]{1,60}))'
    r'[^\\]{0,400}?'
    r'(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R13: "We define X as/by ... \begin{gather*}...\end{gather*}" (or other envs)
R13_DEFINE_ENV = re.compile(
    r'(?P<full>'
    r'(?:We\s+)?(?:also\s+)?[Dd]efine\s+'
    r'(?P<name>[^.\\]{1,80}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?:\\begin\{[^}]{1,30}\}.*?\\end\{[^}]{1,30}\}))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R14: "introduce X as/by $$...$$" or "introduce ... as \begin{...}...\end{...}"
R14_INTRODUCE_AS = re.compile(
    r'(?P<full>'
    r'\bintroduce\b\s+'
    r'(?P<name>[^.\\]{1,80}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{[^}]{1,30}\}.*?\\end\{[^}]{1,30}\}))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R15: "the set \begin{equation} <name> = ... \end{equation} is non-empty"
R15_SET_EQUATION = re.compile(
    r'(?P<full>'
    r'\bthe\s+set\b[^\\]{0,150}?'
    r'\\begin\{equation[^}]*\}\s*'
    r'(?P<name>\\?[A-Za-z][A-Za-z0-9_{}^\\]*\s*=)'
    r'.*?'
    r'\\end\{equation[^}]*\})',
    flags=re.IGNORECASE | re.DOTALL,
)

# R16: "X $$ ... $$ denote ..." with "Set" keyword intro
# "Set $$ ... $$" as definitional (paper004 style)
# PRUNED — FP on paper004
# R16_SET_DISPLAY = re.compile(
#     r'(?P<full>'
#     r'(?:^|\n)\s*[Ss]et\s*\n?'
#     r'\$\$\s*'
#     r'(?P<name>[A-Za-z\\][A-Za-z0-9\\{}_^, =\s]{0,80}?)'
#     r'(?==|\$)'
#     r'.*?'
#     r'\$\$'
#     r'(?:[^.]|\.[^A-Z\n]){0,200}?'
#     r'\.)',
#     flags=re.DOTALL,
# )

# R17: "By the concavity of ... we can introduce the convex set X ... as $$...$$"
# More general: introduce ... as $$ ... $$
R17_INTRODUCE_CONVEX = re.compile(
    r'(?P<full>'
    r'\bintroduce\b[^.\\]{0,100}?'
    r'(?:\\emph\{(?P<name>[^}]+)\}|\{\\em\s+(?P<name2>[^}]+)\}|(?P<name3>[A-Z_\\$][^.\\]{0,60}?))'
    r'\s+as\s*\n?'
    r'\$\$.*?\$\$'
    r'(?:[^.\\]|\\[^e]|\\e(?!nd)){0,300}?)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R18: Lines starting with "These definitions are equivalent" / "These definitions..."
# captures the equivalence note for definitions introduced just above
# (not adding this as it would be too broad)

# R19: \subsection paragraph: 'There are two matrices ... defined as'
# This is caught by R4 extension, but also add a special subsection+display pattern
R19_SUBSECTION_DEF = re.compile(
    r'(?:\\(?:sub)+section\*?\{[^}]*\})'
    r'(?:\s*(?:%[^\n]*)?\n)*'
    r'\s*'
    r'(?P<full>'
    r'(?:[^\n]|\n(?!\s*\n)){30,2500}?'
    r'(?:defined?\s+as|are\s+defined|we\s+denote)'
    r'(?:[^\n]|\n(?!\s*\n)){10,1000}?'
    r')'
    r'(?=\n\s*\n|\\(?:sub)*section|\\begin\{(?:proposition|theorem|lemma|proof|corollary)|\\end\{document\})',
    flags=re.DOTALL | re.IGNORECASE,
)

# Referential language (skip)
_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    flags=re.IGNORECASE,
)

# Negative C1 patterns
_C1_NEGATIVE = re.compile(
    r'\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    flags=re.IGNORECASE,
)

# R1 definitional keywords
_R1_DEF_KEYWORDS = re.compile(
    r'\b(define[sd]?|definition|denote[sd]?|notation|call(?:ed)?|'
    r'known\s+as|represent[s]?|form\s+of\s+the|stands?\s+for|'
    r'refer(?:s)?\s+to|mean[s]?\s+that|we\s+say)\b',
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

    def _make_result(raw: str, name_raw: str, rule_name: str, start: int) -> dict:
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': _normalize_name(name_raw) if name_raw else None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_start': start,
        }

    # -----------------------------------------------------------------------
    # R1: Section/subsection paragraph definitions
#     # -----------------------------------------------------------------------
#     for m in R1_SECTION_PARAGRAPH.finditer(text):
#         start = m.start()
#         full = m.group('full').strip()
#         end = start + len(full)
#         if _inside_excluded_env(start, end, excluded_ranges):
#             continue
#         if not _R1_DEF_KEYWORDS.search(full):
#             continue
#         if _REFERENTIAL.search(full[:200]):
#             continue
#         # Name hint: first sentence up to 80 chars
#         first_sent = re.split(r'\.', full)[0][:80]
#         results.append(_make_result(full, first_sent, 'R1_SECTION_PARAGRAPH', start))

    # -----------------------------------------------------------------------
    # R2: "X is called Y" definitional sentences
#     # -----------------------------------------------------------------------
#     for anchor_m in R2_IS_CALLED_ANCHOR.finditer(text):
#         anchor_start = anchor_m.start()
#         # Look back up to 200 chars for sentence start
#         look_back = max(0, anchor_start - 200)
#         prefix = text[look_back:anchor_start]
#         # Find last period or paragraph break
#         dot_pos = max(prefix.rfind('.'), prefix.rfind('\n\n'))
#         if dot_pos >= 0:
#             name_start = look_back + dot_pos + 1
#         else:
#             name_start = look_back
#         name_text = text[name_start:anchor_start].strip()
#         if not name_text or len(name_text) > 200:
#             continue
#         # Find sentence end after anchor
#         search_from = anchor_m.end()
#         search_region = text[search_from:search_from + 600]
#         end_m = re.search(r'\.(?:\s|$)', search_region, flags=re.DOTALL)
#         if not end_m:
#             continue
#         full_end = search_from + end_m.end()
#         full_text = text[name_start:full_end]
#         if len(full_text) < 20 or len(full_text) > 1500:
#             continue
#         if _inside_excluded_env(name_start, full_end, excluded_ranges):
#             continue
#         if _REFERENTIAL.search(full_text):
#             continue
#         results.append(_make_result(full_text, name_text, 'R2_IS_CALLED_ANCHOR', name_start))

    # -----------------------------------------------------------------------
    # R3: {\bf Name:} bold-labeled definition blocks
#     # -----------------------------------------------------------------------
#     for m in R3_BF_LABEL.finditer(text):
#         start = m.start()
#         full = m.group('full').strip()
#         name_raw = m.group('name').strip()
#         end = start + len(full)
#         if _inside_excluded_env(start, end, excluded_ranges):
#             continue
#         if len(full) < 20:
#             continue
#         if _REFERENTIAL.search(full[:150]):
#             continue
#         results.append(_make_result(full, name_raw, 'R3_BF_LABEL', start))

    # -----------------------------------------------------------------------
    # R4: "are defined as" extended anchor
    # -----------------------------------------------------------------------
    for anchor_m in R4_ARE_DEFINED_ANCHOR.finditer(text):
        anchor_start = anchor_m.start()
        # Look back for subject
        look_back = max(0, anchor_start - 200)
        prefix = text[look_back:anchor_start]
        dot_pos = max(prefix.rfind('.'), prefix.rfind('\n\n'))
        if dot_pos >= 0:
            name_start = look_back + dot_pos + 1
        else:
            name_start = look_back
        name_text = text[name_start:anchor_start].strip()
        if not name_text or len(name_text) > 200:
            continue
        # Find sentence/block end: handle display math and equation environments
        search_from = anchor_m.end()
        search_region = text[search_from:search_from + 1500]
        # Try to find end after display math or sentence period
        end_m = re.search(
            r'(?:\\end\{(?:align|equation|gather|eqnarray)\*?\}|'
            r'\\ea\b|\\\]|\$\$)'
            r'[^.]*\.',
            search_region, flags=re.DOTALL
        )
        if not end_m:
            end_m = re.search(r'\.(?:\s+[A-Z]|\s*\n)', search_region, flags=re.DOTALL)
        if not end_m:
            continue
        full_end = search_from + end_m.end()
        full_text = text[name_start:full_end]
        if len(full_text) < 20 or len(full_text) > 2000:
            continue
        if _inside_excluded_env(name_start, full_end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full_text[:200]):
            continue
        results.append(_make_result(full_text, name_text, 'R4_ARE_DEFINED_ANCHOR', name_start))

    # -----------------------------------------------------------------------
    # R5: "We (will) denote by X ..."
#     # -----------------------------------------------------------------------
#     for m in R5_DENOTE_BY.finditer(text):
#         start = m.start()
#         full = m.group('full')
#         name_raw = m.group('name')
#         end = start + len(full)
#         if _inside_excluded_env(start, end, excluded_ranges):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         results.append(_make_result(full, name_raw, 'R5_DENOTE_BY', start))

    # -----------------------------------------------------------------------
    # R6: "\emph{term} ... obeys ..."
    # -----------------------------------------------------------------------
    for m in R6_OBEYS.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('emph_name') or m.group('em_name') or ''
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R6_OBEYS', start))

    # -----------------------------------------------------------------------
    # R7: "X stands for ..."
    # -----------------------------------------------------------------------
    for m in R7_STANDS_FOR.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R7_STANDS_FOR', start))

    # -----------------------------------------------------------------------
    # R8: "Let $...$ denote ..."
    # -----------------------------------------------------------------------
    for m in R8_LET_DENOTE.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R8_LET_DENOTE', start))

    # -----------------------------------------------------------------------
    # R9: "Introduce X \begin{equation}...\end{equation}"
    # -----------------------------------------------------------------------
    for m in R9_INTRODUCE.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R9_INTRODUCE', start))

    # -----------------------------------------------------------------------
    # R10: "we consider <name> $$...$$"
    # -----------------------------------------------------------------------
    for m in R10_WE_CONSIDER.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R10_WE_CONSIDER', start))

    # -----------------------------------------------------------------------
    # R11: "we introduce ... called <name>: \begin{equation*}...\end{equation*}"
    # -----------------------------------------------------------------------
    for m in R11_INTRODUCE_CALLED.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R11_INTRODUCE_CALLED', start))

    # -----------------------------------------------------------------------
    # R12: "Denote by X ... \begin{equation*}...\end{equation*}"
    # -----------------------------------------------------------------------
    for m in R12_DENOTE_BY_EQ.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R12_DENOTE_BY_EQ', start))

    # -----------------------------------------------------------------------
    # R13: "We define X as ... \begin{gather*}...\end{gather*}"
    # -----------------------------------------------------------------------
    for m in R13_DEFINE_ENV.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R13_DEFINE_ENV', start))

    # -----------------------------------------------------------------------
    # R14: "introduce X as $$...$$"
    # -----------------------------------------------------------------------
    for m in R14_INTRODUCE_AS.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R14_INTRODUCE_AS', start))

    # -----------------------------------------------------------------------
    # R15: "the set \begin{equation} <name> = ... \end{equation}"
    # -----------------------------------------------------------------------
    for m in R15_SET_EQUATION.finditer(text):
        start = m.start()
        full = m.group('full')
        name_raw = m.group('name')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name_raw, 'R15_SET_EQUATION', start))

    # -----------------------------------------------------------------------
    # R16: "Set $$ ... $$" display math definitional
#     # -----------------------------------------------------------------------
#     for m in R16_SET_DISPLAY.finditer(text):
#         start = m.start()
#         full = m.group('full').strip()
#         name_raw = m.group('name') if m.group('name') else ''
#         end = start + len(full)
#         if _inside_excluded_env(start, end, excluded_ranges):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if len(full) < 20:
#             continue
#         results.append(_make_result(full, name_raw, 'R16_SET_DISPLAY', start))

    # -----------------------------------------------------------------------
    # R17: "introduce ... as $$...$$" with convex/set context
    # -----------------------------------------------------------------------
    for m in R17_INTRODUCE_CONVEX.finditer(text):
        start = m.start()
        full = m.group('full').strip()
        # Extract name from named groups
        name_raw = (m.group('name') or m.group('name2') or m.group('name3') or '')
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full):
            continue
        if len(full) < 20:
            continue
        results.append(_make_result(full, name_raw, 'R17_INTRODUCE_CONVEX', start))

    # -----------------------------------------------------------------------
    # R19: Subsection-level "defined as / are defined / we denote" paragraphs
    # -----------------------------------------------------------------------
    for m in R19_SUBSECTION_DEF.finditer(text):
        start = m.start()
        full = m.group('full').strip()
        end = start + len(full)
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _REFERENTIAL.search(full[:200]):
            continue
        first_sent = re.split(r'\.', full)[0][:80]
        results.append(_make_result(full, first_sent, 'R19_SUBSECTION_DEF', start))

    # -----------------------------------------------------------------------
    # Deduplicate and clean up internal keys
    # -----------------------------------------------------------------------
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)

    return results
