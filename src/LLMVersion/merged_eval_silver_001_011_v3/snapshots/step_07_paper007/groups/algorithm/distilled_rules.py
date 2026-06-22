import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helper: strip common LaTeX markup to plain text
# ---------------------------------------------------------------------------
def _clean_latex(text: str) -> str:
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common display/inline math markers (keep content)
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$.*?\$', ' ', text, flags=re.DOTALL)
    # Remove \begin{...}...\end{...} for simple environments
    text = re.sub(r'\\begin\{[^}]*\}', '', text)
    text = re.sub(r'\\end\{[^}]*\}', '', text)
    # Remove common LaTeX commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathbf|mathrm|mathit|boldsymbol|'
                  r'bf|it|rm|label|ref|cite[A-Za-z]*|footnote|caption|paragraph|'
                  r'section|subsection|subsubsection)\{([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[A-Za-z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Helper: check whether a match position falls inside an excluded environment
# ---------------------------------------------------------------------------
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|Proof|Example|Remark|rem|note)\}.*?'
    r'\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Helper: extract one level of nested braces content
# ---------------------------------------------------------------------------
def _extract_brace_group(text: str, start: int) -> str:
    """Return content between matched braces starting at `start` (which must be '{')."""
    depth = 0
    result = []
    i = start
    while i < len(text):
        c = text[i]
        if c == '{':
            depth += 1
            if depth > 1:
                result.append(c)
        elif c == '}':
            depth -= 1
            if depth == 0:
                break
            result.append(c)
        else:
            result.append(c)
        i += 1
    return ''.join(result)


# ---------------------------------------------------------------------------
# PATTERN 1: Custom macro ending in 'algorithm' with {title}{body} arguments
#   e.g. \ulesalgorithm{title}{body}
#   Matches any \<prefix>algorithm{...}{...} call
# ---------------------------------------------------------------------------
_MACRO_ALGORITHM_RE = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)\s*'
    r'\{(?P<title>[^{}]*)\}'          # title group — no nested braces
    r'\s*\{',                          # opening brace of body (we parse manually)
    re.DOTALL
)


# ---------------------------------------------------------------------------
# PATTERN 2: \paragraph{... algorithm ...} immediately followed by enumerate
# ---------------------------------------------------------------------------
_PARAGRAPH_ALGORITHM_RE = re.compile(
    r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\}'
    r'[ \t\n]*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    flags=re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# PATTERN 3: enumerate block preceded within ~500 chars by 'algorithm' keyword
#   AND by a trigger phrase like 'following ... steps/procedure/strategy:'
# ---------------------------------------------------------------------------
_PROSE_ENUM_ALGORITHM_RE = re.compile(
    r'(?:algorithm|procedure|strategy|method)\b'
    r'(?:[^\n]{0,500}?)'
    r'following\b[^\n]{0,150}?'
    r'(?:steps?|procedure|strategy)\s*:\s*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    flags=re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# PATTERN 4: enumerate block with >= 4 items (structural proxy for algorithm)
#   Only accepted when NOT already covered by patterns above
# ---------------------------------------------------------------------------
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# _ENUMERATE_BLOCK_RE = re.compile(
#     r'\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}',
#     flags=re.DOTALL
# )
_ITEM_RE = re.compile(r'\\item\b')


# ---------------------------------------------------------------------------
# PATTERN 5: 'following \w+ steps:' immediately before \begin{equation}
# ---------------------------------------------------------------------------
_STEPS_EQUATION_RE = re.compile(
    r'following\s+\w+\s+steps?\s*:\s*'
    r'(?P<body>\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})',
    flags=re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------
def _overlaps(spans: List[tuple], start: int, end: int) -> bool:
    for (s, e) in spans:
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
    # Rule 1: custom macro \<*>algorithm{title}{body}
    # ------------------------------------------------------------------
    for m in _MACRO_ALGORITHM_RE.finditer(text):
        macro_name = m.group('macro')
        title = m.group('title').strip()

        # Skip if macro_name is exactly 'algorithm' or 'Algorithm' — covered by base
        if macro_name.lower() == 'algorithm':
            continue

        # Find the opening brace of the body (m ends just after '{')
        body_start = m.end() - 1  # position of opening '{'
        body = _extract_brace_group(text, body_start)
        match_end = body_start + len(body) + 2  # approximate end

        if _inside_excluded_env(text, m.start(), match_end):
            continue
        if _overlaps(used_spans, m.start(), match_end):
            continue

        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': '_MACRO_ALGORITHM_RE',
            'structure_type': 'algorithm',
        })
        used_spans.append((m.start(), match_end))

    # ------------------------------------------------------------------
    # Rule 2: \paragraph{... algorithm ...} + enumerate
    # ------------------------------------------------------------------
    for m in _PARAGRAPH_ALGORITHM_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(used_spans, start, end):
            continue
        body = m.group('body')
        name = m.group('name').strip()
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': '_PARAGRAPH_ALGORITHM_RE',
            'structure_type': 'algorithm',
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 3: prose 'algorithm ... following ... steps: enumerate'
    # ------------------------------------------------------------------
    for m in _PROSE_ENUM_ALGORITHM_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(used_spans, start, end):
            continue
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_PROSE_ENUM_ALGORITHM_RE',
            'structure_type': 'algorithm',
        })
        used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 4: enumerate with >= 4 items (not already captured)
#     # ------------------------------------------------------------------
#     for m in _ENUMERATE_BLOCK_RE.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         if _overlaps(used_spans, start, end):
#             continue
#         body = m.group('body')
#         item_count = len(_ITEM_RE.findall(body))
#         if item_count < 4:
#             continue
#         clean = _clean_latex(body)
#         results.append({
#             'raw_latex': body,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': '_ENUMERATE_BLOCK_RE',
#             'structure_type': 'algorithm',
#         })
#         used_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 5: 'following N steps:' + equation environment
    # ------------------------------------------------------------------
    for m in _STEPS_EQUATION_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(used_spans, start, end):
            continue
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_STEPS_EQUATION_RE',
            'structure_type': 'algorithm',
        })
        used_spans.append((start, end))

    return results
