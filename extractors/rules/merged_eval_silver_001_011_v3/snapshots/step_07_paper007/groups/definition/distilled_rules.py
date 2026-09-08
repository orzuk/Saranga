import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and return plain-ish text."""
    # Remove comments
    t = re.sub(r'%[^\n]*', ' ', text)
    # Remove display math environments
    t = re.sub(r'\\begin\{[^}]+\}.*?\\end\{[^}]+\}', ' [MATH] ', t, flags=re.DOTALL)
    # Remove $$ ... $$
    t = re.sub(r'\$\$.*?\$\$', ' [MATH] ', t, flags=re.DOTALL)
    # Remove \[ ... \]
    t = re.sub(r'\\\[.*?\\\]', ' [MATH] ', t, flags=re.DOTALL)
    # Remove inline $ ... $
    t = re.sub(r'\$[^$]*\$', '[MATH]', t)
    # Remove \emph{...}, \textbf{...}, \textit{...}, \text{...}
    t = re.sub(r'\\(?:emph|textbf|textit|texttt|text|mathrm)\{([^}]*)\}', r'\1', t)
    # Remove {\em ...}, {\bf ...}, {\it ...}
    t = re.sub(r'\{\\(?:em|bf|it|tt)\s+([^}]*)\}', r'\1', t)
    # Remove remaining \command{...}
    t = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', t)
    # Remove remaining \command
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    # Remove remaining braces
    t = re.sub(r'[{}]', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


# Environments to exclude (proof, theorem-like, example, etc.)
_EXCLUDED_ENVS = [
    'proof', 'Proof',
    'theorem', 'Theorem', 'thm',
    'lemma', 'Lemma', 'lem',
    'proposition', 'Proposition', 'prop',
    'corollary', 'Corollary', 'cor',
    'claim', 'Claim',
    'conjecture', 'Conjecture',
    'example', 'Example', 'exam',
    'exercise', 'Exercise',
    'remark', 'Remark', 'rem',
    'note',
]

_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENVS)) + r')\}(.*?)\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) ranges that are inside excluded environments."""
    ranges = []
    for m in _EXCLUDED_ENV_RE.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if [start, end) overlaps any excluded range."""
    for rs, re_ in excluded_ranges:
        if start < re_ and end > rs:
            return True
    return False


def _extract_name_from_emphasis(text: str) -> str:
    """Try to extract a concept name from \emph{}, {\em }, \textbf{}, {\bf } markup."""
    m = re.search(
        r'\\(?:emph|textbf|textit)\{([^}]{1,80})\}'
        r'|\{\\(?:em|bf|it)\s+([^}]{1,80})\}',
        text
    )
    if m:
        return (m.group(1) or m.group(2) or '').strip()
    return ''


def _normalize_name(raw: str, max_len: int = 80) -> str:
    """Strip LaTeX and whitespace from a candidate name string."""
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', raw)
    t = re.sub(r'[{}$]', '', t)
    t = re.sub(r'\s+', ' ', t)
    t = t.strip()
    return t[:max_len]


# ---------------------------------------------------------------------------
# Sentence-boundary helper
# ---------------------------------------------------------------------------

_SENT_BOUNDARY = re.compile(r'[.!?]\s+|\n\s*\n', flags=re.DOTALL)


def _sentence_start_before(text: str, pos: int) -> int:
    """Return the character index of the start of the sentence containing pos."""
    candidates = list(_SENT_BOUNDARY.finditer(text, 0, pos))
    if candidates:
        return candidates[-1].end()
    return max(0, pos - 300)


# ---------------------------------------------------------------------------
# Referential / negative guards (do not fire on back-references)
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
# Display-math sub-pattern (reusable component)
# ---------------------------------------------------------------------------

_DISPLAY_MATH = (
    r'(?:'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather|multline|eqnarray)[*]?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)[*]?\}'
    r')'
)

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# ------------------------------------------------------------------
# Rule C6_BF_TERM: {\bf Term:} or {\bf Term} followed by definitional prose
# Catches "{\bf The $\eps$-neighborhood graph:} Here we connect ..."
# ------------------------------------------------------------------
# PRUNED — FP on paper001, paper002, paper003 +2 more | also 4 TP — review before uncommenting
# C6_BF_TERM = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}:]{1,120}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,1000}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C7_ALSO_CALLED: '(also called ALIAS)' or '(known as ALIAS)' parenthetical
# ------------------------------------------------------------------
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# C7_ALSO_CALLED = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,200}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,300}?\.)',
#     flags=re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C2_PLURAL_DEFINED_AS: 'are defined as/to be'
# ------------------------------------------------------------------
C2_PLURAL_DEFINED_AS = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)

# tail for C2 plural (same as base C2)
_C2_TAIL = re.compile(
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.',
    flags=re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C5_EMPH_SEMI: '\emph{term}; ... is/are ...'
# Catches 'a \emph{linear code}; a linear code is ...'
# ------------------------------------------------------------------
C5_EMPH_SEMI = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,200}?;\s*'
    r'[^.]{1,400}?'
    r'\b(?:is|are)\b[^.]{0,300}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C6_DENOTE_BY: 'We (will) denote by X ...' or 'Denote by X ...'
# ------------------------------------------------------------------
# PRUNED — FP on paper002, paper003, paper004 +1 more | also 1 TP — review before uncommenting
# C6_DENOTE_BY = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:will\s+)?|[Ll]et\s+us\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,.!\s]{1,80}?))'
#     r'\s+(?:the\s+|a\s+|an\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){0,600}?\.)',
#     flags=re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C7_OBEYS_IF: '{\em term} obeys/satisfies ... if ...'
# ------------------------------------------------------------------
C7_OBEYS_IF = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.]{0,200}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{equation[*]?\}.*?\\end\{equation[*]?\}|[^.]){0,600}?'
    r'\bif\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{equation[*]?\}.*?\\end\{equation[*]?\}|[^.]){0,400}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C5_STANDS_FOR: 'X stands for ...', 'X denotes ...'
# ------------------------------------------------------------------
# PRUNED — FP on paper001, paper003, paper005 +1 more | also 2 TP — review before uncommenting
# C5_STANDS_FOR = re.compile(
#     r'(?P<full>'
#     r'(?P<name>(?:The\s+notation\s+)?(?:\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})?|[A-Za-z0-9\\_{} ,.]{1,60}?))'
#     r'\s+(?:stands\s+for|denotes|refers\s+to)\s+'
#     r'(?:the\s+|a\s+|an\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){1,600}?\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C6_LET_DENOTE: 'Let X denote ...'
# ------------------------------------------------------------------
# PRUNED — FP on paper006 | also 1 TP — review before uncommenting
# C6_LET_DENOTE = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]+\$|\{[^}]{1,40}\}|[A-Za-z0-9\\_{} ,.]{1,60}?))'
#     r'\s+denote\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){1,600}?\.)',
#     flags=re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C7_IMPERATIVE: 'Introduce ...' or 'Set ...' at paragraph/sentence start
# ------------------------------------------------------------------
C7_IMPERATIVE = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=[.\n]))\s*'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^.\$\\]{1,100}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.]){0,600}?\.)',
    flags=re.DOTALL | re.MULTILINE,
)

# ------------------------------------------------------------------
# Rule C9_INTRODUCE_CALL: 'we introduce ... (that we will) call {\it NAME}:'
# ------------------------------------------------------------------
C9_INTRODUCE_CALL = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.]{1,150}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?call\s+'
    r'(?:\{\\it\s+|\{\\emph\{|\\textit\{|\\emph\{)?[^{}]{1,80}(?:\}\}?)?\s*'
    r'(?::'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)[*]?\}.*?\\end\{(?:equation|align|gather|multline)[*]?\}'
    r'|\s*\$\$.*?\$\$|\s*\\\[.*?\\\])'
    r'|\.)'
    r')',
    flags=re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C1B_DEFINE_ENV: 'We define X as/by \begin{env}...\end{env}'
# Handles definition bodies that ARE a display environment
# ------------------------------------------------------------------
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# C1B_DEFINE_ENV = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
#     r'(?P<name>[^.\\]{1,120}?)'
#     r'\s*(?:as|by|to\s+be|:=|=|via)\s*'
#     r'(?:[^\\]|\\(?!begin)){0,100}?'
#     r'(?P<envbody>\\begin\{(?P<envn>[a-zA-Z*]+)\}.*?\\end\{(?P=envn)\})'
#     r')',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C6_INTRODUCE_AS: 'we (can) introduce X as $$ ... $$'
# ------------------------------------------------------------------
C6_INTRODUCE_AS = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.]{1,100}?)'
    r'\s+as\s+'
    r'(?:[^$\\]|\$(?!\$)|\\(?!begin)){0,100}?'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{(?:equation|align|gather|multline)[*]?\}.*?\\end\{(?:equation|align|gather|multline)[*]?\})'
    r'(?:[^.]*\.)?'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C5_IS_GIVEN_BY: 'X is given by \begin{equation}...\end{equation}'
# ------------------------------------------------------------------
# PRUNED — FP on paper002, paper004 | also 1 TP — review before uncommenting
# C5_IS_GIVEN_BY = re.compile(
#     r'(?P<preamble>[^.]{0,300}?\b(?:is\s+given|is\s+defined)\s+by\s*)'
#     r'(?P<body>'
#     r'\\begin\{(?:equation|align|gather|multline|eqnarray)[*]?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)[*]?\}'
#     r')',
#     flags=re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C1C_DEFINE_DIRECT: 'define the NAME \begin{equation}' (no explicit connector)
# ------------------------------------------------------------------
C1C_DEFINE_DIRECT = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+(?:can\s+)?)?define\s+'
    r'(?P<name>(?:the\s+)?[A-Za-z][^\\\n]{2,120}?)'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)[*]?\}.*?\\end\{(?:equation|align|gather|multline)[*]?\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C6_A_IS_IF: 'A/An NAME is [property] if ... \begin{equation}...'
# ------------------------------------------------------------------
C6_A_IS_IF = re.compile(
    r'(?P<full>'
    r'(?:A|An)\s+'
    r'(?P<name>[A-Za-z][^.\n]{2,120}?)\s+is\s+[^.\n]{2,200}?\s+if\s+'
    r'[^.\n]{0,400}?'
    r'(?:\\begin\{(?:equation|align|gather|multline)[*]?\}.*?\\end\{(?:equation|align|gather|multline)[*]?\})'
    r')',
    flags=re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C5_EMPH_IF: '\emph{property} if <condition>.'
# ------------------------------------------------------------------
# PRUNED — FP on paper002, paper005 | also 1 TP — review before uncommenting
# C5_EMPH_IF = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.]{0,200}?'
#     r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
#     r'[^.]{0,300}?'
#     r'\b(?:if|when|provided|whenever)\b'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){0,400}?\.)',
#     flags=re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C6_EMPH_DISPLAY: '\emph{name} (ABBR) followed by display math
# ------------------------------------------------------------------
C6_EMPH_DISPLAY = re.compile(
    r'(?P<full>'
    r'[^\n.]{0,200}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'(?:\s*\([A-Z][A-Za-z0-9*]{0,10}\))?'
    r'\s*'
    r'(?:'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:align|equation|gather|multline)[*]?\}.*?\\end\{(?:align|equation|gather|multline)[*]?\}'
    r')'
    r')',
    flags=re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C7_NOUN_DISPLAY: 'the <noun phrase> is\n$$...$$'
# ------------------------------------------------------------------
C7_NOUN_DISPLAY = re.compile(
    r'(?P<full>'
    r'(?:Given[^,]{0,200},\s*)?'
    r'(?:the|The)\s+'
    r'(?P<name>[A-Za-z][^$\\]{1,80}?)'
    r'\s+is(?:\s+(?:given\s+by|defined\s+as|defined\s+by))?\s*'
    r'(?:'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:align|equation|gather|multline)[*]?\}.*?\\end\{(?:align|equation|gather|multline)[*]?\}'
    r')'
    r')',
    flags=re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C8_DISPLAY_WHERE: '<noun ending in math-type word>: $$...$$ where ...'
# ------------------------------------------------------------------
# PRUNED — FP on paper004, paper006 | also 1 TP — review before uncommenting
# C8_DISPLAY_WHERE = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,300}?'
#     r'(?P<name>'
#     r'(?:the\s+)?[a-z][a-z\s]{2,60}?'
#     r'(?:norm|measure|metric|distance|kernel|cost|function|map|operator|'
#     r'space|matrix|bound|rate|set|quantity|polytope|table)'
#     r')'
#     r'[^$\\]{0,50}?'
#     r'[:\s]\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline)[*]?\}.*?\\end\{(?:align|equation|gather|multline)[*]?\}'
#     r')'
#     r'[^.]{0,400}?'
#     r'\bwhere\b'
#     r'[^.]{0,300}?\.)',
#     flags=re.DOTALL,
# )

# ------------------------------------------------------------------
# Rule C5_SECTION_EM: paragraph after \section/\subsection containing {\em ...}
# (handled procedurally below, no single top-level regex)
# ------------------------------------------------------------------
_SECTION_HEADING = re.compile(
    r'\\(?:(?:sub){0,2}section)\*?\{[^}]*\}',
    flags=re.DOTALL,
)
_EM_TERM = re.compile(
    r'(?:\{\\em\s+(?P<name>[^}]{2,80})\}|\\(?:textit|emph)\{(?P<name2>[^}]{2,80})\})',
)
_NEXT_BLOCK = re.compile(
    r'\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}',
)

# ------------------------------------------------------------------
# Rule C_WE_WRITE: 'we write X for Y, namely ...'
# ------------------------------------------------------------------
C_WE_WRITE = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9_\\(),.\s]{1,80}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin|\\section|\\subsection).){1,400}?'
    r'\bnamely\b'
    r'(?:(?!\\begin|\\section|\\subsection).){0,800}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C_WE_CONSIDER_LET: 'we consider ... let X denote ...'
# ------------------------------------------------------------------
C_WE_CONSIDER_LET = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+consider\s+'
    r'(?P<name>[^.]{1,100}?)'
    r'\s*[.,]\s*'
    r'(?:and\s+)?let\s+[^.]{1,100}?\s+denote\s+'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.]){0,600}?\.)',
    flags=re.DOTALL,
)

# ------------------------------------------------------------------
# Rule C2B_THAT_IS_ASSUME: 'That is, we assume that ... \begin{equation}...'
# ------------------------------------------------------------------
C2B_THAT_IS_ASSUME = re.compile(
    r'(?P<full>'
    r'(?P<name>[^.\n]{1,200}?)'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)[^{}]{1,100}(?:\}\}?)\s+(?:property|condition)[^.]*\.\s*'
    r'(?:That\s+is[,.]?\s*)?[Ww]e\s+assume\s+that\s+'
    r'(?:[^.]*\.\s*){0,3}?'
    r'\\begin\{equation[*]?\}.*?\\end\{equation[*]?\}'
    r'[^.]*\.)',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Priority map for deduplication
# ---------------------------------------------------------------------------

_SOURCE_PRIORITY = {
    # Lower number = higher priority (keep this one over others)
    'C6_BF_TERM': 1,
    'C5_EMPH_SEMI': 2,
    'C6_DENOTE_BY': 2,
    'C7_OBEYS_IF': 2,
    'C5_STANDS_FOR': 2,
    'C6_LET_DENOTE': 2,
    'C9_INTRODUCE_CALL': 2,
    'C5_IS_GIVEN_BY': 2,
    'C1C_DEFINE_DIRECT': 2,
    'C6_A_IS_IF': 2,
    'C5_EMPH_IF': 2,
    'C7_ALSO_CALLED': 3,
    'C1B_DEFINE_ENV': 3,
    'C6_INTRODUCE_AS': 3,
    'C7_IMPERATIVE': 3,
    'C5_EMPH_SECTION': 3,
    'C_WE_WRITE': 3,
    'C_WE_CONSIDER_LET': 3,
    'C2B_THAT_IS_ASSUME': 3,
    'C6_EMPH_DISPLAY': 3,
    'C7_NOUN_DISPLAY': 3,
    'C8_DISPLAY_WHERE': 4,
    'C2_PLURAL_DEFINED_AS': 2,
}

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract additional definition structures from LaTeX text.
    Complements the base _extract_definitions_manual method.
    Returns list of dicts with keys: raw_latex, clean_text, name,
    env_name, rule_name, structure_type.
    """
    results: List[dict] = []
    excluded_ranges = _build_excluded_ranges(text)

    def _guard(start: int, end: int, full_text: str) -> bool:
        """Return True if this match should be skipped."""
        if _inside_excluded_env(start, end, excluded_ranges):
            return True
        if _REFERENTIAL.search(full_text):
            return True
        return False

    def _add(raw: str, name: str, rule_name: str, source_pos: int):
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': _normalize_name(name)[:80] if name else None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_source_pos': source_pos,
        })

    # ------------------------------------------------------------------
    # C6_BF_TERM: {\bf Term:} followed by definitional prose
