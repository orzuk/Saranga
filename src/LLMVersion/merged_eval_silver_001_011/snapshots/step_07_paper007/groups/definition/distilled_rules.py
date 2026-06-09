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
    text = re.sub(r'\\(?:emph|textbf|textit|mathrm|mathbf|mathit|mathcal|mathbb|text|mbox|hbox|vbox)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:label|ref|cite[a-zA-Z]*|eqref)\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    text = re.sub(r'\{\\(?:bf|it|em|rm|tt|sf|sc)\s+([^}]*)\}', r'\1', text)
    # Math display blocks
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]+\$', ' [MATH] ', text)
    # Remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})*', ' ', text)
    text = re.sub(r'[{}]', '', text)
    # Normalise whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments to exclude (proofs, theorems, etc. — not standalone definitions)
_EXCLUDED_ENV_NAMES = [
    'proof', 'Proof',
    'theorem', 'Theorem', 'thm',
    'lemma', 'Lemma', 'lem',
    'proposition', 'Proposition', 'prop',
    'corollary', 'Corollary', 'cor',
    'claim', 'Claim',
    'conjecture', 'Conjecture',
    'problem', 'Problem',
    'example', 'Example', 'exam',
    'exercise', 'Exercise',
    'remark', 'Remark', 'rem', 'note',
]

_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\}' +
    r'(.*?)' +
    r'\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_spans(text: str):
    """Return list of (start, end) spans that are inside excluded environments."""
    spans = []
    for m in _EXCLUDED_ENV_RE.finditer(text):
        spans.append((m.start(), m.end()))
    return spans


def _inside_excluded_env(start: int, end: int, excluded_spans) -> bool:
    for es, ee in excluded_spans:
        if start >= es and end <= ee:
            return True
        if start < ee and end > es:
            return True
    return False


# ---------------------------------------------------------------------------
# Referential / negative guards
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

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule: bold-labeled definition blocks  {\bf Name:} or \textbf{Name:}
# PRUNED — FP on paper001, paper002, paper003 +2 more | also 3 TP — review before uncommenting
# INLINE_BF_LABEL = re.compile(
#     r'(?P<full>'
#     r'(?:\{\\bf\s+|\{\\textbf\s+|\\textbf\{)'
#     r'(?P<name>[^}:]{1,120})'
#     r'(?::?\}|\}:?)'
#     r'[ \t]*(?:\\\\)?[ \t]*'
#     r'(?P<body>(?:[^\n]|\n(?!\s*\n)){20,1200}?)'
#     r')'
#     r'(?=\n[ \t]*\n|\{\\bf\s|\{\\textbf\s|\\textbf\{|\\\\[ \t]*\n|'
#     r'\\(?:sub)*section|\\begin|\\end\{document\})',
#     flags=re.DOTALL,
# )

# Rule: "X is called Y" definitional sentences
INLINE_IS_CALLED = re.compile(
    r'(?P<full>'
    r'(?P<name>[^.\n]{5,120}?)'
    r'\s+is\s+called\b'
    r'(?:[^.\n]|\n(?!\s*\n)){5,300}?'
    r'\.)',
    flags=re.DOTALL,
)

# Rule: "X (also called Y) is the expected ..." using parenthetical alias
# PRUNED — FP on paper001, paper002, paper003 +4 more | also 2 TP — review before uncommenting
# INLINE_THE_X_IS = re.compile(
#     r'(?P<full>'
#     r'(?:The\s+)?'
#     r'(?P<name>[A-Z][^.()\n]{2,80}?)'
#     r'(?:\s*\([^)\n]{1,80}\))?'
#     r'\s+(?:is|are)\s+the\s+'
#     r'(?:[^.\n]|\n(?!\s*\n)){20,400}?'
#     r'\.)',
#     flags=re.DOTALL,
# )

_THE_X_IS_KEYWORDS = re.compile(
    r'\b(expected|defined|denoted|refers?\s+to|known\s+as|'
    r'called|probability|distance|measure|number|set|function|matrix|'
    r'time|notion|concept|collection|procedure|algorithm)\b',
    flags=re.IGNORECASE,
)

