import re
from typing import List, Dict

try:
    from latex_clean import clean_latex_to_text as _clean_latex
except Exception:
    _clean_latex = lambda s: s

# ---------------------------------------------------------------------------
# Excluded environment helper
# ---------------------------------------------------------------------------

_EXCLUDED_ENV_PATTERN = re.compile(
    r"\\begin\{("
    r"proof|theorem|lemma|proposition|corollary|claim|conjecture|"
    r"algorithm|algorithmic|algorithm2e|verbatim|lstlisting|minted|"
    r"figure|table"
    r")\}.*?\\end\{\1\}",
    flags=re.DOTALL | re.IGNORECASE,
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Shared sub-patterns
# ---------------------------------------------------------------------------

_DISPLAY_MATH = (
    r"(?:\\\[.*?\\\]"
    r"|\$\$.*?\$\$"
    r"|\\begin\{equation\*?\}.*?\\end\{equation\*?\}"
    r"|\\begin\{align\*?\}.*?\\end\{align\*?\}"
    r"|\\begin\{eqnarray\*?\}.*?\\end\{eqnarray\*?\}"
    r"|\\begin\{multline\*?\}.*?\\end\{multline\*?\}"
    r")"
)

_REFERENTIAL = re.compile(
    r"\b(?:defined?\s+)?(?:below|above|right|left|"
    r"in\s+the\s+(?:next|previous|following|preceding)\s+"
    r"(?:section|chapter|subsection|paragraph))\b",
    flags=re.IGNORECASE,
)

_C1_NEGATIVE = re.compile(
    r"\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|"
    r"Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|"
    r"as\s+(?:before|above|below|follows)|defined\s+(?:above|below|"
    r"earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|"
    r"in\s+Equation|in\s+Definition))\b",
    flags=re.IGNORECASE,
)

# Tail after an anchor: can cross display math environments and plain non-period chars
_C2_TAIL = re.compile(
    r"(?:"
    + _DISPLAY_MATH
    + r"|[^.])*\.",
    flags=re.DOTALL,
)

# Extended tail that also crosses arbitrary LaTeX environments
_C2_TAIL_ENV = re.compile(
    r"(?:(?:\\begin\{[^}]+\}.*?\\end\{[^}]+\})"
    r"|\$\$.*?\$\$"
    r"|\\\[.*?\\\]"
    r"|[^.])*\.",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# R1: 'is then defined as / is defined as / is defined to be' + display math tail
R1_IS_DEFINED_AS_DISPLAY = re.compile(
    r"\bis\s+(?:then\s+)?defined\s+(?:as|to\s+be|in\s+terms\s+of|by)\s*[,]?\s*",
    flags=re.IGNORECASE,
)

# R2: 'We use X as/to represent/to denote ...' definitional sentence
# PRUNED — FP on 1512.05406v1, 1811.04151v1 | also 1 TP — review before uncommenting
# R2_WE_USE_AS = re.compile(
#     r"(?P<full>"
#     r"We\s+use\s+"
#     r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_ ,\{\}]{1,80}?))"
#     r"\s+(?:as|to\s+represent|to\s+denote)\s+"
#     r"(?:" + _DISPLAY_MATH + r"|[^.])*\.)",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R3: 'X is used as/to represent' anchor-based
# PRUNED — FP on 1207.0773v2, 1512.05406v1 | also 1 TP — review before uncommenting
# R3_IS_USED_AS = re.compile(
#     r"\bis\s+used\s+(?:as|to\s+represent|to\s+denote)\s",
#     flags=re.IGNORECASE,
# )

# R4: 'X is called (the/a/an) <name>' anchor-based
R4_IS_CALLED = re.compile(
    r"\bis\s+called\s+(?:the\s+|a\s+|an\s+)?",
    flags=re.IGNORECASE,
)

# R5: 'X are/is considered as \textit{term}' or \emph{term}
R5_CONSIDERED_AS = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.]{1,200}?)"
    r"\s+(?:is|are)\s+considered\s+as\s+"
    r"(?:\\textit\{[^}]+\}|\\emph\{[^}]+\}|\\textbf\{[^}]+\})"
    r"(?:" + _DISPLAY_MATH + r"|[^.])*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R6: 'X ...; that is, \begin{equation*}...\end{equation*} where ...'
R6_THAT_IS_EQUATION = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.\n]{1,200}?)"
    r"(?:;|,)?\s*that\s+is,?\s*"
    r"(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\}"
    r"|\\\[.*?\\\]"
    r"|\$\$.*?\$\$)"
    r"(?:\s*where\b(?:" + _DISPLAY_MATH + r"|[^.])*\.)?"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)

# R7: \item entries inside itemize with a label + display equation
R7_ITEMIZE_ENV = re.compile(
    r"\\begin\{itemize\}(.*?)\\end\{itemize\}",
    flags=re.DOTALL,
)
R7_ITEM_SPLIT = re.compile(r"\\item\b", flags=re.DOTALL)
R7_ITEM_LABEL = re.compile(
    r"^\s*(?:\\textbf\{(?P<label1>[^}]+)\}|(?P<label2>[A-Z][^.\n]{0,80}?))\.\s*(?P<body>.+)$",
    flags=re.DOTALL,
)
R7_HAS_DISPLAY = re.compile(
    r"\\begin\{equation\*?\}|\\\[|\$\$",
    flags=re.DOTALL,
)

# R8: '\textit{X} means that ...'
R8_MEANS_THAT = re.compile(
    r"(?P<full>"
    r"(?:\\textit\{|\\emph\{)(?P<name>[^}]{1,80})\}"
    r"\s+(?:of\s+[^.]{0,60}\s+)?means\s+that\s+"
    r"(?:" + _DISPLAY_MATH + r"|[^.])*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R9: 'The <TERM> of X is \begin{equation*}...\end{equation*}'
R9_IS_EQUATION = re.compile(
    r"(?P<full>"
    r"(?:The\s+)?(?:\\emph\{|\\textit\{|\\textbf\{)?(?P<name>[A-Za-z][A-Za-z\s\-]{1,60})(?:\})?"
    r"(?:\s+\([A-Z]{2,10}\))?"
    r"[^.]{0,300}?\bis\b\s*"
    r"(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\}"
    r"|\\\[.*?\\\]"
    r"|\$\$.*?\$\$)"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)

# R10: 'we call [that] <description> <term>' — term at end before period
# PRUNED — FP on 1103.5544v1, 1502.03482v2, 1601.01819v1 | also 2 TP — review before uncommenting
# R10_WE_CALL_END = re.compile(
#     r"(?P<full>"
#     r"(?:We\s+)?\bcall\b\s+(?:that\s+)?"
#     r"(?:" + _DISPLAY_MATH + r"|[^.]){0,300}?"
#     r"\s+(?P<name>[A-Za-z][A-Za-z\s\-]{1,60})\s*\.)",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R11: 'We call ... as (a/an) \emph{NAME}.'
R11_WE_CALL_EMPH = re.compile(
    r"(?P<full>"
    r"(?:We\s+)?\bcall\b\s+"
    r"(?:" + _DISPLAY_MATH + r"|[^.]){0,300}?"
    r"\bas\s+(?:a\s+|an\s+)?(?:\\emph\{|\\textit\{|\\textbf\{)"
    r"(?P<name>[^}]{1,80})"
    r"\}"
    r"[^.]{0,40}\."
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)

# R12: 'We call it/them/this/these (a/an/the) \emph{NAME}.'
R12_CALL_IT_EMPH = re.compile(
    r"(?P<full>"
    r"(?:We\s+)?\bcall\b\s+(?:it|them|this|these)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:\\emph\{|\\textit\{|\\textbf\{)"
    r"(?P<name>[^}]{1,120})"
    r"\}\."
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)

# R13: description with \emph{term} followed by display equation in same paragraph
R13_EMPH_DISPLAY_EQ = re.compile(
    r"(?P<full>"
    r"(?:[A-Z][^.\n]{0,300}?)"
    r"(?:\\emph\{|\\textit\{)(?P<name>[^}]{1,80})\}"
    r"[^$\[]{0,400}?"
    r"(?:" + _DISPLAY_MATH + r")"
    r"(?:[^.]*\.)?"
    r")",
    flags=re.DOTALL,
)

# R14: 'We can represent X by/as/using ..., where \begin{equation*}...\end{equation*}'
R14_REPRESENT_BY = re.compile(
    r"(?P<full>"
    r"(?:We\s+)?(?:can\s+)?represent\s+"
    r"(?P<name>[^,.]{1,80})"
    r"\s+(?:by|as|using|with)\s+"
    r"(?:[^.\\]|\\[^b]){0,300}?"
    r"(?:" + _DISPLAY_MATH + r")"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)

# R15: 'we measure/denote TERM by <display equation>'
R15_MEASURE_BY = re.compile(
    r"(?P<full>"
    r"(?:For\s+[^,.]{1,80},\s+)?"
    r"(?:We\s+)?\b(?:measure|denote|express|write)\b\s+"
    r"(?P<name>[^.,$]{1,100}?)"
    r"\s+by\s+(?:the\s+)?[^.$]{0,120}?"
    r"(?:" + _DISPLAY_MATH + r")"
    r"(?:[^.]*\.)?"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)

# R16: Named model/process introduced with acronym (e.g. '(SIS) model')
# PRUNED — FP on 1301.1423v2
# R16_NAMED_MODEL = re.compile(
#     r"(?P<full>"
#     r"[A-Z][^.]{0,300}"
#     r"\([A-Z]{2,10}\)\s+(?:model|process|framework|scheme|protocol|algorithm)"
#     r"[^.]*\."
#     r"(?:\s+[A-Z][^.]*\.){1,5}"
#     r")",
#     flags=re.DOTALL,
# )
_MODEL_KEYWORDS = re.compile(
    r"\b(rate|parameter|probability|recover|infect|susceptible|state|transition|"
    r"node|vertex|edge|agent|individual|step|spread|contagion|transmit|heal)\b",
    flags=re.IGNORECASE,
)

# R17: \mypar{...} / \paragraph{...} style heading + following prose block
# PRUNED — FP on 1512.05406v1 | also 1 TP — review before uncommenting
# R17_MYPAR = re.compile(
#     r"(?P<full>"
#     r"\\(?:mypar|myparagraph|paragraph)\s*\{(?P<name>[^}]{1,80})\}\s*"
#     r"(?P<body>(?:(?!\\(?:mypar|myparagraph|paragraph|section|subsection)).){20,800}?)"
#     r"(?=\\(?:mypar|myparagraph|paragraph|section|subsection)|\\end\{document\}|\Z)"
#     r")",
#     flags=re.DOTALL,
# )

# R18: '\begin{defn}...\end{defn}' and similar short-form definition envs
R18_DEFN_ENV = re.compile(
    r"\\begin\{(defn|dfn|Defn|Def)\}"
    r"(?:\[(?P<opt>[^\]]*)])?"
    r"(?P<body>.*?)"
    r"\\end\{\1\}",
    flags=re.DOTALL | re.IGNORECASE,
)

# R19: 'when X, Y is Z' enumerative definitional sentences (at least 2 clauses)
R19_WHEN_ENUM = re.compile(
    r"(?P<full>"
    r"(?:[^.]*?\bwhen\b[^,;.]+,[^;.]+){2,}"
    r"[^.]*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)
_WHEN_DEFN_INDICATOR = re.compile(
    r"\bis\b[^,;.]{1,80}"
    r"(?:operator|matrix|method|approach|strategy|scheme|algorithm|estimator|procedure)\b",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# New patterns (R20+)
# ---------------------------------------------------------------------------

# R20: 'X is/are, by definition, ...' or 'X which, by definition, ...'
R20_BY_DEFINITION = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.]{1,100}?)"
    r"\s+(?:(?:is|are),?\s+by\s+definition,?|which,?\s+by\s+definition,?)\s+"
    r"(?:" + _DISPLAY_MATH + r"|[^.])*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R21: 'X takes the form / is given by <display env> where ...'
# PRUNED — FP on 1102.4533v1, 1103.5544v1, 1601.01819v1 +2 more | also 7 TP — review before uncommenting
# R21_TAKES_FORM = re.compile(
#     r"(?P<full>"
#     r"(?P<name>[^.\n]{1,120}?)"
#     r"(?:takes?\s+the\s+form|is\s+given\s+by|is\s+defined\s+(?:as|by))"
#     r"\s*"
#     r"(?:\\begin\{[^}]+\}.*?\\end\{[^}]+\}|\\\[.*?\\\]|\$\$.*?\$\$)"
#     r"(?P<where_clause>[^.]{0,400}?(?:where|with)[^.]{0,400}\.)?)",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R22: 'X means (that) ...'
# PRUNED — FP on 1512.05406v1
# R22_MEANS_THAT = re.compile(
#     r"(?P<full>"
#     r"(?P<name>[^.]{1,100}?)"
#     r"\s+means?\s+(?:that\s+)?"
#     r"(?:" + _DISPLAY_MATH + r"|[^.])*\.)",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R23: 'X are/is parametrized/characterized/denoted/written by Y if <cond>'
R23_PARAMETRIZED_IF = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.]{1,120}?)"
    r"\s+(?:are|is)\s+(?:therefore\s+)?"
    r"(?:parametrized|denoted|written|expressed|characterized)"
    r"[^.]{0,200}?"
    r"\s+if\s+"
    r"(?:" + _DISPLAY_MATH + r"|[^.])*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R24: 'Introducing/Defining/Denoting X via/as/by ... is given by / := <block>'
R24_INTRODUCING = re.compile(
    r"(?P<full>"
    r"(?:Introducing|Defining|Denoting)\s+"
    r"(?P<name>[^.]{1,80}?)"
    r"\s+(?:via|as|by|through|with)\s+"
    r"(?:" + _DISPLAY_MATH + r"|[^.\\])*?"
    r"(?:is\s+given\s+by|is\s+defined\s+(?:as|by)|:=|=)"
    r"(?:\s*\\begin\{[^}]+\}.*?\\end\{[^}]+\}|\s*\\\[.*?\\\]|\s*\$\$.*?\$\$|[^.]*\.))",
    flags=re.IGNORECASE | re.DOTALL,
)

# R25: 'the following functions/quantities/objects: <env with :=>'
R25_FOLLOWING_FUNCTIONS = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.\n]{1,200}?)"
    r"\s+the\s+following\s+"
    r"(?:functions?|quantities?|objects?|notation|expressions?|formulas?|variables?|shorthand[s]?)\s*:?\s*"
    r"(?:\\begin\{[^}]+\}.*?\\end\{[^}]+\}))",
    flags=re.IGNORECASE | re.DOTALL,
)

# R26: '[subject] are/is given by <display env or $$>'
R26_GIVEN_BY_ENV = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.\n]{1,150}?)"
    r"\s+(?:is|are)\s+given\s+by\s*"
    r"(?:\\begin\{[^}]+\}.*?\\end\{[^}]+\}|\$\$.*?\$\$|\\\[.*?\\\]))",
    flags=re.IGNORECASE | re.DOTALL,
)

# R27: '[subject] are/is defined by <display env or $$>'
R27_DEFINED_BY_DISPLAY = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.\n]{1,120}?)"
    r"\s+(?:is|are)\s+defined\s+by\s*"
    r"(?:\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{[^}]+\}.*?\\end\{[^}]+\})"
    r"[^.]*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R28: 'X can/may/could be defined as ...' (modal form of C2)
R28_CAN_BE_DEFINED = re.compile(
    r"\b(?:can|may|could)\s+be\s+defined\s+(?:as|to\s+be)\s",
    flags=re.IGNORECASE,
)

# R29: '[subject] defined through/via the following <words> <env>'
R29_DEFINED_THROUGH = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.\n]{1,150}?)"
    r"\s+defined\s+(?:through|via|by)\s+the\s+following\s+[^\\{]{0,60}?"
    r"(?:\([^)]*\))?\s*:?\s*"
    r"\\begin\{[^}]+\}.*?\\end\{[^}]+\})",
    flags=re.IGNORECASE | re.DOTALL,
)

# R30: 'We define X through/by/via the formula \begin{equation}...\end{equation}'
R30_DEFINE_VIA_ENV = re.compile(
    r"(?P<full>"
    r"(?:We\s+)?(?:also\s+)?(?:Therefore\s+we\s+)?define\s+"
    r"(?P<name>[^.\\]{1,80}?)"
    r"\s*(?:through|via|by|as|using)?\s*"
    r"(?:the\s+(?:formula|expression|equation|relation|unique\s+solution[^.]{0,60}?))?\s*"
    r"(?:\\begin\{(?:equation|align|gather|multline|eqnarray)[*]?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)[*]?\})"
    r"(?:[^.]{0,300}\.)?)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R31: '...as follows: <env> This definition...' pattern
R31_AS_FOLLOWS_DEFN = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.\n]{1,120}?)"
    r"\s+as\s+follows\s*:\s*"
    r"(?:\\begin\{[^}]+\}.*?\\end\{[^}]+\}|\$\$.*?\$\$|\\\[.*?\\\])"
    r"\s*This\s+definition\b[^.]*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R32: 'the notion/concept of X defined by ...'
