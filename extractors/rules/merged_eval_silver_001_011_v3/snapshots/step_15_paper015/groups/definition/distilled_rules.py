import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very small LaTeX-to-text cleaner (no project dependencies)."""
    t = text
    # Remove display math environments
    t = re.sub(r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}', ' [MATH] ', t, flags=re.DOTALL)
    t = re.sub(r'\$\$.*?\$\$', ' [MATH] ', t, flags=re.DOTALL)
    t = re.sub(r'\\\[.*?\\\]', ' [MATH] ', t, flags=re.DOTALL)
    # Inline math
    t = re.sub(r'\$[^$]{1,200}\$', ' [MATH] ', t, flags=re.DOTALL)
    # Common LaTeX macros
    t = re.sub(r'\\(?:emph|textbf|textit|texttt|mathrm|mathbf|mathit|mathcal|mathbb)\{([^}]*)\}', r'\1', t)
    t = re.sub(r'\{\\(?:em|bf|it|tt)\s+([^}]*)\}', r'\1', t)
    t = re.sub(r'\\(?:section|subsection|subsubsection|paragraph)\*?\{([^}]*)\}', r'\1', t)
    t = re.sub(r'\\(?:label|ref|eqref|cite|citeA|citep|citet)\{[^}]*\}', '', t)
    t = re.sub(r'\\[a-zA-Z]+\s*', ' ', t)
    t = re.sub(r'[{}]', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


# Environments whose interiors should be excluded from inline matching
_EXCLUDED_ENV_NAMES = [
    'proof', 'Proof',
    'theorem', 'Theorem', 'thm',
    'lemma', 'Lemma', 'lem',
    'proposition', 'Proposition', 'prop',
    'corollary', 'Corollary', 'cor',
    'claim', 'Claim',
    'conjecture', 'Conjecture',
    'problem', 'Problem',
    'algorithm', 'algorithmic', 'algorithm2e', 'algorithmics',
    'verbatim', 'lstlisting', 'minted',
    'example', 'Example',
    'remark', 'Remark',
    'figure', 'table',
]

_excluded_env_re = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\}.*?\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) spans that are inside excluded environments."""
    ranges = []
    for m in _excluded_env_re.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if [start,end) overlaps any excluded range."""
    for (a, b) in excluded_ranges:
        if start < b and end > a:
            return True
    return False


def _extract_name_hint(raw: str) -> str:
    """Extract a readable name hint from a raw LaTeX fragment."""
    if not raw:
        return ''
    raw = raw.strip()
    # Prefer inline math
    m = re.search(r'\$([^$]{1,80})\$', raw)
    if m:
        return m.group(1).strip()
    # Strip common LaTeX wrappers
    raw = re.sub(r'\\(?:emph|textbf|textit|texttt)\{([^}]*)\}', r'\1', raw)
    raw = re.sub(r'\{\\(?:em|bf|it|tt)\s+([^}]*)\}', r'\1', raw)
    raw = re.sub(r'\\[a-zA-Z]+\s*', ' ', raw)
    raw = re.sub(r'[{}]', '', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw[:80]


# ---------------------------------------------------------------------------
# Negative / guard patterns
# ---------------------------------------------------------------------------

_referential = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    flags=re.IGNORECASE,
)

_c1_negative = re.compile(
    r'\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    flags=re.IGNORECASE,
)

_definition_keywords = re.compile(
    r'\b(set|function|map|mapping|sequence|matrix|space|operator|'
    r'define|denote|notation|collection|family|class|group|ring|field|'
    r'graph|path|tree|partition|permutation|morphism|homomorphism|'
    r'variable|random\s+variable|distribution|measure|process|transform|'
    r'vector|tensor|kernel|manifold|metric|norm|inner\s+product)\b',
    flags=re.IGNORECASE,
)

# Tail pattern that consumes to end of sentence, optionally spanning display math
_sentence_tail = re.compile(
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|[^.]'
    r')*\.',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# R01: {\bf Term:} or {\bf Term} followed by definitional prose
# Catches bold-labelled inline definitions (e.g., "{\bf $k$-nearest neighbor graphs:} Here...")
# PRUNED — FP on paper001, paper002, paper003 +5 more | also 3 TP — review before uncommenting
# R01_bf_term = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}:]{1,100}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,800}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# R02: \textbf{Term:} variant of R01
# PRUNED — FP on paper002, paper003, paper004 +5 more
# R02_textbf_term = re.compile(
#     r'(?P<full>'
#     r'\\textbf\{(?P<name>[^}:]{1,100}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\\textbf\{).){10,800}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# R03: 'We (will) denote by X the ...' — standard math notation definition
# PRUNED — FP on paper002, paper003, paper004 +1 more | also 2 TP — review before uncommenting
# R03_denote_by = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:will\s+)?|[Ll]et\s+us\s+)denote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,\s]{1,60}?))'
#     r'\s+(?:the\s+)?'
#     r'(?:'
#     r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
#     r'|\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|[^.]'
#     r')*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R04: 'Denote by X ...' — imperative form
# PRUNED — FP on paper004
# R04_denote_by_imperative = re.compile(
#     r'(?P<full>'
#     r'(?<![a-zA-Z])[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,\s]{1,60}?))'
#     r'\s+'
#     r'(?:'
#     r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
#     r'|\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|[^.]'
#     r')*\.)',
#     flags=re.DOTALL,
# )

# R05: 'X stands for ...' / 'X denotes ...' / 'X refers to ...' — notation intro
# PRUNED — FP on paper001, paper003, paper005 +4 more | also 2 TP — review before uncommenting
# R05_stands_for = re.compile(
#     r'(?P<full>'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{}\s,.]+?))'
#     r'\s+(?:stands\s+for|denotes|refers\s+to)\s+'
#     r'(?:the\s+|a\s+|an\s+)?'
#     r'(?:'
#     r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
#     r'|\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|[^.]'
#     r')*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R06: 'Let X denote ...' — definitional idiom (complement to existing 'Let X be')
# PRUNED — FP on paper004, paper006, paper008 +1 more
# R06_let_denote = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{}\s,.]+?))'
#     r'\s+denote\s+'
#     r'(?:'
#     r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
#     r'|\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|[^.]'
#     r')*\.)',
#     flags=re.DOTALL,
# )

# R07: 'Introduce ...' or 'Set ...' — imperative definitional sentence
R07_imperative = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=[.\n]))\s*'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^.\$\\]{1,80}?)'
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|[^.]'
    r')*\.)',
    flags=re.DOTALL | re.MULTILINE,
)

# R08: 'let us introduce [a/an/the] <name> ...' — definitional paragraph opener
R08_let_us_introduce = re.compile(
    r'(?P<full>'
    r'[Ll]et\s+us\s+introduce\s+(?:a\s+|an\s+|the\s+)?'
    r'(?P<name>[^.:\n]{1,80}?)'
    r'(?::\s*|\s+)'
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|[^.]'
    r')*.)',
    flags=re.DOTALL,
)

# R09: 'we (can) introduce X as $$ ... $$' — introduce-as pattern
R09_introduce_as = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.\n]{1,80}?)'
    r'\s+as\s+'
    r'(?:[^$\\]|\$(?!\$))*?'
    r'(?P<math>'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r')'
    r'(?:[^.]*\.)?'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R10: 'we introduce ... (that we will) call {\it NAME}:' followed by equation
R10_introduce_call = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.\n]{1,120}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?call\s+'
    r'(?:\{\\it\s+|\{\\emph\{|\\textit\{|\\emph\{)?[^{}\n]{1,60}(?:\}\}?)?\s*'
    r':'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\s*\$\$.*?\$\$'
    r'|\s*\\\[.*?\\\])'
    r')',
    flags=re.DOTALL,
)

# R11: 'we will (also) refer to X as Y' — naming/definition pattern
# PRUNED — FP on paper003, paper004, paper015 | also 1 TP — review before uncommenting
# R11_refer_to = re.compile(
#     r'(?P<full>'
#     r'[Ww]e\s+(?:will\s+)?(?:also\s+|therefore\s+|henceforth\s+|hereby\s+)?'
#     r'refer\s+to\s+'
#     r'(?P<name>[^.\n]{1,100}?)'
#     r'\s+as\s+'
#     r'(?:'
#     r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
#     r'|\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|[^.]'
#     r')*.)',
#     flags=re.DOTALL,
# )

# R12: '(also called ALIAS)' or '(known as ALIAS)' parenthetical definition
# PRUNED — FP on paper001, paper010, paper014 | also 1 TP — review before uncommenting
# R12_also_called = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,120}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,300}?\.)',
#     flags=re.DOTALL,
# )

# R13: 'is called (the/a/an) <name>' — passive naming
# Two-phase: anchor + look-back/forward (handled in loop below)
# PRUNED — FP on paper001, paper005, paper009 +2 more | also 6 TP — review before uncommenting
# R13_is_called_anchor = re.compile(
#     r'\bis\s+called\s+(?:the\s+|a\s+|an\s+)?',
#     flags=re.IGNORECASE,
# )

# R14: 'are defined as' — plural passive (extends existing C2 singular)
R14_are_defined_anchor = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)

# Tail pattern shared with C2 processing
_c2_tail = re.compile(
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|[^.]'
    r')*\.',
    flags=re.DOTALL,
)

# R15: '\emph{term}; ... is/are ...' — emph term introduced then defined after semicolon
R15_emph_semi = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.\n]{0,120}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.\n]{0,300}\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R16: '\emph{term}' followed (in sentence) by 'if/when' + equation
# e.g. "The kernel K is \emph{positive definite} if ||f|| > 0 => ||f||_K > 0"
R16_emph_if = re.compile(
    r'(?P<full>'
    r'[A-Z][^.\n]{0,120}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'[^.\n]{0,200}?'
    r'\b(?:if|when|provided|whenever)\b'
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|[^.]'
    r')*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R17: '...the \emph{term} (ABBR)\n$$...$$' or '\emph{term} followed by display math
R17_emph_display = re.compile(
    r'(?P<full>'
    r'[^\n.]{0,150}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'(?:\s*\([A-Z][A-Za-z0-9*]{0,10}\))?'
    r'\s*'
    r'(?:'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:align|equation|gather|multline)\*?\}.*?\\end\{(?:align|equation|gather|multline)\*?\}'
    r')'
    r')',
    flags=re.DOTALL,
)

# R18: 'the <noun phrase> is [given by / defined as] \begin{equation}...'
# PRUNED — FP on paper002, paper004, paper009 +1 more
# R18_noun_is_given_by = re.compile(
#     r'(?P<full>'
#     r'(?:Given[^,\n]{0,100},\s*)?'
#     r'(?:the|The|a|A|an|An)\s+'
#     r'(?P<name>[A-Za-z][^$\\\n]{1,80}?)'
#     r'\s+is(?:\s+(?:given\s+by|defined\s+as|defined\s+by))?\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline)\*?\}.*?\\end\{(?:align|equation|gather|multline)\*?\}'
#     r')'
#     r')',
#     flags=re.DOTALL,
# )

# R19: 'A/An X is <predicate> if ... \begin{equation}...' — property definition
R19_is_if_equation = re.compile(
    r'(?P<full>'
    r'(?:A|An)\s+'
    r'(?P<name>[A-Za-z][^.\n]{2,100}?)\s+is\s+[^.\n]{2,120}?\s+if\s+'
    r'[^.\n]{0,200}?'
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r')'
    r')',
    flags=re.DOTALL,
)

# R20: 'we consider/define/study X of the form \begin{equation}...'
R20_of_the_form = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:consider|study|adopt|define|use|introduce|propose|set)\s+'
    r'(?P<name>[^.\n]{1,100}?)'
    r'\s+of\s+the\s+form\b'
    r'(?:[^.]{0,600}?\.)'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R21: 'we write X for Y, namely ...' — notation introduction
R21_we_write_for = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9_\\(),.\s]{1,60}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin|\\section|\\subsection).){1,300}?'
    r'\bnamely\b'
    r'(?:(?!\\begin|\\section|\\subsection).){0,600}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R22: 'we define X as/by \begin{env}...\end{env}' — define + display math env
R22_define_with_env = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,120}?)'
    r'\s*(?:as|by|to\s+be|:=|=|via)\s*'
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r')'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R23: 'we can define X \begin{equation}' — no explicit connector
R23_define_direct = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+(?:can\s+)?)?define\s+'
    r'(?P<name>(?:the\s+)?[A-Za-z][^\\\n]{2,100}?)'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# R24: 'is called \emph{NAME}[,...] and (it) is defined as ...' — compound naming+def
R24_called_then_defined = re.compile(
    r'(?P<full>'
    r'(?:is\s+called\s+(?:the\s+)?|called\s+(?:the\s+)?)'
    r'(?:\\emph\{|\\textbf\{|\\textit\{)?'
    r'(?P<name>[^},\n]{1,80}?)'
    r'(?:}\s*)?'
    r'[^.\n]{0,300}?'
    r'(?:is\s+defined\s+as|it\s+is\s+defined|defined\s+to\s+be|:=)'
    r'(?:[^.]*(?:'
    r'\\begin\{(?:align|equation|gather|multline)\*?\}.*?\\end\{(?:align|equation|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'))*'
    r'[^.]*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R25: 'X is called Y' / 'X are called Y' with \emph
R25_is_called_emph = re.compile(
    r'(?P<full>'
    r'[A-Z][^.\n]{0,120}?'
    r'(?:is|are)\s+called\s+(?:the\s+|a\s+|an\s+)?'
    r'(?:\\emph\{|\\textit\{|\\textbf\{|\{\\em\s+|\{\\it\s+)?'
    r'(?P<name>[^}.\n]{1,80})'
    r'(?:}\s*)?'
    r'[^.\n]{0,300}?\.)',
    flags=re.DOTALL,
)

# R26: Colon-introduced display-math definition
# Sentence ending ':' containing definitional language, then display math block
# PRUNED — FP on paper013, paper014 | also 3 TP — review before uncommenting
# R26_colon_display = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^\n]{0,300}?'
#     r'\b(?:define|denote|set|let|given\s+by|equal\s+to|as\s+follows|introduce)\b'
#     r'[^\n]{0,200}?:\s*\n?)'
#     r'(?P<mathblock>'
#     r'\\begin\{(?:align|equation|gather|multline)[*]?\}'
#     r'(?:.*?\\begin\{split\}.*?\\end\{split\}.*?|.*?)'
#     r'\\end\{(?:align|equation|gather|multline)[*]?\}'
#     r')'
#     r'(?:\s*where\s[^\n]{0,300}\.)?'
#     r')',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R27: Display math + 'where' clause — definition via formula + explanation
# PRUNED — FP on paper004, paper006, paper009 +3 more | also 2 TP — review before uncommenting
# R27_display_where = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,200}?'
#     r'(?P<name>'
#     r'(?:the\s+)?[a-z][a-z\s]{2,50}?'
#     r'(?:norm|measure|metric|distance|kernel|cost|function|map|operator|'
#     r'space|matrix|bound|rate|set|transform|estimator|distribution)'
#     r')'
#     r'[^$\\\n]{0,30}?'
#     r'[:\s]'
#     r'\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline)\*?\}.*?\\end\{(?:align|equation|gather|multline)\*?\}'
#     r')'
#     r'[^.]{0,300}?'
#     r'\bwhere\b'
#     r'[^.]{0,200}?\.)',
#     flags=re.DOTALL,
# )

# R28: '\emph{term}; obeys/satisfies ... if ...'
R28_emph_obeys = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.\n]{0,120}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|[^.]'
    r'){0,400}?'
    r'\bif\b'
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|[^.]'
    r')*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# R29: Multi-sentence paragraph 'we define X as ...' ending at paragraph boundary
R29_define_paragraph = re.compile(
    r'(?P<full>'
    r'(?:[A-Z][^.\n]{0,200}?)?'
    r'[Ww]e\s+(?:also\s+)?define\s+'
    r'(?P<name>[^.\n]{1,80}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\b'
    r'(?:(?!\n\s*\n|\\begin\{(?:proof|theorem|lemma)).){40,1200}'
    r')',
    flags=re.DOTALL,
)

# R30: 'called a/an/the \emph{Name}' + definitional body
# PRUNED — FP on paper007
# R30_called_emph = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,300}?'
#     r'(?:called|known\s+as)\s+'
#     r'(?:\\emph\{|\\textit\{|\\textbf\{|\{\\em\s+)'
#     r'(?P<name>[^}]{1,80})'
#     r'\}'
#     r'[^.\n]{0,300}?\.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# Priorities (lower number = higher priority / kept in dedup)
# ---------------------------------------------------------------------------
_RULE_PRIORITY = {
    'R22_define_with_env': 1,
    'R23_define_direct': 1,
    'R29_define_paragraph': 1,
    'R03_denote_by': 2,
    'R04_denote_by_imperative': 2,
    'R06_let_denote': 2,
    'R07_imperative': 2,
    'R08_let_us_introduce': 2,
    'R09_introduce_as': 2,
    'R10_introduce_call': 2,
    'R11_refer_to': 2,
    'R14_are_defined_anchor': 2,
    'R13_is_called_anchor': 2,
    'R24_called_then_defined': 2,
    'R25_is_called_emph': 2,
    'R15_emph_semi': 2,
    'R26_colon_display': 2,
    'R01_bf_term': 3,
    'R02_textbf_term': 3,
    'R05_stands_for': 3,
    'R12_also_called': 3,
    'R16_emph_if': 3,
    'R17_emph_display': 3,
    'R18_noun_is_given_by': 3,
    'R19_is_if_equation': 3,
    'R20_of_the_form': 3,
    'R21_we_write_for': 3,
    'R27_display_where': 3,
    'R28_emph_obeys': 3,
    'R30_called_emph': 3,
}


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX source text using structural patterns.
    Returns list of dicts with keys: raw_latex, clean_text, name, env_name,
    rule_name, structure_type.

    These rules complement the base parser; they do NOT duplicate environment-based
    or the core C1–C4 inline patterns already in the base method.
    """
    results: List[dict] = []
    excluded_ranges = _build_excluded_ranges(text)

    def _make_result(raw: str, name_raw: str, rule_name: str, start: int) -> dict:
        name_hint = _extract_name_hint(name_raw) if name_raw else None
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name_hint,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_start': start,
        }

    def _add(m, name_raw: str, rule_name: str):
        full = m.group('full') if hasattr(m, 'groupdict') else m.group(0)
        s = m.start()
        e = s + len(full)
        if _inside_excluded_env(s, e, excluded_ranges):
            return
        results.append(_make_result(full, name_raw, rule_name, s))

    # --- R01: {\bf Term:} blocks ---
