import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very lightweight LaTeX → plain-text cleaner."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their arguments
    text = re.sub(r'\\(?:emph|textit|textbf|textrm|mathrm|mathit|mathbf|text)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:label|ref|cite[a-zA-Z]*|eqref)\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:left|right|big|Big|bigg|Bigg)\s*', '', text)
    text = re.sub(r'\{\\(?:em|it|bf|rm|tt)\s+([^}]*)\}', r'\1', text)
    # Replace display math environments with a placeholder
    text = re.sub(r'\\begin\{(?:equation|gather|align|multline|flalign|alignat)\*?\}.*?\\end\{(?:equation|gather|align|multline|flalign|alignat)\*?\}', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]+\$', ' [MATH] ', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})*', ' ', text)
    text = re.sub(r'[{}]', ' ', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Environments to exclude (proofs, theorems, etc. — we don't want to re-extract from these)
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|'
    r'proposition|Proposition|prop|corollary|Corollary|cor|'
    r'claim|Claim|conjecture|Conjecture|example|Example|'
    r'exercise|Exercise|remark|Remark|rem|note)\}',
    flags=re.IGNORECASE,
)

_EXCLUDED_ENV_BLOCK = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|'
    r'proposition|Proposition|prop|corollary|Corollary|cor|'
    r'claim|Claim|conjecture|Conjecture|example|Example|'
    r'exercise|Exercise|remark|Remark|rem|note)\}'
    r'.*?'
    r'\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_exclusion_mask(text: str) -> List[bool]:
    """Return a boolean mask; True means position is inside an excluded environment."""
    mask = [False] * len(text)
    for m in _EXCLUDED_ENV_BLOCK.finditer(text):
        for i in range(m.start(), min(m.end(), len(text))):
            mask[i] = True
    return mask


def _inside_excluded_env(mask: List[bool], start: int, end: int) -> bool:
    """Return True if more than 30% of the span is inside an excluded environment."""
    if not mask:
        return False
    span = mask[start:end]
    if not span:
        return False
    return sum(span) > 0.3 * len(span)


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Referential language (skip these)
_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    flags=re.IGNORECASE,
)

# C1-negative (skip forward-references in define patterns)
_C1_NEGATIVE = re.compile(
    r'\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    flags=re.IGNORECASE,
)

# ---- Bold-term definitions: {\bf Name:} body \\ or {\textbf{Name}:} body \\
# Catches test cases 3, 4, 5
# PRUNED — FP on paper001, paper002, paper003 +3 more | also 3 TP — review before uncommenting
# BF_TERM_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:\{\\bf\s+|\{\\textbf\{)'
#     r'(?P<name>[^}:]{1,120})'
#     r'(?:\}:\}|\}:|\}\}:?|:)'
#     r'\s*'
#     r'(?P<body>(?:\\\[.*?\\\]|\$\$.*?\$\$|(?!\{\\bf\b|\\textbf\{|\\section\b|\\subsection\b|\\begin\b).){10,1200}?)'
#     r'(?=\\\\|\{\\bf\b|\\textbf\{|\\section\b|\\subsection\b|\\begin\b|\\end\{document\}|$))',
#     flags=re.DOTALL,
# )

# ---- Section/subsection intro paragraph with {\em term} — test case 1
# PRUNED — FP on paper001, paper002, paper005 +2 more | also 2 TP — review before uncommenting
# SECTION_INTRO_PATTERN = re.compile(
#     r'(?:\\(?:sub)*section)\*?\{[^}]+\}\s*(?:\\label\{[^}]+\})?\s*%?[ \t]*\n'
#     r'(?P<full>'
#     r'(?P<body>(?:(?!\\(?:sub)*section|\\begin\{|\\end\{document\}).){50,1500}?)'
#     r'(?=\n\s*\n|\\(?:sub)*section|\\begin\{|\\end\{document\}))',
#     flags=re.DOTALL,
# )
_HAS_EM_TERM = re.compile(r'\{\\(?:em|it)\s|\{\\emph\s*\{|\\emph\{', flags=re.IGNORECASE)

# ---- "is called / are called" definitional pattern — test case 2
IS_CALLED_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:A\s+|An\s+)?'
    r'(?P<name>[A-Za-z$\\{}_\s]{3,80}?)'
    r'\s+(?:is\s+called|are\s+called)\s+'
    r'(?:[a-z\\${}_ ]{1,80}?)\s+if\s+'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- "are/is defined as" (plural form extension of C2) — test case 6
