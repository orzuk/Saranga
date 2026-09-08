import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX → plain-text cleaner."""
    t = text
    # Remove comments
    t = re.sub(r'%[^\n]*', '', t)
    # \emph{X} → X, \textbf{X} → X, etc.
    for cmd in ('emph', 'textbf', 'textit', 'textrm', 'mathrm',
                'mathbf', 'mathit', 'text', 'mbox', 'hbox'):
        t = re.sub(r'\\' + cmd + r'\{([^}]*)\}', r'\1', t)
    # {\em X} {\bf X} etc.
    t = re.sub(r'\{\\(?:em|bf|it|rm|tt)\s+([^}]*)\}', r'\1', t)
    # \label{...} \ref{...} \cite{...} → ''
    t = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', t)
    # sectioning
    t = re.sub(r'\\(?:sub)*section\*?\{([^}]*)\}', r'\1', t)
    # Display math environments → [MATH]
    t = re.sub(r'\\begin\{(?:equation|align|gather|multline)[*]?\}.*?'
               r'\\end\{(?:equation|align|gather|multline)[*]?\}',
               ' [MATH] ', t, flags=re.DOTALL)
    t = re.sub(r'\$\$.*?\$\$', ' [MATH] ', t, flags=re.DOTALL)
    t = re.sub(r'\\\[.*?\\\]', ' [MATH] ', t, flags=re.DOTALL)
    # inline math
    t = re.sub(r'\$[^$]+\$', '[MATH]', t)
    # remaining braces / backslash commands
    t = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', t)
    t = re.sub(r'[{}]', '', t)
    # whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t


# Environments to exclude (definitions found inside these are likely spurious)
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|theorem|lemma|proposition|corollary|claim|'
    r'conjecture|problem|algorithm|algorithmic|verbatim|lstlisting|minted)\}',
    re.IGNORECASE,
)

def _build_exclusion_spans(text: str):
    """Return list of (start, end) intervals that are inside excluded environments."""
    spans = []
    env_pat = re.compile(
        r'\\begin\{(proof|theorem|lemma|proposition|corollary|claim|'
        r'conjecture|problem|algorithm|algorithmic|verbatim|lstlisting|minted)\}'
        r'.*?'
        r'\\end\{\1\}',
        re.DOTALL | re.IGNORECASE,
    )
    for m in env_pat.finditer(text):
        spans.append((m.start(), m.end()))
    return spans


def _inside_excluded_env(spans, start: int, end: int) -> bool:
    for s, e in spans:
        if s <= start and end <= e:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Negative / referential guards (reused across rules)
_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    re.IGNORECASE,
)

_C1_NEGATIVE = re.compile(
    r'\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    re.IGNORECASE,
)

# Sentence-boundary finder (for look-back heuristics)
_SENT_BOUNDARY = re.compile(r'[.!?]\s+|\n\s*\n', re.DOTALL)

# Structural cut markers for look-back
_STRUCTURAL_CUTS = (
    "\n\n", "\\section", "\\subsection", "\\maketitle",
    "\\begin", "\\end", "\\item", "\\State", "\\par",
)

# Tail: rest of sentence after an anchor
_TAIL = re.compile(r'(?:[^.]|\\\[.*?\\\]|\$\$.*?\$\$)*\.', re.DOTALL)

# ---------- R01: {\bf Term:} or {\bf Term} introductory paragraph ----------
# PRUNED — FP on paper001, paper002, paper003 +7 more | also 4 TP — review before uncommenting
# R01_BF_TERM = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}:]{1,100}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,800}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     re.DOTALL,
# )

# ---------- R02: \textbf{Term:} or \textbf{Term} paragraph ----------------
# PRUNED — FP on paper002, paper003, paper004 +6 more
# R02_TEXTBF_TERM = re.compile(
#     r'(?P<full>'
#     r'\\textbf\{(?P<name>[^}:]{1,100}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\\textbf\{).){10,800}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     re.DOTALL,
# )

# ---------- R03: \noindent{\bf Name.}~ definitional paragraph --------------
R03_NOINDENT_BF = re.compile(
    r'(?P<full>'
    r'\\noindent\s*\{\\(?:bf|textbf)\s*\{(?P<name>[^}]{1,80})\}\}\s*[~]?\s*'
    r'(?P<body>(?:[^\n]|\n(?!\s*\n)){20,800})'
    r')',
    re.DOTALL,
)

# ---------- R04: \noindent\textbf{Name.}~ definitional paragraph -----------
# PRUNED — FP on paper008
# R04_NOINDENT_TEXTBF = re.compile(
#     r'(?P<full>'
#     r'\\noindent\s*\\textbf\{(?P<name>[^}]{1,80})\}\s*[~.]?\s*'
#     r'(?P<body>(?:[^\n]|\n(?!\s*\n)){20,800})'
#     r')',
#     re.DOTALL,
# )

# ---------- R05: 'we write X for Y, namely ...' ----------------------------
R05_WE_WRITE = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9_\\(),.\s]{1,60}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin|\\section|\\subsection).){1,300}?'
    r'\bnamely\b'
    r'(?:(?!\\begin|\\section|\\subsection).){0,600}?\.)',
    re.IGNORECASE | re.DOTALL,
)

# ---------- R06: 'Let X denote ...' ----------------------------------------
# PRUNED — FP on paper006, paper008, paper013 +1 more | also 1 TP — review before uncommenting
# R06_LET_DENOTE = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.()+*-]{1,80}?))'
#     r'\s+denote\s+'
#     r'(?:the\s+|a\s+|an\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     re.DOTALL,
# )

# ---------- R07: 'We (will) denote by X ...' -------------------------------
# PRUNED — FP on paper002, paper003, paper004 +1 more | also 2 TP — review before uncommenting
# R07_DENOTE_BY = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:will\s+)?|[Ll]et\s+us\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.()]+?))'
#     r'\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     re.DOTALL,
# )

# ---------- R08: 'X stands for / refers to ...' ----------------------------
# PRUNED — FP on paper004, paper005
# R08_STANDS_FOR = re.compile(
#     r'(?P<full>'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{}\|\| ,.()*+-]{1,80}?))'
#     r'\s+(?:stands\s+for|refers\s+to)\s+'
#     r'(?:the\s+|a\s+|an\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     re.IGNORECASE | re.DOTALL,
# )

# ---------- R09: 'Introduce ...' / 'Set ...' imperative at sentence start --
R09_IMPERATIVE = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=[.\n]))\s*'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^\n.]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    re.DOTALL | re.MULTILINE,
)

# ---------- R10: 'We introduce ... call ... :' + equation block ------------
R10_INTRODUCE_CALL = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?(?:call|denote)\b'
    r'[^:]{0,120}?:'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)[*]?\}.*?'
    r'\\end\{(?:equation|align|gather|multline)[*]?\}'
    r'|\s*\$\$.*?\$\$|\s*\\\[.*?\\\]))',
    re.DOTALL,
)

# ---------- R11: '(also called X)' or '(known as X)' parenthetical --------
# PRUNED — FP on paper001, paper010, paper014 | also 1 TP — review before uncommenting
# R11_ALSO_CALLED = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.]{0,120}?'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,300}?\.)',
#     re.DOTALL,
# )

# ---------- R12: '\emph{X}; ... is/are ...' (emph + semicolon definition) --
R12_EMPH_SEMI = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,120}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.]{0,300}\.)',
    re.IGNORECASE | re.DOTALL,
)

# ---------- R13: 'are defined as' (plural C2 extension) -------------------
# PRUNED — FP on paper016
# R13_ARE_DEFINED_AS = re.compile(
#     r'\bare\s+defined\s+(?:as|to\s+be)\s',
#     re.IGNORECASE,
# )

# ---------- R14: 'X obeys/satisfies ... if ...' with emph term -------------
R14_OBEYS_IF = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.]{0,120}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'[^.]{0,600}?'
    r'\bif\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    re.IGNORECASE | re.DOTALL,
)

# ---------- R15: 'is called the/a \emph{Name}' passive naming pattern ------
# PRUNED — FP on paper006, paper007, paper013 | also 1 TP — review before uncommenting
# R15_IS_CALLED_EMPH = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.]{0,200}?'
#     r'(?:is\s+called|called)\s+(?:the\s+|a\s+|an\s+)?'
#     r'(?:\\emph\{|\\textit\{|\\textbf\{)\s*'
#     r'(?P<name>[^}]{1,80})'
#     r'\}'
#     r'[^.]{0,300}?\.)',
#     re.DOTALL,
# )

# ---------- R16: 'called a \emph{Name}' with definitional keyword ----------
R16_CALLED_EMPH_DEF = re.compile(
    r'(?P<full>'
    r'[A-Z][^.\n]{0,300}?'
    r'(?:called|known\s+as)\s+'
    r'(?:\\emph\{|\\textit\{|\\textbf\{)'
    r'(?P<name>[^}]{1,80})'
    r'\}'
    r'[^.\n]{0,300}?\.)',
    re.DOTALL,
)

_R16_DEF_KW = re.compile(
    r'\b(defined?\s+(?:by|via|as|through)|denoted?\s+by|given\s+by|'
    r'equation|ODE|PDE|map|operator|density|distribution|function|path|field|'
    r'set|sequence|space|matrix|vector|kernel|norm|measure|process)\b',
    re.IGNORECASE,
)

# ---------- R17: 'The \emph{X} is \emph{property} if ...' -----------------
R17_EMPH_IF = re.compile(
    r'(?P<full>'
    r'[A-Z][^.]{0,120}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'[^.]{0,200}?'
    r'\b(?:if|when|provided|whenever)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    re.IGNORECASE | re.DOTALL,
)

# ---------- R18: '\emph{Term} (ABBREV)' + display math --------------------
R18_EMPH_DISPLAY = re.compile(
    r'(?P<full>'
    r'[^\n.]{0,150}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'(?:\s*\([A-Z][A-Za-z0-9*]{0,10}\))?'
    r'\s*'
    r'(?:'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:align|equation|gather|multline)[*]?\}.*?'
    r'\\end\{(?:align|equation|gather|multline)[*]?\}'
    r'))',
    re.DOTALL,
)

# ---------- R19: 'is given by' / 'is defined by' + equation block ---------
# PRUNED — FP on paper002, paper004, paper013 | also 2 TP — review before uncommenting
# R19_IS_GIVEN_BY = re.compile(
#     r'(?P<preamble>[^.\n]{0,300}?\b(?:is\s+given|is\s+defined)\s+by\s*)'
#     r'(?P<body>\\begin\{(?:equation|align|gather|multline)[*]?\}'
#     r'.*?'
#     r'\\end\{(?:equation|align|gather|multline)[*]?\})',
#     re.DOTALL,
# )

# ---------- R20: 'we (can) introduce X as $$...$$' -------------------------
R20_INTRODUCE_AS = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.]{1,80}?)'
    r'\s+as\s+'
    r'(?:[^$]|\$(?!\$))*?'
    r'(?P<math>\$\$.*?\$\$)'
    r'(?:[^.]*\.)?)',
    re.IGNORECASE | re.DOTALL,
)

# ---------- R21: 'we define X as/by/= \begin{equation}...' ----------------
R21_DEFINE_EQN = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,120}?)'
    r'\s*(?:as|by|to\s+be|:=|=|via)\s*'
    r'(?:\\begin\{(?:equation|align|gather|multline)[*]?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline)[*]?\}))',
    re.IGNORECASE | re.DOTALL,
)

# ---------- R22: 'define X \begin{equation}' (no connector) ---------------
R22_DEFINE_DIRECT_EQN = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+(?:can\s+)?)?define\s+'
    r'(?P<name>(?:the\s+)?[A-Za-z][^\\\n]{2,100}?)'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)[*]?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline)[*]?\}))',
    re.IGNORECASE | re.DOTALL,
)

# ---------- R23: 'A/An X is [property] if ...' + equation block -----------
R23_IS_IF_EQN = re.compile(
    r'(?P<full>'
    r'(?:A|An)\s+'
    r'(?P<name>[A-Za-z][^.\n]{2,100}?)\s+is\s+[^.\n]{2,120}?\s+if\s+'
    r'[^.\n]{0,200}?'
    r'(?:\\begin\{(?:equation|align|gather|multline)[*]?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline)[*]?\}))',
    re.DOTALL,
)

# ---------- R24: 'Consider ... :' + display equation with := / \defeq -----
R24_CONSIDER_EQN = re.compile(
    r'(?P<full>'
    r'Consider\s+'
    r'(?P<name>[^.\n]{5,120}?)'
    r'(?::|(?:following|below|as\s+follows)\s*:)\s*'
    r'\\begin\{(?:equation|equation\*|align|align\*|gather|gather\*)\}'
    r'.*?'
    r'\\end\{(?:equation|equation\*|align|align\*|gather|gather\*)\}'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# ---------- R25: 'we define X as follows / the following ...' + display ---
R25_DEFINE_DISPLAY = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\n]{2,100}?)'
    r'(?:\.\s*|\s*(?:as\s+follows|below|following)\s*[.:]?\s*|:\s*)'
    r'\\begin\{(?:align|align\*|equation|equation\*|gather|gather\*|'
    r'multline|multline\*)\}'
    r'.*?'
    r'\\end\{(?:align|align\*|equation|equation\*|gather|gather\*|'
    r'multline|multline\*)\}'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# ---------- R26: Colon-introduced display math after definitional verb -----
# PRUNED — FP on paper013, paper014, paper016 | also 4 TP — review before uncommenting
# R26_COLON_DISPLAY = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^\n]{0,300}?'
#     r'\b(?:define|denote|set|let|given\s+by|equal\s+to|as\s+follows)\b'
#     r'[^\n]{0,200}?:\s*\n?'
#     r'(?P<mathblock>'
#     r'\\begin\{(?:align|equation|gather|multline)[*]?\}'
#     r'(?:.*?\\begin\{split\}.*?\\end\{split\}.*?|.*?)'
#     r'\\end\{(?:align|equation|gather|multline)[*]?\}'
#     r')'
#     r'(?:\s*where\s[^\n]{0,300}\.)?'
#     r')',
#     re.IGNORECASE | re.DOTALL,
# )

# ---------- R27: 'The <noun> is\n$$...$$' or 'Given ..., the <noun> is ...' -
# PRUNED — FP on paper013
# R27_NOUN_DISPLAY = re.compile(
#     r'(?P<full>'
#     r'(?:Given[^,]{0,100},\s*)?'
#     r'(?:the|The)\s+'
#     r'(?P<name>[A-Za-z][^$\\]{1,60}?)'
#     r'\s+is(?:\s+(?:given\s+by|defined\s+as|defined\s+by))?\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline)[*]?\}'
#     r'.*?'
#     r'\\end\{(?:align|equation|gather|multline)[*]?\}'
#     r')'
#     r')',
#     re.DOTALL,
# )

_R27_EXCLUDE_NAMES = re.compile(
    r'^(?:following|above|below|result|fact|situation|case|latter|former)$',
    re.IGNORECASE,
)

# ---------- R28: display math + 'where ...' clause definitional block ------
# PRUNED — FP on paper004, paper006, paper009 +4 more | also 4 TP — review before uncommenting
# R28_DISPLAY_WHERE = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,200}?'
#     r'(?P<name>'
#     r'(?:the\s+)?[a-z][a-z\s]{2,50}?'
#     r'(?:norm|measure|metric|distance|kernel|cost|function|map|operator|'
#     r'space|matrix|bound|rate|set|distribution|divergence|energy|loss)'
#     r')'
#     r'[^$\\]{0,30}?'
#     r'[:\s]'
#     r'\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline)[*]?\}.*?'
#     r'\\end\{(?:align|equation|gather|multline)[*]?\}'
#     r')'
#     r'[^.]{0,300}?'
#     r'\bwhere\b'
#     r'[^.]{0,200}?\.)',
#     re.DOTALL,
# )

# ---------- R29: 'is called' look-back/look-ahead (like C2 but for naming) -
R29_IS_CALLED_ANCHOR = re.compile(
    r'\bis\s+called\s+(?:the\s+|a\s+|an\s+)?',
    re.IGNORECASE,
)

# ---------- R30: 'we (will) refer to X as Y' naming pattern ---------------
# PRUNED — FP on paper003, paper004, paper015 | also 1 TP — review before uncommenting
# R30_REFER_TO = re.compile(
#     r'(?P<full>'
#     r'[Ww]e\s+(?:will\s+)?(?:also\s+|therefore\s+|henceforth\s+|hereby\s+)?'
#     r'refer\s+to\s+'
#     r'(?P<name>[^.]{1,100}?)'
#     r'\s+as\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*.)',
#     re.DOTALL,
# )

# ---------- R31: 'Let us introduce a/an/the <name>' -----------------------
R31_LET_US_INTRODUCE = re.compile(
    r'(?P<full>'
    r'[Ll]et\s+us\s+introduce\s+(?:a\s+|an\s+|the\s+)?'
    r'(?P<name>[^.:]{1,80}?)'
    r'(?::\s*|\s+)'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    re.DOTALL,
)

# ---------- R32: 'of the form \begin{equation}' ---------------------------
R32_OF_THE_FORM = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:consider|study|adopt|define|use|introduce|propose|set)\s+'
    r'(?P<name>[^.\n]{1,100}?)'
    r'\s+of\s+the\s+form\b'
    r'(?:[^.]{0,600}?\.))',
    re.IGNORECASE | re.DOTALL,
)

_R32_DISPLAY = re.compile(
    r'\\begin\{(?:equation|align|gather|multline|eqnarray)[*]?\}'
    r'|\\\[',
    re.DOTALL,
)

# ---------- R33: '<Name> computes/defines the following ...: \begin{eq}' --
R33_COMPUTES_FOLLOWING = re.compile(
    r'(?P<full>'
    r'(?P<name>[A-Z][A-Za-z0-9 \\{}\'"`.,()\-]{2,80}?)'
    r'\s+(?:computes?|defines?|produces?|involves?|performs?|applies?)\s+'
    r'(?:the\s+following|a\s+(?:following)?)'
    r'[^.\n]{0,120}?'
    r'(?::|[.])\s*'
    r'\\begin\{(?:equation|equation\*|align|align\*|gather|gather\*)\}'
    r'.*?'
    r'\\end\{(?:equation|equation\*|align|align\*|gather|gather\*)\}'
    r'[^.]{0,300}?\.)',
    re.DOTALL,
)

# ---------- R34: '<Name> involves/computes <desc>:' + display eq ----------
# PRUNED — FP on paper013
# R34_COMPUTES_DIRECT = re.compile(
#     r'(?P<full>'
#     r'(?P<name>[A-Z][A-Za-z0-9 \\{}\'"`.,()\-]{2,80}?)'
#     r'\s+(?:computes?|defines?|produces?|involves?|performs?|applies?|'
#     r'consists?\s+of)'
#     r'[^\n]{5,200}?'
#     r':\s*'
#     r'\\begin\{(?:equation|equation\*|align|align\*|gather|gather\*)\}'
#     r'.*?'
#     r'\\end\{(?:equation|equation\*|align|align\*|gather|gather\*)\}'
#     r'[^.]{0,400}?\.)',
#     re.DOTALL,
# )

# ---------- R35: 'is called \emph{X} ... and is defined ...' --------------
R35_CALLED_DEFINED = re.compile(
    r'(?P<full>'
    r'(?:is\s+called\s+(?:the\s+)?|called\s+(?:the\s+)?)'
    r'(?:\\emph\{|\\textbf\{|\\textit\{)?'
    r'(?P<name>[^},]{1,80}?)'
    r'(?:}\s*)?'
    r'[^.]{0,300}?'
    r'(?:is\s+defined\s+as|it\s+is\s+defined|defined\s+to\s+be|:=)'
    r'(?:[^.]*(?:\\begin\{(?:align|equation|gather)[*]?\}.*?'
    r'\\end\{(?:align|equation|gather)[*]?\}|\$\$.*?\$\$|\\\[.*?\\\]))*'
    r'[^.]*\.)',
    re.IGNORECASE | re.DOTALL,
)

# ---------- R36: 'are defined as' plural anchor (two-phase) ---------------
# (handled in the function body like C2)

# ---------- R37: 'we consider X and let Y denote ...' --------------------
R37_CONSIDER_LET_DENOTE = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+consider\s+'
    r'(?P<name>[^.]{1,80}?)'
    r'\s*(?:\.{3}|,|\s)\s*'
    r'(?:and\s+)?let\s+[^.]{1,80}?\s+denote\s+'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    re.DOTALL,
)

# ---------- R38: 'X is a sequence-to-sequence function ...' is-a paragraph -
# PRUNED — FP on paper009, paper013 | also 1 TP — review before uncommenting
# R38_IS_A_DISPLAY = re.compile(
#     r'(?P<full>'
#     r'(?:^|\n\n)'
#     r'(?P<name>[A-Z][A-Za-z0-9 \\{}\'"`.,()\-]{2,80}?)'
#     r'\s+is\s+(?:a|an)\s+'
#     r'(?:(?!\\begin\{(?:proof|theorem|lemma|proposition|corollary))'
#     r'(?:[^{}]|\{[^{}]*\})){10,600}?'
#     r'\\begin\{(?:align|equation|align\*|equation\*|gather|gather\*|'
#     r'multline|multline\*)\}'
#     r'.*?'
#     r'\\end\{(?:align|equation|align\*|equation\*|gather|gather\*|'
#     r'multline|multline\*)\}'
#     r'[^.]*\.?)',
#     re.DOTALL | re.MULTILINE,
# )

# ---------- R39: 'by solving / based on / via' + equation block ------------
R39_BY_SOLVING = re.compile(
    r'(?P<preamble>[^.]{0,300}?\b(?:by\s+solving|estimating[^.]{0,60}?by|'
    r'based\s+on[^.]{0,60}?by|via)\s*)'
    r'(?P<body>\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _dedup(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex substantially overlaps a previous result."""
    kept = []
    seen_spans = []  # list of (start, end) character spans keyed by source_pos
    for r in results:
        pos = r.get('_source_pos', 0)
        length = len(r.get('raw_latex', ''))
        end = pos + length
        # Check overlap with already kept items
        overlapping = False
        for (s, e) in seen_spans:
            overlap_start = max(pos, s)
            overlap_end = min(end, e)
            if overlap_end > overlap_start:
                overlap_len = overlap_end - overlap_start
                min_len = min(length, e - s)
                if min_len > 0 and overlap_len / min_len > 0.5:
                    overlapping = True
                    break
        if not overlapping:
            kept.append(r)
            seen_spans.append((pos, end))
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX source that are NOT already
    caught by the base _extract_definitions_manual method.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    excl_spans = _build_exclusion_spans(text)

    def _make_result(raw: str, name, rule_name: str, source_pos: int) -> dict:
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name.strip() if name else None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_source_pos': source_pos,
        }

    def _extract_name(raw: str) -> str:
        raw = raw.strip()
        # prefer inline math
        m = re.search(r'\$(.+?)\$', raw)
        if m:
            return _clean_latex(m.group(1))[:80]
        return _clean_latex(raw)[:80]

    # ------------------------------------------------------------------
    # R01: {\bf Term:} paragraph
