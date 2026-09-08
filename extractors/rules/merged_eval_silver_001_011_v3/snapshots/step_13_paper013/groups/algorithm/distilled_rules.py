import re
from typing import List, Dict, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX markup to produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \begin{...} / \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math \[ ... \]
    text = re.sub(r'\\\[.*?\\\]', ' ', text, flags=re.DOTALL)
    # Remove inline math $ ... $
    text = re.sub(r'\$[^$]*\$', ' ', text)
    # Remove \label, \ref, \cite, \eqref etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*|bibitem)\{[^}]*\}', '', text)
    # Remove common text-formatting macros but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|boldsymbol|bf|it|rm|sc|sf|tt)\{([^}]*)\}', r'\1', text)
    # Remove remaining macros with one brace argument
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining macros without arguments
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments whose content should be excluded from algorithm extraction
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note|figure|table|figure\*|table\*)\}',
    re.IGNORECASE
)

_EXCLUDED_ENV_FULL = re.compile(
    r'\\begin\{(?:proof|Proof|example|Example|remark|Remark|rem|note|figure|table|figure\*|table\*)\}'
    r'.*?'
    r'\\end\{(?:proof|Proof|example|Example|remark|Remark|rem|note|figure|table|figure\*|table\*)\}',
    re.DOTALL | re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_FULL.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _already_in_algorithm_env(text: str, start: int, end: int) -> bool:
    """Return True if the span is already inside a standard algorithm environment."""
    algo_env = re.compile(
        r'\\begin\{algorithm[*]?\}.*?\\end\{algorithm[*]?\}',
        re.DOTALL | re.IGNORECASE
    )
    for m in algo_env.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns  (rule_name = variable name)
# ---------------------------------------------------------------------------

# Rule A: Custom macro of the form  \<word>algorithm{title}{body}
# (covers \ulesalgorithm, \myalgorithm, etc.)
# Title: no nested braces. Body: one level of nesting.
CUSTOM_MACRO_ALG_RE = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)\s*'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# Rule B: \paragraph{... algorithm ...} followed by \begin{enumerate}...\end{enumerate}
PARAGRAPH_ALG_ENUM_RE = re.compile(
    r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\}'
    r'[ \t]*\n?'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# Rule C: \paragraph{... algorithm ...} followed by \begin{itemize}...\end{itemize}
PARAGRAPH_ALG_ITEM_RE = re.compile(
    r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\}'
    r'[ \t]*\n?'
    r'(?P<body>\\begin\{itemize\}.*?\\end\{itemize\})',
    re.DOTALL | re.IGNORECASE
)