# Rule: "X are defined as" (plural extension of C2)
INLINE_ARE_DEFINED_AS = re.compile(
    r'(?P<name>[^.\n]{5,150}?)'
    r'\s+are\s+defined\s+as\s*'
    r'(?P<body>'
    r'(?:\\ba.*?\\ea|'
    r'\\begin\{(?:align|equation|gather)\*?\}.*?\\end\{(?:align|equation|gather)\*?\}|'
    r'\\\[.*?\\\]|'
    r'\$\$.*?\$\$|'
    r'[^.]*?)'
    r'(?:[^.]*\.))',
    flags=re.DOTALL | re.IGNORECASE,
)

# Rule: "We will denote by X ..." style
# PRUNED — FP on paper004, paper007 | also 1 TP — review before uncommenting
# INLINE_DENOTE = re.compile(
#     r'(?P<full>'
#     r'(?:We\s+)?(?:will\s+)?(?:also\s+)?denote\s+by\s+'
#     r'(?P<name>(?:\$[^$\n]+\$|[A-Za-z0-9\\{}_^ ]{1,60}))'
#     r'(?:[^.\n]|\n(?!\s*\n)){5,400}?'
#     r'\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# Rule: "Denote by X ... \begin{equation*}...\end{equation*}"
INLINE_DENOTE_BY = re.compile(
    r'(?P<full>'
    r'\bDenote\s+by\s+'
    r'(?P<name>(?:\$[^$\n]+\$|[A-Za-z0-9\\_{} ]{1,60}))'
    r'(?:[^\n]|\n(?!\s*\n)){0,400}?'
    r'(?P<body>'
    r'\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r')'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: "Let $$ ... $$ denote ..."
# PRUNED — FP on paper003, paper006 | also 1 TP — review before uncommenting
# INLINE_LET_DENOTE = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$\$.*?\$\$|\$[^$\n]+\$))'
#     r'(?:[^\n]|\n(?!\s*\n)){0,300}?'
#     r'\bdenote\b'
#     r'(?:[^.\n]|\n(?!\s*\n)){0,200}?'
#     r'\.)',
#     flags=re.DOTALL,
# )

# Rule: "Introduce X ..." definitional imperative with display math
INLINE_INTRODUCE = re.compile(
    r'(?P<full>'
    r'\bIntroduce\b\s+'
    r'(?P<name>[^.$\n]{1,80}?)'
    r'(?P<body>'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}'
    r')'
    r'(?:[^.\n]|\n(?!\s*\n)){0,200}?'
    r'\.)',
    flags=re.DOTALL,
)

# Rule: "we introduce ... called <name>: \begin{equation*}..."
INLINE_INTRODUCE_CALLED = re.compile(
    r'(?P<full>'
    r'\bwe\s+introduce\b(?:[^\n]|\n(?!\s*\n)){0,150}?'
    r'(?:call(?:ed)?)\s+'
    r'(?:\{\\it\s+)?(?P<name>[^}.\n]{1,80})(?:\})?\s*:?\s*'
    r'(?P<body>'
    r'\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r')'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: "we consider <name> $$ ... $$" definitional
INLINE_WE_CONSIDER = re.compile(
    r'(?P<full>'
    r'\bwe\s+consider\b\s+'
    r'(?P<name>[^.$\n]{1,80}?)'
    r'(?P<body>'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\}'
    r')'
    r'(?:[^.\n]|\n(?!\s*\n)){0,300}?'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'X stands for ...'
