import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # \emph{X} -> X,  \textbf{X} -> X,  {\em X} -> X,  {\bf X} -> X
    text = re.sub(r'\\(?:emph|textbf|textit|mathrm|mathbf|mathit|text)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:em|bf|it|rm)\s+([^}]*)\}', r'\1', text)
    # \cite{...} -> ''
    text = re.sub(r'\\cite[a-zA-Z]*\{[^}]*\}', '', text)
    # \label{...} -> ''
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # \ref{...} -> ''
    text = re.sub(r'\\ref\{[^}]*\}', '', text)
    # \section, \subsection etc. -> just the title
    text = re.sub(r'\\(?:sub)*section\*?\{([^}]*)\}', r'\1', text)
    # display math environments: \ba...\ea  \[...\]  $$...$$
    text = re.sub(r'\\ba\b.*?\\ea\b', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    # begin/end environments we don't care about
    text = re.sub(r'\\begin\{[^}]*\}.*?\\end\{[^}]*\}', ' [MATH] ', text, flags=re.DOTALL)
    # remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # braces
    text = re.sub(r'[{}]', '', text)
    # normalise whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose content we exclude from inline matching
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop'
    r'|corollary|Corollary|cor|claim|Claim|conjecture|Conjecture'
    r'|problem|Problem|proof|Proof|example|Example|remark|Remark)\}'
    r'.*?'
    r'\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _build_exclusion_mask(text: str) -> List[bool]:
    """Return a boolean mask: True at positions inside excluded environments."""
    mask = [False] * len(text)
    for m in _EXCLUDED_ENV_RE.finditer(text):
        for i in range(m.start(), min(m.end(), len(text))):
            mask[i] = True
    return mask


def _inside_excluded_env(mask: List[bool], start: int, end: int) -> bool:
    """Return True if the majority of [start,end) is inside an excluded env."""
    if not mask:
        return False
    end = min(end, len(mask))
    if start >= end:
        return False
    hits = sum(1 for i in range(start, end) if mask[i])
    return hits > (end - start) * 0.5


# ---------------------------------------------------------------------------
# Referential / negative guards (shared across rules)
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

# Rule R1 – {\bf Name:} / \textbf{Name:} bold-labelled definition blocks
# Captures e.g. "{\bf The $\eps$-neighborhood graph:} Here we connect..."
# and "{\bf $k$-nearest neighbor graphs:} Here the goal is..."
# PRUNED — FP on paper001, paper002 | also 3 TP — review before uncommenting
# INLINE_BF_LABEL = re.compile(
#     r'(?P<full>'
#     r'(?:\{\\bf\s+|\{\\textbf\s+|\\textbf\{)'
#     r'(?P<name>[^}:]{1,120})'
#     r'(?::?\}|\}:?)'
#     r'[ \t]*'
#     r'(?P<body>(?:.|\n){30,1200}?)'
#     r')'
#     r'(?='
#     r'\n[ \t]*\n'               # blank line
#     r'|\{\\bf\s'                # next \bf block
#     r'|\\textbf\{'              # next \textbf
#     r'|\\\\\s*\n\s*\n'          # double newline after \\
#     r'|\\\\[ \t]*\n[ \t]*\n'
#     r'|\\(?:sub)*section'
#     r'|\\begin\{'
#     r'|\\end\{document\}'
#     r')',
#     flags=re.DOTALL,
# )

# Rule R2 – "X is called Y" definitional sentences
# Anchored on "is called"; looks back up to 150 chars for sentence start
# PRUNED — FP on paper001
# _R2_ANCHOR = re.compile(
#     r'\bis\s+called\b',
#     flags=re.IGNORECASE,
# )
_R2_TAIL = re.compile(
    r'(?:[^.!?]|\.\d)*[.!?]',
    flags=re.DOTALL,
)

# Rule R3 – "are defined as" / "is defined as" with display math in body
# Extension of base C2: also matches "are defined" and handles \ba...\ea
_R3_ANCHOR = re.compile(
    r'\b(?:is|are)\s+defined\s+(?:as|to\s+be)\s',
    flags=re.IGNORECASE,
)
# Tail: greedily consume up to 600 chars then find a period
# (handles embedded display math blocks)
_R3_TAIL = re.compile(
    r'(?:'
    r'\\ba\b.*?\\ea\b'
    r'|\\begin\{(?:align|equation|gather|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|eqnarray)\*?\}'
    r'|\\\[.*?\\\]'
    r'|\$\$.*?\$\$'
    r'|[^.]'
    r'){1,600}[.]',
    flags=re.DOTALL,
)

# Rule R4 – "We (will) denote by $X$ ..."
INLINE_DENOTE = re.compile(
    r'(?P<full>'
    r'(?:We\s+)?(?:will\s+)?(?:also\s+)?[Dd]enote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|\{[^}]+\}|[A-Za-z0-9\\{}_^]+))'
    r'(?:[^.!?]|\$[^$]+\$|\{[^}]+\}|\[[^\]]+\])*'
    r'[.!?]'
    r')',
    flags=re.DOTALL,
)

# Rule R5 – "a {\em term} obeys PROPERTY ... if ..."
INLINE_OBEYS = re.compile(
    r'(?P<full>'
    r'(?:a\s+)?'
    r'(?:\\emph\{(?P<emph_name>[^}]+)\}|\{\\em\s+(?P<em_name>[^}]+)\})'
    r'(?:[^.!?]|\$[^$]*\$){0,150}?'
    r'\bobeys\b'
    r'(?:[^.!?]|\$[^$]*\$|\{[^}]*\}|\[[^\]]*\]|\n(?!\n)){0,500}'
    r'[.!?]'
    r')',
    flags=re.DOTALL,
)

# Rule R6 – Paragraph-level section definition
# "Suppose now that X is compressible in the sense that ..."
# "a linear code is a given collection of codewords..."
# Triggered by: after \emph{}; followed by semicolon + "is a ..."
INLINE_EMPH_SEMICOLON = re.compile(
    r'(?P<full>'
    r'(?:[^.!?]{0,120}?)'
    r'\\emph\{(?P<emph_name>[^}]+)\}'
    r'[^.;]{0,60}[;]\s*'
    r'(?P<name>[A-Za-z][A-Za-z0-9 \-]{1,60}?)'
    r'\s+is\s+(?:a|an|the)\s+(?:given\s+)?'
    r'(?:collection|set|sequence|map|mapping|function|family|class|space|operator|'
    r'matrix|vector|graph|code|measure|distribution|process|transform|pair|triple|'
    r'tuple|list|array|structure|object|element|member|subset|subspace|subgroup|'
    r'ring|field|group|algebra|category|bundle|module|lattice|poset|order|relation|'
    r'partition|cover|basis|frame|system|scheme|variety|manifold|surface|curve|'
    r'form|tensor|functional|filter|ideal|kernel|image|homomorphism|isomorphism|'
    r'automorphism|endomorphism|morphism|functor|limit|colimit|product|coproduct)\b'
    r'(?:[^.!?]|\$[^$]*\$|\{[^}]*\}){0,400}'
    r'[.!?]'
    r')',
    flags=re.IGNORECASE | re.DOTALL,
)

# Rule R7 – "Suppose now that the object ... is compressible in the sense that"
# or free-form paragraph definition with compressible/decay/power-law keywords
INLINE_SUPPOSE_DEF = re.compile(
    r'(?P<full>'
    r'(?:Suppose\s+(?:now\s+)?that\s+)'
    r'(?P<name>[^.!?]{1,120}?)'
    r'(?:is|are)\s+'
    r'(?:\\emph\{[^}]+\}|\{\\em\s+[^}]+\}|[A-Za-z]+)'
    r'(?:\s+in\s+the\s+sense\s+that\s+)?'
    r'(?:[^.!?]|\$[^$]*\$|\{[^}]*\}|\n(?!\n)){10,600}'
    r'[.!?]'
    r')',
    flags=re.DOTALL,
)

# Rule R8 – "X (also called Y) is the ..." definitional sentences
INLINE_THE_X_IS = re.compile(
    r'(?P<full>'
    r'(?:The\s+)'
    r'(?P<name>[A-Z][^.()]{2,80}?)'
    r'(?:\s*\([^)]{1,80}\))?'            # optional parenthetical alias
    r'\s+(?:is|are|refers?\s+to|denotes?)\s+the\s+'
    r'(?:[^.!?]|\$[^$]*\$|\{[^}]*\}|\n(?!\n)){20,500}'
    r'[.!?]'
    r')',
    flags=re.DOTALL,
)

_THE_X_IS_KEYWORDS = re.compile(
    r'\b(expected|defined|denoted|notation|refers?\s+to|known\s+as|'
    r'called|probability|distance|measure|number|set|function|matrix|time)\b',
    flags=re.IGNORECASE,
)

# Rule R9 – Section/subsection-level introductory paragraph definition
# Captures the first substantive paragraph after a section header when it
# contains definitional language.
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# _SECTION_HEADER = re.compile(
#     r'\\(?:sub)*section\*?\{[^}]*\}',
#     flags=re.IGNORECASE,
# )
_SECTION_DEF_KEYWORDS = re.compile(
    r'\b(define[sd]?|definition|denote[sd]?|call|refer\s+to|known\s+as|'
    r'represent[s]?|consists?\s+of|form\s+of\s+the|intuitive\s+goal|'
    r'goal\s+of|we\s+(?:say|use|write)|the\s+problem\s+of|'
    r'similarity\s+graph|clustering\s+is\s+to)\b',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[Dict]) -> List[Dict]:
    """Remove results whose raw_latex substantially overlaps a prior result."""
    kept: List[Dict] = []
    kept_texts: List[str] = []
    for r in results:
        ct = (r.get('clean_text') or '').strip().lower()
        if not ct:
            kept.append(r)
            continue
        is_dup = False
        for prev in kept_texts:
            if ct in prev or prev in ct:
                is_dup = True
                break
            min_len = min(len(ct), len(prev))
            if min_len > 40 and ct[:40] == prev[:40]:
                is_dup = True
                break
        if not is_dup:
            kept.append(r)
            kept_texts.append(ct)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[Dict]:
    results: List[Dict] = []

    # Build exclusion mask once
    mask = _build_exclusion_mask(text)

    def _make_result(raw: str, name: str | None, rule: str, pos: int) -> Dict:
        return {
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule,
            'structure_type': 'definition',
            '_pos': pos,
        }

    def _extract_name_hint(raw: str) -> str | None:
        raw = raw.strip()
        if not raw:
            return None
        # Try to pull out an inline math label
        m = re.search(r'\$(.+?)\$', raw)
        if m:
            inner = m.group(1)
            inner = re.sub(r'\\[a-zA-Z]+', '', inner)
            inner = re.sub(r'[{}]', '', inner)
            return inner.strip()[:80] or None
        # Strip LaTeX commands and braces
        plain = re.sub(r'\\[a-zA-Z]+\*?', ' ', raw)
        plain = re.sub(r'[{}]', '', plain)
        plain = re.sub(r'\s+', ' ', plain).strip()
        return plain[:80] or None

    # ------------------------------------------------------------------
    # R1: {\bf Name:} bold-labelled definition blocks
#     # ------------------------------------------------------------------
#     for m in INLINE_BF_LABEL.finditer(text):
#         if _inside_excluded_env(mask, m.start(), m.end()):
#             continue
#         full = m.group('full').strip()
#         name_raw = m.group('name').strip()
#         if len(full) < 30:
#             continue
#         if _REFERENTIAL.search(full):
#             continue
#         name_hint = _extract_name_hint(name_raw)
#         results.append(_make_result(full, name_hint, 'INLINE_BF_LABEL', m.start()))

    # ------------------------------------------------------------------
    # R2: "X is called Y" — look-back anchor approach
#     # ------------------------------------------------------------------
#     for anchor_m in _R2_ANCHOR.finditer(text):
#         if _inside_excluded_env(mask, anchor_m.start(), anchor_m.end()):
#             continue
#         look_back = max(0, anchor_m.start() - 150)
#         prefix = text[look_back:anchor_m.start()]
#         # Find last sentence boundary in prefix
#         dot_pos = max(prefix.rfind('.'), prefix.rfind('\n\n'))
#         if dot_pos >= 0:
#             name_start = look_back + dot_pos + 1
#         else:
#             name_start = look_back
#         name_text = text[name_start:anchor_m.start()].strip()
#         if not name_text or len(name_text) > 150:
#             continue
#         tail_m = _R2_TAIL.match(text, anchor_m.end())
#         if not tail_m:
#             continue
#         full_text = text[name_start:tail_m.end()]
#         if _REFERENTIAL.search(full_text):
#             continue
#         if _inside_excluded_env(mask, name_start, tail_m.end()):
#             continue
#         name_hint = _extract_name_hint(name_text)
#         results.append(_make_result(full_text, name_hint, '_R2_ANCHOR', name_start))

    # ------------------------------------------------------------------
    # R3: "is/are defined as" with display math in body
    # ------------------------------------------------------------------
    for anchor_m in _R3_ANCHOR.finditer(text):
        if _inside_excluded_env(mask, anchor_m.start(), anchor_m.end()):
            continue
        look_back = max(0, anchor_m.start() - 150)
        prefix = text[look_back:anchor_m.start()]
        dot_pos = max(prefix.rfind('.'), prefix.rfind('\n\n'))
        if dot_pos >= 0:
            name_start = look_back + dot_pos + 1
        else:
            name_start = look_back
        name_text = text[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 150:
            continue
        tail_m = _R3_TAIL.match(text, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()]
        if _REFERENTIAL.search(full_text):
            continue
        if _inside_excluded_env(mask, name_start, tail_m.end()):
            continue
        name_hint = _extract_name_hint(name_text)
        results.append(_make_result(full_text, name_hint, '_R3_ANCHOR', name_start))

    # ------------------------------------------------------------------
    # R4: "We (will) denote by X ..."
    # ------------------------------------------------------------------
    for m in INLINE_DENOTE.finditer(text):
        if _inside_excluded_env(mask, m.start(), m.end()):
            continue
        full = m.group('full').strip()
        if _REFERENTIAL.search(full):
            continue
        if _C1_NEGATIVE.search(full):
            continue
        name_raw = m.group('name')
        name_hint = _extract_name_hint(name_raw)
        results.append(_make_result(full, name_hint, 'INLINE_DENOTE', m.start()))

    # ------------------------------------------------------------------
    # R5: "a {\em term} obeys PROPERTY ... if ..."
    # ------------------------------------------------------------------
    for m in INLINE_OBEYS.finditer(text):
        if _inside_excluded_env(mask, m.start(), m.end()):
            continue
        full = m.group('full').strip()
        if _REFERENTIAL.search(full):
            continue
        emph = m.group('emph_name') or m.group('em_name')
        name_hint = _extract_name_hint(emph) if emph else None
        results.append(_make_result(full, name_hint, 'INLINE_OBEYS', m.start()))

    # ------------------------------------------------------------------
    # R6: \emph{term}; term is a <noun> ...
    # ------------------------------------------------------------------
    for m in INLINE_EMPH_SEMICOLON.finditer(text):
        if _inside_excluded_env(mask, m.start(), m.end()):
            continue
        full = m.group('full').strip()
        if _REFERENTIAL.search(full):
            continue
        emph = m.group('emph_name')
        name_hint = _extract_name_hint(emph) if emph else _extract_name_hint(m.group('name'))
        results.append(_make_result(full, name_hint, 'INLINE_EMPH_SEMICOLON', m.start()))

    # ------------------------------------------------------------------
    # R7: "Suppose now that the object of interest is {\em compressible}..."
    # ------------------------------------------------------------------
    for m in INLINE_SUPPOSE_DEF.finditer(text):
        if _inside_excluded_env(mask, m.start(), m.end()):
            continue
        full = m.group('full').strip()
        if _REFERENTIAL.search(full):
            continue
        name_raw = m.group('name').strip()
        name_hint = _extract_name_hint(name_raw)
        results.append(_make_result(full, name_hint, 'INLINE_SUPPOSE_DEF', m.start()))

    # ------------------------------------------------------------------
    # R8: "The X (also called Y) is the ..."
    # ------------------------------------------------------------------
    for m in INLINE_THE_X_IS.finditer(text):
        if _inside_excluded_env(mask, m.start(), m.end()):
            continue
        full = m.group('full').strip()
        if not _THE_X_IS_KEYWORDS.search(full):
            continue
        if _REFERENTIAL.search(full):
            continue
        if len(full) < 40:
            continue
        name_raw = m.group('name').strip()
        name_hint = _extract_name_hint(name_raw)
        results.append(_make_result(full, name_hint, 'INLINE_THE_X_IS', m.start()))

    # ------------------------------------------------------------------
    # R9: Section/subsection introductory paragraph definitions
    # Captures the first non-blank paragraph after a section header when
    # it contains definitional language.
#     # ------------------------------------------------------------------
#     for sec_m in _SECTION_HEADER.finditer(text):
#         after = text[sec_m.end():]
#         # Skip comment lines and whitespace immediately after header
#         stripped = re.sub(r'^([ \t]*%[^\n]*\n|[ \t]*\n)+', '', after)
#         if not stripped:
#             continue
#         # Find first paragraph boundary (double newline) or structural command
#         para_end = re.search(
#             r'\n[ \t]*\n'
#             r'|\\(?:sub)*section\*?\{'
#             r'|\\begin\{'
#             r'|\\end\{document\}',
#             stripped,
#             flags=re.DOTALL,
#         )
#         if para_end:
#             para_text = stripped[:para_end.start()].strip()
#         else:
#             para_text = stripped[:1500].strip()
#         if len(para_text) < 80:
#             continue
#         if not _SECTION_DEF_KEYWORDS.search(para_text):
#             continue
#         if _REFERENTIAL.search(para_text):
#             continue
#         pos = sec_m.end() + (len(after) - len(stripped))
#         if _inside_excluded_env(mask, pos, pos + len(para_text)):
#             continue
#         # name hint: first sentence up to 80 chars
#         first_sent = para_text.split('.')[0][:80]
#         name_hint = _extract_name_hint(first_sent)
#         results.append(_make_result(para_text, name_hint, '_SECTION_HEADER', pos))

    # ------------------------------------------------------------------
    # Sort by position, deduplicate, strip internal _pos key
    # ------------------------------------------------------------------
    results.sort(key=lambda r: r.get('_pos', 0))
    results = _deduplicate(results)
    for r in results:
        r.pop('_pos', None)

    return results
