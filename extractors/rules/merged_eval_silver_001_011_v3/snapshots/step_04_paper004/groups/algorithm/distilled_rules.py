import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule A: custom macros of the form \<word>algorithm{title}{body}
# where body may contain one level of nested braces
PATTERN_MACRO_ALGORITHM = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)\s*'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# Rule B: enumerate environments that look like procedural step lists
# (structural heuristic: >= 4 \item entries)
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# PATTERN_ENUMERATE_STEPS = re.compile(
#     r'\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}',
#     re.DOTALL
# )

# Rule C: sections/subsections whose heading contains the word "algorithm"
# followed by prose content up to the next section heading
PATTERN_ALGORITHM_SECTION = re.compile(
    r'\\(?:sub)*section\*?\s*\{(?P<title>[^}]*\balgorithm\b[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.IGNORECASE | re.DOTALL
)

# Excluded environments: proof, example, remark, table, figure
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|table|figure|tikzpicture)\}',
    re.IGNORECASE
)

_EXCLUDED_ENV_BLOCK_RE = re.compile(
    r'\\begin\{(?P<env>proof|example|remark|table|figure|tikzpicture)\}'
    r'.*?'
    r'\\end\{(?P=env)\}',
    re.IGNORECASE | re.DOTALL
)

# For cleaning LaTeX to plain text
_LATEX_CMD_RE = re.compile(r'\\[A-Za-z]+\*?')
_LATEX_MATH_RE = re.compile(r'\$\$.*?\$\$|\$.*?\$', re.DOTALL)
_LATEX_BRACE_RE = re.compile(r'[{}]')
_LATEX_COMMENT_RE = re.compile(r'%[^\n]*')
_MULTI_SPACE_RE = re.compile(r'\s+')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip LaTeX markup to approximate plain text."""
    text = _LATEX_COMMENT_RE.sub('', text)
    text = _LATEX_MATH_RE.sub(' ', text)
    text = _LATEX_CMD_RE.sub(' ', text)
    text = _LATEX_BRACE_RE.sub('', text)
    text = _MULTI_SPACE_RE.sub(' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    for m in _EXCLUDED_ENV_BLOCK_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _overlaps(spans: List[tuple], start: int, end: int) -> bool:
    """Return True if [start, end) overlaps with any span in the list."""
    for s, e in spans:
        if start < e and end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []
    used_spans: List[tuple] = []

    # ------------------------------------------------------------------
    # Rule A: \<word>algorithm{title}{body} macro invocations
    # ------------------------------------------------------------------
    for m in PATTERN_MACRO_ALGORITHM.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(used_spans, start, end):
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
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule B: enumerate environments with >= 4 \item (procedural steps)
#     # ------------------------------------------------------------------
#     for m in PATTERN_ENUMERATE_STEPS.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         if _overlaps(used_spans, start, end):
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
#         used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule C: sections with "algorithm" in the heading — prose algorithms
    # Only add if the body is non-trivial (> 100 chars) and contains
    # procedural signal words to reduce false positives.
    # ------------------------------------------------------------------
    _PROCEDURAL_SIGNAL = re.compile(
        r'\b(step|input|output|procedure|repeat|iterate|compute|select|sample|initialize|return)\b',
        re.IGNORECASE
    )
    for m in PATTERN_ALGORITHM_SECTION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(used_spans, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 100:
            continue
        clean = _clean_latex(body)
        if not _PROCEDURAL_SIGNAL.search(clean):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_ALGORITHM_SECTION',
            'structure_type': 'algorithm',
        })
        used_spans.append((start, end))

    return results