#     # ------------------------------------------------------------------
#     for m in R01_BF_TERM.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         if len(full.strip()) < 20:
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R01_BF_TERM', m.start()))

    # ------------------------------------------------------------------
    # R02: \textbf{Term:} paragraph
#     # ------------------------------------------------------------------
#     for m in R02_TEXTBF_TERM.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         if len(full.strip()) < 20:
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R02_TEXTBF_TERM', m.start()))

    # ------------------------------------------------------------------
    # R03: \noindent{\bf Name.}~ paragraph
    # ------------------------------------------------------------------
    for m in R03_NOINDENT_BF.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        name = name.rstrip('.').strip()
        if _REFERENTIAL.search(full):
            continue
        if len(full.strip()) < 30:
            continue
        results.append(_make_result(full, _extract_name(name), 'R03_NOINDENT_BF', m.start()))

    # ------------------------------------------------------------------
    # R04: \noindent\textbf{Name.}~ paragraph
#     # ------------------------------------------------------------------
#     for m in R04_NOINDENT_TEXTBF.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         name = name.rstrip('.').strip()
#         if _REFERENTIAL.search(full):
#             continue
#         if len(full.strip()) < 30:
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R04_NOINDENT_TEXTBF', m.start()))

    # ------------------------------------------------------------------
    # R05: 'we write X for Y, namely ...'
    # ------------------------------------------------------------------
    for m in R05_WE_WRITE.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R05_WE_WRITE', m.start()))

    # ------------------------------------------------------------------
    # R06: 'Let X denote ...'
