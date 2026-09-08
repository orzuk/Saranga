import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return approximate plain text."""
    # Remove comments
    t = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments
    t = re.sub(r'\\begin\{(?:equation|align|eqnarray|array|ba|gather)\*?\}.*?\\end\{(?:equation|align|eqnarray|array|ba|gather)\*?\}', ' ... ', t, flags=re.DOTALL)
    # Remove \[ ... \] and $$ ... $$
    t = re.sub(r'\\\[.*?\\\]', ' ... ', t, flags=re.DOTALL)
    t = re.sub(r'\$\$.*?\$\$', ' ... ', t, flags=re.DOTALL)
    # Inline math $...$ → keep content
    t = re.sub(r'\$([^$]{1,120})\$', r'\1', t)
    # Remove \emph{X}, \textbf{X}, \textit{X}, \text{X} → X
    for cmd in ('emph', 'textbf', 'textit', 'textrm', 'text', 'mathrm'):
        t = re.sub(r'\\' + cmd + r'\{([^}]*)\}', r'\1', t)
    # Remove {\em X} → X, {\bf X} → X, {\it X} → X
    t = re.sub(r'\{\\(?:em|bf|it|rm)\s+([^}]*)\}', r'\1', t)
    # Remove \cite{...}, \ref{...}, \label{...}, \eqref{...}
    t = re.sub(r'\\(?:cite[A-Za-z]*|ref|label|eqref|autoref)\{[^}]*\}', '', t)
    # Remove \section, \subsection etc headings
    t = re.sub(r'\\(?:sub)*section\*?\{[^}]*\}', '', t)
    # Remove remaining LaTeX commands with arguments
    t = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', ' ', t)
    # Remove remaining LaTeX commands
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    # Remove braces
    t = re.sub(r'[{}]', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


# Environments that should be masked out (not re-matched as definitions)
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop'
    r'|corollary|Corollary|cor|claim|Claim|conjecture|Conjecture|proof|Proof'
    r'|example|Example|exam|remark|Remark|rem|note|exercise|Exercise)\}',
    flags=re.IGNORECASE,
)

_EXCLUDED_ENV_FULL = re.compile(
    r'\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop'
    r'|corollary|Corollary|cor|claim|Claim|conjecture|Conjecture|proof|Proof'
    r'|example|Example|exam|remark|Remark|rem|note|exercise|Exercise)\}'
    r'.*?\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_ranges(text: str):
    """Return list of (start, end) ranges for excluded environments."""
    ranges = []
    for m in _EXCLUDED_ENV_FULL.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if [start, end) overlaps any excluded range."""
    for (es, ee) in excluded_ranges:
        if start < ee and end > es:
            return True
    return False


def _build_masked_text(text: str, excluded_ranges) -> str:
    """Replace excluded environment bodies with spaces."""
    chars = list(text)
    for (es, ee) in excluded_ranges:
        for i in range(es, min(ee, len(chars))):
            chars[i] = ' '
    return ''.join(chars)


# ---------------------------------------------------------------------------
# Referential / negative patterns (shared guards)
# ---------------------------------------------------------------------------

_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph)|'
    r'as\s+(?:before|above|below|follows|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition|the\s+previous))\b',
    flags=re.IGNORECASE,
)