INLINE_STANDS_FOR = re.compile(
    r'(?P<full>'
    r'(?:The\s+notation\s+)?'
    r'(?P<name>(?:\$[^$\n]+\$|\$\$[^$]+\$\$|[A-Za-z0-9\\_ ]{1,60}?))'
    r'\s+stands\s+for\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|(?:[^.\n]|\n(?!\s*\n)){0,400}?)'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'We define X as \begin{gather*}...\end{gather*}' (env body)
INLINE_DEFINE_ENV = re.compile(
    r'(?P<full>'
    r'(?:We\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^.\\]{1,80}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?P<body>\\begin\{[^}]*\}.*?\\end\{[^}]*\})'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'introduce X as $$...$$' or 'introduce X as \[...\]'
INLINE_INTRODUCE_AS = re.compile(
    r'(?P<full>'
    r'\bintroduce\s+'
    r'(?P<name>[^.\\]{1,80}?)'
    r'\s*(?:as|by|to\s+be|:=|=)\s*'
    r'(?P<body>'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{[^}]*\}.*?\\end\{[^}]*\}'
    r')'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'X is given by \begin{equation}...\end{equation}'
INLINE_GIVEN_BY = re.compile(
    r'(?P<name>(?:[^\n.]|\n(?!\s*\n)){5,150}?)'
    r'\s+is\s+given\s+by\s*\n?\s*'
    r'(?P<body>'
    r'\\begin\{(?:equation|align|gather|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|eqnarray)\*?\}'
    r'|\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: optimization problem sentence + \begin{equation} containing \defeq/\argmin
INLINE_OPTIM_PROBLEM = re.compile(
    r'(?P<name>(?:[^\n.]|\n(?!\s*\n)){5,200}?)'
    r'(?:optimization\s+problem|is\s+based\s+on(?:[^\n.]|\n(?!\s*\n)){0,100}?'
    r'solving(?:[^\n.]|\n(?!\s*\n)){0,60}?problem)'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'define/denote X via \begin{equation}...'
INLINE_DEFINE_VIA = re.compile(
    r'(?:we\s+)?(?:also\s+)?(?:define|denote)\s+'
    r'(?P<name>[^.\\\n]{1,120}?)'
    r'\s+via\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'we can define X \begin{equation*}...'
INLINE_DEFINE_EQ = re.compile(
    r'(?:we\s+)?(?:can\s+)?(?:also\s+)?define\s+'
    r'(?P<name>[^\\\n]{1,120}?)'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'X is <property> ... if ... we have \begin{equation*}...'
INLINE_PROPERTY_IF = re.compile(
    r'(?P<name>(?:[A-Z][^\n.]{0,80}?))'
    r'\s+is\s+(?:[^\n.]{0,120}?)\bif\b(?:[^\n.]{0,120}?)\bwe\s+have\b'
    r'\s*\n?\s*'
    r'(?P<body>\\begin\{(?:equation|align|gather)\*?\}.*?\\end\{(?:equation|align|gather)\*?\})',
    flags=re.DOTALL,
)

# Rule: 'X is \emph{term} if ...'
INLINE_EMPH_IF = re.compile(
    r'(?P<full>'
    r'(?P<name>(?:[^\n.]{5,100}?))'
    r'\s+is\s+\\emph\{[^}]+\}'
    r'(?:\s+with\s+respect\s+to\s+[^\n.]{0,80}?)?'
    r'\s+if\s+'
    r'(?:[^\n]|\n(?!\s*\n)){10,300}?'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'the \emph{term} [(abbrev)] [display-math-or-align-env]'
INLINE_EMPH_NAMED = re.compile(
    r'(?P<full>'
    r'(?:[^\n.]{0,120}?)'
    r'(?:the\s+)?\\emph\{(?P<name>[^}]{1,80})\}'
    r'(?:\s*\([^)\n]{1,20}\))?'
    r'\s*(?:'
    r'\$\$.*?\$\$'
    r'|\\\[.*?\\\]'
    r'|\\begin\{(?:align|equation|gather)\*?\}.*?\\end\{(?:align|equation|gather)\*?\}'
    r')'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'the <noun phrase> is $$ ... $$'
INLINE_NOUN_IS_FORMULA = re.compile(
    r'(?P<full>'
    r'[Tt]he\s+(?P<name>[a-zA-Z][^\n$]{1,80}?)\s+is\s*'
    r'(?P<body>'
    r'\\\[.*?\\\]'
    r'|\$\$.*?\$\$'
    r')'
    r'(?:[^\n.]*\.)?)',
    flags=re.DOTALL,
)

# Rule: '<Sentence ending with colon> $$ ... $$'
# PRUNED — FP on paper004, paper005, paper007 | also 3 TP — review before uncommenting
# INLINE_COLON_FORMULA = re.compile(
#     r'(?P<full>'
#     r'(?P<name>[A-Z][^\n:]{5,150}?):'
#     r'\s*(?:'
#     r'\\\[.*?\\\]'
#     r'|\$\$.*?\$\$'
#     r')'
#     r'(?:[^\n.]*\.)?)',
#     flags=re.DOTALL,
# )

# Rule: 'X obeys \emph{} property ...'
INLINE_OBEYS = re.compile(
    r'(?P<full>'
    r'(?:a\s+)?(?:\\emph\{(?P<emph_name>[^}]+)\}|\{\\em\s+(?P<em_name>[^}]+)\})'
    r'(?:[^\n.]|\n(?!\s*\n)){0,150}?'
    r'\bobeys\b'
    r'(?:[^\n.]|\n(?!\s*\n)){5,400}?'
    r'\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule: 'X is a/an [defined-noun]' — inline "is a" definition
# PRUNED — FP on paper001, paper002, paper003 +1 more | also 1 TP — review before uncommenting
# INLINE_IS_A = re.compile(
#     r'(?P<full>'
#     r'(?:\\emph\{(?P<emph_name>[^}]+)\}[^\n.;]{0,40}[;,]\s*)?'
#     r'(?P<name>[A-Za-z][A-Za-z0-9 \-]{1,60}?)'
#     r'\s+is\s+(?:a|an|the)\s+(?:given\s+)?'
#     r'(?:collection|set|sequence|map|mapping|function|family|class|space|operator|'
#     r'matrix|vector|graph|code|measure|distribution|process|transform|pair|triple|'
#     r'tuple|list|array|structure|object|element|member|subset|subspace|subgroup|'
#     r'ring|field|group|algebra|category|bundle|complex|chain|module|lattice|poset|'
#     r'order|relation|partition|cover|basis|frame|system|scheme|variety|manifold|'
#     r'surface|curve|form|tensor|functional|filter|ideal|kernel|image|homomorphism|'
#     r'isomorphism|automorphism|endomorphism|morphism|functor|limit|colimit|'
#     r'localization|completion|compactification|extension|deformation|homotopy|'
#     r'cohomology|homology|model|theory|language|formula|sentence|proof|argument|'
#     r'algorithm|procedure|protocol|strategy|policy|rule|criterion|condition|'
#     r'property|invariant|characteristic|feature|parameter|variable|constant|'
#     r'symbol|notation|abbreviation|term|notion|concept|definition)\b'
#     r'(?:[^\n.]|\n(?!\s*\n)){0,300}?'
#     r'\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# Rule: paragraph definitions right after \section/\subsection headers
# PRUNED — FP on paper001, paper002, paper003 +2 more | also 5 TP — review before uncommenting
# INLINE_SECTION_DEF = re.compile(
#     r'(?:\\(?:sub)*section\*?\{[^}]*\})'
#     r'(?:[ \t]*%[^\n]*\n)*'
#     r'[ \t]*(?:\\label\{[^}]*\})?\s*'
#     r'(?P<full>'
#     r'(?P<name>[^\n.]{1,120}?)'
#     r'(?:(?!\\(?:sub)*section|\\begin|\\end\{document\})[\s\S]){50,2000}?'
#     r')'
#     r'(?=\n[ \t]*\n|\\(?:sub)*section|\\begin|\\end\{document\})',
#     flags=re.DOTALL,
# )

_SECTION_DEF_KEYWORDS = re.compile(
    r'\b(define[sd]?|definition|notation|denote[sd]?|call|refer\s+to|known\s+as|'
    r'represent[s]?|consists?\s+of|form\s+of\s+the|we\s+(?:say|use|write))\b',
    flags=re.IGNORECASE,
)

# Rule: 'A subset X is called' multi-sentence block (connectivity/partition defs)
INLINE_SUBSET_IS_CALLED = re.compile(
    r'(?P<full>'
    r'(?P<name>A\s+(?:subset|set|collection|family|class|group|sequence|pair)'
    r'[^\n.]{5,120}?)'
    r'\s+is\s+(?:called|defined\s+as|said\s+to\s+be)\b'
    r'(?:[^\n]|\n(?!\s*\n)){10,600}?'
    r'\.)',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove overlapping/duplicate matches; keep longer/earlier match."""
    if not results:
        return results
    # Sort by start position
    results.sort(key=lambda d: d.get('_start', 0))
    deduped = []
    for r in results:
        rs = r.get('_start', 0)
        re_ = r.get('_end', rs + len(r.get('raw_latex', '')))
        dominated = False
        for kept in deduped:
            ks = kept.get('_start', 0)
            ke = kept.get('_end', ks + len(kept.get('raw_latex', '')))
            # Overlap check
            if rs < ke and re_ > ks:
                overlap = min(re_, ke) - max(rs, ks)
                min_len = min(re_ - rs, ke - ks)
                if min_len > 0 and overlap / min_len > 0.5:
                    dominated = True
                    break
        if not dominated:
            deduped.append(r)
    for r in deduped:
        r.pop('_start', None)

    return deduped


def _make_result(raw_latex: str, name, env_name: str, rule_name: str,
                 start: int, end: int) -> dict:
    return {
        'raw_latex': raw_latex,
        'clean_text': _clean_latex(raw_latex),
        'name': name,
        'env_name': env_name,
        'rule_name': rule_name,
        'structure_type': 'definition',
        '_start': start,
        '_end': end,
    }


def _extract_name(text: str) -> str:
    """Extract a short name hint from a raw LaTeX fragment."""
    text = text.strip()
    # Prefer inline math
    m = re.search(r'\$([^$]+)\$', text)
    if m:
        return m.group(1)[:80]
    # Strip LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\s*', '', text)
    text = re.sub(r'[{}]', '', text)
    return text[:80].strip()


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    results: List[dict] = []
    excluded_spans = _build_excluded_spans(text)

    def _add(raw: str, name_raw, rule_name: str, start: int, end: int):
        if _inside_excluded_env(start, end, excluded_spans):
            return
        name = _extract_name(name_raw) if name_raw else None
        results.append(_make_result(raw, name, 'distilled', rule_name, start, end))

    # ------------------------------------------------------------------
    # INLINE_BF_LABEL : {\bf Name:} body blocks
#     # ------------------------------------------------------------------
#     for m in INLINE_BF_LABEL.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name')
#         if _REFERENTIAL.search(full):
#             continue
#         _add(full, name_raw, 'INLINE_BF_LABEL', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_IS_CALLED : "X is called Y"
    # ------------------------------------------------------------------
    for m in INLINE_IS_CALLED.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_IS_CALLED', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_SUBSET_IS_CALLED : "A subset X is called/defined as ..."
    # ------------------------------------------------------------------
    for m in INLINE_SUBSET_IS_CALLED.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_SUBSET_IS_CALLED', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_THE_X_IS : "The X (also called Y) is the expected ..."
#     # ------------------------------------------------------------------
#     for m in INLINE_THE_X_IS.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name')
#         if not _THE_X_IS_KEYWORDS.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.end(), excluded_spans):
#             continue
#         if len(full) < 40:
#             continue
#         _add(full, name_raw, 'INLINE_THE_X_IS', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_ARE_DEFINED_AS : "X are defined as ..."
    # ------------------------------------------------------------------
    for m in INLINE_ARE_DEFINED_AS.finditer(text):
        name_raw = m.group('name').strip()
        body = m.group('body')
        full = m.group(0)
        if not name_raw or len(name_raw) > 150:
            continue
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_ARE_DEFINED_AS', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_DENOTE : "We will denote by X ..."
#     # ------------------------------------------------------------------
#     for m in INLINE_DENOTE.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name')
#         if _REFERENTIAL.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.end(), excluded_spans):
#             continue
#         _add(full, name_raw, 'INLINE_DENOTE', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_DENOTE_BY : "Denote by X ... \begin{equation}..."
#     # ------------------------------------------------------------------
#     for m in INLINE_DENOTE_BY.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name')
#         if _REFERENTIAL.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.end(), excluded_spans):
#             continue
#         _add(full, name_raw, 'INLINE_DENOTE_BY', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_LET_DENOTE : "Let $...$ denote ..."
#     # ------------------------------------------------------------------
#     for m in INLINE_LET_DENOTE.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name')
#         if _REFERENTIAL.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.end(), excluded_spans):
#             continue
#         _add(full, name_raw, 'INLINE_LET_DENOTE', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_INTRODUCE : "Introduce X $$ ... $$"
    # ------------------------------------------------------------------
    for m in INLINE_INTRODUCE.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_INTRODUCE', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_INTRODUCE_CALLED : "we introduce ... called <name>: \begin{equation}..."
    # ------------------------------------------------------------------
    for m in INLINE_INTRODUCE_CALLED.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_INTRODUCE_CALLED', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_WE_CONSIDER : "we consider <name> $$ ... $$"
    # ------------------------------------------------------------------
    for m in INLINE_WE_CONSIDER.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_WE_CONSIDER', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_STANDS_FOR : "X stands for ..."
    # ------------------------------------------------------------------
    for m in INLINE_STANDS_FOR.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_STANDS_FOR', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_DEFINE_ENV : "We define X as \begin{gather*}..."
    # ------------------------------------------------------------------
    for m in INLINE_DEFINE_ENV.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_DEFINE_ENV', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_INTRODUCE_AS : "introduce X as $$ ... $$"
    # ------------------------------------------------------------------
    for m in INLINE_INTRODUCE_AS.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_INTRODUCE_AS', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_GIVEN_BY : "X is given by \begin{equation}..."
    # ------------------------------------------------------------------
    for m in INLINE_GIVEN_BY.finditer(text):
        name_raw = m.group('name').strip()
        body = m.group('body')
        full = m.group(0)
        if not name_raw or len(name_raw) > 150:
            continue
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_GIVEN_BY', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_OPTIM_PROBLEM : optimization problem + \begin{equation} with \defeq
    # ------------------------------------------------------------------
    for m in INLINE_OPTIM_PROBLEM.finditer(text):
        body = m.group('body')
        if not re.search(r'\\(?:defeq|argmin|triangleq|coloneqq|in\\s*\\argmin)', body):
            continue
        full = m.group(0)
        name_raw = m.group('name').strip()
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_OPTIM_PROBLEM', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_DEFINE_VIA : "define/denote X via \begin{equation}..."
    # ------------------------------------------------------------------
    for m in INLINE_DEFINE_VIA.finditer(text):
        name_raw = m.group('name').strip()
        full = m.group(0)
        if not name_raw:
            continue
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_DEFINE_VIA', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_DEFINE_EQ : "we can define X \begin{equation*}..."
    # ------------------------------------------------------------------
    for m in INLINE_DEFINE_EQ.finditer(text):
        name_raw = m.group('name').strip()
        full = m.group(0)
        if not name_raw:
            continue
        if _C1_NEGATIVE.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_DEFINE_EQ', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_PROPERTY_IF : "X is <property> if ... we have \begin{equation*}..."
    # ------------------------------------------------------------------
    for m in INLINE_PROPERTY_IF.finditer(text):
        name_raw = m.group('name').strip()
        full = m.group(0)
        if not name_raw:
            continue
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_PROPERTY_IF', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_EMPH_IF : "X is \emph{term} if ..."
    # ------------------------------------------------------------------
    for m in INLINE_EMPH_IF.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_EMPH_IF', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_EMPH_NAMED : "the \emph{term} [(abbrev)] [display math]"
    # ------------------------------------------------------------------
    for m in INLINE_EMPH_NAMED.finditer(text):
        full = m.group('full')
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_EMPH_NAMED', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_NOUN_IS_FORMULA : "the <noun> is $$ ... $$"
    # ------------------------------------------------------------------
    for m in INLINE_NOUN_IS_FORMULA.finditer(text):
        full = m.group('full')
        if not re.search(r'\$\$|\\\[', full):
            continue
        name_raw = m.group('name')
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_NOUN_IS_FORMULA', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_COLON_FORMULA : "<sentence>: $$ ... $$"
#     # ------------------------------------------------------------------
#     for m in INLINE_COLON_FORMULA.finditer(text):
#         full = m.group('full')
#         if not re.search(r'\$\$|\\\[', full):
#             continue
#         name_raw = m.group('name')
#         if re.search(r'\\begin|\\end', name_raw):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.end(), excluded_spans):
#             continue
#         _add(full, name_raw, 'INLINE_COLON_FORMULA', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_OBEYS : "a \emph{term} obeys ..."
    # ------------------------------------------------------------------
    for m in INLINE_OBEYS.finditer(text):
        full = m.group('full')
        emph = m.group('emph_name') or m.group('em_name')
        name_raw = emph if emph else ''
        if _REFERENTIAL.search(full):
            continue
        if _inside_excluded_env(m.start(), m.end(), excluded_spans):
            continue
        _add(full, name_raw, 'INLINE_OBEYS', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_IS_A : "X is a/an <defined-noun> ..."
#     # ------------------------------------------------------------------
#     for m in INLINE_IS_A.finditer(text):
#         full = m.group('full')
#         emph = m.group('emph_name')
#         name_raw = emph if emph else m.group('name')
#         if _REFERENTIAL.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.end(), excluded_spans):
#             continue
#         _add(full, name_raw, 'INLINE_IS_A', m.start(), m.end())

    # ------------------------------------------------------------------
    # INLINE_SECTION_DEF : paragraph after \section header with def keywords
#     # ------------------------------------------------------------------
#     for m in INLINE_SECTION_DEF.finditer(text):
#         full = m.group('full').strip()
#         if not _SECTION_DEF_KEYWORDS.search(full):
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         if _inside_excluded_env(m.start(), m.end(), excluded_spans):
#             continue
#         if len(full) < 50:
#             continue
#         name_raw = m.group('name') if m.group('name') else full[:80]
#         _add(full, name_raw, 'INLINE_SECTION_DEF', m.start(), m.end())

    # ------------------------------------------------------------------
    # Deduplicate and clean up internal keys
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
