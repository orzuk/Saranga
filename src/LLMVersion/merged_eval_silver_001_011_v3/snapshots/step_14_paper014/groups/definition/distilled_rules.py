import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup, returning approximate plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \begin{...} / \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math environments ($$...$$)
    text = re.sub(r'\$\$.*?\$\$', ' MATH ', text, flags=re.DOTALL)
    # Remove \[...\]
    text = re.sub(r'\\\[.*?\\\]', ' MATH ', text, flags=re.DOTALL)
    # Remove inline math $...$
    text = re.sub(r'\$[^$]*\$', ' MATH ', text)
    # Remove \emph{...}, \textit{...}, \textbf{...}, \textrm{...} — keep content
    text = re.sub(r'\\(?:emph|textit|textbf|textrm|texttt|mathrm|mathbf|mathit|mathcal|mathbb)\{([^}]*)\}', r'\1', text)
    # Remove {\em ...}, {\bf ...}, {\it ...} — keep content
    text = re.sub(r'\{\\(?:em|bf|it|rm|tt)\s+([^}]*)\}', r'\1', text)
    # Remove \label{...}, \cite{...}, \ref{...}, \eqref{...}
    text = re.sub(r'\\(?:label|cite|citeA|citeB|citep|citet|ref|eqref|autoref)\{[^}]*\}', '', text)
    # Remove \noindent, \par, \newline, \\
    text = re.sub(r'\\(?:noindent|par|newline|\\)', ' ', text)
    # Remove remaining simple commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Collapse braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n\n', text)
    return text.strip()


