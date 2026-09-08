import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX markup to produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...} etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*|pageref)\{[^}]*\}', '', text)
    # Unwrap \emph{}, \textbf{}, \textit{}, \text{}, \mathrm{} etc.
    text = re.sub(r'\\(?:emph|textbf|textit|texttt|textrm|text|mathrm|mathbf|mathit|mathcal|mathbb|mathsf|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove {\em ...}, {\bf ...}, {\it ...}
    text = re.sub(r'\{\\(?:em|bf|it|rm|tt|sc)\s+([^}]*)\}', r'\1', text)
    # Remove \begin{...} / \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math environments markers
    text = re.sub(r'\\(?:ba|ea|bb|ee)\b', '', text)
    # Convert \\ to space
    text = re.sub(r'\\\\', ' ', text)
    # Remove remaining commands with optional args
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments to exclude (proofs, theorems, etc. — definitions already handled by base)
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|'
    r'proposition|Proposition|prop|corollary|Corollary|cor|'
    r'claim|Claim|conjecture|Conjecture|remark|Remark|rem|'
    r'example|Example|exam|exercise|Exercise|'
    r'algorithm|algorithm\*|table|figure|figure\*|'
    r'definition|Definition|defn|dfn|Def|Defn)\}',
    re.IGNORECASE,
)

_EXCLUDED_ENV_FULL = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|'
    r'proposition|Proposition|prop|corollary|Corollary|cor|'
    r'claim|Claim|conjecture|Conjecture|remark|Remark|rem|'
    r'example|Example|exam|exercise|Exercise|'
    r'algorithm|algorithm\*|table|figure|figure\*|'
    r'definition|Definition|defn|dfn|Def|Defn)\}.*?'
    r'\\end\{\1\}',
    re.DOTALL | re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) ranges that are inside excluded environments."""
    ranges = []
    for m in _EXCLUDED_ENV_FULL.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if [start, end) overlaps any excluded range."""
    for (es, ee) in excluded_ranges:
        if start < ee and end > es:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# R1: {\bf Name:} or \textbf{Name:} style bold-labeled definition blocks
# PRUNED — FP on paper001, paper002, paper003 +3 more | also 3 TP — review before uncommenting
# R1_BF_LABEL = re.compile(
#     r'(?:'
#     r'\{\\bf\s+(?P<name1>[^}:]{1,120})(?::?\}|\}:?)'
#     r'|\\textbf\{(?P<name2>[^}:]{1,120})(?::?\}|\}:?)'
#     r')'
#     r'[ \t]*(?:\\\\)?[ \t]*'
#     r'(?P<body>(?:[^\n]|\n(?!\s*\n)){20,1200})',
#     re.DOTALL,
# )

# R2: "X is called Y" — 'is called' anchor with preceding subject
# PRUNED — FP on paper001, paper009 | also 2 TP — review before uncommenting
# R2_IS_CALLED = re.compile(
#     r'\bis\s+called\b',
#     re.IGNORECASE,
# )

# R3: "are defined as/to be" — extends base C2 to plural
# PRUNED — FP on paper001, paper003, paper004 +1 more | also 3 TP — review before uncommenting
# R3_ARE_DEFINED = re.compile(
#     r'\b(?:is|are)\s+defined\s+(?:as|to\s+be)\s',
#     re.IGNORECASE,
# )

# R4: "X is given by \begin{equation}..." — 'is given by' + equation env
R4_GIVEN_BY = re.compile(
    r'(?P<name>[^\n.]{5,150}?)\s+is\s+given\s+by\s*\n?\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    re.IGNORECASE | re.DOTALL,
)

# R5: "We define X via \begin{equation}..."
R5_DEFINE_VIA = re.compile(
    r'(?:we\s+)?(?:also\s+)?(?:can\s+)?(?:define|denote)\s+'
    r'(?P<name>[^\\\n]{1,120}?)'
    r'\s+via\s*\n?\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    re.IGNORECASE | re.DOTALL,
)