_NEGATIVE_DEFINE = re.compile(
    r'\b(?:in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'defined\s+(?:above|below|earlier|previously|in\s+Section|in\s+Theorem|'
    r'in\s+Lemma|in\s+Equation|in\s+Definition))\b',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# C_BF_TERM: {\bf Term:} or {\bf Term} followed by definitional prose
# Covers bold-labeled concept introductions like {\bf The foo graph:} Here we...
# PRUNED — FP on paper001, paper002, paper003 | also 3 TP — review before uncommenting
# C_BF_TERM = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}]{1,120}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){15,1200}?)'
#     r'(?=\\\\\s*(?:\n|$)|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}|\\paragraph\b)'
#     r')',
#     flags=re.DOTALL,
# )

# C_TEXTBF_TERM: \textbf{Term:} followed by definitional prose
# PRUNED — FP on paper002, paper003
# C_TEXTBF_TERM = re.compile(
#     r'(?P<full>'
#     r'\\textbf\{(?P<name>[^}]{1,120}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\\textbf\{).){15,1200}?)'
#     r'(?=\\\\\s*(?:\n|$)|\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}|\\paragraph\b)'
#     r')',
#     flags=re.DOTALL,
# )

# C_EM_SECTION: paragraph after \section/\subsection containing {\em term} or \emph{term}
# Used for concept introductions following section headings
C_EM_SECTION_HEADING = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*\}',
    flags=re.DOTALL,
)

C_EM_TERM_IN_PARA = re.compile(
    r'(?:\{\\em\s+(?P<name>[^}]{2,80})\}|\\emph\{(?P<name2>[^}]{2,80})\})',
)

_PARA_END = re.compile(
    r'\n\s*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}|\\paragraph\b',
)

# C_ARE_DEFINED_AS: plural "are defined as/to be" anchor (complement to base C2)
C_ARE_DEFINED_AS = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)

_C2_TAIL = re.compile(
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.',
    flags=re.DOTALL,
)

# C_ALSO_CALLED: parenthetical "(also called X)" or "(known as X)" definitional pattern
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# C_ALSO_CALLED = re.compile(
#     r'(?P<full>'
#     r'(?:[A-Z][^.]{0,200}?)'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)'
#     r'[^.]{0,400}?\.)',
#     flags=re.DOTALL,
# )

# C_DENOTE_BY: "We (will) denote by X ..." or "Let us denote by X ..."
C_DENOTE_BY = re.compile(
    r'(?P<full>'
    r'(?:(?:We\s+(?:will\s+)?)|(?:[Ll]et\s+us\s+))'
    r'denote\s+by\s+'
    r'(?P<name>(?:\$[^$]{1,60}\$|[A-Za-z0-9\\{}_^,\s]{1,60}?))'
    r'(?:\s+the\s+|\s+)'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C_EMPH_SEMI: \emph{term}; ... is/are ... — em-introduced term defined after semicolon
C_EMPH_SEMI = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,200}?;\s*'
    r'(?:a\s+|an\s+|the\s+)?\w[^.]{0,400}\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C_OBEYS_IF: '{\em term} obeys/satisfies ... if ...' — definitional condition
C_OBEYS_IF = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.]{0,200}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){0,600}?'
    r'\bif\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){0,400}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C_CALLED_NAMED: 'X is called/named "Y"' — naming pattern
C_CALLED_NAMED = re.compile(
    r'(?P<full>'
    r'(?:[A-Z][^.]{5,200}?)'
    r'\bis\s+(?:called|named)\s+'
    r'(?:the\s+|a\s+|an\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\}'
    r'|\\textit\{(?P<name3>[^}]{1,80})\}'
    r'|["\u201c](?P<name4>[^""\u201d]{1,80})["\u201d]'
    r'|(?P<name5>[A-Z][A-Za-z\s\-]{1,60}))'
    r'[^.]{0,300}?\.)',
    flags=re.DOTALL,
)

# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and a_end > b_start


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex span overlaps a higher-or-equal priority result."""
    # Priority: lower number = higher priority
    priority_map = {
        'C_BF_TERM': 1,
        'C_TEXTBF_TERM': 1,
        'C_EM_SECTION': 2,
        'C_ARE_DEFINED_AS': 2,
        'C_ALSO_CALLED': 2,
        'C_DENOTE_BY': 2,
        'C_EMPH_SEMI': 2,
        'C_CALLED_NAMED': 2,
        'C_OBEYS_IF': 3,
    }

    def prio(r):
        return priority_map.get(r.get('rule_name', ''), 99)

    # Sort by priority then by start position
    keyed = sorted(results, key=lambda r: (prio(r), r.get('_start', 0)))

    kept = []
    for r in keyed:
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

    # Also deduplicate by clean_text similarity (first 40 chars)
    final = []
    seen_prefixes = []
    for r in kept:
        ct = (r.get('clean_text') or '').strip().lower()
        prefix = ct[:40]
        if prefix and any(prefix == sp for sp in seen_prefixes):
            continue
        final.append(r)
        if prefix:
            seen_prefixes.append(prefix)

    # Remove internal keys
    for r in final:
        r.pop('_start', None)
        r.pop('_end', None)

    return final


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    """
    Extract definition structures from LaTeX text using supplementary rules
    that fill gaps not covered by the base _extract_definitions_manual method.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    excluded_ranges = _build_excluded_ranges(text)
    masked = _build_masked_text(text, excluded_ranges)

    def _make_result(raw: str, name, rule_name: str, start: int) -> dict:
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_start': start,
            '_end': start + len(raw),
        }

    def _extract_name(raw_name: str) -> str:
        if not raw_name:
            return ''
        raw_name = raw_name.strip()
        # If it's a math expression keep it short
        m = re.search(r'\$([^$]{1,60})\$', raw_name)
        if m:
            return m.group(1).strip()
        return _clean_latex(raw_name)[:80]

    # -----------------------------------------------------------------------
    # Rule C_BF_TERM: {\bf Term:} ... prose block
#     # -----------------------------------------------------------------------
#     for m in C_BF_TERM.finditer(masked):
#         if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
#             continue
#         full = text[m.start():m.end()]
#         name_raw = m.group('name') or ''
#         name = _extract_name(name_raw)
#         if not name:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, name or None, 'C_BF_TERM', m.start()))

    # -----------------------------------------------------------------------
    # Rule C_TEXTBF_TERM: \textbf{Term:} ... prose block
#     # -----------------------------------------------------------------------
#     for m in C_TEXTBF_TERM.finditer(masked):
#         if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
#             continue
#         full = text[m.start():m.end()]
#         name_raw = m.group('name') or ''
#         name = _extract_name(name_raw)
#         if not name:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, name or None, 'C_TEXTBF_TERM', m.start()))

    # -----------------------------------------------------------------------
    # Rule C_EM_SECTION: paragraph after section heading containing {\em}
#     # -----------------------------------------------------------------------
#     for sec_m in C_EM_SECTION_HEADING.finditer(masked):
#         if _inside_excluded_env(sec_m.start(), sec_m.end(), excluded_ranges):
#             continue
#         para_start = sec_m.end()
#         # Skip whitespace / comment lines
#         ws_m = re.match(r'[\s%][^\n]*\n', masked[para_start:])
#         if ws_m:
#             para_start += ws_m.end()
#         nb = _PARA_END.search(masked, para_start)
#         para_end = nb.start() if nb else len(masked)
#         if para_end <= para_start:
#             continue
#         para_masked = masked[para_start:para_end].strip()
#         if not para_masked or len(para_masked) < 50:
#             continue
#         em_m = C_EM_TERM_IN_PARA.search(para_masked)
#         if not em_m:
#             continue
#         name_raw = em_m.group('name') or em_m.group('name2') or ''
#         name = _extract_name(name_raw)
#         # Use original (unmasked) text for the paragraph
#         para_text_orig = text[para_start:para_start + len(para_masked)]
#         if _REFERENTIAL.search(para_text_orig):
#             continue
#         results.append(_make_result(para_text_orig, name or None, 'C_EM_SECTION', para_start))

    # -----------------------------------------------------------------------
    # Rule C_ARE_DEFINED_AS: plural "are defined as/to be" (extends base C2)
    # -----------------------------------------------------------------------
    for anchor_m in C_ARE_DEFINED_AS.finditer(masked):
        if _inside_excluded_env(anchor_m.start(), anchor_m.end(), excluded_ranges):
            continue
        start_search = max(0, anchor_m.start() - 120)
        prefix = masked[start_search:anchor_m.start()]
        # Find sentence boundary
        dot_pos = max(prefix.rfind('.'), prefix.rfind('\n\n'))
        name_start = (start_search + dot_pos + 1) if dot_pos >= 0 else start_search
        name_text = masked[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 100:
            continue
        tail_m = _C2_TAIL.match(masked, anchor_m.end())
        if not tail_m:
            continue
        full_masked = masked[name_start:tail_m.end()]
        full_orig = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_orig) or _NEGATIVE_DEFINE.search(full_orig):
            continue
        name = _extract_name(name_text)
        results.append(_make_result(full_orig, name or None, 'C_ARE_DEFINED_AS', name_start))

    # -----------------------------------------------------------------------
    # Rule C_ALSO_CALLED: "(also called X)" or "(known as X)"
