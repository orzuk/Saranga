import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very lightweight LaTeX -> plain-text cleaner."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments but keep content
    text = re.sub(r'\\begin\{(?:align|equation|gather|array|matrix|pmatrix|bmatrix)\*?\}(.*?)\\end\{(?:align|equation|gather|array|matrix|pmatrix|bmatrix)\*?\}', r' \1 ', text, flags=re.DOTALL)
    # \ba ... \ea display math
    text = re.sub(r'\\ba\b(.*?)\\ea\b', r' \1 ', text, flags=re.DOTALL)
    # Remove common LaTeX commands but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb|bf|em|rm|it)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|em|it|rm)\s+([^}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite, \eqref etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[A-Za-z]*|citeA|citep|citet)\{[^}]*\}', '', text)
    # Remove \section, \subsection etc.
    text = re.sub(r'\\(?:sub)*section\*?\{[^}]*\}', '', text)
    # Remove other single-arg commands
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Excluded environment names (proof, theorem, lemma, etc.) — we skip matches inside these
_EXCLUDED_ENV_NAMES = [
    'proof', 'Proof',
    'theorem', 'Theorem', 'thm',
    'lemma', 'Lemma', 'lem',
    'proposition', 'Proposition', 'prop',
    'corollary', 'Corollary', 'cor',
    'claim', 'Claim',
    'conjecture', 'Conjecture',
    'problem', 'Problem',
    'example', 'Example', 'exam', 'ex',
    'exercise', 'Exercise',
    'remark', 'Remark', 'rem', 'note',
]

_excluded_env_re = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENV_NAMES)) + r')\}.*?\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if [start, end) overlaps with any excluded environment."""
    for m in _excluded_env_re.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _build_masked_text(text: str) -> str:
    """
    Replace excluded environments with spaces so inline patterns don't
    accidentally match inside them.
    """
    result = list(text)
    for m in _excluded_env_re.finditer(text):
        for i in range(m.start(), m.end()):
            result[i] = ' '
    return ''.join(result)


# ---------------------------------------------------------------------------
# Referential / negative guards (shared)
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

# ---------------------------------------------------------------------------
# Module-level compiled patterns  (rule_name == variable name)
# ---------------------------------------------------------------------------

# R1: {\bf Name:} / \textbf{Name:} bold-labeled definition blocks
# PRUNED — FP on paper001, paper002, paper003 | also 3 TP — review before uncommenting
# inline_bf_pattern = re.compile(
#     r'(?:'
#     r'\{\\bf\s+(?P<name1>[^}:]{1,120}?)(?::?\}|\}:?)'
#     r'|\\textbf\{(?P<name2>[^}:]{1,120}?)(?::?\}|\}:?)'
#     r')'
#     r'[ \t]*(?:\\\\)?[ \t]*'
#     r'(?P<body>(?:[^\n]|\n(?!\s*\n)){10,1200}?)'
#     r'(?=\n\s*\n|\{\\bf\s|\\textbf\{|\\\\\s*\n|\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

# R2: "X is called Y" definitional sentences
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# _c6_anchor = re.compile(
#     r'\bis\s+called\b',
#     flags=re.IGNORECASE,
# )
_c6_tail = re.compile(
    r'(?:[^.]|\.[^A-Z\s])*\.',
    flags=re.DOTALL,
)

# R3: "are defined as" extended C2 anchor
_c2_anchor_extended = re.compile(
    r'\b(?:is|are)\s+defined\s+(?:as|to\s+be)\b',
    flags=re.IGNORECASE,
)

# Tail that handles display math blocks too
_c2_tail_extended = re.compile(
    r'(?:'
    r'\\ba\b.*?\\ea\b'
    r'|\\begin\{(?:align|equation|gather|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|eqnarray)\*?\}'
    r'|\\\[.*?\\\]'
    r'|\$\$.*?\$\$'
    r'|[^.]'
    r')*\.',
    flags=re.DOTALL,
)

# R4: "We (will) denote by NAME ..." inline definition
inline_denote_pattern = re.compile(
    r'(?P<full>'
    r'(?:We\s+)?(?:will\s+)?(?:also\s+)?[Dd]enote\s+by\s+'
    r'(?P<name>(?:\$[^$]+\$|\{[^}]+\}|[A-Za-z0-9\\{}_^]+))'
    r'(?:[^.]|\.[a-z])*\.)',
    flags=re.DOTALL,
)

# R5: '\emph{term} / {\em term} ... obeys ...' style inline definition
inline_obeys_pattern = re.compile(
    r'(?P<full>'
    r'(?:a\s+)?(?:\\emph\{(?P<emph_name>[^}]+)\}|\{\\em\s+(?P<em_name>[^}]+)\})'
    r'[^.]{0,200}?'
    r'\bobeys\b'
    r'(?:[^.]|\.[a-z])*\.)',
    flags=re.DOTALL,
)