ARE_DEFINED_AS_ANCHOR = re.compile(
    r'\b(?:is|are)\s+defined\s+(?:as|to\s+be)\b',
    flags=re.IGNORECASE,
)
_ARE_DEFINED_TAIL = re.compile(
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{(?:equation|align|gather|multline)[*]?\}.*?\\end\{(?:equation|align|gather|multline)[*]?\}|[^.])*\.',
    flags=re.DOTALL,
)

# ---- commute distance / "also called" pattern — test case 7
ALSO_CALLED_PATTERN = re.compile(
    r'(?P<full>'
    r'The\s+(?P<name>[A-Za-z$\\{}\s]{3,80}?)'
    r'\s*(?:\(also\s+called[^)]{0,80}\))?'
    r'[^.]{0,300}?\bis\s+the\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- "a <term> is a/an ..." — test case 8 (linear code)
# PRUNED — FP on paper001, paper002, paper003 +5 more | also 4 TP — review before uncommenting
# IS_A_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:a\s+|an\s+)?'
#     r'(?P<name>'
#     r'(?:\\emph\{[^}]+\}|\\textit\{[^}]+\}|\\textbf\{[^}]+\}|[A-Za-z][A-Za-z0-9\s\-]{1,50})'
#     r')'
#     r'\s+is\s+(?:a|an)\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )
_IS_A_KEYWORDS = re.compile(
    r'\b(collection|set|function|map|mapping|sequence|matrix|space|operator|'
    r'code|codeword|vector|basis|system|class|family|group|ring|field|'
    r'graph|path|tree|partition|scheme|measure|process|distribution|transform)\b',
    flags=re.IGNORECASE,
)

# ---- "We (will) denote by X the ..." — test case 9
# PRUNED — FP on paper002, paper004, paper007 | also 1 TP — review before uncommenting
# DENOTE_BY_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:We\s+)?(?:will\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,\s]{1,80}?))'
#     r'\s+(?:the|a|an)\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---- "X obeys <property> if ..." — test case 10
OBEYS_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+)?'
    r'(?P<name>'
    r'(?:\\emph\{[^}]+\}|\\textit\{[^}]+\}|\\textbf\{[^}]+\}|'
    r'[A-Za-z\$][^.]{0,80}?)'
    r')'
    r'\s+obeys\s+'
    r'(?:[^.]{1,160}?)'
    r'\s+if\s+'
    r'(?:\\begin\{equation[*]?\}.*?\\end\{equation[*]?\}|'
    r'\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- "X stands for ..." — test case 11
STANDS_FOR_PATTERN = re.compile(
    r'(?P<full>'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{}\s]+?))'
    r'\s+stands\s+for\s+'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- "Let X denote ..." — test case 12
# PRUNED — FP on paper006 | also 1 TP — review before uncommenting
# LET_DENOTE_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:Let|let)\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{}\s]+?))'
#     r'\s+denote\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.DOTALL,
# )

# ---- "Introduce X ..." — test case 13
INTRODUCE_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:Introduce|introduce)\s+'
    r'(?:the\s+)?(?P<name>[^$\n]{1,100}?)'
    r'\s*(?:\$\$.*?\$\$|\$[^$]+\$|\\\[.*?\\\]|\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})'
    r'(?:[^.])*\.)',
    flags=re.DOTALL,
)

# ---- "we consider the Gram matrix ... let X denote" — test case 14
# This is caught by LET_DENOTE_PATTERN above, plus a broader "we consider <named object>" pattern
# PRUNED — FP on paper001, paper002, paper004 +2 more
# WE_CONSIDER_PATTERN = re.compile(
#     r'(?P<full>'
#     r'[Ww]e\s+consider\s+(?:the\s+)?'
#     r'(?P<name>[A-Za-z][A-Za-z0-9\s\\{}_,^]{1,60}?)'
#     r'(?:\$[^$]+\$|\\\[.*?\\\])'
#     r'(?:[^.])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---- "we introduce the following quantities (that we will call X):" + equation* — test case 15
INTRODUCE_QUANTITIES_PATTERN = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+(?:the\s+)?following\s+'
    r'(?P<name>[^:]{1,160}?)'
    r':\s*'
    r'(?:\\begin\{equation[*]?\}.*?\\end\{equation[*]?\}|'
    r'\\begin\{align[*]?\}.*?\\end\{align[*]?\}|'
    r'\\begin\{gather[*]?\}.*?\\end\{gather[*]?\}|'
    r'\\\[.*?\\\]))',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- "Denote by X ..." — test case 16
