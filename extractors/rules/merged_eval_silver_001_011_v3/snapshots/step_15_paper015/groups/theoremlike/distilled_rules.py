import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# 1. \begin{restatable}{<kind>}{<macro>}[opt] ... \end{restatable}
RESTATABLE_PATTERN = re.compile(
    r'\\begin\{restatable\}'
    r'\{(?P<kind>[^}]+)\}'
    r'\{(?P<macro>[^}]*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{restatable\}',
    flags=re.DOTALL | re.IGNORECASE,
)

# 2. \begin{property}[opt] ... \end{property}  (maps to proposition)
PROPERTY_PATTERN = re.compile(
    r'\\begin\{(property)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{property\}',
    flags=re.DOTALL | re.IGNORECASE,
)

# 3. Optimization problems in equation/align/gather environments whose body
#    contains an objective (\min or \max) AND a constraint marker (s.t./subject to)
OPT_PROBLEM_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<envname>equation|align|gather)\*?\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\*?\}',
    flags=re.DOTALL | re.IGNORECASE,
)
_OBJ_RE = re.compile(r'\\(?:min|max|inf|sup|argmin|argmax)\b', re.IGNORECASE)
_ST_RE  = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}'
    r'|\\mathrm\s*\{\s*s\.?\s*t\.?\s*\}'
    r'|\bsubject\s+to\b',
    re.IGNORECASE | re.DOTALL,
)

# 4. Open-problem paragraphs via prose signals
#    Paragraph = text between two blank lines (or start/end of document)
# PRUNED — FP on paper003, paper007, paper008 +2 more | also 4 TP — review before uncommenting
# OPEN_PROB_PARAGRAPH_PATTERN = re.compile(
#     r'(?:(?<=\n\n)|(?<=\A))'
#     r'(?P<body>'
#     r'(?:(?!\\begin\{(?:proof|example|remark)\}).){40,2000}?'
#     r'(?:'
#     r'[Ww]e\s+leave\b[^.]{0,400}?(?:open\s+(?:question|problem)|future\s+work)'
#     r'|remain(?:s)?\s+open\b'
#     r'|open\s+(?:question|problem)s?\b[^.]{0,300}'
#     r'|[Ww]e\s+leave\s+(?:this|these|it|the\s+following)\b[^.]{0,300}?(?:to|for)\s+future\s+work'
#     r')'
#     r'[^.]{0,300}\.'
#     r'(?:[^.]*\.){0,5}'
#     r')'
#     r'(?=\n\n|\Z)',
#     flags=re.DOTALL,
# )

# 5. Interrogative paragraphs inside open-problem / discussion / future-work sections
OPEN_SECTION_RE = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*(?:open\s*(?:problem|question)s?|discussion|conclusion|future\s*work)[^}]*\}',
    flags=re.IGNORECASE,
)

# Excluded environments — matches must not be inside these
_EXCLUDED_ENVS = ['proof', 'example', 'remark', 'note', 'algorithmic', 'algorithm']

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text cleaning."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their arguments
    text = re.sub(r'\\(?:emph|textbf|textit|text|mathrm|mathbf|mathit|mathcal)\{([^}]*)\}', r'\1', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \cref{...}, \eqref{...}
    text = re.sub(r'\\(?:label|ref|eqref|cite[tp]?|cref|autoref)\{[^}]*\}', '', text)
    # Remove \begin/\end
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is nested inside an excluded environment."""
    for env in _EXCLUDED_ENVS:
        pattern = re.compile(
            r'\\begin\{' + re.escape(env) + r'\*?\}.*?\\end\{' + re.escape(env) + r'\*?\}',
            re.DOTALL | re.IGNORECASE,
        )
        for m in pattern.finditer(text):
            if m.start() <= start and end <= m.end():
                return True
    return False


def _subtype_from_kind(kind_str: str) -> str:
    """Normalise a raw environment kind string to a canonical subtype."""
    s = kind_str.lower().rstrip('*').strip()
    mapping = {
        'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
        'lemma': 'lemma', 'lem': 'lemma',
        'proposition': 'proposition', 'prop': 'proposition',
        'property': 'proposition',
        'corollary': 'corollary', 'cor': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem',
        'open_problem': 'open_problem', 'openproblem': 'open_problem',
        'openquestion': 'open_problem', 'open': 'open_problem',
    }
    return mapping.get(s, 'theorem')


def _dedup(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex substantially overlaps an earlier one."""
    kept: List[dict] = []
    for r in sorted(results, key=lambda x: x.get('_start', 0)):
        s = r.get('_start', 0)
        e = r.get('_end', s + len(r['raw_latex']))
        overlap = False
        for k in kept:
            ks = k.get('_start', 0)
            ke = k.get('_end', ks + len(k['raw_latex']))
            # overlap if intervals share more than 50 chars
            overlap_len = max(0, min(e, ke) - max(s, ks))
            if overlap_len > 50:
                overlap = True
                break
        if not overlap:
            kept.append(r)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \begin{restatable}{<kind>}{...} ... \end{restatable}
    # ------------------------------------------------------------------
    for m in RESTATABLE_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        inner_kind = m.group('kind').strip()
        subtype = _subtype_from_kind(inner_kind)
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'RESTATABLE_PATTERN',
            'structure_type': subtype,
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule B: \begin{property}[opt] ... \end{property} -> proposition
    # ------------------------------------------------------------------
    for m in PROPERTY_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PROPERTY_PATTERN',
            'structure_type': 'proposition',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule C: equation/align/gather blocks containing min/max + s.t.
    #         -> problem
    # ------------------------------------------------------------------
    for m in OPT_PROBLEM_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if not (_OBJ_RE.search(body) and _ST_RE.search(body)):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPT_PROBLEM_ENV_PATTERN',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule D: Prose paragraphs with open-problem signal phrases
#     # ------------------------------------------------------------------
#     for m in OPEN_PROB_PARAGRAPH_PATTERN.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         body = m.group('body').strip()
#         if len(body) < 60:
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'OPEN_PROB_PARAGRAPH_PATTERN',
#             'structure_type': 'open_problem',
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # ------------------------------------------------------------------
    # Rule E: Interrogative paragraphs (containing '?') inside
    #         sections whose headings mention open-problems/discussion/
    #         conclusion/future-work
    # ------------------------------------------------------------------
    for sec_m in OPEN_SECTION_RE.finditer(text):
        sec_start = sec_m.end()
        # Find the next section/subsection heading to bound the search
        next_sec = re.search(r'\\(?:sub)*section\*?\{', text[sec_start:])
        sec_end = sec_start + next_sec.start() if next_sec else len(text)
        section_body = text[sec_start:sec_end]

        # Split into paragraphs
        paragraphs = re.split(r'\n{2,}', section_body)
        pos = sec_start
        for para in paragraphs:
            stripped = para.strip()
            # Require at least one '?' and meaningful length
            if '?' in stripped and len(stripped) >= 80:
                if not _inside_excluded_env(text, pos, pos + len(para)):
                    results.append({
                        'raw_latex': stripped,
                        'clean_text': _clean_latex(stripped),
                        'name': None,
                        'env_name': 'distilled',
                        'rule_name': 'OPEN_SECTION_RE',
                        'structure_type': 'open_problem',
                        '_start': pos,
                        '_end': pos + len(para),
                    })
            pos += len(para) + 2  # account for the '\n\n' separator

    # ------------------------------------------------------------------
    # Deduplicate and strip internal keys
    # ------------------------------------------------------------------
    deduped = _dedup(results)
    for r in deduped:
        r.pop('_start', None)
        r.pop('_end', None)

    return deduped
