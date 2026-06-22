import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: Custom macro of the form \<word>algorithm{title}{body}
# where body may contain one level of nested braces.
PATTERN_MACRO_ALGORITHM = re.compile(
    r'\\(?P<macro>[A-Za-z]+[Aa]lgorithm)'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# Pattern 2: enumerate environment used as a procedural step list
# (structural signal: the environment exists; content filter applied in code)
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# PATTERN_ENUMERATE_STEPS = re.compile(
#     r'\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}',
#     re.DOTALL
# )

# Pattern 3: algorithmicx / algorithmic inner environments
# e.g. \begin{algorithmic}...\end{algorithmic}
PATTERN_ALGORITHMIC_ENV = re.compile(
    r'\\begin\{(?P<env>algorithmic[sx*]*|pseudocode|Algorithmic)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

# Pattern 4: \begin{algorithm}...\end{algorithm} variants not caught by base
# (handles algorithm2e, algorithmwh, etc.)
PATTERN_ALGORITHM_ENV_EXTENDED = re.compile(
    r'\\begin\{(?P<env>algorithm[^}]*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

# Excluded environments: do not extract from inside these
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|Proof|Example|Remark)\}.*?\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light cleaning of LaTeX markup to plain text."""
    # Remove comments
    t = re.sub(r'%[^\n]*', '', text)
    # Remove common formatting macros but keep their argument
    t = re.sub(r'\\(?:textbf|textit|emph|textrm|texttt|text|mathbf|mathrm|boldsymbol|bf|it)\{([^{}]*)\}', r'\1', t)
    # Remove \label, \ref, \cite, \citeA etc.
    t = re.sub(r'\\(?:label|ref|eqref|cite[A-Za-z]*)\{[^{}]*\}', '', t)
    # Remove remaining simple macros with one brace argument
    t = re.sub(r'\\[A-Za-z]+\{([^{}]*)\}', r'\1', t)
    # Remove standalone macros
    t = re.sub(r'\\[A-Za-z]+', ' ', t)
    # Collapse whitespace
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENVS.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _overlaps(spans: List[tuple], start: int, end: int) -> bool:
    """Return True if [start, end) overlaps any already-recorded span."""
    for (s, e) in spans:
        if start < e and end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []
    recorded_spans: List[tuple] = []

    # ------------------------------------------------------------------
    # Rule 1: Custom macro \<word>algorithm{title}{body}
    # Catches patterns like \ulesalgorithm{Title}{body} and similar
    # author-defined macros whose name ends with 'algorithm'.
    # ------------------------------------------------------------------
    for m in PATTERN_MACRO_ALGORITHM.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(recorded_spans, start, end):
            continue
        macro = m.group('macro')
        title = m.group('title').strip()
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_MACRO_ALGORITHM',
            'structure_type': 'algorithm',
        })
        recorded_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 2: enumerate environment whose items encode procedural steps
    # Structural heuristic: >= 4 \item entries (not content-dependent).
#     # ------------------------------------------------------------------
#     for m in PATTERN_ENUMERATE_STEPS.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         if _overlaps(recorded_spans, start, end):
#             continue
#         body = m.group('body')
#         item_count = len(re.findall(r'\\item', body))
#         if item_count < 4:
#             continue
#         clean = _clean_latex(body)
#         results.append({
#             'raw_latex': body,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'PATTERN_ENUMERATE_STEPS',
#             'structure_type': 'algorithm',
#         })
#         recorded_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 3: algorithmicx / algorithmic / pseudocode environments
    # These inner environments describe algorithm steps but are not
    # caught by the base extractor (which looks for 'algorithm' env only).
    # ------------------------------------------------------------------
    for m in PATTERN_ALGORITHMIC_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(recorded_spans, start, end):
            continue
        env = m.group('env')
        body = m.group('body')
        opt = m.group('opt')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_ALGORITHMIC_ENV',
            'structure_type': 'algorithm',
        })
        recorded_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 4: Extended algorithm environment variants
    # e.g. \begin{algorithm2e}, \begin{algorithmwh}, etc.
    # The base extractor catches only 'algorithm' and 'algorithm*';
    # this catches other suffixed variants.
    # Guard: skip the plain 'algorithm' and 'algorithm*' names to avoid
    # duplicating what the base method already extracts.
    # ------------------------------------------------------------------
    _base_algorithm_names = {'algorithm', 'algorithm*'}
    for m in PATTERN_ALGORITHM_ENV_EXTENDED.finditer(text):
        start, end = m.start(), m.end()
        env_name_found = m.group('env').lower()
        if env_name_found in _base_algorithm_names:
            continue
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(recorded_spans, start, end):
            continue
        body = m.group('body')
        opt = m.group('opt')
        # Try to extract a name from \caption{...} inside the body
        caption_m = re.search(r'\\caption\{([^{}]*)\}', body)
        name = caption_m.group(1).strip() if caption_m else (opt.strip() if opt else None)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_ALGORITHM_ENV_EXTENDED',
            'structure_type': 'algorithm',
        })
        recorded_spans.append((start, end))

    return results
