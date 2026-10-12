import re
from typing import List, Dict

try:
    from latex_clean import clean_latex_to_text as _clean_latex
except Exception:
    _clean_latex = lambda s: s


# Environments already handled by the base parser; never re-match inside them.
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|assumption)\*?\}.*?\\end\{\1\*?\}',
    re.DOTALL,
)

# Environment-anchored remark / example / assumption blocks that the base
# parser may miss (e.g. non-standard spellings or starred variants).
REMARK_ENV_RE = re.compile(
    r'\\begin\{(remark)\*?\}(?P<body>.*?)\\end\{\1\*?\}', re.DOTALL | re.IGNORECASE
)
EXAMPLE_ENV_RE = re.compile(
    r'\\begin\{(example)\*?\}(?P<body>.*?)\\end\{\1\*?\}', re.DOTALL | re.IGNORECASE
)
ASSUMPTION_ENV_RE = re.compile(
    r'\\begin\{(assumption)\*?\}(?P<body>.*?)\\end\{\1\*?\}', re.DOTALL | re.IGNORECASE
)

# Bold/emph-anchored leads on the first sentence of a paragraph, e.g.
# \textbf{Remark.} ... or \emph{Example 2.} ...
EMPH_LEAD_RE = re.compile(
    r'(?m)^[ \t]*\\(?:textbf|emph|textit)\{(?P<lead>Remark|Example|Assumption)[^}]*\}[^\n]*'
    r'(?:\n(?![ \t]*\n)[^\n]*)*',
    re.IGNORECASE,
)

# Run-in styled heading ending in a period, followed by prose in the same
# paragraph: \textit{Topic.} body...  Anchors on markup structure only.
# PRUNED — FP on 1102.4533v1, 1502.03482v2, 1503.04023v2 +2 more | also 4 TP — review before uncommenting
# RUN_IN_REMARK_RE = re.compile(
#     r'(?m)^[ \t]*\\(?:textit|textbf|emph)\{(?P<lead>[^{}]{1,80})\}\.?[ \t]+'
#     r'(?P<body>[^\n]+(?:\n(?![ \t]*\n)[^\n]*)*)',
# )
RUN_IN_REMARK_RE = re.compile(r'(?!x)x')  # PRUNED

# PRUNED — FP on 1512.05406v1 | also 3 TP — review before uncommenting
# RUNIN_REMARK_RE = re.compile(
#     r'(?m)^[ \t]*\\(?:mypar|paragraph)\{(?P<lead>[^{}]{1,80})\}[ \t]*\n?'
#     r'(?P<body>[^\n]+(?:\n(?![ \t]*\n)[^\n]*)*)',
# )
RUNIN_REMARK_RE = re.compile(r'(?!x)x')  # PRUNED

# PRUNED — FP on 1102.4533v1, 1708.00522v2 | also 4 TP — review before uncommenting
# REMARK_LEAD_RE = re.compile(
#     r'(?m)^[ \t]*(?:We\s+remark\s+that|Remark\.?|Note(?:\s+also)?\s+that|Observe\s+that|Notice\s+that)\b'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
REMARK_LEAD_RE = re.compile(r'(?!x)x')  # PRUNED

# Plain remark-signalling paragraph openers outside environments:
# "It should be mentioned that ...", "It is worth noting ...", "We remark that ...".
# PRUNED — FP on 1102.4533v1, 1104.2168v1, 1502.03482v2 +4 more | also 15 TP — review before uncommenting
# REMARK_SIGNAL_RE = re.compile(
#     r'(?m)^[ \t]*(?:It\s+(?:should|must|is\s+worth|is\s+important\s+to)\s+(?:be\s+)?'
#     r'(?:mentioned|noted|remarked|emphasized)|We\s+(?:remark|note|would\s+like\s+to\s+point\s+out)\s+that|'
#     r'Note\s+that|We\s+emphasize\s+that)\b'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
REMARK_SIGNAL_RE = re.compile(r'(?!x)x')  # PRUNED

