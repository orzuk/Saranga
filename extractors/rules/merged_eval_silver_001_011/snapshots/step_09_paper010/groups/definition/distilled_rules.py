import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX → plain-text conversion."""
    t = text
    # remove comments
    t = re.sub(r'%[^\n]*', '', t)
    # remove common commands, keep argument
    for cmd in ('textbf', 'textit', 'emph', 'text', 'mathrm', 'mathbf',
                'mathit', 'mathcal', 'mathbb', 'mathfrak', 'operatorname',
                'overline', 'underline', 'widehat', 'widetilde', 'hat',
                'tilde', 'bar', 'vec', 'dot', 'ddot', 'it', 'bf', 'em',
                'rm', 'tt', 'sf'):
        t = re.sub(r'\\' + cmd + r'\{([^}]*)\}', r'\1', t)
    # remove \label, \ref, \cite, \eqref, \citeA, \citet, \citep
    t = re.sub(r'\\(?:label|ref|eqref|cite[A-Za-z]*)\{[^}]*\}', '', t)
    # remove remaining simple commands
    t = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', t)
    # remove braces
    t = re.sub(r'[{}]', '', t)
    # collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start,end) is inside a proof/theorem/lemma/etc."""
    _EXCL = re.compile(
        r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|'
        r'proposition|Proposition|prop|corollary|Corollary|cor|claim|Claim|'
        r'conjecture|Conjecture|example|Example|exercise|Exercise|remark|'
        r'Remark|note|rem)\}',
        re.IGNORECASE,
    )
    _END = re.compile(r'\\end\{([^}]+)\}')
    depth = {}
    for m in _EXCL.finditer(text):
        if m.start() > start:
            break
        env = m.group(1)
        depth[env] = depth.get(env, 0) + 1
    for m in _END.finditer(text):
        if m.start() > start:
            break
        env = m.group(1)
        if env in depth:
            depth[env] = max(0, depth[env] - 1)
    return any(v > 0 for v in depth.values())


def _overlap(spans: list, new_start: int, new_end: int) -> bool:
    """Return True if [new_start, new_end) overlaps any existing span."""
    for s, e in spans:
        if new_start < e and new_end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# (variable names are used verbatim as rule_name)
# ---------------------------------------------------------------------------

# --- Bold-label blocks: {\bf Name:} body \\ or until next \bf / struct break ---
# PRUNED — FP on paper001, paper002, paper003 +4 more | also 4 TP — review before uncommenting
# INLINE_BF_LABEL = re.compile(
#     r'(?:'
#     r'(?:\{\\bf\s+'
#     r'(?P<name1>[^}:]{1,120}?)'
#     r'(?::?\}|\}:?)'
#     r')'
#     r'|'
#     r'(?:\\textbf\{'
#     r'(?P<name2>[^}:]{1,120}?)'
#     r'(?::?\}|\}:?)'
#     r')'
#     r')'
#     r'[ \t]*(?:\\\\)?[ \t]*\n?'
#     r'(?P<body>(?:(?!(?:\{\\bf\s|\\textbf\{|\\(?:sub)*section|\\begin\{|\\end\{document\})).){15,1200})',
#     re.DOTALL,
# )

# --- "X is called Y" anchor + tail ---
# PRUNED — FP on paper001, paper005, paper009 | also 4 TP — review before uncommenting
# INLINE_IS_CALLED_ANCHOR = re.compile(r'\bis\s+called\b', re.IGNORECASE)
INLINE_IS_CALLED_TAIL = re.compile(r'(?:[^.]|\.\s*[a-z])*\.', re.DOTALL)

# --- "are defined as/to be" extended anchor ---
INLINE_ARE_DEFINED_ANCHOR = re.compile(
    r'\b(?:is|are)\s+defined\s+(?:as|to\s+be)\b', re.IGNORECASE
)
INLINE_ARE_DEFINED_TAIL = re.compile(
    r'(?:'
    r'\\ba.*?\\ea'
    r'|\\begin\{(?:align|equation|gather|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|eqnarray)\*?\}'
    r'|\\\[.*?\\\]'
    r'|\$\$.*?\$\$'
    r'|[^.]*?'
    r')(?:[^.]*\.)',
    re.DOTALL,
)

