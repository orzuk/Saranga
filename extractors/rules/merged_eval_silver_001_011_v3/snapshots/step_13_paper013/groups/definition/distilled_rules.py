import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX markup to produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|text|mathrm|mathit|mathbf|mathbb|mathcal|mathsf)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|it|em|rm|sf|tt)\s+([^}]*)\}', r'\1', text)
    # Remove \cite, \ref, \label, \eqref
    text = re.sub(r'\\(?:cite[a-zA-Z]*|ref|eqref|label)\{[^}]*\}', '', text)
    # Remove \begin/\end environment markers
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math delimiters
    text = re.sub(r'\\\[|\\\]', '', text)
    text = re.sub(r'\$\$', '', text)
    # Collapse inline math to a placeholder
    text = re.sub(r'\$[^$]*\$', '<MATH>', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*', '', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments that should be excluded (definitions inside them are not standalone defs)
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(theorem|thm|lemma|lem|proposition|prop|corollary|cor|claim|'
    r'conjecture|proof|Proof|algorithm|algorithmic|algorithm2e|verbatim|'
    r'lstlisting|minted|tikzpicture|figure|table)\*?\}',
    re.IGNORECASE,
)
_EXCLUDED_ENV_END_RE = re.compile(
    r'\\end\{(theorem|thm|lemma|lem|proposition|prop|corollary|cor|claim|'
    r'conjecture|proof|Proof|algorithm|algorithmic|algorithm2e|verbatim|'
    r'lstlisting|minted|tikzpicture|figure|table)\*?\}',
    re.IGNORECASE,
)


def _build_excluded_spans(text: str):
    """Return list of (start, end) character spans that are inside excluded environments."""
    spans = []
    env_stack = []
    pos = 0
    combined = re.compile(
        r'\\begin\{([^}]+)\}|\\end\{([^}]+)\}',
        re.IGNORECASE,
    )
    excluded = {
        'theorem', 'thm', 'lemma', 'lem', 'proposition', 'prop',
        'corollary', 'cor', 'claim', 'conjecture', 'proof',
        'algorithm', 'algorithmic', 'algorithm2e', 'verbatim',
        'lstlisting', 'minted', 'tikzpicture', 'figure', 'table',
    }
    for m in combined.finditer(text):
        if m.group(1) is not None:
            env_name = m.group(1).rstrip('*').lower()
            if env_name in excluded:
                env_stack.append((env_name, m.start()))
        elif m.group(2) is not None:
            env_name = m.group(2).rstrip('*').lower()
            if env_stack and env_stack[-1][0] == env_name:
                start_pos = env_stack.pop()[1]
                spans.append((start_pos, m.end()))
    return spans


def _inside_excluded_env(spans, start: int, end: int) -> bool:
    """Return True if the span [start, end) overlaps any excluded environment span."""
    for (es, ee) in spans:
        if start < ee and end > es:
            return True
    return False


# ---------------------------------------------------------------------------
# Referential / negative guards (reused across patterns)
# ---------------------------------------------------------------------------

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

_SENTENCE_BOUNDARY = re.compile(r'[.!?]\s+|\n\s*\n', re.DOTALL)

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# C6: {\bf Term:} or {\bf Term} followed by definitional prose
# PRUNED — FP on paper001, paper002, paper003 +5 more | also 4 TP — review before uncommenting
# inline_bf_term_pattern = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}:]{1,120}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,1000}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     re.DOTALL,
# )

# C6b: \textbf{Term:} form
# PRUNED — FP on paper002, paper003, paper004 +5 more
# inline_textbf_term_pattern = re.compile(
#     r'(?P<full>'
#     r'\\textbf\{(?P<name>[^}:]{1,120}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\\textbf\{).){10,1000}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     re.DOTALL,
# )

# C7: (also called ALIAS) or (called ALIAS) or (known as ALIAS) parenthetical definition
# PRUNED — FP on paper001, paper010 | also 1 TP — review before uncommenting
# inline_also_called_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,120}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,300}?\.)',
#     re.DOTALL,
# )

# C2 plural: 'are defined as/to be'
_c2_anchor_plural = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    re.IGNORECASE,
)
_c2_tail = re.compile(
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.',
    re.DOTALL,
)

