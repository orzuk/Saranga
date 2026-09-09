try:
    from latex_clean import clean_latex_to_text as _clean_latex
except Exception:
    _clean_latex = lambda s: s

import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helper: detect whether a span falls inside an excluded environment
# ---------------------------------------------------------------------------
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|figure|table|lstlisting|verbatim|tikzpicture)\*?\}.*?'
    r'\\end\{\1\*?\}',
    re.DOTALL | re.IGNORECASE,
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Custom-prefixed theorem-like environments (my*, custom*, etc.)
# ---------------------------------------------------------------------------
_CUSTOM_THEOREM_ENV_RE = re.compile(
    r'\\begin\{(?P<env>'
    r'my(?:Thm|Theorem|Lem|Lemma|Prop|Proposition|Cor|Corollary|Claim|Conj|Conjecture|Problem)'
    r'|custom(?:Thm|Theorem|Lem|Lemma|Prop|Proposition|Cor|Corollary|Claim)'
    r')\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)

_CUSTOM_ENV_KIND: Dict[str, str] = {
    'mythm': 'theorem',
    'mytheorem': 'theorem',
    'mylem': 'lemma',
    'mylemma': 'lemma',
    'myprop': 'proposition',
    'myproposition': 'proposition',
    'mycor': 'corollary',
    'mycorollary': 'corollary',
    'myclaim': 'claim',
    'myconj': 'conjecture',
    'myconjecture': 'conjecture',
    'myproblem': 'problem',
    'customthm': 'theorem',
    'customtheorem': 'theorem',
    'customlem': 'lemma',
    'customlemma': 'lemma',
    'customprop': 'proposition',
    'customproposition': 'proposition',
    'customcor': 'corollary',
    'customcorollary': 'corollary',
    'customclaim': 'claim',
}


# ---------------------------------------------------------------------------
# \begin{property} / \begin{fact} environments — mapped to proposition/claim
# ---------------------------------------------------------------------------
_PROPERTY_FACT_ENV_RE = re.compile(
    r'\\begin\{(?P<env>property\*?|fact\*?|Property\*?|Fact\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?:\[[^\]]*\])?'
    r'(?:\([^)]*\))?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)

_PROPERTY_FACT_KIND: Dict[str, str] = {
    'property': 'proposition',
    'property*': 'proposition',
    'fact': 'proposition',
    'fact*': 'proposition',
}


# ---------------------------------------------------------------------------
# Starred variants of standard theorem-like environments
# e.g. \begin{lemma*}...\end{lemma*}, \begin{theorem*}...\end{theorem*}
# ---------------------------------------------------------------------------
_STARRED_THEOREM_ENV_RE = re.compile(
    r'\\begin\{(?P<env>'
    r'(?:lemma|theorem|proposition|corollary|claim|conjecture|problem)\*'
    r')\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)

_STARRED_ENV_KIND: Dict[str, str] = {
    'lemma*': 'lemma',
    'theorem*': 'theorem',
    'proposition*': 'proposition',
    'corollary*': 'corollary',
    'claim*': 'claim',
    'conjecture*': 'conjecture',
    'problem*': 'problem',
}

# ---------------------------------------------------------------------------
# \claim{...} macro pattern
# ---------------------------------------------------------------------------
_CLAIM_MACRO_RE = re.compile(
    r'\\claim\{(?P<body>[^}]{10,})\}',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# \begin{description}...\end{description} — mathematical case/type enumeration
# mapped to 'claim'
# ---------------------------------------------------------------------------
_DESCRIPTION_ENV_RE = re.compile(
    r'\\begin\{(?P<env>description\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# \begin{itemize}...\end{itemize} — mathematical enumeration lists
# mapped to 'claim' when containing math content
# ---------------------------------------------------------------------------
# PRUNED — FP on 1207.0773v2, 1512.05406v1, 1705.02177v2 +3 more | also 17 TP — review before uncommenting
# _ITEMIZE_ENV_RE = re.compile(
#     r'\\begin\{(?P<env>itemize\*?)\}'
#     r'(?:\[(?P<opt>[^\]]*)\])?'
#     r'(?P<body>.*?)'
#     r'\\end\{(?P=env)\}',
#     re.DOTALL | re.IGNORECASE,
# )


# ---------------------------------------------------------------------------
# Optimization problems in eqnarray / eqnarray* / align / align*
# preceded by an introducing sentence
# ---------------------------------------------------------------------------
_OPT_EQNARRAY_RE = re.compile(
    r'(?P<intro>[^\n]{0,400}?'
    r'(?:we\s+(?:solve|consider|formulate|study|address|propose)|'
    r'(?:following|this|the)\s+(?:sparse\s+coding\s+)?(?:optimization\s+)?problem|'
    r'minimiz|maximiz|optim(?:iz|is))'
    r'[^\n]{0,300}\n)'
    r'(?P<env>\\begin\{(?P<envname>eqnarray\*?|align\*?|equation\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)

_OPT_BODY_TRIGGER_RE = re.compile(
    r'\\(?:arg\s*\\)?(?:min|max)\b|\\operatorname\{(?:arg\s*)?(?:min|max)\}|'
    r'subject\s+to|\\text\{s\.t\.',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Optimization problems in enumerate blocks
# ---------------------------------------------------------------------------
_OPT_ENUMERATE_RE = re.compile(
    r'(?P<intro>[^\n]{0,500}?'
    r'(?:minimiz|maximiz|optim(?:iz|is)|cases?\s+to\s+be\s+considered)'
    r'[^\n]{0,300}\n)'
    r'(?P<env>\\begin\{enumerate\}(?:\[[^\]]*\])?'
    r'(?P<body>.*?)'
    r'\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Future-work / open-problem sentences (prose, not in an environment)
# ---------------------------------------------------------------------------
# PRUNED — FP on 1207.0773v2, 1502.03482v2, 1705.02177v2 +2 more | also 5 TP — review before uncommenting
# _FUTURE_WORK_RE = re.compile(
#     r'(?:^|(?<=[.\n]))\s*'
#     r'(?P<sentence>'
#     r'[A-Z][^.!?]{10,600}?'
#     r'(?:'
#     r'leave[^.!?]{0,120}future\s+work|'
#     r'future\s+work[^.!?]{0,120}|'
#     r'open\s+(?:problem|question)[^.!?]{0,120}|'
#     r'remain[^.!?]{0,80}open|'
#     r'left\s+(?:as\s+)?(?:an?\s+)?(?:open\s+)?(?:future|open)'
#     r')'
#     r'[^.!?]*[.!?]'
#     r')',
#     re.DOTALL | re.IGNORECASE | re.MULTILINE,
# )


# ---------------------------------------------------------------------------
# Inline bold/italic theorem-like keyword pattern — PRUNED
# PRUNED — FP on 1508.06062v1
# _INLINE_THM_KEYWORD_RE = re.compile(
#     r'(?:^|(?<=\n))[ \t]*'
#     r'(?:\\textbf\{|\\textit\{|\\emph\{)?'
#     r'(?P<kind>Theorem|Lemma|Proposition|Corollary|Claim|Conjecture|Problem|Observation)'
#     r'(?:\})?'
#     r'(?:\s*\d+(?:\.\d+)*)?'
#     r'\s*[.:]\s*'
#     r'(?P<body>[^\n]{20,}(?:\n(?!\n)[^\n]+){0,10})',
#     re.MULTILINE,
# )

_INLINE_THM_KIND_MAP: Dict[str, str] = {
    'theorem': 'theorem',
    'lemma': 'lemma',
    'proposition': 'proposition',
    'corollary': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'problem': 'problem',
    'observation': 'theorem',
}


# ---------------------------------------------------------------------------
# Inline named conjecture/theorem statement pattern
# e.g. "the Willmore Conjecture says that ..."
# ---------------------------------------------------------------------------
# PRUNED — FP on 1705.02177v2
# _NAMED_STATEMENT_RE = re.compile(
#     r'(?:(?:the|The)\s+)?'
#     r'(?:[A-Z][A-Za-z\-]+\s+){0,3}'
#     r'(?P<kind>Conjecture|Theorem|Lemma|Proposition|Claim)'
#     r'\s+(?:says?|states?|asserts?|claims?|predicts?)\s+that\s+'
#     r'(?P<body>.{30,600}?)'
#     r'(?=\.\s|\n\n|\\(?:begin|section|subsection))',
#     re.DOTALL,
# )


# ---------------------------------------------------------------------------
# Inline problem statement pattern — PRUNED
# PRUNED — FP on 1512.05406v1
# _INLINE_PROBLEM_RE = re.compile(...)


# ---------------------------------------------------------------------------
# Open problem / gap prose sentences
# Extends _FUTURE_WORK_RE with additional anchors
# ---------------------------------------------------------------------------
# PRUNED — FP on 1102.4533v1, 1412.0216v2, 1705.02177v2 +1 more | also 2 TP — review before uncommenting
# _OPEN_PROBLEM_PROSE_RE = re.compile(
#     r'(?:^|(?<=[.\n]))\s*'
#     r'(?P<sentence>'
#     r'[A-Z][^.!?]{10,600}?'
#     r'(?:'
#     r'(?:is|are)\s+(?:almost\s+completely\s+|still\s+|largely\s+)?open(?:\s+up\s+to\s+now)?|'
#     r'leave\s+(?:this\s+)?(?:\w+\s+)?(?:issue\s+)?open|'
#     r'missing\s+up\s+to\s+now|'
#     r'an?\s+open\s+(?:problem|question)|'
#     r'open\s+(?:problem|question)\s+(?:for|in|to)|'
#     r'(?:is|remains?)\s+unknown'
#     r')'
#     r'[^.!?]{0,200}[.!?]'
#     r')',
#     re.DOTALL | re.IGNORECASE | re.MULTILINE,
# )


# ---------------------------------------------------------------------------
# Informal claim/observation phrases — PRUNED
# PRUNED — FP on 1103.5544v1, 1502.03482v2 | also 2 TP — review before uncommenting
# _INFORMAL_CLAIM_RE = re.compile(...)


# ---------------------------------------------------------------------------
# Result-announcing phrase before display math (eqnarray or equation)
# ---------------------------------------------------------------------------
_RESULT_INTRO_EQNARRAY_RE = re.compile(
    r'(?:'
    r'one\s+(?:finds?|gets?|has|obtains?)'
    r'|we\s+(?:find|get|obtain|have|derive|show)'
    r'|leads?\s+to\s+the\s+(?:following|final|main|key|simple)\s+\w+'
    r'|have\s+the\s+(?:simple\s+)?(?:general\s+)?form'
    r'|the\s+(?:final|main|key|central|simple)\s+result\s+(?:is|reads)'
    r')'
    r'[^%\\]{0,400}?'
    r'(?P<env>\\begin\{(?P<envname>eqnarray\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)

_RESULT_INTRO_EQ_RE = re.compile(
    r'(?:'
    r'one\s+(?:finds?|gets?|has|obtains?)'
    r'|we\s+(?:find|get|obtain|have|derive|show)'
    r'|leads?\s+to\s+the\s+(?:following|final|main|key|simple)\s+\w+'
    r'|have\s+the\s+(?:simple\s+)?(?:general\s+)?form'
    r'|the\s+(?:final|main|key|central|simple)\s+result\s+(?:is|reads)'
    r')'
    r'[^%\\]{0,400}?'
    r'(?P<env>\\begin\{(?P<envname>equation\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Prose open-problem sentences with forward-looking / future-work language
# ---------------------------------------------------------------------------
_FORWARD_LOOKING_RE = re.compile(
    r'(?:^|(?<=\n\n)|\.\s+)'
    r'(?P<sentence>'
    r'(?:'
    r'It\s+(?:will\s+be|would\s+be|remains?)\s+(?:interesting|important|natural|worthwhile)'
    r'|[Aa]n?\s+(?:open|outstanding|interesting)\s+(?:problem|question|challenge)'
    r'|[Ff]uture\s+(?:work|research|directions?)'
    r'|[Ww]e\s+(?:leave|defer|plan|intend)\s+(?:this|these|it|the)'
    r'|[Ii]t\s+would\s+be\s+(?:interesting|desirable|useful)\s+to'
    r'|[Ww]e\s+hope\s+that'
    r'|[Aa]\s+new\s+idea\s+is\s+needed'
    r')'
    r'[^.!?]{20,600}[.!?]'
    r')',
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Prose claim sentences with assertive opening anchors — PRUNED
# PRUNED — FP on 1512.05406v1, 1601.01819v1, 1705.02177v2 | also 4 TP — review before uncommenting
# _PROSE_CLAIM_RE = re.compile(...)


# ---------------------------------------------------------------------------
# Prose conjecture: "We conjecture ..." / "We believe ..." — PRUNED
# PRUNED — FP on 1502.03482v2, 1512.05406v1 | also 1 TP — review before uncommenting
# _WE_CONJECTURE_RE = re.compile(...)


# ---------------------------------------------------------------------------
# Prose conjecture: "<Name/phrase> conjectured that ..."
# ---------------------------------------------------------------------------
_X_CONJECTURED_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,200}?'
    r'\bconjectured\s+that\b'
    r'[^.!?]{10,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose conjecture: "... conjecture ..., stating that ..."
# ---------------------------------------------------------------------------
_CONJECTURE_STATING_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'\bconjecture\b[^.!?]{0,100}?'
    r'stating\s+that\b'
    r'[^.!?]{10,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose conjecture: "... conjecture ... states that ..."
# ---------------------------------------------------------------------------
_CONJECTURE_STATES_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'\bconjecture\b[^.!?]{0,100}?'
    r'states?\s+that\b'
    r'[^.!?]{10,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose conjecture: "... asserts that ..." (conjecture-like inline assertion)
# ---------------------------------------------------------------------------
_ASSERTS_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'\basserts?\s+that\b'
    r'[^.!?]{10,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose conjecture: "... hypothesize[d] that ..." / "we hypothesize that ..."
# ---------------------------------------------------------------------------
_HYPOTHESIZE_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'\bhypothesized?\s+that\b'
    r'[^.!?]{10,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose conjecture: "We conjecture / we expect / we anticipate ..." inline
# Catches: "We conjecture a crossover ...", "We anticipate that ...",
#          "We expect that ...", "It is expected that ..."
# ---------------------------------------------------------------------------
# PRUNED — FP on 1502.03482v2, 1510.04064v1, 1512.05406v1 +4 more | also 2 TP — review before uncommenting
# _WE_CONJECTURE_INLINE_RE = re.compile(
#     r'(?:^|(?<=[.!?\n]))\s*'
#     r'(?P<body>'
#     r'(?:'
#     r'[Ww]e\s+conjecture\b'
#     r'|[Ww]e\s+expect\b'
#     r'|[Ww]e\s+anticipate\b'
#     r'|[Ww]e\s+believe\b'
#     r'|[Ww]e\s+predict\b'
#     r'|[Ii]t\s+is\s+(?:conjectured|expected|believed|anticipated)\b'
#     r')'
#     r'[^.!?]{10,600}?'
#     r'[.!?]'
#     r')',
#     re.MULTILINE | re.DOTALL,
# )


# ---------------------------------------------------------------------------
# Prose open problem: "The question is whether/if ..."
# ---------------------------------------------------------------------------
_THE_QUESTION_IS_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[Tt]he\s+question\s+is\s+(?:whether|if)\b'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose open problem: "we don't/do not know ..."
# ---------------------------------------------------------------------------
_WE_DONT_KNOW_RE = re.compile(
    r'(?:^|(?<=[,;.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,200}?'
    r"(?:we\s+don'?t\s+know|we\s+do\s+not\s+know)\b"
    r'[^.!?]{5,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Prose open problem: "We wonder if/whether ..."
# ---------------------------------------------------------------------------
_WE_WONDER_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'(?:We|I)\s+wonder\s+(?:if|whether)\b'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose open problem: "It is natural/reasonable to ask ..."
# ---------------------------------------------------------------------------
_IT_IS_NATURAL_TO_ASK_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'(?:[A-Z][^.!?]{0,100}?)?'
    r'[Ii]t\s+is\s+(?:natural|reasonable|interesting|worth(?:while)?)\s+(?:now\s+)?to\s+ask\b'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose open problem: rhetorical question in "What if ..." form
# ---------------------------------------------------------------------------
_WHAT_IF_MATH_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[Ww]hat\s+if\b'
    r'[^?!]{10,500}?'
    r'\$[^$]+\$'
    r'[^?!]{0,300}?'
    r'[?!]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose claim: "There is/are (also) ..." + display math
# ---------------------------------------------------------------------------
_THERE_IS_WITH_MATH_RE = re.compile(
    r'(?:^|\n{2,})'
    r'(?P<body>'
    r'There\s+(?:is(?:\s+also)?|are)\s+[^\n]{0,300}'
    r'(?:'
    r'(?:\$\$.*?\$\$)'
    r'|(?:\\begin\{(?:multline|align|equation|CD|gather)\*?\}.*?\\end\{(?:multline|align|equation|CD|gather)\*?\})'
    r')'
    r'[\s\S]{0,600}?'
    r')'
    r'(?=\n{2,}|\\begin\{(?:conjecture|proposition|theorem|lemma|proof|corollary|remark)\})',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose claim: "So/Thus/Hence there is/are ..." + display math
# ---------------------------------------------------------------------------
_SO_THERE_IS_WITH_MATH_RE = re.compile(
    r'(?:^|\n{2,})'
    r'(?P<body>'
    r'(?:So|Thus|Hence|Therefore|Consequently)\s+there\s+(?:is|are)\s+[^\n]{0,300}'
    r'(?:'
    r'(?:\$\$.*?\$\$)'
    r'|(?:\\begin\{(?:multline|align|equation|CD|gather)\*?\}.*?\\end\{(?:multline|align|equation|CD|gather)\*?\})'
    r')'
    r'[\s\S]{0,600}?'
    r')'
    r'(?=\n{2,}|\\begin\{(?:conjecture|proposition|theorem|lemma|proof|corollary|remark)\})',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose claim: paragraph containing display math ($$...$$) introduced by
# common math-result opener phrases
# ---------------------------------------------------------------------------
_MATH_RESULT_OPENER_RE = re.compile(
    r'(?:^|\n{2,})'
    r'(?P<body>'
    r'(?:So|Thus|Hence|Therefore|Consequently|We\s+(?:get|obtain|have)|'
    r'In\s+\w+(?:\s+\w+)?\s+(?:notation|terms|language|coordinates))[^\n]{0,300}'
    r'(?:'
    r'(?:\$\$.*?\$\$)'
    r'|(?:\\begin\{(?:multline|align|equation|CD|gather)\*?\}.*?\\end\{(?:multline|align|equation|CD|gather)\*?\})'
    r')'
    r'[\s\S]{0,600}?'
    r')'
    r'(?=\n{2,}|\\begin\{(?:conjecture|proposition|theorem|lemma|proof|corollary|remark|section|subsection)\})',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# \noindent{\em Label.} ... paragraph-style informal claims
# ---------------------------------------------------------------------------
_NOINDENT_EM_CLAIM_RE = re.compile(
    r'\\noindent\s*'
    r'(?:\\textit\{|\\emph\{|\{\\em\s+|\{\\it\s+)'
    r'(?P<label>[^}]{1,120})'
    r'\}'
    r'(?P<body>.*?)'
    r'(?=\\(?:small|med|big)skip|\\noindent\s*(?:\\textit\{|\\emph\{|\{\\em\s+|\{\\it\s+)|'
    r'\\(?:sub)*section|\\end\{document\}|\Z)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Open problem items in "further work" / "open problems" sections
# ---------------------------------------------------------------------------
_FURTHER_WORK_SECTION_RE = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*(?:further|open\s+problem|future|direction|conclud)[^}]*\}'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.IGNORECASE | re.DOTALL,
)

_FURTHER_WORK_ITEM_RE = re.compile(
    r'\\noindent\s+'
    r'(?:[IVXLCDM]+|[A-Za-z]|\d+)[.\)]\s*'
    r'(?P<body>.+?)'
    r'(?=\\medskip|\\bigskip|\\smallskip|'
    r'\\noindent\s+(?:[IVXLCDM]+|[A-Za-z]|\d+)[.\)]|'
    r'\\(?:sub)*section|\\end\{document\}|\Z)',
    re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# "It would be interesting to find ..." sentences
# ---------------------------------------------------------------------------
_IT_WOULD_BE_INTERESTING_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[Ii]t\s+(?:would|will|may)\s+be\s+'
    r'(?:interesting|worthwhile|natural|important|desirable|useful|good)\s+'
    r'to\s+(?:find|determine|prove|investigate|study|understand|describe|compute|classify|explore|extend|develop)'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# "It is well known that ..." inline proposition pattern
# ---------------------------------------------------------------------------
_INLINE_WELL_KNOWN_RE = re.compile(
    r'(?:^|(?<=\n\n)|\n)'
    r'(?P<body>'
    r'It\s+is\s+well\s+known\s+that\b'
    r'[^.!?]{10,500}?'
    r'(?:\\cite\{[^}]+\})?'
    r'[^.!?]{0,100}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# "Since [known result with \cite{...}], we get the following." pattern
# ---------------------------------------------------------------------------
_SINCE_WE_GET_FOLLOWING_RE = re.compile(
    r'(?:^|(?<=\n))\s*'
    r'(?P<body>'
    r'Since\b[^.!?]{10,400}?'
    r'\\cite\{[^}]+\}'
    r'[^.!?]{0,200}?'
    r',\s*we\s+get\s+the\s+following'
    r'[^.!?]{0,100}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# "it has been shown / authors have shown that ... \cite{...}" implicit proposition
# ---------------------------------------------------------------------------
_INLINE_SHOWN_THAT_RE = re.compile(
    r'(?:^|(?<=\n\n)|\n)\s*'
    r'(?P<body>'
    r'(?:[A-Z][^.!?\n]{0,200}?)?'
    r'(?:it\s+has\s+been\s+shown|have\s+(?:recently\s+)?shown|has\s+been\s+shown)'
    r'\s+that\b'
    r'[^.!?]{10,600}?'
    r'(?:\\cite\{[^}]+\})'
    r'[^.!?]{0,150}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# "It is not hard to show / easy to see / straightforward to verify ..." — PRUNED
# PRUNED — FP on 1906.04768v3 | also 1 TP — review before uncommenting
# _IT_IS_NOT_HARD_RE = re.compile(...)


# ---------------------------------------------------------------------------
# Inline open problem: "... is currently unknown / remains unknown ..."
# ---------------------------------------------------------------------------
# PRUNED — FP on 1207.0773v2, 1404.1366v4, 1612.05419v3 +1 more | also 3 TP — review before uncommenting
# _CURRENTLY_UNKNOWN_RE = re.compile(
#     r'(?:^|(?<=[.!?\n]))\s*'
#     r'(?P<body>'
#     r'[A-Z][^.!?]{10,500}?'
#     r'(?:'
#     r'currently\s+unknown|'
#     r'remains?\s+(?:an?\s+)?open|'
#     r'is\s+not\s+(?:yet\s+)?(?:known|understood|resolved)|'
#     r'(?:precise|exact)\s+(?:boundary|characterization|interplay)[^.!?]{0,200}(?:unknown|not\s+known)|'
#     r'appears?\s+(?:a\s+)?difficult\s+problem'
#     r')'
#     r'[^.!?]{0,200}?'
#     r'[.!?]'
#     r')',
#     re.MULTILINE | re.DOTALL | re.IGNORECASE,
# )


# ---------------------------------------------------------------------------
# Cited lemma/theorem inline restatement:
# \cite[Lemma N]{ref} which says that / which states that ...
# ---------------------------------------------------------------------------
_INLINE_CITED_LEMMA_RE = re.compile(
    r'\\cite\s*\[[^\]]*(?:Lemma|Theorem|Proposition|Corollary)\s*[^\]]*\]\s*\{[^}]+\}'
    r'\s+(?:which\s+(?:says?|states?|asserts?)|asserting)\s+that\b'
    r'(?P<body>[^.]{10,500}?(?:\.[^.]{0,200}?){0,4})'
    r'(?=\n\n|\\(?:begin|section|subsection|paragraph|end)\b|\Z)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Inline claim/proposition: "X is necessary/sufficient for Y: [claim] \cite{}"
# ---------------------------------------------------------------------------
_INLINE_NECESSITY_CLAIM_RE = re.compile(
    r'(?:^|(?<=\n\n)|\n)\s*'
    r'(?P<body>'
    r'[A-Z][^.!?\n]{5,200}?'
    r'(?:necessary|sufficient|required)\s+(?:condition\s+)?for\s+[^.!?\n]{5,150}?'
    r':\s*'
    r'[^.!?]{10,300}?'
    r'(?:\\cite\{[^}]+\})?'
    r'[^.!?]{0,100}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Inline claim between \end{...} and \begin{...} / section boundaries — PRUNED
# PRUNED — FP on 1103.5544v1, 1502.03482v2, 1512.05406v1 +3 more | also 62 TP — review before uncommenting
# _BETWEEN_ENV_CLAIM_RE = re.compile(...)

# ---------------------------------------------------------------------------
# Inline claim/result following \paragraph{...} heading
# ---------------------------------------------------------------------------
# PRUNED — FP on 1502.03482v2, 1803.04122v2 | also 1 TP — review before uncommenting
# _PARAGRAPH_HEADING_CLAIM_RE = re.compile(
#     r'\\paragraph\{[^}]*\}'
#     r'(?P<body>'
#     r'(?:(?!\\begin\{|\\end\{|\\section\b|\\subsection\b|\\paragraph\b).){40,800}?'
#     r'\$[^$]+\$'
#     r'(?:(?!\\begin\{|\\end\{|\\section\b|\\subsection\b|\\paragraph\b).){0,400}?'
#     r')'
#     r'(?=\\begin\{|\\section\b|\\subsection\b|\\paragraph\b|\Z)',
#     re.DOTALL,
# )

# ---------------------------------------------------------------------------
# "... proved/showed/demonstrated that ..." with \cite{} — PRUNED
# PRUNED — FP on 1705.02177v2
# _CITED_PROVED_SHOWED_RE = re.compile(...)

# ---------------------------------------------------------------------------
# "... showed/proved ... who showed ..." — relative clause result restatement
# ---------------------------------------------------------------------------
_WHO_SHOWED_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'\bwho\s+(?:showed?|proved?|demonstrated?|established?|obtained?)\s+'
    r'(?:that\b|an?\b|the\b)[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "It remains a major open problem whether ..." pattern
# ---------------------------------------------------------------------------
# PRUNED — FP on 1207.0773v2
# _REMAINS_OPEN_PROBLEM_RE = re.compile(
#     r'(?:^|(?<=[.!?\n]))\s*'
#     r'(?P<body>'
#     r'It\s+remains?\s+(?:a\s+)?(?:major\s+|key\s+|central\s+|important\s+)?'
#     r'open\s+(?:problem|question)\s+(?:whether|if|to)\b'
#     r'[^.!?]{10,500}?'
#     r'[.!?]'
#     r')',
#     re.MULTILINE | re.DOTALL | re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# "it is not even known whether ..." open problem pattern
# ---------------------------------------------------------------------------
_NOT_EVEN_KNOWN_RE = re.compile(
    r'(?:^|(?<=[.!?\n,;]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,200}?'
    r'(?:it\s+is\s+not\s+(?:even\s+)?known|not\s+(?:yet\s+)?known)\s+'
    r'(?:whether|if)\b'
    r'[^.!?]{10,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "... suffice / suffices to ..." result claim — PRUNED
# PRUNED — FP on 1207.0773v2, 1803.01284v2 | also 3 TP — review before uncommenting
# _SUFFICE_TO_RE = re.compile(
#     r'(?:^|(?<=[.!?\n]))\s*'
#     r'(?P<body>'
#     r'[A-Z][^.!?]{10,400}?'
#     r'(?:suffices?\s+to\s+(?:determine|identify|solve|find|compute|establish|prove)|'
#     r'\$[^$]{1,100}\$\s+(?:queries?|guesses?|steps?|rounds?|weighings?)\s+suffice)'
#     r'[^.!?]{0,300}?'
#     r'[.!?]'
#     r')',
#     re.MULTILINE | re.DOTALL | re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# "It follows from [ref/result] that ..." inline proposition
# ---------------------------------------------------------------------------
_IT_FOLLOWS_FROM_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'It\s+follows\s+from\b[^.!?]{5,300}?'
    r'(?:\\cite\{[^}]+\}|\\ref\{[^}]+\})'
    r'[^.!?]{0,200}?'
    r'that\b[^.!?]{10,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "... in particular, that ..." / "in particular, X implies Y" claim — PRUNED
# PRUNED — FP on 1708.00522v2
# _IN_PARTICULAR_CITE_RE = re.compile(
#     r'(?:^|(?<=[.!?\n]))\s*'
#     r'(?P<body>'
#     r'[A-Z][^.!?]{0,300}?'
#     r'\bin\s+particular\b[^.!?]{5,400}?'
#     r'\\cite\{[^}]+\}'
#     r'[^.!?]{0,150}?'
#     r'[.!?]'
#     r')',
#     re.MULTILINE | re.DOTALL | re.IGNORECASE,
# )

# ---------------------------------------------------------------------------
# Lettered list item claims: (a) ..., (b) ..., (c) ..., etc.
# ---------------------------------------------------------------------------
_LETTERED_LIST_CLAIM_RE = re.compile(
    r'(?:^|\n)\s*'
    r'\((?P<letter>[a-z])\)\s+'
    r'(?P<body>.+?)'
    r'(?=\n\s*\([a-z]\)\s+|\n\s*\n|\Z)',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Emphasized rhetorical question as open problem
# ---------------------------------------------------------------------------
_EMPH_OPEN_QUESTION_RE = re.compile(
    r'(?:\\emph\{|\{\\em\s+|\\textit\{)'
    r'(?P<body>[^}]{20,600}\?)'
    r'\}',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Optimization / math program introduced by narrative keyword "reads:"
# ---------------------------------------------------------------------------
_PROGRAM_READS_RE = re.compile(
    r'(?P<intro>'
    r'[^\n]{0,400}?'
    r'(?:'
    r'(?:linear|semidefinite|convex|optimization|relaxation)\s+program\b[^\n]{0,200}?reads\b|'
    r'(?:problem|hierarchy)[^\n]{0,200}?reads\b|'
    r'(?:problem|program|relaxation)\s+(?:is\s+)?(?:defined|given)\s+by\b[^\n]{0,200}'
    r')'
    r'[^\n]{0,200}?\n'
    r')'
    r'(?P<math>'
    r'(?:'
    r'\\\[[\s\S]{10,2000}?\\\]'
    r'|\\begin\{(?:equation|eqnarray|align|array)\*?\}[\s\S]{10,2000}?\\end\{(?:equation|eqnarray|align|array)\*?\}'
    r')'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "consider the hierarchy/problem/program ..." + display math
# ---------------------------------------------------------------------------
_CONSIDER_PROBLEM_RE = re.compile(
    r'(?P<intro>'
    r'[^\n]{0,300}?'
    r'(?:consider|define|introduce)\s+'
    r'(?:the\s+)?(?:following\s+)?'
    r'(?:hierarchy|program|problem|relaxation|optimization|formulation)\b'
    r'[^\n]{0,300}\n'
    r')'
    r'(?P<math>'
    r'(?:'
    r'\\\[[\s\S]{10,2000}?\\\]'
    r'|\\begin\{(?:equation|eqnarray|align|array)\*?\}[\s\S]{10,2000}?\\end\{(?:equation|eqnarray|align|array)\*?\}'
    r')'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "It is proved / It is shown that ... \begin{equation}..." pattern
# ---------------------------------------------------------------------------
_IT_IS_PROVED_EQ_RE = re.compile(
    r'(?:^|(?<=\n\n)|\n)\s*'
    r'(?P<intro>'
    r'[A-Z][^.!?]{0,300}?'
    r'(?:it\s+is\s+(?:proved?|shown|established|demonstrated)|'
    r'(?:we|they|one)\s+(?:have\s+)?(?:proved?|shown|established|demonstrated))'
    r'[^.!?]{0,300}?'
    r'that\b[^.!?]{0,300}?'
    r'(?:if\s+and\s+only\s+if|iff|if|when|whenever|such\s+that)?'
    r'[^.!?]{0,100}?'
    r')'
    r'(?P<env>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Italic/bold group open problem — PRUNED
# PRUNED — FP on 1207.0773v2
# _ITALIC_GROUP_OPEN_PROBLEM_RE = re.compile(...)

# ---------------------------------------------------------------------------
# "So/Thus the problem (that) remains is to find ..."
# ---------------------------------------------------------------------------
_PROBLEM_THAT_REMAINS_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'(?:[A-Z][^.!?]{0,100}?)?'
    r'[Tt]he\s+problem\s+(?:that\s+)?(?:remains?|left)\s+'
    r'(?:is\s+to\s+|is\s+(?:as\s+)?follows?|to\s+(?:find|determine|prove|show|construct|decide))'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# "Is it possible that ..." / "Is it true that ..." open question prose
# ---------------------------------------------------------------------------
_IS_IT_POSSIBLE_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[Ii]s\s+it\s+(?:possible|true|known|decidable|the\s+case)\s+'
    r'(?:that|whether|if)\b'
    r'[^?!]{20,600}?'
    r'[?!]'
    r')',
    re.MULTILINE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# "It was shown/proved in \cite{...} that ..." prose theorem
# ---------------------------------------------------------------------------
_IT_WAS_SHOWN_IN_CITE_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'It\s+was\s+(?:shown|proved|established|demonstrated)\s+in\s+'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{5,500}?'
    r'that\b'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "we know / one can see / we see / we have / it holds that ..." with \cite{}
# ---------------------------------------------------------------------------
_WE_KNOW_CITE_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{0,200}?'
    r'(?:we\s+know|one\s+can\s+(?:see|show)|we\s+(?:see|have|get)|it\s+(?:holds|follows))\s+that\b'
    r'[^.!?]{10,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "This result was extended/generalized ... in \cite{...}" prose theorem
# ---------------------------------------------------------------------------
_RESULT_EXTENDED_CITE_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,100}?'
    r'(?:result|theorem|lemma|proposition|bound|estimate|formula)\b'
    r'[^.!?]{0,200}?'
    r'(?:was|were)\s+(?:extended|generalized|strengthened|improved|sharpened|refined|adapted)\b'
    r'[^.!?]{0,300}?'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{0,200}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Inline open problem: named Problem/Question with citation in prose
# ---------------------------------------------------------------------------
_NAMED_PROBLEM_CITE_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'(?:Problem|Question|Open\s+Problem)\s+\d+(?:\.\d+)*'
    r'[^.!?]{0,100}?'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{0,300}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "X proved/showed in \cite{...} that ..." (author-attributed result)
# ---------------------------------------------------------------------------
_AUTHOR_PROVED_CITE_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,200}?'
    r'(?:proved?|showed?|demonstrated?|established?|derived?|obtained?|verified?)\s+'
    r'(?:in\s+)?\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{0,100}?'
    r'that\b'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# "result/theorem/lemma ... can be stated as ..."
# ---------------------------------------------------------------------------
_CAN_BE_STATED_AS_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{0,200}?'
    r'can\s+be\s+stated\b'
    r'[^.!?]{5,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# \noindent{\bf Title} {\it/\sl body} — bold-headed italic-body theorem block
# ---------------------------------------------------------------------------
_NOINDENT_BF_IT_RE = re.compile(
    r'(?:(?:\\medskip|\\smallskip|\\bigskip)\s*)?'
    r'\\noindent\s*'
    r'\{\\bf\s*(?P<title>[^}]{1,200})\}'
    r'\s*'
    r'\{(?:\\it|\\sl)\s*(?P<body>.*?)\}'
    r'(?=\s*(?:\\medskip|\\smallskip|\\bigskip|\\noindent|\\begin|\n\n|\Z))',
    re.DOTALL,
)

_NOINDENT_BF_IT_KIND_MAP: Dict[str, str] = {
    'lemma': 'lemma',
    'proposition': 'proposition',
    'prop': 'proposition',
    'corollary': 'corollary',
    'cor': 'corollary',
    'definition': 'definition',
    'defn': 'definition',
    'remark': 'remark',
    'conjecture': 'conjecture',
    'conj': 'conjecture',
    'claim': 'claim',
    'problem': 'problem',
    'theorem': 'theorem',
    'thm': 'theorem',
}

def _classify_noindent_bf_it(title: str) -> str:
    title_lower = title.lower()
    for keyword, kind in _NOINDENT_BF_IT_KIND_MAP.items():
        if keyword in title_lower:
            return kind
    return 'theorem'


# ---------------------------------------------------------------------------
# "We claim: $$...$$" or "We claim: \be...\ee" inline claim pattern
# ---------------------------------------------------------------------------
_INLINE_CLAIM_WITH_MATH_RE = re.compile(
    r'(?P<intro>[^\n]*?\bclaim\b[^\n]{0,300}?)'
    r'(?P<math>'
    r'\$\$.*?\$\$'
    r'|\\be(?:\s*\\label\{[^}]*\})?\s*.*?\\ee'
    r'|\\begin\{(?:equation|align|eqnarray)\*?\}.*?\\end\{(?:equation|align|eqnarray)\*?\}'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# "It is well-known / well known / classical / known that ..." prose proposition
# Also catches: "Recall that ...", "We recall that ...",
# "The following [result|lemma|...] holds", "has the following invariances/properties"
# ---------------------------------------------------------------------------
_WELLKNOWN_PROSE_RE = re.compile(
    r'(?:^|(?<=\n\n))'
    r'(?P<body>'
    r'(?:'
    r'It\s+is\s+well[- ]known\s+that'
    r'|It\s+is\s+known\s+that'
    r'|It\s+is\s+classical\s+that'
    r'|It\s+is\s+easy\s+to\s+(?:see|check|verify)\s+that'
    r'|Recall\s+that'
    r'|We\s+(?:first\s+|also\s+)?recall\s+(?:from\s+[^,.]{1,100}\s+)?the\s+following'
    r'|We\s+recall\s+that'
    r'|We\s+(?:first\s+|also\s+)?note\s+the\s+following'
    r'|We\s+(?:first\s+|also\s+)?state\s+the\s+following'
    r'|The\s+following\s+(?:result|lemma|proposition|theorem|estimate|bound|inequality|fact)\s+(?:holds|is\s+(?:known|classical|standard))'
    r'|[^.!?\n]{0,200}has\s+the\s+following\s+(?:invariances|properties|consequences|corollaries|implications)'
    r'|[^.!?\n]{0,200}satisfies\s+the\s+following'
    r'|[^.!?\n]{0,200}the\s+following\s+(?:result|estimate|bound|inequality|property)\s+holds'
    r')'
    r'.+?'
    r')'
    r'(?=\n\n|\\(?:section|subsection|subsubsection|medskip|bigskip|noindent)\b|\Z)',
    re.DOTALL | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Consequence paragraph following equation block — PRUNED
# PRUNED — FP on 1103.5544v1, 1209.2510v1, 1210.4765v1 +2 more | also 12 TP — review before uncommenting
# _CONSEQUENCE_AFTER_EQ_RE = re.compile(...)


# ---------------------------------------------------------------------------
# "it is not clear / it is unclear / ..." open problem — PRUNED
# PRUNED — FP on 1207.0773v2, 1705.02177v2, 1711.00418v8
# _NOT_CLEAR_RE = re.compile(...)


# ---------------------------------------------------------------------------
# "We expect / it is expected / expected to be" conjecture-like prose — PRUNED
# PRUNED — FP on 1103.5544v1, 1207.0773v2 | also 1 TP — review before uncommenting
# _EXPECTED_TO_BE_RE = re.compile(...)


# ---------------------------------------------------------------------------
# Prose open-problem paragraph: contains open-question hedging language
# ---------------------------------------------------------------------------
# PRUNED — FP on 1207.0773v2, 1803.01284v2 | also 1 TP — review before uncommenting
# _OPEN_PROBLEM_PARA_RE = re.compile(
#     r'(?:^|\n\n)'
#     r'(?P<body>[^\n]{20,}?'
#     r'(?:unclear|open\s+question|open\s+problem|remains?\s+to\s+(?:be\s+)?(?:seen|determined|understood)|'
#     r'future\s+work|should\s+be\s+devoted|main\s+concern|promising\s+approach|'
#     r'much\s+effort\s+should|it\s+is\s+(?:still\s+)?unclear|how\s+good\s+solutions?\s+are)'
#     r'[^\n]{0,800}?)'
#     r'(?=\n\n|\\begin\{(?:figure|table|section|appendix)\}|\\section|\\ack|\\appendix|\\bibliography|\Z)',
#     re.DOTALL | re.IGNORECASE,
# )


# ---------------------------------------------------------------------------
# Prose intro + eqnarray: "... offers/yields/gives ... [a set of equations]:"
# ---------------------------------------------------------------------------
_PROSE_OFFERS_EQNARRAY_RE = re.compile(
    r'(?P<intro>'
    r'[^\n]{0,600}?'
    r'(?:offers?|yields?|gives?|provides?|converts?|results?\s+in|leads?\s+to)'
    r'[^\n]{0,300}?'
    r'(?:expression|equations?|conditions?|formulation|form|set\s+of\s+(?:self[- ]consistent\s+)?equations?)'
    r'[^\n]{0,200}?'
    r'(?::\s*\n|\s*\n)'
    r')'
    r'(?P<env>\\begin\{(?P<envname>eqnarray\*?|align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# "it was observed / it was noted that ..." inline proposition/claim
# ---------------------------------------------------------------------------
_IT_WAS_OBSERVED_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'(?:it\s+was\s+(?:observed|noted|remarked)|was\s+(?:observed|noted|remarked))\s+that\b'
    r'[^.!?]{10,500}?'
    r'(?:\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}|\$[^$]+\$)'
    r'[^.!?]{0,200}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# "In \cite{X} it was proved / shown / demonstrated that ..." inline theorem
# ---------------------------------------------------------------------------
_IN_CITE_IT_WAS_PROVED_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,200}?'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{0,200}?'
    r'(?:it\s+was\s+(?:proved?|shown|established|demonstrated)|'
    r'(?:was|were)\s+(?:proved?|shown|established|demonstrated))\s+that\b'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# "remains a difficult problem" open problem prose
# ---------------------------------------------------------------------------
_REMAINS_DIFFICULT_PROBLEM_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{10,500}?'
    r'remains?\s+a\s+(?:difficult|hard|challenging|notoriously\s+hard|notoriously\s+difficult)\s+problem'
    r'[^.!?]{0,300}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# \textit{Short title.} paragraph-style labeled proposition/claim
# Catches paragraphs introduced by \textit{Short phrase.} acting as an
# inline section-label (common in survey/overview papers).
# Requires the label to end in '.' and be followed by substantive text.
# ---------------------------------------------------------------------------
_ITALIC_LABEL_PARA_RE = re.compile(
    r'\\textit\{(?P<label>[^}]{3,80}?\.)\}'
    r'[ \t]+'
    r'(?P<body>[A-Z][^\n]{40,}(?:\n(?![ \t]*\\(?:[a-z]|\n))[^\n]{10,}){0,6})',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: Inline bold/italic theorem-like keyword pattern — PRUNED
# PRUNED — FP on 1103.5544v1, 1207.0773v2, 1209.2510v1 +11 more | also 34 TP — review before uncommenting
# _INLINE_ASSERTIVE_CLAIM_RE = re.compile(...)


# ---------------------------------------------------------------------------
# NEW: Prose-intro optimal control / optimization problem
# Catches: "we pose/formulate/state the following [optimal control] problem:"
# followed by one or more equation environments (equation, align, gather, etc.)
# Also catches "is rewritten in the following ... form:" reformulations.
# ---------------------------------------------------------------------------
_PROSE_PROBLEM_TRIGGER_RE = re.compile(
    r'(?P<intro>'
    r'[^\n]{0,400}?'
    r'(?:'
    r'we\s+(?:pose|formulate|state|consider|propose|study|aim\s+to\s+(?:minimize|maximize|solve))\s+'
    r'(?:the\s+following|an?|our)\s+[^\n]{0,200}?(?:problem|program|formulation|objective)'
    r'|(?:the\s+)?(?:optimal\s+control|optimization|variational|control)\s+problem\b[^\n]{0,200}?'
    r'(?:is\s+(?:given|stated|posed|formulated)|reads|follows)'
    r'|(?:is|are)\s+rewritten?\s+in\s+the\s+following\s+[^\n]{0,100}?(?:form|formulation)'
    r'|(?:is|are)\s+reformulated?\s+(?:as|in)\s+the\s+following'
    r')'
    r'[^\n]{0,200}?'
    r'[:\.]?\s*\n'
    r')'
    r'(?P<body>'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}[\s\S]{5,2000}?'
    r'\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}\s*)+'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Prose claim sentences with discourse-marker openers
# PRUNED — FP on 1103.5544v1, 1111.3171v5, 1207.0773v2 +10 more | also 21 TP — review before uncommenting
# _PROSE_DISCOURSE_CLAIM_RE = re.compile(...)


# ---------------------------------------------------------------------------
# NEW: align/align* block with \min or \max objective preceded by
# optimization-problem-introducing prose.
# ---------------------------------------------------------------------------
_ALIGN_OPT_KEYWORD_BEFORE_RE = re.compile(
    r'(?:'
    r'optimization\s+problem|minimization\s+problem|dual\s+problem'
    r'|primal\s+problem|convex\s+(?:\w+\s+){0,4}problem'
    r'|consensus\s+problem|regularization\s+for\s+the\s+problem'
    r'|(?:can\s+be\s+)?(?:solved?|formulated?)\s+(?:as\s+)?(?:an?\s+)?(?:\w+\s+){0,4}(?:problem|program)'
    r'|(?:equivalently\s+)?rewrite(?:\s+the\s+problem)?'
    r'|(?:we|one)\s+(?:can\s+)?(?:consider|formulate|state|pose)\s+(?:the\s+)?(?:following\s+)?(?:\w+\s+){0,4}problem'
    r'|the\s+(?:following\s+)?(?:\w+\s+){0,4}problem\s+(?:reads|is|becomes|follows)'
    r')',
    re.IGNORECASE | re.DOTALL,
)

# PRUNED — FP on 1712.00232v3 | also 8 TP — review before uncommenting
# _ALIGN_WITH_MINMAX_RE = re.compile(
#     r'\\begin\{(align\*?)\}'
#     r'(?P<body>.*?)'
#     r'\\end\{\1\}',
#     re.DOTALL,
# )

_MINMAX_IN_BODY_RE = re.compile(
    r'\\(?:arg\s*\\)?(?:min|max)(?:_|\b)|\\operatorname\{(?:arg\s*)?(?:min|max)\}',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Paragraph starting with a cross-reference to a theorem/lemma that
# then draws a consequence — corollary-like prose.
# Pattern: "Theorem \ref{...} / Lemma \ref{...} provides/gives/shows/implies ..."
# ---------------------------------------------------------------------------
_THEOREM_REF_CONSEQUENCE_RE = re.compile(
    r'(?:^|\n[ \t]*\n)'
    r'(?P<body>'
    r'(?:Theorem|Lemma|Proposition|Corollary)\s*'
    r'(?:\\ref\{[^}]+\}|\\cref\{[^}]+\}|\d+(?:\.\d+)*)'
    r'\s+(?:provides?|gives?|shows?|implies?|yields?|establishes?|states?)'
    r'[^\n]{30,1000}'
    r')'
    r'(?=\n[ \t]*\n|\\(?:section|subsection|begin|end)|\Z)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: "one can show/verify/check/prove that ..." prose claim sentence
# PRUNED — FP on 1601.01819v1 | also 1 TP — review before uncommenting
# _ONE_CAN_SHOW_RE = re.compile(...)


# ---------------------------------------------------------------------------
# NEW: Prose sentence + \begin{itemize} listing mathematical properties
# ---------------------------------------------------------------------------
_PROSE_WITH_ITEMIZE_PROPS_RE = re.compile(
    r'(?:^|\n[ \t]*\n|\n)'
    r'(?P<intro>'
    r'[A-Z][^\n]{10,400}?'
    r'(?:'
    r'[Oo]ne\s+can\s+(?:verify|check|see)\s+that\b[^\n]{0,200}?'
    r'|(?:has|have|satisfies?|fulfills?)\s+the\s+following\s+(?:properties|conditions|attributes)\b[^\n]{0,200}?'
    r'|with\s+the\s+following\s+(?:properties|conditions|features)\b[^\n]{0,200}?'
    r')'
    r'[:\.]?\s*\n'
    r')'
    r'(?P<env>\\begin\{itemize\}'
    r'(?P<body>.*?)'
    r'\\end\{itemize\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Prose sentence immediately after \end{definition} or \end{remark}
# that draws a consequence ("Particularly, ...", "In particular, ...",
# "As a consequence, ...", "It follows that ...") with math content.
# ---------------------------------------------------------------------------
_POST_DEFINITION_CONSEQUENCE_RE = re.compile(
    r'\\end\{(?:definition|remark|notation)\}'
    r'\s*'
    r'(?P<body>'
    r'(?:Particularly|In\s+particular|As\s+a\s+(?:direct\s+)?consequence|'
    r'It\s+follows\s+(?:from\s+[^,]{1,60})?,|Note\s+that|'
    r'Observe\s+that|As\s+a\s+result,?)'
    r'[^.!?\n]{10,600}?'
    r'\$[^$]{2,}?\$'
    r'[^.!?]{0,400}?'
    r'[.!?]'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "it is known that ..." inline theorem-like statements
# Catches sentences of the form "From ... it is known that ..." with math or cite.
# Complements _WELLKNOWN_PROSE_RE (which is anchored at \n\n) for mid-paragraph use.
# ---------------------------------------------------------------------------
_IT_IS_KNOWN_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'it\s+is\s+known\s+that\b'
    r'[^.!?]{10,600}?'
    r'(?:\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}|\$[^$]{2,}?\$)'
    r'[^.!?]{0,200}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "Recall that ..." proposition-like statements (sentence-initial)
# Complements _WELLKNOWN_PROSE_RE for cases not anchored at paragraph boundary.
# Requires math or citation to reduce FP.
# ---------------------------------------------------------------------------
# PRUNED — FP on 1102.4533v1, 1705.02177v2, 1804.04279v1 | also 2 TP — review before uncommenting
# _RECALL_THAT_RE = re.compile(
#     r'(?:^|(?<=[.!?\n]))\s*'
#     r'(?P<body>'
#     r'Recall\s+that\b'
#     r'[^.!?]{10,500}?'
#     r'(?:\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}|\$[^$]{2,}?\$)'
#     r'[^.!?]{0,200}?'
#     r'[.!?]'
#     r')',
#     re.MULTILINE | re.DOTALL,
# )


# ---------------------------------------------------------------------------
# NEW: "In particular, ..." corollary-like consequence immediately after
# \end{theorem} / \end{lemma} / \end{proposition}
# ---------------------------------------------------------------------------
_IN_PARTICULAR_AFTER_THM_RE = re.compile(
    r'\\end\{(?:theorem|thm|Theorem|lemma|lem|prop|proposition|corollary|cor)\}'
    r'[^\n]{0,200}\n+'
    r'(?P<body>'
    r'In\s+particular[,.]'
    r'[^.!?]{20,500}?'
    r'(?:\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}|\$[^$]{2,}?\$)'
    r'[^.!?]{0,200}?'
    r'[.!?]'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "observe that ..." claim-like statements — PRUNED
# PRUNED — FP on 1209.2510v1, 1210.4765v1, 1409.6258v2 +1 more | also 6 TP — review before uncommenting
# _OBSERVE_THAT_RE = re.compile(...)


# ---------------------------------------------------------------------------
# NEW: "It is shown in \cite{...} that ..." proposition
# Extends _INLINE_SHOWN_THAT_RE to catch "It is shown in \cite{X} that ..."
# (where the \cite precedes "that").
# ---------------------------------------------------------------------------
_IT_IS_SHOWN_IN_CITE_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,100}?'
    r'it\s+is\s+shown\s+in\s+'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{0,200}?'
    r'that\b'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Sentence after \end{lemma/theorem/...} starting with "According to
# Lemma/Theorem \ref{...}" — corollary-like prose consequence
# ---------------------------------------------------------------------------
_POST_ENV_ACCORDING_TO_RE = re.compile(
    r'\\end\{(?:lemma|theorem|proposition|corollary|Lemma|Theorem|Proposition|Corollary)\}'
    r'\s*'
    r'(?P<body>'
    r'(?:According\s+to|By|From|Using)\s+'
    r'(?:Lemma|Theorem|Proposition|Corollary|Claim)\s*'
    r'(?:~?\\ref\{[^}]+\}|~?\\cref\{[^}]+\}|\d+(?:\.\d+)*)'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: \begin{itemize} items that are individually theorem/claim-like
# (items containing math and appearing after a theorem-introducing sentence)
# ---------------------------------------------------------------------------
_ITEMIZE_CLAIM_ITEM_RE = re.compile(
    r'\\item\s+'
    r'(?P<body>'
    r'(?:(?!\\item|\\end\{itemize\}).){30,800}?'
    r'\$[^$]{2,}?\$'
    r'(?:(?!\\item|\\end\{itemize\}).){0,400}?'
    r')'
    r'(?=\\item|\\end\{itemize\})',
    re.DOTALL,
)

# Trigger: itemize block preceded by theorem-introducing language
_ITEMIZE_THM_INTRO_RE = re.compile(
    r'(?P<intro>'
    r'[^\n]{10,400}?'
    r'(?:'
    r'(?:we\s+(?:begin|start)\s+with\s+the\s+following\s+(?:observations?|properties|facts))'
    r'|(?:the\s+following\s+(?:observations?|properties|facts|conditions)\s+(?:hold|are\s+(?:true|satisfied)))'
    r'|(?:We\s+(?:make|have)\s+the\s+following\s+(?:key\s+)?(?:observations?|remarks?|claims?))'
    r'|(?:can\s+be\s+easily\s+(?:verified|checked|seen)\s+that)'
    r')'
    r'[^\n]{0,200}\n'
    r')'
    r'(?P<env>\\begin\{itemize\}'
    r'(?P<body>.*?)'
    r'\\end\{itemize\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "No X is known / No better bound is known" open problem sentences
# ---------------------------------------------------------------------------
_NO_X_IS_KNOWN_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'No\s+(?:\w+\s+){1,8}'
    r'(?:is|are)\s+known\b'
    r'[^.!?]{0,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: "only able to analyze / only able to prove" open-problem-like limitation — PRUNED
# PRUNED — FP on 1612.05419v3 | also 1 TP — review before uncommenting
# _ONLY_ABLE_TO_RE = re.compile(...)


# ---------------------------------------------------------------------------
# NEW: "An easy/elementary computation/verification shows that ..." + equation
# ---------------------------------------------------------------------------
_EASY_COMPUTATION_SHOWS_RE = re.compile(
    r'(?:^|(?<=[.!?\n])|\n)\s*'
    r'(?P<intro>'
    r'(?:An?\s+)?(?:easy|elementary|direct|simple|straightforward|routine)\s+'
    r'(?:computation|verification|calculation|check|argument|inspection)\s+'
    r'(?:shows?|reveals?|yields?|gives?|demonstrates?)\s+(?:that\b)?'
    r'[^\n]{0,300}?'
    r')'
    r'(?P<env>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "Recall that the group/structure ... acts/has ..." + itemize list
# ---------------------------------------------------------------------------
_RECALL_WITH_ITEMIZE_RE = re.compile(
    r'(?:^|\n[ \t]*\n|\n)'
    r'(?P<intro>'
    r'(?:Recall|Note)\s+that\s+'
    r'[^\n]{20,400}?'
    r'[:\.]?\s*\n'
    r')'
    r'(?P<env>\\begin\{(?:itemize|enumerate)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?:itemize|enumerate)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "Since ... hence by [theorem/result] ... we obtain ..." consequence prose
# ---------------------------------------------------------------------------
_HENCE_BY_THEOREM_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'(?:hence|therefore|thus|so)\s+by\s+'
    r'(?:(?:Lemma|Theorem|Proposition|Corollary|Claim)\s*'
    r'(?:~?\\ref\{[^}]+\}|~?\\cref\{[^}]+\}|\d+(?:\.\d+)*)'
    r'|\\cite(?:\s*\[[^\]]*\])?\{[^}]+\})'
    r'[^.!?]{5,400}?'
    r'(?:we\s+(?:obtain|get|conclude|have|find)|it\s+follows)'
    r'[^.!?]{5,400}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "We hope that ..." / "a new idea is needed" open-problem prose
# ---------------------------------------------------------------------------
_WE_HOPE_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'(?:'
    r'[Ww]e\s+hope\s+that\b'
    r'|[Aa]\s+new\s+(?:idea|approach|technique|method)\s+is\s+needed\b'
    r'|[Ii]t\s+remains?\s+(?:an?\s+)?(?:open|unsolved|outstanding)\s+(?:problem|question|challenge)'
    r')'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Prose claim: "Then/Consequently ... rejects/controls/level alpha" — statistical decision
# ---------------------------------------------------------------------------
_STATISTICAL_DECISION_CLAIM_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'(?:Then|Consequently|Therefore|Hence)[^.!?]{0,400}?'
    r'(?:'
    r'rejects?\s+the\s+(?:null\s+)?hypothesis'
    r'|controls?\s+the\s+(?:overall\s+)?type\s+(?:one|I|1)\s+error'
    r'|(?:consistent\s+and\s+)?asymptotic(?:ally)?\s+level\s+\$?[^$]{0,30}\$?\s*test'
    r'|yields?\s+a\s+(?:consistent|valid|level)\s+[^.!?]{0,60}test'
    r')'
    r'[^.!?]{0,300}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Hypothesis testing problem: prose framing H_0/H_1 inside equation block
# ---------------------------------------------------------------------------
_HYPOTHESIS_EQ_BODY_RE = re.compile(
    r'H\s*[_^]\s*[{(]?\s*(?:0|1)',
    re.IGNORECASE,
)

_HYPOTHESIS_TESTING_PROBLEM_RE = re.compile(
    r'(?P<intro>'
    r'[^\n]{0,500}?'
    r'(?:'
    r'(?:hypothesis|hypotheses)\s+(?:testing\s+)?(?:problem|framework|setup)'
    r'|testing\s+(?:the\s+)?(?:null\s+)?hypothes(?:is|es)'
    r'|(?:test|compare|evaluate)\s+[^\n]{0,200}?(?:hypothesis|hypotheses)'
    r'|(?:this\s+(?:is\s+)?framed\s+as|leads?\s+to\s+(?:the\s+)?(?:testing|hypothesis))'
    r'|(?:following\s+(?:relevant\s+)?hypothesis)'
    r')'
    r'[^\n]{0,300}?'
    r'\n?'
    r')'
    r'(?P<env>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# "topic for future research" / "X is a topic for future research" open problem
# ---------------------------------------------------------------------------
_TOPIC_FOR_FUTURE_RESEARCH_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{10,600}?'
    r'(?:'
    r'(?:a\s+)?topic\s+for\s+future\s+(?:research|work|investigation|study)'
    r'|(?:left|deferred|reserved)\s+for\s+future\s+(?:research|work|investigation)'
    r'|future\s+(?:research|work|investigation)\s+(?:will|could|should|may|might)'
    r'|direction\s+(?:of|for)\s+future\s+(?:research|work)'
    r'|(?:subject|topic)\s+of\s+(?:ongoing|future|further)\s+(?:research|work|investigation)'
    r')'
    r'[^.!?]{0,300}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Penalized/regularized regression criterion — prose + equation
# ---------------------------------------------------------------------------
_PENALIZED_CRITERION_RE = re.compile(
    r'(?P<intro>'
    r'[^\n]{0,400}?'
    r'(?:'
    r'(?:minimize|maximiz|optim(?:iz|is))\s+(?:the\s+)?(?:following\s+)?'
    r'(?:penalized|regularized|weighted|empirical|sample|loss|objective|criterion|risk)\b'
    r'|(?:following\s+)?(?:penalized|regularized)\s+(?:regression\s+)?(?:criterion|objective|loss)\b'
    r'|(?:criterion|objective|loss\s+function)\s+(?:over|of|with\s+respect\s+to)\b'
    r')'
    r'[^\n]{0,300}?'
    r'[:\.]?\s*\n'
    r')'
    r'(?P<env>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Prose + equation/align claims introduced by common mathematical
# transitional phrases.
# ---------------------------------------------------------------------------
_PROSE_EQUATION_CLAIM_RE = re.compile(
    r'(?:(?<=\n)|(?<=\.))\s*'
    r'(?P<lead>'
    r'(?:'
    r'It\s+then\s+follows\s+that'
    r'|Note\s+that'
    r'|Observe\s+that'
    r'|We\s+(?:also\s+)?recall\s+(?:that|the)'
    r'|We\s+have'
    r'|We\s+obtain'
    r'|Under\s+the\s+same\s+(?:assumptions?|conditions?|hypotheses?)'
    r'|Using\s+(?:\\eqref\{[^}]*\}|\\ref\{[^}]*\}|\([^)]{1,40}\))[^.\n]{0,300}?we\s+(?:obtain|get|have|find)'
    r'|The\s+following\s+results?\s+can\s+be\s+(?:checked|verified|computed?)'
    r'|[A-Z][^.\n]{0,400}?(?:we\s+(?:obtain|get|have|find|derive)|it\s+follows\s+that)'
    r')'
    r'[^.\n]{0,400}?'
    r')'
    r'(?P<eq>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "We recall [cite] \begin{equation}..." lemma/proposition
# ---------------------------------------------------------------------------
_RECALL_CITE_EQUATION_RE = re.compile(
    r'(?:(?<=\n\n)|(?<=\n))\s*'
    r'(?P<lead>'
    r'(?:We\s+(?:also\s+|further\s+|first\s+)?recall|We\s+will\s+(?:also\s+)?need|'
    r'We\s+(?:also\s+)?use|We\s+state\s+for\s+reference)'
    r'[^\n]{0,400}?'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^\n]{0,300}?'
    r'\n?'
    r')'
    r'(?P<eq>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Prose + equation: "We have [cite] \begin{equation}..."
# ---------------------------------------------------------------------------
_WE_HAVE_CITE_EQUATION_RE = re.compile(
    r'(?:(?<=\n\n)|(?<=\n)|\.\s+)'
    r'(?P<lead>'
    r'(?:We\s+have|Moreover\s+we\s+have|Furthermore\s+we\s+have|'
    r'We\s+(?:also\s+)?have|We\s+(?:also\s+)?get|We\s+(?:also\s+)?obtain)'
    r'[^\n]{0,300}?'
    r'(?:\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}|\\(?:eqref|ref)\{[^}]+\})'
    r'[^\n]{0,200}?\n?'
    r')'
    r'(?P<eq>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "By an inverse estimate / by an argument / by the trace estimate
# \begin{equation}...\end{equation}" claim sentences.
# ---------------------------------------------------------------------------
_BY_ESTIMATE_EQUATION_RE = re.compile(
    r'(?:(?<=\n)|(?<=\.))\s*'
    r'(?P<lead>'
    r'(?:By|From|Using|Applying)\s+'
    r'(?:'
    r'(?:an?\s+)?(?:inverse|trace|Sobolev|Poincar[eé]|interpolation|energy|coercivity|triangle|Cauchy|Young|H[oö]lder)\s+'
    r'(?:estimate|inequality|lemma|bound|argument|identity)'
    r'|(?:\\eqref\{[^}]+\}|\\ref\{[^}]+\}|\\cite(?:\s*\[[^\]]*\])?\{[^}]+\})'
    r')'
    r'[^\n]{0,400}?'
    r')'
    r'(?P<eq>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "It follows that ..." / "It follows from the definition ..." + equation
# ---------------------------------------------------------------------------
_IT_FOLLOWS_EQUATION_RE = re.compile(
    r'(?:(?<=\n)|(?<=\.\s))\s*'
    r'(?P<lead>'
    r'It\s+follows\s+(?:from\s+[^.\n]{0,200}?\s+)?that\b'
    r'[^\n]{0,400}?'
    r')'
    r'(?P<eq>'
    r'(?:'
    r'\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?|split\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}'
    r'|\$\$(?P<body2>.*?)\$\$'
    r'|\\a\{(?P<body3>[^}]{5,800})\}'
    r'|\\an\{(?P<body4>[^}]{5,800})\}'
    r'|\\e\{(?P<body5>[^}]{5,800})\}'
    r')'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "It is straightforward to see/check/verify that ..." + equation
# ---------------------------------------------------------------------------
_STRAIGHTFORWARD_EQUATION_RE = re.compile(
    r'(?:(?<=\n)|(?<=\.\s))\s*'
    r'(?P<lead>'
    r'It\s+is\s+(?:straightforward|easy|immediate|clear)\s+'
    r'to\s+(?:see|check|verify|show|compute)\s+that\b'
    r'[^\n]{0,400}?'
    r')'
    r'(?P<eq>'
    r'(?:'
    r'\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}'
    r'|\$\$(?P<body2>.*?)\$\$'
    r')'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "The dimension/cardinality/rank/size of X is ..." + display math
# ---------------------------------------------------------------------------
_DIMENSION_IS_EQUATION_RE = re.compile(
    r'(?:(?<=\n)|(?<=\.\s))\s*'
    r'(?P<lead>'
    r'(?:The\s+)?(?:dimension|rank|cardinality|size|order|degree|number\s+of\s+\w+)\s+'
    r'of\s+[^\n]{5,200}?\s+(?:is|equals?|reads?)\b'
    r'[^\n]{0,200}?'
    r')'
    r'(?P<eq>'
    r'(?:'
    r'\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}'
    r'|\$\$(?P<body2>.*?)\$\$'
    r')'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "Find X such that ..." mathematical problem statement in running prose
# ---------------------------------------------------------------------------
_FIND_SUCH_THAT_PROBLEM_RE = re.compile(
    r'(?:(?<=\n)|(?<=:\s))\s*'
    r'(?P<lead>'
    r'(?:[^\n]{0,200}?reads?[:\s]{1,10})?'
    r'[Ff]ind\s+'
    r'[^\n]{5,400}?'
    r'such\s+that\b'
    r'[^\n]{0,200}?'
    r')'
    r'(?P<eq>'
    r'(?:'
    r'\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}'
    r'|\\[a-z]+\{(?P<body2>[\s\S]{10,1500}?(?:for\s+all|for\s+any)[\s\S]{5,500}?)\}'
    r'|\$\$(?P<body3>.*?)\$\$'
    r')'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Prose paragraph + display math introduced by "In particular," when
# the paragraph contains display math ($$...$$) and is an informal claim.
# ---------------------------------------------------------------------------
_IN_PARTICULAR_WITH_MATH_RE = re.compile(
    r'(?:^|\n{2,})'
    r'(?P<body>'
    r'In\s+particular[,.]\s+'
    r'[^\n]{10,800}?'
    r'(?:'
    r'\$\$[\s\S]{5,1000}?\$\$'
    r'|\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}[\s\S]{5,1000}?'
    r'\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}'
    r')'
    r'[\s\S]{0,600}?'
    r')'
    r'(?=\n{2,}|\\(?:section|subsection|begin|end|paragraph)|\Z)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Prose "X shows/showed that ..." + display math (author-result pattern)
# ---------------------------------------------------------------------------
_AUTHOR_SHOWS_WITH_MATH_RE = re.compile(
    r'(?:^|\n{2,}|\n)'
    r'(?P<body>'
    r'[A-Z][^.!?\n]{0,300}?'
    r'(?:shows?|showed?|proves?|proved?|demonstrates?|demonstrated?|established?|establishes?)\s+'
    r'(?:that\b|the\b)[^.!?\n]{0,400}?'
    r'(?:'
    r'\$\$[\s\S]{5,1000}?\$\$'
    r'|\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}[\s\S]{5,1000}?'
    r'\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}'
    r')'
    r'[\s\S]{0,400}?'
    r')'
    r'(?=\n{2,}|\\(?:section|subsection|begin|end|paragraph)|\Z)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: Prose rhetorical question introducing a problem:
# "one can clearly ask: what is X?" — paragraph with explicit '?' and trigger phrase
# ---------------------------------------------------------------------------
_ONE_CAN_ASK_PROBLEM_RE = re.compile(
    r'(?:^|\n{2,}|\n)'
    r'(?P<body>'
    r'[^\n]{0,400}?'
    r'(?:'
    r'one\s+can\s+(?:clearly\s+|naturally\s+|reasonably\s+)?ask\b'
    r'|[Tt]he\s+(?:natural\s+|key\s+|central\s+|main\s+|open\s+)?question\s+(?:is|becomes|then\s+is)\b'
    r'|[Tt]he\s+(?:key\s+|central\s+|main\s+|natural\s+)?problem\s+(?:is|becomes|then\s+is)\b'
    r'|[Ww]e\s+(?:therefore\s+|now\s+|can\s+|may\s+)?(?:ask|pose\s+the\s+question)\b'
    r'|[Tt]his\s+(?:raises|leads\s+to)\s+the\s+question\b'
    r')'
    r'[^?!]{0,800}?'
    r'\?'
    r'[\s\S]{0,400}?'
    r')'
    r'(?=\n{2,}|\\(?:section|subsection|begin|end|paragraph)|\Z)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "it will follow from this / it follows from this" + display math
# ---------------------------------------------------------------------------
_IT_WILL_FOLLOW_FROM_THIS_RE = re.compile(
    r'(?:^|\n{2,}|\n|(?<=[.!?]))\s*'
    r'(?P<body>'
    r'[^\n]{0,200}?'
    r'[Ii]t\s+(?:will\s+)?follows?\s+from\s+this\b'
    r'[^.!?]{0,600}?'
    r'(?:'
    r'\$\$[\s\S]{5,1000}?\$\$'
    r'|\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}[\s\S]{5,1000}?'
    r'\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}'
    r'|,\s+(?:since|because|as)\s+[^.!?]{10,400}?[.!?]'
    r')'
    r'[\s\S]{0,400}?'
    r')'
    r'(?=\n{2,}|\\(?:section|subsection|begin|end|paragraph)|\Z)',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# "We conjecture / we expect / we anticipate ..." — inline conjecture prose
# Catches sentences like "We conjecture a crossover transition ..."
# and "We anticipate that the solution ... would be of value ..."
# ---------------------------------------------------------------------------
_WE_CONJECTURE_INLINE_KIND_MAP: Dict[str, str] = {
    'conjecture': 'conjecture',
    'expect': 'conjecture',
    'anticipate': 'conjecture',
    'believe': 'conjecture',
    'predict': 'conjecture',
}


# ---------------------------------------------------------------------------
# "In particular ... should also follow ..." conjecture-like inline prose
# Catches: "In particular the statistics ... should also follow this ..."
# Requires "In particular" + "should" within same sentence.
# ---------------------------------------------------------------------------
_IN_PARTICULAR_SHOULD_RE = re.compile(
    r'(?:^|\n{2,}|\n)'
    r'(?P<body>'
    r'In\s+particular\b'
    r'[^.!?]{10,600}?'
    r'\bshould\b'
    r'[^.!?]{5,400}?'
    r'[.!?]'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Free-prose claim paragraphs starting with logical/mathematical
# connective phrases (between theorem environments in running text).
# ---------------------------------------------------------------------------
_IMPLICIT_CLAIM_LEAD_RE = re.compile(
    r'(?:^|\n{2,})'
    r'(?P<body>'
    r'(?:'
    r'(?:Hence|Thus|Therefore|Consequently|Altogether)\b'
    r'|By\s+construction\b'
    r'|Since\s+(?:formula|equation|the\s+(?:strong|weak)|this\s+prescription)'
    r'|From\s+the\s+(?:identity|formula|expression|last|above|previous)'
    r'|It\s+is\s+(?:clear|obvious|readily\s+checked)\s+that\b'
    r'|We\s+have\s+(?:shown|proved|established|demonstrated)\s+that\b'
    r'|Altogether\s+we\s+have\b'
    r'|Now\s+we\s+(?:may|can|want\s+to)\b'
    r'|We\s+(?:now\s+)?(?:argue|conclude|observe)\s+that\b'
    r')'
    r'[^\n]{40,}'           # at least 40 chars on this paragraph
    r'(?:\n(?!\n)[^\n]+)*'  # allow continuation lines (no blank line)
    r')'
    r'(?=\n{2,}|\\(?:begin|end|section|subsection|paragraph)|\Z)',
    re.DOTALL | re.MULTILINE,
)

# Require math or citation content to accept implicit claim paragraphs
_IMPLICIT_CLAIM_MATH_OR_CITE_RE = re.compile(
    r'\$[^$]{2,}?\$'
    r'|\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'|\\ref\{[^}]+\}'
    r'|\\eqref\{[^}]+\}'
    r'|\\begin\{(?:equation|align|eqnarray|gather)\*?\}'
    r'|\$\$',
    re.DOTALL,
)

def _classify_implicit_para(body: str) -> str:
    """Heuristically assign a structure_type to a free-prose paragraph."""
    lower = body.lower()
    if re.search(
        r'\bopen\s+(?:problem|question)\b'
        r'|\bit\s+is\s+natural\s+to\s+investigate\b'
        r'|\bremains\s+open\b'
        r'|\bopen\s+question\b',
        lower
    ):
        return 'open_problem'
    if re.search(r'\bproblem\b', lower):
        return 'problem'
    if re.search(r'\bconjecture\b', lower):
        return 'conjecture'
    return 'claim'


# ---------------------------------------------------------------------------
# NEW: \subsection{...} heading followed by prose body — claim blocks
# ---------------------------------------------------------------------------
_SUBSECTION_CLAIM_RE = re.compile(
    r'\\subsection\*?\{(?P<title>[^}]{1,200})\}'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section\*?\{|\\appendix|\Z)',
    re.DOTALL,
)

# Require performance/comparison language to fire on subsection bodies
_SUBSECTION_CLAIM_TRIGGER_RE = re.compile(
    r'(?:'
    r'outperform|leads?|achieves?|higher\s+than|lower\s+than|better\s+than|'
    r'accuracy|precision|recall|sensitivity|specificity|AUC|F1|'
    r'our\s+(?:model|method|approach|algorithm)\s+(?:leads?|achieves?|outperforms?)|'
    r'compared\s+(?:with|to)|improvement|baseline|state[- ]of[- ]the[- ]art'
    r')',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: {\bfseries <Title>} inline bold heading followed by prose body — claim blocks
# PRUNED — FP on 1804.04206v1 | also 3 TP — review before uncommenting
# _BFSERIES_CLAIM_RE = re.compile(
#     r'\{\\bfseries\s+(?P<title>[^}]{1,200})\}'
#     r'[ \t]*'
#     r'(?P<body>(?:(?!\{\\bfseries|\\(?:sub)*section\*?\{|\\end\{).){40,3000})',
#     re.DOTALL,
# )

# Require substantive content (not just whitespace/punctuation)
_BFSERIES_BODY_MIN_WORDS_RE = re.compile(r'\b\w{4,}\b.*\b\w{4,}\b', re.DOTALL)


# ---------------------------------------------------------------------------
# NEW: \noindent {\bf Label}: body — bold-labeled free-text problem/task block
# Catches task descriptions written as free paragraphs with a bold prefix label,
# e.g. \noindent {\bf T1}: ... or \noindent \textbf{Task 1}: ...
# ---------------------------------------------------------------------------
# PRUNED — FP on 1103.5544v1, 1209.2510v1, 1301.1423v2 +7 more | also 11 TP — review before uncommenting
# _NOINDENT_BOLD_LABEL_RE = re.compile(
#     r'\\noindent\s*'
#     r'(?:'
#     r'\{\\bf\s+(?P<label1>[^}]{1,100})\}'
#     r'|\\textbf\{(?P<label2>[^}]{1,100})\}'
#     r')'
#     r'[:\s]*'
#     r'(?P<body>(?:(?!\\bigskip|\\medskip|\\noindent|\\begin\{|\\section|\\subsection).){30,2000})',
#     re.DOTALL,
# )


# ---------------------------------------------------------------------------
# NEW: Open-question enumerate items preceded by an open-question trigger
# Catches \item entries inside \begin{enumerate}...\end{enumerate} that follow
# a sentence containing open-question/future-work trigger language.
# ---------------------------------------------------------------------------
_OPEN_QUESTION_ENUM_BLOCK_RE = re.compile(
    r'(?:'
    r'open\s+question|open\s+problem|future\s+direction|future\s+work|'
    r'interesting\s+open|open\s+challenge|unsolved|remaining\s+question|'
    r'open\s+problems?\s+related|open\s+questions?\s+related|'
    r'some\s+interesting\s+open|following\s+open'
    r')'
    r'[^\\]{0,500}?'
    r'\\begin\{enumerate\}'
    r'(?P<enum_body>.*?)'
    r'\\end\{enumerate\}',
    re.DOTALL | re.IGNORECASE,
)

_ENUM_ITEM_RE = re.compile(
    r'\\item\s+'
    r'(?P<body>.*?)'
    r'(?=\\item|\\end\{enumerate\}|\Z)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Prose bold-labeled claim: {\bf Claim N} or \textbf{Claim N} in free prose
# Catches inline bold-labeled claim blocks not inside \begin{claim}...\end{claim}
# ---------------------------------------------------------------------------
_PROSE_BOLD_CLAIM_RE = re.compile(
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<kind>Claim|Theorem|Lemma|Proposition|Corollary|Conjecture|Problem)'
    r'(?:\s+\d+(?:\.\d+)*)?\}?\s*'
    r'(?:\\\\[ \t]*\n?)?'
    r'(?P<body>'
    r'(?:(?!\\begin\{proof\}|\\begin\{(?:theorem|lemma|proposition|corollary|claim|conjecture|problem)\}|'
    r'\\(?:sub)*section|\\end\{document\}).){30,2000}'
    r')',
    re.DOTALL,
)

_PROSE_BOLD_CLAIM_KIND_MAP: Dict[str, str] = {
    'claim': 'claim',
    'theorem': 'theorem',
    'lemma': 'lemma',
    'proposition': 'proposition',
    'corollary': 'corollary',
    'conjecture': 'conjecture',
    'problem': 'problem',
}


# ---------------------------------------------------------------------------
# Open problem keyword detector for remark/prose bodies
# ---------------------------------------------------------------------------
_OPEN_PROBLEM_KEYWORDS_RE = re.compile(
    r'\b(?:'
    r'open\s*(?:problem|question)?'
    r'|one\s+(?:may|could|can)\s+(?:ask|wonder)'
    r'|it\s+(?:is|seems)\s+(?:unclear|unknown|open|likely)'
    r'|we\s+do\s+not\s+(?:know|attack|address)'
    r'|remains?\s+open'
    r'|it\s+is\s+(?:an?\s+)?open'
    r'|unclear\s+to\s+us'
    r'|it\s+is\s+unclear'
    r')\b',
    re.IGNORECASE,
)

# Open-problem item detector for list items inside remark/etc. bodies
_OPEN_PROBLEM_ITEM_RE = re.compile(
    r'\\item\s+'
    r'(?P<body>'
    r'(?:(?!\\item|\\end\{).)*'
    r'(?:we\s+do\s+not|one\s+(?:may|could)|it\s+is\s+(?:unclear|unknown)|'
    r'open\s+(?:problem|question)|we\s+do\s+not\s+attack)'
    r'(?:(?!\\item|\\end\{).)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Remark environment body — scan for open-problem content
# ---------------------------------------------------------------------------
_REMARK_ENV_RE = re.compile(
    r'\\begin\{(?P<env>remark|Remark|rem)\*?}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\*?\}',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Inter-environment prose gap detector for open-problem content
# Catches free prose between \end{...} and \begin{...} or section boundaries
# that contains open-problem language.
# ---------------------------------------------------------------------------
_INTER_ENV_PROSE_RE = re.compile(
    r'\\end\{[^}]+\}'
    r'\s*'
    r'(?P<body>'
    r'(?:(?!\\begin\{|\\(?:sub)*section).){40,2000}?'
    r')'
    r'\s*'
    r'(?=\\begin\{|\\(?:sub)*section|\Z)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: "Consider [the/a] [differential/integral/...] equation..." + equation
# Catches problem statements introduced by "Consider the ... equation:"
# followed by a \begin{equation}...\end{equation} block.
# ---------------------------------------------------------------------------
_CONSIDER_EQUATION_PROBLEM_RE = re.compile(
    r'(?:^|\n[ \t]*\n|\n)'
    r'(?P<intro>'
    r'[^\n]{0,200}?'
    r'[Cc]onsider\s+(?:the\s+|a\s+|an?\s+)?'
    r'(?:\w+\s+){0,6}'
    r'(?:equation|system|problem|model|formulation|ODE|PDE|SDE|IVP|BVP)\b'
    r'[^\n]{0,300}?'
    r'[:\.]?\s*\n'
    r')'
    r'(?P<env>\\begin\{(?P<envname>equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\})',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Enumerate block items under (sub)section heading containing math —
# proposition-like list items.
# Catches \item entries inside enumerate under a section/subsection heading
# when they contain inline math ($...$).
# ---------------------------------------------------------------------------
_SECTION_ENUMERATE_ITEM_RE = re.compile(
    r'\\(?:sub)*section\*?\{(?P<title>[^}]{1,200})\}'
    r'(?:[^\n]{0,300}\n){0,5}'         # optional prose lines
    r'\\begin\{enumerate\}'
    r'(?P<enum_body>.*?)'
    r'\\end\{enumerate\}',
    re.DOTALL | re.IGNORECASE,
)

_ENUM_MATH_ITEM_RE = re.compile(
    r'\\item\s+'
    r'(?P<body>'
    r'(?:(?!\\item|\\end\{enumerate\}|\\begin\{enumerate\}).){10,600}?'
    r'\$[^$]{2,}?\$'
    r'(?:(?!\\item|\\end\{enumerate\}|\\begin\{enumerate\}).){0,400}?'
    r')'
    r'(?=\\item|\\end\{enumerate\}|\Z)',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: "authors raised a question whether ..." open problem prose
# Catches: "Then authors raised a question whether ...",
#          "This raises the question of whether ...", etc.
# ---------------------------------------------------------------------------
_RAISED_QUESTION_WHETHER_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'[A-Z][^.!?]{0,300}?'
    r'(?:'
    r'raised?\s+(?:a\s+|the\s+)?question\s+(?:of\s+)?(?:whether|if|about)\b'
    r'|raises?\s+(?:a\s+|the\s+)?question\s+(?:of\s+)?(?:whether|if|about)\b'
    r'|asked?\s+(?:whether|if)\b'
    r'|posed?\s+(?:the\s+)?question\s+(?:of\s+)?(?:whether|if)\b'
    r')'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Inline claim-like paragraphs starting with structural keywords
# containing math (Note that, Also note that, By ..., Under ..., etc.)
# Catches patterns like:
#   "Note that if A is H-supersmooth ... then A is H-smooth ..."
#   "Also note that the estimate ... can be replaced by \begin{align}..."
#   "By a direct calculation, ... Hence ... is the adjoint of ..."
#   "By Proposition ... and this lemma, if A is ... then ... satisfies ..."
# ---------------------------------------------------------------------------
# PRUNED — FP on 1102.4533v1, 1103.5544v1, 1207.0773v2 +12 more | also 16 TP — review before uncommenting
# _INLINE_STRUCTURAL_CLAIM_RE = re.compile(
#     r'(?:^|\n{2,}|\n)'
#     r'(?P<body>'
#     r'(?:'
#     r'(?:Also\s+)?[Nn]ote\s+that\b'
#     r'|[Aa]lso\s+note\s+that\b'
#     r'|[Oo]bserve\s+that\b'
#     r'|[Uu]nder\s+(?:Assumption|assumption|Condition|condition|the\s+hypothesis|the\s+assumption)\b'
#     r'|[Bb]y\s+(?:a\s+)?(?:direct|similar|analogous|straightforward|elementary)\s+'
#     r'(?:calculation|computation|argument|inspection|verification)\b'
#     r'|[Bb]y\s+(?:Proposition|Lemma|Theorem|Corollary)\s*(?:\\ref\{[^}]+\}|\d+(?:\.\d+)*)'
#     r')'
#     r'[^\n]{20,}'
#     r'(?:\n(?!\n)[^\n]+){0,8}'
#     r')'
#     r'(?=\n{2,}|\\(?:begin|end|section|subsection|paragraph)|\Z)',
#     re.DOTALL | re.MULTILINE,
# )

# Require math or citation to accept inline structural claims
_INLINE_STRUCTURAL_CLAIM_MATH_RE = re.compile(
    r'\$[^$]{2,}?\$'
    r'|\\begin\{(?:equation|align|eqnarray|gather)\*?\}'
    r'|\$\$'
    r'|\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'|\\ref\{[^}]+\}'
    r'|\\eqref\{[^}]+\}',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: "We claim that ..." inline claim pattern (general structural marker)
# Catches: "We claim that if X, then Y.", "We claim: ..."
# This is a broadly used mathematical signal appearing across many papers.
# ---------------------------------------------------------------------------
_WE_CLAIM_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'We\s+claim\s+(?:that\b|:)'
    r'[^.!?]{10,600}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: "A straightforward/simple/direct ... shows/proves that ..." prose proposition
# Catches: "A straightforward application of Zorn's lemma shows that ..."
#          "A simple counting argument proves that ..."
# Generalizes over specific argument types.
# ---------------------------------------------------------------------------
_STRAIGHTFORWARD_SHOWS_PROSE_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'A\s+(?:straightforward|simple|direct|elementary|standard|easy|routine)\s+'
    r'(?:\w+\s+){0,5}'
    r'(?:shows?|proves?|demonstrates?|implies?|yields?|gives?|establishes?)\s+'
    r'that\b'
    r'[^.!?]{10,500}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: "It is well known and not difficult to verify that ..." prose proposition
# Catches the pattern "It is well known and not difficult to verify that ..."
# which is a variant of _WELLKNOWN_PROSE_RE not anchored at paragraph boundary.
# Requires math or cite content to reduce false positives.
# ---------------------------------------------------------------------------
_WELL_KNOWN_NOT_DIFFICULT_RE = re.compile(
    r'(?:^|(?<=[.!?\n])|\n)\s*'
    r'(?P<body>'
    r'It\s+is\s+well\s+known\s+and\s+'
    r'(?:not\s+(?:difficult|hard)|easy)\s+'
    r'to\s+(?:verify|see|check|prove|show)\s+that\b'
    r'[^.!?]{10,600}?'
    r'(?:\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}|\$[^$]{2,}?\$|\\ref\{[^}]+\})'
    r'[^.!?]{0,200}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Prose paragraph between two LaTeX environments that:
# 1. Starts with "Alternatively," or a logical transition
# 2. Contains mathematical content ($...$)
# 3. Ends at the next \begin{...} or paragraph break
# This catches informal claim paragraphs like Example 3 above.
# ---------------------------------------------------------------------------
_ALTERNATIVELY_PARA_RE = re.compile(
    r'(?:^|\n{2,})'
    r'(?P<body>'
    r'(?:Alternatively|Moreover|Furthermore|In\s+other\s+words|In\s+addition|'
    r'Equivalently|Conversely|Similarly|Analogously)\b'
    r'[^\n]{20,}'
    r'(?:\n(?!\n)[^\n]+)*'
    r')'
    r'(?=\n{2,}|\\(?:begin|end|section|subsection|paragraph)|\Z)',
    re.DOTALL | re.MULTILINE,
)

# Require math content to accept alternatively paragraphs
_ALTERNATIVELY_PARA_MATH_RE = re.compile(
    r'\$[^$]{2,}?\$'
    r'|\\begin\{(?:equation|align|eqnarray|gather)\*?\}'
    r'|\$\$',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# NEW: "It is proved in \cite{...} that ..." prose proposition
# Catches: "It is proved in \cite{HS2} that, for every $T$, ..."
# Complements _IT_WAS_SHOWN_IN_CITE_RE (past tense) with present tense.
# ---------------------------------------------------------------------------
_IT_IS_PROVED_IN_CITE_THAT_RE = re.compile(
    r'(?:^|(?<=[.!?\n]))\s*'
    r'(?P<body>'
    r'It\s+is\s+(?:proved?|shown|established|demonstrated)\s+in\s+'
    r'\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}'
    r'[^.!?]{0,300}?'
    r'that\b'
    r'[^.!?]{10,600}?'
    r'(?:\\cite(?:\s*\[[^\]]*\])?\{[^}]+\}|\$[^$]{2,}?\$|\\ref\{[^}]+\})?'
    r'[^.!?]{0,200}?'
    r'[.!?]'
    r')',
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# NEW: Inline problem: paragraph starting with "In the <X> problem" or
# "the <X> problem" near a section boundary — catches definitional prose
# problem statements not wrapped in any LaTeX environment.
# ---------------------------------------------------------------------------
_INLINE_PROBLEM_DEFINITION_RE = re.compile(
    r'(?:^|\n{2,})'
    r'(?P<body>'
    r'(?:In\s+)?[Tt]he\s+(?:\w+\s+){1,5}problem\b'
    r'[^\n]{10,600}'
    r'(?:\n(?!\n)[^\n]{0,300}){0,4}'
    r')',
    re.DOTALL,
)

# Require substantive content: must contain a verb and either math or
# a structural keyword to avoid matching mere references like "the sorting problem"
_INLINE_PROBLEM_VERB_RE = re.compile(
    r'(?:we\s+(?:are\s+given|give|propose|present|show|prove|consider|want|aim)|'
    r'the\s+goal\s+is|our\s+goal\s+is|the\s+objective\s+is|'
    r'we\s+want\s+to|we\s+wish\s+to|the\s+task\s+is)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------
def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []
    seen_spans: List[tuple] = []  # (start, end) of already-accepted matches

    def _overlaps(start: int, end: int) -> bool:
        for s, e in seen_spans:
            if start < e and end > s:
                return True
        return False

    def _record(raw: str, name, env_name: str, rule_name: str,
                structure_type: str, start: int, end: int) -> None:
        if _overlaps(start, end):
            return
        if _inside_excluded_env(text, start, end):
            return
        seen_spans.append((start, end))
        clean = _clean_latex(raw)
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': structure_type,
        })

    # ------------------------------------------------------------------
    # 1. Custom-prefixed theorem-like environments
    # ------------------------------------------------------------------
    for m in _CUSTOM_THEOREM_ENV_RE.finditer(text):
        env = m.group('env')
        opt = m.group('opt')
        body = m.group('body')
        kind = _CUSTOM_ENV_KIND.get(env.lower(), 'theorem')
        name = opt.strip() if opt else None
        _record(
            raw=body,
            name=name,
            env_name='distilled',
            rule_name='_CUSTOM_THEOREM_ENV_RE',
            structure_type=kind,
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1b. \begin{property} / \begin{fact} environments
    # ------------------------------------------------------------------
    for m in _PROPERTY_FACT_ENV_RE.finditer(text):
        env = m.group('env').lower()
        opt = m.group('opt')
        body = m.group('body')
        kind = _PROPERTY_FACT_KIND.get(env, 'proposition')
        name = opt.strip() if opt else None
        _record(
            raw=body,
            name=name,
            env_name='distilled',
            rule_name='_PROPERTY_FACT_ENV_RE',
            structure_type=kind,
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1c. Starred variants of standard theorem-like environments
    # ------------------------------------------------------------------
    for m in _STARRED_THEOREM_ENV_RE.finditer(text):
        env = m.group('env').lower()
        opt = m.group('opt')
        body = m.group('body')
        kind = _STARRED_ENV_KIND.get(env, 'theorem')
        name = opt.strip() if opt else None
        _record(
            raw=body,
            name=name,
            env_name='distilled',
            rule_name='_STARRED_THEOREM_ENV_RE',
            structure_type=kind,
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1d. \claim{...} macro pattern
    # ------------------------------------------------------------------
    for m in _CLAIM_MACRO_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_CLAIM_MACRO_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1e. \noindent{\bf Title}{\it/\sl body} bold-headed italic-body blocks
    # ------------------------------------------------------------------
    for m in _NOINDENT_BF_IT_RE.finditer(text):
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kind = _classify_noindent_bf_it(title)
        _record(
            raw=body,
            name=title if title else None,
            env_name='distilled',
            rule_name='_NOINDENT_BF_IT_RE',
            structure_type=kind,
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1f. \textit{Short title.} paragraph-style labeled proposition/claim
    # ------------------------------------------------------------------
    for m in _ITALIC_LABEL_PARA_RE.finditer(text):
        label = m.group('label').strip()
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        label_lower = label.lower()
        kind = 'proposition'
        for kw, k in _NOINDENT_BF_IT_KIND_MAP.items():
            if kw in label_lower:
                kind = k
                break
        raw = label + ' ' + body
        _record(
            raw=raw,
            name=label if label else None,
            env_name='distilled',
            rule_name='_ITALIC_LABEL_PARA_RE',
            structure_type=kind,
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1g. \begin{description}...\end{description} — mathematical case enumeration
    # ------------------------------------------------------------------
    for m in _DESCRIPTION_ENV_RE.finditer(text):
        opt = m.group('opt')
        body = m.group('body')
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if '$' not in body and r'\item' not in body:
            continue
        name = opt.strip() if opt else None
        _record(
            raw=body,
            name=name,
            env_name='distilled',
            rule_name='_DESCRIPTION_ENV_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1h. \begin{itemize}...\end{itemize} — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 1i. {\bfseries <Title>} inline bold heading followed by prose — claim blocks
    # PRUNED — FP on 1804.04206v1 | also 3 TP — review before uncommenting
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 1j. \noindent {\bf Label}: body — bold-labeled free-text problem block
    # PRUNED — see comments above
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 1k. {\bf Claim N} / \textbf{Claim N} prose inline claim blocks
    # ------------------------------------------------------------------
    for m in _PROSE_BOLD_CLAIM_RE.finditer(text):
        kind_str = m.group('kind').lower()
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kind = _PROSE_BOLD_CLAIM_KIND_MAP.get(kind_str, 'claim')
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_PROSE_BOLD_CLAIM_RE',
            structure_type=kind,
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1l. Remark environment bodies containing open-problem language
    # ------------------------------------------------------------------
    for m in _REMARK_ENV_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Only fire if body contains open-problem keywords
        if not _OPEN_PROBLEM_KEYWORDS_RE.search(body):
            continue
        # Also check for open-problem items in list form
        item_found = False
        for item_m in _OPEN_PROBLEM_ITEM_RE.finditer(body):
            item_body = item_m.group('body').strip()
            if len(item_body) < 20:
                continue
            abs_start = m.start('body') + item_m.start()
            abs_end = m.start('body') + item_m.end()
            _record(
                raw=item_body,
                name=None,
                env_name='distilled',
                rule_name='_REMARK_ENV_RE',
                structure_type='open_problem',
                start=abs_start,
                end=abs_end,
            )
            item_found = True
        if not item_found:
            _record(
                raw=body,
                name=None,
                env_name='distilled',
                rule_name='_REMARK_ENV_RE',
                structure_type='open_problem',
                start=m.start(),
                end=m.end(),
            )

    # ------------------------------------------------------------------
    # 1m. Inter-environment prose gap containing open-problem language
    # ------------------------------------------------------------------
    for m in _INTER_ENV_PROSE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if not _OPEN_PROBLEM_KEYWORDS_RE.search(body):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_INTER_ENV_PROSE_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1n. "Consider [the/a] [equation/system/problem]..." + equation block
    #     Catches problem statements introduced by "Consider the ... equation:"
    # ------------------------------------------------------------------
    for m in _CONSIDER_EQUATION_PROBLEM_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_CONSIDER_EQUATION_PROBLEM_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1o. Enumerate items with math under (sub)section headings
    #     Catches proposition-like list items in Properties/Relations sections
    # ------------------------------------------------------------------
    for sec_m in _SECTION_ENUMERATE_ITEM_RE.finditer(text):
        enum_body = sec_m.group('enum_body')
        block_start = sec_m.start()
        if _inside_excluded_env(text, sec_m.start(), sec_m.end()):
            continue
        for item_m in _ENUM_MATH_ITEM_RE.finditer(enum_body):
            item_body = item_m.group('body').strip()
            if len(item_body) < 10:
                continue
            abs_start = block_start + item_m.start()
            abs_end = block_start + item_m.end()
            if _inside_excluded_env(text, abs_start, abs_end):
                continue
            _record(
                raw=item_body,
                name=None,
                env_name='distilled',
                rule_name='_SECTION_ENUMERATE_ITEM_RE',
                structure_type='proposition',
                start=abs_start,
                end=abs_end,
            )

    # ------------------------------------------------------------------
    # 1p. "authors raised a question whether ..." open problem prose
    # ------------------------------------------------------------------
    for m in _RAISED_QUESTION_WHETHER_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_RAISED_QUESTION_WHETHER_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1q. Inline structural claim paragraphs — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 1r. "We claim that ..." inline claim pattern
    # ------------------------------------------------------------------
    for m in _WE_CLAIM_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WE_CLAIM_THAT_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1s. "A straightforward/simple ... shows that ..." prose proposition
    # ------------------------------------------------------------------
    for m in _STRAIGHTFORWARD_SHOWS_PROSE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_STRAIGHTFORWARD_SHOWS_PROSE_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1t. "It is proved in \cite{...} that ..." prose proposition (present tense)
    # ------------------------------------------------------------------
    for m in _IT_IS_PROVED_IN_CITE_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_IS_PROVED_IN_CITE_THAT_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1u. "It is well known and not difficult to verify that ..." proposition
    # ------------------------------------------------------------------
    for m in _WELL_KNOWN_NOT_DIFFICULT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WELL_KNOWN_NOT_DIFFICULT_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1v. "Alternatively/Moreover/..." paragraphs with math content — claim
    # ------------------------------------------------------------------
    for m in _ALTERNATIVELY_PARA_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if not _ALTERNATIVELY_PARA_MATH_RE.search(body):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_ALTERNATIVELY_PARA_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 1w. Inline problem definition: "In the <X> problem ..." / "the <X> problem ..."
    #     Catches definitional prose problem statements not in LaTeX environments.
    # ------------------------------------------------------------------
    for m in _INLINE_PROBLEM_DEFINITION_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Require a problem-definitional verb phrase to avoid false positives
        if not _INLINE_PROBLEM_VERB_RE.search(body):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_INLINE_PROBLEM_DEFINITION_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 2. Optimization problems in eqnarray / align / equation environments
    # ------------------------------------------------------------------
    for m in _OPT_EQNARRAY_RE.finditer(text):
        body = m.group('body')
        if not _OPT_BODY_TRIGGER_RE.search(body):
            continue
        intro = m.group('intro')
        raw = intro.strip() + '\n' + m.group('env')
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_OPT_EQNARRAY_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 3. Optimization problems in enumerate environments
    # ------------------------------------------------------------------
    for m in _OPT_ENUMERATE_RE.finditer(text):
        body = m.group('body')
        if not re.search(r'\\(?:min|max)\b', body):
            continue
        intro = m.group('intro')
        raw = intro.strip() + '\n' + m.group('env')
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_OPT_ENUMERATE_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 4. Future-work / open-problem prose sentences — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 5. Inline bold/italic theorem-like keyword at line start — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 6. Named conjecture/theorem statement — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 7. Inline problem statement — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 8. Open problem / gap prose sentences (extended patterns) — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 9. Informal claim/observation phrases — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 10. Result-announcing phrase before eqnarray
    # ------------------------------------------------------------------
    for m in _RESULT_INTRO_EQNARRAY_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        raw = m.group('env')
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_RESULT_INTRO_EQNARRAY_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 11. Result-announcing phrase before equation
    # ------------------------------------------------------------------
    for m in _RESULT_INTRO_EQ_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        raw = m.group('env')
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_RESULT_INTRO_EQ_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 12. Forward-looking / open-problem sentences in conclusions
    # ------------------------------------------------------------------
    for m in _FORWARD_LOOKING_RE.finditer(text):
        sentence = m.group('sentence').strip()
        if len(sentence) < 30:
            continue
        _record(
            raw=sentence,
            name=None,
            env_name='distilled',
            rule_name='_FORWARD_LOOKING_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 13. Prose claim sentences with assertive opening anchors — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 14. Prose conjecture: "We conjecture ..." / "We believe ..." — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 14b. Prose conjecture: "We conjecture / expect / anticipate ..." inline — PRUNED
    # PRUNED — FP on 1502.03482v2, 1510.04064v1, 1512.05406v1 +4 more | also 2 TP — review before uncommenting
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 14c. "In particular ... should also follow ..." conjecture-like prose
    # ------------------------------------------------------------------
    for m in _IN_PARTICULAR_SHOULD_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IN_PARTICULAR_SHOULD_RE',
            structure_type='conjecture',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 15. Prose conjecture: "<Name/phrase> conjectured that ..."
    # ------------------------------------------------------------------
    for m in _X_CONJECTURED_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_X_CONJECTURED_THAT_RE',
            structure_type='conjecture',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 16. Prose conjecture: "... conjecture ..., stating that ..."
    # ------------------------------------------------------------------
    for m in _CONJECTURE_STATING_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_CONJECTURE_STATING_THAT_RE',
            structure_type='conjecture',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 17. Prose conjecture: "... conjecture ... states that ..."
    # ------------------------------------------------------------------
    for m in _CONJECTURE_STATES_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_CONJECTURE_STATES_THAT_RE',
            structure_type='conjecture',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 17b. Prose conjecture: "... asserts that ..."
    # ------------------------------------------------------------------
    for m in _ASSERTS_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_ASSERTS_THAT_RE',
            structure_type='conjecture',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 17c. Prose conjecture: "... hypothesize[d] that ..."
    # ------------------------------------------------------------------
    for m in _HYPOTHESIZE_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_HYPOTHESIZE_THAT_RE',
            structure_type='conjecture',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 17d. "expected to be" conjecture-like prose — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 18. Prose open problem: "The question is whether/if ..."
    # ------------------------------------------------------------------
    for m in _THE_QUESTION_IS_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_THE_QUESTION_IS_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 19. Prose open problem: "we don't/do not know ..."
    # ------------------------------------------------------------------
    for m in _WE_DONT_KNOW_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WE_DONT_KNOW_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 20. Prose open problem: "We wonder if/whether ..."
    # ------------------------------------------------------------------
    for m in _WE_WONDER_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WE_WONDER_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 20b. Prose open problem: "It is natural/reasonable to ask ..."
    # ------------------------------------------------------------------
    for m in _IT_IS_NATURAL_TO_ASK_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_IS_NATURAL_TO_ASK_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 20c. Prose open problem: "What if ... $math$ ...?"
    # ------------------------------------------------------------------
    for m in _WHAT_IF_MATH_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WHAT_IF_MATH_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 20d. "it is not clear / it is unclear / ..." open problem prose — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 20e. Open problem paragraph with hedging language — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 20f. "We hope that ..." / "a new idea is needed" open problem prose
    # ------------------------------------------------------------------
    for m in _WE_HOPE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WE_HOPE_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 20g. "topic for future research / left for future work ..." open problem
    # ------------------------------------------------------------------
    for m in _TOPIC_FOR_FUTURE_RESEARCH_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_TOPIC_FOR_FUTURE_RESEARCH_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 20h. Open-question enumerate items preceded by open-question trigger
    # ------------------------------------------------------------------
    for m in _OPEN_QUESTION_ENUM_BLOCK_RE.finditer(text):
        enum_body = m.group('enum_body')
        block_start = m.start()
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        for item_m in _ENUM_ITEM_RE.finditer(enum_body):
            item_body = item_m.group('body').strip()
            if len(item_body) < 20:
                continue
            abs_start = block_start + item_m.start()
            abs_end = block_start + item_m.end()
            _record(
                raw=item_body,
                name=None,
                env_name='distilled',
                rule_name='_OPEN_QUESTION_ENUM_BLOCK_RE',
                structure_type='open_problem',
                start=abs_start,
                end=abs_end,
            )

    # ------------------------------------------------------------------
    # 20i. "it would be interesting to investigate which other problems ..."
    #      Open problem sentence in Conclusion/Future Work sections.
    #      Caught by _IT_WOULD_BE_INTERESTING_RE (rule 26) — no separate rule needed.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 21. Prose claim: "There is/are (also) ..." + display math
    # ------------------------------------------------------------------
    for m in _THERE_IS_WITH_MATH_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_THERE_IS_WITH_MATH_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 22. Prose claim: "So/Thus/Hence there is/are ..." + display math
    # ------------------------------------------------------------------
    for m in _SO_THERE_IS_WITH_MATH_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_SO_THERE_IS_WITH_MATH_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23. Prose claim: math-result opener + display math
    # ------------------------------------------------------------------
    for m in _MATH_RESULT_OPENER_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_MATH_RESULT_OPENER_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23b. Inline claim: "we claim" + display math
    # ------------------------------------------------------------------
    for m in _INLINE_CLAIM_WITH_MATH_RE.finditer(text):
        intro = m.group('intro').strip()
        math = m.group('math').strip()
        if len(math) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = intro + '\n' + math
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_INLINE_CLAIM_WITH_MATH_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23c. Inline assertive claim with structured opener — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 23d. "An easy/elementary computation shows ..." + equation
    # ------------------------------------------------------------------
    for m in _EASY_COMPUTATION_SHOWS_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_EASY_COMPUTATION_SHOWS_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23e. Statistical decision claim: "Then/Consequently ... rejects/controls ..."
    # ------------------------------------------------------------------
    for m in _STATISTICAL_DECISION_CLAIM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_STATISTICAL_DECISION_CLAIM_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23f. Prose transition phrase + equation/align claim
    # ------------------------------------------------------------------
    for m in _PROSE_EQUATION_CLAIM_RE.finditer(text):
        lead = m.group('lead').strip()
        body = m.group('body').strip()
        eq = m.group('eq')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = lead + '\n' + eq
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_PROSE_EQUATION_CLAIM_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23g. "It follows that ..." + equation/display-math
    # ------------------------------------------------------------------
    for m in _IT_FOLLOWS_EQUATION_RE.finditer(text):
        lead = m.group('lead').strip()
        eq = m.group('eq')
        body = (m.group('body') or m.group('body2') or
                m.group('body3') or m.group('body4') or
                m.group('body5') or '')
        body = body.strip()
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = lead + '\n' + eq
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_IT_FOLLOWS_EQUATION_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23h. "It is straightforward/easy to see that ..." + equation
    # ------------------------------------------------------------------
    for m in _STRAIGHTFORWARD_EQUATION_RE.finditer(text):
        lead = m.group('lead').strip()
        eq = m.group('eq')
        body = (m.group('body') or m.group('body2') or '')
        body = body.strip()
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = lead + '\n' + eq
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_STRAIGHTFORWARD_EQUATION_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23i. "The dimension/rank of X is ..." + display math
    # ------------------------------------------------------------------
    for m in _DIMENSION_IS_EQUATION_RE.finditer(text):
        lead = m.group('lead').strip()
        eq = m.group('eq')
        body = (m.group('body') or m.group('body2') or '')
        body = body.strip()
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = lead + '\n' + eq
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_DIMENSION_IS_EQUATION_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23j. "Find X such that ..." mathematical problem statement
    # ------------------------------------------------------------------
    for m in _FIND_SUCH_THAT_PROBLEM_RE.finditer(text):
        lead = m.group('lead').strip()
        eq = m.group('eq')
        body = (m.group('body') or m.group('body2') or m.group('body3') or '')
        body = body.strip()
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = lead + '\n' + eq
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_FIND_SUCH_THAT_PROBLEM_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23k. "In particular," + display math — informal claim
    # ------------------------------------------------------------------
    for m in _IN_PARTICULAR_WITH_MATH_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IN_PARTICULAR_WITH_MATH_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23l. "X shows/showed that ..." + display math — author-result claim
    # ------------------------------------------------------------------
    for m in _AUTHOR_SHOWS_WITH_MATH_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_AUTHOR_SHOWS_WITH_MATH_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23m. "it will follow from this ..." + display math consequence claim
    # ------------------------------------------------------------------
    for m in _IT_WILL_FOLLOW_FROM_THIS_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_WILL_FOLLOW_FROM_THIS_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23n. Free-prose claim paragraphs starting with logical/mathematical
    # connective phrases — anchored at paragraph boundaries, requires
    # math or citation content.
    # ------------------------------------------------------------------
    for m in _IMPLICIT_CLAIM_LEAD_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 50:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Require math or citation to reduce false positives
        if not _IMPLICIT_CLAIM_MATH_OR_CITE_RE.search(body):
            continue
        kind = _classify_implicit_para(body)
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IMPLICIT_CLAIM_LEAD_RE',
            structure_type=kind,
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 23o. \subsection{...} prose body — claim blocks (ML/applied papers)
    # Only fires when body contains performance/comparison language.
    # ------------------------------------------------------------------
    for m in _SUBSECTION_CLAIM_RE.finditer(text):
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 150:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Only fire if body contains performance/comparison language
        if not _SUBSECTION_CLAIM_TRIGGER_RE.search(body):
            continue
        raw = title + '\n' + body
        _record(
            raw=raw,
            name=title if title else None,
            env_name='distilled',
            rule_name='_SUBSECTION_CLAIM_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 24. \noindent{\em Label.} ... paragraph-style informal claims
    # ------------------------------------------------------------------
    for m in _NOINDENT_EM_CLAIM_RE.finditer(text):
        label = m.group('label').strip().rstrip('.')
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = label + '. ' + body if label else body
        _record(
            raw=raw,
            name=label if label else None,
            env_name='distilled',
            rule_name='_NOINDENT_EM_CLAIM_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 25. Open problem items in "further work" / "open problems" sections
    # ------------------------------------------------------------------
    for sec_m in _FURTHER_WORK_SECTION_RE.finditer(text):
        sec_body = sec_m.group('body')
        sec_body_start = sec_m.start('body')
        for item_m in _FURTHER_WORK_ITEM_RE.finditer(sec_body):
            body = item_m.group('body').strip()
            if len(body) < 20:
                continue
            abs_start = sec_body_start + item_m.start()
            abs_end = sec_body_start + item_m.end()
            if _inside_excluded_env(text, abs_start, abs_end):
                continue
            _record(
                raw=body,
                name=None,
                env_name='distilled',
                rule_name='_FURTHER_WORK_ITEM_RE',
                structure_type='open_problem',
                start=abs_start,
                end=abs_end,
            )

    # ------------------------------------------------------------------
    # 26. "It would be interesting/worthwhile to find/prove ..." sentences
    # ------------------------------------------------------------------
    for m in _IT_WOULD_BE_INTERESTING_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_WOULD_BE_INTERESTING_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 27. "It is well known that ..." inline proposition
    # ------------------------------------------------------------------
    for m in _INLINE_WELL_KNOWN_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_INLINE_WELL_KNOWN_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 27b. Well-known / recall / following-result prose propositions
    # ------------------------------------------------------------------
    for m in _WELLKNOWN_PROSE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WELLKNOWN_PROSE_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 27c. Consequence paragraph after displayed equation — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 27d. Prose intro + eqnarray: "offers/yields/gives ... equations:"
    # ------------------------------------------------------------------
    for m in _PROSE_OFFERS_EQNARRAY_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_PROSE_OFFERS_EQNARRAY_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 27e. "Recall that ..." + itemize with math content
    # ------------------------------------------------------------------
    for m in _RECALL_WITH_ITEMIZE_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 10:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if '$' not in body and r'\[' not in body:
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_RECALL_WITH_ITEMIZE_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 27f. "We recall [cite] \begin{equation}..." lemma/proposition
    # ------------------------------------------------------------------
    for m in _RECALL_CITE_EQUATION_RE.finditer(text):
        lead = m.group('lead').strip()
        body = m.group('body').strip()
        eq = m.group('eq')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = lead + '\n' + eq
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_RECALL_CITE_EQUATION_RE',
            structure_type='lemma',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 27g. "We have [cite] \begin{equation}..." claim/lemma
    # ------------------------------------------------------------------
    for m in _WE_HAVE_CITE_EQUATION_RE.finditer(text):
        lead = m.group('lead').strip()
        body = m.group('body').strip()
        eq = m.group('eq')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = lead + '\n' + eq
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_WE_HAVE_CITE_EQUATION_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 27h. "By an inverse/trace/Sobolev estimate \begin{equation}..."
    # ------------------------------------------------------------------
    for m in _BY_ESTIMATE_EQUATION_RE.finditer(text):
        lead = m.group('lead').strip()
        body = m.group('body').strip()
        eq = m.group('eq')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = lead + '\n' + eq
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_BY_ESTIMATE_EQUATION_RE',
            structure_type='lemma',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 28. "Since [claim with \cite{...}], we get the following." pattern
    # ------------------------------------------------------------------
    for m in _SINCE_WE_GET_FOLLOWING_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_SINCE_WE_GET_FOLLOWING_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 29. "it has been shown / authors have shown that ... \cite{}" proposition
    # ------------------------------------------------------------------
    for m in _INLINE_SHOWN_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_INLINE_SHOWN_THAT_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 30. "It is not hard to show / easy to see that ..." inline claim — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 31. "... currently unknown / difficult problem / not understood ..." — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 32. \cite[Lemma/Theorem N]{ref} which says/states that ...
    # ------------------------------------------------------------------
    for m in _INLINE_CITED_LEMMA_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        cite_text = text[m.start():m.start('body')]
        if re.search(r'Lemma', cite_text, re.IGNORECASE):
            kind = 'lemma'
        elif re.search(r'Proposition', cite_text, re.IGNORECASE):
            kind = 'proposition'
        elif re.search(r'Corollary', cite_text, re.IGNORECASE):
            kind = 'corollary'
        else:
            kind = 'theorem'
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_INLINE_CITED_LEMMA_RE',
            structure_type=kind,
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 33. "X is necessary/sufficient for Y: [claim] \cite{}" inline claim
    # ------------------------------------------------------------------
    for m in _INLINE_NECESSITY_CLAIM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_INLINE_NECESSITY_CLAIM_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 34. Inline claim in gap between \end{...} and \begin{...} — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 35. Inline claim/result following \paragraph{...} heading — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 36. "... proved/showed/demonstrated that ..." with \cite{} — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 37. "... who showed/proved ..." relative clause result restatement
    # ------------------------------------------------------------------
    for m in _WHO_SHOWED_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WHO_SHOWED_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 38. "It remains a major open problem whether ..." pattern — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 39. "it is not even known whether ..." open problem pattern
    # ------------------------------------------------------------------
    for m in _NOT_EVEN_KNOWN_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_NOT_EVEN_KNOWN_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 40. "... suffice / suffices to ..." result claim — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 41. "It follows from [ref] that ..." inline proposition
    # ------------------------------------------------------------------
    for m in _IT_FOLLOWS_FROM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_FOLLOWS_FROM_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 42. "... in particular ..." + \cite{} corollary-like observation — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 43. Lettered list item claims: (a) ..., (b) ..., (c) ..., etc.
    # ------------------------------------------------------------------
    for m in _LETTERED_LIST_CLAIM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if '$' not in body and len(body) < 60:
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_LETTERED_LIST_CLAIM_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 44. Emphasized rhetorical question as open problem
    # ------------------------------------------------------------------
    for m in _EMPH_OPEN_QUESTION_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_EMPH_OPEN_QUESTION_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 45. Math program introduced by "... reads:" or "defined by:" + display math
    # ------------------------------------------------------------------
    for m in _PROGRAM_READS_RE.finditer(text):
        intro = m.group('intro').strip()
        math = m.group('math').strip()
        if len(math) < 10:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = intro + '\n' + math
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_PROGRAM_READS_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 46. "consider the hierarchy/problem/program ..." + display math
    # ------------------------------------------------------------------
    for m in _CONSIDER_PROBLEM_RE.finditer(text):
        intro = m.group('intro').strip()
        math = m.group('math').strip()
        if len(math) < 10:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if not _OPT_BODY_TRIGGER_RE.search(math) and not re.search(
            r'\\(?:min|max)\b|\\operatorname\{(?:min|max)\}|\\mbox\{s\.t', math
        ):
            continue
        raw = intro + '\n' + math
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_CONSIDER_PROBLEM_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 47. "It is proved/shown that ... \begin{equation}..." inline theorem
    # ------------------------------------------------------------------
    for m in _IT_IS_PROVED_EQ_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_IT_IS_PROVED_EQ_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 48. Italic/bold group open problem starting with imperative verb — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 49. "the problem (that) remains is to find/determine/prove ..."
    # ------------------------------------------------------------------
    for m in _PROBLEM_THAT_REMAINS_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_PROBLEM_THAT_REMAINS_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 50. "Is it possible/true/known that ..." rhetorical open question
    # ------------------------------------------------------------------
    for m in _IS_IT_POSSIBLE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IS_IT_POSSIBLE_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 51. "It was shown/proved in \cite{...} that ..." prose theorem
    # ------------------------------------------------------------------
    for m in _IT_WAS_SHOWN_IN_CITE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_WAS_SHOWN_IN_CITE_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 52. "from \cite{...} we know / by \cite{...} we know that ..."
    # ------------------------------------------------------------------
    for m in _WE_KNOW_CITE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_WE_KNOW_CITE_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 53. "This result was extended/generalized ... in \cite{...}" prose theorem
    # ------------------------------------------------------------------
    for m in _RESULT_EXTENDED_CITE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_RESULT_EXTENDED_CITE_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 54. Named Problem/Question N.M of \cite{...} open problem reference
    # ------------------------------------------------------------------
    for m in _NAMED_PROBLEM_CITE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_NAMED_PROBLEM_CITE_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 55. "X proved/showed in \cite{...} that ..." author-attributed theorem
    # ------------------------------------------------------------------
    for m in _AUTHOR_PROVED_CITE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_AUTHOR_PROVED_CITE_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 56. "result in \cite{...} can be stated as ..." prose restatement
    # ------------------------------------------------------------------
    for m in _CAN_BE_STATED_AS_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_CAN_BE_STATED_AS_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 57. "it was observed/noted that ..." inline proposition/claim
    # ------------------------------------------------------------------
    for m in _IT_WAS_OBSERVED_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_WAS_OBSERVED_THAT_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 58. "In \cite{X} it was proved/shown that ..." inline theorem
    # ------------------------------------------------------------------
    for m in _IN_CITE_IT_WAS_PROVED_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IN_CITE_IT_WAS_PROVED_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 59. "remains a difficult/hard/challenging problem" open problem prose
    # ------------------------------------------------------------------
    for m in _REMAINS_DIFFICULT_PROBLEM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_REMAINS_DIFFICULT_PROBLEM_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 60. Prose-introduced optimization/control problem with equation block(s)
    # ------------------------------------------------------------------
    for m in _PROSE_PROBLEM_TRIGGER_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if not _OPT_BODY_TRIGGER_RE.search(body) and not re.search(
            r'\\(?:min|max)\b|\\operatorname\{(?:min|max)\}|subject\s+to|\\mbox\{s\.t',
            body, re.IGNORECASE
        ):
            continue
        raw = intro + '\n' + body
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_PROSE_PROBLEM_TRIGGER_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 60b. Penalized/regularized regression criterion + equation block
    # ------------------------------------------------------------------
    for m in _PENALIZED_CRITERION_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_PENALIZED_CRITERION_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 61. Discourse-marker prose claim sentences — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 62. align/align* with \min or \max preceded by optimization prose — PRUNED
    # PRUNED — FP on 1712.00232v3 | also 8 TP — review before uncommenting
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 63. Paragraph starting with Theorem/Lemma \ref{} + consequence verb
    # Catches corollary-like prose that refers back to a numbered result.
    # ------------------------------------------------------------------
    for m in _THEOREM_REF_CONSEQUENCE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_THEOREM_REF_CONSEQUENCE_RE',
            structure_type='corollary',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 64. "one can show/verify/check/prove that ..." with math or cite — PRUNED
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 65. Prose sentence + \begin{itemize} listing mathematical properties
    # ------------------------------------------------------------------
    for m in _PROSE_WITH_ITEMIZE_PROPS_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 10:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if '$' not in body and r'\[' not in body:
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_PROSE_WITH_ITEMIZE_PROPS_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 66. Consequence sentence immediately after \end{definition}/\end{remark}
    # ------------------------------------------------------------------
    for m in _POST_DEFINITION_CONSEQUENCE_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_POST_DEFINITION_CONSEQUENCE_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 67. "it is known that ..." inline theorem/proposition
    # ------------------------------------------------------------------
    for m in _IT_IS_KNOWN_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_IS_KNOWN_THAT_RE',
            structure_type='theorem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 68. "Recall that ..." proposition-like statement (sentence-initial) — PRUNED
    # PRUNED — FP on 1102.4533v1, 1705.02177v2, 1804.04279v1 | also 2 TP — review before uncommenting
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 69. "In particular, ..." corollary after \end{theorem}/\end{lemma}
    # ------------------------------------------------------------------
    for m in _IN_PARTICULAR_AFTER_THM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IN_PARTICULAR_AFTER_THM_RE',
            structure_type='corollary',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 70. "observe that ..." claim-like statement — PRUNED
    # PRUNED — FP on 1209.2510v1, 1210.4765v1, 1409.6258v2 +1 more | also 6 TP — review before uncommenting
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 71. "It is shown in \cite{...} that ..." proposition
    # ------------------------------------------------------------------
    for m in _IT_IS_SHOWN_IN_CITE_THAT_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_IT_IS_SHOWN_IN_CITE_THAT_RE',
            structure_type='proposition',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 72. Sentence after \end{lemma/theorem} starting with "According to
    # Lemma/Theorem \ref{...}" — corollary-like consequence prose
    # ------------------------------------------------------------------
    for m in _POST_ENV_ACCORDING_TO_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_POST_ENV_ACCORDING_TO_RE',
            structure_type='corollary',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 73. Itemize block preceded by "following observations/properties" intro
    # ------------------------------------------------------------------
    for m in _ITEMIZE_THM_INTRO_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 10:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if '$' not in body and r'\[' not in body:
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_ITEMIZE_THM_INTRO_RE',
            structure_type='claim',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 74. "No X is known / No better bound is known" open problem sentences
    # ------------------------------------------------------------------
    for m in _NO_X_IS_KNOWN_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_NO_X_IS_KNOWN_RE',
            structure_type='open_problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 75. "only able to analyze / new ideas are needed" limitation sentences — PRUNED
    # PRUNED — FP on 1612.05419v3 | also 1 TP — review before uncommenting
    # ------------------------------------------------------------------
    pass  # PRUNED: body commented out

    # ------------------------------------------------------------------
    # 76. "hence by Theorem/Lemma \ref{...} we obtain ..." consequence prose
    # ------------------------------------------------------------------
    for m in _HENCE_BY_THEOREM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_HENCE_BY_THEOREM_RE',
            structure_type='corollary',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 77. Hypothesis testing problem: prose framing H_0/H_1 inside equation block
    # ------------------------------------------------------------------
    for m in _HYPOTHESIS_TESTING_PROBLEM_RE.finditer(text):
        intro = m.group('intro').strip()
        body = m.group('body').strip()
        env = m.group('env')
        if len(body) < 5:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        if not _HYPOTHESIS_EQ_BODY_RE.search(body):
            continue
        raw = intro + '\n' + env
        _record(
            raw=raw,
            name=None,
            env_name='distilled',
            rule_name='_HYPOTHESIS_TESTING_PROBLEM_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # 78. "one can clearly ask: what is X?" — prose problem with question
    # ------------------------------------------------------------------
    for m in _ONE_CAN_ASK_PROBLEM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _record(
            raw=body,
            name=None,
            env_name='distilled',
            rule_name='_ONE_CAN_ASK_PROBLEM_RE',
            structure_type='problem',
            start=m.start(),
            end=m.end(),
        )

    return results


# --- realise the selected subset: non-selected PRODUCING rules made inert ---
_SUBSET_NEVER = re.compile(r'(?!x)x')
_AUTHOR_PROVED_CITE_RE = _SUBSET_NEVER
_CONJECTURE_STATES_THAT_RE = _SUBSET_NEVER
_CONSIDER_PROBLEM_RE = _SUBSET_NEVER
_CUSTOM_THEOREM_ENV_RE = _SUBSET_NEVER
_DESCRIPTION_ENV_RE = _SUBSET_NEVER
_HYPOTHESIS_TESTING_PROBLEM_RE = _SUBSET_NEVER
_INLINE_CLAIM_WITH_MATH_RE = _SUBSET_NEVER
_INLINE_WELL_KNOWN_RE = _SUBSET_NEVER
_ITEMIZE_THM_INTRO_RE = _SUBSET_NEVER
_IT_IS_NATURAL_TO_ASK_RE = _SUBSET_NEVER
_IT_IS_SHOWN_IN_CITE_THAT_RE = _SUBSET_NEVER
_NO_X_IS_KNOWN_RE = _SUBSET_NEVER
_OPT_ENUMERATE_RE = _SUBSET_NEVER
_OPT_EQNARRAY_RE = _SUBSET_NEVER
_PENALIZED_CRITERION_RE = _SUBSET_NEVER
_PROGRAM_READS_RE = _SUBSET_NEVER
_PROSE_OFFERS_EQNARRAY_RE = _SUBSET_NEVER
_PROSE_PROBLEM_TRIGGER_RE = _SUBSET_NEVER
_SINCE_WE_GET_FOLLOWING_RE = _SUBSET_NEVER
_STARRED_THEOREM_ENV_RE = _SUBSET_NEVER
_STATISTICAL_DECISION_CLAIM_RE = _SUBSET_NEVER
_THE_QUESTION_IS_RE = _SUBSET_NEVER
_WE_HOPE_RE = _SUBSET_NEVER
