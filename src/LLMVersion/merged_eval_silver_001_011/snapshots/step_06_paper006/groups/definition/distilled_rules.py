import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Minimal LaTeX -> plain-text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common LaTeX commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb|mathsf|hat|tilde|bar|vec|widehat|widetilde|overline|underline|operatorname)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:left|right|big|Big|bigg|Bigg)\s*[\[\](){}|.]', '', text)
    text = re.sub(r'\{\\(?:bf|it|em|rm|tt|sf|sc)\s+([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:bf|it|em|rm|tt|sf|sc)\b', '', text)
    text = re.sub(r'\\(?:label|ref|eqref|cite|citeA|citep|citet|citealt|Cite[A-Za-z]*)\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:noindent|centering|raggedright|raggedleft|small|large|Large|LARGE|huge|Huge|normalsize|footnotesize|scriptsize|tiny)\b', '', text)
    text = re.sub(r'\\(?:vspace|hspace|vskip|hskip)\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:medskip|bigskip|smallskip|newline|linebreak|pagebreak|clearpage)\b', ' ', text)
    text = re.sub(r'\\\\', ' ', text)
    text = re.sub(r'\\,|\\;|\\:|\\!|\\quad|\\qquad', ' ', text)
    text = re.sub(r'\\begin\{[^}]*\}|\\end\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:ba|ea)\b', '', text)
    text = re.sub(r'\\\[|\\\]', '', text)
    text = re.sub(r'\\[a-zA-Z]+\*?\s*', '', text)
    text = re.sub(r'[{}]', '', text)
    text = re.sub(r'\$\$?(.*?)\$\$?', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments to exclude (proofs, theorems, etc. — we don't want to
# re-extract definitions that are part of these)
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|'
    r'proposition|Proposition|prop|corollary|Corollary|cor|'
    r'claim|Claim|conjecture|Conjecture|example|Example|'
    r'exercise|Exercise|remark|Remark|rem)\}',
    flags=re.IGNORECASE,
)

_EXCLUDED_ENV_BODY = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|'
    r'proposition|Proposition|prop|corollary|Corollary|cor|'
    r'claim|Claim|conjecture|Conjecture|example|Example|'
    r'exercise|Exercise|remark|Remark|rem)\}'
    r'.*?'
    r'\\end\{\1\}',
    flags=re.IGNORECASE | re.DOTALL,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) character ranges that are inside excluded environments."""
    ranges = []
    for m in _EXCLUDED_ENV_BODY.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if [start, end) overlaps any excluded range."""
    for (es, ee) in excluded_ranges:
        if start < ee and end > es:
            return True
    return False


def _normalize(text: str, max_len: int = 80) -> str:
    t = _clean_latex(text).strip()
    if len(t) > max_len:
        t = t[:max_len]
    return t


def _extract_name(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r'\$(.+?)\$', raw)
    if m:
        return _normalize(m.group(1), 80)
    return _normalize(_clean_latex(raw), 80)


# ---------------------------------------------------------------------------
# Negative / filter patterns
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

