import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|eqnarray|array|gather|multline)\*?\}.*?\\end\{(?:equation|align|eqnarray|array|gather|multline)\*?\}', ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]+\$', '[MATH]', text)
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    # Remove common commands keeping their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:em|bf|it|rm|tt)\s+([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Normalise whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose bodies we do NOT want to match inside
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop'
    r'|corollary|Corollary|cor|claim|Claim|conjecture|Conjecture'
    r'|proof|Proof|example|Example|exam|ex|exercise|Exercise'
    r'|remark|Remark|rem|note)\*?\}(.*?)\\end\{\1\*?\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_excluded_spans(text: str):
    """Return list of (start, end) spans that are inside excluded environments."""
    spans = []
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        spans.append((m.start(), m.end()))
    return spans


def _inside_excluded_env(spans, start: int, end: int) -> bool:
    """Return True if the interval [start, end) overlaps any excluded span."""
    for s, e in spans:
        if start < e and end > s:
            return True
    return False


def _extract_name_from_raw(raw: str) -> str:
    """Try to pull a short name hint from a raw LaTeX fragment."""
    m = re.search(r'\$([^$]{1,60})\$', raw)
    if m:
        return _clean_latex(m.group(1))[:80]
    cleaned = _clean_latex(raw)
    return cleaned[:80] if cleaned else ''


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# C6 – {\bf Term:} or {\bf Term} (possibly containing math) followed by prose
# Ends at \\\\ + newline, double blank line, \begin{, \section, or \end{document}
# PRUNED — FP on paper001, paper002 | also 3 TP — review before uncommenting
# INLINE_BF_TERM_PATTERN = re.compile(
#     r'(?P<full>'
#     r'\{\\bf\s+(?P<name>[^}]{1,120}?)\s*:?\s*\}'
#     r'(?::?\s*)'
#     r'(?P<prose>(?:(?!\{\\bf\s).){10,1200}?)'
#     r'(?=\\\\\s*\n|\n[ \t]*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\})'
#     r')',
#     flags=re.DOTALL,
# )

# C7 – (also called ALIAS) or (also known as ALIAS) parenthetical definition
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# INLINE_ALSO_CALLED_PATTERN = re.compile(
#     r'(?P<full>'
#     r'[A-Z][^.]{0,180}?'
#     r'\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{2,80})\)'
#     r'[^.]{0,400}?\.)',
#     flags=re.DOTALL,
# )

# C8 – 'We (will) denote by X the/a ...' standard math definition
INLINE_DENOTE_BY_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:We\s+(?:will\s+)?|[Ll]et\s+us\s+)denote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\{}_^,\s]{1,60}?))'
    r'\s+(?:the\s+|a\s+)?'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.]){0,600}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C9 – 'are defined as' plural variant of the C2 'is defined as' anchor
# Two-part: anchor + tail
INLINE_ARE_DEFINED_AS_ANCHOR = re.compile(
    r'\bare\s+defined\s+(?:as|to\s+be)\b',
    flags=re.IGNORECASE,
)

_C2_TAIL = re.compile(
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{(?:equation|align|eqnarray|array|gather|multline)\*?\}.*?\\end\{(?:equation|align|eqnarray|array|gather|multline)\*?\}|[^.]){0,800}?\.',
    flags=re.DOTALL,
)

# C10 – {\em term}; ... is/are ... (italicised term then definition after semicolon)
INLINE_EMPH_SEMI_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^;.]{0,200}?;'
    r'[^.]{0,400}?'
    r'\b(?:is|are)\b'
    r'[^.]{0,400}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C11 – {\em term} obeys/satisfies ... if ... (definitional condition)