# Rule D: Prose introducing 'the following ... steps/procedure' ending with ':'
# immediately before \begin{enumerate}...\end{enumerate}
# The lead must contain 'algorithm' OR the trailing clause contains 'steps'
PROSE_STEPS_ENUM_RE = re.compile(
    r'(?P<lead>'
    r'(?:\balgorithm\b[^\n]{0,500}?|[^\n]{0,200}?\balgorithm\b[^\n]{0,200}?)?'
    r'\b(?:following|below)\b[^\n]{0,150}?'
    r'\b(?:steps?|procedure|strategy|approach)\b'
    r'[^\n]{0,60}?:\s*'
    r')'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# Rule E: "as follows" / "defined as follows" / "described as follows"
# immediately before \begin{enumerate}...\end{enumerate}
# with 'algorithm' somewhere in the preceding ~600 chars
# PRUNED — FP on paper011
# AS_FOLLOWS_ENUM_RE = re.compile(
#     r'(?P<lead>[^\n]{0,600}?\balgorithm\b[^\n]{0,300}?'
#     r'\b(?:as follows|defined below|described below|the following)\b'
#     r'[^\n]{0,80}?:\s*'
#     r')'
#     r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
#     re.DOTALL | re.IGNORECASE
# )

# Rule F: "the following two/three/... steps" before \begin{equation}...\end{equation}
# (e.g., SGD described with an equation block instead of enumerate)
STEPS_EQUATION_RE = re.compile(
    r'(?P<lead>[^\n]{0,400}?\balgorithm\b[^\n]{0,300}?'
    r'\bfollowing\s+\w+\s+steps\b'
    r'[^\n]{0,80}?:\s*'
    r')'
    r'(?P<body>\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})',
    re.DOTALL | re.IGNORECASE
)

# Rule G: enumerate environment used as a multi-step procedure
# Structural heuristic: >= 4 \item tokens, and the surrounding context (500 chars before)
# contains the word 'algorithm', 'procedure', 'method', or 'steps'
BARE_ENUM_ALG_RE = re.compile(
    r'(?P<body>\\begin\{enumerate\}(?:(?!\\begin\{enumerate\}).)*?\\end\{enumerate\})',
    re.DOTALL
)

# Rule H: Prose paragraph where 'we call this [procedure|algorithm|...]' names a procedure
# and a display math \[ ... \] block is present within the paragraph
# PRUNED — SLOW backtracking (16.99s > 10.00s/paper cap)
# PROSE_NAMED_PROC_RE = re.compile(
#     r'(?P<body>'
#     r'(?:[^\n]|\n(?!\s*\n)){0,700}?'
#     r'\\\[.*?\\\]'
#     r'(?:[^\n]|\n(?!\s*\n)){0,400}?'
#     r'\bwe\s+(?:call|refer\s+to)\s+this\s+'
#     r'(?:procedure|algorithm|method|approach|scheme|strategy)\b'
#     r'[^.!?]*[.!?]'
#     r')',
#     re.DOTALL | re.IGNORECASE
# )


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex span overlaps a previously accepted result."""
    accepted: List[dict] = []
    accepted_spans: List[tuple] = []
    # Sort by length descending so larger (more complete) matches win
    results_sorted = sorted(results, key=lambda r: len(r.get('raw_latex', '')), reverse=True)
    for r in results_sorted:
        pos = r.get('_source_pos', 0)
        end = pos + len(r.get('raw_latex', ''))
        overlaps = False
        for (a_start, a_end) in accepted_spans:
            # Check for any overlap
            if pos < a_end and end > a_start:
                overlaps = True
                break
        if not overlaps:
            accepted.append(r)
            accepted_spans.append((pos, end))
    return accepted


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    """
    Extract algorithm-like structures from LaTeX source that are NOT already
    caught by the base _extract_algorithms method (which handles standard
    \\begin{algorithm}...\\end{algorithm} environments).

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: Custom macros  \<word>algorithm{title}{body}
    # ------------------------------------------------------------------
    for m in CUSTOM_MACRO_ALG_RE.finditer(text):
        start = m.start()
        body = m.group('body')
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _already_in_algorithm_env(text, start, end):
            continue
        title = m.group('title').strip()
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'CUSTOM_MACRO_ALG_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule B: \paragraph{... algorithm ...} + enumerate
    # ------------------------------------------------------------------
    for m in PARAGRAPH_ALG_ENUM_RE.finditer(text):
        start = m.start()
        body = m.group('body')
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _already_in_algorithm_env(text, start, end):
            continue
        name = _clean_latex(m.group('name').strip())
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_ALG_ENUM_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule C: \paragraph{... algorithm ...} + itemize
    # ------------------------------------------------------------------
    for m in PARAGRAPH_ALG_ITEM_RE.finditer(text):
        start = m.start()
        body = m.group('body')
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _already_in_algorithm_env(text, start, end):
            continue
        name = _clean_latex(m.group('name').strip())
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_ALG_ITEM_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule D: Prose "following <N> steps/procedure:" + enumerate
    # ------------------------------------------------------------------
    for m in PROSE_STEPS_ENUM_RE.finditer(text):
        start = m.start()
        body = m.group('body')
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _already_in_algorithm_env(text, start, end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_STEPS_ENUM_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule E: "algorithm ... as follows:" + enumerate
#     # ------------------------------------------------------------------
#     for m in AS_FOLLOWS_ENUM_RE.finditer(text):
#         start = m.start()
#         body = m.group('body')
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         if _already_in_algorithm_env(text, start, end):
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'AS_FOLLOWS_ENUM_RE',
#             'structure_type': 'algorithm',
#             '_source_pos': start,
#         })

    # ------------------------------------------------------------------
    # Rule F: "following <N> steps:" + equation block
    # ------------------------------------------------------------------
    for m in STEPS_EQUATION_RE.finditer(text):
        start = m.start()
        body = m.group('body')
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _already_in_algorithm_env(text, start, end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'STEPS_EQUATION_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule G: Bare enumerate with >= 4 \item tokens,
    # preceded (within 600 chars) by 'algorithm'/'procedure'/'method'
    # ------------------------------------------------------------------
    _algo_context_kw = re.compile(
        r'\b(?:algorithm|procedure|method|approach)\b',
        re.IGNORECASE
    )
    for m in BARE_ENUM_ALG_RE.finditer(text):
        start = m.start()
        body = m.group('body')
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _already_in_algorithm_env(text, start, end):
            continue
        # Structural check: enough \item tokens
        item_count = len(re.findall(r'\\item', body))
        if item_count < 4:
            continue
        # Context check: 'algorithm' or related word in preceding 600 chars
        preceding = text[max(0, start - 600):start]
        if not _algo_context_kw.search(preceding):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BARE_ENUM_ALG_RE',
            'structure_type': 'algorithm',
            '_source_pos': start,
        })

    # ------------------------------------------------------------------
    # Rule H: Prose paragraph with display math + "we call this [procedure|algorithm]"
#     # ------------------------------------------------------------------
#     for m in PROSE_NAMED_PROC_RE.finditer(text):
#         start = m.start()
#         body = m.group('body')
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         if _already_in_algorithm_env(text, start, end):
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'PROSE_NAMED_PROC_RE',
#             'structure_type': 'algorithm',
#             '_source_pos': start,
#         })

    # ------------------------------------------------------------------
    # Deduplicate overlapping matches and clean up internal key
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    for r in results:
        r.pop('_source_pos', None)

    return results