# --- "We denote by X ..." ---
# PRUNED — FP on paper002, paper004, paper007 | also 2 TP — review before uncommenting
# INLINE_DENOTE = re.compile(
#     r'(?P<full>'
#     r'(?:We\s+)?(?:will\s+)?(?:also\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|\$\$[^$]+\$\$|[A-Za-z0-9\\{}_^ ]{1,60}))'
#     r'(?:(?!\\begin\{|\n\n).){0,400}?'
#     r'(?:\.(?!\d)|\n\n|(?=\\begin\{(?:equation|align|gather)[^}]*\})))',
#     re.DOTALL,
# )

# --- "Denote by X ... equation_env" ---
INLINE_DENOTE_BY_EQ = re.compile(
    r'[Dd]enote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ]{1,60}))'
    r'(?P<middle>(?:(?!\\begin\{).){0,400}?)'
    r'(?P<body>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])',
    re.DOTALL,
)

# --- "stands for" ---
INLINE_STANDS_FOR = re.compile(
    r'(?P<full>'
    r'(?:The\s+notation\s+)?'
    r'(?P<name>(?:\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})?|[A-Za-z0-9\\_ ]{1,60}?))'
    r'\s+stands\s+for\b'
    r'(?:(?!\n\n).){0,500}?'
    r'(?:\.(?!\d)|\n\n))',
    re.DOTALL,
)

# --- "Let $...$ denote ..." ---
# PRUNED — FP on paper003, paper006 | also 1 TP — review before uncommenting
# INLINE_LET_DENOTE = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$\$.*?\$\$|\$[^$]+\$))'
#     r'(?:(?!\n\n).){0,400}?'
#     r'\bdenote\b'
#     r'(?:(?!\n\n).){0,400}?'
#     r'(?:\.(?!\d)|\n\n))',
#     re.DOTALL,
# )

# --- "Introduce X ..." imperative ---
INLINE_INTRODUCE = re.compile(
    r'(?P<full>'
    r'\bIntroduce\b\s+'
    r'(?P<name>[^.$\n\\]{1,100}?)'
    r'(?:'
    r'(?P<body_eq>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])'
    r'|(?:(?!\n\n).){0,400}?(?:\.(?!\d)|\n\n)'
    r'))',
    re.DOTALL,
)

# --- "we introduce ... call(ed) <name>: equation_env" ---
INLINE_INTRODUCE_CALLED = re.compile(
    r'(?P<full>'
    r'\bwe\s+introduce\b'
    r'(?:(?!\n\n).){0,200}?'
    r'\bcall(?:ed)?\b\s+'
    r'(?:\{\\it\s+|\{\\em\s+|\\emph\{)?'
    r'(?P<name>[^}.\n]{1,80})'
    r'(?:\})?\s*:?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\]))',
    re.IGNORECASE | re.DOTALL,
)

# --- "we consider ... equation_env" ---
INLINE_WE_CONSIDER = re.compile(
    r'(?P<full>'
    r'\bwe\s+consider\b\s+'
    r'(?P<name>[^.$\n]{1,120}?)'
    r'(?P<body>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])'
    r'(?:(?!\n\n).){0,300}?'
    r'(?:\.(?!\d)|\n\n))',
    re.IGNORECASE | re.DOTALL,
)

# --- "define X as/by ... env" (env-body variant) ---
INLINE_DEFINE_ENV = re.compile(
    r'(?P<full>'
    r'(?:We\s+)?(?:also\s+)?[Dd]efine\s+'
    r'(?P<name>[^.{\\]{1,100}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?P<body>\\begin\{[^}]+\}.*?\\end\{[^}]+\}))',
    re.DOTALL,
)