# R6: "we can define X \begin{equation}..." (no keyword 'as/by/via')
R6_DEFINE_EQ = re.compile(
    r'(?:we\s+)?(?:can\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^\\\n]{1,120}?)'
    r'\s*\n?\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    re.IGNORECASE | re.DOTALL,
)

# R7: "We define X as/by ... \begin{env}...\end{env}"
# PRUNED — FP on paper001, paper003
# R7_DEFINE_ENV = re.compile(
#     r'(?:We\s+)?(?:also\s+)?define\s+'
#     r'(?P<name>[^.]{1,80}?)'
#     r'\s*(?:as|by|to\s+be|:=|=)\s*'
#     r'(?P<eq>\\begin\{[^}]*\}.*?\\end\{[^}]*\})',
#     re.IGNORECASE | re.DOTALL,
# )

# R8: "We will denote by X ..." style
# PRUNED — FP on paper002, paper004, paper007 | also 1 TP — review before uncommenting
# R8_DENOTE_BY = re.compile(
#     r'(?:We\s+)?(?:will\s+)?(?:also\s+)?denote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^ ]{1,60}))'
#     r'(?P<tail>(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     re.IGNORECASE | re.DOTALL,
# )

# R9: "Denote by X ... \begin{equation}..."
R9_DENOTE_BY_EQ = re.compile(
    r'\bDenote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ]{1,60}))'
    r'(?P<tail>[^\\]{0,400}?)'
    r'(?P<eq>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\])',
    re.IGNORECASE | re.DOTALL,
)

# R10: "Introduce X ..." / "we introduce ... called <name>: \begin{equation}..."
# PRUNED — FP on paper001, paper002, paper004 +4 more | also 2 TP — review before uncommenting
# R10_INTRODUCE = re.compile(
#     r'\b(?:Introduce|we\s+introduce)\b\s+'
#     r'(?P<name>[^.$\n\\]{1,100}?)'
#     r'(?:'
#     r'(?P<eq1>(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{[^}]*\}.*?\\end\{[^}]*\}))'
#     r'|(?P<tail>[^.]{0,300}?\.)'
#     r')',
#     re.IGNORECASE | re.DOTALL,
# )

# R10b: "introduce ... called <name>: \begin{equation}..." specifically
R10B_INTRODUCE_CALLED = re.compile(
    r'\b(?:introduce|we\s+introduce)\b[^.\\]{0,150}?'
    r'(?:call(?:ed)?)\s+'
    r'(?:\{\\it\s+)?(?P<name>[^}.\n]{1,80})(?:\})?\s*:?\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    re.IGNORECASE | re.DOTALL,
)

# R11: "introduce X as $$...$$" or "introduce X as \[...\]"
R11_INTRODUCE_AS = re.compile(
    r'introduce\s+'
    r'(?P<name>[^.]{1,80}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?P<eq>(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{[^}]*\}.*?\\end\{[^}]*\}))',
    re.IGNORECASE | re.DOTALL,
)

# R12: "Let $$...$$ denote ..."
# PRUNED — FP on paper003, paper006 | also 1 TP — review before uncommenting
# R12_LET_DENOTE = re.compile(
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$\$.*?\$\$|\$[^$]+\$))'
#     r'(?P<tail>[^.]{0,400}?)'
#     r'\bdenote\b'
#     r'(?P<rest>(?:\$\$.*?\$\$|\$[^$]+\$|[^.])*\.)',
#     re.DOTALL,
# )

# R13: "X stands for ..."
R13_STANDS_FOR = re.compile(
    r'(?:The\s+notation\s+)?'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_ ]{1,60}?))'
    r'\s+stands\s+for\b'
    r'(?P<tail>(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    re.IGNORECASE | re.DOTALL,
)

