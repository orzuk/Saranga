import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helper: strip common LaTeX markup to plain text
# ---------------------------------------------------------------------------
def _clean_latex(text: str) -> str:
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \begin{...} \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math environments
    text = re.sub(r'\\\[.*?\\\]', ' MATH ', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', ' MATH ', text, flags=re.DOTALL)
    # Keep inline math content roughly
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    # Remove \ba ... \ea (custom align)
    text = re.sub(r'\\ba\b.*?\\ea\b', ' MATH ', text, flags=re.DOTALL)
    # Remove common formatting commands but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathbf|mathrm|mathit|bf|em|it)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|em|it|rm)\s+([^}]*)\}', r'\1', text)
    # Remove remaining commands with arguments
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Helper: check whether a position range falls inside an excluded environment
# ---------------------------------------------------------------------------
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop'
    r'|corollary|Corollary|cor|claim|Claim|conjecture|Conjecture'
    r'|proof|Proof|example|Example|exam|remark|Remark|rem|note'
    r'|exercise|Exercise)\}(.*?)\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# C5: paragraph-level section definitions
# Captures the paragraph that immediately follows a \section / \subsection header
# PRUNED — FP on paper001 | also 2 TP — review before uncommenting
# inline_section_def_pattern = re.compile(
#     r'(?:\\(?:sub)*section\*?\{[^}]*\})'
#     r'(?:\s*(?:\\label\{[^}]*\}|%[^\n]*\n))*'
#     r'\s*%?\s*\n\s*'
#     r'(?P<full>'
#     r'(?P<name>[^\n]{1,120})'
#     r'(?:(?!\\(?:sub)*section|\\begin\{|\\end\{document\}).){50,2000}?'
#     r')'
#     r'(?=\n\s*\n|\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

_section_def_keywords = re.compile(
    r'\b(define[sd]?|definition|notation|denote[sd]?|call|refer\s+to|known\s+as'
    r'|represent[s]?|consists?\s+of|form\s+of\s+the|we\s+(?:say|use|write)'
    r'|intuitive\s+goal|goal\s+of|is\s+in\s+form\s+of)\b',
    flags=re.IGNORECASE,
)

# C6: "X is called Y" definitional sentences
_c6_anchor = re.compile(
    r'\bis\s+called\b',
    flags=re.IGNORECASE,
)
_c6_tail = re.compile(
    r'[^.]*\.',
    flags=re.DOTALL,
)

# C7: {\bf Name:} / \textbf{Name:} bold-labeled inline definitions
# PRUNED — FP on paper001 | also 3 TP — review before uncommenting
# inline_bf_pattern = re.compile(
#     r'(?P<full>'
#     r'(?:\{\\bf\s+|\\textbf\{)'
#     r'(?P<name>[^}]{1,120})'
#     r'\}:?'
#     r'[ \t]*'
#     r'(?:\\\\[ \t]*\n?|\n)?'
#     r'[ \t]*'
#     r'(?:[^\x00]){30,1200}?'
#     r')'
#     r'(?=\n[ \t]*\n|\{\\bf\s|\\textbf\{|\\\\[ \t]*\n[ \t]*\n'
#     r'|\\(?:sub)*section|\\begin\{|\\end\{document\})',
#     flags=re.DOTALL,
# )

# C6-ext: extended "are defined as/to be" (extends base C2 to plural + display math)
_c2_anchor_extended = re.compile(
    r'\b(?:is|are)\s+defined\s+(?:as|to\s+be)\b',
    flags=re.IGNORECASE,
)

_c2_tail_extended = re.compile(
    r'(?:'
    r'\\ba\b.*?\\ea\b'
    r'|\\begin\{(?:align|equation|gather|eqnarray)\*?\}.*?\\end\{(?:align|equation|gather|eqnarray)\*?\}'
    r'|\\\[.*?\\\]'
    r'|\$\$.*?\$\$'
    r'|[^\n]'
    r')*?'
    r'(?:\n[ \t]*\n|(?<=[^\\])\.\s)',
    flags=re.DOTALL,
)

# C8: "The X (also called Y) is the expected ..." definitional sentences
_c8_pattern = re.compile(
    r'(?P<full>'
    r'(?:The\s+)'
    r'(?P<name>[A-Z][^.()\n]{2,80}?)'
    r'(?:\s*\([^)\n]{1,80}\))?'
    r'\s+(?:is|are|refers?\s+to|denotes?)\s+the\s+'
    r'(?:[^\n]){20,600}?'
    r'\.)',
    flags=re.DOTALL,
)

_c8_def_keywords = re.compile(
    r'\b(expected|defined|denoted|notation|refers?\s+to|known\s+as'
    r'|called|probability|distance|measure|number|set|function|matrix'
    r'|time|way|method|approach)\b',
    flags=re.IGNORECASE,
)

_referential = re.compile(
    r'\b(?:defined?\s+)?(?:below|above|right|left'
    r'|in\s+the\s+(?:next|previous|following|preceding)\s+'
    r'(?:section|chapter|subsection|paragraph))\b',
    flags=re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Mask helpers
# ---------------------------------------------------------------------------
_DEF_ENV_RE = re.compile(
    r'\\begin\{(definition|Definition|defn|dfn|Def|Defn)\}(?:\[[^\]]*\])?'
    r'(.*?)\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)

_THEOREM_ENV_RE = re.compile(
    r'\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop'
    r'|corollary|Corollary|cor|claim|Claim|conjecture|Conjecture'
    r'|proof|Proof|example|Example|exam|remark|Remark|rem|note'
    r'|exercise|Exercise)\}(.*?)\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE,
)


def _mask_regions(text: str, pattern: re.Pattern) -> str:
    result = list(text)
    for m in pattern.finditer(text):
        for i in range(m.start(), m.end()):
            result[i] = ' '
    return ''.join(result)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------
def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of a longer result,
    or which have >60% character overlap with a higher-priority result."""
    if not results:
        return results

    # Sort by length descending (longer = higher priority to keep)
    results_sorted = sorted(results, key=lambda r: -len(r.get('raw_latex', '')))
    kept = []
    kept_spans = []  # (start_char_approx, end_char_approx) not available, use text

    for r in results_sorted:
        rt = (r.get('raw_latex') or '').strip()
        if not rt:
            kept.append(r)
            continue
        is_dup = False
        for k in kept:
            kt = (k.get('raw_latex') or '').strip()
            if not kt:
                continue
            # substring check
            if rt in kt or kt in rt:
                is_dup = True
                break
            # prefix check
            min_len = min(len(rt), len(kt))
            if min_len > 40 and rt[:40] == kt[:40]:
                is_dup = True
                break
        if not is_dup:
            kept.append(r)

    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------
def extract_distilled_definition(text: str) -> List[dict]:
    results: List[dict] = []

    # Build a masked version of the text so inline patterns don't fire
    # inside definition environments or theorem-like environments.
    masked = _mask_regions(text, _DEF_ENV_RE)
    masked = _mask_regions(masked, _THEOREM_ENV_RE)

    # ------------------------------------------------------------------
    # C5: Paragraph definitions right after \section / \subsection
#     # ------------------------------------------------------------------
#     for m in inline_section_def_pattern.finditer(text):
#         full_text = m.group('full').strip()
#         if not full_text:
#             continue
#         if not _section_def_keywords.search(full_text):
#             continue
#         if _referential.search(full_text):
#             continue
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         name_raw = full_text[:120].split('.')[0].strip()
#         name_hint = _clean_latex(name_raw)[:80] or None
#         results.append({
#             'raw_latex': full_text,
#             'clean_text': _clean_latex(full_text),
#             'name': name_hint,
#             'env_name': 'distilled',
#             'rule_name': 'inline_section_def_pattern',
#             'structure_type': 'definition',
#         })

    # ------------------------------------------------------------------
    # C6: "X is called Y" definitional sentences
    # ------------------------------------------------------------------
    for anchor_m in _c6_anchor.finditer(masked):
        start_search = max(0, anchor_m.start() - 120)
        prefix = masked[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        if dot_pos >= 0:
            name_start = start_search + dot_pos + 1
        else:
            name_start = start_search
        name_text = masked[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _c6_tail.match(masked, anchor_m.end())
        if not tail_m:
            continue
        full_text = text[name_start:tail_m.end()].strip()
        if not full_text or len(full_text) < 20:
            continue
        if _referential.search(full_text):
            continue
        if _inside_excluded_env(text, name_start, tail_m.end()):
            continue
        name_hint = _clean_latex(name_text)[:80] or None
        results.append({
            'raw_latex': full_text,
            'clean_text': _clean_latex(full_text),
            'name': name_hint,
            'env_name': 'distilled',
            'rule_name': '_c6_anchor',
            'structure_type': 'definition',
        })

    # ------------------------------------------------------------------
    # C7: {\bf Name:} / \textbf{Name:} bold-labeled inline definitions
#     # ------------------------------------------------------------------
#     for m in inline_bf_pattern.finditer(text):
#         full_text = m.group('full').strip()
#         name_raw = m.group('name').strip()
#         if not full_text or len(full_text) < 20:
#             continue
#         if _referential.search(full_text):
#             continue
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         name_hint = _clean_latex(name_raw)[:80] or None
#         results.append({
#             'raw_latex': full_text,
#             'clean_text': _clean_latex(full_text),
#             'name': name_hint,
#             'env_name': 'distilled',
#             'rule_name': 'inline_bf_pattern',
#             'structure_type': 'definition',
#         })

    # ------------------------------------------------------------------
    # C6-ext: "are defined as/to be" with display math in body
    # ------------------------------------------------------------------
    for anchor_m in _c2_anchor_extended.finditer(masked):
        start_search = max(0, anchor_m.start() - 200)
        prefix = masked[start_search:anchor_m.start()]
        dot_pos = prefix.rfind('.')
        if dot_pos >= 0:
            name_start = start_search + dot_pos + 1
        else:
            name_start = start_search
        name_text = masked[name_start:anchor_m.start()].strip()
        if not name_text or len(name_text) > 200:
            continue
        # Try tail match
        search_end = min(len(masked), anchor_m.end() + 800)
        tail_region = masked[anchor_m.end():search_end]
        tail_m = _c2_tail_extended.match(tail_region)
        if not tail_m:
            # Fallback: find next double newline or paragraph break
            para_end = masked.find('\n\n', anchor_m.end())
            if para_end < 0 or para_end - anchor_m.end() > 800:
                continue
            end_pos = para_end
        else:
            end_pos = anchor_m.end() + tail_m.end()
        full_text = text[name_start:end_pos].strip()
        if not full_text or len(full_text) < 20:
            continue
        if _referential.search(full_text):
            continue
        if _inside_excluded_env(text, name_start, end_pos):
            continue
        name_hint = _clean_latex(name_text)[:80] or None
        results.append({
            'raw_latex': full_text,
            'clean_text': _clean_latex(full_text),
            'name': name_hint,
            'env_name': 'distilled',
            'rule_name': '_c2_anchor_extended',
            'structure_type': 'definition',
        })

    # ------------------------------------------------------------------
    # C8: "The X (also called Y) is the ..." definitional sentences
    # ------------------------------------------------------------------
    for m in _c8_pattern.finditer(masked):
        full_text = m.group('full').strip()
        name_raw = m.group('name').strip()
        if not _c8_def_keywords.search(full_text):
            continue
        if _referential.search(full_text):
            continue
        if len(full_text) < 40:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Use original text for raw_latex
        raw_full = text[m.start():m.end()].strip()
        name_hint = _clean_latex(name_raw)[:80] or None
        results.append({
            'raw_latex': raw_full,
            'clean_text': _clean_latex(raw_full),
            'name': name_hint,
            'env_name': 'distilled',
            'rule_name': '_c8_pattern',
            'structure_type': 'definition',
        })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    return _deduplicate(results)