#     for m in R01_bf_term.finditer(text):
#         name_raw = m.group('name')
#         if not name_raw or len(name_raw.strip()) < 1:
#             continue
#         if _referential.search(m.group('full')):
#             continue
#         _add(m, name_raw, 'R01_bf_term')

    # --- R02: \textbf{Term:} blocks ---
#     for m in R02_textbf_term.finditer(text):
#         name_raw = m.group('name')
#         if not name_raw or len(name_raw.strip()) < 1:
#             continue
#         if _referential.search(m.group('full')):
#             continue
#         _add(m, name_raw, 'R02_textbf_term')

    # --- R03: We (will) denote by X the ... ---
#     for m in R03_denote_by.finditer(text):
#         full = m.group('full')
#         if _referential.search(full) or _c1_negative.search(full):
#             continue
#         _add(m, m.group('name'), 'R03_denote_by')

    # --- R04: Denote by X ... (imperative) ---
#     for m in R04_denote_by_imperative.finditer(text):
#         full = m.group('full')
#         if _referential.search(full) or _c1_negative.search(full):
#             continue
#         _add(m, m.group('name'), 'R04_denote_by_imperative')

    # --- R05: X stands for / denotes / refers to ---
#     for m in R05_stands_for.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name')
#         if not name_raw or len(name_raw.strip()) < 1:
#             continue
#         if _referential.search(full):
#             continue
#         # Avoid matching things like "Section 2 refers to ..."
#         if re.match(r'^\s*(?:Section|Figure|Table|Equation|Theorem|Lemma|Appendix)', name_raw, re.IGNORECASE):
#             continue
#         _add(m, name_raw, 'R05_stands_for')

    # --- R06: Let X denote ... ---