#     # -----------------------------------------------------------------------
#     for m in C_ALSO_CALLED.finditer(masked):
#         if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
#             continue
#         full = text[m.start():m.end()]
#         name_raw = m.group('name') or ''
#         name = _extract_name(name_raw)
#         if not name:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         results.append(_make_result(full, name or None, 'C_ALSO_CALLED', m.start()))

    # -----------------------------------------------------------------------
    # Rule C_DENOTE_BY: "We (will) denote by X ..."
    # -----------------------------------------------------------------------
    for m in C_DENOTE_BY.finditer(masked):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = text[m.start():m.end()]
        name_raw = m.group('name') or ''
        name = _extract_name(name_raw)
        if _REFERENTIAL.search(full) or _NEGATIVE_DEFINE.search(full):
            continue
        results.append(_make_result(full, name or None, 'C_DENOTE_BY', m.start()))

    # -----------------------------------------------------------------------
    # Rule C_EMPH_SEMI: \emph{term}; ... is/are ...
    # -----------------------------------------------------------------------
    for m in C_EMPH_SEMI.finditer(masked):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = text[m.start():m.end()]
        name_raw = m.group('name') or m.group('name2') or ''
        name = _extract_name(name_raw)
        # Must contain is/are after semicolon
        semi_pos = full.find(';')
        if semi_pos < 0:
            continue
        after_semi = full[semi_pos:]
        if not re.search(r'\b(?:is|are)\b', after_semi, re.IGNORECASE):
            continue
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name or None, 'C_EMPH_SEMI', m.start()))

    # -----------------------------------------------------------------------
    # Rule C_CALLED_NAMED: "X is called/named [em-term]"
    # -----------------------------------------------------------------------
    for m in C_CALLED_NAMED.finditer(masked):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = text[m.start():m.end()]
        name_raw = (m.group('name') or m.group('name2') or m.group('name3')
                    or m.group('name4') or m.group('name5') or '')
        name = _extract_name(name_raw)
        if not name:
            continue
        if _REFERENTIAL.search(full) or _NEGATIVE_DEFINE.search(full):
            continue
        results.append(_make_result(full, name or None, 'C_CALLED_NAMED', m.start()))

    # -----------------------------------------------------------------------
    # Rule C_OBEYS_IF: '{\em term} obeys/satisfies ... if ...'
    # -----------------------------------------------------------------------
    for m in C_OBEYS_IF.finditer(masked):
        if _inside_excluded_env(m.start(), m.end(), excluded_ranges):
            continue
        full = text[m.start():m.end()]
        name_raw = m.group('name') or m.group('name2') or ''
        if not name_raw.strip():
            continue
        name = _extract_name(name_raw)
        if _REFERENTIAL.search(full):
            continue
        results.append(_make_result(full, name or None, 'C_OBEYS_IF', m.start()))

    # -----------------------------------------------------------------------
    # Deduplicate and return
    # -----------------------------------------------------------------------
    results = _deduplicate(results)
    return results