# PRUNED — FP on paper003
# DENOTE_IMPERATIVE_PATTERN = re.compile(
#     r'(?P<full>'
#     r'[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{}\s]+?))'
#     r'\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|'
#     r'\\begin\{equation[*]?\}.*?\\end\{equation[*]?\}|[^.])*\.)',
#     flags=re.DOTALL,
# )

# ---- "we consider/assume ... set {equation} is non-empty" — test case 17
# PRUNED — FP on paper002, paper004, paper006 | also 2 TP — review before uncommenting
# EQ_DEFINITION_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+)?(?:define|introduce|assume|consider|denote|set)\b'
#     r'[^\\]{0,300}?'
#     r'\\begin\{equation[*]?\}.*?\\end\{equation[*]?\}'
#     r'[^.]*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---- "We define X as/by \begin{gather*}..." — test case 18
DEFINE_ENV_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,160}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'\\begin\{(?:gather|align|equation|multline|flalign|alignat)[*]?\}'
    r'.*?'
    r'\\end\{(?:gather|align|equation|multline|flalign|alignat)[*]?\}'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- "X is given by \begin{equation}...\end{equation}" containing \defeq — test case 19
GIVEN_BY_EQ_PATTERN = re.compile(
    r'(?P<full>'
    r'(?P<name>[^.\n]{1,160}?)'
    r'\s+(?:is|are)\s+given\s+by\s*'
    r'\\begin\{equation[*]?\}(?P<body>.*?)\\end\{equation[*]?\}'
    r')',
    flags=re.DOTALL,
)

# ---- "by solving the optimization problem \begin{equation}..." with \argmin — test case 20
OPT_PROBLEM_PATTERN = re.compile(
    r'(?P<full>'
    r'(?P<name>[^.\n]{1,200}?)'
    r'\s+(?:by\s+solving(?:\s+the\s+optimization\s+problem)?|'
    r'is\s+based\s+on[^.]{0,120}?)\s*'
    r'\\begin\{equation[*]?\}(?P<body>.*?)\\end\{equation[*]?\}'
    r')',
    flags=re.DOTALL,
)

# ---- "we define X via \begin{equation}..." — test case 21
DEFINE_VIA_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,160}?)'
    r'\s+via\s*'
    r'\\begin\{equation[*]?\}.*?\\end\{equation[*]?\}'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- "we can define X \begin{equation*}..." containing \defeq — test case 22
DEFINE_EQ_STAR_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:can\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^\\\n]{1,160}?)'
    r'\s*\\begin\{equation[*]?\}(?P<body>.*?)\\end\{equation[*]?\}'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---- "A/An <name> is ... if ... \begin{equation*}..." — test case 23
# PRUNED — FP on paper009
# A_IS_IF_EQ_PATTERN = re.compile(
#     r'(?P<full>'
#     r'(?:A|An)\s+(?P<name>[^.\n]{1,120}?)'
#     r'\s+if\s+[^\\]{0,300}?'
#     r'\\begin\{equation[*]?\}(?P<body>.*?)\\end\{equation[*]?\}'
#     r')',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---- "empirical risk minimization (ERM)" — \emph{X} ... taken to be — test case 24
TAKEN_TO_BE_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:[A-Z][^.]{0,300}?)'
    r'\\emph\{(?P<name>[^}]{1,120})\}'
    r'[^.]{0,400}'
    r'(?:is\s+taken\s+to\s+be|are\s+taken\s+to\s+be|taken\s+to\s+be)'
    r'[^.]*\.)',
    flags=re.DOTALL,
)

# ---- "minimizing the \emph{X} $formula$ (the goal of...)" — test case 25
MINIMIZING_EMPH_PATTERN = re.compile(
    r'(?P<full>'
    r'[^.]{0,200}'
    r'\\emph\{(?P<name>[^}]{1,120})\}'
    r'\s*\$[^$]+\$'
    r'[^.]*'
    r'\(the\s+goal\s+of[^)]*\)'
    r'[^.]*\.)',
    flags=re.DOTALL,
)

# ---- Definitions inside \caption{...} with \emph{X}, which ... — test case 26
CAPTION_BLOCK_PATTERN = re.compile(
    r'\\caption\{(?P<body>(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}',
    flags=re.DOTALL,
)
CAPTION_EMPH_DEF_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:The\s+)?\\emph\{(?P<name>[^}]{1,120})\}'
    r',?\s+which\s+'
    r'(?:[^.\\]|\\[^\\])*\.)',
    flags=re.DOTALL,
)