# Remark-cue paragraphs that directly follow a proof or theorem-like
# environment (interpretive commentary placed after the closing \end{...}).
POST_ENV_REMARK_RE = re.compile(
    r'\\end\{(?:proof|theorem|lemma|proposition|corollary|conjecture|myThm|myConj)\*?\}'
    r'[ \t]*\n+'
    r'(?P<body>(?:In\s+general|However,|We\s+(?:see|note|observe)|Note\s+that|'
    r'Remark|For\s+example|Similar\s+to|It\s+is\s+(?:thus\s+)?possible|'
    r'Although|Moreover|Furthermore)'
    r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*)',
    re.IGNORECASE,
)

# PRUNED — FP on 1502.03482v2 | also 1 TP — review before uncommenting
# EXAMPLE_CUE_RE = re.compile(
#     r'(?m)^[ \t]*(?:We\s+now\s+(?:show|give|present|illustrate)|As\s+an\s+example|'
#     r'Here\s+is\s+an\s+example|Toy\s+example|We\s+still\s+use\b[^\n]{0,80}?as\s+an\s+example|'
#     r'Another\s+(?:explanation|way)\b)'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
EXAMPLE_CUE_RE = re.compile(r'(?!x)x')  # PRUNED

# Assumption sentences introduced by a standard lead-in ("we assume ...").
ASSUMPTION_LEAD_RE = re.compile(
    r'(?m)^[ \t]*(?:(?:In\s+(?:the\s+following|general|what\s+follows)|Throughout|Henceforth)'
    r'[^\n.]{0,60}?,\s*)?\bwe\s+assume\b[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
    re.IGNORECASE,
)
# PRUNED — FP on 1102.4533v1, 1503.04023v2, 1510.04064v1 | also 5 TP — review before uncommenting
# ASSUME_SENT_RE = re.compile(
#     r'(?:^|(?<=[.!?]\s))(?:We\s+will\s+(?:also\s+)?assume|Assume|Suppose)\s+that\b'
#     r'[^.!?\n]*(?:[.!?](?=\s|$)|\n)',
#     re.IGNORECASE | re.MULTILINE,
# )
ASSUME_SENT_RE = re.compile(r'(?!x)x')  # PRUNED
ASSUMPTION_SENT_RE = re.compile(
    r'(?:^|(?<=[.!?]\s))'
    r'((?:[^.!?\n]*?,\s*)?(?:we|one)\s+(?:must\s+|can\s+|will\s+|also\s+)?'
    r'(?:assume|impose|suppose|require|focus\s+on)\b[^.!?]*[.!?])',
    re.IGNORECASE,
)

# Attributed assumption lead-ins: "Following \cite{...}, we set/fix ...".
ATTRIBUTED_ASSUMPTION_RE = re.compile(
    r'(?:^|(?<=[.!?]\s))'
    r'((?:Following\s+\\(?:newcite|cite[a-z]*|citet|citep)\{[^}]*\},\s*)'
    r'(?:we|one)\s+(?:assume|set|suppose|fix)\b[^.!?]*[.!?])',
    re.IGNORECASE,
)

# Convention sentences: "For identifiability, ... we center ..."
CONVENTION_SENT_RE = re.compile(
    r'(?:^|(?<=[.!?]\s))'
    r'((?:For|In order to|To)\s+[^,.!?]{1,60},\s*[^.!?]*?\b(?:we|one)\s+'
    r'(?:also\s+)?(?:center|centre|normalize|standardize|assume|impose|require)\b[^.!?]*[.!?])',
    re.IGNORECASE,
)