# R14: "the set \begin{equation} <name> = ... \end{equation} is non-empty"
R14_SET_EQUATION = re.compile(
    r'\bthe\s+set\b[^\\]{0,150}?'
    r'(?P<eq>\\begin\{equation[^}]*\}[^\\]*?'
    r'(?P<name>\\?[A-Za-z][A-Za-z0-9_{}^\\]*\s*=)'
    r'.*?'
    r'\\end\{equation[^}]*\})',
    re.IGNORECASE | re.DOTALL,
)

# R15: "X is \emph{term} if ..." — emph-introduced property definition
R15_EMPH_IF = re.compile(
    r'(?P<name>[^.]{1,80}?)'
    r'\s+is\s+\\emph\{(?P<term>[^}]+)\}'
    r'(?:\s+with\s+respect\s+to\s+[^.]{0,80}?)?'
    r'\s+if\s+'
    r'(?P<tail>(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    re.IGNORECASE | re.DOTALL,
)

# R16: "... the \emph{term} [(abbrev)] \begin{align*}..." — NTK-style
R16_EMPH_NAMED_ENV = re.compile(
    r'(?P<prefix>[^.\n]{0,150}?)'
    r'(?:the\s+)?\\emph\{(?P<name>[^}]{1,80})\}'
    r'(?:\s*\([^)]{1,30}\))?'
    r'\s*(?P<eq>\\begin\{(?:align|equation|gather)\*?\}.*?\\end\{(?:align|equation|gather)\*?\})',
    re.IGNORECASE | re.DOTALL,
)

# R17: "<noun phrase> is $$ ... $$" — noun is display math
R17_NOUN_IS_FORMULA = re.compile(
    r'[Tt]he\s+(?P<name>[a-zA-Z][^$\n]{1,80}?)\s+is\s*'
    r'(?P<eq>(?:\$\$.*?\$\$|\\\[.*?\\\]))'
    r'(?P<tail>[^.]*\.)?',
    re.DOTALL,
)

# R18: "<sentence>: $$ ... $$" — colon followed by display math
# PRUNED — FP on paper004, paper005, paper007 +1 more | also 2 TP — review before uncommenting
# R18_COLON_FORMULA = re.compile(
#     r'(?P<name>[A-Z][^:\n\\]{5,150}):'
#     r'\s*(?P<eq>(?:\$\$.*?\$\$|\\\[.*?\\\]))'
#     r'(?P<tail>[^.]*\.)?',
#     re.DOTALL,
# )

# R19: "X is a/an <defined-noun>" — 'is a/an' with definitional noun
_IS_A_NOUNS = (
    r'(?:given\s+)?(?:collection|set|function|map|mapping|sequence|matrix|vector|'
    r'space|operator|graph|code|measure|distribution|process|transform|'
    r'pair|triple|tuple|structure|object|subset|subspace|group|ring|field|'
    r'algebra|manifold|form|tensor|functional|algorithm|procedure|protocol|'
    r'strategy|policy|rule|criterion|condition|property|invariant|'
    r'parameter|variable|constant|symbol|notation|abbreviation|term|notion|'
    r'concept|definition|norm|distance|cost|quantity|bound|estimator|'
    r'approximation|solution|minimizer|maximizer|optimizer)'
)
# PRUNED — FP on paper001, paper002, paper003 +2 more | also 3 TP — review before uncommenting
# R19_IS_A = re.compile(
#     r'(?:\\emph\{(?P<emph>[^}]+)\}[^.;]{0,60}[;,]\s*)?'
#     r'(?P<name>[A-Za-z][A-Za-z0-9 \-]{1,80}?)'
#     r'\s+is\s+(?:a|an|the)\s+' + _IS_A_NOUNS +
#     r'(?P<tail>[^.]{0,400}?\.)',
#     re.IGNORECASE | re.DOTALL,
# )

# R20: "\emph{term}; term is a given collection..." via emph + semicolon
R20_EMPH_SEMICOLON = re.compile(
    r'\\emph\{(?P<name>[^}]+)\}\s*[;,]\s*'
    r'(?P=name)\s+is\s+(?:a|an|the)\s+'
    r'(?P<tail>[^.]{1,400}?\.)',
    re.IGNORECASE | re.DOTALL,
)

