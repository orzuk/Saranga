import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: Custom macro of the form \<word>algorithm{title}{body}
# Matches any macro ending in 'algorithm' (case-insensitive) with two
# brace-delimited arguments. Body may contain one level of nested braces.
PATTERN_MACRO_ALGORITHM = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\}|\{(?:[^{}]|\{[^{}]*\})*\})*)\}',
    re.DOTALL,
)

# Pattern 2: enumerate environment used as a procedural step list
# Structural heuristic: >= 4 \item entries
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# PATTERN_ENUMERATE_STEPS = re.compile(
#     r'\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}',
#     re.DOTALL,
# )

# Environments to exclude (proof, example, remark, figure, table)
EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|figure|figure\*|table|table\*)\}',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...} etc.
    text = re.sub(r'\\(?:label|ref|cite[A-Za-z]*|pageref)\{[^}]*\}', '', text)
    # Remove \begin{...} and \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math environments ($$...$$)
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math ($...$)
    text = re.sub(r'\$[^$]*\$', ' [MATH] ', text)
    # Remove \textbf, \textit, \emph, \boldsymbol, \mathbf, etc.
    text = re.sub(r'\\(?:textbf|textit|emph|boldsymbol|mathbf|mathrm|mathcal|mathbb|bf|it)\{([^}]*)\}', r'\1', text)
    # Remove remaining simple commands with one argument
    text = re.sub(r'\\[A-Za-z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining backslash commands
    text = re.sub(r'\\[A-Za-z]+\*?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the span [start, end) is inside an excluded environment
    (proof, example, remark, figure, table).
    """
    excluded_envs = [
        'proof', 'Proof', 'example', 'Example',
        'remark', 'Remark', 'figure', 'figure*',
        'table', 'table*',
    ]
    for env in excluded_envs:
        env_open = re.compile(
            r'\\begin\{' + re.escape(env) + r'\}',
            re.DOTALL,
        )
        env_close = re.compile(
            r'\\end\{' + re.escape(env) + r'\}',
            re.DOTALL,
        )
        for om in env_open.finditer(text):
            if om.start() >= start:
                break
            # Find matching close after the open
            cm = env_close.search(text, om.end())
            if cm and cm.end() > start and om.start() < end:
                return True
    return False


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the first encountered."""
    kept = []
    used_spans = []
    for r in results:
        span = (r.get('_start', 0), r.get('_end', 0))
        overlaps = False
        for us in used_spans:
            if span[0] < us[1] and span[1] > us[0]:
                overlaps = True
                break
        if not overlaps:
            kept.append(r)
            used_spans.append(span)
    # Remove internal position keys
    for r in kept:
        r.pop('_start', None)
        r.pop('_end', None)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    """
    Extract algorithm structures NOT already caught by the base parser.

    Covers:
      1. Custom macros of the form \\<word>algorithm{title}{body}
         (e.g. \\ulesalgorithm, \\myalgorithm, etc.)
      2. enumerate environments with >= 4 \\item entries used as
         procedural step lists (structural heuristic only).

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule 1: macro-style algorithm definitions  \<word>algorithm{...}{...}
    # ------------------------------------------------------------------
    for m in PATTERN_MACRO_ALGORITHM.finditer(text):
        start, end = m.start(), m.end()
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
            'rule_name': 'PATTERN_MACRO_ALGORITHM',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule 2: enumerate environments that look like algorithmic step lists
    # (structural signal: >= 4 \item entries)
#     # ------------------------------------------------------------------
#     for m in PATTERN_ENUMERATE_STEPS.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
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
#             '_start': start,
#             '_end': end,
#         })

    # ------------------------------------------------------------------
    # Deduplicate overlapping matches and return
    # ------------------------------------------------------------------
    results.sort(key=lambda r: r.get('_start', 0))
    return _deduplicate(results)