# PRUNED — FP on 1102.4533v1 | also 1 TP — review before uncommenting
# STANDING_ASSUMP_RE = re.compile(
#     r'(?:^|(?<=[.!?]\s))'
#     r'((?:For\s+notational\s+convenience|Throughout\s+(?:this|the)\s+(?:paper|section)|'
#     r'Without\s+loss\s+of\s+generality|(?:we|one)\s+assume\s+without\s+loss\s+of\s+generality)'
#     r'\b[^.!?]*[.!?])',
#     re.IGNORECASE,
# )
STANDING_ASSUMP_RE = re.compile(r'(?!x)x')  # PRUNED

# Standing-assumption opener: "In this section, let $E$ be ..." / "Throughout, let ..."
# followed by display or inline math; anchors on the structural opener only.
STANDING_OPENER_RE = re.compile(
    r'(?m)^[ \t]*(?:In\s+this\s+(?:section|subsection)|Throughout|For\s+the\s+rest\s+of\s+this\s+section),?\s+'
    r'(?:let|assume|suppose)\b[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
    re.IGNORECASE,
)

# Causal imposition sentences: "Since ..., we impose the constraint ..."
IMPOSE_SENT_RE = re.compile(
    r'(?:^|(?<=[.!?]\s))'
    r'((?:(?:Since|Because|As)\s+[^.!?]*?,\s*)?(?:we|one)\s+(?:now\s+)?'
    r'(?:impose|enforce|require)\s+(?:the\s+)?(?:constraint|condition)?\b[^.!?]*[.!?])',
    re.IGNORECASE,
)

# Discourse-connective normalization sentences: "Moreover, we standardize ..."
NORMALIZE_SENT_RE = re.compile(
    r'(?:^|(?<=[.!?]\s))'
    r'((?:Moreover|Furthermore|Also|Additionally|Finally)\s*,\s*(?:we|one)\s+'
    r'(?:also\s+)?(?:standardize|normalize|center|centre|scale|rescale|regularize)\b[^.!?]*[.!?])',
    re.IGNORECASE,
)

# Scoping assumption paragraphs: "Throughout this section/paper ..." and
# "Starting from this section ..." / "From now on ..." followed by a
# standing hypothesis (assume / work over / is an arbitrary field).
ASSUMPTION_SCOPE_RE = re.compile(
    r'(?m)^[ \t]*(?:\{\\bf\s+Conventions\.\}\s*)?'
    r'(?:Throughout\s+(?:the\s+paper|this\s+(?:section|subsection|chapter))|'
    r'Starting\s+from\s+this\s+(?:section|subsection)|From\s+now\s+on|'
    r'Throughout\s+the\s+section)\b'
    r'[^\n]*?\b(?:we\s+(?:work|assume|consider)|assume\s+that|assume|is|are)\b'
    r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
    re.IGNORECASE,
)

# Scoping sentences: "In this section, we focus on ..." / "Throughout this paper, we restrict ..."
SCOPE_SENT_RE = re.compile(
    r'(?:^|(?<=[.!?]\s))'
    r'((?:Throughout|In)\s+(?:this|the)\s+(?:section|paper|subsection|setting|case)\s*,\s*'
    r'(?:we|one)\s+(?:focus|restrict|consider|work)\b(?:\s+(?:on|to))?[^.!?]*[.!?])',
    re.IGNORECASE,
)

# PRUNED — FP on 1102.4533v1, 1502.03482v2, 1708.00522v2 | also 8 TP — review before uncommenting
# PROSE_REMARK_CUE_RE = re.compile(
#     r'(?m)^[ \t]*(?:We\s+remark\s+that|Note\s+that|Observe\s+that|Notice\s+that|'
#     r'It\s+is\s+(?:easy|worth)\s+to\s+(?:see|note))\b'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
PROSE_REMARK_CUE_RE = re.compile(r'(?!x)x')  # PRUNED

# PRUNED — FP on 1102.4533v1, 1502.03482v2, 1708.00522v2 | also 1 TP — review before uncommenting
# PROSE_REF_REMARK_RE = re.compile(
#     r'(?m)^[ \t]*(?:From|By|Recall\s+that|As\s+in|Using)\b'
#     r'[^\n]*?\\(?:eq)?ref\{[^}]*\}[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
PROSE_REF_REMARK_RE = re.compile(r'(?!x)x')  # PRUNED