#     # ------------------------------------------------------------------
#     for m in R06_LET_DENOTE.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R06_LET_DENOTE', m.start()))

    # ------------------------------------------------------------------
    # R07: 'Denote by X ...' / 'We denote by X ...'
#     # ------------------------------------------------------------------
#     for m in R07_DENOTE_BY.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R07_DENOTE_BY', m.start()))

    # ------------------------------------------------------------------
    # R08: 'X stands for / refers to ...'
#     # ------------------------------------------------------------------
#     for m in R08_STANDS_FOR.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R08_STANDS_FOR', m.start()))

    # ------------------------------------------------------------------
    # R09: 'Introduce ...' / 'Set ...' imperative
    # ------------------------------------------------------------------
    for m in R09_IMPERATIVE.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full').strip()
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R09_IMPERATIVE', m.start()))

    # ------------------------------------------------------------------
    # R10: 'We introduce ... call ... :'
    # ------------------------------------------------------------------
    for m in R10_INTRODUCE_CALL.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R10_INTRODUCE_CALL', m.start()))

    # ------------------------------------------------------------------
    # R11: '(also called X)' parenthetical
#     # ------------------------------------------------------------------
#     for m in R11_ALSO_CALLED.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if not name.strip() or len(name.strip()) < 2:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R11_ALSO_CALLED', m.start()))

    # ------------------------------------------------------------------
    # R12: '\emph{X}; ... is/are ...'
    # ------------------------------------------------------------------
    for m in R12_EMPH_SEMI.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or m.group('name2') or ''
        semi_pos = full.find(';')
        if semi_pos < 0:
            continue
        after_semi = full[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R12_EMPH_SEMI', m.start()))

    # ------------------------------------------------------------------
    # R13: 'are defined as' plural two-phase (like C2)
    # ------------------------------------------------------------------
    _tail_re = re.compile(r'(?:[^.]|\\\[.*?\\\]|\$\$.*?\$\$)*\.', re.DOTALL)
#     for anchor_m in R13_ARE_DEFINED_AS.finditer(text):
#         if _inside_excluded_env(excl_spans, anchor_m.start(), anchor_m.end()):
#             continue
#         start_search = max(0, anchor_m.start() - 80)
#         prefix = text[start_search:anchor_m.start()]
#         cuts = [prefix.rfind('.')]
#         for mk in _STRUCTURAL_CUTS:
#             p = prefix.rfind(mk)
#             if p >= 0:
#                 cuts.append(p + len(mk) - 1)
#         best = max(cuts)
#         name_start = start_search + (best + 1 if best >= 0 else 0)
#         name_text = text[name_start:anchor_m.start()].strip()
#         if not name_text or len(name_text) > 80:
#             continue
#         tail_m = _tail_re.match(text, anchor_m.end())
#         if not tail_m:
#             continue
#         full = text[name_start:tail_m.end()]
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name_text), 'R13_ARE_DEFINED_AS', name_start))

    # ------------------------------------------------------------------
    # R14: '\emph{X} obeys/satisfies ... if ...'
    # ------------------------------------------------------------------
    for m in R14_OBEYS_IF.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or m.group('name2') or ''
        if not name.strip():
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R14_OBEYS_IF', m.start()))

    # ------------------------------------------------------------------
    # R15: 'is called the/a \emph{Name}' passive naming