_DEF_KEYWORDS = re.compile(
    r'\b(set|function|map|mapping|sequence|matrix|space|operator|'
    r'define|denote|notation|collection|family|class|group|ring|field|'
    r'graph|path|tree|partition|permutation|morphism|homomorphism|'
    r'distance|measure|distribution|probability|risk|estimator|'
    r'eigenvalue|correlation|norm|entropy|divergence|information)\b',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Module-level compiled patterns (rule_name = variable name)
# ---------------------------------------------------------------------------

# R1: Bold-label definitions: {\bf Name:} or \textbf{Name:} followed by body
# Captures definitions introduced with a bold header label
# PRUNED — FP on paper001, paper002, paper003 +2 more | also 3 TP — review before uncommenting
# BOLD_LABEL_DEF = re.compile(
#     r'(?:'
#     r'\{\\bf\s+(?P<name1>[^}:]{1,120}?)(?::?\s*\}|\}:?)'
#     r'|\\textbf\{(?P<name2>[^}:]{1,120}?)(?::?\s*\}|\}:?)'
#     r')'
#     r'[ \t]*(?:\\\\)?[ \t]*\n?'
#     r'(?P<body>(?:[^\n]|\n(?!\s*\n)|\n\s*\n(?!\s*\n)){30,1200}?)'
#     r'(?=\n\s*\n|\{\\bf\s|\\textbf\{|\\\\\s*\n?(?:\s*\n\s*\n|\{\\bf)|'
#     r'\\(?:sub)*section|\\begin\{|\\end\{document\}|$)',
#     flags=re.DOTALL,
# )

# R2: "X is called Y" - definitional sentences
IS_CALLED_DEF = re.compile(
    r'(?P<pre>[^.]{0,120}?)'
    r'\bis\s+called\b'
    r'(?P<post>(?:[^.]|\\.){0,400}?\.)',
    flags=re.DOTALL,
)

# R3: "are defined as" extended (plural form + display math)
ARE_DEFINED_AS_DEF = re.compile(
    r'(?P<pre>[^.]{0,200}?)'
    r'\b(?:is|are)\s+defined\s+(?:as|to\s+be)\b'
    r'(?P<post>'
    r'(?:'
    r'(?:.*?\\ba.*?\\ea)'
    r'|(?:.*?\\begin\{(?:align|equation|gather|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|eqnarray)\*?\})'
    r'|(?:.*?\\[.*?\\])'
    r'|(?:.*?\$\$.*?\$\$)'
    r'|(?:[^.]{0,600}?\.)'
    r')'
    r')',
    flags=re.DOTALL,
)

# R4: "We denote by X ..." or "We will denote by X ..."
# PRUNED — FP on paper003, paper004
# DENOTE_BY_DEF = re.compile(
#     r'(?P<full>'
#     r'(?:We\s+)?(?:will\s+)?(?:also\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|\$\$[^$]+\$\$|[A-Za-z0-9\\{}_^, ]{1,80}))'
#     r'(?:[^.\\]{0,300}?'
#     r'(?:\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
#     r'|\$\$.*?\$\$|\\\[.*?\\\]'
#     r'|[^.]{0,200}?\.))'
#     r')',
#     flags=re.DOTALL,
# )

# R5: "X stands for ..." / "The notation X stands for ..."
STANDS_FOR_DEF = re.compile(
    r'(?P<full>'
    r'(?:The\s+notation\s+)?'
    r'(?P<name>(?:\$[^$]+\$|\$\$[^$]+\$\$|[A-Za-z0-9\\{}_^, ]{1,80}?))'
    r'\s+stands\s+for\b'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}'
    r'|[^.]{0,400}?\.))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R6: "Let $...$ denote ..." or "Let X denote ..."
# PRUNED — FP on paper003, paper006 | also 1 TP — review before uncommenting
# LET_DENOTE_DEF = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$\$[^$]*\$\$|\$[^$]+\$|[A-Za-z][A-Za-z0-9\\_{}, ]{0,60}))'
#     r'(?:[^.]{0,300}?)'
#     r'\bdenote\b'
#     r'(?:\$\$.*?\$\$|\\\[.*?\\\]'
#     r'|\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}'
#     r'|[^.]{0,400}?\.))',
#     flags=re.DOTALL,
# )

# R7: "Introduce X ..." - definitional imperative with display math
INTRODUCE_DEF = re.compile(
    r'(?P<full>'
    r'\bIntroduce\b\s+'
    r'(?P<name>[^.$\n\\]{1,80}?)'
    r'\s*'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\})'
    r'(?:[^.]{0,300}?\.)?)',
    flags=re.DOTALL,
)

