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
    # Remove label/ref commands
    text = re.sub(r'\\(?:label|ref|eqref|cite\w*|footnote)\{[^}]*\}', '', text)
    # Remove \begin/\end
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove leftover braces and backslash-commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Environments that should exclude content from extraction
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|Proof|Example|Remark)\}',
    re.DOTALL
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside a proof/example/remark env."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        env_name = m.group(1)
        env_end_pat = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\}',
            re.DOTALL
        )
        em = env_end_pat.search(text, m.end())
        if em and m.start() <= start and em.end() >= end:
            return True
    return False


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove overlapping results, keeping the one with more raw_latex content."""
    if not results:
        return results
    # sort by start position
    results.sort(key=lambda d: d.get('_start', 0))
    merged = []
    for r in results:
        if not merged:
            merged.append(r)
            continue
        prev = merged[-1]
        prev_end = prev.get('_end', 0)
        cur_start = r.get('_start', 0)
        if cur_start < prev_end:
            # overlap — keep the longer one
            if len(r.get('raw_latex', '')) > len(prev.get('raw_latex', '')):
                merged[-1] = r
        else:
            merged.append(r)
    return merged


# ---------------------------------------------------------------------------
# Subtype resolver
# ---------------------------------------------------------------------------

_SUBTYPE_MAP = {
    'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
    'lemma': 'lemma', 'lem': 'lemma',
    'proposition': 'proposition', 'prop': 'proposition',
    'corollary': 'corollary', 'cor': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'problem': 'problem',
    'property': 'proposition',
    'align': 'problem',
    'equation': 'problem',
}

def _resolve_subtype(env_or_word: str) -> str:
    key = env_or_word.lower().rstrip('*')
    return _SUBTYPE_MAP.get(key, 'theorem')


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule A: \begin{property}[opt?] ... \end{property}
# Maps to proposition (subtype)
PATTERN_PROPERTY_ENV = re.compile(
    r'\\begin\{([Pp]roperty)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# Rule B: \begin{align*?} containing \max or \min and s.t. / subject to
# Maps to problem
PATTERN_OPTIMIZATION_ALIGN = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)
_OPT_SIGNAL = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_ST_SIGNAL = re.compile(r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|\\text\s*\{\s*subject\s+to\s*\}', re.IGNORECASE)

# Rule C: \begin{equation*?} ... \end{equation*?} containing (P_N) optimization label
PATTERN_PROBLEM_EQUATION = re.compile(
    r'\\begin\{(equation\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)
_PROBLEM_LABEL = re.compile(r'\(\s*P[\w_]*\s*\)')

# Rule D: Free-text \ba...\ea blocks preceded by a problem-signaling preamble sentence
# Targets paper001 mincut/ratiocut/ncut problems
# PRUNED — FP on paper001 | also 6 TP — review before uncommenting
# PATTERN_BA_EA_PROBLEM = re.compile(
#     r'(?P<preamble>(?:[^\n]|\n(?!\n)){30,800}?)'
#     r'\\ba\s*(?P<body>.*?)\\ea',
#     re.DOTALL
# )
_BA_SIGNAL = re.compile(
    r'(mincut|cut|partition|ratiocut|ncut|minmaxcut|objective\s+function|'
    r'maximize|minimize|argmin|argmax|criterion|consists\s+in\s+choosing)',
    re.IGNORECASE
)

# Rule E: Prose paragraph containing \argmin or \argmax as a definitional problem
# Targets paper004 Lasso/Dantzig definitions
# PRUNED — FP on paper004, paper007, paper010 | also 1 TP — review before uncommenting
# PATTERN_ARGMIN_PROSE = re.compile(
#     r'(?:(?<=\n\n)|(?:^))(?P<body>(?:[^\n]|\n(?!\n)){20,2000}?'
#     r'\\(?:argmin|argmax)\b'
#     r'(?:[^\n]|\n(?!\n)){10,2000}?)'
#     r'(?=\n\n|\Z)',
#     re.DOTALL | re.MULTILINE
# )

# Rule F: "Our goal is to estimate/predict/understand" paragraph + optional equation block
# Targets paper006 goal-problem descriptions
PATTERN_GOAL_PROBLEM = re.compile(
    r'(?P<preamble>'
    r'(?:Our\s+goal\s+is\s+to\b|The\s+goal\s+of\s+this\s+paper\s+is\s+to\b)'
    r'(?:[^\n]|\n(?!\n)){10,800}?'
    r')'
    r'(?:'
    r'(?P<eqblock>\\begin\{equation\*?\}.*?\\end\{equation\*?\})'
    r')?',
    re.DOTALL
)

# Rule G: align* block preceded within ~600 chars by a "guarantees ... that" phrasing
# followed by equation* - targets paper006 minimax lower bound theorem
PATTERN_MINIMAX_THEOREM = re.compile(
    r'(?P<preamble>'
    r'(?:guarantees\s+for\s+\\emph\{any\s+estimator\}|'
    r'H\\\'ajek|Hajek|minimax\s+theorem|lower\s+bound)'
    r'(?:[^\n]|\n(?!\n)){5,600}?'
    r')'
    r'\\begin\{equation\*?\}'
    r'(?P<body>.*?)'
    r'\\end\{equation\*?\}',
    re.DOTALL
)

# Rule H: align* block in paper002 with eigenvalue expressions (Marchenko-Pastur style)
# Not wrapped in a theorem env; signals: lambda_min / lambda_max goto
# PRUNED — FP on paper002
# PATTERN_EIGENVALUE_THEOREM = re.compile(
#     r'(?P<preamble>'
#     r'(?:[^\n]|\n(?!\n)){20,400}?'
#     r'(?:proved\s+that|following\s+upon\s+the\s+work\s+of)'
#     r'(?:[^\n]|\n(?!\n)){0,200}?'
#     r')'
#     r'\\begin\{(align\*?)\}'
#     r'(?P<body>.*?)'
#     r'\\end\{\2\}',
#     re.DOTALL
# )
_EIGEN_SIGNAL = re.compile(r'\\lambda_\{?\\(?:min|max)\}?', re.IGNORECASE)

# Rule I: \begin{definition}...\end{definition} describing a named problem
# (ANN / approximate near neighbor / etc.) -> reclassify as problem
PATTERN_DEFINITION_AS_PROBLEM = re.compile(
    r'\\begin\{([Dd]efinition)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)
_PROBLEM_CONTENT_SIGNAL = re.compile(
    r'\b(approximate\s+near\s+neighbor|ANN\b|NP.hard|sparse\s+solution|'
    r'underdetermined|data\s+structure.*query)',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: property environment -> proposition
    # ------------------------------------------------------------------
    for m in PATTERN_PROPERTY_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        opt = m.group('opt')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PROPERTY_ENV',
            'structure_type': 'proposition',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule B: optimization align blocks -> problem
    # ------------------------------------------------------------------
    for m in PATTERN_OPTIMIZATION_ALIGN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        if _OPT_SIGNAL.search(body) and _ST_SIGNAL.search(body):
            # grab preamble sentence before the align block (up to 600 chars back)
            preamble_start = max(0, start - 600)
            preamble_chunk = text[preamble_start:start]
            # find last paragraph boundary before align
            last_para = preamble_chunk.rfind('\n\n')
            if last_para >= 0:
                preamble = preamble_chunk[last_para:].strip()
            else:
                preamble = preamble_chunk.strip()
            raw = (preamble + '\n' + m.group(0)).strip() if preamble else m.group(0)
            results.append({
                'raw_latex': raw,
                'clean_text': _clean_latex(raw),
                'name': None,
                'env_name': 'distilled',
                'rule_name': 'PATTERN_OPTIMIZATION_ALIGN',
                'structure_type': 'problem',
                '_start': start,
                '_end': end,
            })

    # ------------------------------------------------------------------
    # Rule C: equation blocks with (P_N) label -> problem
    # ------------------------------------------------------------------
    # We want to join consecutive labeled equation blocks that belong to the same problem
    eq_matches = []
    for m in PATTERN_PROBLEM_EQUATION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        if _PROBLEM_LABEL.search(body) or _OPT_SIGNAL.search(body):
            eq_matches.append(m)

    # Group consecutive equation blocks (within 500 chars of each other) into one result
    used = set()
    for i, m in enumerate(eq_matches):
        if i in used:
            continue
        start = m.start()
        end = m.end()
        group_raw = m.group(0)
        # look ahead for closely following equation blocks
        for j in range(i + 1, len(eq_matches)):
            nm = eq_matches[j]
            if nm.start() - end < 500:
                gap = text[end:nm.start()]
                group_raw = group_raw + gap + nm.group(0)
                end = nm.end()
                used.add(j)
            else:
                break
        # grab preamble
        preamble_start = max(0, start - 400)
        preamble_chunk = text[preamble_start:start]
        last_para = preamble_chunk.rfind('\n\n')
        preamble = preamble_chunk[last_para:].strip() if last_para >= 0 else preamble_chunk.strip()
        raw = (preamble + '\n' + group_raw).strip() if preamble else group_raw
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PROBLEM_EQUATION',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule D: \ba...\ea free-text problems (paper001)
#     # ------------------------------------------------------------------
#     for m in PATTERN_BA_EA_PROBLEM.finditer(text):
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         preamble = m.group('preamble')
#         body = m.group('body')
#         if not _BA_SIGNAL.search(preamble):
#             continue
#         raw = preamble.strip() + ' \\ba ' + body.strip() + ' \\ea'
#         results.append({
#             'raw_latex': raw,
#             'clean_text': _clean_latex(raw),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'PATTERN_BA_EA_PROBLEM',
#             'structure_type': 'problem',
#             '_start': start,
#             '_end': end,
#         })

    # ------------------------------------------------------------------
    # Rule E: \argmin / \argmax definitional prose paragraphs (paper004)
#     # ------------------------------------------------------------------
#     for m in PATTERN_ARGMIN_PROSE.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         body = m.group('body')
#         if len(body.strip()) < 40:
#             continue
#         results.append({
#             'raw_latex': body.strip(),
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'PATTERN_ARGMIN_PROSE',
#             'structure_type': 'problem',
#             '_start': start,
#             '_end': end,
#         })

    # ------------------------------------------------------------------
    # Rule F: "Our goal is to..." / "The goal of this paper..." paragraphs
    # ------------------------------------------------------------------
    for m in PATTERN_GOAL_PROBLEM.finditer(text):
        start = m.start()
        preamble = m.group('preamble')
        eqblock = m.group('eqblock') or ''
        if len(preamble.strip()) < 30:
            continue
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = (preamble + eqblock).strip()
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_GOAL_PROBLEM',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule G: minimax / lower-bound theorem (paper006)
    # ------------------------------------------------------------------
    for m in PATTERN_MINIMAX_THEOREM.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        preamble = m.group('preamble')
        body = m.group('body')
        raw = (preamble + '\\begin{equation*}' + body + '\\end{equation*}').strip()
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_MINIMAX_THEOREM',
            'structure_type': 'theorem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule H: eigenvalue theorem (paper002 align* with lambda_min/max)
#     # ------------------------------------------------------------------
#     for m in PATTERN_EIGENVALUE_THEOREM.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         body = m.group('body')
#         preamble = m.group('preamble')
#         if not _EIGEN_SIGNAL.search(body):
#             continue
#         align_env = m.group(2)
#         raw = (preamble + '\\begin{' + align_env + '}' +
#                body + '\\end{' + align_env + '}').strip()
#         results.append({
#             'raw_latex': raw,
#             'clean_text': _clean_latex(raw),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'PATTERN_EIGENVALUE_THEOREM',
#             'structure_type': 'theorem',
#             '_start': start,
#             '_end': end,
#         })

    # ------------------------------------------------------------------
    # Rule I: definition environment describing a problem (paper011 ANN)
    # ------------------------------------------------------------------
    for m in PATTERN_DEFINITION_AS_PROBLEM.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        opt = m.group('opt')
        if not _PROBLEM_CONTENT_SIGNAL.search(body):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_DEFINITION_AS_PROBLEM',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Deduplicate and clean up internal keys
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