#     # ------------------------------------------------------------------
#     for m in R15_IS_CALLED_EMPH.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R15_IS_CALLED_EMPH', m.start()))

    # ------------------------------------------------------------------
    # R16: 'called a \emph{Name}' with definitional keyword
    # ------------------------------------------------------------------
    for m in R16_CALLED_EMPH_DEF.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if not _R16_DEF_KW.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R16_CALLED_EMPH_DEF', m.start()))

    # ------------------------------------------------------------------
    # R17: '\emph{X} is/when ... property ... if ...'
    # ------------------------------------------------------------------
    for m in R17_EMPH_IF.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if len(name.strip()) < 3:
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R17_EMPH_IF', m.start()))

    # ------------------------------------------------------------------
    # R18: '\emph{Name} (ABBREV)' + display math
    # ------------------------------------------------------------------
    for m in R18_EMPH_DISPLAY.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if len(name.strip()) < 3:
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R18_EMPH_DISPLAY', m.start()))

    # ------------------------------------------------------------------
    # R19: 'is given by / is defined by' + \begin{equation}
#     # ------------------------------------------------------------------
#     for m in R19_IS_GIVEN_BY.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         preamble = m.group('preamble')
#         body = m.group('body')
#         # Find sentence start
#         boundaries = list(_SENT_BOUNDARY.finditer(text, 0, m.start()))
#         sent_start = boundaries[-1].end() if boundaries else max(0, m.start() - 200)
#         full = text[sent_start: m.end()].strip()
#         # Extract name from emphasized text in preamble
#         emph_m = re.search(r'\\(?:emph|textbf|textit)\{([^}]+)\}', preamble)
#         name = emph_m.group(1) if emph_m else preamble.strip()[-80:]
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R19_IS_GIVEN_BY', sent_start))

    # ------------------------------------------------------------------
    # R20: 'we (can) introduce X as $$...$$'
    # ------------------------------------------------------------------
    for m in R20_INTRODUCE_AS.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R20_INTRODUCE_AS', m.start()))

    # ------------------------------------------------------------------
    # R21: 'we define X as/by/= \begin{equation}...'
    # ------------------------------------------------------------------
    for m in R21_DEFINE_EQN.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R21_DEFINE_EQN', m.start()))

    # ------------------------------------------------------------------
    # R22: 'define X \begin{equation}' (no connector)
    # ------------------------------------------------------------------
    for m in R22_DEFINE_DIRECT_EQN.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R22_DEFINE_DIRECT_EQN', m.start()))

    # ------------------------------------------------------------------
    # R23: 'A/An X is [property] if ...' + equation block
    # ------------------------------------------------------------------
    for m in R23_IS_IF_EQN.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R23_IS_IF_EQN', m.start()))

    # ------------------------------------------------------------------
    # R24: 'Consider ...: \begin{equation} := ...'
    # ------------------------------------------------------------------
    for m in R24_CONSIDER_EQN.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R24_CONSIDER_EQN', m.start()))

    # ------------------------------------------------------------------
    # R25: 'we define X as follows / the following' + display math
    # ------------------------------------------------------------------
    for m in R25_DEFINE_DISPLAY.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R25_DEFINE_DISPLAY', m.start()))

    # ------------------------------------------------------------------
    # R26: colon-introduced display math after definitional verb