# R6: '\emph{term}; term is a/an ...' inline definition (semicolon-introduced)
# PRUNED — FP on paper001, paper003 | also 1 TP — review before uncommenting
# inline_is_a_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:\\emph\{(?P<emph_name>[^}]+)\}[^.;]{0,80}[;,]\s*)?'
#     r'(?P<name>[A-Za-z][A-Za-z0-9 \-]{1,60}?)'
#     r'\s+is\s+(?:a|an|the)\s+(?:given\s+)?'
#     r'(?:collection|set|sequence|map|mapping|function|family|class|space|operator|'
#     r'matrix|vector|graph|code|measure|distribution|process|transform|pair|triple|'
#     r'tuple|list|array|structure|object|element|member|subset|subspace|subgroup|'
#     r'ring|field|group|algebra|category|bundle|module|lattice|poset|relation|'
#     r'partition|cover|basis|frame|system|variety|manifold|surface|curve|form|'
#     r'tensor|functional|filter|ideal|kernel|homomorphism|isomorphism|morphism|'
#     r'functor|algorithm|procedure|protocol|strategy|policy|rule|criterion|condition|'
#     r'property|invariant|characteristic|feature|parameter|variable|constant|symbol|'
#     r'notation|abbreviation|term|notion|concept|definition)\b'
#     r'(?:[^.]|\.[a-z])*\.)',
#     flags=re.IGNORECASE | re.DOTALL,
# )

# R7: Paragraph-level definition after \section/\subsection
# PRUNED — FP on paper003
# inline_section_def_pattern = re.compile(
#     r'(?:\\(?:sub)*section\*?\{[^}]*\})'
#     r'(?:\s*%[^\n]*\n)*'
#     r'\s*'
#     r'(?P<full>'
#     r'(?P<first_sent>[^\n.]{10,200}\.)'
#     r'(?:(?!\\(?:sub)*section|\\begin\{|\\end\{document\}).){0,1200}?)'
#     r'(?=\n\s*\n|\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

_section_def_keywords = re.compile(
    r'\b(define[sd]?|definition|notation|denote[sd]?|call|refer\s+to|'
    r'known\s+as|represent[s]?|consists?\s+of|form\s+of\s+the|'
    r'we\s+(?:say|use|write)|is\s+called|similarity\s+graph|'
    r'clustering|partition)\b',
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Priority map for deduplication
# ---------------------------------------------------------------------------

_source_priority = {
    'inline_bf_label': 1,
    'inline_are_defined_as': 2,
    'inline_denote': 2,
    'inline_is_called': 2,
    'inline_obeys': 2,
    'inline_is_a': 2,
    'inline_section_def': 3,
    'inline_the_x_is': 3,
}


def _extract_name_hint(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r'\$(.+?)\$', raw)
    if m:
        inner = m.group(1)
        inner = re.sub(r'\\[a-zA-Z]+', '', inner)
        inner = re.sub(r'[{}]', '', inner)
        return inner.strip()[:80]
    cleaned = _clean_latex(raw)
    return cleaned[:80]


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[Dict]:
    results: List[Dict] = []
    masked = _build_masked_text(text)

    def _add(raw_latex: str, name: str | None, rule_name: str, source_pos: int):
        ct = _clean_latex(raw_latex)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': ct,
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'definition',
            '_source_pos': source_pos,
        })

    # ------------------------------------------------------------------
    # R1: {\bf Name:} / \textbf{Name:} bold-labeled definition blocks
#     # ------------------------------------------------------------------
#     for m in inline_bf_pattern.finditer(masked):
#         name_raw = m.group('name1') or m.group('name2') or ''
#         body = m.group('body') or ''
#         # Full text = entire match
#         full = m.group(0)
#         if len(full.strip()) < 20:
#             continue
#         if _referential.search(full):
#             continue
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         name_hint = _extract_name_hint(name_raw)
#         _add(full, name_hint or None, 'inline_bf_pattern', m.start())

    # ------------------------------------------------------------------
    # R2: "X is called Y" definitional sentences