INLINE_OBEYS_IF_PATTERN = re.compile(
    r'(?P<full>'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:\\emph\{(?P<name>[^}]{1,80})\}|\{\\em\s+(?P<name2>[^}]{1,80})\})'
    r'[^.]{0,200}?'
    r'\b(?:obeys?|satisfies?|verifies?|fulfills?)\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{equation\}.*?\\end\{equation\}|[^.]){0,600}?'
    r'\bif\b'
    r'(?:\\\[.*?\\\]|\$\$.*?\$\$|\\begin\{equation\}.*?\\end\{equation\}|[^.]){0,600}?\.)',
    flags=re.IGNORECASE | re.DOTALL,
)

# C12 – Section/subsection heading followed immediately by a paragraph with {\em} or \emph{}
# PRUNED — FP on paper001, paper002 | also 1 TP — review before uncommenting
# _SECTION_HEADING_RE = re.compile(
#     r'\\(?:sub)*section\*?\{[^}]{0,120}\}',
#     flags=re.DOTALL,
# )
_EM_TERM_RE = re.compile(
    r'(?:\\emph\{(?P<name>[^}]{2,80})\}|\{\\em\s+(?P<name2>[^}]{2,80})\})',
)
_NEXT_BLOCK_RE = re.compile(
    r'\n[ \t]*\n|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}',
)

