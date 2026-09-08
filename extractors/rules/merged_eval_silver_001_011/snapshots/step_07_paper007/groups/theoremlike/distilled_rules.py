import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very small LaTeX -> plain-text cleaner."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common LaTeX commands but keep their arguments
    text = re.sub(r'\\(?:text|mathrm|mathbf|mathit|mathcal|mathbb|emph|textbf|textit|texttt)\{([^}]*)\}', r'\1', text)
    # Remove labels, refs, cites
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note)\}',
    re.DOTALL
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start,end) is inside a proof/example/remark env."""
    # Find all excluded env spans before 'end'
    excl_open = re.compile(
        r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note)\}',
        re.DOTALL
    )
    excl_close = re.compile(
        r'\\end\{(proof|Proof|example|Example|remark|Remark|rem|note)\}',
        re.DOTALL
    )
    depth = 0
    pos = 0
    while pos < start:
        next_open = excl_open.search(text, pos, start)
        next_close = excl_close.search(text, pos, start)
        if next_open and (not next_close or next_open.start() < next_close.start()):
            depth += 1
            pos = next_open.end()
        elif next_close:
            depth = max(0, depth - 1)
            pos = next_close.end()
        else:
            break
    return depth > 0


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(matches: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the longer one."""
    if not matches:
        return matches
    # Sort by start position
    sorted_m = sorted(matches, key=lambda x: x.get('_start', 0))
    result = []
    last_end = -1
    for m in sorted_m:
        s = m.get('_start', 0)
        e = m.get('_end', s + len(m.get('raw_latex', '')))
        if s >= last_end:
            result.append(m)
            last_end = e
        else:
            # Keep the longer one
            if result and (e - s) > (result[-1].get('_end', 0) - result[-1].get('_start', 0)):
                result[-1] = m
                last_end = e
    return result


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule A: \begin{property}...\end{property}  -> proposition
PROP_ENV_RE = re.compile(
    r'\\begin\{(property|Property)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# Rule B: bare \begin{align}...\end{align} or align* containing \max or \min
#         together with s.t. / subject to -> problem
OPT_ALIGN_RE = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)
_OPT_MARKER = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_ST_MARKER = re.compile(r'(?:\\text\s*\{\s*s\.?t\.?\s*\}|\\text\s*\{\s*subject\s+to\s*\})', re.IGNORECASE)

# Rule C: equation/equation* environment containing (P_N) label -> problem
PROB_EQ_RE = re.compile(
    r'\\begin\{(equation\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?\(P[_0-9\w]*\).*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# Rule D: free-text \ba...\ea blocks with problem-signaling preamble -> problem
# \ba ... \ea is a shorthand for a display equation block
# PRUNED — FP on paper001 | also 6 TP — review before uncommenting
# BA_EA_RE = re.compile(
#     r'(?P<preamble>(?:[^\n]|\n(?!\n)){20,800}?)'
#     r'\\ba\s*(?P<body>.*?)\\ea',
#     re.DOTALL
# )
_PROBLEM_SIGNAL = re.compile(
    r'(?:mincut|cut|partition|objective\s+function|criterion|maximize|minimize|'
    r'Ratiocut|Ncut|MinmaxCut|graph\s+cut|problem)',
    re.IGNORECASE
)

# Rule E: implicit theorem in subsection body (before \begin{algorithm})
SUBSECTION_THEOREM_RE = re.compile(
    r'\\subsection\*?\{[^}]*\}\s*'
    r'(?P<body>(?:(?!\\begin\{(?:algorithm|theorem|lemma|proposition|corollary|proof|example|remark|figure|table)\b)[\s\S]){60,800}?)'
    r'(?=\\begin\{algorithm\b)',
    re.DOTALL
)

# Rule F: prose paragraph containing \argmin (optimization problem definition) -> problem
# PRUNED — FP on paper004, paper007
# ARGMIN_PROSE_RE = re.compile(
#     r'(?:(?<=\n\n)|(?<=\A)|\n\n)'
#     r'(?P<body>[^\n]*?\\argmin[\s\S]*?)'
#     r'(?=\n\n|\Z)',
#     re.DOTALL
# )

# Rule G: "Our goal is to estimate" + equation block -> problem
GOAL_ESTIMATE_RE = re.compile(
    r'(?P<preamble>Our\s+goal\s+is\s+to\s+estimate\b[^\\]*?)'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\})',
    re.DOTALL
)

