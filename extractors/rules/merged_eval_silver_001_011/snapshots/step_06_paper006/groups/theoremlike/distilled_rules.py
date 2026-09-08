import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*|citeNP|citeA)\s*(?:\[[^\]]*\])?\s*\{[^}]*\}', '', text)
    # Remove \begin{...} / \end{...} markers
    text = re.sub(r'\\(?:begin|end)\s*\{[^}]*\}', '', text)
    # Remove display math wrappers
    text = re.sub(r'\\[\[\]]', '', text)
    # Collapse common commands but keep their argument
    text = re.sub(r'\\(?:text|mathbf|mathit|mathrm|mathcal|textbf|textit|emph|widehat|what|widetilde|hat|tilde|bar|vec)\s*\{([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments that should be excluded as containers
_EXCLUDED_ENVS = ['proof', 'Proof', 'example', 'Example', 'remark', 'Remark',
                  'rem', 'note', 'exercise', 'Exercise']

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    prefix = text[:start]
    for env in _EXCLUDED_ENVS:
        open_pat = re.compile(r'\\begin\{' + re.escape(env) + r'\}', re.IGNORECASE)
        close_pat = re.compile(r'\\end\{' + re.escape(env) + r'\}', re.IGNORECASE)
        opens = [m.start() for m in open_pat.finditer(prefix)]
        closes = [m.start() for m in close_pat.finditer(prefix)]
        if len(opens) > len(closes):
            return True
    return False


def _deduplicate(matches: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the one with the longer raw_latex."""
    if not matches:
        return matches
    # Sort by start position
    matches_with_pos = sorted(matches, key=lambda d: d.get('_start', 0))
    result = []
    last_end = -1
    for m in matches_with_pos:
        s = m.get('_start', 0)
        e = m.get('_end', s + len(m['raw_latex']))
        if s >= last_end:
            result.append(m)
            last_end = e
        else:
            # Overlap: keep the longer one
            if result and len(m['raw_latex']) > len(result[-1]['raw_latex']):
                result[-1] = m
                last_end = e
    # Remove internal position keys
    for m in result:
        m.pop('_start', None)
        m.pop('_end', None)
    return result


# ---------------------------------------------------------------------------
# Pattern 1: \begin{property}...\end{property}
# Catches custom 'property' environments used in paper005 -> proposition
# ---------------------------------------------------------------------------
PROPERTY_ENV_RE = re.compile(
    r'\\begin\{([Pp]roperty)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 2: \begin{align}...\end{align} with \max or \min AND s.t. / subject to
# Catches optimization problem blocks (paper002, paper003)
# ---------------------------------------------------------------------------
OPTIMIZATION_ALIGN_RE = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

_OPT_VERB_RE = re.compile(r'\\(max|min)\b', re.IGNORECASE)
_ST_RE = re.compile(r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|subject\s+to', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Pattern 3: \begin{equation}...\end{equation} containing (P_0), (P_1), etc.
# Catches labelled problem equations in paper002
# ---------------------------------------------------------------------------
PROBLEM_EQUATION_RE = re.compile(
    r'\\begin\{(equation\*?)\}'
    r'(?P<body>.*?\(P[_0-9a-zA-Z]*\).*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 4: Free-text \ba...\ea blocks preceded by a 'problem-signaling' sentence
# Catches graph-cut problem descriptions in paper001
# ---------------------------------------------------------------------------
BA_EA_PROBLEM_RE = re.compile(
    r'(?P<preamble>(?:(?!\\ba|\\begin\{|\\end\{)[^\n]){20,800}?)'
    r'\\ba\s*(?P<math>.*?)\\ea',
    re.DOTALL
)

_PROBLEM_SIGNAL_RE = re.compile(
    r'mincut|partition\s+of|cut\s+objective|objective\s+function|minimize|'
    r'criterion|definition\s+are|we\s+introduce|consists\s+in\s+choosing|'
    r'Ratiocut|Ncut|MinmaxCut|simply\s+consists|problem\s+is\s+to',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 5: Prose paragraph + embedded equation block for 'problem' definitions
# Catches Lasso / Dantzig estimator definitions (paper004)
# ---------------------------------------------------------------------------
ARGMIN_PROSE_PROBLEM_RE = re.compile(
    r'(?:(?<=\n\n)|(?<=\A)|\n\n)'
    r'(?P<body>[^\n]{10,300}'     # opening sentence on same line
    r'(?:(?!\n\n).)*?'            # continue until double newline
    r'\\argmin'                   # must contain \argmin
    r'(?:(?!\n\n).)*?'            # continue
    r'(?:'
        r'\\begin\{equation\}'    # optionally include equation envs
        r'(?:(?!\\end\{equation\}).)*?'
        r'\\end\{equation\}'
        r'(?:(?!\n\n).)*?'
    r'){1,4}'
    r')',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 6: "Our goal is to estimate/predict" + equation block -> problem
# Catches paper006 goal-statement problems
# ---------------------------------------------------------------------------
OUR_GOAL_PROBLEM_RE = re.compile(
    r'(?P<preamble>Our\s+goal\s+is\s+to\s+(?:estimate|predict)'
    r'(?:(?!\n\n).){10,600}?)'
    r'(?P<eqblock>'
        r'\\begin\{equation\*?\}'
        r'(?:(?!\\end\{equation\}).)*?'
        r'\\end\{equation\*?\}'
    r')',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 7: "The goal of this paper is to" prose paragraph -> problem
# Catches paper006 paper-goal statement
# ---------------------------------------------------------------------------
PAPER_GOAL_PROBLEM_RE = re.compile(
    r'(?P<body>The\s+goal\s+of\s+this\s+paper\s+is\s+to\b'
    r'(?:(?!\n\n|\\paragraph|\\section|\\subsection).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 8: Subsection body preceding \begin{algorithm} -> theorem
# Catches paper005 subsection-level theorem prose
# ---------------------------------------------------------------------------
SUBSECTION_THEOREM_RE = re.compile(
    r'\\subsection\*?\{[^}]*\}\s*'
    r'(?P<body>(?:(?!\\begin\{algorithm\}|\\subsection|\\section)(?!\\begin\{(?:theorem|lemma|proposition|corollary|claim|conjecture|property)\}).)+?)'
    r'(?=\\begin\{algorithm\})',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 9: align* block with label eq:geman (paper002 Marchenko-Pastur theorem)
# Catches theorem-like math results stated in align* without theorem env
# ---------------------------------------------------------------------------
LABELED_ALIGN_THEOREM_RE = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?\\label\{[^}]*\}.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 10: "Then under our assumptions" + equation block -> theorem
# Catches paper006 minimax lower bound theorem stated in prose
# ---------------------------------------------------------------------------
MINIMAX_THEOREM_RE = re.compile(
    r'(?P<preamble>'
        r'(?:Then\s+under\s+our\s+assumptions|'
        r'H\\\'ajek|Hajek|minimax\s+theorem|guarantees\s+for\s+'
        r'\\\\?emph\{any\s+estimator\}|guarantees\s+for\s+\\emph)'
    r'(?:(?!\n\n).){10,600}?)'
    r'(?P<eqblock>'
        r'\\begin\{equation\*?\}'
        r'(?:(?!\\end\{equation\}).)*?'
        r'\\end\{equation\*?\}'
    r')',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Subtype resolver
# ---------------------------------------------------------------------------

_ENV_TO_SUBTYPE: Dict[str, str] = {
    'theorem': 'theorem', 'Theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
    'lemma': 'lemma', 'Lemma': 'lemma', 'lem': 'lemma',
    'proposition': 'proposition', 'Proposition': 'proposition', 'prop': 'proposition',
    'property': 'proposition', 'Property': 'proposition',
    'corollary': 'corollary', 'Corollary': 'corollary', 'cor': 'corollary',
    'claim': 'claim', 'Claim': 'claim',
    'conjecture': 'conjecture', 'Conjecture': 'conjecture',
    'problem': 'problem', 'Problem': 'problem',
    'align': 'problem', 'align*': 'problem',
    'equation': 'problem', 'equation*': 'problem',
    'optimization': 'problem',
    'freetext_ba': 'problem',
    'prose_problem': 'problem',
    'goal_problem': 'problem',
    'paper_goal': 'problem',
    'subsection_implicit': 'theorem',
    'minimax_theorem': 'theorem',
    'labeled_align': 'theorem',
}


def _subtype_from_env(env_name: str) -> str:
    return _ENV_TO_SUBTYPE.get(env_name, 'theorem')


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \begin{property}...\end{property} -> proposition
    # ------------------------------------------------------------------
    for m in PROPERTY_ENV_RE.finditer(text):
        env_name = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PROPERTY_ENV_RE',
            'structure_type': 'proposition',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule B: align/align* optimization problems (\max/\min + s.t.)
    # ------------------------------------------------------------------
    for m in OPTIMIZATION_ALIGN_RE.finditer(text):
        body = m.group('body')
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if not (_OPT_VERB_RE.search(body) and _ST_RE.search(body)):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPTIMIZATION_ALIGN_RE',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule C: equation environments containing (P_N) labels -> problem
    # ------------------------------------------------------------------
    for m in PROBLEM_EQUATION_RE.finditer(text):
        body = m.group('body')
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROBLEM_EQUATION_RE',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule D: \ba...\ea blocks with a problem-signaling preamble
    # ------------------------------------------------------------------
    for m in BA_EA_PROBLEM_RE.finditer(text):
        preamble = m.group('preamble')
        math = m.group('math')
        if not _PROBLEM_SIGNAL_RE.search(preamble):
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = preamble.strip() + ' \\ba ' + math.strip() + ' \\ea'
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(preamble + ' ' + math),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BA_EA_PROBLEM_RE',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule E: Prose paragraphs containing \argmin + equation blocks -> problem
    # ------------------------------------------------------------------
    # Use a simpler approach: find double-newline-delimited blocks containing \argmin
    paragraphs = list(re.finditer(r'(?:(?<=\n\n)|(?:^))(.+?)(?=\n\n|\Z)', text, re.DOTALL))
    for pm in paragraphs:
        body = pm.group(0)
        start = pm.start()
        end = pm.end()
        if '\\argmin' not in body:
            continue
        if _inside_excluded_env(text, start, end):
            continue
        # Must contain at least one equation environment
        if not re.search(r'\\begin\{equation', body):
            continue
        # Must not already be caught by a named theorem env (check for \begin{theorem} etc.)
        if re.search(r'\\begin\{(?:theorem|lemma|proposition|corollary|claim|conjecture|problem)\}', body, re.IGNORECASE):
            continue
        results.append({
            'raw_latex': body.strip(),
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'ARGMIN_PROSE_PROBLEM_RE',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule F: "Our goal is to estimate/predict" + equation -> problem
    # ------------------------------------------------------------------
    for m in OUR_GOAL_PROBLEM_RE.finditer(text):
        preamble = m.group('preamble')
        eqblock = m.group('eqblock')
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = preamble.strip() + '\n' + eqblock.strip()
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OUR_GOAL_PROBLEM_RE',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule G: "The goal of this paper is to" paragraph -> problem
    # ------------------------------------------------------------------
    for m in PAPER_GOAL_PROBLEM_RE.finditer(text):
        body = m.group('body')
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if len(body.strip()) < 40:
            continue
        results.append({
            'raw_latex': body.strip(),
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PAPER_GOAL_PROBLEM_RE',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule H: Subsection body before \begin{algorithm} -> theorem
    # ------------------------------------------------------------------
    for m in SUBSECTION_THEOREM_RE.finditer(text):
        body = m.group('body')
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if len(body.strip()) < 50:
            continue
        results.append({
            'raw_latex': body.strip(),
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_THEOREM_RE',
            'structure_type': 'theorem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule I: align* with \label (theorem-like math result) -> theorem
    # Only when content is substantive and not an optimization problem
    # ------------------------------------------------------------------
    for m in LABELED_ALIGN_THEOREM_RE.finditer(text):
        body = m.group('body')
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        # Skip if it's an optimization problem (already handled by Rule B)
        if _OPT_VERB_RE.search(body) and _ST_RE.search(body):
            continue
        # Must have a label that looks like a result (geman, eigenvalue, etc.)
        if not re.search(r'\\label\{', body):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'LABELED_ALIGN_THEOREM_RE',
            'structure_type': 'theorem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule J: Minimax / lower-bound theorems stated in prose + equation
    # ------------------------------------------------------------------
    for m in MINIMAX_THEOREM_RE.finditer(text):
        preamble = m.group('preamble')
        eqblock = m.group('eqblock')
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = preamble.strip() + '\n' + eqblock.strip()
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'MINIMAX_THEOREM_RE',
            'structure_type': 'theorem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    return results
