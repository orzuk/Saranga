import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very lightweight LaTeX -> plain-text cleaner."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common display math environments (replace with placeholder)
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}',
                  ' [MATH] ', text, flags=re.DOTALL)
    # Remove $$ ... $$
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove \[ ... \]
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math $ ... $
    text = re.sub(r'\$[^$]+\$', '[MATH]', text)
    # Remove \emph{...}, \textit{...}, \textbf{...}, \textrm{...}
    text = re.sub(r'\\(?:emph|textit|textbf|textrm|mathrm|mathbf|mathit)\{([^}]*)\}', r'\1', text)
    # Remove {\em ...}, {\bf ...}, {\it ...}
    text = re.sub(r'\{\\(?:em|bf|it|rm)\s+([^}]*)\}', r'\1', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \citep{...}, \citet{...}
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove \begin{...} \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove remaining LaTeX commands \cmd{...}
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining LaTeX commands \cmd
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Normalise whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments that should be masked out (definitions inside them are not
# standalone definitions we want to extract here).
_EXCLUDED_ENV_NAMES = (
    'theorem', 'Theorem', 'thm',
    'lemma', 'Lemma', 'lem',
    'proposition', 'Proposition', 'prop',
    'corollary', 'Corollary', 'cor',
    'claim', 'Claim',
    'conjecture', 'Conjecture',
    'problem', 'Problem',
    'proof', 'Proof',
    'example', 'Example', 'exam',
    'exercise', 'Exercise',
    'remark', 'Remark', 'rem',
    'note',
    'definition', 'Definition', 'defn', 'dfn', 'Def', 'Defn',
    'algorithm', 'figure', 'table',
)

_EXCL_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\}'
    r'.*?'
    r'\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) character ranges that are inside excluded environments."""
    ranges = []
    for m in _EXCL_ENV_RE.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if the span [start, end) overlaps any excluded range."""
    for (es, ee) in excluded_ranges:
        if start < ee and end > es:
            return True
    return False


def _extract_name_hint(raw: str) -> str:
    """Extract a plain-text name hint from a raw LaTeX string."""
    if not raw:
        return ''
    raw = raw.strip()
    # Prefer content of \emph{...} or \textbf{...}
    m = re.search(r'\\(?:emph|textbf|textit)\{([^}]{1,80})\}', raw)
    if m:
        return _clean_latex(m.group(1))[:80]
    # Prefer inline math
    m = re.search(r'\$([^$]{1,60})\$', raw)
    if m:
        return m.group(1).strip()[:80]
    return _clean_latex(raw)[:80]


# ---------------------------------------------------------------------------
# Referential / negative guard patterns (shared across rules)
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
# Compiled patterns (module-level — rule_name == variable name)
# ---------------------------------------------------------------------------

# C6: {\bf Term:} prose block
# PRUNED — FP on paper001, paper002, paper003 +3 more | also 3 TP — review before uncommenting
# INLINE_BF_TERM = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}:]{1,120}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,900}?)'
#     r'(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# C_EM_SECTION: paragraph after \section/\subsection containing {\em term}
_SECTION_HEADING = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*\}',
    flags=re.DOTALL,
)
_EM_TERM_IN_PARA = re.compile(
    r'(?:\{\\em\s+(?P<name>[^}]{2,80})\}'
    r'|\\(?:emph|textit)\{(?P<name2>[^}]{2,80})\})',
)
_NEXT_BLOCK = re.compile(
    r'\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}',
)

# C_ARE_DEFINED: 'are defined as/to be'
INLINE_ARE_DEFINED_AS = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)
# Tail after 'are defined as' – grabs up to the next sentence end
_C2_TAIL = re.compile(
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.',
    flags=re.DOTALL,
)

# C_ALSO_CALLED: (also called ALIAS) parenthetical
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# INLINE_ALSO_CALLED = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,150}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,300}?\.)',
#     flags=re.DOTALL,
# )

# C_EMPH_SEMI: \emph{term}; ... is/are ...
INLINE_EMPH_SEMI = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,160}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.]{0,400}\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C_DENOTE_BY: We (will) denote by X ...
# PRUNED — FP on paper002, paper004, paper007 | also 1 TP — review before uncommenting
# INLINE_DENOTE_BY = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+(?:will\s+)?|[Ll]et\s+us\s+)denote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,\s]{1,60}?))'
#     r'\s+(?:the\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# C_DENOTE_BY2: Denote by X ... (imperative, no 'We')
# PRUNED — FP on paper004
# INLINE_DENOTE_BY2 = re.compile(
#     r'(?P<full>'
#     r'[Dd]enote\s+by\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,.() ]{1,60}?))'
#     r'\s+'
#     r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
#     flags=re.DOTALL,
# )

# C_STANDS_FOR: X stands for / denotes / refers to
# PRUNED — FP on paper001, paper003, paper006 +1 more | also 2 TP — review before uncommenting
# INLINE_STANDS_FOR = re.compile(
#     r'(?P<full>'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]+?))'
#     r'\s+(?:stands\s+for|denotes|refers\s+to)\s+'
#     r'(?:the\s+|a\s+|an\s+)?'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# C_LET_DENOTE: Let X denote ...
# PRUNED — FP on paper004, paper006
# INLINE_LET_DENOTE = re.compile(
#     r'(?P<full>'
#     r'[Ll]et\s+'
#     r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_{} ,.]+?))'
#     r'\s+denote\s+'
#     r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
#     flags=re.DOTALL,
# )

# C_INTRODUCE_IMPERATIVE: Sentence-start 'Introduce ...' or 'Set ...'
INLINE_INTRODUCE_IMPERATIVE = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=[.\n]))\s*'
    r'(?:Introduce|Set)\s+'
    r'(?P<name>[^.\$\\]{1,100}?)'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    flags=re.DOTALL | re.MULTILINE,
)

# C_INTRODUCE_CALL: 'we introduce ... (that we will) call {\it NAME}:'
INLINE_INTRODUCE_CALL = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+introduce\s+'
    r'(?P<name>[^.]{1,140}?)'
    r'(?:that\s+we\s+(?:will\s+)?)?call\s+'
    r'(?:\{\\it\s+|\{\\emph\{|\\textit\{|\\emph\{)?'
    r'[^{}]{1,80}'
    r'(?:\}\}?)?\s*:'
    r'(?:\s*\\begin\{[a-zA-Z*]+\}.*?\\end\{[a-zA-Z*]+\}'
    r'|\s*\$\$.*?\$\$'
    r'|\s*\\\[.*?\\\]))',
    flags=re.DOTALL,
)

# C_WE_WRITE_FOR: 'we write X for Y, namely ...'
INLINE_WE_WRITE = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+write\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9_\\(),.\s]{1,60}?))'
    r'\s+for\s+'
    r'(?:(?!\\begin\{|\\section\b|\\subsection\b).){1,400}?'
    r'\bnamely\b'
    r'(?:(?!\\begin\{|\\section\b|\\subsection\b).){0,600}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C_DEFINE_ENV: 'We define X as \begin{env}...\end{env}'
# PRUNED — FP on paper001, paper006 | also 3 TP — review before uncommenting
# INLINE_DEFINE_ENV = re.compile(
#     r'(?P<full>'
#     r'(?:[Ww]e\s+)?(?:also\s+)?define\s+'
#     r'(?P<name>[^.\\]{1,100}?)'
#     r'\s*(?:as|by|to\s+be|:=|=|via)\s*'
#     r'(?:[^\\]|\\(?!begin))*?'
#     r'(?P<envbody>\\begin\{(?P<envn>[a-zA-Z*]+)\}.*?\\end\{(?P=envn)\})'
#     r')',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# C_INTRODUCE_AS: 'we (can) introduce X as $$...$$'
INLINE_INTRODUCE_AS = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+(?:can\s+)?(?:also\s+)?introduce\s+'
    r'(?P<name>[^.]{1,100}?)'
    r'\s+as\s+'
    r'(?:[^$]|\$(?!\$))*?'
    r'(?P<math>\$\$.*?\$\$)'
    r'(?:[^.]*\.)?'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# C_IS_GIVEN_BY_EQN: 'X is given by \begin{equation}'
# PRUNED — FP on paper002, paper004 | also 1 TP — review before uncommenting
# INLINE_IS_GIVEN_BY = re.compile(
#     r'(?P<preamble>[^.\n]{0,250}?\b(?:is\s+given|is\s+defined)\s+by\s*)'
#     r'(?P<body>\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})',
#     flags=re.DOTALL,
# )

# C_NOUN_DISPLAY: 'the <noun> is\n$$...$$'
# PRUNED — FP on paper002, paper004
# INLINE_NOUN_DISPLAY = re.compile(
#     r'(?P<full>'
#     r'(?:Given[^,\n]{0,120},\s*)?'
#     r'(?:the|The)\s+'
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

# C_EMPH_IF: '...is \emph{property} if <condition>.'
INLINE_EMPH_IF = re.compile(
    r'(?P<full>'
    r'[A-Z][^.\n]{0,150}?'
    r'\\(?:emph|textbf|textit)\{(?P<name>[^}]{1,80})\}'
    r'[^.\n]{0,250}?'
    r'\b(?:if|when|provided|whenever)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C_EMPH_DISPLAY: '\emph{term} (ABBREV) followed by display math'
INLINE_EMPH_DISPLAY = re.compile(
    r'(?P<full>'
    r'[^\n.]{0,200}?'
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

# C_DISPLAY_WHERE: 'the <math-noun> ... $$...$$ ... where ...'
# PRUNED — FP on paper004, paper006, paper009 | also 1 TP — review before uncommenting
# INLINE_DISPLAY_WHERE = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.\n]{0,250}?'
#     r'(?P<name>'
#     r'(?:the\s+)?[a-z][a-z\s]{2,60}?'
#     r'(?:norm|measure|metric|distance|kernel|cost|function|map|operator|space|matrix|bound|rate|set)'
#     r')'
#     r'[^$\\\n]{0,50}?'
#     r'[:\s]'
#     r'\s*'
#     r'(?:'
#     r'\$\$.*?\$\$'
#     r'|\\\[.*?\\\]'
#     r'|\\begin\{(?:align|equation|gather|multline)\*?\}.*?\\end\{(?:align|equation|gather|multline)\*?\}'
#     r')'
#     r'[^.]{0,400}?'
#     r'\bwhere\b'
#     r'[^.]{0,300}?\.)',
#     flags=re.DOTALL,
# )

# C_A_IS_IF_EQN: 'A/An X is [property] if ... \begin{equation}...'
INLINE_A_IS_IF_EQN = re.compile(
    r'(?P<full>'
    r'(?:A|An)\s+'
    r'(?P<name>[A-Za-z][^.\n]{2,120}?)'
    r'\s+is\s+[^.\n]{2,150}?\s+if\s+'
    r'[^.\n]{0,250}?'
    r'(?:\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\})'
    r')',
    flags=re.DOTALL,
)

# C_OBEYS_IF: '\emph{term} obeys/satisfies ... if ...'
INLINE_OBEYS_IF = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.]{0,150}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$'
    r'|\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|[^.]){0,500}?'
    r'\bif\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$'
    r'|\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}'
    r'|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C_WE_CONSIDER_DENOTE: 'we consider X ... and let Y denote ...'
INLINE_WE_CONSIDER_DENOTE = re.compile(
    r'(?P<full>'
    r'[Ww]e\s+consider\s+'
    r'(?P<name>[^.]{1,100}?)'
    r'\s*(?:[.,]|\.{3})\s*'
    r'(?:and\s+)?let\s+[^.]{1,100}?\s+denote\s+'
    r'(?:\$\$.*?\$\$|\\\[.*?\\\]|[^.])*\.)',
    flags=re.DOTALL,
)

# Sentence boundary finder (used for the 'is given by' rule)
_SENT_BOUNDARY = re.compile(r'[.!?]\s+|\n\s*\n', flags=re.DOTALL)

# ---------------------------------------------------------------------------
# Helper: deduplicate results by overlap
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex span overlaps a higher-priority kept result."""
    if not results:
        return results
    # Sort by length of raw_latex descending (longer = more specific → keep first)
    results_sorted = sorted(results, key=lambda r: len(r.get('raw_latex', '')), reverse=True)
    kept = []
    kept_texts = []
    for r in results_sorted:
        rt = (r.get('raw_latex') or '').strip()
        if not rt:
            kept.append(r)
            continue
        duplicate = False
        for kt in kept_texts:
            # If either contains the other as substring, it's a dup
            if rt in kt or kt in rt:
                duplicate = True
                break
            # Also check first-30-char prefix overlap
            minl = min(len(rt), len(kt))
            if minl > 30 and rt[:30] == kt[:30]:
                duplicate = True
                break
        if not duplicate:
            kept.append(r)
            kept_texts.append(rt)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX source text that are NOT already
    caught by the base parser's _extract_definitions_manual method.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    excluded_ranges = _build_excluded_ranges(text)

    def _make(raw_latex: str, name_raw: str, rule_name: str, source_pos: int) -> dict:
        name_hint = _extract_name_hint(name_raw) if name_raw else None
        return {
            'raw_latex': raw_latex,
            'clean_text': _clean_latex(raw_latex),
            'name': name_hint or None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
        }

    def _add(raw_latex: str, name_raw: str, rule_name: str, source_pos: int):
        if not raw_latex or len(raw_latex.strip()) < 15:
            return
        if _inside_excluded_env(source_pos, source_pos + len(raw_latex), excluded_ranges):
            return
        if _REFERENTIAL.search(raw_latex):
            return
        results.append(_make(raw_latex, name_raw, rule_name, source_pos))

    # ------------------------------------------------------------------
    # Rule: INLINE_BF_TERM  {\bf Term:} prose
#     # ------------------------------------------------------------------
#     for m in INLINE_BF_TERM.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if not name_raw.strip():
#             continue
#         _add(full, name_raw, 'INLINE_BF_TERM', m.start())

    # ------------------------------------------------------------------
    # Rule: C_EM_SECTION  paragraph after \section containing {\em term}
    # ------------------------------------------------------------------
    for sec_m in _SECTION_HEADING.finditer(text):
        para_start = sec_m.end()
        nb = _NEXT_BLOCK.search(text, para_start)
        para_end = nb.start() if nb else len(text)
        para_text = text[para_start:para_end].strip()
        if not para_text or len(para_text) < 40:
            continue
        em_m = _EM_TERM_IN_PARA.search(para_text)
        if not em_m:
            continue
        if _inside_excluded_env(para_start, para_end, excluded_ranges):
            continue
        if _REFERENTIAL.search(para_text):
            continue
        name_hint = (em_m.group('name') or em_m.group('name2') or '').strip()
        results.append({
            'raw_latex': para_text,
            'clean_text': _clean_latex(para_text),
            'name': name_hint or None,
            'env_name': 'distilled',
            'rule_name': 'C_EM_SECTION',
            'structure_type': 'definition',
        })

    # ------------------------------------------------------------------
    # Rule: INLINE_ARE_DEFINED_AS  'are defined as/to be'
    # (extends base C2 which only covers singular 'is defined as')
    # ------------------------------------------------------------------
    for anchor_m in INLINE_ARE_DEFINED_AS.finditer(text):
        start_search = max(0, anchor_m.start() - 100)
        prefix = text[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        name_start = (start_search + dot_pos + 1) if dot_pos >= 0 else start_search
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _C2_TAIL.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _inside_excluded_env(name_start, tail_m.end(), excluded_ranges):
            continue
        if _REFERENTIAL.search(full_text):
            continue
        results.append({
            'raw_latex': full_text,
            'clean_text': _clean_latex(full_text),
            'name': _extract_name_hint(name_text),
            'env_name': 'distilled',
            'rule_name': 'INLINE_ARE_DEFINED_AS',
            'structure_type': 'definition',
        })

    # ------------------------------------------------------------------
    # Rule: INLINE_ALSO_CALLED  '(also called ALIAS)'
#     # ------------------------------------------------------------------
#     for m in INLINE_ALSO_CALLED.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         _add(full, name_raw, 'INLINE_ALSO_CALLED', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_EMPH_SEMI  \emph{term}; ... is/are ...
    # ------------------------------------------------------------------
    for m in INLINE_EMPH_SEMI.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or m.group('name2') or ''
        # require 'is' or 'are' after the semicolon
        semi_pos = full.find(';')
        if semi_pos < 0:
            continue
        after_semi = full[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        _add(full, name_raw, 'INLINE_EMPH_SEMI', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_DENOTE_BY  'We (will) denote by X ...'
#     # ------------------------------------------------------------------
#     for m in INLINE_DENOTE_BY.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _C1_NEGATIVE.search(full):
#             continue
#         _add(full, name_raw, 'INLINE_DENOTE_BY', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_DENOTE_BY2  'Denote by X ...' (imperative)
#     # ------------------------------------------------------------------
#     for m in INLINE_DENOTE_BY2.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _C1_NEGATIVE.search(full):
#             continue
#         _add(full, name_raw, 'INLINE_DENOTE_BY2', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_STANDS_FOR  'X stands for / denotes / refers to'
#     # ------------------------------------------------------------------
#     for m in INLINE_STANDS_FOR.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _C1_NEGATIVE.search(full):
#             continue
#         _add(full, name_raw, 'INLINE_STANDS_FOR', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_LET_DENOTE  'Let X denote ...'
#     # ------------------------------------------------------------------
#     for m in INLINE_LET_DENOTE.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _C1_NEGATIVE.search(full):
#             continue
#         _add(full, name_raw, 'INLINE_LET_DENOTE', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_INTRODUCE_IMPERATIVE  'Introduce ...' / 'Set ...' at sent. start
    # ------------------------------------------------------------------
    for m in INLINE_INTRODUCE_IMPERATIVE.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        if _C1_NEGATIVE.search(full):
            continue
        _add(full, name_raw, 'INLINE_INTRODUCE_IMPERATIVE', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_INTRODUCE_CALL  'we introduce ... call {\it NAME}:'
    # ------------------------------------------------------------------
    for m in INLINE_INTRODUCE_CALL.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        _add(full, name_raw, 'INLINE_INTRODUCE_CALL', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_WE_WRITE  'we write X for Y, namely ...'
    # ------------------------------------------------------------------
    for m in INLINE_WE_WRITE.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        _add(full, name_raw, 'INLINE_WE_WRITE', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_DEFINE_ENV  'We define X as \begin{env}...\end{env}'
#     # ------------------------------------------------------------------
#     for m in INLINE_DEFINE_ENV.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _C1_NEGATIVE.search(full):
#             continue
#         _add(full, name_raw, 'INLINE_DEFINE_ENV', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_INTRODUCE_AS  'we can introduce X as $$...$$'
    # ------------------------------------------------------------------
    for m in INLINE_INTRODUCE_AS.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        _add(full, name_raw, 'INLINE_INTRODUCE_AS', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_IS_GIVEN_BY  'X is given by \begin{equation}...'
#     # ------------------------------------------------------------------
#     for m in INLINE_IS_GIVEN_BY.finditer(text):
#         preamble = m.group('preamble')
#         body = m.group('body')
#         # find start of sentence
#         sent_boundaries = list(_SENT_BOUNDARY.finditer(text, 0, m.start()))
#         if sent_boundaries:
#             sent_start = sent_boundaries[-1].end()
#         else:
#             sent_start = max(0, m.start() - 250)
#         full_text = text[sent_start: m.end()].strip()
#         name_raw_text = text[sent_start: m.start()].strip()
#         if not full_text or len(full_text) < 15:
#             continue
#         if _inside_excluded_env(sent_start, m.end(), excluded_ranges):
#             continue
#         if _REFERENTIAL.search(full_text):
#             continue
#         # Extract name from emphasis in preamble
#         emph_m = re.search(r'\\(?:emph|textbf|textit)\{([^}]+)\}', name_raw_text)
#         name_hint = _extract_name_hint(emph_m.group(1) if emph_m else name_raw_text[-80:])
#         results.append({
#             'raw_latex': full_text,
#             'clean_text': _clean_latex(full_text),
#             'name': name_hint or None,
#             'env_name': 'distilled',
#             'rule_name': 'INLINE_IS_GIVEN_BY',
#             'structure_type': 'definition',
#         })

    # ------------------------------------------------------------------
    # Rule: INLINE_NOUN_DISPLAY  'the <noun> is $$...$$'
    # ------------------------------------------------------------------
    _GENERIC_NAMES = re.compile(
        r'^(?:following|above|below|result|fact|situation|case|proof|idea)$',
        re.IGNORECASE,
    )
#     for m in INLINE_NOUN_DISPLAY.finditer(text):
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         name_raw = name_raw.strip()
#         if not name_raw or len(name_raw) < 3 or len(name_raw) > 100:
#             continue
#         if _GENERIC_NAMES.match(name_raw):
#             continue
#         _add(full, name_raw, 'INLINE_NOUN_DISPLAY', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_EMPH_IF  '...is \emph{property} if <condition>.'
    # ------------------------------------------------------------------
    for m in INLINE_EMPH_IF.finditer(text):
        full = m.group('full')
        name_candidate = (m.group('name') or '').strip()
        if len(name_candidate) < 3:
            continue
        _add(full, name_candidate, 'INLINE_EMPH_IF', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_EMPH_DISPLAY  '\emph{name} (ABBREV) followed by display math'
    # ------------------------------------------------------------------
    for m in INLINE_EMPH_DISPLAY.finditer(text):
        full = m.group('full')
        name_candidate = (m.group('name') or '').strip()
        if len(name_candidate) < 3:
            continue
        _add(full, name_candidate, 'INLINE_EMPH_DISPLAY', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_DISPLAY_WHERE  '<math-noun> ... $$...$$ ... where ...'
#     # ------------------------------------------------------------------
#     for m in INLINE_DISPLAY_WHERE.finditer(text):
#         full = m.group('full')
#         name_raw = (m.group('name') or '').strip()
#         if not name_raw or len(name_raw) < 3:
#             continue
#         _add(full, name_raw, 'INLINE_DISPLAY_WHERE', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_A_IS_IF_EQN  'A/An X is [property] if ... \begin{equation}'
    # ------------------------------------------------------------------
    for m in INLINE_A_IS_IF_EQN.finditer(text):
        full = m.group('full')
        name_raw = (m.group('name') or '').strip()
        if not name_raw or len(name_raw) < 3:
            continue
        _add(full, name_raw, 'INLINE_A_IS_IF_EQN', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_OBEYS_IF  '\emph{term} obeys/satisfies ... if ...'
    # ------------------------------------------------------------------
    for m in INLINE_OBEYS_IF.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or m.group('name2') or ''
        if not name_raw.strip():
            continue
        _add(full, name_raw, 'INLINE_OBEYS_IF', m.start())

    # ------------------------------------------------------------------
    # Rule: INLINE_WE_CONSIDER_DENOTE  'we consider X ... and let Y denote ...'
    # ------------------------------------------------------------------
    for m in INLINE_WE_CONSIDER_DENOTE.finditer(text):
        full = m.group('full')
        name_raw = m.group('name') or ''
        _add(full, name_raw, 'INLINE_WE_CONSIDER_DENOTE', m.start())

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    return results