#     # ------------------------------------------------------------------
#     for m in R26_COLON_DISPLAY.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         # Extract name from first inline math or emphasized text
#         name_m = re.search(r'\\(?:emph|textbf|textit)\{([^}]+)\}|\$([^$]{1,60})\$', full)
#         name = name_m.group(1) or name_m.group(2) if name_m else ''
#         results.append(_make_result(full, _extract_name(name) if name else None, 'R26_COLON_DISPLAY', m.start()))

    # ------------------------------------------------------------------
    # R27: 'The <noun> is\n$$...$$'
#     # ------------------------------------------------------------------
#     for m in R27_NOUN_DISPLAY.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         name_stripped = name.strip()
#         if not name_stripped or len(name_stripped) < 3 or len(name_stripped) > 80:
#             continue
#         if _R27_EXCLUDE_NAMES.match(name_stripped):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R27_NOUN_DISPLAY', m.start()))

    # ------------------------------------------------------------------
    # R28: display math + 'where ...' clause
#     # ------------------------------------------------------------------
#     for m in R28_DISPLAY_WHERE.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if not name.strip() or len(name.strip()) < 3:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R28_DISPLAY_WHERE', m.start()))

    # ------------------------------------------------------------------
    # R29: 'is called' two-phase look-back/look-ahead
    # ------------------------------------------------------------------
    for anchor_m in R29_IS_CALLED_ANCHOR.finditer(text):
        if _inside_excluded_env(excl_spans, anchor_m.start(), anchor_m.end()):
            continue
        start_search = max(0, anchor_m.start() - 80)
        prefix = text[start_search:anchor_m.start()]
        cuts = [prefix.rfind('.')]
        for mk in _STRUCTURAL_CUTS:
            p = prefix.rfind(mk)
            if p >= 0:
                cuts.append(p + len(mk) - 1)
        best = max(cuts)
        name_start = start_search + (best + 1 if best >= 0 else 0)
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 80:
            continue
        tail_m = _tail_re.match(text, anchor_m.end())
        if not tail_m:
            continue
        full = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name_text), 'R29_IS_CALLED_ANCHOR', name_start))

    # ------------------------------------------------------------------
    # R30: 'we (will) refer to X as Y'