# R8: "we introduce ... call(ed) <name>: equation_env"
INTRODUCE_CALLED_DEF = re.compile(
    r'(?P<full>'
    r'\bwe\s+introduce\b[^.\\]{0,200}?'
    r'(?:call(?:ed)?)\s+'
    r'(?:\{\\it\s+|\{\\em\s+|\\emph\{)?'
    r'(?P<name>[^}.\n]{1,80})'
    r'(?:\})?\s*:?\s*'
    r'(?:\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\]))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R9: "Denote by X ... called <name> ... equation_env"
DENOTE_BY_CALLED_DEF = re.compile(
    r'(?P<full>'
    r'\bDenote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ]{1,80}))'
    r'[^\\]{0,400}?'
    r'(?:\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\]))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R10: "we consider <name> $$ ... $$" definitional
WE_CONSIDER_DEF = re.compile(
    r'(?P<full>'
    r'\bwe\s+consider\b\s+'
    r'(?P<name>[^.$\n\\]{1,120}?)'
    r'\s*'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\})'
    r'(?:[^.]{0,400}?\.)?)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R11: "the set \begin{equation} name = ... \end{equation} is non-empty"
SET_EQUATION_DEF = re.compile(
    r'(?P<full>'
    r'\bthe\s+set\b[^\\]{0,200}?'
    r'\\begin\{equation[^}]*\}'
    r'[^\\]*?'
    r'(?P<name>\\?[A-Za-z][A-Za-z0-9_{}^\\]*\s*=)'
    r'.*?'
    r'\\end\{equation[^}]*\})',
    flags=re.IGNORECASE | re.DOTALL,
)

# R12: "We define X as \begin{gather*}...\end{gather*}" - define with env body
DEFINE_ENV_BODY_DEF = re.compile(
    r'(?P<full>'
    r'(?:We\s+)?(?:also\s+)?[Dd]efine\s+'
    r'(?P<name>[^.\\]{1,100}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?:\\begin\{(?:gather|align|equation|eqnarray|array)\*?\}.*?\\end\{(?:gather|align|equation|eqnarray|array)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\]))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R13: "introduce X as $$...$$" or "introduce X as \[...\]"
INTRODUCE_AS_DEF = re.compile(
    r'(?P<full>'
    r'\bintroduce\s+'
    r'(?P<name>[^.\\]{1,100}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}))',
    flags=re.IGNORECASE | re.DOTALL,
)

# R14: "X is given by \begin{equation}...\end{equation}"
IS_GIVEN_BY_DEF = re.compile(
    r'(?P<name>[^.\n]{1,200}?)'
    r'\s+is\s+given\s+by\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])',
    flags=re.IGNORECASE | re.DOTALL,
)

# R15: Sentence leading into an equation block containing \defeq/\argmin
# "... optimization problem / ... by solving ..." + equation with \defeq
OPTIM_PROBLEM_DEF = re.compile(
    r'(?P<name>[^.\n]{1,300}?)'
    r'(?:optimization\s+problem|by\s+solving[^.]{0,100}?problem|'
    r'based\s+on\s+estimating[^.]{0,150}?solving[^.]{0,100}?problem)'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\})',
    flags=re.IGNORECASE | re.DOTALL,
)

# R16: "define X via \begin{equation}...\end{equation}"
DEFINE_VIA_DEF = re.compile(
    r'(?:we\s+)?(?:also\s+)?(?:can\s+)?(?:define|denote)\s+'
    r'(?P<name>[^.\n\\]{1,150}?)'
    r'\s+via\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\])',
    flags=re.IGNORECASE | re.DOTALL,
)

# R17: "we can define X \begin{equation*}...\end{equation*}" (no 'as/by' keyword)
DEFINE_DIRECTLY_DEF = re.compile(
    r'(?:we\s+)?(?:can\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\n\\]{1,150}?)'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\})',
    flags=re.IGNORECASE | re.DOTALL,
)

# R18: "X is <property> ... if ... we have \begin{equation*}...\end{equation*}"
PROPERTY_IF_WE_HAVE_DEF = re.compile(
    r'(?P<name>(?:[A-Z$\\][^.\n]{0,100}?))'
    r'\s+is\s+[^.\n]{0,150}?\bif\b[^.\n]{0,150}?\bwe\s+have\b'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\}'
    r'|\\begin\{align\*?\}.*?\\end\{align\*?\})',
    flags=re.DOTALL,
)

