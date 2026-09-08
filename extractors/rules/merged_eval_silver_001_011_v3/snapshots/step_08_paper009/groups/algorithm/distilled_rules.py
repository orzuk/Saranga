import re
from typing import List, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return plain text approximation."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|eqnarray|gather|multline)\*?\}.*?\\end\{(?:equation|align|eqnarray|gather|multline)\*?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', ' ', text, flags=re.DOTALL)
    # Remove common LaTeX commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|boldsymbol|bf|it)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:label|ref|cite|citeA|citealt|citep|citet|eqref)\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?', ' ', text)
    text = re.sub(r'[{}]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside a proof/example/remark environment."""
    excluded = ['proof', 'Proof', 'example', 'Example', 'remark', 'Remark', 'rem', 'note']
    pattern = re.compile(
        r'\\begin\{(' + '|'.join(map(re.escape, excluded)) + r')\}',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        env_name = m.group(1)
        env_start = m.start()
        if env_start > start:
            break
        end_pattern = re.compile(r'\\end\{' + re.escape(env_name) + r'\}', re.DOTALL)
        end_m = end_pattern.search(text, m.end())
        if end_m and end_m.end() >= end:
            return True
    return False


def _deduplicate(matches: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the one with more raw_latex content."""
    if not matches:
        return matches
    # Sort by source_pos
    matches_sorted = sorted(matches, key=lambda d: d.get('_source_pos', 0))
    result = []
    last_end = -1
    for m in matches_sorted:
        pos = m.get('_source_pos', 0)
        end = pos + len(m.get('raw_latex', ''))
        if pos >= last_end:
            result.append(m)
            last_end = end
        else:
            # Keep the longer one
            if result and end > last_end:
                result[-1] = m
                last_end = end
    return result


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: Custom macro \<word>algorithm{title}{body}
# Matches \ulesalgorithm{title}{body} and similar macros ending in 'algorithm'
# Body allows one level of nested braces
_MACRO_ALGORITHM_RE = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# Rule 2: \paragraph{... algorithm ...} followed by \begin{enumerate}...\end{enumerate}
_PARA_ENUM_ALGORITHM_RE = re.compile(
    r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# Rule 3: Prose containing 'algorithm'/'procedure'/'strategy'/'method' +
#          'following ... steps/procedure/strategy:' + enumerate block
_PROSE_ENUM_ALGORITHM_RE = re.compile(
    r'(?:'
    r'(?:algorithm|procedure|strategy|method)\b[^\n]{0,500}?'
    r')?'
    r'following\s+\w+(?:\s+\w+)?\s*(?:steps|strategy|procedure|stages)\s*[:\-]\s*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# Rule 4: 'following ... steps:' immediately before \begin{equation}
_STEPS_EQUATION_ALGORITHM_RE = re.compile(
    r'following\s+\w+(?:\s+\w+)?\s+steps\s*[:\-]\s*'
    r'(?P<body>\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})',
    re.DOTALL | re.IGNORECASE
)

# Rule 5: Large enumerate blocks (>= 4 items) that appear near algorithmic keywords
# in surrounding context — structural heuristic for procedure descriptions
_LARGE_ENUMERATE_RE = re.compile(
    r'(?P<preamble>[^\n]{0,200}\n?[^\n]{0,200})'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL
)

_ALGO_CONTEXT_KEYWORDS_RE = re.compile(
    r'\b(?:algorithm|procedure|experiment|designed|following|steps?|select|sample|'
    r'compute|repeat|iterate|perform|initialize|output|input)\b',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    """
    Extract algorithm structures from LaTeX source that are NOT caught by the
    base _extract_algorithms method (which handles \\begin{algorithm}...).
    Returns a list of dicts with structure_type='algorithm'.
    """
    results: List[dict] = []

    # -------------------------------------------------------------------
    # Rule 1: Custom macro \<word>algorithm{title}{body}
    # e.g. \ulesalgorithm{Unnormalized spectral clustering}{...}
    # -------------------------------------------------------------------
    for m in _MACRO_ALGORITHM_RE.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        macro = m.group('macro')
        # Skip if the macro IS 'algorithm' / 'Algorithm' — base already handles those
        if re.fullmatch(r'[Aa]lgorithm', macro):
            continue
        title = m.group('title').strip()
        body = m.group('body')
        raw_latex = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': '_MACRO_ALGORITHM_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # -------------------------------------------------------------------
    # Rule 2: \paragraph{... algorithm ...} + \begin{enumerate}...\end{enumerate}
    # -------------------------------------------------------------------
    for m in _PARA_ENUM_ALGORITHM_RE.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        name = m.group('name').strip()
        body = m.group('body')
        raw_latex = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': '_PARA_ENUM_ALGORITHM_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # -------------------------------------------------------------------
    # Rule 3: Prose + 'following ... steps:' + enumerate
    # -------------------------------------------------------------------
    for m in _PROSE_ENUM_ALGORITHM_RE.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        raw_latex = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_PROSE_ENUM_ALGORITHM_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # -------------------------------------------------------------------
    # Rule 4: 'following ... steps:' + equation environment
    # -------------------------------------------------------------------
    for m in _STEPS_EQUATION_ALGORITHM_RE.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        raw_latex = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_STEPS_EQUATION_ALGORITHM_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # -------------------------------------------------------------------
    # Rule 5: Large enumerate blocks (>= 4 items) in algorithmic context
    # Only fire when preamble contains algorithmic keywords AND
    # the enumerate has >= 4 \item entries.
    # This catches procedural lists not wrapped in algorithm/paragraph.
    # -------------------------------------------------------------------
    for m in _LARGE_ENUMERATE_RE.finditer(text):
        start = m.start('body')
        end = m.end('body')
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        preamble = m.group('preamble')
        # Count items
        item_count = len(re.findall(r'\\item', body))
        if item_count < 4:
            continue
        # Check preamble for algorithmic context keywords
        keyword_matches = _ALGO_CONTEXT_KEYWORDS_RE.findall(preamble)
        if len(keyword_matches) < 2:
            continue
        # Skip if this enumerate is already inside a \begin{enumerate}
        # that we already captured via rules 2 or 3 (handled by dedup)
        raw_latex = body
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_LARGE_ENUMERATE_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # -------------------------------------------------------------------
    # Deduplicate overlapping matches
    # -------------------------------------------------------------------
    results = _deduplicate(results)

    # Remove internal helper key before returning
    for r in results:
        r.pop('_source_pos', None)

    return results