# PRUNED — FP on 1502.03482v2, 1512.05406v1 | also 1 TP — review before uncommenting
# PROSE_SPECIAL_CASE_RE = re.compile(
#     r'(?m)^[ \t]*[^\n]*?\b(?:special\s+(?:case|type|kind)\s+of)\b'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
PROSE_SPECIAL_CASE_RE = re.compile(r'(?!x)x')  # PRUNED

# PRUNED — FP on 1512.05406v1
# PROSE_ALIAS_RE = re.compile(
#     r'(?m)^[ \t]*[^\n]*?\b(?:also\s+known\s+as|can\s+also\s+be\s+seen\s+as)\b'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
PROSE_ALIAS_RE = re.compile(r'(?!x)x')  # PRUNED

# Generalization / analogue remarks in prose ("... is a generalization of ...").
# PRUNED — FP on 1712.00232v3 | also 1 TP — review before uncommenting
# PROSE_GENERALIZATION_RE = re.compile(
#     r'(?:^|(?<=[.!?]\s))'
#     r'([^.!?\n]*?\b(?:generalization|generalisation|analogue|analog|variant)\s+of\b[^.!?]*[.!?])'
# )
PROSE_GENERALIZATION_RE = re.compile(r'(?!x)x')  # PRUNED

# Comparative remarks: "compared to \ref{...} ..." / "in contrast to \ref{...}".
PROSE_COMPARE_RE = re.compile(
    r'(?m)^[ \t]*(?:Note\s+that\s+)?(?:compared\s+to|in\s+contrast\s+to|unlike)\b'
    r'[^\n]*?\\(?:eq)?ref\{[^}]*\}[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
    re.IGNORECASE,
)

# PRUNED — FP on 1102.4533v1, 1502.03482v2, 1503.04023v2 +3 more | also 3 TP — review before uncommenting
# PROSE_DISCOURSE_OPENER_RE = re.compile(
#     r'(?:^|(?<=[.!?]\s))'
#     r'((?:In\s+fact,|If,?\s+(?:for\s+example,\s+)?|Finally,\s+we\s+would\s+like\s+to\s+'
#     r'(?:remark|note|point\s+out)\s+that|we\s+would\s+like\s+to\s+(?:remark|note)\s+that|'
#     r'It\s+is\s+interesting\s+to)[^.!?]*[.!?])',
#     re.IGNORECASE,
# )
PROSE_DISCOURSE_OPENER_RE = re.compile(r'(?!x)x')  # PRUNED

# Consequence connectives in plain prose: "... is therefore ...".
PROSE_CONSEQUENCE_RE = re.compile(
    r'(?:^|(?<=[.!?]\s))([^.!?\n]*?\b(?:is|are)\s+therefore\b[^.!?]*[.!?])'
)

# Hedged / concluding remarks in plain prose (requires math in the paragraph).
# PRUNED — FP on 1510.04064v1, 1712.00232v3 | also 2 TP — review before uncommenting
# PROSE_HEDGE_RE = re.compile(
#     r'(?m)^[ \t]*[^\n]*?\b(?:unfortunately|does\s+not\s+seem|might\s+be\s+possible|'
#     r'it\s+is\s+not\s+clear)\b[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
PROSE_HEDGE_RE = re.compile(r'(?!x)x')  # PRUNED

# PRUNED — FP on 1102.4533v1, 1502.03482v2, 1708.00522v2 | also 4 TP — review before uncommenting
# PROSE_REMARK_LEAD_FALLBACK_RE = re.compile(
#     r'(?m)^[ \t]*(?:\\(?:textbf|emph|textit)\{)?\s*(?:Remark|Note)(?:\s+that|\s*[:.])?\b'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
PROSE_REMARK_LEAD_FALLBACK_RE = re.compile(r'(?!x)x')  # PRUNED