# R19: "a \emph{term}; term is a given collection ..." emph + is-a definition
EMPH_IS_A_DEF = re.compile(
    r'(?P<full>'
    r'(?:\\emph\{(?P<emph1>[^}]+)\}|\{\\em\s+(?P<emph2>[^}]+)\})'
    r'[^.;]{0,60}?[;,]\s*'
    r'(?P<body_name>[A-Za-z][A-Za-z0-9 \-]{1,60}?)'
    r'\s+is\s+(?:a|an|the)\s+(?:given\s+)?'
    r'(?:collection|set|sequence|map|mapping|function|family|class|space|operator|'
    r'matrix|vector|graph|code|measure|distribution|process|transform|pair|triple|'
    r'tuple|list|array|structure|object|element|member|subset|subspace|module|'
    r'lattice|order|relation|partition|basis|frame|system|scheme|variety|manifold|'
    r'surface|curve|form|tensor|functional|filter|ideal|kernel|image|morphism|'
    r'functor|adjunction|limit|product|model|theory|language|formula|sentence|'
    r'proof|argument|algorithm|procedure|protocol|strategy|policy|rule|criterion|'
    r'condition|property|invariant|characteristic|feature|parameter|variable|'
    r'constant|symbol|notation|abbreviation|term|notion|concept|definition)'
    r'\b'
    r'(?:[^.]){0,400}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R20: "a {\em term} obeys PROPERTY ... if [equation]"
OBEYS_PROPERTY_DEF = re.compile(
    r'(?P<full>'
    r'(?:a\s+)?(?:\\emph\{(?P<emph1>[^}]+)\}|\{\\em\s+(?P<emph2>[^}]+)\})'
    r'[^.]{0,150}?'
    r'\bobeys\b'
    r'(?:[^.\\]|\\(?!begin|end)){0,300}?'
    r'(?:\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\]|\.)'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R21: Section paragraph definitions - paragraph right after \section/\subsection
# that contains definitional language
# PRUNED — FP on paper001, paper003, paper005 +1 more | also 2 TP — review before uncommenting
# SECTION_PARA_DEF = re.compile(
#     r'(?:\\(?:sub)*section\*?\{[^}]*\})'
#     r'(?:\s*%[^\n]*\n)*'
#     r'(?:\s*\\label\{[^}]*\}\s*)?'
#     r'(?:\s*%[^\n]*\n)*'
#     r'\s*'
#     r'(?P<full>'
#     r'(?P<name>[^\n.]{1,120})'
#     r'(?:(?!\\(?:sub)*section|\\begin\{|\\end\{document\}|\n\s*\n\s*\n).){60,2000}?'
#     r')'
#     r'(?=\n\s*\n\s*\n|\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

_SECTION_DEF_KEYWORDS = re.compile(
    r'\b(define[sd]?|definition|notation|denote[sd]?|call(?:ed)?|refer\s+to\s+as|'
    r'known\s+as|represent[s]?|consists?\s+of|form\s+of\s+the|'
    r'we\s+(?:say|use|write)|stands?\s+for|is\s+called|we\s+connect|'
    r'goal\s+is\s+to|intuitive\s+goal)\b',
    flags=re.IGNORECASE,
)

# R22: "The commute distance ... is the expected time ..."
# Generic: "The X (also called Y) is <definition noun phrase>"
# PRUNED — FP on paper005
# THE_X_IS_DEF = re.compile(
#     r'(?P<full>'
#     r'(?:The\s+)'
#     r'(?P<name>[A-Z][^.()]{2,100}?)'
#     r'(?:\s*\([^)]{1,80}\))?'
#     r'\s+(?:is|are|refers?\s+to|denotes?)\s+the\s+'
#     r'(?:[^.\\]|\\.){20,500}?'
#     r'\.)',
#     flags=re.DOTALL,
# )

_THE_X_IS_KEYWORDS = re.compile(
    r'\b(expected|defined|denoted|notation|refers?\s+to|known\s+as|'
    r'called|probability|distance|measure|number|set|function|matrix|'
    r'time|cost|weight|sum|product|minimum|maximum|average|mean)\b',
    flags=re.IGNORECASE,
)

# R23: "A subset ... is connected if ..." / property definitions
# More general "X if any/all ..." pattern for connectivity-style definitions
# PRUNED — FP on paper001
# CONNECTIVITY_DEF = re.compile(
#     r'(?P<full>'
#     r'(?:A|An)\s+'
#     r'(?P<name>[^.]{2,80}?)'
#     r'\s+is\s+(?:connected|complete|compact|bounded|closed|open|'
#     r'convex|concave|monotone|increasing|decreasing|differentiable|'
#     r'continuous|measurable|integrable|summable|finite|infinite|'
#     r'countable|dense|separable|complete|path-connected|simply\s+connected)'
#     r'\s+if\s+'
#     r'(?:[^.\\]|\\.){10,400}?'
#     r'\.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Priority map for deduplication
# ---------------------------------------------------------------------------

_RULE_PRIORITY = {
    # Lower number = higher priority (kept over higher-number duplicates)
    'BOLD_LABEL_DEF': 1,
    'ARE_DEFINED_AS_DEF': 1,
    'IS_GIVEN_BY_DEF': 1,
    'DENOTE_BY_DEF': 1,
    'DENOTE_BY_CALLED_DEF': 1,
    'INTRODUCE_CALLED_DEF': 1,
    'LET_DENOTE_DEF': 2,
    'INTRODUCE_DEF': 2,
    'INTRODUCE_AS_DEF': 2,
    'DEFINE_ENV_BODY_DEF': 2,
    'DEFINE_VIA_DEF': 2,
    'DEFINE_DIRECTLY_DEF': 2,
    'OPTIM_PROBLEM_DEF': 2,
    'PROPERTY_IF_WE_HAVE_DEF': 2,
    'STANDS_FOR_DEF': 2,
    'WE_CONSIDER_DEF': 2,
    'SET_EQUATION_DEF': 2,
    'OBEYS_PROPERTY_DEF': 2,
    'EMPH_IS_A_DEF': 2,
    'IS_CALLED_DEF': 3,
    'THE_X_IS_DEF': 3,
    'CONNECTIVITY_DEF': 3,
    'SECTION_PARA_DEF': 3,
    'DENOTE_BY_DEF': 1,
}


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX source text.
    Returns list of dicts with keys:
      raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    excluded_ranges = _build_excluded_ranges(text)

    def _make_result(raw: str, name_raw: str, rule_name: str, pos: int) -> dict:
        name = _extract_name(name_raw) if name_raw else None
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_pos': pos,
        }

    def _add(raw: str, name_raw: str, rule_name: str, pos: int):
        if not raw or len(raw.strip()) < 20:
            return
        if _inside_excluded_env(pos, pos + len(raw), excluded_ranges):
            return
        results.append(_make_result(raw, name_raw, rule_name, pos))

    # -----------------------------------------------------------------------
    # R1: Bold-label definitions
#     # -----------------------------------------------------------------------
#     for m in BOLD_LABEL_DEF.finditer(text):
#         name_raw = m.group('name1') or m.group('name2') or ''
#         body = m.group('body') or ''
#         full = m.group(0)
#         if _REFERENTIAL.search(full):
#             continue
#         if len(body.strip()) < 20:
#             continue
#         _add(full, name_raw, 'BOLD_LABEL_DEF', m.start())

    # -----------------------------------------------------------------------
    # R2: "X is called Y"
    # -----------------------------------------------------------------------
    for m in IS_CALLED_DEF.finditer(text):
        pre = m.group('pre') or ''
        post = m.group('post') or ''
        full = (pre + ' is called' + post).strip()
        if _REFERENTIAL.search(full):
            continue
        # Skip trivial matches
        if len(full) < 30:
            continue
        # name is the subject (pre part)
        # find sentence start in pre
        dot_pos = pre.rfind('.')
        if dot_pos >= 0:
            name_raw = pre[dot_pos+1:].strip()
        else:
            name_raw = pre.strip()
        if len(name_raw) > 150:
            continue
        _add(full, name_raw, 'IS_CALLED_DEF', m.start())

    # -----------------------------------------------------------------------
    # R3: "are/is defined as" (extended, handles display math)
    # -----------------------------------------------------------------------
    for m in ARE_DEFINED_AS_DEF.finditer(text):
        pre = m.group('pre') or ''
        post = m.group('post') or ''
        full = (pre + ' are defined as' + post).strip()
        if _REFERENTIAL.search(full):
            continue
        if _C1_NEGATIVE.search(full):
            continue
        # Extract name from pre
        dot_pos = pre.rfind('.')
        if dot_pos >= 0:
            name_raw = pre[dot_pos+1:].strip()
        else:
            name_raw = pre.strip()
        if len(name_raw) > 200:
            continue
        _add(full, name_raw, 'ARE_DEFINED_AS_DEF', m.start())

    # -----------------------------------------------------------------------
    # R4: "We denote by X ..."
#     # -----------------------------------------------------------------------
#     for m in DENOTE_BY_DEF.finditer(text):
#         full = m.group('full') or m.group(0)
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         _add(full, name_raw, 'DENOTE_BY_DEF', m.start())

    # -----------------------------------------------------------------------
    # R5: "X stands for ..."
    # -----------------------------------------------------------------------
    for m in STANDS_FOR_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'STANDS_FOR_DEF', m.start())

    # -----------------------------------------------------------------------
    # R6: "Let X denote ..."
