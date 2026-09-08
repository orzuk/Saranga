import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and return readable text."""
    t = text
    # Remove comments
    t = re.sub(r'%[^\n]*', '', t)
    # Remove common commands with arguments
    for cmd in ('textbf', 'textit', 'emph', 'text', 'mathrm', 'mathbf',
                'mathit', 'mathcal', 'mathbb', 'operatorname', 'label',
                'ref', 'cite', 'citeA', 'citep', 'citet', 'eqref',
                'footnote', 'footnotetext', 'caption'):
        t = re.sub(r'\\' + cmd + r'\{([^}]*)\}', r'\1', t)
    # Remove \em, \bf, \it inside braces
    t = re.sub(r'\{\\(?:em|bf|it|rm)\s+([^}]*)\}', r'\1', t)
    # Remove display math environments
    for env in ('equation', 'align', 'gather', 'multline', 'eqnarray',
                'equation*', 'align*', 'gather*', 'multline*', 'eqnarray*'):
        t = re.sub(r'\\begin\{' + re.escape(env) + r'\}.*?\\end\{' + re.escape(env) + r'\}',
                   ' FORMULA ', t, flags=re.DOTALL)
    # \ba...\ea style
    t = re.sub(r'\\ba\b.*?\\ea\b', ' FORMULA ', t, flags=re.DOTALL)
    # Display math
    t = re.sub(r'\$\$.*?\$\$', ' FORMULA ', t, flags=re.DOTALL)
    t = re.sub(r'\\\[.*?\\\]', ' FORMULA ', t, flags=re.DOTALL)
    # Inline math
    t = re.sub(r'\$[^$]+\$', ' MATH ', t)
    # Remove remaining commands
    t = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', ' ', t)
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    t = re.sub(r'[{}]', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


# Environments to exclude (inside these, inline patterns fire too many FPs)
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
    'remark', 'Remark', 'rem', 'note',
    'figure', 'table', 'algorithm',
]

_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\}' +
    r'.*?\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) ranges for excluded environments."""
    ranges = []
    for m in _EXCLUDED_ENV_RE.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if [start, end) overlaps any excluded range."""
    for (rs, re_) in excluded_ranges:
        if start < re_ and end > rs:
            return True
    return False


# ---------------------------------------------------------------------------
# Negative / referential filters
# ---------------------------------------------------------------------------

_C1_NEGATIVE = re.compile(
    r'\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    flags=re.IGNORECASE,
)

_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# R1: {\bf Name:} / \textbf{Name:} style bold-labeled definition blocks
# PRUNED — FP on paper001, paper002, paper003 +4 more | also 5 TP — review before uncommenting
# BF_LABEL_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:\{\\bf\s+|\{\\textbf\s+|\\textbf\{)'
#     r'(?P<name>[^}:]{1,120})'
#     r'(?::?\}|\}:?)'
#     r'\s*(?:\\\\)?\s*'
#     r'(?:(?!\\begin\{(?:' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\})'
#     r'(?:(?!\{\\bf\b)(?!\\textbf\{)(?!\\(?:sub)*section\b)(?!\\end\{document\}).)){20,1200}'
#     r')'
#     r'(?=\n\s*\n|\{\\bf\s|\\textbf\{|\\\\\s*\n|\\(?:sub)*section|\\begin|\\end\{document\})',
#     flags=re.DOTALL,
# )

# R2: "X is called Y" definitional sentences
IS_CALLED_ANCHOR = re.compile(
    r'\bis\s+called\b',
    flags=re.IGNORECASE,
)
IS_CALLED_TAIL = re.compile(
    r'[^.]*\.',
    flags=re.DOTALL,
)

# R3: "are defined as" extension (plural + display math)
ARE_DEFINED_AS_PATTERN = re.compile(
    r'(?P<name>[^.\n]{5,200}?)'
    r'\s+are\s+(?:closely\s+related\s+to\s+each\s+other\s+and\s+)?(?:both\s+)?defined\s+as\s*\n?\s*'
    r'(?P<body>'
    r'(?:\\ba\b.*?\\ea\b)'
    r'|(?:\\begin\{(?:align|equation|gather|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|eqnarray)\*?\})'
    r'|(?:\$\$.*?\$\$)'
    r'|(?:\\\[.*?\\\])'
    r')',
    flags=re.DOTALL | re.IGNORECASE,
)

# R4: "The commute distance ... is ..." named-concept "is the <noun>" definition
# PRUNED — FP on paper001, paper003, paper005 +4 more | also 3 TP — review before uncommenting
# NAMED_CONCEPT_IS_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:The\s+)?'
#     r'(?P<name>[A-Z][^.()\n]{2,100}?)'
#     r'(?:\s*\([^)]{1,80}\))?'
#     r'\s+(?:is|are)\s+(?:the\s+|an?\s+)'
#     r'(?:[^.\n]{20,400}?)'
#     r'\.)',
    flags=re.DOTALL,
)

_NAMED_CONCEPT_KEYWORDS = re.compile(
    r'\b(expected|probability|distance|measure|number|set|function|matrix|'
    r'collection|sequence|space|operator|mapping|graph|code|distribution|'
    r'process|transform|vector|algorithm|method|criterion|property|notion|'
    r'concept|quantity|value|cost|time|class|family|basis|norm)\b',
    flags=re.IGNORECASE,
)

# R5: "a linear code is a given collection ..." / "X is a <structural noun>"
# PRUNED — FP on paper001, paper003, paper006 +2 more | also 1 TP — review before uncommenting
# IS_A_STRUCTURAL_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:\\emph\{(?P<emph_name>[^}]+)\}[^.;]{0,60}[;,]\s*)?'
#     r'(?P<name>[A-Za-z][A-Za-z0-9 \-]{1,80}?)'
#     r'\s+is\s+(?:a|an|the)\s+(?:given\s+)?'
#     r'(?:collection|set|sequence|map|mapping|function|family|class|space|'
#     r'operator|matrix|vector|graph|code|measure|distribution|process|'
#     r'transform|pair|triple|tuple|list|array|structure|element|subset|'
#     r'subspace|group|ring|field|algebra|module|lattice|poset|relation|'
#     r'partition|basis|frame|system|scheme|manifold|form|tensor|functional|'
#     r'filter|ideal|kernel|image|morphism|functor|model|theory|formula|'
#     r'algorithm|procedure|protocol|strategy|policy|rule|criterion|'
#     r'condition|property|invariant|characteristic|parameter|variable|'
#     r'constant|symbol|notation|abbreviation|term|notion|concept|definition)\b'
#     r'(?:[^.]{5,400}?)'
#     r'\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R6: "We (will) denote by X ..." 
# PRUNED — FP on paper003, paper004, paper007
# DENOTE_BY_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:We\s+)?(?:will\s+)?(?:also\s+)?denote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^]+))'
#     r'(?:[^.]{5,400}?)'
#     r'\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R7: "X obeys/satisfies PROPERTY if ..." — after \emph or {\em term}
OBEYS_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:a\s+)?'
    r'(?:\\emph\{(?P<emph_name>[^}]+)\}|\{\\em\s+(?P<em_name>[^}]+)\})'
    r'[^.]{0,200}?'
    r'\bobeys\b'
    r'[^.]{0,400}?'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R8: "The notation X stands for ..."
STANDS_FOR_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:The\s+notation\s+)?'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\\s_]{1,80}?))'
    r'\s+stands\s+for\b'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{[^}]*\}.*?\\end\{[^}]*\}|[^.]{0,400}?)'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R9: "Let $$ ... $$ denote ..."  or "Let $ ... $ denote ..."
# PRUNED — FP on paper003, paper006 | also 1 TP — review before uncommenting
# LET_DENOTE_PATTERN = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$\$[^$]*\$\$|\$[^$]+\$))'
#     r'[^.]{0,400}?'
#     r'\bdenote\b'
#     r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.]{0,400}?)'
#     r'\.)',
#     flags=re.DOTALL,
# )

# R10: "Introduce X ..." imperative (standalone sentence, e.g. "Introduce the residual sum...")
INTRODUCE_IMPERATIVE_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=\n))\s*'
    r'\bIntroduce\b\s+'
    r'(?P<name>[^.$\n]{1,120}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{[^}]*\}.*?\\end\{[^}]*\})'
    r'(?:[^.]{0,300}?)'
    r'\.)',
    flags=re.DOTALL | re.MULTILINE,
)

# R11: "we introduce ... called <name>: \begin{equation*}..."
INTRODUCE_CALLED_PATTERN = re.compile(
    r'(?P<full>'
    r'\bwe\s+introduce\b[^.\\]{0,200}?'
    r'(?:call(?:ed)?)\s+'
    r'(?:\{\\it\s+)?(?P<name>[^{}.\n]{1,100})(?:\})?\s*:?\s*'
    r'(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\\begin\{equation\}.*?\\end\{equation\}'
    r'|\\begin\{align\}.*?\\end\{align\}'
    r'))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R12: "Denote by X ... \begin{equation*}..."
DENOTE_BY_EQUATION_PATTERN = re.compile(
    r'(?P<full>'
    r'\bDenote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ]{1,80}))'
    r'[^\\]{0,500}?'
    r'(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\\begin\{equation\}.*?\\end\{equation\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R13: "the set \begin{equation} <name> = ..." 
SET_EQUATION_PATTERN = re.compile(
    r'(?P<full>'
    r'\bthe\s+set\b[^\\]{0,200}?'
    r'\\begin\{equation[^}]*\}[^\n]*?'
    r'(?P<name>\\?[A-Za-z][A-Za-z0-9_{}^\\]*\s*=)'
    r'.*?'
    r'\\end\{equation[^}]*\}'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R14: "We define X as/by ... \begin{gather*}...\end{gather*}" (env body)
DEFINE_ENV_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:We\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,120}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?:\\begin\{[^}]*\}.*?\\end\{[^}]*\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R15: "introduce X as $$...$$" or "introduce X as \begin{...}...\end{...}"
INTRODUCE_AS_PATTERN = re.compile(
    r'(?P<full>'
    r'\bintroduce\s+'
    r'(?P<name>[^.\\]{1,120}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{[^}]*\}.*?\\end\{[^}]*\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R16: "X is given by \begin{equation}..."
GIVEN_BY_EQUATION_PATTERN = re.compile(
    r'(?P<name>[^.\n]{5,200}?)'
    r'\s+is\s+given\s+by\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{equation\}.*?\\end\{equation\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R17: "define/denote X via \begin{equation}..."
DEFINE_VIA_PATTERN = re.compile(
    r'(?:(?:we\s+)?(?:also\s+)?(?:define|denote)\s+'
    r'(?P<name>[^.\\\n]{1,160}?)'
    r'\s+via\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{equation\}.*?\\end\{equation\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R18: "we can define X \begin{equation*}..." (no 'as/by/to be' keyword)
DEFINE_EQ_PATTERN = re.compile(
    r'(?:(?:we\s+)?(?:can\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^\\\n]{1,160}?)'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{equation\}.*?\\end\{equation\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R19: "X is <property> ... if ... we have \begin{equation*}..."
PROPERTY_IF_WE_HAVE_PATTERN = re.compile(
    r'(?P<name>(?:[A-Z][^.\n]{0,120}?))'
    r'\s+is\s+[^.\n]{0,200}?\bif\b[^.\n]{0,200}?\bwe\s+have\b'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{equation\}.*?\\end\{equation\}'
    r')',
    flags=re.DOTALL,
)

# R20: "X is \emph{term} if ..." — emph-based conditional definition
EMPH_IF_PATTERN = re.compile(
    r'(?P<full>'
    r'(?P<name>[^.\n]{1,120}?)'
    r'\s+is\s+\\emph\{[^}]+\}'
    r'(?:\s+with\s+respect\s+to\s+[^.\n]{0,80}?)?'
    r'\s+if\s+'
    r'(?:[^.\\]|\\(?!begin|end|section|subsection)){5,400}?'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R21: "\emph{name} [(abbrev)] followed by align*/equation block"
EMPH_NAMED_ENV_PATTERN = re.compile(
    r'(?P<full>'
    r'[^.\n]{0,200}?'
    r'(?:the\s+)?\\emph\{(?P<name>[^}]{1,100})\}'
    r'(?:\s*\([^)]{1,30}\))?'
    r'\s*(?:\$\$.*?\$\$|\\\[.*?\\\]'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{equation\}.*?\\end\{equation\}'
    r')'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R22: "the <noun phrase> is $$...$$" 
NOUN_IS_FORMULA_PATTERN = re.compile(
    r'(?P<full>'
    r'[Tt]he\s+(?P<name>[a-zA-Z][^$\n]{1,80}?)\s+is\s*'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\])'
    r'(?:[^.]*\.)?)',
    flags=re.DOTALL,
)

# R23: "<sentence ending with colon> $$ ... $$"
# PRUNED — FP on paper004, paper005, paper007 +2 more | also 2 TP — review before uncommenting
# COLON_FORMULA_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?P<name>[A-Z][^:\n\\]{5,160}?):'
#     r'\s*(?:\$\$.*?\$\$|\\\[.*?\\\])'
#     r'(?:[^.]*\.)?)',
#     flags=re.DOTALL,
# )

# R24: "we consider <name> $$...$$ , and let X denote ..."
WE_CONSIDER_PATTERN = re.compile(
    r'(?P<full>'
    r'\bwe\s+consider\b\s+'
    r'(?P<name>[^.$\n]{1,120}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]'
    r'|\\begin\{[^}]*\}.*?\\end\{[^}]*\})'
    r'(?:[^.]{0,400}?)'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R25: "X (also called Y) is ..." broader named-concept definitional sentence
ALSO_CALLED_PATTERN = re.compile(
    r'(?P<full>'
    r'(?P<name>[A-Z][^.\n(]{2,100}?)'
    r'(?:\s*\((?:also\s+)?called\s+[^)]{1,80}\))'
    r'\s+(?:is|are|denotes?|refers?\s+to)\s+'
    r'(?:[^.\n]{20,500}?)'
    r'\.)',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Priority map for deduplication
# ---------------------------------------------------------------------------

_RULE_PRIORITY = {
    'BF_LABEL_PATTERN': 1,
    'ARE_DEFINED_AS_PATTERN': 1,
    'IS_CALLED_ANCHOR': 2,
    'IS_A_STRUCTURAL_PATTERN': 2,
    'DENOTE_BY_PATTERN': 2,
    'LET_DENOTE_PATTERN': 2,
    'INTRODUCE_CALLED_PATTERN': 2,
    'DENOTE_BY_EQUATION_PATTERN': 2,
    'SET_EQUATION_PATTERN': 2,
    'DEFINE_ENV_PATTERN': 2,
    'INTRODUCE_AS_PATTERN': 2,
    'GIVEN_BY_EQUATION_PATTERN': 2,
    'DEFINE_VIA_PATTERN': 2,
    'DEFINE_EQ_PATTERN': 2,
    'PROPERTY_IF_WE_HAVE_PATTERN': 2,
    'EMPH_IF_PATTERN': 2,
    'EMPH_NAMED_ENV_PATTERN': 2,
    'NOUN_IS_FORMULA_PATTERN': 2,
    'COLON_FORMULA_PATTERN': 2,
    'WE_CONSIDER_PATTERN': 2,
    'ALSO_CALLED_PATTERN': 2,
    'INTRODUCE_IMPERATIVE_PATTERN': 2,
    'NAMED_CONCEPT_IS_PATTERN': 3,
    'OBEYS_PATTERN': 2,
    'STANDS_FOR_PATTERN': 2,
}

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX source, complementing the base parser.
    Returns list of dicts with keys: raw_latex, clean_text, name, env_name,
    rule_name, structure_type.
    """
    results: List[dict] = []
    excluded_ranges = _build_excluded_ranges(text)

    def _make_result(raw: str, name_raw: str | None, rule_name: str, pos: int) -> dict | None:
        if not raw or len(raw.strip()) < 15:
            return None
        # Check excluded
        if _inside_excluded_env(pos, pos + len(raw), excluded_ranges):
            return None
        clean = _clean_latex(raw)
        name = None
        if name_raw:
            name_raw = name_raw.strip()
            # Extract from math
            mm = re.search(r'\$(.+?)\$', name_raw)
            if mm:
                name = re.sub(r'\\[a-zA-Z]+\*?', ' ', mm.group(1)).strip()[:80]
            else:
                name = _clean_latex(name_raw)[:80].strip() or None
        return {
            'raw_latex': raw.strip(),
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
        }

    # -----------------------------------------------------------------------
    # R1: Bold-labeled definition blocks  {\bf Name:} ... or \textbf{Name:} ...