R32_NOTION_OF = re.compile(
    r"(?P<full>"
    r"(?:We\s+(?:will\s+)?use\s+)?"
    r"the\s+notion\s+of\s+"
    r"(?P<name>[^.]{1,80}?)"
    r"\s+defined\s+by\s+"
    r"(?:\$[^$]+\$|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|[^.])"
    r"[\s\S]*?\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R33: 'there is/exists a <type> X such that <block>'
# PRUNED — FP on 1705.02177v2 | also 1 TP — review before uncommenting
# R33_THERE_EXISTS = re.compile(
#     r"(?P<full>"
#     r"there\s+(?:is|exists|are)\s+"
#     r"(?:a\s+|an\s+)?"
#     r"(?:[a-zA-Z]+\s+){0,4}"
#     r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\]+))"
#     r"\s+such\s+that\s*"
#     r"(?:\\begin\{[^}]+\}[\s\S]*?\\end\{[^}]+\}|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|[^.]*\.))",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R34: 'shorthand/convenient notation(s)' followed by math block with ':='
R34_SHORTHAND_NOTATION = re.compile(
    r"(?P<full>"
    r"(?:[^.\n]{0,200}?)"
    r"(?:shorthand\s+notation[s]?|"
    r"following\s+notation[s]?|"
    r"convenient\s+(?:to\s+use\s+the\s+following\s+)?notation[s]?|"
    r"following\s+abbreviation[s]?|"
    r"following\s+shorthand[s]?)"
    r"[^.\n]{0,100}:?\s*"
    r"(?P<mathblock>\\begin\{"
    r"(?:align|align\*|equation|equation\*|gather|gather\*)[^}]*\}"
    r"[\s\S]*?"
    r"\\end\{(?:align|align\*|equation|equation\*|gather|gather\*)[^}]*\}))",
    flags=re.IGNORECASE | re.DOTALL,
)

# R35: 'so-called / known as X ... given/defined by <math block>'
R35_SO_CALLED = re.compile(
    r"(?P<full>"
    r"(?:[^.\n]{0,200}?)"
    r"(?:so[- ]called|known\s+as)\s+"
    r"(?P<name>[^.]{1,80}?)"
    r"\s+(?:[^.]{0,100}?)"
    r"(?:given|defined)\s+by\s*"
    r"(?:\\begin\{[^}]+\}[\s\S]*?\\end\{[^}]+\}|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]))",
    flags=re.IGNORECASE | re.DOTALL,
)

# R36: ':=' inside $$ ... $$ or \[ ... \] display math (prose-level definition)
# PRUNED — FP on 1705.02177v2 | also 7 TP — review before uncommenting
# R36_WALRUS_DISPLAY = re.compile(
#     r"(?P<full>"
#     r"(?P<lead>[^\n]{0,300}?)"
#     r"(?P<math>\$\$[^$]*:=[\s\S]*?\$\$|\\\[[^\]]*:=[^\]]*\\\])"
#     r"(?P<tail>[^.\n]{0,300}\.)?)",
#     flags=re.DOTALL,
# )

# R37: ':=' inside align/equation/gather environments (preceded by prose)
_MATH_ENV_NAMES_FOR_DEF = (
    r"align|align\*|equation|equation\*|"
    r"gather|gather\*|multline|multline\*|eqnarray|eqnarray\*"
)
R37_WALRUS_ENV = re.compile(
    r"(?P<prose>[^\n.]{0,300})\n?\s*"
    r"\\begin\{(?:" + _MATH_ENV_NAMES_FOR_DEF + r")\}"
    r"(?:\[[^\]]*\])?"
    r"(?P<body>.*?:=.*?)"
    r"\\end\{(?:" + _MATH_ENV_NAMES_FOR_DEF + r")\}",
    flags=re.DOTALL,
)

# R38: 'X will be / is / are denoted by $Y$'
R38_DENOTED_BY = re.compile(
    r"(?P<full>"
    r"(?P<name>(?:[^.]{1,120}?))"
    r"\s+(?:will\s+be|is|are)\s+denoted\s+by\s+"
    r"(?:\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})*)[^.]*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# R39: 'motivate the name(s) (i) X, (ii) Y ...' naming pattern
R39_MOTIVATE_NAMES = re.compile(
    r"(?P<full>"
    r"(?:[^.]{0,200}?)"
    r"(?:motivate(?:s)?\s+the\s+names?|we\s+(?:refer\s+to|call)\s+[^.]{0,60}?\s+as)"
    r"[^.]{0,400}?"
    r"\(i(?:i|ii|v)?\)"
    r"[^.]*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R40: equation env with \label + definitional suffix ('being', 'denotes', etc.)
# ---------------------------------------------------------------------------
R40_EQ_LABEL_SUFFIX = re.compile(
    r"(?P<full>"
    r"\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}"
    r"(?P<body>(?:(?!\\end\{(?:equation|eqnarray|align|multline|gather)).)*"
    r"\\label\{[^}]+\}"
    r"(?:(?!\\end\{(?:equation|eqnarray|align|multline|gather)).)*)"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}"
    r"[^.\n]{0,15}"
    r"(?P<suffix>[^.\n]{0,150}"
    r"\b(?:being|denot(?:es|ed|ing)|where\b[^.]{0,120}\bis\b|"
    r"here\b[^.]{0,120}\bdenotes\b|is\s+the\b|are\s+the\b|"
    r"playing\s+the\s+role|represents?|stands?\s+for)"
    r"[^.]*\.?))",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R41: equation env containing \equiv or := (definitional equality)
# ---------------------------------------------------------------------------
R41_EQ_EQUIV = re.compile(
    r"(?P<full>"
    r"\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}"
    r"(?P<body>(?:(?!\\end\{(?:equation|eqnarray|align|multline|gather)).)*"
    r"(?:\\equiv|:=)"
    r"(?:(?!\\end\{(?:equation|eqnarray|align|multline|gather)).)*)"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R42: 'where the following ...' + equation + 'have been introduced'
# ---------------------------------------------------------------------------
R42_INTRODUCED_FOR = re.compile(
    r"(?P<prefix>where\s+the\s+following\s+[^\\\n]{0,80}?\n?\s*)"
    r"(?P<full>"
    r"\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}"
    r"(?P<body>(?:(?!\\end\{(?:equation|eqnarray|align|multline|gather)).)*)"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}"
    r")"
    r"(?P<suffix>[^.]{0,120}?"
    r"\bhave\s+been\s+introduced\b"
    r"[^.]*\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R43: 'where' or 'with' + labelled equation env
# ---------------------------------------------------------------------------
# PRUNED — FP on 1601.01819v1 | also 2 TP — review before uncommenting
# R43_WHERE_LABELLED_EQ = re.compile(
#     r"(?P<prefix>\b(?:where|with|and)\b"
#     r"(?:\\footnote\{[^}]*\})?\s{0,30})"
#     r"(?P<full>"
#     r"\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}"
#     r"(?P<body>(?:(?!\\end\{(?:equation|eqnarray|align|multline|gather)).)*"
#     r"\\label\{[^}]+\}"
#     r"(?:(?!\\end\{(?:equation|eqnarray|align|multline|gather)).)*)"
#     r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}"
#     r")"
#     r"(?P<suffix>[^\\\n]{0,120})?",
#     flags=re.DOTALL | re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# R44: 'X is given by \begin{equation}...\end{equation}' (chains)
# ---------------------------------------------------------------------------
# PRUNED — FP on 1102.4533v1, 1601.01819v1, 1705.02177v2 +1 more | also 3 TP — review before uncommenting
# R44_IS_GIVEN_BY_EQ = re.compile(
#     r"(?P<full>"
#     r"(?P<name>[^.\n]{1,120}?)"
#     r"(?:is|are)\s+given\s+by\s*"
#     r"(?:\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}.*?"
#     r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}\s*)+"
#     r"(?:(?:with|where|which|is\s+the|are\s+the|playing)[^.]{0,250}\.)?)",
#     flags=re.DOTALL | re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# R45: 'definition of X \begin{equation}...\end{equation}'
# ---------------------------------------------------------------------------
R45_DEFINITION_OF_EQ = re.compile(
    r"(?P<full>"
    r"[^.\n]{0,120}?\bdefinition\s+of\b[^.\n]{0,80}?"
    r"(?:\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}.*?"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}\s*)+"
    r")",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R46: 'leads to ... expression \begin{equation}...\end{equation}'
# ---------------------------------------------------------------------------
R46_LEADS_TO_EXPR = re.compile(
    r"(?P<full>"
    r"[^.]{0,200}?\bleads?\s+to\b[^.]{0,120}?\bexpression\b[^\\]{0,30}?"
    r"(?:\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}.*?"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}\s*)+"
    r")",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R47: 'where X are [description]: \begin{equation}...\end{equation}'
# ---------------------------------------------------------------------------
R47_WHERE_COLON_EQ = re.compile(
    r"(?P<full>"
    r"\bwhere\b[^:]{1,120}:[ \t]*\n?"
    r"(?:\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}.*?"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}\s*)+"
    r")",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R48: 'Here \begin{equation}...\end{equation} is/are [description].'
# ---------------------------------------------------------------------------
R48_HERE_EQ_IS = re.compile(
    r"(?P<full>"
    r"(?:^|\n)\s*\bHere\b[^\\\n]{0,40}?"
    r"(?:\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}.*?"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}\s*)+"
    r"(?:is|are)\s+(?:the\s+|an?\s+)?[^.]{1,250}\."
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R49: 'by the substitution \begin{equation}...\end{equation} which ...'
# ---------------------------------------------------------------------------
R49_BY_SUBSTITUTION = re.compile(
    r"(?P<full>"
    r"[^.]{0,150}?\bby\s+the\s+substitution\b[^\\]{0,30}?"
    r"(?:\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}.*?"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}\s*)+"
    r"which\b[^.]{0,300}\."
    r")",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R50: 'introducing [the] X \begin{equation}...\end{equation} [where ...]'
# ---------------------------------------------------------------------------
R50_INTRODUCING_EQ = re.compile(
    r"(?P<full>"
    r"[^.]{0,100}?\bintroducing\b[^\\]{0,80}?"
    r"(?:\\begin\{(?:equation|eqnarray|align|multline|gather)\*?\}.*?"
    r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}\s*)+"
    r"(?:where\b[^.]{0,250}\.)?)"
    ,
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R51: anchor 'are/is (inferred|given|obtained|derived) (from|by) the (expansion|formula...)'
# ---------------------------------------------------------------------------
R51_INFERRED_FROM = re.compile(
    r"\b(?:are|is)\s+(?:inferred|derived|introduced|given|obtained|expressed|computed|defined)"
    r"\s+(?:from|by|via|through|as)\s+(?:the\s+)?"
    r"(?:expansion|formula|equation|expression|relation|series)\b",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R52: Enumerated definition block: 'namely:' or 'as follows:' + (i)...(ii)...
# ---------------------------------------------------------------------------
R52_ENUMERATED_DEFN = re.compile(
    r"(?P<full>"
    r"(?:[^.]{0,300}?\b(?:namely|as\s+follows)\s*:\s*)"
    r"(?:[(](?:[ivxlcdmIVXLCDM]+|[a-z])[)]\s+[^;.]{1,300}[;.]\s*){1,}"
    r"(?:[(](?:[ivxlcdmIVXLCDM]+|[a-z])[)]\s+[^.]{1,300}\.))",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R53: 'we need/introduce/require/use the <noun> ... where ...' definition trigger
# ---------------------------------------------------------------------------
# PRUNED — FP on 1512.05406v1, 1705.02177v2
# R53_WE_NEED_THE = re.compile(
#     r"\bwe\s+(?:need|introduce|require|use)\s+the\b",
#     flags=re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# R54: '<math or prose> called <Name>.' — definitional 'called' pattern
# PRUNED — FP on 1103.5544v1, 1601.01819v1
# R54_CALLED_NAME = re.compile(
#     r"(?P<full>"
#     r"(?:[^.\n]{0,200}?)"
#     r"\bcalled\s+"
#     r"(?P<name>[A-Z][^.,;]{1,80}?)"
#     r"\.)",
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R55: 'Let $X$ be ... so that <display math>.' — extended Let pattern
# ---------------------------------------------------------------------------
R55_LET_SO_THAT = re.compile(
    r"(?P<full>"
    r"(?:Let|let)\s+"
    r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_]+))"
    r"[^.]{0,400}?"
    r"\bso\s+that\b"
    r"(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R56: 'This ... induces (a) <display math> by ...' — definitional 'induces' pattern