#     # -----------------------------------------------------------------------
#     for m in LET_DENOTE_DEF.finditer(text):
#         full = m.group('full') or m.group(0)
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'LET_DENOTE_DEF', m.start())

    # -----------------------------------------------------------------------
    # R7: "Introduce X ..." (imperative with display math)
    # -----------------------------------------------------------------------
    for m in INTRODUCE_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'INTRODUCE_DEF', m.start())

    # -----------------------------------------------------------------------
    # R8: "we introduce ... called <name>: equation"
    # -----------------------------------------------------------------------
    for m in INTRODUCE_CALLED_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'INTRODUCE_CALLED_DEF', m.start())

    # -----------------------------------------------------------------------
    # R9: "Denote by X ... called <name> ... equation"
    # -----------------------------------------------------------------------
    for m in DENOTE_BY_CALLED_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'DENOTE_BY_CALLED_DEF', m.start())

    # -----------------------------------------------------------------------
    # R10: "we consider <name> $$ ... $$"
    # -----------------------------------------------------------------------
    for m in WE_CONSIDER_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        if not _DEF_KEYWORDS.search(full):
            continue
        _add(full, name_raw, 'WE_CONSIDER_DEF', m.start())

    # -----------------------------------------------------------------------
    # R11: "the set \begin{equation} name = ... \end{equation}"
    # -----------------------------------------------------------------------
    for m in SET_EQUATION_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'SET_EQUATION_DEF', m.start())

    # -----------------------------------------------------------------------
    # R12: "We define X as \begin{gather*}...\end{gather*}"
    # -----------------------------------------------------------------------
    for m in DEFINE_ENV_BODY_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        name_raw = m.group('name') or ''
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'DEFINE_ENV_BODY_DEF', m.start())

    # -----------------------------------------------------------------------
    # R13: "introduce X as $$...$$"
    # -----------------------------------------------------------------------
    for m in INTRODUCE_AS_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'INTRODUCE_AS_DEF', m.start())

    # -----------------------------------------------------------------------
    # R14: "X is given by \begin{equation}..."
    # -----------------------------------------------------------------------
    for m in IS_GIVEN_BY_DEF.finditer(text):
        name_raw = m.group('name') or ''
        body = m.group('body') or ''
        # name_raw must be non-trivial
        if not name_raw.strip() or len(name_raw.strip()) > 200:
            continue
        # Sentence boundary: take part after last period in name_raw
        dot_pos = name_raw.rfind('.')
        if dot_pos >= 0:
            name_raw = name_raw[dot_pos+1:].strip()
        full = m.group(0)
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'IS_GIVEN_BY_DEF', m.start())

    # -----------------------------------------------------------------------
    # R15: optimization problem + equation containing \defeq/\argmin
    # -----------------------------------------------------------------------
    for m in OPTIM_PROBLEM_DEF.finditer(text):
        body = m.group('body') or ''
        if not re.search(r'\\(?:defeq|argmin|triangleq|coloneqq|in\s*\\argmin)', body):
            continue
        name_raw = m.group('name') or ''
        dot_pos = name_raw.rfind('.')
        if dot_pos >= 0:
            name_raw = name_raw[dot_pos+1:].strip()
        full = m.group(0)
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'OPTIM_PROBLEM_DEF', m.start())

    # -----------------------------------------------------------------------
    # R16: "define X via \begin{equation}..."
    # -----------------------------------------------------------------------
    for m in DEFINE_VIA_DEF.finditer(text):
        name_raw = m.group('name') or ''
        full = m.group(0)
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'DEFINE_VIA_DEF', m.start())

    # -----------------------------------------------------------------------
    # R17: "we can define X \begin{equation*}..."
    # -----------------------------------------------------------------------
    for m in DEFINE_DIRECTLY_DEF.finditer(text):
        name_raw = m.group('name') or ''
        full = m.group(0)
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'DEFINE_DIRECTLY_DEF', m.start())

    # -----------------------------------------------------------------------
    # R18: "X is <property> ... if ... we have \begin{equation*}..."
    # -----------------------------------------------------------------------
    for m in PROPERTY_IF_WE_HAVE_DEF.finditer(text):
        name_raw = m.group('name') or ''
        full = m.group(0)
        if _REFERENTIAL.search(full):
            continue
        if len(name_raw.strip()) > 120:
            continue
        _add(full, name_raw, 'PROPERTY_IF_WE_HAVE_DEF', m.start())

    # -----------------------------------------------------------------------
    # R19: "\emph{term}; term is a <type>..."
    # -----------------------------------------------------------------------
    for m in EMPH_IS_A_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        emph = m.group('emph1') or m.group('emph2') or m.group('body_name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, emph, 'EMPH_IS_A_DEF', m.start())

    # -----------------------------------------------------------------------
    # R20: "a {\em term} obeys PROPERTY..."
    # -----------------------------------------------------------------------
    for m in OBEYS_PROPERTY_DEF.finditer(text):
        full = m.group('full') or m.group(0)
        emph = m.group('emph1') or m.group('emph2') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, emph, 'OBEYS_PROPERTY_DEF', m.start())

    # -----------------------------------------------------------------------
    # R21: Section paragraph definitions