#     # ------------------------------------------------------------------
#     for m in C6_BF_TERM.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _guard(m.start(), m.end(), full):
#             continue
#         if not name_raw.strip():
#             continue
#         _add(full, name_raw, 'C6_BF_TERM', m.start())

    # ------------------------------------------------------------------
    # C7_ALSO_CALLED: '(also called X)' or '(known as X)'
#     # ------------------------------------------------------------------
#     for m in C7_ALSO_CALLED.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _guard(m.start(), m.end(), full):
#             continue
#         if len(name_raw.strip()) < 2:
#             continue
#         _add(full, name_raw, 'C7_ALSO_CALLED', m.start())

    # ------------------------------------------------------------------
    # C2_PLURAL_DEFINED_AS: 'are defined as/to be' (two-phase)
    # ------------------------------------------------------------------
    for anchor_m in C2_PLURAL_DEFINED_AS.finditer(text):
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
        tail_m = _C2_TAIL.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _guard(name_start, tail_m.end(), full_text):
            continue
        _add(full_text, name_text, 'C2_PLURAL_DEFINED_AS', name_start)

    # ------------------------------------------------------------------
    # C5_EMPH_SEMI: '\emph{term}; ... is/are ...'
    # ------------------------------------------------------------------
    for m in C5_EMPH_SEMI.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or m.group('name2') or ''
        semi_pos = full.find(';')
        if semi_pos < 0:
            continue
        after_semi = full[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        if _guard(m.start(), m.end(), full):
            continue
        _add(full, name_raw, 'C5_EMPH_SEMI', m.start())

    # ------------------------------------------------------------------
    # C6_DENOTE_BY: 'We (will) denote by X ...' or 'Denote by X ...'
#     # ------------------------------------------------------------------
#     for m in C6_DENOTE_BY.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _guard(m.start(), m.end(), full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         _add(full, name_raw, 'C6_DENOTE_BY', m.start())

    # ------------------------------------------------------------------
    # C7_OBEYS_IF: '\emph{term} obeys/satisfies ... if ...'
    # ------------------------------------------------------------------
    for m in C7_OBEYS_IF.finditer(text):
        full = m.group('full')
        name_raw = (m.group('name') or m.group('name2') or '').strip()
        if not name_raw:
            continue
        if _guard(m.start(), m.end(), full):
            continue
        _add(full, name_raw, 'C7_OBEYS_IF', m.start())

    # ------------------------------------------------------------------
    # C5_STANDS_FOR: 'X stands for ...' / 'X denotes ...'
#     # ------------------------------------------------------------------
#     for m in C5_STANDS_FOR.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _guard(m.start(), m.end(), full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         _add(full, name_raw, 'C5_STANDS_FOR', m.start())

    # ------------------------------------------------------------------
    # C6_LET_DENOTE: 'Let X denote ...'
#     # ------------------------------------------------------------------
#     for m in C6_LET_DENOTE.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _guard(m.start(), m.end(), full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'C6_LET_DENOTE', m.start())

    # ------------------------------------------------------------------
    # C7_IMPERATIVE: 'Introduce ...' or 'Set ...' at sentence start
    # ------------------------------------------------------------------
    for m in C7_IMPERATIVE.finditer(text):
        full = m.group('full').strip()
        name_raw = m.group('name') or ''
        if _guard(m.start(), m.end(), full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'C7_IMPERATIVE', m.start())

    # ------------------------------------------------------------------
    # C9_INTRODUCE_CALL: 'we introduce ... call {\it NAME}:'
    # ------------------------------------------------------------------
    for m in C9_INTRODUCE_CALL.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _guard(m.start(), m.end(), full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'C9_INTRODUCE_CALL', m.start())

    # ------------------------------------------------------------------
    # C1B_DEFINE_ENV: 'We define X as/by \begin{env}...\end{env}'
#     # ------------------------------------------------------------------
#     for m in C1B_DEFINE_ENV.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _guard(m.start(), m.end(), full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'C1B_DEFINE_ENV', m.start())

    # ------------------------------------------------------------------
    # C6_INTRODUCE_AS: 'we (can) introduce X as $$ ... $$'
    # ------------------------------------------------------------------
    for m in C6_INTRODUCE_AS.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _guard(m.start(), m.end(), full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'C6_INTRODUCE_AS', m.start())

    # ------------------------------------------------------------------
    # C5_IS_GIVEN_BY: 'X is given by \begin{equation}...\end{equation}'
    # (two-phase: find anchor, then look back for sentence start)
#     # ------------------------------------------------------------------
#     for m in C5_IS_GIVEN_BY.finditer(text):
#         body = m.group('body')
#         preamble_end = m.start('body')
#         sent_start = _sentence_start_before(text, m.start('preamble') + 10)
#         full_text = text[sent_start:m.end()].strip()
#         if _guard(sent_start, m.end(), full_text):
#             continue
#         # Extract name from emphasis in preamble
#         preamble_text = text[sent_start:preamble_end]
#         name_hint = _extract_name_from_emphasis(preamble_text)
#         if not name_hint:
#             name_hint = _normalize_name(preamble_text[-80:])
#         _add(full_text, name_hint, 'C5_IS_GIVEN_BY', sent_start)

    # ------------------------------------------------------------------
    # C1C_DEFINE_DIRECT: 'define the NAME \begin{equation}' no explicit connector
    # ------------------------------------------------------------------
    for m in C1C_DEFINE_DIRECT.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _guard(m.start(), m.end(), full):
            continue
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'C1C_DEFINE_DIRECT', m.start())

    # ------------------------------------------------------------------
    # C6_A_IS_IF: 'A/An NAME is [property] if ... \begin{equation}...'
    # ------------------------------------------------------------------
    for m in C6_A_IS_IF.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _guard(m.start(), m.end(), full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'C6_A_IS_IF', m.start())

    # ------------------------------------------------------------------
    # C5_EMPH_IF: '\emph{property name} if <condition>.'
