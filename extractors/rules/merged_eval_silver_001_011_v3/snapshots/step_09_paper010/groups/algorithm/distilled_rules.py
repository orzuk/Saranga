import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common display/inline math wrappers (keep content)
    text = re.sub(r'\$\$|\$', ' ', text)
    text = re.sub(r'\\[\(\)\[\]]', ' ', text)
    # Remove \cmd{...} wrappers – keep inner text
    for _ in range(6):
        text = re.sub(r'\\[a-zA-Z]+\*?\{([^{}]*)\}', r'\1', text)
    # Remove remaining \ commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose content we want to exclude from algorithm extraction
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note)\}',
    re.DOTALL
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) sits inside an excluded environment."""
    prefix = text[:start]
    # Count open excluded envs before this position
    opens = re.findall(
        r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note)\}',
        prefix
    )
    closes_all = []
    for env in set(opens):
        closes_all.extend(re.findall(re.escape(r'\end{' + env + '}'), prefix))
    return len(opens) > len(closes_all)


# ---------------------------------------------------------------------------
# Deduplicate overlapping spans
# ---------------------------------------------------------------------------

def _deduplicate(matches: List[dict]) -> List[dict]:
    """Remove duplicates / overlapping matches, keeping the longer one."""
    if not matches:
        return matches
    # Sort by start position then by length desc
    matches = sorted(matches, key=lambda m: (m['_start'], -(m['_end'] - m['_start'])))
    result = []
    last_end = -1
    for m in matches:
        if m['_start'] >= last_end:
            result.append(m)
            last_end = m['_end']
    return result


# ---------------------------------------------------------------------------
# Rule 1 – Custom macro ending in "algorithm": \<something>algorithm{title}{body}
#
# Catches patterns like \ulesalgorithm{title}{body} and similar user-defined
# macros.  We allow one level of brace nesting in the body argument.
# ---------------------------------------------------------------------------

_MACRO_ALG_RE = re.compile(
    r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)'
    r'\{(?P<title>[^{}]*)\}'
    r'\{(?P<body>(?:[^{}]|\{[^{}]*\})*)\}',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Rule 2 – \paragraph{... algorithm ...} followed by \begin{enumerate}...\end{enumerate}
#
# Catches algorithm descriptions introduced by a \paragraph heading that
# contains the word "algorithm".
# ---------------------------------------------------------------------------

_PARA_ALG_ENUM_RE = re.compile(
    r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\}'
    r'[ \t]*\n?[ \t]*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 3 – Prose "following N steps:" / "as follows:" anchor before enumerate
#
# Catches algorithms described as "performs the following two steps:" or
# "the following procedure:" followed immediately by \begin{enumerate}.
# Requires one of the algorithmic lead-in words (algorithm/procedure/strategy/
# method/step) somewhere in the preceding sentence to reduce false positives.
# ---------------------------------------------------------------------------

_PROSE_ALG_ENUM_RE = re.compile(
    r'(?:algorithm|procedure|strategy|method)\b'
    r'[^\n]{0,500}?'
    r'(?:following[^\n]{0,150}?(?:steps|procedure|strategy)|as\s+follows)\s*:\s*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 4 – Standalone enumerate with >= 4 items that contains algorithmic
#           keywords (Input/Output/repeat/compute/select/sample/initialize)
#           AND is NOT already covered by Rule 2 or 3.
#
# We require BOTH a structural signal (>= 4 \item) AND at least two
# algorithmic-flavour keywords to reduce false positives.
# ---------------------------------------------------------------------------

_ENUM_BLOCK_RE = re.compile(
    r'\\begin\{enumerate\}(?P<body>.*?)\\end\{enumerate\}',
    re.DOTALL
)

_ALG_KEYWORD_RE = re.compile(
    r'\b(input|output|repeat|initialize|initialise|compute|select|sample|'
    r'iterate|iteration|convergence|terminate|return|update|step)\b',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 5 – "following N steps:" anchor before an equation block
#           (catches SGD-style two-step iterative update displayed as equation)
# ---------------------------------------------------------------------------

_STEPS_EQ_RE = re.compile(
    r'following\s+\w+\s+steps?\s*:\s*'
    r'(?P<body>\\begin\{equation[*]?\}.*?\\end\{equation[*]?\})',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []

    # ---- Rule 1: custom macro \<word>algorithm{title}{body} ---------------
    for m in _MACRO_ALG_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': '_MACRO_ALG_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # ---- Rule 2: \paragraph{... algorithm ...} + enumerate ----------------
    for m in _PARA_ALG_ENUM_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        name = m.group('name').strip()
        body = m.group('body')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': '_PARA_ALG_ENUM_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # ---- Rule 3: prose algorithmic lead-in + enumerate --------------------
    for m in _PROSE_ALG_ENUM_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_PROSE_ALG_ENUM_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # ---- Rule 4: standalone enumerate with >= 4 items + algo keywords -----
    for m in _ENUM_BLOCK_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        item_count = len(re.findall(r'\\item', body))
        kw_count = len(_ALG_KEYWORD_RE.findall(body))
        if item_count >= 4 and kw_count >= 2:
            results.append({
                'raw_latex': body,
                'clean_text': _clean_latex(body),
                'name': None,
                'env_name': 'distilled',
                'rule_name': '_ENUM_BLOCK_RE',
                'structure_type': 'algorithm',
                '_start': start,
                '_end': end,
            })

    # ---- Rule 5: "following N steps:" + equation block --------------------
    for m in _STEPS_EQ_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_STEPS_EQ_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # ---- Deduplicate and clean up internal keys ---------------------------
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