# Example-introducing lead-ins in prose: "For example", "For instance", "E.g.".
EXAMPLE_LEAD_RE = re.compile(
    r'(?m)^[ \t]*(?:For\s+(?:example|instance)|E\.g\.)(?=[\s,:])'
    r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
    re.IGNORECASE,
)

# Explanatory / intuition paragraphs ("To explain this ...", "Intuitively, ...", "This means ...").
EXPLAIN_LEAD_RE = re.compile(
    r'(?m)^[ \t]*(?:To\s+(?:explain|understand|see)\b|Intuitively\b|This\s+(?:means|suggests|shows)\b)'
    r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
    re.IGNORECASE,
)

# Unclaimed proof-step / commentary paragraphs containing math and a
# structural discourse cue ("main difficulty", "in order to prove", ...).
# PRUNED — FP on 1102.4533v1, 1502.03482v2, 1503.04023v2 +3 more | also 4 TP — review before uncommenting
# PROSE_PROOF_STEP_RE = re.compile(
#     r'(?m)^[ \t]*[^\n]*?\b(?:main\s+difficulty|in\s+order\s+to\s+prove|'
#     r'consider\s+the\s+following|we\s+may\s+use|attempt\s+to\s+show|'
#     r'it\s+is\s+therefore\s+sufficient|easy\s+consequence)\b'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
PROSE_PROOF_STEP_RE = re.compile(r'(?!x)x')  # PRUNED

# Plain-prose "we point out / we find / experiments show" observation paragraphs.
# PRUNED — FP on 1102.4533v1, 1204.5115v1, 1502.03482v2 +6 more | also 3 TP — review before uncommenting
# OBSERVATION_RE = re.compile(
#     r'(?m)^[ \t]*[^\n]*?\b(?:we\s+find|experiments?\s+(?:show|suggest)|we\s+observe|it\s+turns\s+out)\b'
#     r'[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*',
#     re.IGNORECASE,
# )
OBSERVATION_RE = re.compile(r'(?!x)x')  # PRUNED

# Standalone list-item remarks inside list-like environments (itemize / enumerate / compactitem).
# PRUNED — FP on 1502.03482v2, 1503.04023v2, 1510.04064v1 +4 more | also 17 TP — review before uncommenting
# LIST_ENV_ITEM_RE = re.compile(
#     r'\\begin\{(?P<env>itemize|enumerate|compactitem|compactenum)\}(?P<body>.*?)\\end\{(?P=env)\}',
#     re.DOTALL,
# )
LIST_ENV_ITEM_RE = re.compile(r'(?!x)x')  # PRUNED

_SUBTYPE_BY_WORD = {'remark': 'remark', 'example': 'example', 'assumption': 'assumption'}


