import re
from typing import List, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX markup to produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, etc.
    text = re.sub(r'\\(?:label|ref|cite[a-zA-Z]*|eqref)\{[^}]*\}', '', text)
    # Remove \begin{...} and \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove common formatting macros but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathbf|mathrm|mathit|boldsymbol|bf|it|rm)\{([^}]*)\}', r'\1', text)
    # Remove display math environments
    text = re.sub(r'\\\[.*?\\\]', ' [math] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$[^$]*\$', ' [math] ', text, flags=re.DOTALL)
    # Remove remaining macros with one argument
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining macros without arguments
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    # Remove stray braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments to exclude (results inside these are discarded)
_EXCLUDED_ENVS = ['proof', 'example', 'remark', 'note', 'rem']

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    prefix = text[:start]
    for env in _EXCLUDED_ENVS:
        begin_pat = re.compile(r'\\begin\{' + re.escape(env) + r'\}', re.IGNORECASE)
        end_pat = re.compile(r'\\end\{' + re.escape(env) + r'\}', re.IGNORECASE)
        begins = [m.start() for m in begin_pat.finditer(prefix)]
        ends = [m.start() for m in end_pat.finditer(prefix)]
        if len(begins) > len(ends):
            return True
    return False


def _balance_braces(text: str, start: int) -> int:
    """
    Given text and a position right after an opening '{', return the position
    of the matching closing '}'. Returns -1 if not found.
    """
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    if depth == 0:
        return i - 1
    return -1


def _extract_brace_arg(text: str, pos: int) -> Tuple[Optional[str], int]:
    """
    Extract the content of a brace-delimited argument starting at or after pos.
    Returns (content, end_pos) or (None, pos) if no brace found.
    """
    # Skip whitespace
    i = pos
    while i < len(text) and text[i] in ' \t\n\r':
        i += 1
    if i >= len(text) or text[i] != '{':
        return None, pos
    end = _balance_braces(text, i + 1)
    if end == -1:
        return None, pos
    return text[i+1:end], end + 1


# ---------------------------------------------------------------------------
# Pattern 1: Custom macro ending in 'algorithm' with two brace arguments
# e.g. \ulesalgorithm{title}{body} or \myalgorithm{title}{body}
# ---------------------------------------------------------------------------
_MACRO_ALGORITHM_RE = re.compile(
    r'\\(?P<macro>[A-Za-z]+[Aa]lgorithm)\s*\{',
    re.DOTALL
)


def _extract_macro_algorithm(text: str) -> List[dict]:
    """
    Match custom macros whose name ends in 'algorithm' (case-insensitive)
    and takes two brace-delimited arguments: {title}{body}.
    """
    results = []
    for m in _MACRO_ALGORITHM_RE.finditer(text):
        macro_name = m.group('macro')
        # Skip standard \begin{algorithm} - handled by base
        if macro_name.lower() in ('algorithm',):
            continue
        # The match ends just after the opening '{' of the first argument
        title_start = m.end()  # position right after the '{'
        title_end = _balance_braces(text, title_start)
        if title_end == -1:
            continue
        title = text[title_start:title_end].strip()
        # Now find the second argument
        body_content, body_end = _extract_brace_arg(text, title_end + 1)
        if body_content is None:
            continue
        source_start = m.start()
        source_end = body_end
        if _inside_excluded_env(text, source_start, source_end):
            continue
        results.append({
            'raw_latex': body_content,
            'clean_text': _clean_latex(body_content),
            'name': _clean_latex(title) if title else None,
            'env_name': 'distilled',
            'rule_name': '_MACRO_ALGORITHM_RE',
            'structure_type': 'algorithm',
            '_source_start': source_start,
            '_source_end': source_end,
        })
    return results


# ---------------------------------------------------------------------------
# Pattern 2: \paragraph{... algorithm ...} followed by \begin{enumerate}...\end{enumerate}
# ---------------------------------------------------------------------------
_PARA_ALG_ENUM_RE = re.compile(
    r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\}'
    r'(?P<gap>[^\\]{0,200}?)'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    flags=re.DOTALL | re.IGNORECASE
)


def _extract_paragraph_algorithm(text: str) -> List[dict]:
    """
    Match \\paragraph{... algorithm ...} followed (within ~200 chars) by
    \\begin{enumerate}...\\end{enumerate}.
    """
    results = []
    for m in _PARA_ALG_ENUM_RE.finditer(text):
        name = m.group('name').strip()
        body = m.group('body')
        source_start = m.start()
        source_end = m.end()
        if _inside_excluded_env(text, source_start, source_end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': _clean_latex(name) if name else None,
            'env_name': 'distilled',
            'rule_name': '_PARA_ALG_ENUM_RE',
            'structure_type': 'algorithm',
            '_source_start': source_start,
            '_source_end': source_end,
        })
    return results