# ---------------------------------------------------------------------------
R56_INDUCES_DISPLAY = re.compile(
    r"(?P<full>"
    r"This\s+[^.]{0,150}?\binduces\b[^.\\]{0,200}?"
    r"(?P<name>\$\$[^$]+\$\$|\\\[[^\]]+\\\])"
    r"[^.]{0,300}?\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R57: 'we set \begin{align/equation/...}...\end{...}' — definitional 'we set' pattern
# ---------------------------------------------------------------------------
R57_WE_SET_ENV = re.compile(
    r"(?P<full>"
    r"(?:[^.\n]{0,200}?)\bwe\s+set\b[^\\]{0,80}?"
    r"(?P<mathblock>\\begin\{(?:align|equation|gather|multline)[*]?\}"
    r".*?"
    r"\\end\{(?:align|equation|gather|multline)[*]?\}))",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R58: 'we write $X$ for <description>' — notation introduction
# PRUNED — FP on 1103.5544v1
# R58_WE_WRITE_FOR = re.compile(
#     r"(?P<full>"
#     r"(?:if\s+)?we\s+write\s+"
#     r"(?P<name>\$[^$]+\$)"
#     r"\s+for\s+"
#     r"[^.]{1,300}?\.)",
#     flags=re.DOTALL | re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# R59: '<X> is measured by <named object> of ... <display math>.'
# ---------------------------------------------------------------------------
R59_MEASURED_BY = re.compile(
    r"(?P<full>"
    r"[^.\n]{0,200}?\bis\s+measured\s+by\b\s+"
    r"(?P<name>[^.\\]{1,100}?)"
    r"(?:\\begin\{[^}]+\}.*?\\end\{[^}]+\}|\$\$.*?\$\$|\\\[.*?\\\]|[^.]*)\."
    r")",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R60: 'The {\em term} ... is ...' and 'A/An {\em term} ... is ...'
# ---------------------------------------------------------------------------
R60_THE_EM_IS = re.compile(
    r"(?P<full>"
    r"(?:The|A|An)\s+"
    r"(?:\{\\em\s+(?P<name1>[^}]{1,80})\}"
    r"|\\emph\{(?P<name2>[^}]{1,80})\}"
    r"|\\textit\{(?P<name3>[^}]{1,80})\}"
    r"|\{\\it\s+(?P<name4>[^}]{1,80})\})"
    r"[^.]{0,300}?"
    r"\bis\b"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R61: 'We adopt/use/introduce the following notation: ...' + display math
# ---------------------------------------------------------------------------
R61_FOLLOWING_NOTATION = re.compile(
    r"(?P<full>"
    r"(?:We\s+)?(?:adopt|use|introduce)\s+the\s+following\s+notation[:\s]"
    r"(?P<body>(?:[^\\]|\\(?!begin))*?)"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{[^}]+\}.*?\\end\{[^}]+\})"
    r"[^.]*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R62: 'A/An {\em term} ...' definitional sentence
# PRUNED — FP on 1207.0773v2, 1210.4765v1, 1304.5152v1 +3 more | also 6 TP — review before uncommenting
# R62_A_EM_DEFN = re.compile(...)

_EM_DEFN_VERBS = re.compile(
    r"\b(?:is|are|denotes?|produces?|represents?|means?|refers?\s+to|"
    r"gives?|yields?|consists?\s+of|forms?|comprises?|equals?|satisfies?)\b",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R63: '{\em term} if \begin{enumerate/itemize}...\end{...}'
# ---------------------------------------------------------------------------
R63_EM_IF_LIST = re.compile(
    r"(?P<full>"
    r"(?:[A-Z][^.]{0,200}?)?"
    r"(?:\{\\em\s+(?P<name1>[^}]{1,80})\}"
    r"|\\emph\{(?P<name2>[^}]{1,80})\}"
    r"|\{\\it\s+(?P<name3>[^}]{1,80})\}"
    r"|\\textit\{(?P<name4>[^}]{1,80})\})"
    r"[^.\\]{0,100}?"
    r"\bif\b"
    r"(?:[^\\]|\\(?!begin))*?"
    r"\\begin\{(?:enumerate|itemize)\}"
    r".*?"
    r"\\end\{(?:enumerate|itemize)\}"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R64: '... called [the/a/an] {\em term}' — definitional 'called' with emphasis
# ---------------------------------------------------------------------------
R64_CALLED_EM = re.compile(
    r"(?P<full>"
    r"(?:[^.\n]{0,300}?)"
    r"\bcalled\s+(?:the\s+|a\s+|an\s+)?"
    r"(?:\{\\em\s+(?P<name1>[^}]{1,80})\}"
    r"|\\emph\{(?P<name2>[^}]{1,80})\}"
    r"|\{\\it\s+(?P<name3>[^}]{1,80})\}"
    r"|\\textit\{(?P<name4>[^}]{1,80})\})"
    r"[^.]{0,200}?"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R65: 'define [the] {\em name} [of X] to be/as ...' — emphatic-name define
# ---------------------------------------------------------------------------
R65_DEFINE_EM_NAME = re.compile(
    r"(?P<full>"
    r"(?:(?:If|Given|For|With|Let)\s+[^.]{0,300}?,\s*)?"
    r"[Dd]efine\s+"
    r"(?:the\s+|an?\s+)?"
    r"(?:\{\\em\s+(?P<name1>[^}]{1,120})\}"
    r"|\\emph\{(?P<name2>[^}]{1,120})\}"
    r"|\{\\it\s+(?P<name3>[^}]{1,120})\}"
    r"|\\textit\{(?P<name4>[^}]{1,120})\}"
    r"|(?P<name5>\$[^$]+\$))"
    r"[^.]{0,200}?"
    r"(?:to\s+be|as|by|:=|=)"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{[^}]+\}.*?\\end\{[^}]+\}|[^.]*)\."
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R66: 'define X to be/as ... \[ ... \]' or 'define X := \begin{...}...\end{...}'
# PRUNED — FP on 1103.5544v1, 1508.06062v1, 1906.04768v3 | also 6 TP — review before uncommenting
# R66_DEFINE_DISPLAY = re.compile(...)

# ---------------------------------------------------------------------------
# R67: 'leading/prompting/motivating us to define X := ...'
# ---------------------------------------------------------------------------
R67_LEADING_TO_DEFINE = re.compile(
    r"(?P<full>"
    r"(?:leading|prompting|allowing|forcing|motivating)\s+us\s+to\s+define\s+"
    r"(?P<name>[^.\\]{1,80}?)"
    r"\s*(?:as|by|to\s+be|:=|=)\s*"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{[^}]+\}.*?\\end\{[^}]+\}|[^.]*)\."
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R68: 'X is referred to as [a/an] {\em term}' anchor-based
# ---------------------------------------------------------------------------
R68_REFERRED_TO_AS = re.compile(
    r"\bis\s+referred\s+to\s+as\s+(?:a\s+|an\s+)?",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R69: 'is defined (for ... ) by ...' — extended passive definition anchor
# ---------------------------------------------------------------------------
R69_IS_DEFINED_FOR_BY = re.compile(
    r"\bis\s+defined\s+(?:for\s+[^,]{0,80},\s*)?(?:by)\s",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R70: 'X is a {\em term} ... if/when ...' — 'is a <emph> if' pattern
# ---------------------------------------------------------------------------
R70_IS_A_EM_IF = re.compile(
    r"(?P<full>"
    r"(?:[A-Z][^.]{0,200}?)"
    r"\bis\s+(?:a\s+|an\s+)?[^.]{0,100}?"
    r"(?:\{\\em\s+(?P<name1>[^}]{1,80})\}"
    r"|\\emph\{(?P<name2>[^}]{1,80})\}"
    r"|\{\\it\s+(?P<name3>[^}]{1,80})\}"
    r"|\\textit\{(?P<name4>[^}]{1,80})\})"
    r"[^.]{0,300}?"
    r"(?:\bif\b|\bwhen\b|\bwhenever\b)"
    r"(?:\\begin\{(?:enumerate|itemize)\}.*?\\end\{(?:enumerate|itemize)\}"
    r"|\\\[.*?\\\]|\$\$.*?\$\$|[^.]*)\."
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R71: 'we denote [, <qualifier>,] by X [the] ...' — extended 'denote by' pattern
# ---------------------------------------------------------------------------
# PRUNED — FP on 1207.0773v2, 1209.2510v1, 1502.03482v2 +3 more | also 18 TP — review before uncommenting
# R71_DENOTE_BY = re.compile(
#     r"(?P<full>"
#     r"(?:we\s+)?denote(?:[^.]{0,80}?)?\bby\s+"
#     r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{},^()]+))"
#     r"[^.]{0,400}?"
#     r"(?:\\emph\{[^}]+\}|\\textit\{[^}]+\}|the\s+[^.]{1,200}?)"
#     r"[^.]*\.)",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R72: 'X is called \emph{Y}' — definitional 'is called' with emphasis
# ---------------------------------------------------------------------------
R72_IS_CALLED_EMPH = re.compile(
    r"(?P<full>"
    r"(?P<subject>[^.\n]{1,200}?)"
    r"\bis\s+called\s+(?:conservative|commutative|[a-z]+\s+)?(?:a\s+|an\s+)?"
    r"(?:(?:\\emph\{(?P<name1>[^}]{1,80})\}"
    r"|\\textit\{(?P<name2>[^}]{1,80})\}"
    r"|\{\\em\s+(?P<name3>[^}]{1,80})\}"
    r"|\{\\it\s+(?P<name4>[^}]{1,80})\})"
    r"[^.]{0,300}?\.)"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R73: PRUNED — FP on 1111.3171v5, 1304.5152v1 | also 1 TP — review before uncommenting
# R73_APPOSITIVE_WHICH_IS = re.compile(...)

# ---------------------------------------------------------------------------
# R74: 'X is a \emph{Y} if <condition>' — definition via definitional 'if'
# ---------------------------------------------------------------------------
R74_IS_EMPH_IF = re.compile(
    r"(?P<full>"
    r"(?P<subject>[^.\n]{1,200}?)"
    r"\bis\s+(?:a\s+|an\s+)?"
    r"(?:\\emph\{(?P<name1>[^}]{1,80})\}"
    r"|\\textit\{(?P<name2>[^}]{1,80})\}"
    r"|\{\\em\s+(?P<name3>[^}]{1,80})\}"
    r"|\{\\it\s+(?P<name4>[^}]{1,80})\})"
    r"[^.]{0,300}?"
    r"\bif\b"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R75: Definitions inside \footnote{...} with \emph{} definitional terms
# ---------------------------------------------------------------------------
R75_FOOTNOTE_EM_DEFN = re.compile(
    r"\\footnote\{(?P<body>"
    r"(?:[^{}]|\{[^{}]*\})*"
    r"(?:\\emph\{[^}]+\}|\\textit\{[^}]+\}|\{\\em\s+[^}]+\}|\{\\it\s+[^}]+\})"
    r"(?:[^{}]|\{[^{}]*\})*"
    r")\}",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R76: 'we (will) refer to X as \emph{Y}' — inline 'refer to as' with emphasis
# ---------------------------------------------------------------------------
R76_REFER_TO_AS_EMPH = re.compile(
    r"(?P<full>"
    r"[Ww]e\s+(?:will\s+|shall\s+|also\s+)?refer\s+to\s+"
    r"(?P<subject>[^.]{1,120}?)"
    r"\s+as\s+"
    r"(?:(?:\\emph\{(?P<name1>[^}]{1,80})\}"
    r"|\\textit\{(?P<name2>[^}]{1,80})\}"
    r"|\{\\em\s+(?P<name3>[^}]{1,80})\}"
    r"|\{\\it\s+(?P<name4>[^}]{1,80})\}"
    r"|``(?P<name5>[^']{1,80})'')"
    r"[^.]{0,200}?\.)"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R77: '\emph{TERM}, where a/an TERM ...' — emph term with definitional where-clause
# ---------------------------------------------------------------------------
R77_EMPH_WHERE_CLAUSE = re.compile(
    r"(?P<full>"
    r"[A-Z][^.]{0,300}?"
    r"\\emph\{(?P<name>[^}]{1,80})\}"
    r"[^.]{0,200}?"
    r",\s*where\b"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R78: 'we define ... \emph{TERM} to be ...' — define with emph and optional parenthetical
# ---------------------------------------------------------------------------
R78_DEFINE_EMPH_TO_BE = re.compile(
    r"(?P<full>"
    r"[Ww]e\s+(?:also\s+)?define\s+"
    r"(?:\([^)]{0,100}\)\s*)?"   # optional parenthetical e.g. (similar to~\cite{...})
    r"(?:a(?:n)?\s+)?"
    r"(?:\\emph\{(?P<name1>[^}]{1,120})\}"
    r"|\\textit\{(?P<name2>[^}]{1,120})\}"
    r"|\{\\em\s+(?P<name3>[^}]{1,120})\}"
    r"|\{\\it\s+(?P<name4>[^}]{1,120})\})"
    r"[^.]{0,300}?"
    r"(?:to\s+be|as|by|:=|=)\s+"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R79: 'we define NAME to be/as/by ...' — flexible 'we define' anchor
# ---------------------------------------------------------------------------
# PRUNED — FP on 1209.2510v1, 1508.06062v1, 1610.03950v1 | also 3 TP — review before uncommenting
# R79_WE_DEFINE_ANCHOR = re.compile(
#     r"\bwe\s+define\s+",
#     flags=re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# R80: 'We say that NAME if \[ ... \]' — definitional 'we say' with 'if' and display math
# ---------------------------------------------------------------------------
R80_WE_SAY_IF_DISPLAY = re.compile(
    r"(?P<full>"
    r"[Ww]e\s+say\s+that\s+"
    r"(?P<name>[^.]{1,100}?)"
    r"\s+(?:is|are|if|when)\s+"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R81: PRUNED — FP on 1207.0773v2, 1502.03482v2
# R81_THE_EMPH_OF_IS = re.compile(...)

# ---------------------------------------------------------------------------
# R82: PRUNED — FP on 1502.03482v2, 1705.02177v2
# R82_LET_DENOTE = re.compile(...)

# ---------------------------------------------------------------------------
# R83: 'let NAME := EXPR [, description]' — definitional assignment ':='
# ---------------------------------------------------------------------------
R83_LET_WALRUS = re.compile(
    r"(?P<full>"
    r"\blet\s+"
    r"(?P<name>\$[^$]+\$|[A-Za-z]\w*(?:\([^)]*\))?)"
    r"\s*(?::=|\\defeq|\\triangleq|\\coloneqq)"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R84: 'Denote by $X$ ... the <description>' — standalone denote-by sentence
# ---------------------------------------------------------------------------
# PRUNED — FP on 1207.0773v2, 1209.2510v1, 1409.6258v2 +5 more | also 20 TP — review before uncommenting
# R84_DENOTE_BY_SENTENCE = re.compile(
#     r"(?P<full>"
#     r"(?:Also,?\s+|Finally,?\s+|Similarly,?\s+)?"
#     r"[Dd]enote\s+by\s+"
#     r"(?P<name>(?:\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})*|[A-Za-z0-9\\{}\[\]_^(),\s]{1,60}?))"
#     r"(?:\s+(?:the|a|an)\s+|\s+)?"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R85: 'write $X$ ... and denote by $Y$ ...' — write + denote mid-sentence notation
# ---------------------------------------------------------------------------
R85_WRITE_AND_DENOTE = re.compile(
    r"(?P<full>"
    r"(?:If\s+[^,]{0,80},\s+)?[Ww]rite\s+"
    r"(?:\$[^$]+\$\s*){0,3}"
    r"[^.]{0,120}?"
    r"\band\s+denote\s+by\s+"
    r"(?P<name>(?:\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})*|[A-Za-z0-9\\{}\[\]_^()]{1,40}))"
    r"[^.]*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R86: PRUNED — FP on 1502.03482v2, 1711.00418v8 | also 1 TP — review before uncommenting
# R86_LET_DENOTE = re.compile(...)

# ---------------------------------------------------------------------------
# R87: 'where $X$ = {... : ...}' set-builder notation definitions
# ---------------------------------------------------------------------------
R87_WHERE_SET_BUILDER = re.compile(
    r"(?P<full>"
    r"where\s+"
    r"(?P<name>\$[^$]{1,60}\$)"
    r"\s*[=:]\s*"
    r"(?:\\\{[^}]{0,300}\\\}|\$\{[^$]{0,300}\$|\$[^$]*\\{[^$]*:[^$]*\}[^$]*\$)"
    r"[^.]*\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R88: General footnote with definitional trigger language
# ---------------------------------------------------------------------------
R88_FOOTNOTE_DEFN = re.compile(
    r"\\footnote\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}",
    flags=re.DOTALL,
)

_R88_TRIGGER = re.compile(
    r"\b(?:is\s+a\n?|is\s+an\n?|is\s+defined\s+(?:as|to\s+be)|"
    r"holds?\s+(?:for|if|when|whenever)|"
    r"denote|define|means\s+that|refers?\s+to\s+as|stands?\s+for|"
    r"is\s+called|is\s+referred\s+to\s+as)\b",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R89: PRUNED — FP on 1508.06062v1
# R89_DISPLAY_WALRUS = re.compile(...)

# ---------------------------------------------------------------------------
# R90: Named concept in LaTeX double-quotes with 'called/termed/known as'
# ---------------------------------------------------------------------------
R90_CALLED_DQUOTE = re.compile(
    r"(?P<full>"
    r"(?:[^.]{0,200}?)"
    r"(?:can\s+be\s+called|is\s+called|are\s+called|called|termed|"
    r"known\s+as|referred\s+to\s+as|call\s+(?:it|them|this|these))\s+"
    r"``(?P<name>[^']{1,80})''"
    r"[^.]*\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R91: 'assumption/notion/concept/condition of ``term''' with definitional clause
# ---------------------------------------------------------------------------
R91_ASSUMPTION_OF_DQUOTE = re.compile(
    r"(?P<full>"
    r"(?:the\s+)?(?:assumption|notion|concept|condition|property|principle|idea)"
    r"\s+of\s+``(?P<name>[^']{1,80})''"
    r"(?:[^.]{0,300}"
    r"(?:which\s+is|meaning|means|i\.e\.|defined\s+as|ensures?|guarantees?)[^.]*)?\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R92: 'so-called ``term''' — so-called with double-quoted term
# ---------------------------------------------------------------------------
# PRUNED — FP on 1605.09252v2
# R92_SO_CALLED_DQUOTE = re.compile(
#     r"(?P<full>"
#     r"(?:[^.]{0,150}?)"
#     r"so[- ]?called\s+``(?P<name>[^']{1,80})''"
#     r"(?:[^.]{0,300})\.)",
#     flags=re.DOTALL | re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# R93: '[concept/method] is as follows' multi-sentence definitional block
# ---------------------------------------------------------------------------
R93_IS_AS_FOLLOWS = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.\n]{4,120}?)"
    r"\s+(?:is|are)\s+as\s+follows[.:]\s*"
    r"(?:[^\n]{10,600})"
    r")",
    flags=re.DOTALL | re.IGNORECASE,
)

_AS_FOLLOWS_PRONOUN = re.compile(
    r"^(?:it|this|that|these|those|they|we|the|and|but|or)\s*$",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R94: '[Concept] consists in [definitional description]'
# ---------------------------------------------------------------------------
R94_CONSISTS_IN = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.\n]{5,100}?)"
    r"\s+consists?\s+in\s+"
    r"(?:[^.]{10,400})\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

_CONSISTS_IN_PRONOUN = re.compile(
    r"^(?:it|this|that|these|those|they|we|the|and|but|or)\b",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R95: 'In other words, $X$ (and $Y$) are/is in fact $A$ (and $B$)' — notation rename
# ---------------------------------------------------------------------------
R95_IN_OTHER_WORDS_MATH = re.compile(
    r"(?P<full>"
    r"[Ii]n\s+other\s+words[,:]\s*"
    r"(?P<name>\$[^$]{1,60}\$(?:\s+and\s+\$[^$]{1,60}\$)*)"
    r"\s+(?:is|are)\s+in\s+fact\s+"
    r"(?:[^.]{0,200})\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R96: 'In the terminology of X, Y is a [named concept]'
# ---------------------------------------------------------------------------
R96_IN_TERMINOLOGY_OF = re.compile(
    r"(?P<full>"
    r"[Ii]n\s+the\s+terminology\s+of\s+[^,]{1,60},\s*"
    r"(?P<name>[^.]{1,120}?)"
    r"\s+is\s+(?:a|an)\s+[^.]{1,200}"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R97: Custom definition-like environments: convention, notation, remark-style
# ---------------------------------------------------------------------------
R97_CONVENTION_ENV = re.compile(
    r"\\begin\{(convention|Convention|notation|Notation|note|Note|"
    r"definition\*|Definition\*|defn\*|remark\*|Remark\*)\}"
    r"(?:\[(?P<opt>[^\]]*)])?"
    r"(?P<body>.*?)"
    r"\\end\{\1\}",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R98: 'By $X$ denote ...' — 'By X denote Y' definitional pattern
# ---------------------------------------------------------------------------
R98_BY_DENOTE = re.compile(
    r"(?P<full>"
    r"[Bb]y\s+"
    r"(?P<name>(?:\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})*|[A-Za-z0-9\\_{}\[\]^()]{1,60}))"
    r"[^.]{0,200}?"
    r"\bdenote\b"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R99: PRUNED — FP on 1111.3171v5
# R99_DISPLAY_EQUIV = re.compile(...)

# ---------------------------------------------------------------------------
# R100: PRUNED — FP on 1111.3171v5 | also 2 TP — review before uncommenting
# R100_MATH_MEANS_THAT = re.compile(...)

# ---------------------------------------------------------------------------
# R101: 'is shorthand for' — tabular/array definitional shorthands
# ---------------------------------------------------------------------------
R101_IS_SHORTHAND_FOR = re.compile(
    r"(?P<full>"
    r"(?P<name>[^&\n\\]{1,120}?)"
    r"\s+(?:\\text\{is\s+shorthand\s+for\}|is\s+shorthand\s+for)\s+"
    r"(?P<expansion>[^&\\\n]{1,200})"
    r"(?=\\\\|&|$|\n))",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R102: \begin{array}...\end{array} containing 'is shorthand for' or '\text{corresponds to}'
# ---------------------------------------------------------------------------
R102_ARRAY_SHORTHAND = re.compile(
    r"(?P<full>"
    r"\\begin\{array\}"
    r"(?:\{[^}]*\})?"
    r"(?P<body>.*?(?:is\s+shorthand\s+for|corresponds\s+to|\\text\{is\s+shorthand\s+for\}|\\text\{corresponds\s+to\}).*?)"
    r"\\end\{array\})",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R103: 'Formally, <name> = ...' — 'Formally,' definitional marker
# ---------------------------------------------------------------------------
R103_FORMALLY = re.compile(
    r"(?P<full>"
    r"Formally,?\s+"
    r"(?P<name>(?:\$[^$]+\$|[A-Z][A-Za-z0-9_\\{}^,\s]{0,60}?))"
    r"[^.\n]{0,400}"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R104: PRUNED — FP on 1304.5152v1, 1508.06062v1 | also 1 TP — review before uncommenting
# R104_CALL_IT = re.compile(...)

# ---------------------------------------------------------------------------
# R105: 'X abbreviates ... <display math>' — abbreviation definitional pattern
# ---------------------------------------------------------------------------
R105_ABBREVIATES = re.compile(
    r"(?P<full>"
    r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{^}()\s,]{1,60}?))"
    r"\s+abbreviates?\b"
    r"(?:[^.]{0,400}(?:\$\$.*?\$\$|\\\[.*?\\\])[^.]{0,200}"
    r"|[^.]{0,400})"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R106: 'let <name> = $$...$$' — 'let X = <display math>' definitional pattern
# ---------------------------------------------------------------------------
R106_LET_DISPLAY_MATH = re.compile(
    r"(?P<full>"
    r"(?:for\s+[^,]{1,60},\s*)?"
    r"(?:let|define)\s+"
    r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{^}]+(?:\s*\([^)]{0,40}\))?))"
    r"\s*(?:=|:=|\\triangleq|\\defeq|\\stackrel\{[^}]*\}\{=\})"
    r"\s*(?:\$\$.*?\$\$|\\\[.*?\\\])"
    r"(?:[^.\n]{0,300}\.)?)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R107: PRUNED — FP on 1111.3171v5, 1207.0773v2, 1210.4765v1 +4 more | also 6 TP — review before uncommenting
# R107_X_DENOTES = re.compile(...)

# ---------------------------------------------------------------------------
# R108: 'We call (G,l) a {\it term} if ...\begin{env}...\end{env}'
# ---------------------------------------------------------------------------
R108_WE_CALL_A_IF = re.compile(
    r"(?P<full>"
    r"(?:[Ww]e|[Oo]ne)\s+call\s+"
    r"(?P<subject>[^.]{1,80}?)"
    r"\s+(?:a|an)\s+"
    r"(?:\{\\it\s+(?P<name1>[^}]{1,80})\}"
    r"|\{\\em\s+(?P<name2>[^}]{1,80})\}"
    r"|\\emph\{(?P<name3>[^}]{1,80})\}"
    r"|\\textit\{(?P<name4>[^}]{1,80})\}"
    r"|(?P<name5>[A-Za-z][A-Za-z\s\-]{1,60}?))"
    r"\s+if\b"
    r"(?:[^\\]|\\(?!end))*?"
    r"(?:\\begin\{(?:enumerate|itemize|enumroman|enumarab)[^}]*\}.*?"
    r"\\end\{(?:enumerate|itemize|enumroman|enumarab)[^}]*\}|[^.]{0,400}\.)"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R109: 'We say that a <NounPhrase> is <property> if ...'
# ---------------------------------------------------------------------------
R109_WE_SAY_IS_IF = re.compile(
    r"(?P<full>"
    r"[Ww]e\s+say\s+(?:that\s+)?"
    r"(?:a\s+|an\s+|the\s+)?"
    r"(?P<name>[^.]{1,120}?)"
    r"\s+is\s+"
    r"(?:\{\\it\s+[^}]{1,80}\}|\\emph\{[^}]{1,80}\}|\\textit\{[^}]{1,80}\}|[A-Za-z][A-Za-z\s\-]{1,60}?)"
    r"\s+if\b"
    r"(?:[^.]{0,400}(?:\$\$.*?\$\$|\\\[.*?\\\])?[^.]{0,200})"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R110: 'X is {\it Y} iff ...' — italicized iff-definition pattern
# ---------------------------------------------------------------------------
R110_IS_IT_IFF = re.compile(
    r"(?P<full>"
    r"[A-Z][^.]{0,200}?"
    r"\bis\s+(?:a\s+|an\s+)?"
    r"(?:\{\\it\s+(?P<name1>[^}]{1,80})\}"
    r"|\{\\em\s+(?P<name2>[^}]{1,80})\}"
    r"|\\emph\{(?P<name3>[^}]{1,80})\}"
    r"|\\textit\{(?P<name4>[^}]{1,80})\})"
    r"[^.]{0,20}?"
    r"\biff\b"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R111: PRUNED — FP on 1207.0773v2, 1304.5152v1, 1502.03482v2
# R111_CALLED_A_COMMA = re.compile(...)

# ---------------------------------------------------------------------------
# R112: 'Call this a/an <name>.' or 'Call X a/an <name>.' — imperative naming
# ---------------------------------------------------------------------------
R112_CALL_THIS_A = re.compile(
    r"(?P<full>"
    r"(?:[^.]{0,200}?)?"
    r"\bCall\s+(?:this|it|them|[A-Za-z0-9$\\{}_^]+)\s+"
    r"(?:a\s+|an\s+)?"
    r"(?:\{\\it\s+(?P<name1>[^}]{1,80})\}"
    r"|\{\\em\s+(?P<name2>[^}]{1,80})\}"
    r"|\\emph\{(?P<name3>[^}]{1,80})\}"
    r"|\\textit\{(?P<name4>[^}]{1,80})\}"
    r"|(?P<name5>[A-Za-z][\w\s\{\}\\'-]{1,60}?))"
    r"\s*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R113: PRUNED — FP on 1304.5152v1, 1502.03482v2, 1512.05406v1 | also 2 TP — review before uncommenting
# R113_WILL_DEFINE = re.compile(...)

# ---------------------------------------------------------------------------
# R114: 'We strengthen/extend/generalize <condition> to (<label>) $$...$$'
# ---------------------------------------------------------------------------
R114_STRENGTHEN_TO = re.compile(
    r"(?P<full>"
    r"[Ww]e\s+"
    r"(?:strengthen|extend|generalize|generalise|refine|replace|upgrade|modify|weaken)\s+"
    r"(?P<name>[^.]{0,100}?)"
    r"\s+to\s+"
    r"(?:\([^)]{0,40}\)\s*)?"
    r"(?:\$\$.*?\$\$|\\\[.*?\\\])"
    r"(?:[^.]{0,400}\.)?)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R115: PRUNED — FP on 1304.5152v1
# R115_PROPERTY_MEANS = re.compile(...)

# ---------------------------------------------------------------------------
# R116: PRUNED — FP on 1705.02177v2, 1906.04768v3 | also 1 TP — review before uncommenting
# R116_THE_NAME_IS_MATH = re.compile(...)

# ---------------------------------------------------------------------------
# R117: 'X is said to be <property/name> if ...' — 'is said to be' anchor-based
# ---------------------------------------------------------------------------
R117_IS_SAID_TO_BE = re.compile(
    r"\bis\s+said\s+to\s+be\s",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R118: 'We introduce [the] {\em TERM} / \emph{TERM}' — definitional 'We introduce'
# ---------------------------------------------------------------------------
R118_WE_INTRODUCE_EM = re.compile(
    r"(?P<full>"
    r"[Ww]e\s+introduce\s+(?:the\s+|a\s+|an\s+)?"
    r"(?:\{\\em\s+(?P<name1>[^}]{1,80})\}"
    r"|\\emph\{(?P<name2>[^}]{1,80})\}"
    r"|\{\\it\s+(?P<name3>[^}]{1,80})\}"
    r"|\\textit\{(?P<name4>[^}]{1,80})\})"
    r"(?:[^.]{0,400}?"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{[^}]+\}.*?\\end\{[^}]+\}|[^.]*)\.))",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R119: PRUNED — FP on 1705.02177v2
# R119_WE_INTRODUCE_DISPLAY = re.compile(...)

# ---------------------------------------------------------------------------
# R120: '\item <Name>, defined as <definition>.' — bullet-list inline definitions
# ---------------------------------------------------------------------------
R120_ITEM_DEFINED_AS = re.compile(
    r"(?P<full>"
    r"\\item\s+"
    r"(?P<name>[^,\n]{1,120}?)"
    r",\s+defined\s+as\s+"
    r"(?P<tail>(?:\\footnote\{[^}]*\}|[^.\n]){1,500}"
    r"(?:\.[^a-z]|\.$|(?=\s*\\item)|(?=\\end\{)))"
    r")",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R121: PRUNED — FP on 1705.02177v2, 1811.04151v1 | also 3 TP — review before uncommenting
# R121_ITEM_ABBREV_COLON = re.compile(...)

# ---------------------------------------------------------------------------
# R122: '(referred to as ``X'')' or '(referred to as X)' — inline alias pattern
# ---------------------------------------------------------------------------
R122_REFERRED_TO_AS_INLINE = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.]{1,150}?)"
    r"\(referred\s+to\s+as\s+"
    r"(?:``(?P<alias1>[^']{1,80})''|\"(?P<alias2>[^\"]{1,80})\"|(?P<alias3>[^)]{1,80}))"
    r"\)"
    r"[^.]{0,200}?\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R123: PRUNED — FP on 1103.5544v1, 1111.3171v5, 1207.0773v2 +10 more | also 33 TP — review before uncommenting
# R123_IS_A_THAT = re.compile(...)

# Gate: require substantive clause content (not just 'that is')
_IS_A_THAT_GATE = re.compile(
    r"\b(?:that|which|where)\b\s+\S+\s+\S+",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R124: 'Likewise/Similarly, X ... combine/consist of/constitute ...'
# ---------------------------------------------------------------------------
R124_LIKEWISE_COMBINES = re.compile(
    r"(?P<full>"
    r"(?:Likewise|Similarly)[,.]\s+"
    r"(?P<name>[A-Z][^,]{1,80}?)"
    r"(?:,\s*which[^,]*,)?\s+"
    r"(?:combine|consist\s+of|constitute|comprise|form)s?\s+"
    r"[^.]{5,250}\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R125: 'we implement/introduce/adopt/propose X as ...' — implementation-as definition
# ---------------------------------------------------------------------------
# PRUNED — FP on 1404.1366v4, 1801.06104v2 | also 2 TP — review before uncommenting
# R125_IMPLEMENT_AS = re.compile(
#     r"(?P<full>"
#     r"(?:we|I)\s+(?:implement|introduce|adopt|present|propose)\s+"
#     r"(?P<name>[^.]{1,80}?)"
#     r"\s+as\s+"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R126: 'called X, plays/...: $$...$$ with \begin{equation}...\end{equation}'
# ---------------------------------------------------------------------------
R126_CALLED_DISPLAY_EQ = re.compile(
    r"(?P<full>"
    r"[^.\n]{0,200}?\bcalled\b[^.]{0,200}?"
    r"(?::\s*|,\s*)"
    r"(?:\$\$.*?\$\$|\\\[.*?\\\])"
    r"(?:\s*with\s*)?"
    r"(?:\s*\\begin\{(?:equation|align|gather|multline|eqnarray)[*]?\}.*?"
    r"\\end\{(?:equation|align|gather|multline|eqnarray)[*]?\})?)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R127: 'let ... $$SYMBOL = \left\{...\right\}$$' display-math set definitions
# ---------------------------------------------------------------------------
R127_LET_DISPLAY_SET = re.compile(
    r"(?P<full>"
    r"(?:let|consider|more\s+precisely,?\s+let)\s*\n?\s*"
    r"\$\$\s*"
    r"(?P<name>\\?[A-Za-z][A-Za-z0-9_{}\\^*]*(?:\{[^}]*\})?)"
    r"\s*=\s*"
    r"\\left\\?\{"
    r".*?"
    r"\\right\\?\}"
    r"\s*\.?\s*\$\$)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R128: 'Let/Set/Define X \begin{equation}...\end{equation}' — Let + equation env
# ---------------------------------------------------------------------------
# PRUNED — FP on 1508.06062v1
# R128_LET_EQUATION_ENV = re.compile(
#     r"(?P<full>"
#     r"(?:Let|let|Set|set|Define|define)\s+"
#     r"(?P<name>[^\\\n]{0,60}?)"
#     r"\\begin\{(?:equation|align|gather|multline|eqnarray)[*]?\}"
#     r"(?P<body>.*?)"
#     r"\\end\{(?:equation|align|gather|multline|eqnarray)[*]?\}"
#     r")",
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R129: PRUNED — FP on 1508.06062v1, 1705.02177v2 | also 1 TP — review before uncommenting
# R129_LET_SUCH_THAT_DISPLAY = re.compile(...)

# ---------------------------------------------------------------------------
# R130: 'Let X be the solution of \be...\ee' (short-hand \be...\ee environment)
# ---------------------------------------------------------------------------
R130_LET_BE_SHORTHAND_ENV = re.compile(
    r"(?P<full>"
    r"(?:Let|let|Set|set|Define|define)\s+"
    r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ^*]+))"
    r"[^\n]{0,200}?"
    r"\\be\b"
    r"(?P<body>.*?)"
    r"\\ee\b"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R131: 'we set/and set \be...\ee' — definitional 'we set' with \be...\ee shorthand
# ---------------------------------------------------------------------------
R131_WE_SET_SHORTHAND_ENV = re.compile(
    r"(?P<full>"
    r"(?:[^.\n]{0,200}?)"
    r"(?:we\s+set|and\s+set|simply\s+set|now\s+set)\s*"
    r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ^*]*)?)"
    r"[^\n]{0,60}?"
    r"\\be\b"
    r"(?P<body>.*?)"
    r"\\ee\b"
    r")",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R132: Multiple \be...\ee definitions with definitional context (multi-assign block)
# ---------------------------------------------------------------------------
R132_MULTI_DEF_SHORTHAND = re.compile(
    r"(?P<full>"
    r"\\be\b"
    r"(?P<body>.*?)"
    r"\\ee\b"
    r")",
    flags=re.DOTALL,
)

_DEF_CONTEXT_BEFORE = re.compile(
    r"\b(?:define|defined|set|let|denote|where|given\s+by|introduce|consider)\b",
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R133: PRUNED — FP on 1210.4765v1, 1502.03482v2, 1508.06062v1 +3 more | also 4 TP — review before uncommenting
# R133_LET_AND_CONSIDER = re.compile(...)

# ---------------------------------------------------------------------------
# R134: 'Indeed/let ... $$ G(s) = ... $$ and $$ H(s) = ... $$'
# ---------------------------------------------------------------------------
R134_LET_DISPLAY_ASSIGN = re.compile(
    r"(?P<full>"
    r"(?:Indeed,?\s+)?(?:let|define|set)\s+"
    r"(?P<name>\$\$[^$]{1,400}?\$\$)"
    r"(?:\s+and\s+\$\$[^$]{1,400}?\$\$)*"
    r")",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R135: 'where $$ NAME = formula $$' — display-math definition introduced by 'where'
# ---------------------------------------------------------------------------
# PRUNED — FP on 1209.2510v1, 1404.7475v3, 1909.06098v1 | also 2 TP — review before uncommenting
# R135_WHERE_DISPLAY_ASSIGN = re.compile(
#     r"(?P<full>"
#     r"\bwhere\b\s*\n?\s*"
#     r"(?:\$\$(?P<mathbody>[^$]{1,1000})\$\$"
#     r"|\\\[(?P<mathbody2>[^\]]{1,1000})\\\])"
#     r")",
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R136: '\subsection{Definition of ...}' block — catch whole definitional subsection
# ---------------------------------------------------------------------------
R136_SUBSEC_DEFINITION = re.compile(
    r"(?P<full>"
    r"\\(?:sub)*section\{[Dd]efinition[^}]*\}"
    r"(?P<body>(?:.|\n){0,3000}?)"
    r"(?=\\(?:sub)*section|\\begin\{(?:lemma|theorem|proposition|corollary|proof)\}|\Z)"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# NEW RULES (R137+) from suggestions
# ---------------------------------------------------------------------------

# R137: '\textit{Term} (abbrev) is a/an ...' — italicized term introduction at sentence start
# Catches: '\textit{Compressed sensing} (CS) is a technique for ...'
R137_TEXTIT_IS_A = re.compile(
    r"(?P<full>"
    r"\\textit\{(?P<name>[^}]{1,80})\}"
    r"(?:\s*\([^)]{0,40}\))?"
    r"\s+is\s+(?:a|an)\s+"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL,
)

# R138: 'often/sometimes called {\em Name}' or 'referred to as {\em Name}' — called/referred with emphasis
# PRUNED — FP on 1512.05406v1
# R138_OFTEN_CALLED_EM = re.compile(
#     r"(?P<full>"
#     r"(?:[A-Z][^.]{0,200}?)"
#     r"(?:often\s+|sometimes\s+|also\s+|commonly\s+|usually\s+)?"
#     r"(?:called|termed|known\s+as|referred\s+to\s+as)\s+"
#     r"(?:the\s+|a\s+|an\s+)?"
#     r"(?:\{\\em\s+(?P<name1>[^}]{1,80})\}"
#     r"|\{\\it\s+(?P<name2>[^}]{1,80})\}"
#     r"|\\emph\{(?P<name3>[^}]{1,80})\}"
#     r"|\\textit\{(?P<name4>[^}]{1,80})\})"
#     r"[^.]{0,300}"
#     r"\.)",
#     flags=re.DOTALL | re.IGNORECASE,
# )

# R139: '$X$ and/or $Y$ denote(s) ...' — math symbol(s) followed by 'denotes'
# PRUNED — FP on 1111.3171v5, 1207.0773v2, 1209.2510v1 +6 more | also 11 TP — review before uncommenting
# R139_MATH_DENOTES = re.compile(
#     r"(?P<full>"
#     r"(?P<name>"
#     r"(?:\$[^$]{1,80}\$)"
#     r"(?:\s+and\s+(?:\$[^$]{1,80}\$))?"
#     r")"
#     r"\s+denotes?\s+"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
#     flags=re.DOTALL | re.IGNORECASE,
# )

# R140: 'We therefore/also introduce X for/as ...' — 'introduce' definitional verb
# PRUNED — FP on 1207.0773v2, 1512.05406v1 | also 1 TP — review before uncommenting
# R140_INTRODUCE_FOR = re.compile(
#     r"(?P<full>"
#     r"[Ww]e\s+(?:therefore\s+|also\s+|now\s+|next\s+|further\s+)?introduce\s+"
#     r"(?:an?\s+)?(?:extra\s+|additional\s+|new\s+)?"
#     r"(?P<name>[^.]{1,80}?)"
#     r"\s+(?:for|as|to\s+(?:represent|denote)|:=|=)"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
#     flags=re.DOTALL | re.IGNORECASE,
# )

# R141: 'The <noun phrase> \begin{equation}...\end{equation} where X = Y, ...'
# PRUNED — FP on 1301.1423v2, 1512.05406v1, 1601.01819v1 +1 more
# R141_THE_NOUN_EQ_WHERE = re.compile(
#     r"(?P<full>"
#     r"(?:^|(?<=\n))\s*"
#     r"(?:The|This|An?)\s+"
#     r"(?P<name>[A-Za-z][^.\n]{1,80}?)"
#     r"\s*"
#     r"(?:\\begin\{(?:equation|eqnarray|align|multline|gather)[*]?\}.*?"
#     r"\\end\{(?:equation|eqnarray|align|multline|gather)[*]?\})"
#     r"[^.]{0,400}?"
#     r"\bwhere\b[^.]{0,300}"
#     r"\.)",
#     flags=re.DOTALL,
# )

# R142: 'Here, X denotes ...' — 'Here' prefix + symbol + denotes
# PRUNED — FP on 1304.5152v1, 1705.02177v2
# R142_HERE_DENOTES = re.compile(
#     r"(?P<full>"
#     r"Here[,:]?\s+"
#     r"(?P<name>(?:\$[^$]{1,80}\$|\\[a-zA-Z]+(?:\{[^}]*\})*|[A-Za-z][^,\n]{0,60}?))"
#     r"\s+denotes?\s+"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
#     flags=re.DOTALL,
# )

# R143: connector ('and'/'where') + equation env containing '=' — named object via connector
R143_CONNECTOR_EQ_ASSIGN = re.compile(
    r"(?P<full>"
    r"(?P<pre>[^.\n]{0,80}?\b(?:and|where|with|in\s+which)\b[^.\n]{0,40}?)"
    r"(?P<display>\\begin\{(?:eqnarray|eqnarray\*|equation|equation\*|align|align\*|gather|gather\*)\}"
    r"(?P<body>(?:(?!\\end\{).)*[^=!<>]=[^=](?:(?!\\end\{).)*)"
    r"\\end\{(?:eqnarray|eqnarray\*|equation|equation\*|align|align\*|gather|gather\*)\})"
    r")",
    flags=re.DOTALL,
)

# R144: 'use as a performance measure/metric/criterion ...: \begin{env}...'
R144_USE_AS_MEASURE = re.compile(
    r"(?P<full>"
    r"(?P<pre>[^.\n]{0,200}?"
    r"\buse\b[^.]{0,80}?"
    r"(?:as\s+a\s+)?(?:performance\s+)?(?:measure|metric|criterion|index|quantity|statistic)"
    r"[^.:]{0,100}?)"
    r":\s*"
    r"\\begin\{(?:eqnarray|eqnarray\*|equation|equation\*|align|align\*)\}"
    r".*?"
    r"\\end\{(?:eqnarray|eqnarray\*|equation|equation\*|align|align\*)\})",
    flags=re.DOTALL | re.IGNORECASE,
)

# R145: 'parameterized/approximated as \begin{env}...\end{env}' — named object via parameterized-as
# PRUNED — FP on 1301.1423v2, 1502.03482v2
# R145_PARAMETERIZED_AS_ENV = re.compile(
#     r"(?P<full>"
#     r"(?P<pre>[^.\n]{0,200}?\bparametrized\s+as|approximated\s+as|expressed\s+as|written\s+as)\b"
#     r"[^\\]{0,60}?"
#     r"\\begin\{(?:eqnarray|eqnarray\*|equation|equation\*|align|align\*|gather|gather\*)\}"
#     r"(?P<body>.*?)"
#     r"\\end\{(?:eqnarray|eqnarray\*|equation|equation\*|align|align\*|gather|gather\*)\}"
#     r")",
#     flags=re.DOTALL | re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# R146: 'Set X := ...' definitional pattern (from suggestion 1)
# ---------------------------------------------------------------------------
R146_SET_WALRUS = re.compile(
    r"(?P<full>"
    r"(?:^|(?<=\n)|(?<=\.\s)|\.\s+)"
    r"Set\s+"
    r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{},\^]+))"
    r"\s*:=\s*"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.\n]*)\."
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R147: '..., called [the/a/an] <name> [of X].' — passive 'called' prose pattern
# ---------------------------------------------------------------------------
R147_CALLED_PLAIN_NAME = re.compile(
    r"(?P<full>"
    r"[A-Z$][^.]{5,250}?"
    r",\s*called\s+(?:the\s+|a\s+|an\s+)?"
    r"(?P<name>[A-Za-z][^.,\n]{2,80}?)"
    r"(?:\s+of\s+[^.]{1,80})?"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R148: 'Let us consider [noun phrase] $$...$$' or 'Let us consider ... given by $$...$$'
# ---------------------------------------------------------------------------
R148_LET_US_CONSIDER_DISPLAY = re.compile(
    r"(?P<full>"
    r"Let\s+us\s+(?:consider|denote|define|choose|construct)\s+"
    r"(?P<name>[^$\n]{1,150}?)"
    r"(?:\s+(?:given|defined|induced)\s+by)?\s*"
    r"(?:\$\$.*?\$\$|\\\[.*?\\\])"
    r"(?:[^.\n]*\.)?)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R149: 'Let us define [the] [following] <noun> [:]  \begin{itemize/enumerate}...\end{...}'
# ---------------------------------------------------------------------------
R149_LET_US_DEFINE_LIST = re.compile(
    r"(?P<full>"
    r"Let\s+us\s+define\s+"
    r"(?P<name>[^\n:]{3,120}?)"
    r"[:\s]*"
    r"\\begin\{(?:itemize|enumerate|description)\}"
    r".*?"
    r"\\end\{(?:itemize|enumerate|description)\}"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R150: 'we can define/construct [the] <noun> [: or via] $$...$$'
# ---------------------------------------------------------------------------
R150_WE_CAN_DEFINE_DISPLAY = re.compile(
    r"(?P<full>"
    r"(?:we\s+can\s+|one\s+can\s+)?(?:define|construct|obtain|introduce)\s+"
    r"(?:a\s+|an\s+|the\s+)?"
    r"(?P<name>[^$\n]{1,100}?)"
    r"(?:\s*:\s*|\s+)"
    r"(?:\$\$.*?\$\$|\\\[.*?\\\])"
    r"(?:[^.\n]*\.)?)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R151: 'X are/is called the <name>' — plural passive 'called' plain prose
# ---------------------------------------------------------------------------
R151_ARE_CALLED_PLAIN = re.compile(
    r"(?P<full>"
    r"[A-Z$][^.]{5,200}?"
    r"\s+are\s+called\s+(?:the\s+|an?\s+)?"
    r"(?P<name>[A-Za-z][^.,\n]{2,80}?)"
    r"(?:\s+of\s+[^.]{1,80})?"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R152: 'Let X be ... defined by the inclusion ...' or 'Let X be ... given by ...'
# PRUNED — FP on 1409.6258v2, 1502.03482v2, 1705.02177v2 | also 3 TP — review before uncommenting
# R152_LET_BE_DEFINED_BY = re.compile(
#     r"(?P<full>"
#     r"(?:Let|let)\s+"
#     r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ^*]+))"
#     r"[^.]{0,300}?"
#     r"\s+be\s+"
#     r"[^.]{0,300}?"
#     r"(?:defined\s+by|given\s+by|induced\s+by|determined\s+by)"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{[^}]+\}.*?\\end\{[^}]+\}|[^.]*)\."
#     r")",
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R153: 'Given [context], [the] <name> of [entity] is $$...$$'
# ---------------------------------------------------------------------------
R153_GIVEN_CONTEXT_IS_DISPLAY = re.compile(
    r"(?P<full>"
    r"Given\s+[^,]{1,120},\s*"
    r"(?:the\s+)?(?P<name>[^,.]{1,100}?)"
    r"(?:\s+of\s+[^,]{1,80})?"
    r"\s+is\s+"
    r"(?:\$\$.*?\$\$|\\\[.*?\\\])"
    r"(?:[^.\n]*\.)?)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R154: 'We split/partition X into ... disjoint ...' — set-partition definitions
# PRUNED — FP on 1304.5152v1, 1512.05406v1 | also 1 TP — review before uncommenting
# R154_SPLIT_INTO_DISJOINT = re.compile(
#     r"(?P<full>"
#     r"(?:We\s+)?\b(?:split|partition|divide|decompose)\b\s+"
#     r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_ ]{1,60}?))"
#     r"[^.]{0,300}?"
#     r"\b(?:disjoint|non-overlapping|non\s*overlapping)\b"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R155: 'X (denoted/written/abbreviated as/by ...) : it is a ...' — 'denoted as' inline definitions
# ---------------------------------------------------------------------------
R155_DENOTED_AS_COLON = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.()]{1,80}?)"
    r"\s*\((?:denoted|written|abbreviated)\s+(?:as|by)\s+(?P<symbol>[^)]{1,60})\)"
    r"\s*(?::|is|are|=)\s+"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R156: 'we propose [a] X ... is computed by/given by \[ ... \]'
# ---------------------------------------------------------------------------
R156_PROPOSE_COMPUTED_BY = re.compile(
    r"(?P<full>"
    r"(?:we\s+(?:therefore\s+)?(?:also\s+)?propose\s+(?:a\s+|an\s+|the\s+)?)"
    r"(?P<name>(?:\\texttt\{[^}]+\}|\\text[a-z]*\{[^}]+\}|[A-Za-z][A-Za-z0-9_\\-]{0,60}))\b"
    r"[^.]{0,400}?"
    r"(?:is\s+computed\s+by|is\s+defined\s+(?:as|by)|is\s+given\s+by|as\s+follows)"
    r"[^.]{0,100}?"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{[^}]+\}.*?\\end\{[^}]+\})"
    r"(?:[^.]{0,400}\.)?)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R157: '{\bf Term} ... is/consists/denotes ...' — bold-introduced definition
# PRUNED — FP on 1210.4765v1, 1409.6258v2
# R157_BOLD_TERM_DEFN = re.compile(
#     r"(?P<full>"
#     r"(?:^|(?<=[.\n])|(?<=\}\s))\s*"
#     r"(?:\{\\bf\s+(?P<name1>[^}]{1,80})\}|\\textbf\{(?P<name2>[^}]{1,80})\})"
#     r"[^.]{0,400}"
#     r"\.)",
#     flags=re.DOTALL | re.MULTILINE,
# )

# ---------------------------------------------------------------------------
# R158: Bold term introduced after 'the {\bf Term}' or 'a {\bf Term}' — bold with article
# ---------------------------------------------------------------------------
R158_THE_BOLD_IS = re.compile(
    r"(?P<full>"
    r"(?:[^.\n]{0,200}?)"
    r"(?:the\s+|a\s+|an\s+)"
    r"(?:\{\\bf\s+(?P<name1>[^}]{1,80})\}|\\textbf\{(?P<name2>[^}]{1,80})\})"
    r"[^.]{0,400}"
    r"(?:\bdenoted\b|\bis\b|\bare\b|\bdefined\b)"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{[^}]+\}.*?\\end\{[^}]+\}|[^.]*)\."
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R159: '{\bf Term} ... defined as the composite \begin{align}...'
# ---------------------------------------------------------------------------
R159_BOLD_DEFINED_AS_DISPLAY = re.compile(
    r"(?P<full>"
    r"(?:[^.\n]{0,300}?)"
    r"(?:\{\\bf\s+(?P<name1>[^}]{1,80})\}|\\textbf\{(?P<name2>[^}]{1,80})\})"
    r"[^.]{0,300}?"
    r"(?:defined\s+as|is\s+the\s+composite|denoted|:=|=)\s*"
    r"(?:\\begin\{[^}]+\}.*?\\end\{[^}]+\}|\\\[.*?\\\]|\$\$.*?\$\$)"
    r"(?:[^.]{0,300}\.)?)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R160: '... let X be the Y defined by ...' — explicit 'let ... be ... defined by'
# PRUNED — FP on 1409.6258v2, 1502.03482v2, 1705.02177v2 | also 2 TP — review before uncommenting
# R160_LET_BE_DEFINED_BY_DISPLAY = re.compile(
#     r"(?P<full>"
#     r"[Ll]et\s+"
#     r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,]+))"
#     r"[^.]{0,300}?"
#     r"\bdef(?:ined|ines?)\s+by\b"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{[^}]+\}.*?\\end\{[^}]+\}|[^.]*)"
#     r"(?:\.(?=\s)|\Z))",
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R161: '... usually/commonly/often referred to as \textbf{term1} and \textbf{term2}'
# ---------------------------------------------------------------------------
R161_REFERRED_AS_BOLD = re.compile(
    r"(?P<full>"
    r"[^.]{0,300}?"
    r"\b(?:referred\s+to\s+as|known\s+as|called)\s+"
    r"(?:\{\\bf\s+(?P<name1>[^}]{1,80})\}|\\textbf\{(?P<name2>[^}]{1,80})\})"
    r"(?:\s+and\s+(?:\{\\bf\s+[^}]{1,80}\}|\\textbf\{[^}]{1,80}\}))?"
    r"[^.]{0,300}"
    r"\.)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R162: Post-environment continuation with display math and definitional context
# ---------------------------------------------------------------------------
R162_POST_ENV_DISPLAY_DEFN = re.compile(
    r"(?P<full>"
    r"(?:This\s+[^.\n]{5,200}?"
    r"(?:homotopy\s+equivalent|structure\s+of|bimodule|module|action|denote|given\s+by)"
    r"[^.\n]{0,200}?)"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$)"
    r"(?:[^.\n]{0,200}\.)?)",
    flags=re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R163: 'NOUN (risk/process/... of ...)' parenthetical inline definition
# ---------------------------------------------------------------------------
R163_PARENTHETICAL_DEF = re.compile(
    r"(?P<full>"
    r"(?P<name>[A-Z][a-z]+(?:\s+[a-z]+){0,4})"
    r"\s+\("
    r"(?:risk|process|act|measure|probability|rate|concept|notion|idea|"
    r"phenomenon|property|ability|capacity|tendency|practice|procedure|"
    r"method|event|occurrence|state|condition|situation|set|function|"
    r"sequence|collection|map|mapping|class|system)\s+of\s+"
    r"[^)]{5,200}\)"
    r"[^.]*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R164: 'TERM, by definition, refers to/means/is ...' — comma-framed 'by definition'
# ---------------------------------------------------------------------------
R164_BY_DEFINITION_REFERS = re.compile(
    r"(?P<full>"
    r"(?P<name>[^.,\n]{2,80}?)"
    r",\s+by\s+definition,\s+"
    r"(?:refers?\s+to|means?|is|denotes?|indicates?|signifies?|implies?)\s+"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R165: '... called NAME, which was/where/for the reason ...' — named concept introduction
# ---------------------------------------------------------------------------
R165_CALLED_WHICH = re.compile(
    r"(?P<full>"
    r"[^.]{0,120}?\bcalled\s+"
    r"(?P<name>[A-Z][A-Za-z0-9_-]{1,30}(?:\s+[A-Z][A-Za-z0-9_-]{1,20}){0,3})"
    r"(?:[,.]\s*(?:which|where|for\s+the\s+reason|because|since|as|defined|named)\b)"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R166: 'NOUN $X$ denotes/represents/stands for ...' — parameter/variable definition
# PRUNED — FP on 1103.5544v1, 1111.3171v5, 1207.0773v2 +16 more | also 70 TP — review before uncommenting
# R166_NOUN_MATH_DENOTES = re.compile(
#     r"(?P<full>"
#     r"(?:[A-Z][a-z]+(?:\s+[A-Za-z]+){0,5}\s+)?"
#     r"(?:,\s*)?(?P<name>\$[^$]+\$|[A-Z][a-zA-Z0-9_]{0,20})(?:,\s*)?"
#     r"\s*(?:denotes?|represents?|stands?\s+for|is\s+the|describes?)\s+"
#     r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R167: 'with $X$ denoting ...' — participial variable definition
# ---------------------------------------------------------------------------
R167_WITH_DENOTING = re.compile(
    r"(?P<full>"
    r"[^.]{0,80}?\bwith\s+"
    r"(?P<name>\$[^$]+\$|[A-Za-z][a-zA-Z0-9_]{0,20})"
    r"\s+denoting\s+"
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R168: '{\sf <term>}' sans-serif definitional marker
# ---------------------------------------------------------------------------
R168_SF_TERM = re.compile(
    r"(?P<full>"
    r"(?:"
    r"(?:(?:We\s+|we\s+)?(?:call|denote|define|say|name|refer\s+to)[^.]{0,200}?)"
    r"|(?:[A-Z][^.]{0,150}?)"
    r")"
    r"\{\\sf\s+(?P<name>[^}]{1,80})\}"
    r"[^.]{0,200}?"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R169: '{\bfseries Term} Body...' — bold-series term introduction
# PRUNED — FP on 1102.4533v1, 1207.0773v2, 1209.2510v1 +9 more | also 6 TP — review before uncommenting
# R169_BFSERIES_TERM = re.compile(
#     r"(?P<full>"
#     r"(?:^|(?<=\n)|(?<=\.\s))"
#     r"\s*"
#     r"(?:\{\\bfseries\s+(?P<name1>[^}]{1,80})\}"
#     r"|\{\\bf\s+(?P<name2>[^}]{1,80})\}"
#     r"|\\textbf\{(?P<name3>[^}]{1,80})\})"
#     r"\s+"
#     r"(?P<body>(?:(?!\{\\bfseries|\{\\bf|\\textbf\{|\\section|\\subsection|\\begin\{).){20,800})"
#     r")",
#     flags=re.DOTALL | re.MULTILINE,
# )

# ---------------------------------------------------------------------------
# R170: '$expr$ is the [noun phrase] ...' — 'is the' inline prose definition
# PRUNED — FP on 1102.4533v1, 1301.1423v2, 1409.6258v2 +14 more | also 17 TP — review before uncommenting
# R170_MATH_IS_THE_NOUN = re.compile(
#     r"(?P<full>"
#     r"(?P<name>\$[^$]{1,80}\$)"
#     r"\s+is\s+the\s+"
#     r"(?P<desc>[A-Za-z][^.$\n]{5,200}?)"
#     r"\.)",
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R171: 'We call [this/the] [noun phrase] [as/the] [name]' — naming a previously
# introduced object. Catches: 'We call this function as Ramanujan function ...'
# Merged from suggestion 1 (C5 pattern).
# ---------------------------------------------------------------------------
R171_WE_CALL_THIS_AS = re.compile(
    r"(?P<full>"
    r"[Ww]e\s+call\s+"
    r"(?P<subject>(?:this|the|it|them)\s+[^.]{1,80}?)"
    r"\s+(?:as\s+|the\s+)?"
    r"(?P<name>[A-Za-z][^.,\n]{1,80}?)"
    r"\.)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R172: 'We denote [X] by \begin{equation}...\end{equation}' — notation definition
# Merged from suggestions 2 and 3 (C6 pattern).
# Catches: 'We denote the series in (\ref{...}) by \begin{equation}...'
#          'We denote this series by \begin{equation}...'
# ---------------------------------------------------------------------------
R172_WE_DENOTE_BY_ENV = re.compile(
    r"(?P<full>"
    r"[Ww]e\s+(?:also\s+)?denote\s+"
    r"(?P<name>[^.\\]{1,120}?)"
    r"\s+by\s*\n?"
    r"(?:\\begin\{(?:equation|align|eqnarray|gather|multline)[*]?\}.*?"
    r"\\end\{(?:equation|align|eqnarray|gather|multline)[*]?\}"
    r"|\$\$.*?\$\$"
    r"|\\\[.*?\\\])"
    r"(?:[^.]{0,200})?)",
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R173: '[The/A] <name> works as follows.' — procedural definition pattern
# Merged from suggestions 2 & 3 (C6 pattern): anchor on '<NounPhrase> works as follows'
# ---------------------------------------------------------------------------
R173_WORKS_AS_FOLLOWS = re.compile(
    r"(?P<full>"
    r"(?:The|A|An)\s+(?P<name>[^.]{1,80}?)\s+works\s+as\s+follows[.:]?"
    r"(?:\s+(?:[^.]*\.))+)",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R174: '\item The \emph{name}[math], which ...' — itemize-list emph component definitions
# Merged from suggestions 4, 5, 6, 7 (C7 pattern)
# ---------------------------------------------------------------------------
R174_ITEM_THE_EMPH = re.compile(
    r"(?P<full>"
    r"\\item\s+"
    r"(?:The|A|An)\s+"
    r"(?P<name_part>"
    r"(?:\\emph\{[^}]{1,120}\}|\\textit\{[^}]{1,120}\}|\{\\em\s+[^}]{1,120}\}|\{\\it\s+[^}]{1,120}\})"
    r"(?:\s*\$[^$]*\$)?"
    r")"
    r"(?:[^.]{0,600}?\.){1,15}"
    r")",
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anchor_lookback(text: str, anchor_start: int):
    """Return (name_text, name_start) by looking back from anchor_start."""
    start_search = max(0, anchor_start - 100)
    prefix = text[start_search:anchor_start]
    cuts = [prefix.rfind(".")]
    for mk in ("\n\n", "\\section", "\\subsection", "\\maketitle",
               "\\begin", "\\end", "\\item", "\\State", "\\par", "}"):
        p = prefix.rfind(mk)
        if p >= 0:
            cuts.append(p + len(mk) - 1)
    best = max(cuts)
    name_start = start_search + (best + 1 if best >= 0 else 0)
    name_text = text[name_start:anchor_start].strip()
    return name_text, name_start


def _name_from_raw(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    m = re.search(r"\$(.+?)\$", raw)
    if m:
        return m.group(1)[:80]
    # strip latex commands
    cleaned = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", raw)
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:80]


def _trim_name_to_boundary(raw: str, max_len: int = 150) -> str:
    """Trim a raw name string to the last sentence/structural boundary."""
    for sep in (".", "\n\n", "\\end{", "}", "\\begin{"):
        p = raw.rfind(sep)
        if p >= 0:
            raw = raw[p + len(sep):]
    return raw.strip()[:max_len]


def _overlaps(start: int, end: int, seen: list) -> bool:
    for s, e in seen:
        if start < e and end > s:
            return True
    return False


def _make_result(raw_latex: str, name, env_name: str, rule_name: str) -> dict:
    return {
        "raw_latex": raw_latex,
        "clean_text": _clean_latex(raw_latex),
        "name": name,
        "env_name": env_name,
        "rule_name": rule_name,
        "structure_type": "definition",
    }


def _extract_em_name(text: str):
    """Extract name from {\em ...}, \emph{...}, \textit{...}, {\it ...} in text."""
    m = re.search(
        r"(?:\{\\em\s+([^}]+)\}"
        r"|\\emph\{([^}]+)\}"
        r"|\{\\it\s+([^}]+)\}"
        r"|\\textit\{([^}]+)\})",
        text,
    )
    if m:
        return next((g for g in m.groups() if g), None)
    return None


def _extract_bold_name(text: str):
    """Extract name from {\bf ...} or \textbf{...} in text."""
    m = re.search(
        r"(?:\{\\bf\s+([^}]+)\}|\\textbf\{([^}]+)\})",
        text,
    )
    if m:
        return next((g for g in m.groups() if g), None)
    return None


def _extract_sf_name(text: str):
    """Extract name from {\\sf ...} in text."""
    m = re.search(r"\{\\sf\s+([^}]+)\}", text)
    if m:
        return m.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    results: List[dict] = []
    seen_spans: list = []  # list of (start, end)

    def add(raw: str, name, rule_name: str, pos: int):
        end = pos + len(raw)
        if _overlaps(pos, end, seen_spans):
            return
        if _inside_excluded_env(text, pos, end):
            return
        seen_spans.append((pos, end))
        results.append(_make_result(raw, name, "distilled", rule_name))

    # ------------------------------------------------------------------
    # Build a masked version of text (mask excluded environments)
    # ------------------------------------------------------------------
    masked = list(text)
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        for i in range(m.start(), m.end()):
            masked[i] = " "
    masked_text = "".join(masked)

    # ------------------------------------------------------------------
    # R97: Custom definition-like environments (convention, notation, etc.)
    # ------------------------------------------------------------------
    for m in R97_CONVENTION_ENV.finditer(text):
        body = m.group("body")
        opt = m.group("opt")
        name = opt.strip() if opt else None
        raw = m.group(0)
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        add(raw, name, "R97_CONVENTION_ENV", m.start())

    # ------------------------------------------------------------------
    # R18: defn/dfn environments
    # ------------------------------------------------------------------
    for m in R18_DEFN_ENV.finditer(text):
        body = m.group("body")
        opt = m.group("opt")
        name = opt.strip() if opt else None
        raw = m.group(0)
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        add(raw, name, "R18_DEFN_ENV", m.start())

    # ------------------------------------------------------------------
    # R102: \begin{array}...\end{array} containing 'is shorthand for'
    # ------------------------------------------------------------------
    for m in R102_ARRAY_SHORTHAND.finditer(text):
        raw = m.group(0)
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(raw) > 10000:
            continue
        body = m.group("body") or ""
        first_m = re.search(
            r"([^&\\\n]{1,80}?)\s+(?:\\text\{is\s+shorthand\s+for\}|is\s+shorthand\s+for)\s+([^&\\\n]{1,80})",
            body,
            re.IGNORECASE,
        )
        name = _name_from_raw(first_m.group(1)) if first_m else "shorthand"
        add(raw, name or None, "R102_ARRAY_SHORTHAND", m.start())

    # ------------------------------------------------------------------
    # R101: 'is shorthand for' — inline definitional shorthands
    # ------------------------------------------------------------------
    for m in R101_IS_SHORTHAND_FOR.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 1000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 120:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R101_IS_SHORTHAND_FOR", m.start())

    # ------------------------------------------------------------------
    # R98: 'By $X$ denote ...'
    # ------------------------------------------------------------------
    for m in R98_BY_DENOTE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R98_BY_DENOTE", m.start())

    # ------------------------------------------------------------------
    # R158: 'the {\bf Term} ... is/denoted ...' — bold term with article
    # ------------------------------------------------------------------
    for m in R158_THE_BOLD_IS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 4000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or "").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R158_THE_BOLD_IS", m.start())

    # ------------------------------------------------------------------
    # R159: bold term + 'defined as' + display math
    # ------------------------------------------------------------------
    for m in R159_BOLD_DEFINED_AS_DISPLAY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or "").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R159_BOLD_DEFINED_AS_DISPLAY", m.start())

    # ------------------------------------------------------------------
    # R161: '... referred to as \textbf{term1} and \textbf{term2}'
    # ------------------------------------------------------------------
    for m in R161_REFERRED_AS_BOLD.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or "").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R161_REFERRED_AS_BOLD", m.start())

    # ------------------------------------------------------------------
    # R162: Post-environment display math with definitional context
    # ------------------------------------------------------------------
    for m in R162_POST_ENV_DISPLAY_DEFN.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        if len(full_text.strip()) < 20:
            continue
        add(full_text, None, "R162_POST_ENV_DISPLAY_DEFN", m.start())

    # ------------------------------------------------------------------
    # R137: '\textit{Term} (abbrev) is a/an ...' — italicized term introduction
    # ------------------------------------------------------------------
    for m in R137_TEXTIT_IS_A.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R137_TEXTIT_IS_A", m.start())

    # ------------------------------------------------------------------
    # R143: connector ('and'/'where') + equation env containing '='
    # ------------------------------------------------------------------
    for m in R143_CONNECTOR_EQ_ASSIGN.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        body = m.group("body") or ""
        lhs_m = re.search(r"([^\s\\,&$]{1,60})\s*=", body)
        name_raw = lhs_m.group(1).strip() if lhs_m else None
        if name_raw and len(name_raw) > 80:
            name_raw = None
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name or None, "R143_CONNECTOR_EQ_ASSIGN", m.start())

    # ------------------------------------------------------------------
    # R144: 'use as a performance measure/metric ...: \begin{env}...'
    # ------------------------------------------------------------------
    for m in R144_USE_AS_MEASURE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        pre = m.group("pre") or ""
        abbr_m = re.search(r"\(([A-Z]{2,10})\)", pre)
        if abbr_m:
            name = abbr_m.group(1)
        else:
            name = None
        add(full_text, name or None, "R144_USE_AS_MEASURE", m.start())

    # ------------------------------------------------------------------
    # R146: 'Set X := ...' definitional pattern
    # ------------------------------------------------------------------
    for m in R146_SET_WALRUS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R146_SET_WALRUS", m.start())

    # ------------------------------------------------------------------
    # R147: '..., called [the/a/an] <name> [of X].' — passive 'called' plain prose
    # ------------------------------------------------------------------
    for m in R147_CALLED_PLAIN_NAME.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        if re.search(r"\\emph\{|\\textit\{|\{\\em\s|\{\\it\s", full_text):
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R147_CALLED_PLAIN_NAME", m.start())

    # ------------------------------------------------------------------
    # R148: 'Let us consider/define/choose [noun] [given by] $$...$$'
    # ------------------------------------------------------------------
    for m in R148_LET_US_CONSIDER_DISPLAY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        name_raw = _trim_name_to_boundary(name_raw, max_len=120)
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R148_LET_US_CONSIDER_DISPLAY", m.start())

    # ------------------------------------------------------------------
    # R149: 'Let us define [noun] [: \begin{itemize}...\end{itemize}]'
    # ------------------------------------------------------------------
    for m in R149_LET_US_DEFINE_LIST.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R149_LET_US_DEFINE_LIST", m.start())

    # ------------------------------------------------------------------
    # R150: 'we can define/construct [name]: $$...$$'
    # ------------------------------------------------------------------
    for m in R150_WE_CAN_DEFINE_DISPLAY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _C1_NEGATIVE.search(full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 4000:
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        name_raw = _trim_name_to_boundary(name_raw, max_len=100)
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R150_WE_CAN_DEFINE_DISPLAY", m.start())

    # ------------------------------------------------------------------
    # R151: 'X are called the <name>' — plural passive 'called' plain prose
    # ------------------------------------------------------------------
    for m in R151_ARE_CALLED_PLAIN.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        if re.search(r"\\emph\{|\\textit\{|\{\\em\s|\{\\it\s", full_text):
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R151_ARE_CALLED_PLAIN", m.start())

    # ------------------------------------------------------------------
    # R153: 'Given [context], [the] <name> of [entity] is $$...$$'
    # ------------------------------------------------------------------
    for m in R153_GIVEN_CONTEXT_IS_DISPLAY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 4000:
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        if not name_raw or len(name_raw) > 100:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R153_GIVEN_CONTEXT_IS_DISPLAY", m.start())

    # ------------------------------------------------------------------
    # R155: 'X (denoted/written/abbreviated as/by ...) : it is a ...'
    # ------------------------------------------------------------------
    for m in R155_DENOTED_AS_COLON.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) < 3 or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R155_DENOTED_AS_COLON", m.start())

    # ------------------------------------------------------------------
    # R156: 'we propose [a] X ... is computed by/given by \[ ... \]'
    # ------------------------------------------------------------------
    for m in R156_PROPOSE_COMPUTED_BY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        if not re.search(r"\\\[|\$\$|\\begin\{equation|\\begin\{align", full_text):
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R156_PROPOSE_COMPUTED_BY", m.start())

    # ------------------------------------------------------------------
    # R163: 'NOUN (definitional-head-noun of ...)' parenthetical inline definition
    # ------------------------------------------------------------------
    for m in R163_PARENTHETICAL_DEF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R163_PARENTHETICAL_DEF", m.start())

    # ------------------------------------------------------------------
    # R164: 'TERM, by definition, refers to/means/is ...'
    # ------------------------------------------------------------------
    for m in R164_BY_DEFINITION_REFERS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) < 2 or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R164_BY_DEFINITION_REFERS", m.start())

    # ------------------------------------------------------------------
    # R165: '... called NAME, which was/where/for the reason ...'
    # ------------------------------------------------------------------
    for m in R165_CALLED_WHICH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        if re.search(r"\\emph\{|\\textit\{|\{\\em\s|\{\\it\s", full_text):
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R165_CALLED_WHICH", m.start())

    # ------------------------------------------------------------------
    # R167: 'with $X$ denoting ...' — participial variable definition
    # ------------------------------------------------------------------
    for m in R167_WITH_DENOTING.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R167_WITH_DENOTING", m.start())

    # ------------------------------------------------------------------
    # R168: '{\sf <term>}' sans-serif definitional marker
    # ------------------------------------------------------------------
    for m in R168_SF_TERM.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R168_SF_TERM", m.start())

    # ------------------------------------------------------------------
    # R171: 'We call [this/the] [noun] [as/the] [name]' — naming introduced object
    # ------------------------------------------------------------------
    for m in R171_WE_CALL_THIS_AS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        if not name_raw or len(name_raw) < 2 or len(name_raw) > 80:
            continue
        # Filter out overly short or stop-word-only names
        if re.match(r'^(?:it|this|that|these|those|them|here|there)\s*$',
                    name_raw, re.IGNORECASE):
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R171_WE_CALL_THIS_AS", m.start())

    # ------------------------------------------------------------------
    # R172: 'We denote [X] by \begin{equation}...\end{equation}'
    # ------------------------------------------------------------------
    for m in R172_WE_DENOTE_BY_ENV.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        # Must contain an equation environment or display math
        if not re.search(r"\\begin\{|\\\\|\$\$|\\\[", full_text):
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        name_raw = _trim_name_to_boundary(name_raw, max_len=120)
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R172_WE_DENOTE_BY_ENV", m.start())

    # ------------------------------------------------------------------
    # R173: '[The/A] <name> works as follows.' — procedural definition pattern
    # ------------------------------------------------------------------
    for m in R173_WORKS_AS_FOLLOWS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 10000:
            continue
        # Require at least 2 sentences after the header
        if full_text.count('.') < 2:
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        if not name_raw or len(name_raw) > 120:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R173_WORKS_AS_FOLLOWS", m.start())

    # ------------------------------------------------------------------
    # R174: '\item The \emph{name}[math], which ...' — itemize-list emph component definitions
    # ------------------------------------------------------------------
    for m in R174_ITEM_THE_EMPH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 8000:
            continue
        if len(full_text.strip()) < 30:
            continue
        name_part = m.group("name_part") or ""
        # Extract the emph/textit name
        name_raw = _extract_em_name(name_part) or ""
        if not name_raw:
            # fallback: strip command wrappers
            name_raw = re.sub(r"\\(?:emph|textit)\{([^}]*)\}", r"\1", name_part)
            name_raw = re.sub(r"\{\\(?:em|it)\s+([^}]*)\}", r"\1", name_raw)
            name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 120:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R174_ITEM_THE_EMPH", m.start())

    # ------------------------------------------------------------------
    # R1: anchor 'is (then) defined as/to be/in terms of/by'
    # ------------------------------------------------------------------
    for anchor_m in R1_IS_DEFINED_AS_DISPLAY.finditer(masked_text):
        name_text, name_start = _anchor_lookback(masked_text, anchor_m.start())
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _C2_TAIL.match(masked_text, anchor_m.end())
        if not tail_m:
            tail_m = _C2_TAIL_ENV.match(masked_text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        name = _name_from_raw(name_text)
        add(full_text, name or None, "R1_IS_DEFINED_AS_DISPLAY", name_start)

    # ------------------------------------------------------------------
    # R117: anchor 'is said to be'
    # ------------------------------------------------------------------
    for anchor_m in R117_IS_SAID_TO_BE.finditer(masked_text):
        name_text, name_start = _anchor_lookback(masked_text, anchor_m.start())
        if not name_text or len(name_text) > 150:
            continue
        tail_m = _C2_TAIL_ENV.match(masked_text, anchor_m.end())
        if not tail_m:
            tail_m = _C2_TAIL.match(masked_text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        if _inside_excluded_env(text, name_start, tail_m.end()):
            continue
        if len(full_text) > 3000:
            continue
        after_anchor = masked_text[anchor_m.end():anchor_m.end() + 120]
        prop_m = re.match(r"([^.,:;]{1,80}?)\s+(?:if|when|whenever|iff|\.|,)", after_anchor)
        em_name = _extract_em_name(full_text)
        if em_name:
            name = _name_from_raw(em_name)
        elif prop_m:
            name = _name_from_raw(prop_m.group(1))
        else:
            name = _name_from_raw(name_text)
        add(full_text, name or None, "R117_IS_SAID_TO_BE", name_start)

    # ------------------------------------------------------------------
    # R4: 'X is called (the/a/an) <name>' anchor-based
    # ------------------------------------------------------------------
    for anchor_m in R4_IS_CALLED.finditer(masked_text):
        name_text, name_start = _anchor_lookback(masked_text, anchor_m.start())
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _C2_TAIL.match(masked_text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        called_start = anchor_m.end()
        called_snippet = masked_text[called_start:called_start + 80]
        called_m = re.match(r"([^.,;]+)", called_snippet)
        called_name = called_m.group(1).strip() if called_m else None
        name = _name_from_raw(called_name) if called_name else _name_from_raw(name_text)
        add(full_text, name or None, "R4_IS_CALLED", name_start)

    # ------------------------------------------------------------------
    # R5: 'X is/are considered as \emph/\textit{term}'
    # ------------------------------------------------------------------
    for m in R5_CONSIDERED_AS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group("name")
        emph_m = re.search(r"\\(?:emph|textit|textbf)\{([^}]{1,80})\}", full_text)
        name = emph_m.group(1) if emph_m else _name_from_raw(name_raw)
        add(full_text, name or None, "R5_CONSIDERED_AS", m.start())

    # ------------------------------------------------------------------
    # R6: 'X ...; that is, <display eq> [where ...]'
    # ------------------------------------------------------------------
    for m in R6_THAT_IS_EQUATION.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name")
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name, "R6_THAT_IS_EQUATION", m.start())

    # ------------------------------------------------------------------
    # R7: \item entries inside itemize with label + display equation
    # ------------------------------------------------------------------
    for env_m in R7_ITEMIZE_ENV.finditer(masked_text):
        env_body = env_m.group(1)
        env_start = env_m.start(1)
        items = R7_ITEM_SPLIT.split(env_body)
        offset = 0
        for item_text in items:
            item_len = len(item_text)
            if not item_text.strip():
                offset += item_len
                continue
            if not R7_HAS_DISPLAY.search(item_text):
                offset += item_len
                continue
            lm = R7_ITEM_LABEL.match(item_text)
            if lm:
                label_name = lm.group("label1") or lm.group("label2")
                body_text = lm.group("body")
                if label_name and body_text:
                    item_start = env_start + offset
                    full_raw = text[item_start: item_start + item_len]
                    name = label_name.strip()
                    add(full_raw, name, "R7_ITEMIZE_ENV", item_start)
            offset += item_len

    # ------------------------------------------------------------------
    # R8: '\textit{X} means that ...'
    # ------------------------------------------------------------------
    for m in R8_MEANS_THAT.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name = m.group("name")
        add(full_text, name or None, "R8_MEANS_THAT", m.start())

    # ------------------------------------------------------------------
    # R9: 'The <TERM> of X is <display equation>'
    # ------------------------------------------------------------------
    for m in R9_IS_EQUATION.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        name_raw = m.group("name")
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name, "R9_IS_EQUATION", m.start())

    # ------------------------------------------------------------------
    # R11: 'We call ... as (a/an) \emph{NAME}.'
    # ------------------------------------------------------------------
    for m in R11_WE_CALL_EMPH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name = m.group("name")
        add(full_text, name or None, "R11_WE_CALL_EMPH", m.start())

    # ------------------------------------------------------------------
    # R12: 'We call it/them/this/these (a/an/the) \emph{NAME}.'
    # ------------------------------------------------------------------
    for m in R12_CALL_IT_EMPH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name = m.group("name")
        add(full_text, name or None, "R12_CALL_IT_EMPH", m.start())

    # ------------------------------------------------------------------
    # R13: prose with \emph{term} + display equation in same block
    # ------------------------------------------------------------------
    for m in R13_EMPH_DISPLAY_EQ.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if len(full_text) > 3000:
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        name = m.group("name")
        add(full_text, name or None, "R13_EMPH_DISPLAY_EQ", m.start())

    # ------------------------------------------------------------------
    # R14: 'represent X by/as/using ... <display equation>'
    # ------------------------------------------------------------------
    for m in R14_REPRESENT_BY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group("name")
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name, "R14_REPRESENT_BY", m.start())

    # ------------------------------------------------------------------
    # R15: 'we measure/denote TERM by <display equation>'
    # ------------------------------------------------------------------
    for m in R15_MEASURE_BY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group("name")
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name, "R15_MEASURE_BY", m.start())

    # ------------------------------------------------------------------
    # R19: Enumerative 'when X, Y is Z' definitional sentences
    # ------------------------------------------------------------------
    for m in R19_WHEN_ENUM.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if not _WHEN_DEFN_INDICATOR.search(full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 2000:
            continue
        add(full_text, None, "R19_WHEN_ENUM", m.start())

    # ------------------------------------------------------------------
    # R20: 'X is/are, by definition, ...'
    # ------------------------------------------------------------------
    for m in R20_BY_DEFINITION.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group("name").strip()
        if len(name_raw) < 2 or len(name_raw) > 100:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R20_BY_DEFINITION", m.start())

    # ------------------------------------------------------------------
    # R23: 'X are/is parametrized/characterized by ... if <cond>'
    # ------------------------------------------------------------------
    for m in R23_PARAMETRIZED_IF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group("name").strip()
        if len(name_raw) < 2 or len(name_raw) > 120:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R23_PARAMETRIZED_IF", m.start())

    # ------------------------------------------------------------------
    # R24: 'Introducing/Defining/Denoting X via/as/by ...'
    # ------------------------------------------------------------------
    for m in R24_INTRODUCING.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if len(name_raw) < 1 or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R24_INTRODUCING", m.start())

    # ------------------------------------------------------------------
    # R25: 'the following functions/quantities/objects: <env with :=>'
    # ------------------------------------------------------------------
    for m in R25_FOLLOWING_FUNCTIONS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if ":=" not in full_text:
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = m.group("name")
        name_raw = _trim_name_to_boundary(name_raw, max_len=200)
        if not name_raw:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R25_FOLLOWING_FUNCTIONS", m.start())

    # ------------------------------------------------------------------
    # R26: '[subject] are/is given by <display env or $$>'
    # ------------------------------------------------------------------
    for m in R26_GIVEN_BY_ENV.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name")
        name_raw = _trim_name_to_boundary(name_raw, max_len=150)
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R26_GIVEN_BY_ENV", m.start())

    # ------------------------------------------------------------------
    # R27: '[subject] are/is defined by <display env or $$>'
    # ------------------------------------------------------------------
    for m in R27_DEFINED_BY_DISPLAY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        name_raw = m.group("name")
        name_raw = _trim_name_to_boundary(name_raw, max_len=120)
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R27_DEFINED_BY_DISPLAY", m.start())

    # ------------------------------------------------------------------
    # R28: 'X can/may/could be defined as ...' (modal C2 extension)
    # ------------------------------------------------------------------
    for anchor_m in R28_CAN_BE_DEFINED.finditer(masked_text):
        name_text, name_start = _anchor_lookback(masked_text, anchor_m.start())
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _C2_TAIL_ENV.match(masked_text, anchor_m.end())
        if not tail_m:
            tail_m = _C2_TAIL.match(masked_text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        name = _name_from_raw(name_text)
        add(full_text, name or None, "R28_CAN_BE_DEFINED", name_start)

    # ------------------------------------------------------------------
    # R29: '[subject] defined through/via the following <words> <env>'
    # ------------------------------------------------------------------
    for m in R29_DEFINED_THROUGH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 4000:
            continue
        name_raw = m.group("name")
        name_raw = _trim_name_to_boundary(name_raw, max_len=150)
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R29_DEFINED_THROUGH", m.start())

    # ------------------------------------------------------------------
    # R30: 'We define X through/by/via the formula \begin{equation}...'
    # ------------------------------------------------------------------
    for m in R30_DEFINE_VIA_ENV.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _C1_NEGATIVE.search(full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text.strip()) < 20:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R30_DEFINE_VIA_ENV", m.start())

    # ------------------------------------------------------------------
    # R31: '...as follows: <env> This definition...'
    # ------------------------------------------------------------------
    for m in R31_AS_FOLLOWS_DEFN.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group("name")
        name_raw = _trim_name_to_boundary(name_raw, max_len=120)
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R31_AS_FOLLOWS_DEFN", m.start())

    # ------------------------------------------------------------------
    # R32: 'the notion/concept of X defined by ...'
    # ------------------------------------------------------------------
    for m in R32_NOTION_OF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R32_NOTION_OF", m.start())

    # ------------------------------------------------------------------
    # R34: shorthand/convenient notation(s) + math block
    # ------------------------------------------------------------------
    for m in R34_SHORTHAND_NOTATION.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if not full_text.strip():
            continue
        if len(full_text) > 5000:
            continue
        lhs = re.search(r"([\$\\A-Za-z_][^&=:,\s]{0,40}):=", full_text)
        name = _name_from_raw(lhs.group(1).strip()) if lhs else "notation"
        add(full_text, name or None, "R34_SHORTHAND_NOTATION", m.start())

    # ------------------------------------------------------------------
    # R35: 'so-called / known as X ... given/defined by <math block>'
    # ------------------------------------------------------------------
    for m in R35_SO_CALLED.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if not full_text.strip():
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R35_SO_CALLED", m.start())

    # ------------------------------------------------------------------
    # R37: ':=' inside align/equation/gather environments
    # ------------------------------------------------------------------
    for m in R37_WALRUS_ENV.finditer(masked_text):
        prose = m.group("prose").strip()
        body = m.group("body")
        if not prose:
            continue
        if _REFERENTIAL.search(prose):
            continue
        full_text = text[m.start():m.end()]
        if not full_text.strip() or len(full_text) > 5000:
            continue
        name_raw = prose[-80:]
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name, "R37_WALRUS_ENV", m.start())

    # ------------------------------------------------------------------
    # R38: 'X will be / is / are denoted by $Y$'
    # ------------------------------------------------------------------
    for m in R38_DENOTED_BY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        name_raw = m.group("name").strip()
        name_raw = _trim_name_to_boundary(name_raw, max_len=120)
        if not name_raw or len(name_raw) < 2:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R38_DENOTED_BY", m.start())

    # ------------------------------------------------------------------
    # R39: 'motivate the name(s) (i) X, (ii) Y ...' naming pattern
    # ------------------------------------------------------------------
    for m in R39_MOTIVATE_NAMES.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if len(full_text) > 1000:
            continue
        if _REFERENTIAL.search(full_text):
            continue
        add(full_text, None, "R39_MOTIVATE_NAMES", m.start())

    # ------------------------------------------------------------------
    # R40: equation env with \label + definitional suffix
    # ------------------------------------------------------------------
    for m in R40_EQ_LABEL_SUFFIX.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        suffix_text = m.group("suffix") or ""
        name_m = re.search(
            r"\b(?:is\s+the|are\s+the|denotes?|represents?|stands?\s+for)\s+"
            r"(?:the\s+|an?\s+)?([^.,;\n]{1,60})",
            suffix_text,
            re.IGNORECASE,
        )
        name = _name_from_raw(name_m.group(1)) if name_m else None
        add(full_text, name, "R40_EQ_LABEL_SUFFIX", m.start())

    # ------------------------------------------------------------------
    # R41: equation env containing \equiv or := (definitional equality)
    # ------------------------------------------------------------------
    for m in R41_EQ_EQUIV.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group("body")
        lhs_m = re.search(r"([^\s\\,&]{1,40})\s*(?:\\equiv|:=)", body)
        name = _name_from_raw(lhs_m.group(1)) if lhs_m else None
        add(full_text, name, "R41_EQ_EQUIV", m.start())

    # ------------------------------------------------------------------
    # R42: 'where the following ...' + equation + 'have been introduced'
    # ------------------------------------------------------------------
    for m in R42_INTRODUCED_FOR.finditer(masked_text):
        prefix_text = m.group("prefix") or ""
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = prefix_text.strip()
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name, "R42_INTRODUCED_FOR", m.start())

    # ------------------------------------------------------------------
    # R45: 'definition of X \begin{equation}...\end{equation}'
    # ------------------------------------------------------------------
    for m in R45_DEFINITION_OF_EQ.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        pre_m = re.search(
            r"\bdefinition\s+of\s+(?P<name>[^\n{]{1,60}?)\s*\\begin",
            full_text,
            re.IGNORECASE | re.DOTALL,
        )
        name = _name_from_raw(pre_m.group("name")) if pre_m else None
        add(full_text, name, "R45_DEFINITION_OF_EQ", m.start())

    # ------------------------------------------------------------------
    # R46: 'leads to ... expression \begin{equation}...\end{equation}'
    # ------------------------------------------------------------------
    for m in R46_LEADS_TO_EXPR.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        add(full_text, None, "R46_LEADS_TO_EXPR", m.start())

    # ------------------------------------------------------------------
    # R47: 'where X are [description]: \begin{equation}...\end{equation}'
    # ------------------------------------------------------------------
    for m in R47_WHERE_COLON_EQ.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        pre_m = re.match(
            r"\bwhere\b\s*(?P<name>[^:]{1,80}?)\s*:",
            full_text,
            re.IGNORECASE | re.DOTALL,
        )
        name = _name_from_raw(pre_m.group("name")) if pre_m else None
        add(full_text, name, "R47_WHERE_COLON_EQ", m.start())

    # ------------------------------------------------------------------
    # R48: 'Here \begin{equation}...\end{equation} is/are [description].'
    # ------------------------------------------------------------------
    for m in R48_HERE_EQ_IS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        post_m = re.search(
            r"\\end\{(?:equation|eqnarray|align|multline|gather)\*?\}\s*"
            r"(?:is|are)\s+(?:the\s+|an?\s+)?(?P<name>[^.]{1,80})\.",
            full_text,
            re.DOTALL,
        )
        name = _name_from_raw(post_m.group("name")) if post_m else None
        add(full_text, name, "R48_HERE_EQ_IS", m.start())

    # ------------------------------------------------------------------
    # R49: 'by the substitution \begin{equation}...\end{equation} which ...'
    # ------------------------------------------------------------------
    for m in R49_BY_SUBSTITUTION.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        add(full_text, None, "R49_BY_SUBSTITUTION", m.start())

    # ------------------------------------------------------------------
    # R50: 'introducing [the] X \begin{equation}...\end{equation} [where ...]'
    # ------------------------------------------------------------------
    for m in R50_INTRODUCING_EQ.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        pre_m = re.search(
            r"\bintroducing\s+(?:the\s+)?(?P<name>[^\\\n]{1,60}?)\s*\\begin",
            full_text,
            re.IGNORECASE | re.DOTALL,
        )
        name = _name_from_raw(pre_m.group("name")) if pre_m else None
        add(full_text, name, "R50_INTRODUCING_EQ", m.start())

    # ------------------------------------------------------------------
    # R51: anchor 'are/is (inferred|given|...) (from|by) the (expansion|formula...)'
    # ------------------------------------------------------------------
    for anchor_m in R51_INFERRED_FROM.finditer(masked_text):
        name_text, name_start = _anchor_lookback(masked_text, anchor_m.start())
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _C2_TAIL_ENV.match(masked_text, anchor_m.end())
        if not tail_m:
            tail_m = _C2_TAIL.match(masked_text, anchor_m.end())
        if not tail_m:
            eq_end_m = re.search(
                r"\\end\{(?:equation|align|eqnarray|gather|multline)[*]?\}",
                masked_text[anchor_m.end():anchor_m.end() + 600],
            )
            if not eq_end_m:
                continue
            tail_end = anchor_m.end() + eq_end_m.end()
        else:
            tail_end = tail_m.end()
        full_text = text[name_start:tail_end]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        name = _name_from_raw(name_text)
        add(full_text, name or None, "R51_INFERRED_FROM", name_start)

    # ------------------------------------------------------------------
    # R52: Enumerated definition block: 'namely:' / 'as follows:' + (i)...(ii)...
    # ------------------------------------------------------------------
    for m in R52_ENUMERATED_DEFN.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        parts = re.split(r"\b(?:namely|as\s+follows)\s*:", full_text, maxsplit=1, flags=re.IGNORECASE)
        name_raw = parts[0].strip() if parts else ""
        for sep in (".", "\n"):
            pos = name_raw.rfind(sep)
            if pos >= 0:
                name_raw = name_raw[pos + 1:].strip()
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name, "R52_ENUMERATED_DEFN", m.start())

    # ------------------------------------------------------------------
    # R55: 'Let $X$ be ... so that <display math>.'
    # ------------------------------------------------------------------
    for m in R55_LET_SO_THAT.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R55_LET_SO_THAT", m.start())

    # ------------------------------------------------------------------
    # R56: 'This ... induces ... <display math> by ...'
    # ------------------------------------------------------------------
    for m in R56_INDUCES_DISPLAY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name") or ""
        lhs_m = re.search(r"\$\$\s*([^:=\s\\$][^:=]{0,40}?)\s*(?::|=)", name_raw)
        name = _name_from_raw(lhs_m.group(1)) if lhs_m else None
        add(full_text, name or None, "R56_INDUCES_DISPLAY", m.start())

    # ------------------------------------------------------------------
    # R57: 'we set \begin{align/equation/...}...\end{...}'
    # ------------------------------------------------------------------
    for m in R57_WE_SET_ENV.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        mathblock = m.group("mathblock") or ""
        lhs_m = re.search(r"([^\s\\,&$]{1,40})\s*(?:&?=|:=)", mathblock)
        name = _name_from_raw(lhs_m.group(1)) if lhs_m else None
        add(full_text, name or None, "R57_WE_SET_ENV", m.start())

    # ------------------------------------------------------------------
    # R59: '<X> is measured by <named object> of ...'
    # ------------------------------------------------------------------
    for m in R59_MEASURED_BY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 100:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R59_MEASURED_BY", m.start())

    # ------------------------------------------------------------------
    # R60: 'The/A/An {\em term} ... is ...' inline prose definition
    # ------------------------------------------------------------------
    for m in R60_THE_EM_IS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or
                    m.group("name3") or m.group("name4") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R60_THE_EM_IS", m.start())

    # ------------------------------------------------------------------
    # R61: 'We adopt/use/introduce the following notation: ...' + display math
    # ------------------------------------------------------------------
    for m in R61_FOLLOWING_NOTATION.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        lhs_m = re.search(r"([^\s\\,&$:]{1,40})\s*:=", full_text)
        name = _name_from_raw(lhs_m.group(1)) if lhs_m else "notation"
        add(full_text, name or None, "R61_FOLLOWING_NOTATION", m.start())

    # ------------------------------------------------------------------
    # R63: '{\em term} if \begin{enumerate/itemize}...' — def via list
    # ------------------------------------------------------------------
    for m in R63_EM_IF_LIST.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or
                    m.group("name3") or m.group("name4") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R63_EM_IF_LIST", m.start())

    # ------------------------------------------------------------------
    # R64: '... called [the/a/an] {\em term}' — definitional 'called' with emphasis
    # ------------------------------------------------------------------
    for m in R64_CALLED_EM.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or
                    m.group("name3") or m.group("name4") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R64_CALLED_EM", m.start())

    # ------------------------------------------------------------------
    # R65: 'define [the] {\em name} [of X] to be/as ...'
    # ------------------------------------------------------------------
    for m in R65_DEFINE_EM_NAME.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _C1_NEGATIVE.search(full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 4000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or m.group("name3") or
                    m.group("name4") or m.group("name5") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 120:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R65_DEFINE_EM_NAME", m.start())

    # ------------------------------------------------------------------
    # R67: 'leading/prompting/motivating us to define X := ...'
    # ------------------------------------------------------------------
    for m in R67_LEADING_TO_DEFINE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _C1_NEGATIVE.search(full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        name_raw = _trim_name_to_boundary(name_raw, max_len=80)
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name or None, "R67_LEADING_TO_DEFINE", m.start())

    # ------------------------------------------------------------------
    # R68: 'X is referred to as [a/an] {\em term}' anchor-based
    # ------------------------------------------------------------------
    for anchor_m in R68_REFERRED_TO_AS.finditer(masked_text):
        name_text, name_start = _anchor_lookback(masked_text, anchor_m.start())
        if not name_text or len(name_text) > 120:
            continue
        after_anchor = masked_text[anchor_m.end():anchor_m.end() + 300]
        em_name = _extract_em_name(after_anchor)
        tail_m = _C2_TAIL.match(masked_text, anchor_m.end())
        if not tail_m:
            tail_m = _C2_TAIL_ENV.match(masked_text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, name_start, tail_m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name = _name_from_raw(em_name) if em_name else _name_from_raw(name_text)
        add(full_text, name or None, "R68_REFERRED_TO_AS", name_start)

    # ------------------------------------------------------------------
    # R69: 'is defined (for ...) by ...' — extended passive definition anchor
    # ------------------------------------------------------------------
    for anchor_m in R69_IS_DEFINED_FOR_BY.finditer(masked_text):
        r1_test = re.match(r"\bis\s+(?:then\s+)?defined\s+(?:as|to\s+be)\s",
                           masked_text[anchor_m.start():], re.IGNORECASE)
        if r1_test:
            continue
        name_text, name_start = _anchor_lookback(masked_text, anchor_m.start())
        if not name_text or len(name_text) > 150:
            continue
        tail_m = _C2_TAIL_ENV.match(masked_text, anchor_m.end())
        if not tail_m:
            tail_m = _C2_TAIL.match(masked_text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _C1_NEGATIVE.search(full_text):
            continue
        if _inside_excluded_env(text, name_start, tail_m.end()):
            continue
        if len(full_text) > 3000:
            continue
        em_name = _extract_em_name(name_text)
        name = _name_from_raw(em_name) if em_name else _name_from_raw(name_text)
        add(full_text, name or None, "R69_IS_DEFINED_FOR_BY", name_start)

    # ------------------------------------------------------------------
    # R70: 'X is a {\em term} ... if/when ...' — 'is a <emph> if' pattern
    # ------------------------------------------------------------------
    for m in R70_IS_A_EM_IF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or
                    m.group("name3") or m.group("name4") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R70_IS_A_EM_IF", m.start())

    # ------------------------------------------------------------------
    # R72: 'X is called \emph{Y}' — definitional 'is called' with emphasis
    # ------------------------------------------------------------------
    for m in R72_IS_CALLED_EMPH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if not re.search(r"\\(?:emph|textit)\{", full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or m.group("name3") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R72_IS_CALLED_EMPH", m.start())

    # ------------------------------------------------------------------
    # R74: 'X is a \emph{Y} if <condition>' — definition via definitional 'if'
    # ------------------------------------------------------------------
    for m in R74_IS_EMPH_IF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if not re.search(r"\\(?:emph|textit)\{", full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or
                    m.group("name3") or m.group("name4") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R74_IS_EMPH_IF", m.start())

    # ------------------------------------------------------------------
    # R75: Definitions inside \footnote{...} with \emph{} definitional terms
    # ------------------------------------------------------------------
    for fn_m in R75_FOOTNOTE_EM_DEFN.finditer(masked_text):
        fn_body = fn_m.group("body")
        if not fn_body.strip():
            continue
        if _inside_excluded_env(text, fn_m.start(), fn_m.end()):
            continue
        _fn_is_emph_if = re.search(
            r"(?P<full>"
            r"(?P<subject>[^.\n]{1,200}?)"
            r"\bis\s+(?:a\s+|an\s+)?"
            r"(?:\\emph\{(?P<name1>[^}]{1,80})\}"
            r"|\\textit\{(?P<name2>[^}]{1,80})\}"
            r"|\{\\em\s+(?P<name3>[^}]{1,80})\})"
            r"[^.]{0,300}?"
            r"(?:\bif\b|\bwhen\b)"
            r"[^.]*\.)",
            fn_body,
            flags=re.DOTALL,
        )
        if _fn_is_emph_if:
            raw_match = _fn_is_emph_if.group("full")
            name_raw = (_fn_is_emph_if.group("name1") or
                        _fn_is_emph_if.group("name2") or
                        _fn_is_emph_if.group("name3") or "")
            name_raw = name_raw.strip()
            if name_raw and len(name_raw) <= 80:
                name = _name_from_raw(name_raw)
                raw_text = text[fn_m.start():fn_m.end()]
                add(raw_text, name or None, "R75_FOOTNOTE_EM_DEFN", fn_m.start())
                continue
        _fn_means = re.search(
            r"(?P<full>"
            r"(?:\\emph\{(?P<name>[^}]{1,80})\}|\\textit\{(?P<name2>[^}]{1,80})\})"
            r"[^.]{0,300}?\bif\b[^.]*\.)",
            fn_body,
            flags=re.DOTALL,
        )
        if _fn_means:
            name_raw = (_fn_means.group("name") or _fn_means.group("name2") or "")
            name_raw = name_raw.strip()
            if name_raw and len(name_raw) <= 80:
                name = _name_from_raw(name_raw)
                raw_text = text[fn_m.start():fn_m.end()]
                add(raw_text, name or None, "R75_FOOTNOTE_EM_DEFN", fn_m.start())

    # ------------------------------------------------------------------
    # R76: 'we (will) refer to X as \emph{Y}' — inline 'refer to as' with emphasis
    # ------------------------------------------------------------------
    for m in R76_REFER_TO_AS_EMPH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or m.group("name3") or
                    m.group("name4") or m.group("name5") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R76_REFER_TO_AS_EMPH", m.start())

    # ------------------------------------------------------------------
    # R77: '\emph{TERM}, where ...' — emph term with definitional where-clause
    # ------------------------------------------------------------------
    for m in R77_EMPH_WHERE_CLAUSE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R77_EMPH_WHERE_CLAUSE", m.start())

    # ------------------------------------------------------------------
    # R78: 'we define ... \emph{TERM} to be ...' with optional parenthetical
    # ------------------------------------------------------------------
    for m in R78_DEFINE_EMPH_TO_BE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _C1_NEGATIVE.search(full_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 4000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or
                    m.group("name3") or m.group("name4") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 120:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R78_DEFINE_EMPH_TO_BE", m.start())

    # ------------------------------------------------------------------
    # R80: 'We say that NAME if \[ ... \]' — definitional 'we say' with display math
    # ------------------------------------------------------------------
    for m in R80_WE_SAY_IF_DISPLAY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 100:
            continue
        em_name = _extract_em_name(full_text)
        name = _name_from_raw(em_name) if em_name else _name_from_raw(name_raw)
        add(full_text, name or None, "R80_WE_SAY_IF_DISPLAY", m.start())

    # ------------------------------------------------------------------
    # R83: 'let NAME := EXPR [, description]' — definitional assignment ':='
    # ------------------------------------------------------------------
    for m in R83_LET_WALRUS.finditer(text):
        full_text = m.group("full")
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R83_LET_WALRUS", m.start())

    # ------------------------------------------------------------------
    # R85: 'write $X$ ... and denote by $Y$ ...'
    # ------------------------------------------------------------------
    for m in R85_WRITE_AND_DENOTE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R85_WRITE_AND_DENOTE", m.start())

    # ------------------------------------------------------------------
    # R87: 'where $X$ = {... : ...}' set-builder notation definitions
    # ------------------------------------------------------------------
    for m in R87_WHERE_SET_BUILDER.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 1000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R87_WHERE_SET_BUILDER", m.start())

    # ------------------------------------------------------------------
    # R88: General footnote with definitional trigger language
    # ------------------------------------------------------------------
    for fn_m in R88_FOOTNOTE_DEFN.finditer(text):
        fn_body = fn_m.group("body")
        if not fn_body.strip():
            continue
        if not _R88_TRIGGER.search(fn_body):
            continue
        if re.search(r"\\(?:emph|textit)\{|\\{\\em\s", fn_body):
            continue
        if len(fn_body) > 2000:
            continue
        raw_text = fn_m.group(0)
        name_m = re.match(
            r"\s*(?:[Aa]n?\s+)?(?P<name>[A-Z][^.]{1,60}?)\s+"
            r"(?:is\s+a|is\s+an|holds?\s+for|is\s+defined)",
            fn_body,
            re.IGNORECASE,
        )
        name_raw = name_m.group("name").strip() if name_m else None
        if name_raw and len(name_raw) > 80:
            name_raw = None
        name = _name_from_raw(name_raw) if name_raw else None
        add(raw_text, name, "R88_FOOTNOTE_DEFN", fn_m.start())

    # ------------------------------------------------------------------
    # R90: Named concept in LaTeX double-quotes with 'called/termed/known as'
    # ------------------------------------------------------------------
    for m in R90_CALLED_DQUOTE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip().rstrip(".")
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R90_CALLED_DQUOTE", m.start())

    # ------------------------------------------------------------------
    # R91: 'assumption/notion/concept/condition of ``term''' with definitional clause
    # ------------------------------------------------------------------
    for m in R91_ASSUMPTION_OF_DQUOTE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R91_ASSUMPTION_OF_DQUOTE", m.start())

    # ------------------------------------------------------------------
    # R93: '[concept/method] is as follows' multi-sentence definitional block
    # ------------------------------------------------------------------
    for m in R93_IS_AS_FOLLOWS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        name_raw = m.group("name").strip()
        if len(name_raw) < 4:
            continue
        if _AS_FOLLOWS_PRONOUN.match(name_raw):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R93_IS_AS_FOLLOWS", m.start())

    # ------------------------------------------------------------------
    # R94: '[Concept] consists in [definitional description]'
    # ------------------------------------------------------------------
    for m in R94_CONSISTS_IN.finditer(masked_text):
        full_text = text[m.start():m.end()]
        name_raw = m.group("name").strip()
        if len(name_raw) < 5:
            continue
        if _CONSISTS_IN_PRONOUN.match(name_raw):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R94_CONSISTS_IN", m.start())

    # ------------------------------------------------------------------
    # R95: 'In other words, $X$ (and $Y$) are/is in fact $A$ (and $B$)'
    # ------------------------------------------------------------------
    for m in R95_IN_OTHER_WORDS_MATH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R95_IN_OTHER_WORDS_MATH", m.start())

    # ------------------------------------------------------------------
    # R96: 'In the terminology of X, Y is a [named concept]'
    # ------------------------------------------------------------------
    for m in R96_IN_TERMINOLOGY_OF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 120:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R96_IN_TERMINOLOGY_OF", m.start())

    # ------------------------------------------------------------------
    # R103: 'Formally, <name> = ...' — 'Formally,' as definitional marker
    # ------------------------------------------------------------------
    for m in R103_FORMALLY.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R103_FORMALLY", m.start())

    # ------------------------------------------------------------------
    # R105: 'X abbreviates ... <display math>' — abbreviation definitional pattern
    # ------------------------------------------------------------------
    for m in R105_ABBREVIATES.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        if not re.search(r'\$\$|\\\[|\$[^$]', full_text):
            if len(full_text.strip()) < 30:
                continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R105_ABBREVIATES", m.start())

    # ------------------------------------------------------------------
    # R106: 'let <name> = $$...$$' — 'let X = <display math>' definitional pattern
    # ------------------------------------------------------------------
    for m in R106_LET_DISPLAY_MATH.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R106_LET_DISPLAY_MATH", m.start())

    # ------------------------------------------------------------------
    # R108: 'We call (G,l) a {\it term} if ...' — extended 'we call X a <term> if'
    # ------------------------------------------------------------------
    for m in R108_WE_CALL_A_IF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        if len(full_text.strip()) < 30:
            continue
        name_raw = (m.group("name1") or m.group("name2") or m.group("name3") or
                    m.group("name4") or m.group("name5") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R108_WE_CALL_A_IF", m.start())

    # ------------------------------------------------------------------
    # R109: 'We say that a <NounPhrase> is <property> if ...'
    # ------------------------------------------------------------------
    for m in R109_WE_SAY_IS_IF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        if len(full_text.strip()) < 30:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 120:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R109_WE_SAY_IS_IF", m.start())

    # ------------------------------------------------------------------
    # R110: 'X is {\it Y} iff ...' — italicized iff-definition pattern
    # ------------------------------------------------------------------
    for m in R110_IS_IT_IFF.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or
                    m.group("name3") or m.group("name4") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R110_IS_IT_IFF", m.start())

    # ------------------------------------------------------------------
    # R112: 'Call this/it a/an <name>.' — imperative naming pattern
    # ------------------------------------------------------------------
    for m in R112_CALL_THIS_A.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or m.group("name3") or
                    m.group("name4") or m.group("name5") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R112_CALL_THIS_A", m.start())

    # ------------------------------------------------------------------
    # R114: 'We strengthen/extend/generalize <condition> to (<label>) $$...$$'
    # ------------------------------------------------------------------
    for m in R114_STRENGTHEN_TO.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        if len(full_text.strip()) < 20:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 100:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R114_STRENGTHEN_TO", m.start())

    # ------------------------------------------------------------------
    # R118: 'We introduce [the] {\em TERM} / \emph{TERM}' — definitional 'We introduce'
    # ------------------------------------------------------------------
    for m in R118_WE_INTRODUCE_EM.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = (m.group("name1") or m.group("name2") or
                    m.group("name3") or m.group("name4") or "")
        name_raw = name_raw.strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R118_WE_INTRODUCE_EM", m.start())

    # ------------------------------------------------------------------
    # R120: '\item <Name>, defined as <definition>.' — bullet-list inline definitions
    # ------------------------------------------------------------------
    for m in R120_ITEM_DEFINED_AS.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 3000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 120:
            continue
        name_raw = re.sub(r"^(?:The|A|An)\s+", "", name_raw)
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R120_ITEM_DEFINED_AS", m.start())

    # ------------------------------------------------------------------
    # R122: '(referred to as ``X'')' — inline alias/nickname pattern
    # ------------------------------------------------------------------
    for m in R122_REFERRED_TO_AS_INLINE.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 2000:
            continue
        alias_raw = (m.group("alias1") or m.group("alias2") or m.group("alias3") or "")
        alias_raw = alias_raw.strip().strip('"').strip("'").strip("`").strip("'")
        if not alias_raw or len(alias_raw) > 80:
            continue
        name = _name_from_raw(alias_raw)
        add(full_text, name or None, "R122_REFERRED_TO_AS_INLINE", m.start())

    # ------------------------------------------------------------------
    # R124: 'Likewise/Similarly, X ... combine/consist of ...'
    # ------------------------------------------------------------------
    for m in R124_LIKEWISE_COMBINES.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 1000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R124_LIKEWISE_COMBINES", m.start())

    # ------------------------------------------------------------------
    # R126: 'called X, plays/...: $$...$$ with \begin{equation}...\end{equation}'
    # ------------------------------------------------------------------
    for m in R126_CALLED_DISPLAY_EQ.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        if len(full_text.strip()) < 20:
            continue
        if not re.search(r'\$\$|\\\[', full_text):
            continue
        name_m = re.search(
            r'\bcalled\s+(?P<name>[\w\s\\${}^_]{1,60}?)(?:\s*,|\s*plays|\s*:|\s*is\b)',
            full_text, re.IGNORECASE
        )
        name_raw = name_m.group("name").strip() if name_m else None
        if name_raw and len(name_raw) > 80:
            name_raw = None
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name or None, "R126_CALLED_DISPLAY_EQ", m.start())

    # ------------------------------------------------------------------
    # R127: 'let ... $$SYMBOL = \left\{...\right\}$$' display-math set definitions
    # ------------------------------------------------------------------
    for m in R127_LET_DISPLAY_SET.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = m.group("name").strip() if m.group("name") else ""
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name or None, "R127_LET_DISPLAY_SET", m.start())

    # ------------------------------------------------------------------
    # R130: 'Let X be the solution of \be...\ee' (short-hand environment)
    # ------------------------------------------------------------------
    for m in R130_LET_BE_SHORTHAND_ENV.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = m.group("name").strip()
        if not name_raw or len(name_raw) > 80:
            continue
        if not re.search(
            r'\b(be|solution|function|map|space|operator|denote|given|satisfy)\b',
            full_text, re.IGNORECASE
        ):
            continue
        name = _name_from_raw(name_raw)
        add(full_text, name or None, "R130_LET_BE_SHORTHAND_ENV", m.start())

    # ------------------------------------------------------------------
    # R131: 'we set/and set \be...\ee' — definitional 'we set' with \be...\ee
    # ------------------------------------------------------------------
    for m in R131_WE_SET_SHORTHAND_ENV.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        body = m.group("body") or ""
        name_raw = m.group("name").strip() if m.group("name") else ""
        if not name_raw:
            lhs_m = re.match(r'\s*(?:\\label\{[^}]*\})?\s*([^=]{1,40})=', body)
            if lhs_m:
                name_raw = lhs_m.group(1).strip()
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name or None, "R131_WE_SET_SHORTHAND_ENV", m.start())

    # ------------------------------------------------------------------
    # R132: \be...\ee blocks with multiple definitions and definitional context
    # ------------------------------------------------------------------
    for m in R132_MULTI_DEF_SHORTHAND.finditer(masked_text):
        body = m.group("body")
        full_text = text[m.start():m.end()]
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if body.count('=') < 2:
            continue
        if not re.search(r',|\\quad|\\qquad|\\\\', body):
            continue
        pre_start = max(0, m.start() - 300)
        pre_text = masked_text[pre_start:m.start()]
        if not _DEF_CONTEXT_BEFORE.search(pre_text):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if len(full_text) > 3000:
            continue
        lhs_m = re.match(r'\s*(?:\\label\{[^}]*\})?\s*([^=,\\&]{1,40})=', body)
        name_raw = lhs_m.group(1).strip() if lhs_m else None
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name or None, "R132_MULTI_DEF_SHORTHAND", m.start())

    # ------------------------------------------------------------------
    # R134: 'let/define/set ... $$ G(s) = ... $$' display-math assignment
    # ------------------------------------------------------------------
    for m in R134_LET_DISPLAY_ASSIGN.finditer(masked_text):
        full_text = text[m.start():m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 5000:
            continue
        name_raw = m.group("name") or ""
        lhs_m = re.search(r'\$\$\s*([^$=]{1,40})\s*=', name_raw)
        if lhs_m:
            name_raw = lhs_m.group(1).strip()
        else:
            name_raw = ""
        if "=" not in full_text:
            continue
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name or None, "R134_LET_DISPLAY_ASSIGN", m.start())

    # ------------------------------------------------------------------
    # R136: '\subsection{Definition of ...}' block — definitional subsection
    # ------------------------------------------------------------------
    for m in R136_SUBSEC_DEFINITION.finditer(masked_text):
        full_text = text[m.start():m.end()]
        body = m.group("body") or ""
        if not re.search(r'\b(?:Let|let|Define|define|Set|set)\b', body):
            continue
        if not re.search(r'\\be\b|\\begin\{equation|\\begin\{align|\$\$|\\\[', body):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if len(full_text) > 10000:
            continue
        title_m = re.search(r'\\(?:sub)*section\{([^}]*)\}', full_text)
        name_raw = title_m.group(1).strip() if title_m else None
        name = _name_from_raw(name_raw) if name_raw else None
        add(full_text, name or None, "R136_SUBSEC_DEFINITION", m.start())

    # ------------------------------------------------------------------
    # Final deduplication by text overlap (keep first / larger span)
    # ------------------------------------------------------------------
    results.sort(key=lambda r: (text.find(r["raw_latex"]) if r["raw_latex"] in text else 0))

    deduped = []
    final_spans: list = []
    for r in results:
        raw = r["raw_latex"]
        pos = text.find(raw)
        if pos < 0:
            deduped.append(r)
            continue
        end = pos + len(raw)
        if _overlaps(pos, end, final_spans):
            continue
        final_spans.append((pos, end))
        deduped.append(r)

    for r in deduped:
        r.pop('_start', None)

    return deduped


# --- auto-repair: alias case-mismatched globals ---
_referential = _REFERENTIAL