# Negative / referential guards (shared)
_REFERENTIAL = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left|'
    r'in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    flags=re.IGNORECASE,
)
_NEGATIVE_C1 = re.compile(
    r'\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|'
    r'Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|'
    r'as\s+(?:before|above|below|follows)|defined\s+(?:above|below|'
    r'earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|'
    r'in\s+Equation|in\s+Definition))\b',
    flags=re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[Dict]:
    """
    Extract definition structures from LaTeX source that are NOT already
    captured by the base _extract_definitions_manual method.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[Dict] = []
    excluded_spans = _build_excluded_spans(text)

    def _add(raw_latex: str, name: str, rule_name: str, source_pos: int):
        clean = _clean_latex(raw_latex)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_source_pos': source_pos,
        })

    # ------------------------------------------------------------------
    # Rule C6 – {\bf Term:} prose blocks
#     # ------------------------------------------------------------------
#     for m in INLINE_BF_TERM_PATTERN.finditer(text):
#         if _inside_excluded_env(excluded_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         name_raw = m.group('name') or ''
#         if _referential.search(full) if False else _REFERENTIAL.search(full):
#             continue
#         name_hint = _extract_name_from_raw(name_raw)
#         _add(full, name_hint, 'INLINE_BF_TERM_PATTERN', m.start())

    # ------------------------------------------------------------------
    # Rule C7 – (also called / also known as ALIAS)
#     # ------------------------------------------------------------------
#     for m in INLINE_ALSO_CALLED_PATTERN.finditer(text):
#         if _inside_excluded_env(excluded_spans, m.start(), m.end()):
#             continue
#         full = m.group('full')
#         if _REFERENTIAL.search(full):
#             continue
#         name_raw = m.group('name') or ''
#         name_hint = _clean_latex(name_raw).strip()[:80]
#         _add(full, name_hint, 'INLINE_ALSO_CALLED_PATTERN', m.start())

    # ------------------------------------------------------------------
    # Rule C8 – We (will) denote by X ...
    # ------------------------------------------------------------------
    for m in INLINE_DENOTE_BY_PATTERN.finditer(text):
        if _inside_excluded_env(excluded_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        if _NEGATIVE_C1.search(full):
            continue
        name_raw = m.group('name') or ''
        name_hint = _extract_name_from_raw(name_raw)
        _add(full, name_hint, 'INLINE_DENOTE_BY_PATTERN', m.start())

    # ------------------------------------------------------------------
    # Rule C9 – 'are defined as' (plural C2 variant) – two-phase
    # ------------------------------------------------------------------
    for anchor_m in INLINE_ARE_DEFINED_AS_ANCHOR.finditer(text):
        if _inside_excluded_env(excluded_spans, anchor_m.start(), anchor_m.end()):
            continue
        start_search = max(0, anchor_m.start() - 120)
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
        if _REFERENTIAL.search(full_text):
            continue
        name_hint = _extract_name_from_raw(name_text)
        _add(full_text, name_hint, 'INLINE_ARE_DEFINED_AS_ANCHOR', name_start)

    # ------------------------------------------------------------------
    # Rule C10 – {\em term}; ... is/are ...
    # ------------------------------------------------------------------
    for m in INLINE_EMPH_SEMI_PATTERN.finditer(text):
        if _inside_excluded_env(excluded_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name') or m.group('name2') or ''
        name_hint = _clean_latex(name_raw).strip()[:80]
        _add(full, name_hint, 'INLINE_EMPH_SEMI_PATTERN', m.start())

    # ------------------------------------------------------------------
    # Rule C11 – {\em term} obeys/satisfies ... if ...
    # ------------------------------------------------------------------
    for m in INLINE_OBEYS_IF_PATTERN.finditer(text):
        if _inside_excluded_env(excluded_spans, m.start(), m.end()):
            continue
        full = m.group('full')
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name') or m.group('name2') or ''
        if not name_raw.strip():
            continue
        name_hint = _clean_latex(name_raw).strip()[:80]
        _add(full, name_hint, 'INLINE_OBEYS_IF_PATTERN', m.start())

    # ------------------------------------------------------------------
    # Rule C12 – Section heading followed by paragraph with {\em} / \emph{}
#     # ------------------------------------------------------------------
#     for sec_m in _SECTION_HEADING_RE.finditer(text):
#         para_start = sec_m.end()
#         # Skip whitespace / comment lines
#         skip = re.match(r'(?:[ \t]*(?:%[^\n]*)?\n)*[ \t]*', text[para_start:])
#         if skip:
#             para_start += skip.end()
#         nb = _NEXT_BLOCK_RE.search(text, para_start)
#         para_end = nb.start() if nb else len(text)
#         if para_end <= para_start:
#             continue
#         para_text = text[para_start:para_end].strip()
#         if len(para_text) < 40:
#             continue
#         if _inside_excluded_env(excluded_spans, para_start, para_end):
#             continue
#         em_m = _EM_TERM_RE.search(para_text)
#         if not em_m:
#             continue
#         if _REFERENTIAL.search(para_text):
#             continue
#         name_raw = em_m.group('name') or em_m.group('name2') or ''
#         name_hint = _clean_latex(name_raw).strip()[:80]
#         _add(para_text, name_hint, '_SECTION_HEADING_RE', para_start)

    # ------------------------------------------------------------------
    # Deduplication: remove overlapping matches, keeping the longer one
    # ------------------------------------------------------------------
    if not results:
        return results

    # Sort by source position, then by length descending
    results.sort(key=lambda r: (r['_source_pos'], -len(r['raw_latex'])))

    deduped: List[Dict] = []
    occupied: List[tuple] = []  # list of (start, end)

    for r in results:
        pos = r['_source_pos']
        end = pos + len(r['raw_latex'])
        overlaps = False
        for os, oe in occupied:
            if pos < oe and end > os:
                overlaps = True
                break
        if not overlaps:
            deduped.append(r)
            occupied.append((pos, end))

    # Also deduplicate by near-identical clean_text (substring containment)
    final: List[Dict] = []
    seen_texts: List[str] = []
    for r in deduped:
        ct = (r['clean_text'] or '').strip().lower()
        if not ct:
            final.append(r)
            continue
        is_dup = False
        for prev in seen_texts:
            if ct in prev or prev in ct:
                is_dup = True
                break
            min_len = min(len(ct), len(prev))
            if min_len > 30 and ct[:30] == prev[:30]:
                is_dup = True
                break
        if not is_dup:
            final.append(r)
            seen_texts.append(ct)

    # Clean up internal key before returning
    for r in final:
        r.pop('_source_pos', None)

    return final


# --- auto-repair: alias case-mismatched globals ---
_referential = _REFERENTIAL