# C5: 'X stands for ...', 'X denotes ...', 'X refers to ...'
# PRUNED — FP on paper001, paper003, paper005 +5 more | also 2 TP — review before uncommenting
# inline_stands_for_pattern = re.compile(
#     r'(?P<full>'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]+?))'
#     r'\s+(?:stands\s+for|denotes|refers\s+to)\s+'
#     r'(?:the\s+|a\s+|an\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     re.IGNORECASE | re.DOTALL,
# )

# C6 (let denote): 'Let X denote ...'
# PRUNED — FP on paper006, paper008, paper013 | also 1 TP — review before uncommenting
# inline_let_denote_pattern = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]+?))'
#     r'\s+denote\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     re.DOTALL,
# )

# C7 (imperative): 'Introduce ...' or 'Set ...' at sentence/paragraph start
inline_imperative_pattern = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=[.\n]))\s*'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^.\$]{1,80}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    re.DOTALL | re.MULTILINE,
)

# C8 (we consider + let denote): 'we consider X ... let Y denote ...'
inline_we_consider_pattern = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+consider\s+'
    r'(?P<name>[^.]{1,80}?)'
    r'\s*(?:\.{3}|,|\s)\s*'
    r'(?:and\s+)?let\s+[^.]{1,80}?\s+denote\s+'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    re.DOTALL,
)

# C9 (introduce call): 'we introduce ... call ... :'
inline_introduce_call_pattern = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?call\s+'
    r'(?:\{\\it\s+|\{\\emph\{|\\textit\{|\\emph\{)?[^{}\n]{1,60}(?:\}\}?)?\s*:'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\s*\$\$.*?\$\$|\s*\\\[.*?\\\]))',
    re.DOTALL,
)

# C10 (denote by): '(We) denote by X ...'
# PRUNED — FP on paper002, paper003, paper004 +1 more | also 2 TP — review before uncommenting
# inline_denote_by_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:will\s+)?|[Ll]et\s+us\s+)?[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]+?))'
#     r'\s+'
#     r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
#     re.DOTALL,
# )

# C5_emph_semi: '{\em term}; ... is ...' or '\emph{term}; ...'
inline_emph_semi_pattern = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,120}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.]{0,300}\.)',
    re.IGNORECASE | re.DOTALL,
)

# C1b: 'define X as \begin{env}...\end{env}'
inline_define_env_pattern = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,120}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?:[^\\]|\\(?!begin))*?'
    r'(?P<envbody>\\begin\{(?P<envn>[a-zA-Z*]+)\}.*?\\end\{(?P=envn)\})'
    r')',
    re.IGNORECASE | re.DOTALL,
)

# C1c: 'define X \begin{equation}' with no explicit connector
inline_define_direct_eqn_pattern = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+(?:can\s+)?)?define\s+'
    r'(?P<name>(?:the\s+)?[A-Za-z][^\\\n]{2,100}?)'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}))',
    re.IGNORECASE | re.DOTALL,
)

# C5b (is given by): '... is given by \begin{equation}...'
# PRUNED — FP on paper002, paper004, paper013 | also 2 TP — review before uncommenting
# inline_is_given_by_pattern = re.compile(
#     r'(?P<preamble>[^.]{0,300}?\b(?:is\s+given|is\s+defined)\s+by\s*)'
#     r'(?P<body>\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})',
#     re.DOTALL,
# )

# C6b (A X is property if): 'A/An X is [property] if ... \begin{equation}...'
inline_a_x_is_if_pattern = re.compile(
    r'(?P<full>'
    r'(?:A|An)\s+'
    r'(?P<name>[A-Za-z][^.\n]{2,100}?)\s+is\s+[^.\n]{2,120}?\s+if\s+'
    r'[^.\n]{0,200}?'
    r'(?:\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}))',
    re.DOTALL,
)

# C5_emph_if: '\emph{property} if <condition>.'
inline_emph_if_pattern = re.compile(
    r'(?P<full>'
    r'[A-Z][^.]{0,120}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'[^.]{0,200}?'
    r'\b(?:if|when|provided|whenever)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    re.IGNORECASE | re.DOTALL,
)

# C6_emph_display: '\emph{name} (ABBR?) followed by display math'
inline_emph_display_pattern = re.compile(
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
    re.DOTALL,
)

# C7_noun_display: 'the <noun> is [given by] <display math>'
# PRUNED — FP on paper013
# inline_noun_display_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:Given[^,]{0,100},\s*)?'
#     r'(?:the|The)\s+'
#     r'(?P<name>[A-Za-z][^$\\]{1,60}?)'
#     r'\s+is(?:\s+(?:given\s+by|defined\s+as|defined\s+by))?\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline)\*?\}.*?\\end\{(?:align|equation|gather|multline)\*?\}'
#     r')'
#     r')',
#     re.DOTALL,
# )