# R21: "a \emph{term} obeys PROPERTY ... if ..."
R21_OBEYS = re.compile(
    r'(?:a\s+)?(?:\\emph\{(?P<emph_name>[^}]+)\}|\{\\em\s+(?P<em_name>[^}]+)\})'
    r'[^.]{0,150}?'
    r'\bobeys\b'
    r'(?P<tail>[^.]{0,400}?\.)',
    re.IGNORECASE | re.DOTALL,
)

# R22: "we consider <name> $$ ... $$" definitional
R22_WE_CONSIDER = re.compile(
    r'\bwe\s+consider\b\s+'
    r'(?P<name>[^.$\n]{1,100}?)'
    r'(?P<eq>(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{[^}]*\}.*?\\end\{[^}]*\}))'
    r'(?P<tail>[^.]{0,400}?\.)?',
    re.IGNORECASE | re.DOTALL,
)

# R23: "X is \emph{property} on a set ... if ... we have \begin{equation*}..."
R23_PROPERTY_IF_WE_HAVE = re.compile(
    r'(?P<name>(?:[A-Z][^.\n]{0,100}?))'
    r'\s+is\s+[^.\n]{0,150}?\bif\b[^.\n]{0,150}?\bwe\s+have\b'
    r'\s*\n?\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    re.DOTALL,
)

# Negative / referential filters (mirroring base parser)
_C1_NEGATIVE = re.compile(
    r'\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    re.IGNORECASE,
)
_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    re.IGNORECASE,
)