#     # ------------------------------------------------------------------
#     for m in R30_REFER_TO.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R30_REFER_TO', m.start()))

    # ------------------------------------------------------------------
    # R31: 'Let us introduce a/an/the <name>'
    # ------------------------------------------------------------------
    for m in R31_LET_US_INTRODUCE.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R31_LET_US_INTRODUCE', m.start()))

    # ------------------------------------------------------------------
    # R32: '... of the form \begin{equation}...'
    # ------------------------------------------------------------------
    for m in R32_OF_THE_FORM.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        if not _R32_DISPLAY.search(full):
            continue
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R32_OF_THE_FORM', m.start()))

    # ------------------------------------------------------------------
    # R33: '<Name> computes/defines the following ...: \begin{equation}'
    # ------------------------------------------------------------------
    for m in R33_COMPUTES_FOLLOWING.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R33_COMPUTES_FOLLOWING', m.start()))

    # ------------------------------------------------------------------
    # R34: '<Name> involves/computes <desc>:' + display eq
#     # ------------------------------------------------------------------
#     for m in R34_COMPUTES_DIRECT.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R34_COMPUTES_DIRECT', m.start()))

    # ------------------------------------------------------------------
    # R35: 'is called \emph{X} ... and is defined ...'
    # ------------------------------------------------------------------
    for m in R35_CALLED_DEFINED.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R35_CALLED_DEFINED', m.start()))

    # ------------------------------------------------------------------
    # R37: 'we consider X and let Y denote ...'
    # ------------------------------------------------------------------
    for m in R37_CONSIDER_LET_DENOTE.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        name = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, _extract_name(name), 'R37_CONSIDER_LET_DENOTE', m.start()))

    # ------------------------------------------------------------------
    # R38: '<Term> is a/an ...' paragraph with display math
