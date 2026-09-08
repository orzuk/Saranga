import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and return plain text."""
    # Remove \label{...}
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # Remove \cite..{...}
    text = re.sub(r'\\cite[A-Za-z]*\{[^}]*\}', '', text)
    # Remove \ref{...}
    text = re.sub(r'\\ref\{[^}]*\}', '', text)
    # Remove \nonumber, \notag
    text = re.sub(r'\\(nonumber|notag)\b', '', text)
    # Remove display math environments but keep content
    text = re.sub(r'\\begin\{(align\*?|equation\*?|array|cases|gather\*?)\}', '', text)
    text = re.sub(r'\\end\{(align\*?|equation\*?|array|cases|gather\*?)\}', '', text)
    # Replace \\ with space
    text = re.sub(r'\\\\', ' ', text)
    # Replace \ba and \ea with space
    text = re.sub(r'\\ba\b', ' ', text)
    text = re.sub(r'\\ea\b', ' ', text)
    # Remove \text{...} wrapper but keep content
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    # Remove remaining simple commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


EXCLUDED_ENVS = ['proof', 'Proof', 'example', 'Example', 'remark', 'Remark',
                 'rem', 'note', 'exam', 'ex', 'exercise', 'Exercise']

_EXCLUDED_BEGIN = re.compile(
    r'\\begin\{(' + '|'.join(re.escape(e) for e in EXCLUDED_ENVS) + r')\}',
    re.DOTALL
)
_EXCLUDED_END = re.compile(
    r'\\end\{(' + '|'.join(re.escape(e) for e in EXCLUDED_ENVS) + r')\}',
    re.DOTALL
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    prefix = text[:start]
    begins = list(_EXCLUDED_BEGIN.finditer(prefix))
    ends = list(_EXCLUDED_END.finditer(prefix))
    # Count unclosed excluded environments
    open_count = len(begins) - len(ends)
    return open_count > 0


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove overlapping results, keeping the one with the longest raw_latex."""
    if not results:
        return results
    # Sort by position if available, else by length descending
    results_sorted = sorted(results, key=lambda r: (r.get('_start', 0), -len(r['raw_latex'])))
    deduped = []
    last_end = -1
    for r in results_sorted:
        s = r.get('_start', 0)
        e = r.get('_end', s + len(r['raw_latex']))
        if s >= last_end:
            deduped.append(r)
            last_end = e
        else:
            # Overlap: keep longer
            if len(r['raw_latex']) > len(deduped[-1]['raw_latex']):
                deduped[-1] = r
                last_end = e
    # Remove internal position keys
    for r in deduped:
        r.pop('_start', None)
        r.pop('_end', None)
    return deduped


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: \ba...\ea blocks preceded by a lead-in sentence containing
# problem-signaling content (graph cut, partition, mincut, RatioCut, Ncut,
# MinmaxCut, objective function, criterion, etc.)
# Used for paper001 free-text problems (test cases 1-4)
BA_EA_PROBLEM_PATTERN = re.compile(
    r'(?:^|(?<=\n\n)|(?<=\\\\)\s*\n?)'       # start of paragraph or after \\
    r'(?P<preamble>[^\n]{10,800}?)'            # lead-in prose on same or nearby lines
    r'(?:\\ba|\\begin\{align\*?\})\s*'         # start of display math
    r'(?P<body>.*?)'                           # math body
    r'(?:\\ea|\\end\{align\*?\})',             # end of display math
    re.DOTALL
)

# Signals in preamble that indicate a problem/definition
_PROBLEM_SIGNAL = re.compile(
    r'(?:mincut|cut|partition|RatioCut|Ratiocut|Ncut|MinmaxCut|'
    r'objective\s+function|criterion|minimize|maximiz|minimiz|'
    r'simply\s+consists|definitions?\s+are|'
    r'approach|problem|graph\s+cut)',
    re.IGNORECASE
)

# Pattern 2: \begin{equation}...\end{equation} containing (P_N) — labeled optimization problems
EQUATION_PROBLEM_PATTERN = re.compile(
    r'\\begin\{(equation\*?)\}'
    r'(?:\s*\\label\{[^}]*\})?\s*'
    r'(?P<body>.*?'
    r'\(P[_0-9A-Za-z]*\)'          # must contain (P_0), (P_1), etc.
    r'.*?)'
    r'\\end\{equation\*?\}',
    re.DOTALL
)

# Pattern 3: \begin{align}...\end{align} or align* containing (P_N) — labeled optimization problems
ALIGN_PROBLEM_PATTERN = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?'
    r'\(P[_0-9A-Za-z]*\)'          # must contain (P_0), (P_1), etc.
    r'.*?)'
    r'\\end\{align\*?\}',
    re.DOTALL
)

# Pattern 4: \begin{align}...\end{align} containing \max or \min + subject-to
# Used for paper002/paper003 optimization problems (test cases 6-9)
OPTIMIZATION_ALIGN_PATTERN = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{align\*?\}',
    re.DOTALL
)

_OPT_VERB = re.compile(r'\\(max|min)\b', re.IGNORECASE)
_ST_MARKER = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|\\text\s*\{\s*subject\s+to\s*\}|'
    r'\\mathrm\s*\{\s*s\.?\s*t\.?\s*\}',
    re.IGNORECASE
)