#     for m in R06_let_denote.finditer(text):
#         full = m.group('full')
#         if _referential.search(full):
#             continue
#         _add(m, m.group('name'), 'R06_let_denote')

    # --- R07: Introduce ... / Set ... (imperative) ---
    for m in R07_imperative.finditer(text):
        full = m.group('full')
        if _referential.search(full):
            continue
        _add(m, m.group('name'), 'R07_imperative')

    # --- R08: let us introduce [a/an/the] <name> ... ---
    for m in R08_let_us_introduce.finditer(text):
        full = m.group('full')
        if _referential.search(full):
            continue
        _add(m, m.group('name'), 'R08_let_us_introduce')

    # --- R09: we (can) introduce X as $$ ... $$ ---
    for m in R09_introduce_as.finditer(text):
        full = m.group('full')
        if _referential.search(full):
            continue
        _add(m, m.group('name'), 'R09_introduce_as')

    # --- R10: we introduce ... call ... : equation ---
    for m in R10_introduce_call.finditer(text):
        full = m.group('full')
        if _referential.search(full):
            continue
        _add(m, m.group('name'), 'R10_introduce_call')

    # --- R11: we will refer to X as Y ---
#     for m in R11_refer_to.finditer(text):
#         full = m.group('full')
#         if _referential.search(full):
#             continue
#         _add(m, m.group('name'), 'R11_refer_to')

    # --- R12: (also called ALIAS) / (known as ALIAS) parenthetical ---