#     # ------------------------------------------------------------------
#     for m in R38_IS_A_DISPLAY.finditer(text):
#         if _inside_excluded_env(excl_spans, m.start(), m.end()):
#             continue
#         full = m.group('full').strip()
#         name = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         if len(full) < 50:
#             continue
#         results.append(_make_result(full, _extract_name(name), 'R38_IS_A_DISPLAY', m.start()))

    # ------------------------------------------------------------------
    # R39: 'by solving / via' + \begin{equation}
    # ------------------------------------------------------------------
    for m in R39_BY_SOLVING.finditer(text):
        if _inside_excluded_env(excl_spans, m.start(), m.end()):
            continue
        preamble = m.group('preamble')
        boundaries = list(_SENT_BOUNDARY.finditer(text, 0, m.start()))
        sent_start = boundaries[-1].end() if boundaries else max(0, m.start() - 300)
        full = text[sent_start: m.end()].strip()
        if _REFERENTIAL.search(full):
            continue
        emph_m = re.search(r'\\(?:emph|textbf|textit)\{([^}]+)\}', preamble)
        name = emph_m.group(1) if emph_m else ''
        results.append(_make_result(full, _extract_name(name) if name else None, 'R39_BY_SOLVING', sent_start))

    # ------------------------------------------------------------------
    # Sort by source position, then deduplicate overlapping matches
    # ------------------------------------------------------------------
    results.sort(key=lambda r: r.get('_source_pos', 0))
    results = _dedup(results)

    # Remove internal helper key
    for r in results:
        r.pop('_source_pos', None)

    return results