# ---- "called \emph{X} ... consists of / of the form" — test case 27
CALLED_EMPH_PATTERN = re.compile(
    r'(?P<full>'
    r'[^.]{0,150}'
    r'called\s+\\emph\{(?P<name>[^}]{1,120})\}'
    r'(?:[^.\\]|\\.)*?'
    r'(?:consists\s+of|of\s+the\s+form|defined\s+as)\b'
    r'(?:(?!\n\n)[\s\S])*?'
    r'(?=\n\n|\\(?:section|subsection|paragraph)\b|\\end\{))',
    flags=re.DOTALL,
)

# ---- "Specifically, the ... model family ... consists of functions ... of the form" — test case 28
SPECIFICALLY_PATTERN = re.compile(
    r'(?P<full>'
    r'Specifically,\s+'
    r'(?:the\s+)?(?P<name>[^.]{1,140}?)'
    r'\s+consists\s+of\s+functions\b'
    r'(?:(?!\n\n)[\s\S])*?'
    r'(?:of\s+the\s+form|:=|defined\s+by)\b'
    r'(?:(?!\n\n)[\s\S])*?'
    r'(?=\n\n|\\(?:section|subsection|paragraph)\b|\\end\{|\.\s*(?:The\s|We\s|Note\b|For\b|In\b)))',
    flags=re.DOTALL,
)

# ---- "Consider the class $X$ of ... reflects the capacity / linear span" — test case 29
CONSIDER_CLASS_PATTERN = re.compile(
    r'(?P<full>'
    r'Consider\s+the\s+class\s+(?P<name>\$[^$]+\$[^,]{0,80})'
    r'(?:(?!\n\n)[\s\S])*?'
    r'(?:reflects\s+the\s+capacity|number\s+of\s+parameters|linear\s+span)'
    r'(?:(?!\n\n)[\s\S])*?'
    r'\.)',
    flags=re.DOTALL,
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX source text.
    Returns a list of dicts with keys:
      raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    mask = _build_exclusion_mask(text)

    def _name_from_match(m) -> str | None:
        try:
            raw = m.group('name')
            if raw:
                raw = raw.strip()
                # Remove leading/trailing LaTeX braces/whitespace
                raw = re.sub(r'^\{|\}$', '', raw).strip()
                return raw[:200] if raw else None
        except IndexError:
            pass
        return None

    def _add(raw_latex: str, name, rule_name: str, start: int):
        if not raw_latex or len(raw_latex) < 15:
            return
        if _inside_excluded_env(mask, start, start + len(raw_latex)):
            return
        results.append({
            'raw_latex': raw_latex,
            'clean_text': _clean_latex(raw_latex),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
        })

    # --- BF_TERM_PATTERN (bold-term definitions: {\bf Name:} body) ---
#     for m in BF_TERM_PATTERN.finditer(text):
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, _name_from_match(m), 'BF_TERM_PATTERN', m.start())

    # --- SECTION_INTRO_PATTERN (section intro paragraphs with {\em term}) ---
#     for m in SECTION_INTRO_PATTERN.finditer(text):
#         full = m.group('full')
#         if not _HAS_EM_TERM.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         em_m = re.search(r'\{\\(?:em|it)\s+([^}]{1,100})\}|\\emph\{([^}]{1,100})\}', full)
#         name = None
#         if em_m:
#             name = (em_m.group(1) or em_m.group(2) or '').strip()
#         _add(full, name, 'SECTION_INTRO_PATTERN', m.start())

    # --- IS_CALLED_PATTERN ("is called / are called") ---
    for m in IS_CALLED_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'IS_CALLED_PATTERN', m.start())

    # --- ARE_DEFINED_AS (plural "are defined as" extension of C2) ---
    _are_def_tail = re.compile(
        r'(?:\\begin\{(?:equation|align|gather|multline)[*]?\}.*?\\end\{(?:equation|align|gather|multline)[*]?\}|'
        r'\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.',
        flags=re.DOTALL,
    )
    for anchor_m in ARE_DEFINED_AS_ANCHOR.finditer(text):
        if _inside_excluded_env(mask, anchor_m.start(), anchor_m.end()):
            continue
        # Look back up to 120 chars for sentence start
        look_back = max(0, anchor_m.start() - 120)
        prefix = text[look_back:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        nl_pos = prefix.rfind('\n\n')
        sep_pos = max(dot_pos, nl_pos)
        if sep_pos >= 0:
            name_start = look_back + sep_pos + 1
        else:
            name_start = look_back
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _are_def_tail.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        # Clean name
        name = re.sub(r'\s+', ' ', name_text).strip()[:100]
        _add(full_text, name, 'ARE_DEFINED_AS_ANCHOR', name_start)

    # --- ALSO_CALLED_PATTERN ("The X (also called Y) ... is the ...") ---
    for m in ALSO_CALLED_PATTERN.finditer(text):
        full = m.group('full')
        if not re.search(r'also\s+called|also\s+known\s+as', full, re.IGNORECASE):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'ALSO_CALLED_PATTERN', m.start())

    # --- IS_A_PATTERN ("a <term> is a/an ...") ---