# C8_display_where: '<noun type>: <display math> ... where ...'
# PRUNED — FP on paper004, paper006, paper009 +3 more | also 1 TP — review before uncommenting
# inline_display_where_pattern = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,200}?'
#     r'(?P<name>'
#     r'(?:the\s+)?[a-z][a-z\s]{2,50}?'
#     r'(?:norm|measure|metric|distance|kernel|cost|function|map|operator|space|matrix|bound|rate|set)'
#     r')'
#     r'[^$\\]{0,30}?'
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
#     re.DOTALL,
# )

# C5_called_defined: 'is called \emph{NAME} ... is defined as ...'
inline_called_defined_pattern = re.compile(
    r'(?P<full>'
    r'(?:is\s+called\s+(?:the\s+)?|called\s+(?:the\s+)?)'
    r'(?:\\emph\{|\\textbf\{|\\textit\{)?'
    r'(?P<name>[^},\n]{1,80}?)'
    r'(?:\}\s*)?'
    r'[^.]{0,300}?'
    r'(?:is\s+defined\s+as|it\s+is\s+defined|defined\s+to\s+be|:=)'
    r'(?:[^.]*(?:\\begin\{(?:align|equation|gather|multline)\*?\}.*?\\end\{(?:align|equation|gather|multline)\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\]))*'
    r'[^.]*\.)',
    re.IGNORECASE | re.DOTALL,
)

# C6_colon_display: sentence with definitional word, ending ':', followed by display math
inline_colon_display_pattern = re.compile(
    r'(?P<full>'
    r'(?:[A-Z][^\n]{0,300}?'
    r'\b(?:define|denote|set|let|given\s+by|equal\s+to|as\s+follows)\b'
    r'[^\n]{0,200}?:\s*\n?)'
    r'(?P<mathblock>'
    r'\\begin\{(?:align|equation|gather|multline)\*?\}'
    r'(?:.*?\\begin\{split\}.*?\\end\{split\}.*?|.*?)'
    r'\\end\{(?:align|equation|gather|multline)\*?\}'
    r')'
    r'(?:\s*where\s[^\n]{0,300}\.)?'
    r')',
    re.IGNORECASE | re.DOTALL,
)

# C5_called_emph: '... called a \emph{Name} ...'
# PRUNED — FP on paper007
# inline_called_emph_pattern = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,300}?'
#     r'(?:called|known\s+as)\s+'
#     r'(?:a\s+|an\s+|the\s+)?'
#     r'(?:\\emph\{|\\textit\{|\\textbf\{)'
#     r'(?P<name>[^}]{1,80})'
#     r'\}'
#     r'[^.\n]{0,300}?\.)',
#     re.DOTALL,
# )

_CALLED_EMPH_KEYWORDS = re.compile(
    r'\b(defined?\s+(?:by|via|as|through)|denoted?\s+by|given\s+by|'
    r'equation|ODE|map|operator|density|distribution|function|path|field|'
    r'set|sequence|space|chain|process|model|matrix|graph|norm|kernel|'
    r'flow|transform|measure|cost|formula|criterion|bound)\b',
    re.IGNORECASE,
)

# C6_of_the_form: 'we consider/define X of the form \begin{equation}...'
inline_of_the_form_pattern = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:consider|study|adopt|define|use|introduce|propose|set)\s+'
    r'(?P<name>[^.\n]{1,100}?)'
    r'\s+of\s+the\s+form\b'
    r'(?:[^.]{0,800}?\.)'
    r')',
    re.IGNORECASE | re.DOTALL,
)

_OF_THE_FORM_MATH = re.compile(
    r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}'
    r'|\\\[',
    re.DOTALL,
)

# C11: 'we introduce the following quantities ... called {\it NAME}'
inline_introduce_quantities_pattern = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+the\s+following\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'(?:\{\\it\s+|\{\\emph\{|\\textit\{|\\emph\{|\\textbf\{)?'
    r'[^{}\n]{1,60}'
    r'(?:\}\}?)?'
    r'\s*:'
    r'(?:\s*\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|\s*\$\$.*?\$\$|\s*\\\[.*?\\\])'
    r')',
    re.DOTALL,
)

