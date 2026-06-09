import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text cleaner."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands keeping their argument
    text = re.sub(r'\\(?:text|mathrm|mathbf|mathit|emph|textbf|textit)\{([^}]*)\}', r'\1', text)
    # Remove labels, refs, cites
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove \\ line breaks
    text = re.sub(r'\\\\', ' ', text)
    # Remove leftover commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside a proof/example/remark env."""
    excluded = re.compile(
        r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note)\*?\}',
        re.DOTALL
    )
    end_pat = re.compile(r'\\end\{(proof|Proof|example|Example|remark|Remark|rem|note)\*?\}', re.DOTALL)
    for m in excluded.finditer(text):
        env_start = m.start()
        if env_start > start:
            break
        # find corresponding end
        end_m = end_pat.search(text, m.end())
        if end_m and end_m.end() > end and env_start < start:
            return True
    return False


def _dedup(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the one with longer raw_latex."""
    if not results:
        return results
    results = sorted(results, key=lambda d: (d.get('_start', 0), -len(d.get('raw_latex', ''))))
    out = []
    last_end = -1
    for d in results:
        s = d.get('_start', 0)
        e = d.get('_end', s + len(d.get('raw_latex', '')))
        if s >= last_end:
            out.append(d)
            last_end = e
    return out


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# 1. \begin{property}[opt]...\end{property}  -> proposition
PROP_PROPERTY_ENV = re.compile(
    r'\\begin\{([Pp]roperty)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# 2. \begin{align}...\end{align} containing \max or \min + s.t./subject to -> problem
PROP_OPT_ALIGN = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)
_OPT_SIGNAL = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_ST_SIGNAL = re.compile(r'\\text\s*\{\s*s\.?\s*t\.?|subject\s+to', re.IGNORECASE)

# 3. \ba...\ea blocks preceded by a qualifying preamble sentence -> problem
#    \ba and \ea are short-hand display-math delimiters used in paper001
# PRUNED — FP on paper001 | also 6 TP — review before uncommenting
# PROP_BA_EA = re.compile(
#     r'(?P<preamble>(?:[^\n]|\n(?!\n)){30,800}?)'
#     r'\\ba\s*(?P<body>.*?)\\ea',
#     re.DOTALL
# )
_BA_PROBLEM_SIGNAL = re.compile(
    r'(?:mincut|cut|partition|objective\s+function|criterion|minimize|maximize|Ratiocut|Ncut|MinmaxCut)',
    re.IGNORECASE
)

# 4. equation/* environments containing (P_N) problem tag -> problem
PROP_PROBLEM_EQ = re.compile(
    r'\\begin\{(equation\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?\(P[_0-9a-zA-Z]*\).*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# 5. Prose paragraph + equation containing \argmin -> problem
#    Look for paragraph blocks (delimited by double newline or section/subsection)
#    that contain \argmin within or just before an equation env.
PROP_ARGMIN_PROSE = re.compile(
    r'(?:(?<=\n\n)|(?:^|\n\n))'
    r'(?P<preamble>[^\n]*(?:Define|Introduce|The\s+\w+\s+estimator|estimator\s+of)[^\n]{0,300})'
    r'(?P<eqs>'
        r'(?:(?!\\begin\{(?:theorem|lemma|proposition|corollary|claim|proof|example|remark)\b)[^\n]|\n(?!\n))*'
        r'\\begin\{equation(?:\*|split|\*)?.*?'
        r'\\end\{equation[^}]*\}'
        r'(?:(?!\\begin\{(?:theorem|lemma|proposition|corollary|claim|proof|example|remark)\b)[^\n]|\n(?!\n))*'
    r')'
    r'(?P<trailing>[^\n]{0,300})',
    re.DOTALL
)
_ARGMIN_SIGNAL = re.compile(r'\\argmin\b')

# 6. Prose paragraphs: "Our goal is to estimate/predict..." + optional equation -> problem
PROP_GOAL_ESTIMATE = re.compile(
    r'(?:(?:^|\n\n)|\n(?=Our\s+goal))'
    r'(?P<intro>Our\s+goal\s+is\s+to\s+(?:estimate|predict)[^.]{0,500}\.)'
    r'(?P<body>(?:(?!\\begin\{(?:theorem|lemma|proposition|corollary|proof|example|remark)\b)[^\n]|\n(?!\n)){0,800}'
        r'(?:(?:\\begin\{equation\*?\}.*?\\end\{equation\*?\})'
        r'|(?:\\begin\{align\*?\}.*?\\end\{align\*?\}))?'
        r'(?:(?!\\begin\{(?:theorem|lemma|proposition|corollary|proof|example|remark)\b)[^\n]|\n(?!\n)){0,300}'
    r')',
    re.DOTALL
)

# 7. "The goal of this paper is to..." paragraph -> problem
PROP_PAPER_GOAL = re.compile(
    r'(?:(?:^|\n\n)|\n(?=The\s+goal\s+of\s+this\s+paper))'
    r'(?P<body>The\s+goal\s+of\s+this\s+paper\s+is\s+to\b'
    r'(?:(?!\\begin\{(?:theorem|lemma|proposition|corollary|proof|example|remark)\b)[^\n]|\n(?!\n)){0,800}'
    r')',
    re.DOTALL
)

# 8. Prose + align* around a known result (Marchenko-Pastur type eigenvalue result) -> theorem
#    Matches text containing "proved that" or "guarantees" + align*/equation* block
# PRUNED — FP on paper002, paper006 | also 1 TP — review before uncommenting
# PROP_PROSE_THEOREM = re.compile(
#     r'(?P<preamble>'
#         r'(?:[A-Z][^.!?]{20,400}?)'
#         r'(?:proved that|guarantees\s+for|we\s+have\s+the\s+following|it\s+follows\s+that)'
#         r'[^.!?]{0,200}'
#     r')'
#     r'(?P<eq>'
#         r'\\begin\{(?:align|equation)\*?\}'
#         r'.*?'
#         r'\\end\{(?:align|equation)\*?\}'
#     r')',
#     re.DOTALL
# )

# 9. Prose theorem: sentence containing known minimax / lower bound result -> theorem
PROP_MINIMAX_PROSE = re.compile(
    r'(?P<preamble>[^.]{0,600}?'
        r'(?:H\\\'ajek|Hajek|minimax\s+theorem|minimax\s+lower\s+bound|Cram[eé]r.Rao)[^.]{0,400}?'
    r')'
    r'(?P<eq>\\begin\{equation\*?\}.*?\\end\{equation\*?\})',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \begin{property}...\end{property}  -> proposition
    # ------------------------------------------------------------------
    for m in PROP_PROPERTY_ENV.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        env = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PROP_PROPERTY_ENV',
            'structure_type': 'proposition',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule B: align/align* with \max/\min + s.t.  -> problem
    # ------------------------------------------------------------------
    for m in PROP_OPT_ALIGN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if not (_OPT_SIGNAL.search(body) and _ST_SIGNAL.search(body)):
            continue
        raw = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROP_OPT_ALIGN',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule C: \ba...\ea with problem-signal preamble  -> problem
#     # ------------------------------------------------------------------
#     for m in PROP_BA_EA.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         preamble = m.group('preamble')
#         body = m.group('body')
#         combined = preamble.strip() + ' ' + body.strip()
#         if not _BA_PROBLEM_SIGNAL.search(preamble + body):
#             continue
#         clean = _clean_latex(combined)
#         results.append({
#             'raw_latex': combined,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'PROP_BA_EA',
#             'structure_type': 'problem',
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # ------------------------------------------------------------------
    # Rule D: equation/* containing (P_N) tag  -> problem
    # ------------------------------------------------------------------
    for m in PROP_PROBLEM_EQ.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        raw = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROP_PROBLEM_EQ',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule E: prose paragraph with \argmin + equation blocks  -> problem
    # ------------------------------------------------------------------
    for m in PROP_ARGMIN_PROSE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        full = (m.group('preamble') or '') + (m.group('eqs') or '') + (m.group('trailing') or '')
        if not _ARGMIN_SIGNAL.search(full):
            continue
        clean = _clean_latex(full)
        results.append({
            'raw_latex': full.strip(),
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROP_ARGMIN_PROSE',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule F: "Our goal is to estimate/predict" prose + optional equation -> problem
    # ------------------------------------------------------------------
    for m in PROP_GOAL_ESTIMATE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        intro = m.group('intro') or ''
        body = m.group('body') or ''
        full = intro + body
        clean = _clean_latex(full)
        results.append({
            'raw_latex': full.strip(),
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROP_GOAL_ESTIMATE',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule G: "The goal of this paper is to..." paragraph -> problem
    # ------------------------------------------------------------------
    for m in PROP_PAPER_GOAL.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        clean = _clean_latex(body)
        results.append({
            'raw_latex': body.strip(),
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROP_PAPER_GOAL',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Rule H: prose "proved that / guarantees" + align*/equation* -> theorem
#     # ------------------------------------------------------------------
#     for m in PROP_PROSE_THEOREM.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         preamble = m.group('preamble') or ''
#         eq = m.group('eq') or ''
#         full = preamble + eq
#         clean = _clean_latex(full)
#         results.append({
#             'raw_latex': full.strip(),
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'PROP_PROSE_THEOREM',
#             'structure_type': 'theorem',
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # ------------------------------------------------------------------
    # Rule I: minimax / Hajek-Le Cam prose + equation* -> theorem
    # ------------------------------------------------------------------
    for m in PROP_MINIMAX_PROSE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        preamble = m.group('preamble') or ''
        eq = m.group('eq') or ''
        full = preamble + eq
        clean = _clean_latex(full)
        results.append({
            'raw_latex': full.strip(),
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROP_MINIMAX_PROSE',
            'structure_type': 'theorem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Deduplicate and clean up internal keys
    # ------------------------------------------------------------------
    results = _dedup(results)
    for d in results:
        d.pop('_start', None)
        d.pop('_end', None)

    return results