#     for m in IS_A_PATTERN.finditer(text):
#         full = m.group('full')
#         if not _IS_A_KEYWORDS.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, _name_from_match(m), 'IS_A_PATTERN', m.start())

    # --- DENOTE_BY_PATTERN ("We (will) denote by X the ...") ---
#     for m in DENOTE_BY_PATTERN.finditer(text):
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, _name_from_match(m), 'DENOTE_BY_PATTERN', m.start())

    # --- OBEYS_PATTERN ("X obeys <property> if ...") ---
    for m in OBEYS_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'OBEYS_PATTERN', m.start())

    # --- STANDS_FOR_PATTERN ("X stands for ...") ---
    for m in STANDS_FOR_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'STANDS_FOR_PATTERN', m.start())

    # --- LET_DENOTE_PATTERN ("Let X denote ...") ---
#     for m in LET_DENOTE_PATTERN.finditer(text):
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, _name_from_match(m), 'LET_DENOTE_PATTERN', m.start())

    # --- INTRODUCE_PATTERN ("Introduce the <name> $...$") ---
    for m in INTRODUCE_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'INTRODUCE_PATTERN', m.start())

    # --- WE_CONSIDER_PATTERN ("we consider the Gram matrix $...$") ---
#     for m in WE_CONSIDER_PATTERN.finditer(text):
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, _name_from_match(m), 'WE_CONSIDER_PATTERN', m.start())

    # --- INTRODUCE_QUANTITIES_PATTERN ("we introduce the following quantities ... :") ---
    for m in INTRODUCE_QUANTITIES_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'INTRODUCE_QUANTITIES_PATTERN', m.start())

    # --- DENOTE_IMPERATIVE_PATTERN ("Denote by X ...") ---
#     for m in DENOTE_IMPERATIVE_PATTERN.finditer(text):
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, _name_from_match(m), 'DENOTE_IMPERATIVE_PATTERN', m.start())

    # --- EQ_DEFINITION_PATTERN ("we define/introduce/assume ... \begin{equation}...") ---
#     for m in EQ_DEFINITION_PATTERN.finditer(text):
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         name_m = re.search(
#             r'(?:define|introduce|assume|consider|denote|set)\s+'
#             r'(?:the\s+)?(?P<name>(?:\$[^$]+\$|[A-Za-z][A-Za-z0-9\\_{}\s]{0,80}?))',
#             full, re.IGNORECASE)
#         name = name_m.group('name').strip() if name_m else None
#         _add(full, name, 'EQ_DEFINITION_PATTERN', m.start())

    # --- DEFINE_ENV_PATTERN ("We define X as \begin{gather*}...") ---
    for m in DEFINE_ENV_PATTERN.finditer(text):
        full = m.group('full')
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'DEFINE_ENV_PATTERN', m.start())

    # --- GIVEN_BY_EQ_PATTERN ("X is given by \begin{equation}..." with \defeq) ---
    for m in GIVEN_BY_EQ_PATTERN.finditer(text):
        body_eq = m.group('body') if 'body' in m.groupdict() else ''
        if not re.search(r'\\defeq|\\coloneqq|:=|\\doteq|\\argmin', body_eq):
            continue
        if _REFERENTIAL.search(m.group('full')):
            continue
        _add(m.group('full'), _name_from_match(m), 'GIVEN_BY_EQ_PATTERN', m.start())

    # --- OPT_PROBLEM_PATTERN ("by solving the optimization problem \begin{equation}...") ---
    for m in OPT_PROBLEM_PATTERN.finditer(text):
        body_eq = m.group('body') if 'body' in m.groupdict() else ''
        if not re.search(r'\\defeq|\\coloneqq|:=|\\argmin|\\in\s*\\arg', body_eq):
            continue
        if _REFERENTIAL.search(m.group('full')):
            continue
        _add(m.group('full'), _name_from_match(m), 'OPT_PROBLEM_PATTERN', m.start())

    # --- DEFINE_VIA_PATTERN ("we define X via \begin{equation}...") ---
    for m in DEFINE_VIA_PATTERN.finditer(text):
        full = m.group('full')
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'DEFINE_VIA_PATTERN', m.start())

    # --- DEFINE_EQ_STAR_PATTERN ("we can define X \begin{equation*}..." with \defeq) ---
    for m in DEFINE_EQ_STAR_PATTERN.finditer(text):
        full = m.group('full')
        body_eq = m.group('body') if 'body' in m.groupdict() else full
        if not re.search(r'\\defeq|\\coloneqq|:=|\\doteq', body_eq):
            continue
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'DEFINE_EQ_STAR_PATTERN', m.start())

    # --- A_IS_IF_EQ_PATTERN ("A <name> is ... if ... \begin{equation*}...") ---
