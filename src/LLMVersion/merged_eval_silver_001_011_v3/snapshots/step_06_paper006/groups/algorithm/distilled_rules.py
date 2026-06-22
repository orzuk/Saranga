import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and return approximate plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline)[*]?\}.*?\\end\{(?:equation|align|gather|multline)[*]?\}', ' ', text, flags=re.DOTALL)
    # Remove \command{...} keeping inner text for some
    text = re.sub(r'\\(?:textbf|emph|text|mathrm|mathbf|boldsymbol|bf|it)\{([^}]*)\}', r'\1', text)
    # Remove remaining \command{...}
    text = re.sub(r'\\[A-Za-z]+\{[^}]*\}', ' ', text)
    # Remove remaining \command
    text = re.sub(r'\\[A-Za-z]+\*?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the match [start, end) is inside a proof/example/remark environment."""
    excluded = ['proof', 'Proof', 'example', 'Example', 'remark', 'Remark', 'rem', 'note']
    pattern = re.compile(
        r'\\begin\{(' + '|'.join(map(re.escape, excluded)) + r')\}',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        env_name = m.group(1)
        env_start = m.start()
        if env_start >= end:
            break
        end_pattern = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\}',
            re.DOTALL
        )
        em = end_pattern.search(text, m.end())
        if em:
            env_end = em.end()
            if env_start <= start and end <= env_end:
                return True
    return False


def _deduplicate(matches: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the one with more raw_latex content."""
    if not matches:
        return matches
    # Sort by start position
    matches_with_pos = []
    for m in matches:
        pos = m.get('_source_pos', 0)
        matches_with_pos.append((pos, len(m.get('raw_latex', '')), m))
    matches_with_pos.sort(key=lambda x: x[0])

    result = []
    last_end = -1
    for pos, length, m in matches_with_pos:
        end = pos + length
        if pos >= last_end:
            result.append(m)
            last_end = end
        else:
            # Overlapping: keep longer
            if result and length > len(result[-1].get('raw_latex', '')):
                result[-1] = m
                last_end = max(last_end, end)
    # Remove internal pos key
    for m in result:
        m.pop('_source_pos', None)
    return result


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \<word>algorithm{title}{body} custom macros (e.g. \ulesalgorithm)
# Handles one level of brace nesting in body
MACRO_ALGORITHM_RE = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}',
    re.DOTALL
)

# Rule 2: \paragraph{... algorithm ...} followed by \begin{enumerate}...\end{enumerate}
PARAGRAPH_ALGORITHM_ENUMERATE_RE = re.compile(
    r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\}'
    r'[ \t\r\n]*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# Rule 3: Prose "algorithm ... following ... steps:" then \begin{enumerate}...\end{enumerate}
PROSE_ALGORITHM_ENUMERATE_RE = re.compile(
    r'(?:algorithm|procedure|strategy|method)\b[^\n]{0,500}?'
    r'following[^\n]{0,150}?(?:steps|procedure|strategy)\s*[:\-]\s*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# Rule 4: "following <words> steps:" then \begin{equation*}...\end{equation*}
STEPS_EQUATION_RE = re.compile(
    r'following\s+\w[\w\s]{0,40}?steps\s*[:\-]\s*'
    r'(?P<body>\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})',
    re.DOTALL | re.IGNORECASE
)

# Rule 5: \begin{enumerate}...\end{enumerate} with >= 4 \item entries as standalone
# (catch algorithmic step lists not preceded by \paragraph)
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# ENUMERATE_STEPS_RE = re.compile(
#     r'(?P<body>\\begin\{enumerate\}(?P<inner>.*?)\\end\{enumerate\})',
#     re.DOTALL
# )

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule: MACRO_ALGORITHM_RE ---
    # Custom macros ending in 'algorithm' with {title}{body} syntax
    for m in MACRO_ALGORITHM_RE.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        macro = m.group('macro')
        # Skip if this looks like a standard \begin{algorithm} reference
        if macro.lower() in ('algorithm',):
            continue
        title = m.group('title').strip()
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'MACRO_ALGORITHM_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # --- Rule: PARAGRAPH_ALGORITHM_ENUMERATE_RE ---
    # \paragraph{... algorithm ...} + enumerate block
    for m in PARAGRAPH_ALGORITHM_ENUMERATE_RE.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        name = m.group('name').strip()
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_ALGORITHM_ENUMERATE_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # --- Rule: PROSE_ALGORITHM_ENUMERATE_RE ---
    # Prose description of algorithm with "following ... steps:" + enumerate
    for m in PROSE_ALGORITHM_ENUMERATE_RE.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_ALGORITHM_ENUMERATE_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # --- Rule: STEPS_EQUATION_RE ---
    # "following N steps:" immediately before an equation environment
    for m in STEPS_EQUATION_RE.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'STEPS_EQUATION_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # --- Rule: ENUMERATE_STEPS_RE ---
    # enumerate environments with >= 4 \item entries (standalone algorithmic step lists)
    # Skip if already captured by PARAGRAPH_ALGORITHM_ENUMERATE_RE or PROSE_ALGORITHM_ENUMERATE_RE
    captured_enumerate_starts = set()
    for r in results:
        pos = r.get('_source_pos', -1)
        raw = r.get('raw_latex', '')
        # Mark positions of enumerate bodies already captured
        if r.get('rule_name') in ('PARAGRAPH_ALGORITHM_ENUMERATE_RE', 'PROSE_ALGORITHM_ENUMERATE_RE'):
            idx = text.find(raw, max(0, pos - 20))
            if idx != -1:
                captured_enumerate_starts.add(idx)

#     for m in ENUMERATE_STEPS_RE.finditer(text):
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         inner = m.group('inner')
#         # Count items
#         item_count = len(re.findall(r'\\item', inner))
#         if item_count < 4:
#             continue
#         # Skip if this enumerate was already captured in another rule
#         body_start = text.find(m.group('body'), max(0, start))
#         if body_start in captured_enumerate_starts:
#             continue
#         body = m.group('body')
#         clean = _clean_latex(inner)
#         results.append({
#             'raw_latex': body,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'ENUMERATE_STEPS_RE',
#             'structure_type': 'algorithm',
#             '_source_pos': start,
#         })

    # Deduplicate overlapping results
    results = _deduplicate(results)

    return results