#     for m in R12_also_called.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name')
#         if not name_raw or len(name_raw.strip()) < 2:
#             continue
#         if _referential.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
#             continue
#         results.append(_make_result(full, name_raw, 'R12_also_called', m.start()))

    # --- R13: 'is called the/a/an <name>' — two-phase look-back ---
#     for anchor_m in R13_is_called_anchor.finditer(text):
#         s = anchor_m.start()
#         if _inside_excluded_env(s, s + 1, excluded_ranges):
#             continue
#         start_search = max(0, s - 80)
#         prefix = text[start_search:s]
#         cuts = [prefix.rfind('.')]
#         for mk in ('\n\n', '\\section', '\\subsection', '\\maketitle',
#                    '\\begin', '\\end', '\\item', '\\par', '}'):
#             p = prefix.rfind(mk)
#             if p >= 0:
#                 cuts.append(p + len(mk) - 1)
#         best = max(cuts)
#         name_start = start_search + (best + 1 if best >= 0 else 0)
#         name_text = text[name_start:s].strip()
#         if not name_text or len(name_text) > 80:
#             continue
#         tail_m = _c2_tail.match(text, anchor_m.end())
#         if not tail_m:
#             continue
#         full_text = text[name_start:tail_m.end()]
#         if _referential.search(full_text):
#             continue
#         results.append(_make_result(full_text, name_text, 'R13_is_called_anchor', name_start))

    # --- R14: 'are defined as' — plural passive C2 extension ---
    for anchor_m in R14_are_defined_anchor.finditer(text):
        s = anchor_m.start()
        if _inside_excluded_env(s, s + 1, excluded_ranges):
            continue
        start_search = max(0, s - 80)
        prefix = text[start_search:s]
        cuts = [prefix.rfind('.')]
        for mk in ('\n\n', '\\section', '\\subsection', '\\maketitle',
                   '\\begin', '\\end', '\\item', '\\par', '}'):
            p = prefix.rfind(mk)
            if p >= 0:
                cuts.append(p + len(mk) - 1)
        best = max(cuts)
        name_start = start_search + (best + 1 if best >= 0 else 0)
        name_text = text[name_start:s].strip()
        if not name_text or len(name_text) > 80:
            continue
        tail_m = _c2_tail.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _referential.search(full_text):
            continue
        results.append(_make_result(full_text, name_text, 'R14_are_defined_anchor', name_start))

    # --- R15: \emph{term}; ... is/are ... ---
    for m in R15_emph_semi.finditer(text):
        full = m.group('full')
        semi_pos = full.find(';')
        if semi_pos < 0:
            continue
        after_semi = full[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        if _referential.search(full):
            continue
        name_raw = m.group('name') or m.group('name2') or ''
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, name_raw, 'R15_emph_semi', m.start()))

    # --- R16: \emph{property} if <condition> ---
    for m in R16_emph_if.finditer(text):
        full = m.group('full')
        name_raw = m.group('name').strip()
        if len(name_raw) < 3:
            continue
        if _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, name_raw, 'R16_emph_if', m.start()))

    # --- R17: \emph{term} followed by display math ---
    for m in R17_emph_display.finditer(text):
        full = m.group('full')
        name_raw = m.group('name').strip()
        if len(name_raw) < 3:
            continue
        if _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, name_raw, 'R17_emph_display', m.start()))

    # --- R18: the <noun phrase> is [given by/defined as] + display math ---