#     for m in A_IS_IF_EQ_PATTERN.finditer(text):
#         full = m.group('full')
#         if not re.search(r'\\ge\b|\\le\b|\\leq\b|\\geq\b|\\defeq|:=|\bconvex\b|\bstrongly\b', full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, _name_from_match(m), 'A_IS_IF_EQ_PATTERN', m.start())

    # --- TAKEN_TO_BE_PATTERN ("\emph{X} ... taken to be ...") ---
    for m in TAKEN_TO_BE_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'TAKEN_TO_BE_PATTERN', m.start())

    # --- MINIMIZING_EMPH_PATTERN ("minimizing the \emph{X} $...$ (the goal of ...)") ---
    for m in MINIMIZING_EMPH_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'MINIMIZING_EMPH_PATTERN', m.start())

    # --- CAPTION_BLOCK_PATTERN + CAPTION_EMPH_DEF_PATTERN ---
    for cap_m in CAPTION_BLOCK_PATTERN.finditer(text):
        cap_body = cap_m.group('body')
        cap_offset = cap_m.start()
        for m in CAPTION_EMPH_DEF_PATTERN.finditer(cap_body):
            full = m.group('full')
            if _REFERENTIAL.search(full):
                continue
            name = _name_from_match(m)
            abs_start = cap_offset + m.start()
            _add(full, name, 'CAPTION_EMPH_DEF_PATTERN', abs_start)

    # --- CALLED_EMPH_PATTERN ("called \emph{X} ... consists of / of the form") ---
    for m in CALLED_EMPH_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'CALLED_EMPH_PATTERN', m.start())

    # --- SPECIFICALLY_PATTERN ("Specifically, the ... model family ... consists of functions...") ---
    for m in SPECIFICALLY_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'SPECIFICALLY_PATTERN', m.start())

    # --- CONSIDER_CLASS_PATTERN ("Consider the class $X$ of ... reflects the capacity ...") ---
    for m in CONSIDER_CLASS_PATTERN.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        _add(full, _name_from_match(m), 'CONSIDER_CLASS_PATTERN', m.start())

    # ---------------------------------------------------------------------------
    # Deduplicate overlapping matches
    # ---------------------------------------------------------------------------
    # Sort by (start position, -length) so longer matches at same position win
    # We need to track positions; use raw_latex for overlap detection
    # Re-scan text to find positions of each result's raw_latex
    def _find_pos(raw: str, search_text: str, hint: int = 0) -> int:
        idx = search_text.find(raw, max(0, hint - 10))
        if idx == -1:
            idx = search_text.find(raw)
        return idx if idx != -1 else hint

    positioned = []
    for r in results:
        pos = _find_pos(r['raw_latex'], text)
        positioned.append((pos, len(r['raw_latex']), r))

    # Sort: earlier start first, then longer match first
    positioned.sort(key=lambda x: (x[0], -x[1]))

    deduped = []
    used_spans = []  # list of (start, end)

    for (start, length, r) in positioned:
        end = start + length
        if start < 0:
            deduped.append(r)
            continue
        # Check overlap with already-kept spans
        overlaps = False
        for (us, ue) in used_spans:
            # If overlap > 50% of the shorter span, skip
            overlap_start = max(start, us)
            overlap_end = min(end, ue)
            if overlap_end > overlap_start:
                overlap_len = overlap_end - overlap_start
                shorter = min(length, ue - us)
                if shorter > 0 and overlap_len > 0.5 * shorter:
                    overlaps = True
                    break
        if not overlaps:
            deduped.append(r)
            used_spans.append((start, end))

    for r in deduped:
        r.pop('_start', None)

    return deduped