# Sentence tail helper for 'is called' and 'is defined' anchors
_SENTENCE_TAIL = re.compile(r'(?:[^.]|\.\w)*\.', re.DOTALL)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """Extract definition structures missed by the base parser."""

    excluded_ranges = _build_excluded_ranges(text)
    results: List[dict] = []

    def _make(raw: str, name_raw: str, env: str, rule: str, pos: int) -> dict:
        name = _extract_name(name_raw)
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name,
            'env_name': env,
            'rule_name': rule,
            'structure_type': 'definition',
            '_pos': pos,
        }

    def _extract_name(s: str) -> str:
        if not s:
            return None
        s = s.strip()
        m = re.search(r'\$(.+?)\$', s)
        if m:
            inner = m.group(1)
            inner = re.sub(r'\\[a-zA-Z]+', '', inner)
            inner = re.sub(r'[{}]', '', inner)
            return inner.strip()[:80] or None
        s = _clean_latex(s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s[:80] or None

    # ------------------------------------------------------------------
    # R1: {\bf Name:} style bold-labeled definition blocks
#     # ------------------------------------------------------------------
#     for m in R1_BF_LABEL.finditer(text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_ranges):
#             continue
#         body = m.group('body')
#         if not body or len(body.strip()) < 15:
#             continue
#         name_raw = m.group('name1') or m.group('name2') or ''
#         raw = m.group(0)
#         if _REFERENTIAL.search(raw):
#             continue
#         results.append(_make(raw, name_raw, 'distilled', 'R1_BF_LABEL', s))

    # ------------------------------------------------------------------
    # R2: "X is called Y" — anchor-based
#     # ------------------------------------------------------------------
#     for anchor_m in R2_IS_CALLED.finditer(text):
#         s_anchor = anchor_m.start()
#         e_anchor = anchor_m.end()
#         if _inside_excluded_env(s_anchor, e_anchor, excluded_ranges):
#             continue
#         # Look back for sentence start
#         look_back = max(0, s_anchor - 150)
#         prefix = text[look_back:s_anchor]
#         dot = prefix.rfind('.')
#         nl = prefix.rfind('\n\n')
#         bound = max(dot, nl)
#         name_start = look_back + bound + 1 if bound >= 0 else look_back
#         name_text = text[name_start:s_anchor].strip()
#         if not name_text or len(name_text) > 150:
#             continue
#         # Find end of sentence
#         tail_m = _SENTENCE_TAIL.match(text, e_anchor)
#         if not tail_m:
#             continue
#         raw = text[name_start:tail_m.end()]
#         if _REFERENTIAL.search(raw):
#             continue
#         if len(raw) < 20:
#             continue
#         results.append(_make(raw, name_text, 'distilled', 'R2_IS_CALLED', name_start))

    # ------------------------------------------------------------------
    # R3: "are/is defined as/to be" with display math in tail
    # ------------------------------------------------------------------
    _display_math = re.compile(
        r'(?:\\ba.*?\\ea'
        r'|\\begin\{(?:align|equation|gather)\*?\}.*?\\end\{(?:align|equation|gather)\*?\}'
        r'|\\\[.*?\\\]'
        r'|\$\$.*?\$\$)',
        re.DOTALL,
    )
#     for anchor_m in R3_ARE_DEFINED.finditer(text):
#         s_anchor = anchor_m.start()
#         e_anchor = anchor_m.end()
#         if _inside_excluded_env(s_anchor, e_anchor, excluded_ranges):
#             continue
#         look_back = max(0, s_anchor - 150)
#         prefix = text[look_back:s_anchor]
#         dot = prefix.rfind('.')
#         nl = prefix.rfind('\n\n')
#         bound = max(dot, nl)
#         name_start = look_back + bound + 1 if bound >= 0 else look_back
#         name_text = text[name_start:s_anchor].strip()
#         if not name_text or len(name_text) > 150:
#             continue
#         # Look for display math or sentence end
#         search_region = text[e_anchor:e_anchor + 800]
#         dm = _display_math.search(search_region)
#         tail_m = _SENTENCE_TAIL.match(search_region)
#         if dm and (not tail_m or dm.start() < tail_m.end()):
#             raw_end = e_anchor + dm.end()
#             # Try to grab sentence after display math
#             post = text[raw_end:raw_end + 200]
#             post_m = re.match(r'[^.]*\.', post, re.DOTALL)
#             if post_m:
#                 raw_end += post_m.end()
#         elif tail_m:
#             raw_end = e_anchor + tail_m.end()
#         else:
#             continue
#         raw = text[name_start:raw_end]
#         if _REFERENTIAL.search(raw):
#             continue
#         if len(raw) < 20:
#             continue
#         results.append(_make(raw, name_text, 'distilled', 'R3_ARE_DEFINED', name_start))

    # ------------------------------------------------------------------
    # R4: "X is given by \begin{equation}..."
    # ------------------------------------------------------------------
    for m in R4_GIVEN_BY.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        if not name_raw or len(name_raw) > 150:
            continue
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R4_GIVEN_BY', s))

    # ------------------------------------------------------------------
    # R5: "define/denote X via \begin{equation}..."
    # ------------------------------------------------------------------
    for m in R5_DEFINE_VIA.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _C1_NEGATIVE.search(raw) or _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R5_DEFINE_VIA', s))

    # ------------------------------------------------------------------
    # R6: "we can define X \begin{equation}..." (no 'as/by/via')
    # ------------------------------------------------------------------
    for m in R6_DEFINE_EQ.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _C1_NEGATIVE.search(raw) or _REFERENTIAL.search(raw):
            continue
        if not name_raw:
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R6_DEFINE_EQ', s))

    # ------------------------------------------------------------------
    # R7: "We define X as/by ... \begin{env}...\end{env}"
#     # ------------------------------------------------------------------
#     for m in R7_DEFINE_ENV.finditer(text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_ranges):
#             continue
#         name_raw = m.group('name').strip()
#         raw = m.group(0)
#         if _C1_NEGATIVE.search(raw) or _REFERENTIAL.search(raw):
#             continue
#         results.append(_make(raw, name_raw, 'distilled', 'R7_DEFINE_ENV', s))

    # ------------------------------------------------------------------
    # R8: "We will denote by X ..."
#     # ------------------------------------------------------------------
#     for m in R8_DENOTE_BY.finditer(text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_ranges):
#             continue
#         name_raw = m.group('name').strip()
#         raw = m.group(0)
#         if _REFERENTIAL.search(raw):
#             continue
#         results.append(_make(raw, name_raw, 'distilled', 'R8_DENOTE_BY', s))

    # ------------------------------------------------------------------
    # R9: "Denote by X ... \begin{equation}..."
    # ------------------------------------------------------------------
    for m in R9_DENOTE_BY_EQ.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R9_DENOTE_BY_EQ', s))

    # ------------------------------------------------------------------
    # R10: "Introduce X ..." / "we introduce X ..."
#     # ------------------------------------------------------------------
#     for m in R10_INTRODUCE.finditer(text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_ranges):
#             continue
#         name_raw = m.group('name').strip()
#         raw = m.group(0)
#         if _REFERENTIAL.search(raw):
#             continue
#         if len(raw.strip()) < 20:
#             continue
#         results.append(_make(raw, name_raw, 'distilled', 'R10_INTRODUCE', s))

    # ------------------------------------------------------------------
    # R10B: "introduce ... called <name>: \begin{equation}..."
    # ------------------------------------------------------------------
    for m in R10B_INTRODUCE_CALLED.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R10B_INTRODUCE_CALLED', s))

    # ------------------------------------------------------------------
    # R11: "introduce X as $$...$$"
    # ------------------------------------------------------------------
    for m in R11_INTRODUCE_AS.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R11_INTRODUCE_AS', s))

    # ------------------------------------------------------------------
    # R12: "Let $$...$$ denote ..."
#     # ------------------------------------------------------------------
#     for m in R12_LET_DENOTE.finditer(text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_ranges):
#             continue
#         name_raw = m.group('name').strip()
#         raw = m.group(0)
#         if _REFERENTIAL.search(raw):
#             continue
#         results.append(_make(raw, name_raw, 'distilled', 'R12_LET_DENOTE', s))

    # ------------------------------------------------------------------
    # R13: "X stands for ..."
    # ------------------------------------------------------------------
    for m in R13_STANDS_FOR.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R13_STANDS_FOR', s))

    # ------------------------------------------------------------------
    # R14: "the set \begin{equation} <name> = ..."
    # ------------------------------------------------------------------
    for m in R14_SET_EQUATION.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R14_SET_EQUATION', s))

    # ------------------------------------------------------------------
    # R15: "X is \emph{term} if ..."
    # ------------------------------------------------------------------
    for m in R15_EMPH_IF.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        term = m.group('term').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        if len(raw.strip()) < 20:
            continue
        # Use the emph term as the name
        results.append(_make(raw, term or name_raw, 'distilled', 'R15_EMPH_IF', s))

    # ------------------------------------------------------------------
    # R16: "... the \emph{term} [(abbrev)] \begin{align*}..."
    # ------------------------------------------------------------------
    for m in R16_EMPH_NAMED_ENV.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        if len(raw.strip()) < 20:
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R16_EMPH_NAMED_ENV', s))

    # ------------------------------------------------------------------
    # R17: "the <noun> is $$ ... $$"
    # ------------------------------------------------------------------
    for m in R17_NOUN_IS_FORMULA.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if not re.search(r'\$\$|\\\[', raw):
            continue
        if _REFERENTIAL.search(raw):
            continue
        if len(raw.strip()) < 20:
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R17_NOUN_IS_FORMULA', s))

    # ------------------------------------------------------------------
    # R18: "<sentence>: $$ ... $$" — colon + display math
#     # ------------------------------------------------------------------
#     for m in R18_COLON_FORMULA.finditer(text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_ranges):
#             continue
#         name_raw = m.group('name').strip()
#         raw = m.group(0)
#         if re.search(r'\\begin|\\end', name_raw):
#             continue
#         if not re.search(r'\$\$|\\\[', raw):
#             continue
#         if _REFERENTIAL.search(raw):
#             continue
#         if len(raw.strip()) < 20:
#             continue
#         results.append(_make(raw, name_raw, 'distilled', 'R18_COLON_FORMULA', s))

    # ------------------------------------------------------------------
    # R19: "X is a/an <defined-noun> ..."
#     # ------------------------------------------------------------------
#     for m in R19_IS_A.finditer(text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_ranges):
#             continue
#         emph = m.group('emph')
#         name_raw = emph if emph else m.group('name')
#         raw = m.group(0)
#         if _REFERENTIAL.search(raw):
#             continue
#         if len(raw.strip()) < 20:
#             continue
#         results.append(_make(raw, name_raw, 'distilled', 'R19_IS_A', s))

    # ------------------------------------------------------------------
    # R20: "\emph{term}; term is a given collection..."
    # ------------------------------------------------------------------
    for m in R20_EMPH_SEMICOLON.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R20_EMPH_SEMICOLON', s))

    # ------------------------------------------------------------------
    # R21: "a \emph{term} obeys PROPERTY ..."
    # ------------------------------------------------------------------
    for m in R21_OBEYS.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        emph = m.group('emph_name') or m.group('em_name')
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        results.append(_make(raw, emph or '', 'distilled', 'R21_OBEYS', s))

    # ------------------------------------------------------------------
    # R22: "we consider <name> $$...$$"
    # ------------------------------------------------------------------
    for m in R22_WE_CONSIDER.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        if len(raw.strip()) < 20:
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R22_WE_CONSIDER', s))

    # ------------------------------------------------------------------
    # R23: "X is <property> if ... we have \begin{equation*}..."
    # ------------------------------------------------------------------
    for m in R23_PROPERTY_IF_WE_HAVE.finditer(text):
        s, e = m.start(), m.end()
        if _inside_excluded_env(s, e, excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        if len(raw.strip()) < 20:
            continue
        results.append(_make(raw, name_raw, 'distilled', 'R23_PROPERTY_IF_WE_HAVE', s))

    # ------------------------------------------------------------------
    # Deduplicate overlapping results
    # ------------------------------------------------------------------
    results = _deduplicate(results)

    # Clean up internal position key
    for r in results:
        r.pop('_pos', None)

    return results


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result,
    or which overlap significantly (>60% shared prefix)."""
    if not results:
        return results

    # Sort by position, then by length descending (longer = more specific)
    results.sort(key=lambda r: (r.get('_pos', 0), -len(r.get('raw_latex', ''))))

    kept: List[dict] = []
    kept_spans: List[tuple] = []  # (start, end)

    for r in results:
        pos = r.get('_pos', 0)
        raw = r.get('raw_latex', '')
        r_start = pos
        r_end = pos + len(raw)

        # Check overlap with already kept items
        dominated = False
        for (ks, ke) in kept_spans:
            overlap_start = max(r_start, ks)
            overlap_end = min(r_end, ke)
            if overlap_end > overlap_start:
                overlap_len = overlap_end - overlap_start
                r_len = max(1, r_end - r_start)
                k_len = max(1, ke - ks)
                # If overlap is >60% of either span, consider dominated
                if overlap_len / r_len > 0.6 or overlap_len / k_len > 0.6:
                    dominated = True
                    break

        if not dominated:
            # Also check clean_text similarity
            ct_new = (r.get('clean_text') or '').strip().lower()
            for prev in kept:
                ct_prev = (prev.get('clean_text') or '').strip().lower()
                if not ct_new or not ct_prev:
                    continue
                if ct_new in ct_prev or ct_prev in ct_new:
                    dominated = True
                    break
                min_len = min(len(ct_new), len(ct_prev))
                if min_len > 30 and ct_new[:30] == ct_prev[:30]:
                    dominated = True
                    break

        if not dominated:
            kept.append(r)
            kept_spans.append((r_start, r_end))

    return kept