#     for m in R18_noun_is_given_by.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name').strip()
#         if not name_raw or len(name_raw) < 3 or len(name_raw) > 80:
#             continue
#         if re.match(r'^(?:following|above|below|result|fact|situation|case)$',
#                     name_raw, re.IGNORECASE):
#             continue
#         if _referential.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
#             continue
#         results.append(_make_result(full, name_raw, 'R18_noun_is_given_by', m.start()))

    # --- R19: A/An X is <predicate> if ... equation ---
    for m in R19_is_if_equation.finditer(text):
        full = m.group('full')
        if _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, m.group('name'), 'R19_is_if_equation', m.start()))

    # --- R20: we consider/define X of the form + equation ---
    for m in R20_of_the_form.finditer(text):
        full = m.group('full')
        if not re.search(
            r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}|\\\[',
            full, re.DOTALL
        ):
            continue
        if _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, m.group('name'), 'R20_of_the_form', m.start()))

    # --- R21: we write X for Y, namely ... ---
    for m in R21_we_write_for.finditer(text):
        full = m.group('full')
        if _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, m.group('name'), 'R21_we_write_for', m.start()))

    # --- R22: we define X as \begin{env}...\end{env} ---
    for m in R22_define_with_env.finditer(text):
        full = m.group('full')
        if _c1_negative.search(full) or _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, m.group('name'), 'R22_define_with_env', m.start()))

    # --- R23: we can define X \begin{equation} (no connector) ---
    for m in R23_define_direct.finditer(text):
        full = m.group('full')
        if _c1_negative.search(full) or _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, m.group('name'), 'R23_define_direct', m.start()))

    # --- R24: is called \emph{NAME} and is defined as ... ---
    for m in R24_called_then_defined.finditer(text):
        full = m.group('full')
        if _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, m.group('name'), 'R24_called_then_defined', m.start()))

    # --- R25: X is/are called \emph{name} ... ---
    for m in R25_is_called_emph.finditer(text):
        full = m.group('full')
        name_raw = m.group('name').strip()
        if not name_raw or len(name_raw) < 2:
            continue
        if _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, name_raw, 'R25_is_called_emph', m.start()))

    # --- R26: sentence ending ':' + definitional language + display math ---