# --- "define/denote X via equation_env" ---
INLINE_DEFINE_VIA = re.compile(
    r'(?:we\s+)?(?:also\s+)?(?:define|denote)\s+'
    r'(?P<name>[^.\n]{1,120}?)'
    r'\s+via\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])',
    re.IGNORECASE | re.DOTALL,
)

# --- "we can define X \begin{equation*}..." (no 'as/by' keyword) ---
INLINE_DEFINE_EQ = re.compile(
    r'(?:we\s+)?(?:can\s+)?(?:also\s+)?[Dd]efine\s+'
    r'(?P<name>[^\\\n.]{1,120}?)'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\})',
    re.DOTALL,
)

# --- "X is given by \begin{equation}..." ---
INLINE_GIVEN_BY = re.compile(
    r'(?P<name>[^.\n]{1,160}?)'
    r'\s+is\s+given\s+by\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])',
    re.IGNORECASE | re.DOTALL,
)

# --- "X is \emph{property} if ..." ---
INLINE_EMPH_IF = re.compile(
    r'(?P<full>'
    r'(?P<name>[^.\n]{1,120}?)'
    r'\s+is\s+\\emph\{[^}]+\}'
    r'(?:\s+with\s+[^.]{0,80}?)?'
    r'\s+if\s+'
    r'(?:(?!\n\n).){0,400}?'
    r'(?:\.(?!\d)|\n\n))',
    re.DOTALL,
)

# --- "\emph{name} + display math" named concept introduction ---
INLINE_EMPH_NAMED = re.compile(
    r'(?P<prefix>[^.\n]{0,160}?)'
    r'(?:the\s+)?\\emph\{(?P<name>[^}]{1,100})\}'
    r'(?:\s*\([^)]{1,30}\))?'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{(?:align|align\*|equation|equation\*|gather|gather\*)\}.*?\\end\{(?:align|align\*|equation|equation\*|gather|gather\*)\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])',
    re.IGNORECASE | re.DOTALL,
)

# --- "X is <property> ... if ... we have equation_env" ---
INLINE_PROPERTY_IF = re.compile(
    r'(?P<name>(?:[A-Z][^.\n]{0,120}?))'
    r'\s+is\s+[^.\n]{0,160}?\bif\b[^.\n]{0,160}?\bwe\s+have\b'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])',
    re.DOTALL,
)

# --- "the <noun> is $$ ... $$" ---
INLINE_NOUN_IS_FORMULA = re.compile(
    r'(?P<full>'
    r'[Tt]he\s+(?P<name>[a-zA-Z][^$\n]{1,80}?)\s+is\s*'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$)'
    r'(?:[^.\n]*\.)?)',
    re.DOTALL,
)

# --- "<sentence ending with colon> $$ ... $$" ---
# PRUNED — FP on paper004, paper007, paper009 +1 more | also 2 TP — review before uncommenting
# INLINE_COLON_FORMULA = re.compile(
#     r'(?P<full>'
#     r'(?P<name>[A-Z][^:\n\\]{5,160}?):'
#     r'\s*(?:\\\[.*?\\\]|\$\$.*?\$\$)'
#     r'(?:[^.\n]*\.)?)',
#     re.DOTALL,
# )

# --- "X obeys/satisfies <property> if ..." with \emph or \em ---
INLINE_OBEYS = re.compile(
    r'(?P<full>'
    r'(?:a\s+)?(?:\\emph\{(?P<ename>[^}]+)\}|\{\\em\s+(?P<emname>[^}]+)\})'
    r'(?:(?!\n\n).){0,200}?'
    r'\bobeys\b'
    r'(?:(?!\n\n).){0,400}?'
    r'(?:\.(?!\d)|\n\n))',
    re.DOTALL,
)

