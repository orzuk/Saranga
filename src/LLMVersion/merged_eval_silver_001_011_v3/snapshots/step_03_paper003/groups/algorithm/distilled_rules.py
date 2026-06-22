import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup, returning approximate plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \begin{...} / \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math environments (replace with placeholder)
    text = re.sub(r'\$\$.*?\$\$', ' MATH ', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', ' MATH ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$[^$]*\$', ' MATH ', text)
    # Remove common formatting macros but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathbf|boldsymbol|bf|it)\{([^}]*)\}', r'\1', text)
    # Remove labels, refs, cites
    text = re.sub(r'\\(?:label|ref|eqref|cite[A-Za-z]*)\{[^}]*\}', '', text)
    # Remove remaining macros with one brace argument
    text = re.sub(r'\\[A-Za-z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining macros without arguments
    text = re.sub(r'\\[A-Za-z]+\*?', '', text)
    # Remove lone braces
    text = re.sub(r'[{}]', '', text)
    # Normalise whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the region [start, end) is nested inside an environment
    that we want to exclude (proof, example, remark, figure, table).
    """
    excluded = ['proof', 'Proof', 'example', 'Example', 'remark', 'Remark',
                'figure', 'figure*', 'table', 'table*']
    pattern = re.compile(
        r'\\begin\{(' + '|'.join(map(re.escape, excluded)) + r')\}',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        env_name = m.group(1)
        env_start = m.start()
        if env_start >= start:
            break
        # find matching \end{env_name}
        end_pat = re.compile(r'\\end\{' + re.escape(env_name) + r'\}')
        em = end_pat.search(text, m.end())
        if em and em.end() >= end and env_start < start:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: Custom macro of the form \<word>algorithm{title}{body}
# Handles macros like \ulesalgorithm, \myalgorithm, etc.
# Body allows one level of brace nesting.
PATTERN_MACRO_ALGORITHM = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm\*?)'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# Rule 2: Enumerate environments used as procedural step lists (>= 4 \item entries).
# Structural heuristic only – no content keywords required.
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# PATTERN_ENUMERATE_STEPS = re.compile(
#     r'\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}',
#     re.DOTALL
# )

# Rule 3: \begin{algorithmic}...\end{algorithmic} environments
# (different from algorithm float, catches inner pseudo-code blocks)
PATTERN_ALGORITHMIC_ENV = re.compile(
    r'\\begin\{(?P<env>algorithmic\*?|Algorithmic\*?)\}'
    r'(?:\[[^\]]*\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)

# Rule 4: \begin{procedure}...\end{procedure} or \begin{function}...\end{function}
# Common in algorithm2e / algorithmicx packages
PATTERN_PROCEDURE_ENV = re.compile(
    r'\\begin\{(?P<env>procedure|function|Function|Procedure)\}'
    r'(?:\[[^\]]*\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)

# Rule 5: Section/subsection whose heading contains 'algorithm' followed by
# a body that contains Input: or Output: or Step signals — a minimal prose detection.
PATTERN_ALGORITHM_SECTION = re.compile(
    r'\\(?:sub)*section\*?\s*\{(?P<title>[^}]*?\balgorithm\b[^}]*?)\}'
    r'(?:\\label\{[^}]*\})?\s*'
    r'(?P<body>(?:(?!\\(?:sub)*section\*?\s*\{).)*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is fully contained in another result's raw_latex."""
    if not results:
        return results
    # Sort by length of raw_latex descending so larger matches come first
    sorted_results = sorted(results, key=lambda x: len(x.get('raw_latex', '')), reverse=True)
    kept = []
    kept_texts = []
    for r in sorted_results:
        rt = r.get('raw_latex', '')
        dominated = False
        for kt in kept_texts:
            if rt in kt:
                dominated = True
                break
        if not dominated:
            kept.append(r)
            kept_texts.append(rt)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule 1: Custom \<word>algorithm{title}{body} macros
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
        })

    # ------------------------------------------------------------------
    # Rule 2: Enumerate environments with >= 4 \item entries
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
#         })

    # ------------------------------------------------------------------
    # Rule 3: \begin{algorithmic}...\end{algorithmic}
    # ------------------------------------------------------------------
    for m in PATTERN_ALGORITHMIC_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env = m.group('env')
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_ALGORITHMIC_ENV',
            'structure_type': 'algorithm',
        })

    # ------------------------------------------------------------------
    # Rule 4: \begin{procedure} / \begin{function} environments
    # ------------------------------------------------------------------
    for m in PATTERN_PROCEDURE_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env = m.group('env')
        body = m.group('body')
        clean = _clean_latex(body)
        # Try to extract a caption/name from \caption{...} inside body
        name = None
        cap_m = re.search(r'\\caption\{([^}]*)\}', body)
        if cap_m:
            name = _clean_latex(cap_m.group(1)).strip() or None
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PROCEDURE_ENV',
            'structure_type': 'algorithm',
        })

    # ------------------------------------------------------------------
    # Rule 5: Section headings containing 'algorithm' with Input:/Output:
    # content in the body (prose-level algorithmic descriptions)
    # ------------------------------------------------------------------
    for m in PATTERN_ALGORITHM_SECTION.finditer(text):
        start, end = m.start(), m.end()
        body = m.group('body').strip()
        if not body:
            continue
        # Require structural signal: Input/Output/Step keywords or numbered steps
        has_io = bool(re.search(
            r'\b(?:Input|Output|Step|Steps|Procedure|Require|Ensure)\s*:',
            body, re.IGNORECASE
        ))
        has_enumerate = bool(re.search(r'\\begin\{enumerate\}', body))
        if not (has_io or has_enumerate):
            continue
        if _inside_excluded_env(text, start, end):
            continue
        title = _clean_latex(m.group('title')).strip()
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_ALGORITHM_SECTION',
            'structure_type': 'algorithm',
        })

    return _deduplicate(results)