#     for m in R26_colon_display.finditer(text):
#         full = m.group('full')
#         if _referential.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
#             continue
#         # Extract name hint from first math in intro
#         intro = full[:full.find(':')+1] if ':' in full else full[:80]
#         math_m = re.search(r'\$([^$]{1,60})\$', intro)
#         name_raw = math_m.group(1) if math_m else None
#         results.append(_make_result(full, name_raw or '', 'R26_colon_display', m.start()))

    # --- R27: display math + 'where' clause naming a mathematical object ---
#     for m in R27_display_where.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name').strip()
#         if not name_raw or len(name_raw) < 3:
#             continue
#         if _referential.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
#             continue
#         results.append(_make_result(full, name_raw, 'R27_display_where', m.start()))

    # --- R28: \emph{term} obeys/satisfies ... if ... ---
    for m in R28_emph_obeys.finditer(text):
        full = m.group('full')
        name_raw = (m.group('name') or m.group('name2') or '').strip()
        if not name_raw:
            continue
        if _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, name_raw, 'R28_emph_obeys', m.start()))

    # --- R29: multi-sentence 'we define X as ...' paragraph ---
    for m in R29_define_paragraph.finditer(text):
        full = m.group('full')
        if len(full) < 80:
            continue
        if _c1_negative.search(full) or _referential.search(full):
            continue
        if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
            continue
        results.append(_make_result(full, m.group('name'), 'R29_define_paragraph', m.start()))

    # --- R30: called/known as \emph{Name} + definitional body ---