# --- "the set \begin{equation} <name> = ... \end{equation}" ---
INLINE_SET_EQUATION = re.compile(
    r'(?P<full>'
    r'\bthe\s+set\b(?:(?!\n\n).){0,200}?'
    r'\\begin\{(?:equation|align|gather)[^}]*\}'
    r'(?P<name_eq>(?:(?!\\end).){0,60}?=)'
    r'(?:(?!\\end\{).)*'
    r'\\end\{(?:equation|align|gather)[^}]*\})',
    re.IGNORECASE | re.DOTALL,
)

# --- "optimization problem \begin{equation}... with \defeq or \argmin" ---
INLINE_OPTIM_PROBLEM = re.compile(
    r'(?P<name>(?:(?!\n\n).){1,300}?)'
    r'(?:optimization\s+problem|is\s+based\s+on(?:(?!\n\n).){0,160}?solving(?:(?!\n\n).){0,80}?problem)'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\})',
    re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# Helpers for name extraction
# ---------------------------------------------------------------------------

_NEG_DEFINE = re.compile(
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


def _extract_name(raw: str) -> str:
    if not raw:
        return ''
    raw = raw.strip()
    # prefer first inline math
    m = re.search(r'\$(.+?)\$', raw)
    if m:
        return _clean_latex(m.group(1))[:80]
    return _clean_latex(raw)[:80]


def _make_result(raw_latex: str, name_raw: str, rule_name: str) -> dict:
    return {
        'raw_latex': raw_latex,
        'clean_text': _clean_latex(raw_latex),
        'name': _extract_name(name_raw) or None,
        'env_name': 'distilled',
        'rule_name': rule_name,
        'structure_type': 'definition',
    }


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    results: List[dict] = []
    spans: List[tuple] = []  # (start, end)

    def add(raw: str, name_raw: str, rule_name: str, start: int):
        if not raw or len(raw.strip()) < 15:
            return
        end = start + len(raw)
        if _overlap(spans, start, end):
            return
        if _inside_excluded_env(text, start, end):
            return
        spans.append((start, end))
        results.append(_make_result(raw, name_raw, rule_name))

    # -----------------------------------------------------------------------
    # INLINE_BF_LABEL: {\bf Name:} body
#     # -----------------------------------------------------------------------
#     for m in INLINE_BF_LABEL.finditer(text):
#         name_raw = (m.group('name1') or m.group('name2') or '').strip()
#         body = m.group('body') or ''
#         raw = m.group(0)
#         if _REFERENTIAL.search(raw):
#             continue
#         if len(body.strip()) < 15:
#             continue
#         add(raw, name_raw, 'INLINE_BF_LABEL', m.start())

    # -----------------------------------------------------------------------
    # INLINE_IS_CALLED_ANCHOR + tail: "X is called Y ..."
#     # -----------------------------------------------------------------------
#     for anchor in INLINE_IS_CALLED_ANCHOR.finditer(text):
#         if _inside_excluded_env(text, anchor.start(), anchor.end()):
#             continue
#         look_back = max(0, anchor.start() - 150)
#         prefix = text[look_back:anchor.start()]
#         # find last sentence boundary
#         dot = max(prefix.rfind('.'), prefix.rfind('\n\n'))
#         name_start = look_back + dot + 1 if dot >= 0 else look_back
#         name_text = text[name_start:anchor.start()].strip()
#         if not name_text or len(name_text) > 150:
#             continue
#         tail_m = INLINE_IS_CALLED_TAIL.match(text, anchor.end())
#         if not tail_m:
#             continue
#         raw = text[name_start:tail_m.end()]
#         if _REFERENTIAL.search(raw):
#             continue
#         if _overlap(spans, name_start, tail_m.end()):
#             continue
#         if _inside_excluded_env(text, name_start, tail_m.end()):
#             continue
#         spans.append((name_start, tail_m.end()))
#         results.append(_make_result(raw, name_text, 'INLINE_IS_CALLED_ANCHOR'))

    # -----------------------------------------------------------------------
    # INLINE_ARE_DEFINED_ANCHOR: "are/is defined as/to be" + extended tail
    # -----------------------------------------------------------------------
    for anchor in INLINE_ARE_DEFINED_ANCHOR.finditer(text):
        if _inside_excluded_env(text, anchor.start(), anchor.end()):
            continue
        look_back = max(0, anchor.start() - 160)
        prefix = text[look_back:anchor.start()]
        dot = max(prefix.rfind('.'), prefix.rfind('\n\n'))
        name_start = look_back + dot + 1 if dot >= 0 else look_back
        name_text = text[name_start:anchor.start()].strip()
        if not name_text or len(name_text) > 160:
            continue
        # Try extended tail (handles display math)
        search_region = text[anchor.end():anchor.end() + 800]
        tail_m = INLINE_ARE_DEFINED_TAIL.match(search_region)
        if not tail_m:
            continue
        raw = text[name_start:anchor.end() + tail_m.end()]
        if _REFERENTIAL.search(raw):
            continue
        if _overlap(spans, name_start, anchor.end() + tail_m.end()):
            continue
        if _inside_excluded_env(text, name_start, anchor.end() + tail_m.end()):
            continue
        spans.append((name_start, anchor.end() + tail_m.end()))
        results.append(_make_result(raw, name_text, 'INLINE_ARE_DEFINED_ANCHOR'))

    # -----------------------------------------------------------------------
    # INLINE_DENOTE: "We (will) denote by X ..."
#     # -----------------------------------------------------------------------
#     for m in INLINE_DENOTE.finditer(text):
#         raw = m.group('full')
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(raw):
#             continue
#         add(raw, name_raw, 'INLINE_DENOTE', m.start())

    # -----------------------------------------------------------------------
    # INLINE_DENOTE_BY_EQ: "Denote by X ... equation"
#     # -----------------------------------------------------------------------
#     for m in INLINE_DENOTE_BY_EQ.finditer(text):
#         raw = m.group(0)
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(raw):
#             continue
#         add(raw, name_raw, 'INLINE_DENOTE_BY_EQ', m.start())

    # -----------------------------------------------------------------------
    # INLINE_STANDS_FOR: "X stands for ..."
    # -----------------------------------------------------------------------
    for m in INLINE_STANDS_FOR.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_STANDS_FOR', m.start())

    # -----------------------------------------------------------------------
    # INLINE_LET_DENOTE: "Let $...$ denote ..."
#     # -----------------------------------------------------------------------
#     for m in INLINE_LET_DENOTE.finditer(text):
#         raw = m.group('full')
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(raw):
#             continue
#         add(raw, name_raw, 'INLINE_LET_DENOTE', m.start())

    # -----------------------------------------------------------------------
    # INLINE_INTRODUCE: "Introduce X ..."
    # -----------------------------------------------------------------------
    for m in INLINE_INTRODUCE.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_INTRODUCE', m.start())

    # -----------------------------------------------------------------------
    # INLINE_INTRODUCE_CALLED: "we introduce ... called <name>: equation"
    # -----------------------------------------------------------------------
    for m in INLINE_INTRODUCE_CALLED.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_INTRODUCE_CALLED', m.start())

    # -----------------------------------------------------------------------
    # INLINE_WE_CONSIDER: "we consider <name> equation ..."
    # -----------------------------------------------------------------------
    for m in INLINE_WE_CONSIDER.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_WE_CONSIDER', m.start())

    # -----------------------------------------------------------------------
    # INLINE_DEFINE_ENV: "define X as/by ... \begin{env}...\end{env}"
    # -----------------------------------------------------------------------
    for m in INLINE_DEFINE_ENV.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name') or ''
        if _NEG_DEFINE.search(raw):
            continue
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_DEFINE_ENV', m.start())

    # -----------------------------------------------------------------------
    # INLINE_DEFINE_VIA: "define/denote X via equation"
    # -----------------------------------------------------------------------
    for m in INLINE_DEFINE_VIA.finditer(text):
        raw = m.group(0)
        name_raw = m.group('name') or ''
        if _NEG_DEFINE.search(raw):
            continue
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_DEFINE_VIA', m.start())

    # -----------------------------------------------------------------------
    # INLINE_DEFINE_EQ: "define X \begin{equation*}..."
    # -----------------------------------------------------------------------
    for m in INLINE_DEFINE_EQ.finditer(text):
        raw = m.group(0)
        name_raw = m.group('name') or ''
        if _NEG_DEFINE.search(raw):
            continue
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_DEFINE_EQ', m.start())

    # -----------------------------------------------------------------------
    # INLINE_GIVEN_BY: "X is given by equation"
    # -----------------------------------------------------------------------
    for m in INLINE_GIVEN_BY.finditer(text):
        raw = m.group(0)
        name_raw = m.group('name') or ''
        if not name_raw or len(name_raw) > 200:
            continue
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_GIVEN_BY', m.start())

    # -----------------------------------------------------------------------
    # INLINE_EMPH_IF: "X is \emph{property} if ..."
    # -----------------------------------------------------------------------
    for m in INLINE_EMPH_IF.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_EMPH_IF', m.start())

    # -----------------------------------------------------------------------
    # INLINE_EMPH_NAMED: "\emph{name} + display math"
    # -----------------------------------------------------------------------
    for m in INLINE_EMPH_NAMED.finditer(text):
        name_raw = m.group('name') or ''
        raw = m.group(0)
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_EMPH_NAMED', m.start())

    # -----------------------------------------------------------------------
    # INLINE_PROPERTY_IF: "X is <property> ... if ... we have equation"
    # -----------------------------------------------------------------------
    for m in INLINE_PROPERTY_IF.finditer(text):
        raw = m.group(0)
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_PROPERTY_IF', m.start())

    # -----------------------------------------------------------------------
    # INLINE_NOUN_IS_FORMULA: "the <noun> is $$ ... $$"
    # -----------------------------------------------------------------------
    for m in INLINE_NOUN_IS_FORMULA.finditer(text):
        raw = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(raw):
            continue
        if not re.search(r'\$\$|\\\[', raw):
            continue
        add(raw, name_raw, 'INLINE_NOUN_IS_FORMULA', m.start())

    # -----------------------------------------------------------------------
    # INLINE_COLON_FORMULA: "<sentence>: $$ ... $$"
#     # -----------------------------------------------------------------------
#     for m in INLINE_COLON_FORMULA.finditer(text):
#         raw = m.group('full')
#         name_raw = m.group('name') or ''
#         if not re.search(r'\$\$|\\\[', raw):
#             continue
#         if re.search(r'\\begin|\\end', name_raw):
#             continue
#         if _REFERENTIAL.search(raw):
#             continue
#         add(raw, name_raw, 'INLINE_COLON_FORMULA', m.start())

    # -----------------------------------------------------------------------
    # INLINE_OBEYS: "\emph{term} ... obeys ..."
    # -----------------------------------------------------------------------
    for m in INLINE_OBEYS.finditer(text):
        raw = m.group('full')
        name_raw = (m.group('ename') or m.group('emname') or '').strip()
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_OBEYS', m.start())

    # -----------------------------------------------------------------------
    # INLINE_SET_EQUATION: "the set \begin{equation} X = ..."
    # -----------------------------------------------------------------------
    for m in INLINE_SET_EQUATION.finditer(text):
        raw = m.group('full')
        name_raw = (m.group('name_eq') or '').strip()
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_SET_EQUATION', m.start())

    # -----------------------------------------------------------------------
    # INLINE_OPTIM_PROBLEM: "optimization problem \begin{equation}... with \defeq"
    # -----------------------------------------------------------------------
    for m in INLINE_OPTIM_PROBLEM.finditer(text):
        body_text = m.group('body') or ''
        if not re.search(r'\\(?:defeq|argmin|triangleq|coloneqq)', body_text):
            continue
        raw = m.group(0)
        name_raw = (m.group('name') or '').strip()
        if _REFERENTIAL.search(raw):
            continue
        add(raw, name_raw, 'INLINE_OPTIM_PROBLEM', m.start())

    return results