#     # ------------------------------------------------------------------
#     for m in C5_EMPH_IF.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if len(name_raw.strip()) < 3:
#             continue
#         if _guard(m.start(), m.end(), full):
#             continue
#         _add(full, name_raw, 'C5_EMPH_IF', m.start())

    # ------------------------------------------------------------------
    # C6_EMPH_DISPLAY: '\emph{name} (ABBR) followed by display math
    # ------------------------------------------------------------------
    for m in C6_EMPH_DISPLAY.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if len(name_raw.strip()) < 3:
            continue
        if _guard(m.start(), m.end(), full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'C6_EMPH_DISPLAY', m.start())

    # ------------------------------------------------------------------
    # C7_NOUN_DISPLAY: 'the <noun phrase> is $$...$$'
    # ------------------------------------------------------------------
    _GENERIC_NAMES = re.compile(
        r'^(?:following|above|below|result|fact|situation|case|problem|'
        r'equation|proof|theorem|lemma|proposition|corollary)$',
        re.IGNORECASE
    )
    for m in C7_NOUN_DISPLAY.finditer(text):
        full = m.group('full')
        name_raw = (m.group('name') or '').strip()
        if not name_raw or len(name_raw) < 3 or len(name_raw) > 100:
            continue
        if _GENERIC_NAMES.match(name_raw):
            continue
        if _guard(m.start(), m.end(), full):
            continue
        _add(full, name_raw, 'C7_NOUN_DISPLAY', m.start())

    # ------------------------------------------------------------------
    # C8_DISPLAY_WHERE: '<math-type noun>: $$...$$ where ...'