# ---------------------------------------------------------------------------
# Pattern 3: Prose with "algorithm" + "following ... steps/procedure:" +
# \begin{enumerate}...\end{enumerate}
# ---------------------------------------------------------------------------
_PROSE_ALG_ENUM_RE = re.compile(
    r'(?:'
    r'(?:algorithm|procedure|strategy|method)\b'
    r'[^\n]{0,500}?'
    r')?'
    r'following\s+\w[\w\s]{0,60}?'
    r'(?:steps|procedure|strategy)\s*:\s*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    flags=re.DOTALL | re.IGNORECASE
)


def _extract_prose_algorithm_enum(text: str) -> List[dict]:
    """
    Match prose descriptions that lead into an enumerate block as an algorithm.
    Anchor: 'following ... steps/procedure/strategy:' immediately before enumerate.
    """
    results = []
    for m in _PROSE_ALG_ENUM_RE.finditer(text):
        body = m.group('body')
        source_start = m.start()
        source_end = m.end()
        if _inside_excluded_env(text, source_start, source_end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_PROSE_ALG_ENUM_RE',
            'structure_type': 'algorithm',
            '_source_start': source_start,
            '_source_end': source_end,
        })
    return results


# ---------------------------------------------------------------------------
# Pattern 4: "following ... steps:" + \begin{equation}...\end{equation}
# (for algorithms described via a key equation right after "steps:")
# ---------------------------------------------------------------------------
_STEPS_EQ_RE = re.compile(
    r'following\s+\w[\w\s]{0,60}?steps\s*:\s*'
    r'(?P<body>\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})',
    flags=re.DOTALL | re.IGNORECASE
)


def _extract_steps_equation_algorithm(text: str) -> List[dict]:
    """
    Match 'following ... steps:' immediately before a display equation
    (used when an algorithm is defined by key equations rather than enumerate).
    """
    results = []
    for m in _STEPS_EQ_RE.finditer(text):
        body = m.group('body')
        source_start = m.start()
        source_end = m.end()
        if _inside_excluded_env(text, source_start, source_end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_STEPS_EQ_RE',
            'structure_type': 'algorithm',
            '_source_start': source_start,
            '_source_end': source_end,
        })
    return results


# ---------------------------------------------------------------------------
# Pattern 5: Large enumerate blocks (>= 4 items) used as algorithm steps.
# Only when the enumerate is NOT already captured by patterns 2/3 above.
# ---------------------------------------------------------------------------
# PRUNED — FP on paper001, paper009 | also 1 TP — review before uncommenting
# _LARGE_ENUMERATE_RE = re.compile(
#     r'\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}',
#     flags=re.DOTALL
# )


def _extract_large_enumerate_algorithm(text: str) -> List[dict]:
    """
    Structural heuristic: an enumerate environment with >= 4 \\item entries
    is likely an algorithmic step list.
    """
    results = []
#     for m in _LARGE_ENUMERATE_RE.finditer(text):
#         body = m.group('body')
#         item_count = len(re.findall(r'\\item', body))
#         if item_count < 4:
#             continue
#         source_start = m.start()
#         source_end = m.end()
#         if _inside_excluded_env(text, source_start, source_end):
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': '_LARGE_ENUMERATE_RE',
#             'structure_type': 'algorithm',
#             '_source_start': source_start,
#             '_source_end': source_end,
#         })
    return results


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(matches: List[dict]) -> List[dict]:
    """
    Remove overlapping matches, keeping the one that appears first (leftmost).
    Two matches overlap if their source spans intersect.
    """
    # Sort by start position, then by span length descending (prefer longer)
    matches.sort(key=lambda x: (x['_source_start'], -(x['_source_end'] - x['_source_start'])))
    kept = []
    max_end = -1
    for match in matches:
        s = match['_source_start']
        e = match['_source_end']
        if s >= max_end:
            kept.append(match)
            max_end = e
        # else: overlaps with a previously kept match — skip
    return kept


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    """
    Extract algorithm structures from LaTeX source that are NOT already
    captured by the base _extract_algorithms method (which handles standard
    \\begin{algorithm}...\\end{algorithm} environments).

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    all_matches: List[dict] = []

    all_matches.extend(_extract_macro_algorithm(text))
    all_matches.extend(_extract_paragraph_algorithm(text))
    all_matches.extend(_extract_prose_algorithm_enum(text))
    all_matches.extend(_extract_steps_equation_algorithm(text))
    all_matches.extend(_extract_large_enumerate_algorithm(text))

    # Deduplicate overlapping spans
    all_matches = _deduplicate(all_matches)

    # Remove internal position keys before returning
    result = []
    for m in all_matches:
        clean = {k: v for k, v in m.items() if not k.startswith('_')}
        result.append(clean)

    return result
