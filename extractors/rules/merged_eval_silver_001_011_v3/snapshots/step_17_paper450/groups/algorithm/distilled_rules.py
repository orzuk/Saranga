import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# 1. Custom macro ending in 'algorithm' with two brace-delimited arguments:
#    \<something>algorithm{title}{body}
#    Body allows one level of nested braces.
ULESALGORITHM_RE = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# 2. \paragraph{... algorithm ...} followed by \begin{enumerate}...\end{enumerate}
PARAGRAPH_ALG_RE = re.compile(
    r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\}'
    r'\s*(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# 3. Prose ending with 'following ... steps/procedure/strategy:' immediately
#    before \begin{enumerate}...\end{enumerate}
PROSE_FOLLOWING_ENUM_RE = re.compile(
    r'(?:algorithm|procedure|strategy|method)\b[^\n\r]{0,400}?'
    r'following[^\n\r]{0,120}?(?:steps?|stages?|strategy|procedure)\s*:\s*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# 4. Prose ending with 'as follows' / 'defined as follows' / 'described below'
#    immediately before \begin{enumerate}...\end{enumerate}
AS_FOLLOWS_ENUM_RE = re.compile(
    r'(?P<intro>[^\n\r]{0,500}?'
    r'(?:as follows|following steps?|following procedure|defined below|described below)'
    r'[^\n\r]{0,100}?)'
    r'\s*(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# 5. 'process/procedure/method/algorithm consists of ... steps:' before enumerate
CONSISTS_OF_ENUM_RE = re.compile(
    r'(?:process|procedure|method|algorithm|estimation)\s+consists\s+of'
    r'[^\n\r]{0,200}?'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# 6. 'following N steps:' immediately before \begin{equation}
FOLLOWING_STEPS_EQ_RE = re.compile(
    r'following\s+\w+\s+steps\s*:\s*'
    r'(?P<body>\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})',
    re.DOTALL | re.IGNORECASE
)

# 7. Large enumerate blocks (>= 4 \item entries) as candidate algorithms
#    (structural proxy for multi-step procedures)
# PRUNED — FP on paper001, paper008, paper009 +4 more | also 1 TP — review before uncommenting
# LARGE_ENUMERATE_RE = re.compile(
#     r'\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}',
#     re.DOTALL
# )

# 8. Prose naming a procedure: "We call this [procedure|algorithm|...]" with
#    a display math block \[ ... \]
# PRUNED — SLOW backtracking (TIMEOUT > 10.00s/paper cap)
# PROSE_NAMING_RE = re.compile(
#     r'(?P<body>'
#     r'(?:[^\n]|\n(?!\s*\n)){0,800}?'
#     r'\\\[.*?\\\]'
#     r'(?:[^\n]|\n(?!\s*\n)){0,400}?'
#     r'[Ww]e\s+(?:call|refer\s+to)\s+this\s+'
#     r'(?:procedure|algorithm|method|approach|scheme|strategy)'
#     r'[^.!?]*[.!?]'
#     r')',
#     re.DOTALL
# )

# Environments to exclude (we don't want to extract from inside these)
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note|exercise|Exercise)\}',
    re.DOTALL
)

# Real algorithm environments (already handled by base parser — used for dedup)
_BASE_ALG_ENV_RE = re.compile(
    r'\\begin\{algorithm[*]?\}.*?\\end\{algorithm[*]?\}',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX markup to produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(align|equation|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}',
                  ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*?\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove display math \[ ... \]
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    # Remove common LaTeX commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|boldsymbol|bf|it)\{([^}]*)\}',
                  r'\1', text)
    # Remove \label, \ref, \cite, \eqref
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    # Find all excluded env openings before 'start'
    for m in _EXCLUDED_ENVS.finditer(text):
        env_name = m.group(1)
        env_open = m.start()
        if env_open > start:
            break
        # Find corresponding \end{env_name}
        close_pattern = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\}',
            re.DOTALL
        )
        cm = close_pattern.search(text, env_open)
        if cm and cm.end() >= end:
            return True
    return False