# Environments to exclude (proof/theorem/algorithm/etc.)
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{('
    r'proof|theorem|lemma|proposition|corollary|claim|conjecture|'
    r'problem|algorithm|algorithmic|algorithmics|algorithm2e|'
    r'verbatim|lstlisting|minted|figure|table|tabular'
    r')\}(.*?)\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) ranges for excluded environments."""
    ranges = []
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if [start, end) overlaps any excluded range."""
    for (es, ee) in excluded_ranges:
        if start < ee and end > es:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Referential / negative guard patterns
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

# Sentence-end boundary for look-back
_SENT_BOUNDARY = re.compile(r'[.!?]\s+|\n\s*\n', flags=re.DOTALL)

# Display math block (reusable sub-expression)
_DISPLAY_MATH = (
    r'(?:'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather|multline|eqnarray|split)[*]?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline|eqnarray|split)[*]?\}'
    r')'
)

# ---------------------------------------------------------------------------
# R1: {\bf Term:} ... block  (bold-term definitions)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper001, paper002, paper003 +4 more | also 5 TP — review before uncommenting
# inline_bf_term_pattern = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}:]{1,120}?)\s*:?\s*\}'
#     r':?\s*'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,1200}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R2: \emph{term}; ... is/are ... (emph + semicolon definition)
# ---------------------------------------------------------------------------
inline_emph_semi_pattern = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,200}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.]{0,400}\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R3: We (will) denote by X the ... (denote-by definitions)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper002, paper003, paper004 +1 more | also 1 TP — review before uncommenting
# inline_denote_by_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:will\s+)?|[Ll]et\s+us\s+)?'
#     r'[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]{1,60}?))'
#     r'\s+'
#     r'(?:' + _DISPLAY_MATH + r'|[^.])*.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R4: \emph{term} obeys/satisfies ... if ... (obeys-if definitions)
# ---------------------------------------------------------------------------
inline_obeys_if_pattern = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.]{0,200}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'(?:' + _DISPLAY_MATH + r'|[^.]){0,600}?'
    r'\bif\b'
    r'(?:' + _DISPLAY_MATH + r'|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R5: X stands for / denotes / refers to Y (notation definitions)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper001, paper003, paper006 +3 more | also 2 TP — review before uncommenting
# inline_stands_for_pattern = re.compile(
#     r'(?P<full>'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]+?))'
#     r'\s+(?:stands\s+for|denotes|refers\s+to)\s+'
#     r'(?:the\s+|a\s+|an\s+)?'
#     r'(?:' + _DISPLAY_MATH + r'|[^.])*.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R6: Let X denote ... (let-denote)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper004, paper006, paper008 +1 more
# inline_let_denote_pattern = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]+?))'
#     r'\s+denote\s+'
#     r'(?:' + _DISPLAY_MATH + r'|[^.])*.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R7: Imperative: Introduce / Set <name> ... (sentence start)
# ---------------------------------------------------------------------------
inline_imperative_pattern = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=[.\n]))\s*'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^.$\\]{1,80}?)'
    r'(?:' + _DISPLAY_MATH + r'|[^.])*.)',
    flags=re.DOTALL | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# R8: (also called ALIAS) / (known as ALIAS) parenthetical
# ---------------------------------------------------------------------------
# PRUNED — FP on paper001, paper010, paper014 | also 1 TP — review before uncommenting
# inline_also_called_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,200}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,400}?\.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R9: is called (the/a/an) <name> — passive naming
# (handled via two-phase anchor approach in main function)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper001, paper009 | also 6 TP — review before uncommenting
# _IS_CALLED_ANCHOR = re.compile(
#     r'\bis\s+called\s+(?:the\s+|a\s+|an\s+)?',
#     flags=re.IGNORECASE,
# )

_SENT_TAIL = re.compile(
    r'(?:' + _DISPLAY_MATH + r'|[^.])*\.',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R10: We will (also) refer to X as Y
# ---------------------------------------------------------------------------
# PRUNED — FP on paper003, paper004 | also 1 TP — review before uncommenting
# inline_refer_to_pattern = re.compile(
#     r'(?P<full>'
#     r'[Ww]e\s+(?:will\s+)?(?:also\s+|therefore\s+|henceforth\s+|hereby\s+)?'
#     r'refer\s+to\s+'
#     r'(?P<name>[^.]{1,120}?)'
#     r'\s+as\s+'
#     r'(?:' + _DISPLAY_MATH + r'|[^.])*.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R11: let us introduce [a/an/the] <name>
# ---------------------------------------------------------------------------
inline_let_us_introduce_pattern = re.compile(
    r'(?P<full>'
    r'[Ll]et\s+us\s+introduce\s+(?:a\s+|an\s+|the\s+)?'
    r'(?P<name>[^.:]{1,80}?)'
    r'(?::\s*|\s+)'
    r'(?:' + _DISPLAY_MATH + r'|[^.])*.)',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R12: called a \emph{Name} / called the \emph{Name}
# ---------------------------------------------------------------------------
# PRUNED — FP on paper007, paper009
# inline_called_emph_pattern = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,400}?'
#     r'(?:called|known\s+as)\s+'
#     r'(?:\\emph\{|\\textit\{|\\textbf\{|\{\\em\s+|\{\\it\s+)'
#     r'(?P<name>[^}]{1,80})'
#     r'\}'
#     r'[^.\n]{0,400}?\.)',
#     flags=re.DOTALL,
# )

_CALLED_EMPH_DEFN_KW = re.compile(
    r'\b(?:defined?\s+(?:by|via|as|through)|denoted?\s+by|given\s+by|'
    r'equation|ODE|map|operator|density|distribution|function|path|field|'
    r'set|sequence|space|matrix|kernel|process|norm|measure|flow|transform)\b',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R13: we consider/define ... of the form \begin{equation}
# ---------------------------------------------------------------------------
inline_of_the_form_pattern = re.compile(
    r'(?P<full>'
    r'(?:we\s+)?(?:consider|study|adopt|define|use|introduce|propose|set)\s+'
    r'(?P<name>[^.\n]{1,120}?)'
    r'\s+of\s+the\s+form\b'
    r'(?:[^.]{0,800}?\.)'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

_OF_THE_FORM_MATH = re.compile(
    r'\\begin\{(?:equation|align|gather|multline|eqnarray)[*]?\}'
    r'|\\\[',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R14: We (can) introduce X as $$...$$ or \begin{equation}
# ---------------------------------------------------------------------------
inline_introduce_as_pattern = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.]{1,120}?)'
    r'\s+as\s+'
    r'(?:' + _DISPLAY_MATH + r')'
    r'(?:[^.]*\.)?'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R15: We define X as/by \begin{equation} (extend C1 to include env body)
# ---------------------------------------------------------------------------
inline_define_eqn_pattern = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,120}?)'
    r'\s*(?:as|by|to\s+be|:=|=|via)\s*'
    r'(?:[^\\]|\\(?!begin))*?'
    r'(?:' + _DISPLAY_MATH + r')'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R16: we can define the X \begin{equation} (no explicit connector)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper004
# inline_define_direct_eqn_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:can\s+)?)?define\s+'
#     r'(?P<name>(?:the\s+)?[A-Za-z][^\\\n]{2,100}?)'
#     r'(?:\s*' + _DISPLAY_MATH + r')'
#     r')',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R17: A/An X is [property] if ... \begin{equation}
# ---------------------------------------------------------------------------
inline_is_if_pattern = re.compile(
    r'(?P<full>'
    r'(?:A|An)\s+'
    r'(?P<name>[A-Za-z][^.\n]{2,120}?)'
    r'\s+is\s+[^.\n]{2,200}?\s+if\s+'
    r'[^.\n]{0,300}?'
    r'(?:' + _DISPLAY_MATH + r')'
    r')',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R18: X is given by / defined by \begin{equation}
# ---------------------------------------------------------------------------
# PRUNED — FP on paper002, paper004, paper013 | also 1 TP — review before uncommenting
# inline_is_given_by_pattern = re.compile(
#     r'(?P<preamble>[^.]{0,300}?\b(?:is\s+given|is\s+defined)\s+by\s*)'
#     r'(?P<mathblock>' + _DISPLAY_MATH + r')',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R19: \emph{Name} introduced via display math following it
# (name then optional abbrev in parens then display math)
# ---------------------------------------------------------------------------
inline_emph_display_pattern = re.compile(
    r'(?P<full>'
    r'[^\n.]{0,200}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'(?:\s*\([A-Z][A-Za-z0-9*]{0,10}\))?'
    r'\s*'
    r'(?:' + _DISPLAY_MATH + r')'
    r')',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R20: Colon-introduced display math definition
# sentence ending ':' with definitional word + display math block
# ---------------------------------------------------------------------------
# PRUNED — FP on paper013, paper014 | also 3 TP — review before uncommenting
# inline_colon_display_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^\n]{0,400}?'
#     r'\b(?:define|denote|set|let|given\s+by|equal\s+to|as\s+follows|introduce|presented|expressed)\b'
#     r'[^\n]{0,300}?:\s*\n?)'
#     r'(?P<mathblock>'
#     r'\\begin\{(?:align|equation|gather|multline|eqnarray|split)[*]?\}'
#     r'.*?'
#     r'\\end\{(?:align|equation|gather|multline|eqnarray|split)[*]?\}'
#     r')'
#     r'(?:\s*where\s[^\n]{0,400}\.)?'
#     r')',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R21: we introduce ... call ... : + display equation
# ---------------------------------------------------------------------------
inline_introduce_call_pattern = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.]{1,150}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?call\s+'
    r'(?:\{\\it\s+|\{\\emph\{|\\textit\{|\\emph\{)?[^{}]{1,80}(?:\}\}?)?\s*:'
    r'(?:\s*' + _DISPLAY_MATH + r')'
    r')',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# R22: The <noun> is $$...$$ (noun + display math)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper013
# inline_noun_display_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:Given[^,]{0,120},\s*)?'
#     r'(?:the|The)\s+'
#     r'(?P<name>[A-Za-z][^$\\]{1,80}?)'
#     r'\s+is(?:\s+(?:given\s+by|defined\s+as|defined\s+by))?\s*'
#     r'(?:' + _DISPLAY_MATH + r')'
#     r')',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R23: are defined as (plural extend of C2)
# (handled via two-phase anchor in main function)
# ---------------------------------------------------------------------------
_ARE_DEFINED_ANCHOR = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R24: is called \emph{X} ... and is defined as (combined named definition)
# ---------------------------------------------------------------------------
inline_called_defined_pattern = re.compile(
    r'(?P<full>'
    r'(?:is\s+called\s+(?:the\s+)?|called\s+(?:the\s+)?)'
    r'(?:\\emph\{|\\textbf\{|\\textit\{)?'
    r'(?P<name>[^},]{1,80}?)'
    r'(?:\}\s*)?'
    r'[^.]{0,400}?'
    r'(?:is\s+defined\s+as|it\s+is\s+defined|defined\s+to\s+be|:=)'
    r'(?:[^.]*(?:' + _DISPLAY_MATH + r'))*'
    r'[^.]*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R25: we write X for ... namely  (we-write-for-namely)
# ---------------------------------------------------------------------------
inline_we_write_pattern = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9_\\(),.\s]{1,80}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin|\\section|\\subsection).){1,400}?'
    r'\bnamely\b'
    r'(?:(?!\\begin|\\section|\\subsection).){0,800}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# R26: display math + 'where' clause  (display-where)
# ---------------------------------------------------------------------------
# PRUNED — FP on paper004, paper006, paper009 +4 more | also 2 TP — review before uncommenting
# inline_display_where_pattern = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,300}?'
#     r'(?P<name>'
#     r'(?:the\s+)?[a-z][a-z\s]{2,60}?'
#     r'(?:norm|measure|metric|distance|kernel|cost|function|map|operator|'
#     r'space|matrix|bound|rate|set|quantity|value|estimator|distribution)'
#     r')'
#     r'[^$\\]{0,50}?'
#     r'[:\s]'
#     r'\s*'
#     r'(?:' + _DISPLAY_MATH + r')'
#     r'[^.]{0,400}?'
#     r'\bwhere\b'
#     r'[^.]{0,300}?\.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R27: Extended definition_keywords (for C4-style Let X be ... matching)
# ---------------------------------------------------------------------------
_DEFN_KEYWORDS_EXTENDED = re.compile(
    r'\b(set|function|map|mapping|sequence|matrix|space|operator|'
    r'define|denote|notation|collection|family|class|group|ring|field|'
    r'graph|path|tree|partition|permutation|morphism|homomorphism|'
    r'variable|random\s+variable|distribution|measure|process|transform|'
    r'vector|tensor|kernel|manifold|metric|norm|inner\s+product|'
    r'encoder|decoder|estimator|classifier|model|network|layer|algorithm|'
    r'cost|loss|objective|criterion|functional|probability|density|flow|'
    r'channel|code|scheme|procedure|construction|framework|system)\b',
    flags=re.IGNORECASE,
)

# Let X be ... (extended C4)
# PRUNED — FP on paper001, paper002, paper003 +6 more | also 5 TP — review before uncommenting
# inline_let_be_extended_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:Let|let)\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_]+))'
#     r'[^.]{0,300}?'
#     r'\s+be\s+'
#     r'(?:' + _DISPLAY_MATH + r'|[^.])*\.)',
#     flags=re.DOTALL,
# )

# ---------------------------------------------------------------------------
# R28: \section/\subsection paragraph with \emph term
# ---------------------------------------------------------------------------
_SECTION_HEADING = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*\}',
    flags=re.DOTALL,
)
_EM_TERM = re.compile(
    r'(?:\\emph\{(?P<name>[^}]{2,80})\}|\{\\em\s+(?P<name2>[^}]{2,80})\})',
)
_NEXT_BLOCK = re.compile(
    r'\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}',
)


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and a_end > b_start


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the longer one."""
    # Sort by start position, then by length (longer first)
    results.sort(key=lambda r: (r.get('_start', 0), -len(r.get('raw_latex', ''))))
    kept = []
    for r in results:
        rs = r.get('_start', 0)
        re_ = r.get('_end', rs + len(r.get('raw_latex', '')))
        dominated = False
        for k in kept:
            ks = k.get('_start', 0)
            ke = k.get('_end', ks + len(k.get('raw_latex', '')))
            if _overlaps(rs, re_, ks, ke):
                dominated = True
                break
        if not dominated:
            kept.append(r)
    return kept


def _make_result(raw_latex: str, name, env_name: str, rule_name: str,
                 start: int) -> dict:
    return {
        'raw_latex': raw_latex,
        'clean_text': _clean_latex(raw_latex),
        'name': name,
        'env_name': env_name,
        'rule_name': rule_name,
        'structure_type': 'definition',
        '_start': start,
        '_end': start + len(raw_latex),
    }


def _name_from_emph(text: str):
    """Extract first emphasized term from text."""
    m = re.search(
        r'(?:\\emph\{([^}]{1,80})\}|\\textbf\{([^}]{1,80})\}|'
        r'\\textit\{([^}]{1,80})\}|\{\\em\s+([^}]{1,80})\}|\{\\bf\s+([^}]{1,80})\})',
        text,
    )
    if m:
        return next(g for g in m.groups() if g is not None)
    return None


def _name_from_math(text: str):
    """Extract first inline math token as name hint."""
    m = re.search(r'\$([^$]{1,60})\$', text)
    return m.group(1) if m else None


def _normalize_name(raw: str) -> str:
    if not raw:
        return ''
    # Remove LaTeX commands
    raw = re.sub(r'\\[a-zA-Z]+\*?', ' ', raw)
    raw = re.sub(r'[{}$]', '', raw)
    raw = re.sub(r'\s+', ' ', raw)
    return raw.strip()[:120]


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX text using supplementary rules.
    Returns list of dicts, each with structure_type='definition'.
    """
    results: List[dict] = []
    excluded = _build_excluded_ranges(text)

    def _skip(start: int, end: int, full_text: str) -> bool:
        if _inside_excluded_env(start, end, excluded):
            return True
        if _REFERENTIAL.search(full_text):
            return True
        return False

    # ------------------------------------------------------------------
    # R1: {\bf Term:} ... block
#     # ------------------------------------------------------------------
#     for m in inline_bf_term_pattern.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _skip(m.start(), m.end(), full):
#             continue
#         name = _normalize_name(name_raw) or _normalize_name(_name_from_emph(full) or _name_from_math(full) or '')
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_bf_term_pattern', m.start()))

    # ------------------------------------------------------------------
    # R2: \emph{term}; ... is/are ...
    # ------------------------------------------------------------------
    for m in inline_emph_semi_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        semi_pos = full.find(';')
        if semi_pos < 0:
            continue
        after_semi = full[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        name_raw = m.group('name') or m.group('name2') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_emph_semi_pattern', m.start()))

    # ------------------------------------------------------------------
    # R3: Denote by X ... / We will denote by X ...
#     # ------------------------------------------------------------------
#     for m in inline_denote_by_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         name_raw = m.group('name') or ''
#         name = _normalize_name(name_raw)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_denote_by_pattern', m.start()))

    # ------------------------------------------------------------------
    # R4: \emph{term} obeys/satisfies ... if ...
    # ------------------------------------------------------------------
    for m in inline_obeys_if_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        name_raw = m.group('name') or m.group('name2') or ''
        if not name_raw.strip():
            continue
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_obeys_if_pattern', m.start()))

    # ------------------------------------------------------------------
    # R5: X stands for / denotes / refers to Y
#     # ------------------------------------------------------------------
#     for m in inline_stands_for_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         name_raw = m.group('name') or ''
#         name = _normalize_name(name_raw)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_stands_for_pattern', m.start()))

    # ------------------------------------------------------------------
    # R6: Let X denote ...
#     # ------------------------------------------------------------------
#     for m in inline_let_denote_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         name_raw = m.group('name') or ''
#         name = _normalize_name(name_raw)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_let_denote_pattern', m.start()))

    # ------------------------------------------------------------------
    # R7: Imperative Introduce / Set at sentence start
    # ------------------------------------------------------------------
    for m in inline_imperative_pattern.finditer(text):
        full = m.group('full').strip()
        if not full:
            continue
        start = text.find(full, max(0, m.start() - 5))
        if start < 0:
            start = m.start()
        if _skip(start, start + len(full), full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_imperative_pattern', start))

    # ------------------------------------------------------------------
    # R8: (also called ALIAS) / (known as ALIAS) parenthetical
#     # ------------------------------------------------------------------
#     for m in inline_also_called_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         name_raw = m.group('name') or ''
#         name = _normalize_name(name_raw)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_also_called_pattern', m.start()))

    # ------------------------------------------------------------------
    # R9: Two-phase "is called" anchor
#     # ------------------------------------------------------------------
#     for anchor_m in _IS_CALLED_ANCHOR.finditer(text):
#         start_search = max(0, anchor_m.start() - 120)
#         prefix = text[start_search:anchor_m.start()]
#         cuts = [prefix.rfind('.')]
#         for mk in ('\n\n', '\\section', '\\subsection', '\\maketitle',
#                    '\\begin', '\\end', '\\item', '\\State', '\\par'):
#             p = prefix.rfind(mk)
#             if p >= 0:
#                 cuts.append(p + len(mk) - 1)
#         best = max(cuts)
#         name_start = start_search + (best + 1 if best >= 0 else 0)
#         name_text = text[name_start:anchor_m.start()].strip()
#         if not name_text or len(name_text) > 120:
#             continue
#         tail_m = _SENT_TAIL.match(text, anchor_m.end())
#         if not tail_m:
#             continue
#         full_text = text[name_start:tail_m.end()]
#         if _skip(name_start, tail_m.end(), full_text):
#             continue
#         name = _normalize_name(name_text)
#         results.append(_make_result(full_text, name or None, 'distilled',
#                                     '_IS_CALLED_ANCHOR', name_start))

    # ------------------------------------------------------------------
    # R10: We will refer to X as Y
#     # ------------------------------------------------------------------
#     for m in inline_refer_to_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         name_raw = m.group('name') or ''
#         name = _normalize_name(name_raw)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_refer_to_pattern', m.start()))

    # ------------------------------------------------------------------
    # R11: Let us introduce [a/an/the] <name>
    # ------------------------------------------------------------------
    for m in inline_let_us_introduce_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_let_us_introduce_pattern', m.start()))

    # ------------------------------------------------------------------
    # R12: called a \emph{Name} / called the \emph{Name}
#     # ------------------------------------------------------------------
#     for m in inline_called_emph_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         if not _CALLED_EMPH_DEFN_KW.search(full):
#             continue
#         name_raw = m.group('name') or ''
#         name = _normalize_name(name_raw)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_called_emph_pattern', m.start()))

    # ------------------------------------------------------------------
    # R13: we consider ... of the form \begin{equation}
    # ------------------------------------------------------------------
    for m in inline_of_the_form_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        if not _OF_THE_FORM_MATH.search(full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_of_the_form_pattern', m.start()))

    # ------------------------------------------------------------------
    # R14: We introduce X as $$...$$ / \begin{equation}
    # ------------------------------------------------------------------
    for m in inline_introduce_as_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_introduce_as_pattern', m.start()))

    # ------------------------------------------------------------------
    # R15: We define X as/by \begin{equation}
    # ------------------------------------------------------------------
    for m in inline_define_eqn_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        if _C1_NEGATIVE.search(full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_define_eqn_pattern', m.start()))

    # ------------------------------------------------------------------
    # R16: We can define the X \begin{equation} (no explicit connector)
#     # ------------------------------------------------------------------
#     for m in inline_define_direct_eqn_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         if _C1_NEGATIVE.search(full):
#             continue
#         name_raw = m.group('name') or ''
#         name = _normalize_name(name_raw)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_define_direct_eqn_pattern', m.start()))

    # ------------------------------------------------------------------
    # R17: A/An X is [property] if ... \begin{equation}
    # ------------------------------------------------------------------
    for m in inline_is_if_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_is_if_pattern', m.start()))

    # ------------------------------------------------------------------
    # R18: X is given by / defined by \begin{equation}  (two-phase)
#     # ------------------------------------------------------------------
#     for m in inline_is_given_by_pattern.finditer(text):
#         preamble = m.group('preamble')
#         mathblock = m.group('mathblock')
#         # Determine sentence start
#         sent_boundaries = list(_SENT_BOUNDARY.finditer(text, 0, m.start()))
#         if sent_boundaries:
#             sent_start = sent_boundaries[-1].end()
#         else:
#             sent_start = max(0, m.start() - 200)
#         full_text = text[sent_start: m.end()].strip()
#         start = text.find(full_text, sent_start)
#         if start < 0:
#             start = sent_start
#         if _skip(start, start + len(full_text), full_text):
#             continue
#         name_hint = _name_from_emph(preamble) or _name_from_math(preamble)
#         name = _normalize_name(name_hint or preamble.strip()[-80:])
#         results.append(_make_result(full_text, name or None, 'distilled',
#                                     'inline_is_given_by_pattern', start))

    # ------------------------------------------------------------------
    # R19: \emph{Name} + optional abbreviation + display math
    # ------------------------------------------------------------------
    for m in inline_emph_display_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        name_candidate = (m.group('name') or '').strip()
        if len(name_candidate) < 3:
            continue
        name = _normalize_name(name_candidate)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_emph_display_pattern', m.start()))

    # ------------------------------------------------------------------
    # R20: Colon-introduced display math definition
#     # ------------------------------------------------------------------
#     for m in inline_colon_display_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         # Extract name from first math in intro or emph
#         intro_part = full[:full.find(':') + 1] if ':' in full else full[:80]
#         name_hint = _name_from_emph(intro_part) or _name_from_math(intro_part)
#         name = _normalize_name(name_hint or '')
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_colon_display_pattern', m.start()))

    # ------------------------------------------------------------------
    # R21: we introduce ... call ... : + display equation
    # ------------------------------------------------------------------
    for m in inline_introduce_call_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_introduce_call_pattern', m.start()))

    # ------------------------------------------------------------------
    # R22: The <noun> is [given by] $$...$$ (noun + display math)
#     # ------------------------------------------------------------------
#     for m in inline_noun_display_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         name_candidate = (m.group('name') or '').strip()
#         if not name_candidate or len(name_candidate) < 3 or len(name_candidate) > 100:
#             continue
#         if re.match(
#             r'^(?:following|above|below|result|fact|situation|case|same|problem|'
#             r'question|answer|claim|argument|proof)$',
#             name_candidate,
#             re.IGNORECASE
#         ):
#             continue
#         name = _normalize_name(name_candidate)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_noun_display_pattern', m.start()))

    # ------------------------------------------------------------------
    # R23: Two-phase "are defined as" anchor (plural extend of C2)
    # ------------------------------------------------------------------
    for anchor_m in _ARE_DEFINED_ANCHOR.finditer(text):
        start_search = max(0, anchor_m.start() - 120)
        prefix = text[start_search:anchor_m.start()]
        cuts = [prefix.rfind('.')]
        for mk in ('\n\n', '\\section', '\\subsection', '\\maketitle',
                   '\\begin', '\\end', '\\item', '\\State', '\\par'):
            p = prefix.rfind(mk)
            if p >= 0:
                cuts.append(p + len(mk) - 1)
        best = max(cuts)
        name_start = start_search + (best + 1 if best >= 0 else 0)
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _SENT_TAIL.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _skip(name_start, tail_m.end(), full_text):
            continue
        name = _normalize_name(name_text)
        results.append(_make_result(full_text, name or None, 'distilled',
                                    '_ARE_DEFINED_ANCHOR', name_start))

    # ------------------------------------------------------------------
    # R24: is called \emph{X} ... and is defined as ...
    # ------------------------------------------------------------------
    for m in inline_called_defined_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_called_defined_pattern', m.start()))

    # ------------------------------------------------------------------
    # R25: We write X for ... namely
    # ------------------------------------------------------------------
    for m in inline_we_write_pattern.finditer(text):
        full = m.group('full')
        if _skip(m.start(), m.end(), full):
            continue
        name_raw = m.group('name') or ''
        name = _normalize_name(name_raw)
        results.append(_make_result(full, name or None, 'distilled',
                                    'inline_we_write_pattern', m.start()))

    # ------------------------------------------------------------------
    # R26: display math + 'where' clause
#     # ------------------------------------------------------------------
#     for m in inline_display_where_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         name_candidate = (m.group('name') or '').strip()
#         if not name_candidate or len(name_candidate) < 3:
#             continue
#         name = _normalize_name(name_candidate)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_display_where_pattern', m.start()))

    # ------------------------------------------------------------------
    # R27: Let X be ... (extended C4 with broader keywords)
#     # ------------------------------------------------------------------
#     for m in inline_let_be_extended_pattern.finditer(text):
#         full = m.group('full')
#         if _skip(m.start(), m.end(), full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if not _DEFN_KEYWORDS_EXTENDED.search(full):
#             continue
#         name_raw = m.group('name') or ''
#         name = _normalize_name(name_raw)
#         results.append(_make_result(full, name or None, 'distilled',
#                                     'inline_let_be_extended_pattern', m.start()))

    # ------------------------------------------------------------------
    # R28: Section/subsection paragraph containing \emph term
    # ------------------------------------------------------------------
    for sec_m in _SECTION_HEADING.finditer(text):
        para_start = sec_m.end()
        nb = _NEXT_BLOCK.search(text, para_start)
        para_end = nb.start() if nb else len(text)
        para_text = text[para_start:para_end].strip()
        if not para_text or len(para_text) < 60:
            continue
        em_m = _EM_TERM.search(para_text)
        if not em_m:
            continue
        if _inside_excluded_env(para_start, para_end, excluded):
            continue
        if _REFERENTIAL.search(para_text):
            continue
        name_raw = em_m.group('name') or em_m.group('name2') or ''
        name = _normalize_name(name_raw)
        actual_start = text.find(para_text[:40], para_start)
        if actual_start < 0:
            actual_start = para_start
        results.append(_make_result(para_text, name or None, 'distilled',
                                    '_SECTION_HEADING', actual_start))

    # ------------------------------------------------------------------
    # Final: strip internal keys and deduplicate
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    # Remove internal position keys before returning
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