#     # ------------------------------------------------------------------
#     for anchor_m in _c6_anchor.finditer(masked):
#         if _inside_excluded_env(text, anchor_m.start(), anchor_m.end()):
#             continue
#         start_search = max(0, anchor_m.start() - 150)
#         prefix = masked[start_search:anchor_m.start()]
#         dot_pos = prefix.rfind('.')
#         name_start = (start_search + dot_pos + 1) if dot_pos >= 0 else start_search
#         name_text = masked[name_start:anchor_m.start()].strip()
#         if not name_text or len(name_text) > 150:
#             continue
#         tail_m = _c6_tail.match(masked, anchor_m.end())
#         if not tail_m:
#             continue
#         full_text = text[name_start:tail_m.end()]
#         if _referential.search(full_text):
#             continue
#         name_hint = _extract_name_hint(name_text)
#         _add(full_text, name_hint or None, '_c6_anchor', name_start)

    # ------------------------------------------------------------------
    # R3: "are defined as" / "is defined as" with display math support
    # ------------------------------------------------------------------
    for anchor_m in _c2_anchor_extended.finditer(masked):
        if _inside_excluded_env(text, anchor_m.start(), anchor_m.end()):
            continue
        start_search = max(0, anchor_m.start() - 150)
        prefix = masked[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        name_start = (start_search + dot_pos + 1) if dot_pos >= 0 else start_search
        name_text = masked[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 150:
            continue
        search_end = min(len(masked), anchor_m.end() + 800)
        tail_region = masked[anchor_m.end():search_end]
        tail_m = _c2_tail_extended.match(tail_region)
        if not tail_m:
            continue
        full_text = text[name_start:anchor_m.end() + tail_m.end()]
        if _referential.search(full_text):
            continue
        name_hint = _extract_name_hint(name_text)
        _add(full_text, name_hint or None, '_c2_anchor_extended', name_start)

    # ------------------------------------------------------------------
    # R4: "We (will) denote by NAME ..." inline definition
    # ------------------------------------------------------------------
    for m in inline_denote_pattern.finditer(masked):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        full_text = text[m.start():m.end()]
        if _referential.search(full_text):
            continue
        name_raw = m.group('name') or ''
        name_hint = _extract_name_hint(name_raw)
        _add(full_text, name_hint or None, 'inline_denote_pattern', m.start())

    # ------------------------------------------------------------------
    # R5: '\emph{term} ... obeys ...' inline definition
    # ------------------------------------------------------------------
    for m in inline_obeys_pattern.finditer(masked):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        full_text = text[m.start():m.end()]
        if _referential.search(full_text):
            continue
        emph = m.group('emph_name') or m.group('em_name') or ''
        name_hint = _extract_name_hint(emph) if emph else None
        _add(full_text, name_hint, 'inline_obeys_pattern', m.start())

    # ------------------------------------------------------------------
    # R6: '\emph{term}; term is a/an ...' inline definition
#     # ------------------------------------------------------------------
#     for m in inline_is_a_pattern.finditer(masked):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         full_text = text[m.start():m.end()]
#         if _referential.search(full_text):
#             continue
#         emph = m.group('emph_name')
#         name_raw = emph if emph else (m.group('name') or '')
#         name_hint = _extract_name_hint(name_raw)
#         _add(full_text, name_hint or None, 'inline_is_a_pattern', m.start())

    # ------------------------------------------------------------------
    # R7: Paragraph-level definition after \section/\subsection
#     # ------------------------------------------------------------------
#     for m in inline_section_def_pattern.finditer(masked):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         full_text = m.group('full').strip()
#         if not full_text or len(full_text) < 40:
#             continue
#         if not _section_def_keywords.search(full_text):
#             continue
#         if _referential.search(full_text):
#             continue
#         first_sent = m.group('first_sent') or ''
#         name_hint = _extract_name_hint(first_sent[:80])
#         actual_text = text[m.start('full'):m.start('full') + len(full_text)]
#         _add(actual_text, name_hint or None, 'inline_section_def_pattern', m.start('full'))

    # ------------------------------------------------------------------
    # Deduplicate overlapping matches
    # Prefer higher-priority (lower number) rules; among equals, prefer longer match
    # ------------------------------------------------------------------
    results.sort(key=lambda r: (_source_priority.get(r['rule_name'], 5), r['_source_pos']))

    deduped: List[Dict] = []
    seen_spans: List[tuple] = []   # list of (start, end) kept so far
    seen_texts: List[str] = []

    for r in results:
        pos = r['_source_pos']
        end = pos + len(r['raw_latex'])
        ct = (r['clean_text'] or '').strip().lower()

        # Check span overlap
        is_dup = False
        for (ks, ke) in seen_spans:
            # Overlap: the intervals [pos,end) and [ks,ke) share >50% of the smaller
            overlap = max(0, min(end, ke) - max(pos, ks))
            smaller = min(end - pos, ke - ks)
            if smaller > 0 and overlap / smaller > 0.5:
                is_dup = True
                break

        if not is_dup and ct:
            # Also check text-level duplication
            for prev_ct in seen_texts:
                if not prev_ct:
                    continue
                if ct in prev_ct or prev_ct in ct:
                    is_dup = True
                    break
                min_len = min(len(ct), len(prev_ct))
                if min_len > 30 and ct[:30] == prev_ct[:30]:
                    is_dup = True
                    break

        if not is_dup:
            deduped.append(r)
            seen_spans.append((pos, end))
            seen_texts.append(ct)

    # Clean up internal keys
    for r in deduped:
        r.pop('_source_pos', None)

    for r in deduped:
        r.pop('_start', None)

    return deduped