# Rule H: "The goal of this paper is to" -> problem
PAPER_GOAL_RE = re.compile(
    r'(?P<body>The\s+goal\s+of\s+this\s+paper\s+is\s+to\b.*?)'
    r'(?=\n\n|\\paragraph|\\section|\\subsection)',
    re.DOTALL
)

# Rule I: "Our goal is to predict" + equation* block -> problem
GOAL_PREDICT_RE = re.compile(
    r'(?P<preamble>Our\s+goal\s+is\s+to\s+predict\b[^\\]*?)'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\})',
    re.DOTALL
)

# Rule J: prose paragraph + equation describing a minimax / lower-bound theorem
# (Ha'jek-Le Cam style: "guarantees for any estimator ... \begin{equation*}...\end{equation*}")
MINIMAX_THEOREM_RE = re.compile(
    r'(?P<preamble>(?:guarantees|Hajek|minimax\s+theorem)[^\\]{0,400}?)'
    r'(?P<body>\\begin\{equation\*?\}.*?\\end\{equation\*?\})',
    re.DOTALL
)

# Rule K: \begin{align}...\end{align} containing (P_N) label -> problem
PROB_ALIGN_RE = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?\(P[_0-9\w]*\).*?)'
    r'\\end\{\1\}',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule A: property env -> proposition ---
    for m in PROP_ENV_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PROP_ENV_RE',
            'structure_type': 'proposition',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule B: optimization align -> problem ---
    for m in OPT_ALIGN_RE.finditer(text):
        body = m.group('body')
        if not (_OPT_MARKER.search(body) and _ST_MARKER.search(body)):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPT_ALIGN_RE',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule C: equation with (P_N) -> problem ---
    for m in PROB_EQ_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PROB_EQ_RE',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule K: align with (P_N) -> problem ---
    for m in PROB_ALIGN_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PROB_ALIGN_RE',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule D: \ba...\ea with problem signal -> problem ---
#     for m in BA_EA_RE.finditer(text):
#         preamble = m.group('preamble')
#         body = m.group('body')
#         combined = preamble.strip() + ' ' + body.strip()
#         if not _PROBLEM_SIGNAL.search(preamble):
#             continue
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         results.append({
#             'raw_latex': combined,
#             'clean_text': _clean_latex(combined),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'BA_EA_RE',
#             'structure_type': 'problem',
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # --- Rule E: subsection body before \begin{algorithm} -> theorem ---
    for m in SUBSECTION_THEOREM_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 60:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_THEOREM_RE',
            'structure_type': 'theorem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule F: prose with \argmin -> problem ---
#     for m in ARGMIN_PROSE_RE.finditer(text):
#         body = m.group('body').strip()
#         if len(body) < 40:
#             continue
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'ARGMIN_PROSE_RE',
#             'structure_type': 'problem',
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # --- Rule G: "Our goal is to estimate" + equation -> problem ---
    for m in GOAL_ESTIMATE_RE.finditer(text):
        preamble = m.group('preamble')
        body = m.group('body')
        combined = preamble.strip() + ' ' + body.strip()
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        results.append({
            'raw_latex': combined,
            'clean_text': _clean_latex(combined),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'GOAL_ESTIMATE_RE',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule H: "The goal of this paper is to" -> problem ---
    for m in PAPER_GOAL_RE.finditer(text):
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PAPER_GOAL_RE',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule I: "Our goal is to predict" + equation* -> problem ---
    for m in GOAL_PREDICT_RE.finditer(text):
        preamble = m.group('preamble')
        body = m.group('body')
        combined = preamble.strip() + ' ' + body.strip()
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        results.append({
            'raw_latex': combined,
            'clean_text': _clean_latex(combined),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'GOAL_PREDICT_RE',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule J: minimax theorem prose + equation* -> theorem ---
    for m in MINIMAX_THEOREM_RE.finditer(text):
        preamble = m.group('preamble')
        body = m.group('body')
        combined = preamble.strip() + ' ' + body.strip()
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        results.append({
            'raw_latex': combined,
            'clean_text': _clean_latex(combined),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'MINIMAX_THEOREM_RE',
            'structure_type': 'theorem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # Deduplicate
    results = _deduplicate(results)

    # Remove internal position keys before returning
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