# C12: '{\em term}' or '\emph{term}' introduced after \subsubsection or \paragraph
# followed by definitional sentence
inline_emph_subheading_pattern = re.compile(
    r'(?P<full>'
    r'(?:\\(?:subsubsection|paragraph)\*?\{[^}]*\})'
    r'\s*(?:%[^\n]*\n)*\s*'
    r'[^\\%\n]{0,200}?'
    r'(?:\\emph\{(?P<name>[^}]{2,80})\}|\{\\em\s+(?P<name2>[^}]{2,80})\})'
    r'[^.]{0,600}?\.)',
    re.DOTALL,
)

# C9b: 'we write X for ...' (notation definition)
inline_we_write_pattern = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9_\\(),.\s]{1,60}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin|\\section|\\subsection).){1,400}?\.)',
    re.IGNORECASE | re.DOTALL,
)

# C10b: 'we introduce ... as' followed by display math
inline_introduce_as_pattern = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.]{1,80}?)'
    r'\s+as\s+'
    r'(?:[^$\[\\]|\$(?!\$)|\\.)*?'
    r'(?P<math>\$\$.*?\$\$|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})'
    r'(?:[^.]*\.)?'
    r')',
    re.IGNORECASE | re.DOTALL,
)

# C13: 'X is \emph{NAME}' where NAME is a defined property
# E.g. 'the object of interest is {\em compressible} in the sense that ...'
# PRUNED — FP on paper002
# inline_is_emph_pattern = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.]{0,120}?'
#     r'\bis\s+'
#     r'(?:\{\\em\s+(?P<name>[^}]{2,60})\}|\\emph\{(?P<name2>[^}]{2,60})\})'
#     r'\s+in\s+the\s+sense\s+that\s+'
#     r'[^.]{0,400}?\.)',
#     re.DOTALL,
# )


# ---------------------------------------------------------------------------
# Priority map for deduplication
# ---------------------------------------------------------------------------

_SOURCE_PRIORITY = {
    'inline_bf_term': 1,
    'inline_textbf_term': 1,
    'inline_called_defined': 2,
    'inline_also_called': 2,
    'inline_called_emph': 2,
    'inline_emph_semi': 2,
    'inline_denote_by': 2,
    'inline_is_given_by': 2,
    'inline_a_x_is_if': 2,
    'inline_emph_if': 2,
    'inline_emph_display': 2,
    'inline_noun_display': 2,
    'inline_display_where': 2,
    'inline_called_defined': 2,
    'inline_colon_display': 2,
    'inline_of_the_form': 2,
    'inline_introduce_quantities': 2,
    'inline_emph_subheading': 2,
    'inline_stands_for': 3,
    'inline_let_denote': 3,
    'inline_imperative': 3,
    'inline_we_consider': 3,
    'inline_introduce_call': 3,
    'inline_introduce_as': 3,
    'inline_we_write': 3,
    'inline_define_env': 3,
    'inline_define_direct_eqn': 3,
    'inline_is_emph': 3,
}


