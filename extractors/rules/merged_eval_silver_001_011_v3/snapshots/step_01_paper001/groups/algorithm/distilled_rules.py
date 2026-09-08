import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Match any custom macro whose name ends with "algorithm" (case-insensitive)
# followed by two brace-delimited arguments: {title}{body}.
# Body may contain one level of nested braces.
ALGO_MACRO_TWO_ARGS = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# Match any custom macro whose name ends with "algorithm" (case-insensitive)
# followed by ONE brace-delimited argument: {body} (no separate title arg).
ALGO_MACRO_ONE_ARG = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# Excluded environments: proof, example, remark, figure, table
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|figure|figure\*|table|table\*)\}',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX-to-plain-text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common formatting commands but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|mathbf|boldsymbol|bf|it)\{([^{}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite* commands
    text = re.sub(r'\\(?:label|ref|citeA?|citep|citet|cite)\{[^{}]*\}', '', text)
    # Remove \blobb and similar single-arg macros, keep content
    text = re.sub(r'\\[A-Za-z]+\{([^{}]*)\}', r'\1', text)
    # Remove remaining macros
    text = re.sub(r'\\[A-Za-z]+\*?', ' ', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    # Look for excluded \begin before start; check if corresponding \end comes after start
    prefix = text[:start]
    for m in _EXCLUDED_ENV_RE.finditer(prefix):
        env_name = m.group(1)
        end_pattern = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\}',
            re.IGNORECASE
        )
        # Find last \end{env} before start
        ends_before = list(end_pattern.finditer(prefix))
        begins_before = list(re.finditer(
            r'\\begin\{' + re.escape(env_name) + r'\}',
            prefix,
            re.IGNORECASE
        ))
        if len(begins_before) > len(ends_before):
            # We are inside an open excluded environment
            return True
    return False


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the first (longest) one."""
    # Sort by start position
    results_sorted = sorted(results, key=lambda d: d.get('_start', 0))
    deduped = []
    last_end = -1
    for r in results_sorted:
        s = r.get('_start', 0)
        e = r.get('_end', 0)
        if s >= last_end:
            deduped.append(r)
            last_end = e
    for r in deduped:
        r.pop('_start', None)

    return deduped


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    """
    Extract algorithm structures from LaTeX source that are NOT caught by the
    base \\begin{algorithm}...\\end{algorithm} extractor.

    Targets: custom macros whose names end with 'algorithm' (e.g. \\ulesalgorithm,
    \\myalgorithm, etc.) taking either two brace-delimited arguments {title}{body}
    or one brace-delimited argument {body}.
    """
    results: List[dict] = []
    seen_spans = set()

    # --- Pattern: \<*algorithm>{title}{body} ---
    for m in ALGO_MACRO_TWO_ARGS.finditer(text):
        start, end = m.start(), m.end()
        if (start, end) in seen_spans:
            continue
        if _inside_excluded_env(text, start, end):
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
            'rule_name': 'ALGO_MACRO_TWO_ARGS',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })
        seen_spans.add((start, end))

    # --- Pattern: \<*algorithm>{body} (one-arg form) ---
    # Only catch macros NOT already matched by the two-arg pattern.
    for m in ALGO_MACRO_ONE_ARG.finditer(text):
        start, end = m.start(), m.end()
        if (start, end) in seen_spans:
            continue
        # Skip if this start position is already covered
        already_covered = any(
            s <= start < e for (s, e) in seen_spans
        )
        if already_covered:
            continue
        if _inside_excluded_env(text, start, end):
            continue

        macro = m.group('macro')
        body = m.group('body')
        clean = _clean_latex(body)

        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'ALGO_MACRO_ONE_ARG',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })
        seen_spans.add((start, end))

    # Deduplicate and strip internal position keys
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