def _overlaps(span: tuple, seen: list) -> bool:
    """Return True if span overlaps any span in seen list."""
    s, e = span
    for (ss, se) in seen:
        if s < se and e > ss:
            return True
    return False


def _get_base_alg_spans(text: str) -> list:
    """Return list of (start, end) spans of base algorithm environments."""
    spans = []
    for m in _BASE_ALG_ENV_RE.finditer(text):
        spans.append((m.start(), m.end()))
    return spans


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []
    seen_spans: list = []  # list of (start, end)

    base_spans = _get_base_alg_spans(text)

    def add_result(raw_latex: str, name, env_name: str, rule_name: str,
                   start: int, end: int) -> None:
        span = (start, end)
        # Skip if overlaps already seen span
        if _overlaps(span, seen_spans):
            return
        # Skip if overlaps a base algorithm env
        if _overlaps(span, base_spans):
            return
        # Skip if inside an excluded environment
        if _inside_excluded_env(text, start, end):
            return
        seen_spans.append(span)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': _clean_latex(raw_latex),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'algorithm',
        })

    # ------------------------------------------------------------------
    # Rule 1: \<something>algorithm{title}{body} macro
    # ------------------------------------------------------------------
    for m in ULESALGORITHM_RE.finditer(text):
        title = m.group('title').strip()
        body = m.group('body')
        add_result(
            raw_latex=body,
            name=title if title else None,
            env_name='distilled',
            rule_name='ULESALGORITHM_RE',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # Rule 2: \paragraph{... algorithm ...} + enumerate
    # ------------------------------------------------------------------
    for m in PARAGRAPH_ALG_RE.finditer(text):
        name = m.group('name').strip()
        body = m.group('body')
        add_result(
            raw_latex=body,
            name=name if name else None,
            env_name='distilled',
            rule_name='PARAGRAPH_ALG_RE',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # Rule 3: prose 'following ... steps:' before enumerate
    # ------------------------------------------------------------------
    for m in PROSE_FOLLOWING_ENUM_RE.finditer(text):
        body = m.group('body')
        add_result(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='PROSE_FOLLOWING_ENUM_RE',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # Rule 4: 'as follows' / 'defined below' before enumerate
    # ------------------------------------------------------------------
    for m in AS_FOLLOWS_ENUM_RE.finditer(text):
        body = m.group('body')
        add_result(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='AS_FOLLOWS_ENUM_RE',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # Rule 5: 'consists of ... steps:' before enumerate
    # ------------------------------------------------------------------
    for m in CONSISTS_OF_ENUM_RE.finditer(text):
        body = m.group('body')
        add_result(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='CONSISTS_OF_ENUM_RE',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # Rule 6: 'following N steps:' before equation environment
    # ------------------------------------------------------------------
    for m in FOLLOWING_STEPS_EQ_RE.finditer(text):
        body = m.group('body')
        add_result(
            raw_latex=body,
            name=None,
            env_name='distilled',
            rule_name='FOLLOWING_STEPS_EQ_RE',
            start=m.start(),
            end=m.end(),
        )

    # ------------------------------------------------------------------
    # Rule 7: Large enumerate blocks (>= 4 \item entries)
#     # ------------------------------------------------------------------
#     for m in LARGE_ENUMERATE_RE.finditer(text):
#         body = m.group('body')
#         item_count = len(re.findall(r'\\item', body))
#         if item_count >= 4:
#             add_result(
#                 raw_latex=body,
#                 name=None,
#                 env_name='distilled',
#                 rule_name='LARGE_ENUMERATE_RE',
#                 start=m.start(),
#                 end=m.end(),
#             )

    # ------------------------------------------------------------------
    # Rule 8: Prose naming a procedure with display math
#     # ------------------------------------------------------------------
#     for m in PROSE_NAMING_RE.finditer(text):
#         body = m.group('body')
#         # Only add if it contains a real display math block
#         if re.search(r'\\\[', body):
#             add_result(
#                 raw_latex=body,
#                 name=None,
#                 env_name='distilled',
#                 rule_name='PROSE_NAMING_RE',
#                 start=m.start(),
#                 end=m.end(),
#             )

    return results