def _extract_name_hint(raw_name: str) -> str:
    """Extract a clean name hint from raw LaTeX name fragment."""
    raw_name = raw_name.strip()
    m_math = re.search(r'\$(.+?)\$', raw_name)
    if m_math:
        inner = m_math.group(1)
        inner = re.sub(r'\\[a-zA-Z]+', '', inner)
        inner = re.sub(r'[{}]', '', inner)
        return inner.strip()[:80]
    # Strip LaTeX commands
    cleaned = re.sub(r'\\[a-zA-Z]+\*?(?:\{[^}]*\})?', '', raw_name)
    cleaned = re.sub(r'[{}]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()[:80]


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """Extract definition structures not caught by the base parser."""
    results: List[dict] = []
    excluded_spans = _build_excluded_spans(text)

    def _add(raw_latex: str, name_raw: str, rule_name: str, source_pos: int):
        if not raw_latex or len(raw_latex.strip()) < 20:
            return
        if _inside_excluded_env(excluded_spans, source_pos, source_pos + len(raw_latex)):
            return
        name_hint = _extract_name_hint(name_raw) if name_raw else None
        results.append({
            'raw_latex': raw_latex,
            'clean_text': _clean_latex(raw_latex),
            'name': name_hint or None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_source_pos': source_pos,
        })

    # --- C6: {\bf Term:} blocks ---
#     for m in inline_bf_term_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if not name_raw.strip():
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_bf_term_pattern', m.start())

    # --- C6b: \textbf{Term:} blocks ---
#     for m in inline_textbf_term_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if not name_raw.strip():
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_textbf_term_pattern', m.start())

    # --- C7: (also called ALIAS) parenthetical ---
#     for m in inline_also_called_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if len(name_raw.strip()) < 2:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_also_called_pattern', m.start())

    # --- C2 plural: 'are defined as' ---
    for anchor_m in _c2_anchor_plural.finditer(text):
        start_search = max(0, anchor_m.start() - 80)
        prefix = text[start_search:anchor_m.start()]
        cuts = [prefix.rfind('.')]
        for mk in ('\n\n', '\\section', '\\subsection', '\\begin', '\\end',
                   '\\item', '\\par', '}'):
            p = prefix.rfind(mk)
            if p >= 0:
                cuts.append(p + len(mk) - 1)
        best = max(cuts)
        name_start = start_search + (best + 1 if best >= 0 else 0)
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 80:
            continue
        tail_m = _c2_tail.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(excluded_spans, name_start, tail_m.end()):
            continue
        results.append({
            'raw_latex': full_text,
            'clean_text': _clean_latex(full_text),
            'name': _extract_name_hint(name_text),
            'env_name': 'distilled',
            'rule_name': '_c2_anchor_plural',
            'structure_type': 'definition',
            '_source_pos': name_start,
        })

    # --- C5: 'X stands for ...' ---
#     for m in inline_stands_for_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_stands_for_pattern', m.start())

    # --- C6 let denote: 'Let X denote ...' ---
#     for m in inline_let_denote_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_let_denote_pattern', m.start())

    # --- C7 imperative: 'Introduce ...' / 'Set ...' ---
    for m in inline_imperative_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_imperative_pattern', m.start())

    # --- C8 we_consider: 'we consider X ... let Y denote ...' ---
    for m in inline_we_consider_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_we_consider_pattern', m.start())

    # --- C9 introduce_call: 'we introduce ... call ... :' ---
    for m in inline_introduce_call_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_introduce_call_pattern', m.start())

    # --- C10 denote_by: '(We) denote by X ...' ---
#     for m in inline_denote_by_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_denote_by_pattern', m.start())

    # --- C5 emph_semi: '\emph{term}; ... is ...' ---
    for m in inline_emph_semi_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or m.group('name2') or ''
        semi_pos = full.find(';')
        if semi_pos < 0:
            continue
        after_semi = full[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_emph_semi_pattern', m.start())

    # --- C1b define_env: 'define X as \begin{env}...' ---
    for m in inline_define_env_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_define_env_pattern', m.start())

    # --- C1c define_direct_eqn: 'define X \begin{equation}...' ---
    for m in inline_define_direct_eqn_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_define_direct_eqn_pattern', m.start())

    # --- C5b is_given_by: 'X is given by \begin{equation}...' ---
#     for m in inline_is_given_by_pattern.finditer(text):
#         preamble = m.group('preamble')
#         body = m.group('body')
#         # find sentence start
#         boundaries = list(_SENTENCE_BOUNDARY.finditer(text, 0, m.start()))
#         if boundaries:
#             sent_start = boundaries[-1].end()
#         else:
#             sent_start = max(0, m.start() - 200)
#         full_text = text[sent_start:m.end()].strip()
#         name_raw = text[sent_start:m.start()].strip()
#         emph_m = re.search(r'\\(?:emph|textbf|textit)\{([^}]+)\}', name_raw)
#         name_hint = emph_m.group(1) if emph_m else name_raw[-80:]
#         if _REFERENTIAL.search(full_text):
#             continue
#         if _inside_excluded_env(excluded_spans, sent_start, m.end()):
#             continue
#         results.append({
#             'raw_latex': full_text,
#             'clean_text': _clean_latex(full_text),
#             'name': _extract_name_hint(name_hint),
#             'env_name': 'distilled',
#             'rule_name': 'inline_is_given_by_pattern',
#             'structure_type': 'definition',
#             '_source_pos': sent_start,
#         })

    # --- C6b A_X_is_if: 'A/An X is [property] if ... \begin{equation}...' ---
    for m in inline_a_x_is_if_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_a_x_is_if_pattern', m.start())

    # --- C5_emph_if: '\emph{property} if <condition>.' ---
    for m in inline_emph_if_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if len(name_raw.strip()) < 3:
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_emph_if_pattern', m.start())

    # --- C6_emph_display: '\emph{name} (ABBR?) + display math' ---
    for m in inline_emph_display_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if len(name_raw.strip()) < 3:
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_emph_display_pattern', m.start())

    # --- C7_noun_display: 'the <noun> is ... <display math>' ---
#     for m in inline_noun_display_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if not name_raw or len(name_raw.strip()) < 3 or len(name_raw.strip()) > 80:
#             continue
#         if re.match(r'^(?:following|above|below|result|fact|situation|case)$',
#                     name_raw.strip(), re.IGNORECASE):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_noun_display_pattern', m.start())

    # --- C8_display_where: '<noun type>: <display math> ... where ...' ---
#     for m in inline_display_where_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if not name_raw or len(name_raw.strip()) < 3:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_display_where_pattern', m.start())

    # --- C5_called_defined: 'is called \emph{NAME} ... is defined as ...' ---
    for m in inline_called_defined_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_called_defined_pattern', m.start())

    # --- C6_colon_display: definitional word + colon + display math ---
    for m in inline_colon_display_pattern.finditer(text):
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        # Extract name from math in body
        intro_part = full[:full.find(':') + 1] if ':' in full else full[:60]
        name_m = re.search(r'\$([^$]{1,60})\$', intro_part)
        name_raw = name_m.group(1) if name_m else ''
        _add(full, name_raw, 'inline_colon_display_pattern', m.start())

    # --- C5_called_emph: '... called a \emph{Name} ...' ---
#     for m in inline_called_emph_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if not _CALLED_EMPH_KEYWORDS.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_called_emph_pattern', m.start())

    # --- C6_of_the_form: 'we consider X of the form \begin{equation}...' ---
    for m in inline_of_the_form_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if not _OF_THE_FORM_MATH.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_of_the_form_pattern', m.start())

    # --- C11: 'we introduce the following quantities ... called {\it NAME}' ---
    for m in inline_introduce_quantities_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_introduce_quantities_pattern', m.start())

    # --- C12: emph/em term after \subsubsection or \paragraph ---
    for m in inline_emph_subheading_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or m.group('name2') or ''
        if len(name_raw.strip()) < 2:
            continue
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_emph_subheading_pattern', m.start())

    # --- C9b: 'we write X for ...' ---
    for m in inline_we_write_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_we_write_pattern', m.start())

    # --- C10b: 'we introduce X as <display math>' ---
    for m in inline_introduce_as_pattern.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _REFERENTIAL.search(full):
            continue
        _add(full, name_raw, 'inline_introduce_as_pattern', m.start())

    # --- C13: 'X is \emph{NAME} in the sense that ...' ---
#     for m in inline_is_emph_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or m.group('name2') or ''
#         if len(name_raw.strip()) < 2:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'inline_is_emph_pattern', m.start())

    # ---------------------------------------------------------------------------
    # Deduplication: remove overlapping matches, keep higher priority
    # ---------------------------------------------------------------------------
    if not results:
        return results

    # Sort by priority (lower = more important), then by position
    def _priority(r: dict) -> int:
        return _SOURCE_PRIORITY.get(r['rule_name'], 5)

    results.sort(key=lambda r: (_priority(r), r.get('_source_pos', 0)))

    # Remove overlapping spans (keep earlier in sorted order = higher priority)
    kept: List[dict] = []
    kept_spans: List[tuple] = []  # (start, end) of kept items

    for r in results:
        pos = r.get('_source_pos', 0)
        length = len(r.get('raw_latex', ''))
        end = pos + length

        overlap = False
        for (ks, ke) in kept_spans:
            if pos < ke and end > ks:
                # Check text overlap via clean_text similarity
                ct = re.sub(r'\s+', ' ', (r.get('clean_text') or '').strip().lower())
                for k in kept:
                    kt = re.sub(r'\s+', ' ', (k.get('clean_text') or '').strip().lower())
                    if ct and kt:
                        if ct in kt or kt in ct:
                            overlap = True
                            break
                        min_len = min(len(ct), len(kt))
                        if min_len > 30 and ct[:30] == kt[:30]:
                            overlap = True
                            break
                if overlap:
                    break

        if not overlap:
            kept.append(r)
            kept_spans.append((pos, end))

    # Clean up internal keys
    for r in kept:
        r.pop('_source_pos', None)

    return kept