#     # ------------------------------------------------------------------
#     for m in C8_DISPLAY_WHERE.finditer(text):
#         full = m.group('full')
#         name_raw = (m.group('name') or '').strip()
#         if not name_raw or len(name_raw) < 3:
#             continue
#         if _guard(m.start(), m.end(), full):
#             continue
#         _add(full, name_raw, 'C8_DISPLAY_WHERE', m.start())

    # ------------------------------------------------------------------
    # C5_EMPH_SECTION: paragraph after \section/\subsection containing {\em ...}
    # (procedural two-pass)
    # ------------------------------------------------------------------
    for sec_m in _SECTION_HEADING.finditer(text):
        para_start = sec_m.end()
        nb = _NEXT_BLOCK.search(text, para_start)
        para_end = nb.start() if nb else min(len(text), para_start + 2000)
        para_text = text[para_start:para_end].strip()
        if not para_text or len(para_text) < 40:
            continue
        em_m = _EM_TERM.search(para_text)
        if not em_m:
            continue
        if _inside_excluded_env(para_start, para_end, excluded_ranges):
            continue
        if _REFERENTIAL.search(para_text):
            continue
        name_hint = (em_m.group('name') or em_m.group('name2') or '').strip()
        _add(para_text, name_hint, 'C5_EMPH_SECTION', para_start)

    # ------------------------------------------------------------------
    # C_WE_WRITE: 'we write X for Y, namely ...'
    # ------------------------------------------------------------------
    for m in C_WE_WRITE.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _guard(m.start(), m.end(), full):
            continue
        _add(full, name_raw, 'C_WE_WRITE', m.start())

    # ------------------------------------------------------------------
    # C_WE_CONSIDER_LET: 'we consider ... let X denote ...'
    # ------------------------------------------------------------------
    for m in C_WE_CONSIDER_LET.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _guard(m.start(), m.end(), full):
            continue
        _add(full, name_raw, 'C_WE_CONSIDER_LET', m.start())

    # ------------------------------------------------------------------
    # C2B_THAT_IS_ASSUME: '<property> property ... we assume that ... \begin{equation}'
    # ------------------------------------------------------------------
    for m in C2B_THAT_IS_ASSUME.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _guard(m.start(), m.end(), full):
            continue
        _add(full, name_raw, 'C2B_THAT_IS_ASSUME', m.start())

    # ------------------------------------------------------------------
    # Deduplication: remove overlapping matches, keep highest-priority
    # ------------------------------------------------------------------
    if not results:
        return results

    # Sort by priority (ascending = higher priority), then by source position
    def _priority(r: dict) -> int:
        return _SOURCE_PRIORITY.get(r['rule_name'], 5)

    results.sort(key=lambda r: (_priority(r), r['_source_pos']))

    deduped: List[dict] = []
    seen_texts: List[str] = []
    seen_ranges: List[tuple] = []

    for r in results:
        raw = r['raw_latex']
        ct = _clean_latex(raw).lower().strip()
        pos = r['_source_pos']
        end_pos = pos + len(raw)

        # Check positional overlap
        overlaps = False
        for (s, e) in seen_ranges:
            if pos < e and end_pos > s:
                overlaps = True
                break

        if overlaps:
            continue

        # Check textual overlap
        is_dup = False
        for prev_ct in seen_texts:
            if not prev_ct:
                continue
            if ct in prev_ct or prev_ct in ct:
                is_dup = True
                break
            min_len = min(len(ct), len(prev_ct))
            if min_len > 30 and ct[:30] == prev_ct[:30]:
                is_dup = True
                break

        if not is_dup:
            deduped.append(r)
            seen_texts.append(ct)
            seen_ranges.append((pos, end_pos))

    # Remove internal _source_pos from output
    for r in deduped:
        r.pop('_source_pos', None)

    for r in deduped:
        r.pop('_start', None)

    return deduped