# Pattern 5: prose paragraph followed by \begin{align}...\end{align} containing
# \max/\min + s.t., with the paragraph as context (for test cases 8-9)
# We also want to capture the surrounding prose as part of the "problem"
PROSE_PLUS_ALIGN_PATTERN = re.compile(
    r'(?P<preamble>[^\n]{10,600}?[.:])\s*\n+'   # sentence ending in . or :
    r'(?P<align>\\begin\{(align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{align\*?\})',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Subtype resolution
# ---------------------------------------------------------------------------

_SUBTYPE_MAP = {
    'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
    'lemma': 'lemma', 'lem': 'lemma',
    'proposition': 'proposition', 'prop': 'proposition',
    'corollary': 'corollary', 'cor': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'problem': 'problem',
    'align': 'problem', 'align*': 'problem',
    'equation': 'problem', 'equation*': 'problem',
    'freetext_ba': 'problem',
    'freetext_align': 'problem',
    'optimization': 'problem',
}


def _resolve_subtype(env_name: str, body: str) -> str:
    key = env_name.strip('*').lower()
    if key in _SUBTYPE_MAP:
        return _SUBTYPE_MAP[key]
    # Try to detect from body
    body_lower = body.lower()
    for word, stype in [('theorem', 'theorem'), ('lemma', 'lemma'),
                        ('proposition', 'proposition'), ('corollary', 'corollary'),
                        ('conjecture', 'conjecture'), ('problem', 'problem'),
                        ('claim', 'claim')]:
        if word in body_lower:
            return stype
    return 'theorem'


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    """
    Extract theorem-like structures not caught by the base environment extractor.
    Focuses on:
      - Free-text problems described with \\ba...\\ea or align blocks (paper001)
      - equation/align environments containing (P_N) problem labels (paper002)
      - align environments with \\max/\\min + s.t. optimization problems (paper002/003)
    """
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \ba...\ea or \begin{align}\end{align} free-text problems
    # for paper001-style content (test cases 1-4)
    # ------------------------------------------------------------------
    # We match: preamble sentence + \ba body \ea
    # PRUNED — FP on paper001, paper003 | also 6 TP — review before uncommenting
#     ba_ea_pattern = re.compile(
#         r'(?P<preamble>(?:[^\n]|\n(?!\n)){20,600}?)'
#         r'(?:\\ba\s*(?P<body1>.*?)\\ea|'
#         r'\\begin\{align\*?\}\s*(?P<body2>.*?)\\end\{align\*?\})',
#         re.DOTALL
#     )

#     for m in ba_ea_pattern.finditer(text):
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue

#         preamble = m.group('preamble') or ''
#         body1 = m.group('body1') or ''
#         body2 = m.group('body2') or ''
#         body = body1 if body1 else body2

#         # Only accept if preamble contains problem-signaling text
#         if not _PROBLEM_SIGNAL.search(preamble):
#             continue

#         # Skip if the body contains \max/\min with s.t. (handled by Rule C)
#         if _OPT_VERB.search(body) and _ST_MARKER.search(body):
#             continue

#         # Skip if body contains (P_N) pattern (handled by Rule B)
#         if re.search(r'\(P[_0-9A-Za-z]*\)', body):
#             continue

#         combined_raw = preamble.strip() + '\n' + body.strip()
#         clean = _clean_latex(combined_raw)

#         results.append({
#             'raw_latex': combined_raw,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'ba_ea_pattern',
#             'structure_type': 'problem',
#             '_start': start,
#             '_end': end,
#         })

    # ------------------------------------------------------------------
    # Rule B: equation or align environments containing (P_N) labels
    # for paper002-style labeled problems (test cases 6-7)
    # ------------------------------------------------------------------
    eq_pn_pattern = re.compile(
        r'\\begin\{(equation\*?|align\*?)\}'
        r'(?:\[(?P<opt>[^\]]*)\])?'
        r'(?P<body>.*?\(P[_0-9A-Za-z]*\).*?)'
        r'\\end\{(?:equation\*?|align\*?)\}',
        re.DOTALL
    )

    for m in eq_pn_pattern.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue

        env = m.group(1)
        body = m.group('body')
        raw = m.group(0)
        clean = _clean_latex(raw)

        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'eq_pn_pattern',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule C: align environments with \max/\min + subject-to constraints
    # for paper002/paper003 optimization problems (test cases 6-9)
    # Also capture optional leading prose paragraph
    # ------------------------------------------------------------------
    opt_align_pattern = re.compile(
        r'(?P<prose>(?:[^\n]|\n(?!\n)){10,600}?[.:\n])\s*\n*'
        r'(?P<align>\\begin\{(align\*?)\}'
        r'(?P<body>.*?)'
        r'\\end\{align\*?\})',
        re.DOTALL
    )

    for m in opt_align_pattern.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue

        body = m.group('body')
        prose = m.group('prose') or ''
        align_block = m.group('align')

        if not (_OPT_VERB.search(body) and _ST_MARKER.search(body)):
            continue

        # Skip if this also has (P_N) — handled by Rule B with same align block
        # We still want this for paper003 test cases 8-9 which don't have (P_N)
        # but do have prose + align with max/min + s.t.
        raw = prose.strip() + '\n' + align_block.strip()
        clean = _clean_latex(raw)

        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'opt_align_pattern',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # Also catch bare align blocks (no prose) with max/min + s.t.
    # PRUNED — FP on paper003
#     bare_opt_pattern = re.compile(
#         r'\\begin\{(align\*?)\}'
#         r'(?P<body>.*?)'
#         r'\\end\{align\*?\}',
#         re.DOTALL
#     )
#     for m in bare_opt_pattern.finditer(text):
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue

#         body = m.group('body')
#         if not (_OPT_VERB.search(body) and _ST_MARKER.search(body)):
#             continue

#         raw = m.group(0)
#         clean = _clean_latex(raw)

#         results.append({
#             'raw_latex': raw,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'bare_opt_pattern',
#             'structure_type': 'problem',
#             '_start': start,
#             '_end': end,
#         })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    return results