#     # -----------------------------------------------------------------------
#     for m in SECTION_PARA_DEF.finditer(text):
#         full = m.group('full') or ''
#         name_raw = m.group('name') or ''
#         if not _SECTION_DEF_KEYWORDS.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if len(full.strip()) < 60:
#             continue
#         _add(full, name_raw, 'SECTION_PARA_DEF', m.start())

    # -----------------------------------------------------------------------
    # R22: "The X (also called Y) is the <definition>"
#     # -----------------------------------------------------------------------
#     for m in THE_X_IS_DEF.finditer(text):
#         full = m.group('full') or m.group(0)
#         name_raw = m.group('name') or ''
#         if not _THE_X_IS_KEYWORDS.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if len(full) < 40:
#             continue
#         _add(full, name_raw, 'THE_X_IS_DEF', m.start())

    # -----------------------------------------------------------------------
    # R23: "A/An X is connected/compact/... if ..."
#     # -----------------------------------------------------------------------
#     for m in CONNECTIVITY_DEF.finditer(text):
#         full = m.group('full') or m.group(0)
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'CONNECTIVITY_DEF', m.start())

    # -----------------------------------------------------------------------
    # Deduplication: remove overlapping matches, keeping higher-priority ones
    # -----------------------------------------------------------------------
    if not results:
        return results

    # Sort by priority then position
    results.sort(key=lambda r: (_RULE_PRIORITY.get(r['rule_name'], 9), r['_pos']))

    deduped: List[dict] = []
    kept_ranges: List[tuple] = []  # (start, end) of kept matches

    for r in results:
        pos = r['_pos']
        raw = r['raw_latex']
        end = pos + len(raw)
        raw_lower = (r['clean_text'] or '').strip().lower()

        # Check for positional overlap with already-kept results
        overlaps = False
        for (ks, ke) in kept_ranges:
            if pos < ke and end > ks:
                overlaps = True
                break

        if overlaps:
            continue

        # Check for text similarity overlap
        is_dup = False
        for prev in deduped:
            prev_ct = (prev['clean_text'] or '').strip().lower()
            if not prev_ct or not raw_lower:
                continue
            if raw_lower in prev_ct or prev_ct in raw_lower:
                is_dup = True
                break
            min_len = min(len(raw_lower), len(prev_ct))
            if min_len > 40 and raw_lower[:40] == prev_ct[:40]:
                is_dup = True
                break

        if not is_dup:
            deduped.append(r)
            kept_ranges.append((pos, end))

    # Remove internal _pos key
    for r in deduped:
        r.pop('_pos', None)

    for r in deduped:
        r.pop('_start', None)

    return deduped