#     # -----------------------------------------------------------------------
#     for m in BF_LABEL_PATTERN.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name')
#         if _REFERENTIAL.search(full):
#             continue
#         r = _make_result(full, name_raw, 'BF_LABEL_PATTERN', m.start())
#         if r:
#             results.append(r)

    # -----------------------------------------------------------------------
    # R2: "X is called Y" definitional sentences
    # -----------------------------------------------------------------------
    for anchor_m in IS_CALLED_ANCHOR.finditer(text):
        if _inside_excluded_env(anchor_m.start(), anchor_m.end(), excluded_ranges):
            continue
        start_search = max(0, anchor_m.start() - 180)
        prefix = text[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        name_start = (start_search + dot_pos + 1) if dot_pos >= 0 else start_search
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 180:
            continue
        tail_m = IS_CALLED_TAIL.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        r = _make_result(full_text, name_text, 'IS_CALLED_ANCHOR', name_start)
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R3: "X are defined as \ba...\ea or \begin{align}...\end{align}"
    # -----------------------------------------------------------------------
    for m in ARE_DEFINED_AS_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group(0)
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        # Include surrounding sentence context
        # Look back to find sentence start
        start_search = max(0, m.start() - 200)
        prefix = text[start_search:m.start()]
        dot_pos = prefix.rfind('.')
        sent_start = (start_search + dot_pos + 1) if dot_pos >= 0 else start_search
        full_ext = text[sent_start:m.end()].strip()
        r = _make_result(full_ext, name_raw, 'ARE_DEFINED_AS_PATTERN', sent_start)
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R4: Named concept "is the <noun>" definitional sentence
#     # -----------------------------------------------------------------------
#     for m in NAMED_CONCEPT_IS_PATTERN.finditer(text):
#         if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
#             continue
#         full = m.group('full')
#         name_raw = m.group('name')
#         if not _NAMED_CONCEPT_KEYWORDS.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         if len(full) < 50:
#             continue
#         r = _make_result(full, name_raw, 'NAMED_CONCEPT_IS_PATTERN', m.start())
#         if r:
#             results.append(r)

    # -----------------------------------------------------------------------
    # R5: "X is a/an <structural noun> ..."
#     # -----------------------------------------------------------------------
#     for m in IS_A_STRUCTURAL_PATTERN.finditer(text):
#         if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
#             continue
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         emph = m.group('emph_name') if 'emph_name' in m.groupdict() else None
#         name_raw = emph if emph else m.group('name')
#         r = _make_result(full, name_raw, 'IS_A_STRUCTURAL_PATTERN', m.start())
#         if r:
#             results.append(r)

    # -----------------------------------------------------------------------
    # R6: "We (will) denote by X ..."
#     # -----------------------------------------------------------------------
#     for m in DENOTE_BY_PATTERN.finditer(text):
#         if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
#             continue
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         name_raw = m.group('name')
#         r = _make_result(full, name_raw, 'DENOTE_BY_PATTERN', m.start())
#         if r:
#             results.append(r)

    # -----------------------------------------------------------------------
    # R7: "X obeys ... (after \emph or {\em term})"
    # -----------------------------------------------------------------------
    for m in OBEYS_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        emph = m.group('emph_name') or m.group('em_name')
        r = _make_result(full, emph, 'OBEYS_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R8: "X stands for ..."
    # -----------------------------------------------------------------------
    for m in STANDS_FOR_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'STANDS_FOR_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R9: "Let $ ... $ denote ..."
#     # -----------------------------------------------------------------------
#     for m in LET_DENOTE_PATTERN.finditer(text):
#         if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
#             continue
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         name_raw = m.group('name')
#         r = _make_result(full, name_raw, 'LET_DENOTE_PATTERN', m.start())
#         if r:
#             results.append(r)

    # -----------------------------------------------------------------------
    # R10: "Introduce X ..." imperative
    # -----------------------------------------------------------------------
    for m in INTRODUCE_IMPERATIVE_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'INTRODUCE_IMPERATIVE_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R11: "we introduce ... called <name>: \begin{equation*}..."
    # -----------------------------------------------------------------------
    for m in INTRODUCE_CALLED_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'INTRODUCE_CALLED_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R12: "Denote by X ... \begin{equation*}..."
    # -----------------------------------------------------------------------
    for m in DENOTE_BY_EQUATION_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'DENOTE_BY_EQUATION_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R13: "the set \begin{equation} <name> = ..."
    # -----------------------------------------------------------------------
    for m in SET_EQUATION_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'SET_EQUATION_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R14: "We define X as/by ... \begin{gather*}...\end{gather*}"
    # -----------------------------------------------------------------------
    for m in DEFINE_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'DEFINE_ENV_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R15: "introduce X as $$...$$"
    # -----------------------------------------------------------------------
    for m in INTRODUCE_AS_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'INTRODUCE_AS_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R16: "X is given by \begin{equation}..."
    # -----------------------------------------------------------------------
    for m in GIVEN_BY_EQUATION_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        if not name_raw or len(name_raw) > 200:
            continue
        full = m.group(0)
        if _REFERENTIAL.search(full):
            continue
        # look back for sentence start
        start_search = max(0, m.start() - 100)
        prefix = text[start_search:m.start()]
        dot_pos = prefix.rfind('.')
        sent_start = (start_search + dot_pos + 1) if dot_pos >= 0 else start_search
        full_ext = text[sent_start:m.end()].strip()
        r = _make_result(full_ext, name_raw, 'GIVEN_BY_EQUATION_PATTERN', sent_start)
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R17: "define/denote X via \begin{equation}..."
    # -----------------------------------------------------------------------
    for m in DEFINE_VIA_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        if not name_raw:
            continue
        full = m.group(0)
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        r = _make_result(full, name_raw, 'DEFINE_VIA_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R18: "we can define X \begin{equation*}..."
    # -----------------------------------------------------------------------
    for m in DEFINE_EQ_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        if not name_raw:
            continue
        full = m.group(0)
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        r = _make_result(full, name_raw, 'DEFINE_EQ_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R19: "X is <property> if ... we have \begin{equation*}..."
    # -----------------------------------------------------------------------
    for m in PROPERTY_IF_WE_HAVE_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        name_raw = m.group('name').strip()
        if not name_raw:
            continue
        full = m.group(0)
        if _REFERENTIAL.search(full):
            continue
        r = _make_result(full, name_raw, 'PROPERTY_IF_WE_HAVE_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R20: "X is \emph{term} if ..."
    # -----------------------------------------------------------------------
    for m in EMPH_IF_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'EMPH_IF_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R21: "\emph{name} followed by align*/equation block"
    # -----------------------------------------------------------------------
    for m in EMPH_NAMED_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'EMPH_NAMED_ENV_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R22: "the <noun phrase> is $$...$$"
    # -----------------------------------------------------------------------
    for m in NOUN_IS_FORMULA_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        if not re.search(r'\$\$|\\\[', full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'NOUN_IS_FORMULA_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R23: "<sentence ending colon> $$...$$"
#     # -----------------------------------------------------------------------
#     for m in COLON_FORMULA_PATTERN.finditer(text):
#         if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
#             continue
#         full = m.group('full')
#         if not re.search(r'\$\$|\\\[', full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         name_raw = m.group('name')
#         if re.search(r'\\begin|\\end', name_raw):
#             continue
#         r = _make_result(full, name_raw, 'COLON_FORMULA_PATTERN', m.start())
#         if r:
#             results.append(r)

    # -----------------------------------------------------------------------
    # R24: "we consider <name> $$...$$ ..."
    # -----------------------------------------------------------------------
    for m in WE_CONSIDER_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'WE_CONSIDER_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # R25: "X (also called Y) is ..."
    # -----------------------------------------------------------------------
    for m in ALSO_CALLED_PATTERN.finditer(text):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name')
        r = _make_result(full, name_raw, 'ALSO_CALLED_PATTERN', m.start())
        if r:
            results.append(r)

    # -----------------------------------------------------------------------
    # Deduplication: remove overlapping / near-duplicate matches
    # -----------------------------------------------------------------------
    results = _deduplicate(results, text)
    return results


def _deduplicate(results: List[dict], text: str) -> List[dict]:
    """Remove overlapping and near-duplicate results, keeping higher-priority ones."""
    if not results:
        return results

    # Attach position info for overlap detection
    positioned = []
    for r in results:
        raw = r['raw_latex']
        pos = text.find(raw)
        if pos < 0:
            # Try with stripped
            pos = text.find(raw.strip())
        positioned.append((pos, pos + len(raw) if pos >= 0 else -1, r))

    # Sort by priority (lower = better), then by position, then by length (longer = better)
    def sort_key(item):
        pos, end, r = item
        prio = _RULE_PRIORITY.get(r['rule_name'], 99)
        length = end - pos if pos >= 0 else 0
        return (prio, pos, -length)

    positioned.sort(key=sort_key)

    kept = []
    kept_ranges = []  # list of (start, end) for kept items

    for pos, end, r in positioned:
        if pos < 0:
            kept.append(r)
            continue
        # Check overlap with already kept ranges
        overlap = False
        for (ks, ke) in kept_ranges:
            # Significant overlap: more than 50% of the shorter one
            overlap_len = max(0, min(end, ke) - max(pos, ks))
            shorter = min(end - pos, ke - ks)
            if shorter > 0 and overlap_len / shorter > 0.5:
                overlap = True
                break
        if not overlap:
            kept.append(r)
            kept_ranges.append((pos, end))

    # Also deduplicate by clean_text similarity
    final = []
    seen_texts = []
    for r in kept:
        ct = (r.get('clean_text') or '').strip().lower()
        if not ct:
            final.append(r)
            continue
        is_dup = False
        for prev in seen_texts:
            if ct in prev or prev in ct:
                is_dup = True
                break
            min_len = min(len(ct), len(prev))
            if min_len > 40 and ct[:40] == prev[:40]:
                is_dup = True
                break
        if not is_dup:
            final.append(r)
            seen_texts.append(ct)

    return final