#     for m in R30_called_emph.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name').strip()
#         if not name_raw or len(name_raw) < 2:
#             continue
#         if not re.search(
#             r'\b(defined?\s+(?:by|via|as|through)|denoted?\s+by|given\s+by|'
#             r'equation|ODE|map|operator|density|distribution|function|path|'
#             r'field|set|sequence|space|process|transform|kernel|matrix)\b',
#             full, re.IGNORECASE,
#         ):
#             continue
#         if _referential.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.start() + len(full), excluded_ranges):
#             continue
#         results.append(_make_result(full, name_raw, 'R30_called_emph', m.start()))

    # -----------------------------------------------------------------------
    # Deduplication: remove overlapping matches; keep higher-priority rule
    # -----------------------------------------------------------------------
    # Sort by start position, then by priority (lower = better)
    results.sort(key=lambda r: (r['_start'], _RULE_PRIORITY.get(r['rule_name'], 9)))

    deduped: List[dict] = []
    for r in results:
        rs = r['_start']
        re_end = rs + len(r['raw_latex'])
        overlaps = False
        for kept in deduped:
            ks = kept['_start']
            ke = ks + len(kept['raw_latex'])
            # Check if they overlap
            if rs < ke and re_end > ks:
                # Check text-level similarity (substring)
                rt = re.sub(r'\s+', ' ', r['clean_text'].strip().lower())
                kt = re.sub(r'\s+', ' ', kept['clean_text'].strip().lower())
                if rt and kt and (rt in kt or kt in rt or
                                  (min(len(rt), len(kt)) > 30 and rt[:30] == kt[:30])):
                    overlaps = True
                    break
        if not overlaps:
            deduped.append(r)

    # Remove internal keys before returning
    for r in deduped:
        r.pop('_start', None)

    return deduped