def _subtype_from_word(word: str) -> str:
    return _SUBTYPE_BY_WORD.get(word.strip().rstrip('*').lower(), 'theorem')


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """True if [start, end) lies inside an environment the base parser owns."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _overlaps(span, taken) -> bool:
    s, e = span
    return any(s < te and ts < e for ts, te in taken)


_RULE_VAR_NAMES = {
    id(REMARK_ENV_RE): 'REMARK_ENV_RE',
    id(EXAMPLE_ENV_RE): 'EXAMPLE_ENV_RE',
    id(ASSUMPTION_ENV_RE): 'ASSUMPTION_ENV_RE',
    id(EMPH_LEAD_RE): 'EMPH_LEAD_RE',
    id(RUN_IN_REMARK_RE): 'RUN_IN_REMARK_RE',
    id(REMARK_SIGNAL_RE): 'REMARK_SIGNAL_RE',
    id(POST_ENV_REMARK_RE): 'POST_ENV_REMARK_RE',
    id(ASSUMPTION_LEAD_RE): 'ASSUMPTION_LEAD_RE',
    id(ASSUMPTION_SENT_RE): 'ASSUMPTION_SENT_RE',
    id(ATTRIBUTED_ASSUMPTION_RE): 'ATTRIBUTED_ASSUMPTION_RE',
    id(CONVENTION_SENT_RE): 'CONVENTION_SENT_RE',
    id(STANDING_OPENER_RE): 'STANDING_OPENER_RE',
    id(IMPOSE_SENT_RE): 'IMPOSE_SENT_RE',
    id(NORMALIZE_SENT_RE): 'NORMALIZE_SENT_RE',
    id(ASSUMPTION_SCOPE_RE): 'ASSUMPTION_SCOPE_RE',
    id(SCOPE_SENT_RE): 'SCOPE_SENT_RE',
    id(PROSE_GENERALIZATION_RE): 'PROSE_GENERALIZATION_RE',
    id(PROSE_CONSEQUENCE_RE): 'PROSE_CONSEQUENCE_RE',
    id(PROSE_COMPARE_RE): 'PROSE_COMPARE_RE',
    id(EXAMPLE_LEAD_RE): 'EXAMPLE_LEAD_RE',
    id(EXPLAIN_LEAD_RE): 'EXPLAIN_LEAD_RE',
    id(OBSERVATION_RE): 'OBSERVATION_RE',
    id(LIST_ENV_ITEM_RE): 'LIST_ENV_ITEM_RE',
}


def _rule_var_name(pattern) -> str:
    return _RULE_VAR_NAMES[id(pattern)]


def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []
    taken: List[tuple] = []

    def emit(raw: str, start: int, end: int, rule_name: str,
             subtype: str, name=None, require_math: bool = False) -> None:
        if _inside_excluded_env(text, start, end):
            return
        if _overlaps((start, end), taken):
            return
        raw = raw.strip()
        if not raw:
            return
        if require_math and '$' not in raw and '\\[' not in raw and '\\(' not in raw:
            return
        taken.append((start, end))
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw).strip(),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': subtype,
        })

    # 1. Environment-anchored blocks (highest precision).
    for pattern, word in (
        (REMARK_ENV_RE, 'remark'),
        (EXAMPLE_ENV_RE, 'example'),
        (ASSUMPTION_ENV_RE, 'assumption'),
    ):
        for m in pattern.finditer(text):
            emit(m.group(0), m.start(), m.end(),
                 _rule_var_name(pattern), _subtype_from_word(word))

    # 2. Bold/emph-led paragraphs.
    for m in EMPH_LEAD_RE.finditer(text):
        lead = m.group('lead')
        emit(m.group(0), m.start(), m.end(),
             _rule_var_name(EMPH_LEAD_RE), _subtype_from_word(lead))

    # 3. Run-in styled headings followed by prose (\textit{Topic.} body).
#     for m in RUN_IN_REMARK_RE.finditer(text):
#         emit(m.group(0), m.start(), m.end(),
#              _rule_var_name(RUN_IN_REMARK_RE), 'remark')

    pass  # PRUNED: body commented out
    # 4. Remark-signalling paragraph openers outside environments.
#     for m in REMARK_SIGNAL_RE.finditer(text):
#         emit(m.group(0), m.start(), m.end(),
#              _rule_var_name(REMARK_SIGNAL_RE), 'remark')

    pass  # PRUNED: body commented out
    # 5. Cue-led commentary directly after a proof / theorem-like environment.
    for m in POST_ENV_REMARK_RE.finditer(text):
        emit(m.group('body'), m.start('body'), m.end('body'),
             _rule_var_name(POST_ENV_REMARK_RE), 'remark')

    # 6. List-item remarks inside itemize/enumerate/compactitem blocks.
#     for lm in LIST_ENV_ITEM_RE.finditer(text):
#         body_start = lm.start('body')
#         body = lm.group('body')
#         pos = 0
#         parts = re.split(r'\\item\b', body)
#         for part in parts[1:]:
#             idx = body.find(part, pos)
#             s = body_start + idx
#             e = s + len(part)
#             emit(part, s, e, _rule_var_name(LIST_ENV_ITEM_RE), 'remark')
#             pos = idx + len(part)

    pass  # PRUNED: body commented out
    # 7. Assumption lead-ins and sentence-level assumption/convention statements.
    for m in ASSUMPTION_LEAD_RE.finditer(text):
        emit(m.group(0), m.start(), m.end(),
             _rule_var_name(ASSUMPTION_LEAD_RE), 'assumption')
    for m in ASSUMPTION_SENT_RE.finditer(text):
        emit(m.group(1), m.start(1), m.end(1),
             _rule_var_name(ASSUMPTION_SENT_RE), 'assumption')
    for m in ATTRIBUTED_ASSUMPTION_RE.finditer(text):
        emit(m.group(1), m.start(1), m.end(1),
             _rule_var_name(ATTRIBUTED_ASSUMPTION_RE), 'assumption')
    for m in CONVENTION_SENT_RE.finditer(text):
        emit(m.group(1), m.start(1), m.end(1),
             _rule_var_name(CONVENTION_SENT_RE), 'assumption')
    for m in STANDING_OPENER_RE.finditer(text):
        emit(m.group(0), m.start(), m.end(),
             _rule_var_name(STANDING_OPENER_RE), 'assumption', require_math=True)
    for m in IMPOSE_SENT_RE.finditer(text):
        emit(m.group(1), m.start(1), m.end(1),
             _rule_var_name(IMPOSE_SENT_RE), 'assumption')
    for m in NORMALIZE_SENT_RE.finditer(text):
        emit(m.group(1), m.start(1), m.end(1),
             _rule_var_name(NORMALIZE_SENT_RE), 'assumption')

    # 8. Scoping assumption paragraphs ("Throughout this section ...").
    for m in ASSUMPTION_SCOPE_RE.finditer(text):
        emit(m.group(0), m.start(), m.end(),
             _rule_var_name(ASSUMPTION_SCOPE_RE), 'assumption')
    for m in SCOPE_SENT_RE.finditer(text):
        emit(m.group(1), m.start(1), m.end(1),
             _rule_var_name(SCOPE_SENT_RE), 'assumption')

    # 9. Generalization / analogue sentences.
#     for m in PROSE_GENERALIZATION_RE.finditer(text):
#         emit(m.group(1), m.start(1), m.end(1),
#              _rule_var_name(PROSE_GENERALIZATION_RE), 'remark')

    pass  # PRUNED: body commented out
    # 10. Consequence sentences ("... is therefore ...").
    for m in PROSE_CONSEQUENCE_RE.finditer(text):
        emit(m.group(1), m.start(1), m.end(1),
             _rule_var_name(PROSE_CONSEQUENCE_RE), 'remark')

    # 11. Explanatory / intuition paragraphs.
    for m in EXPLAIN_LEAD_RE.finditer(text):
        emit(m.group(0), m.start(), m.end(),
             _rule_var_name(EXPLAIN_LEAD_RE), 'remark')

    # 12. Observation / experiment paragraphs (require math).
#     for m in OBSERVATION_RE.finditer(text):
#         emit(m.group(0), m.start(), m.end(),
#              _rule_var_name(OBSERVATION_RE), 'remark', require_math=True)

    pass  # PRUNED: body commented out
    # 13. Comparative remarks.
    for m in PROSE_COMPARE_RE.finditer(text):
        emit(m.group(0), m.start(), m.end(),
             _rule_var_name(PROSE_COMPARE_RE), 'remark')

    # 14. Example lead-ins in prose.
    for m in EXAMPLE_LEAD_RE.finditer(text):
        emit(m.group(0), m.start(), m.end(),
             _rule_var_name(EXAMPLE_LEAD_RE), 'example')

    return results
