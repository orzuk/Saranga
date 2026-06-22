import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands, leaving readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite|citep|citet|citealt|bibitem)\{[^}]*\}', '', text)
    # Remove \footnote{...} (simple, non-nested)
    text = re.sub(r'\\footnote\{[^}]*\}', '', text)
    # Remove display math environments, keep content
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}(.*?)\\end\{(?:equation|align|gather|multline)\*?\}',
                  r' \1 ', text, flags=re.DOTALL)
    # Remove \[ ... \]
    text = re.sub(r'\\\[(.*?)\\\]', r' \1 ', text, flags=re.DOTALL)
    # Remove inline math markers $...$ roughly
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]{0,300}?\$', ' ', text, flags=re.DOTALL)
    # Remove common formatting commands
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove remaining \command[...]{...} or \command{...}
    text = re.sub(r'\\[a-zA-Z]+(?:\[[^\]]*\])?(?:\{[^}]*\})*', '', text)
    # Remove remaining braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments that should not contain extracted results
_EXCLUDED_ENVS = ['proof', 'example', 'remark', 'rem', 'Proof', 'Example', 'Remark']
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENVS)) + r')\}',
    re.IGNORECASE
)
_EXCLUDED_END_RE = re.compile(
    r'\\end\{(' + '|'.join(map(re.escape, _EXCLUDED_ENVS)) + r')\}',
    re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    prefix = text[:start]
    # Count opens and closes of excluded envs before our span
    opens = list(_EXCLUDED_ENV_RE.finditer(prefix))
    closes = list(_EXCLUDED_END_RE.finditer(prefix))
    # Simple nesting check: more opens than closes means we're inside one
    if len(opens) > len(closes):
        return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule A: \begin{property}...\end{property}  -> proposition
# Catches custom 'property'/'Property' environments (maps to proposition)
PATTERN_PROPERTY_ENV = re.compile(
    r'\\begin\{(property|Property)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?:property|Property)\}',
    re.DOTALL | re.IGNORECASE
)

# Rule B: Additional theorem-like env names not in base map
# Catches: \begin{theo}...\end{theo}, \begin{thm}...\end{thm} variants,
# and other aliases that might appear in custom style files.
# Only add envs NOT already in BASE_ENV_KIND_MAP.
PATTERN_EXTRA_THEOREM_ENVS = re.compile(
    r'\\begin\{(result|Result|observation|Observation|fact|Fact|'
    r'hypothesis|Hypothesis|criterion|Criterion|assertion|Assertion)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end{\1}',
    re.DOTALL
)

# Rule C: Optimization problems expressed as align/equation blocks
# whose body contains \max or \min together with s.t. / subject to.
# Anchored on LaTeX math environment structure, NOT content tokens.
PATTERN_OPTIMIZATION_PROBLEM_ENV = re.compile(
    r'\\begin\{(?P<envname>align\*?|equation\*?|gather\*?|alignat\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}',
    re.DOTALL
)

_OPT_OBJECTIVE_RE = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_OPT_CONSTRAINT_RE = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}'
    r'|\\text\s*\{\s*subject\s+to\s*\}'
    r'|\bsubject\s+to\b',
    re.IGNORECASE
)

# Rule D: Optimization problem labels (P_0), (P_1), (Q_k), (LP), (SDP) etc.
# inside equation/align environments. Structural anchor: env + leading label pattern.
PATTERN_LABELED_PROBLEM_ENV = re.compile(
    r'\\begin\{(?P<envname>equation\*?|align\*?|gather\*?)\}'
    r'(?:\s*\\label\{[^}]*\}\s*)?'
    r'\s*(?P<body>.*?)'
    r'\\end\{(?P=envname)\}',
    re.DOTALL
)

_PROBLEM_LABEL_RE = re.compile(
    r'^\s*\((?:P|Q|LP|IP|SDP|OPT|NP)(?:[_^]\{?[^\)\}]{0,15}\}?)?\)\s*',
    re.IGNORECASE
)

# Rule E: Open-problem prose paragraphs introduced by recognized structural phrases.
# Anchored on a leading keyword phrase at paragraph start.
PATTERN_OPEN_PROBLEM_PROSE = re.compile(
    r'(?:^|\n\n)'
    r'(?P<body>'
    r'(?:'
    r'It\s+(?:remains|is\s+still)\s+(?:an?\s+)?open'
    r'|[Aa]n?\s+open\s+(?:problem|question|challenge)'
    r'|[Ww]e\s+(?:leave|pose|state)\s+(?:the\s+following\s+)?(?:as\s+an?\s+)?open'
    r'|[Tt]he\s+following\s+(?:problem|question)\s+(?:remains|is)\s+open'
    r'|[Oo]pen\s+(?:Problem|Question|Challenge)\s*[.:]'
    r')'
    r'(?:(?!\n\n).){30,800}'
    r')',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Subtype determination
# ---------------------------------------------------------------------------

_ENV_TO_SUBTYPE: Dict[str, str] = {
    'property': 'proposition',
    'result': 'theorem',
    'observation': 'theorem',
    'fact': 'theorem',
    'hypothesis': 'theorem',
    'criterion': 'theorem',
    'assertion': 'theorem',
}

_KEYWORD_TO_SUBTYPE = [
    (re.compile(r'\btheorem\b', re.IGNORECASE), 'theorem'),
    (re.compile(r'\blemma\b', re.IGNORECASE), 'lemma'),
    (re.compile(r'\bproposition\b', re.IGNORECASE), 'proposition'),
    (re.compile(r'\bcorollary\b', re.IGNORECASE), 'corollary'),
    (re.compile(r'\bclaim\b', re.IGNORECASE), 'claim'),
    (re.compile(r'\bconjecture\b', re.IGNORECASE), 'conjecture'),
    (re.compile(r'\bopen\s*problem\b|\bopen\s*question\b', re.IGNORECASE), 'open_problem'),
    (re.compile(r'\bproblem\b', re.IGNORECASE), 'problem'),
]


def _subtype_from_env(env_name: str) -> str:
    key = env_name.rstrip('*').lower()
    return _ENV_TO_SUBTYPE.get(key, 'theorem')


def _subtype_from_text(text: str, default: str = 'theorem') -> str:
    for pattern, subtype in _KEYWORD_TO_SUBTYPE:
        if pattern.search(text[:120]):
            return subtype
    return default


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result's raw_latex,
    and remove exact duplicates. Keep longest match when overlapping."""
    if not results:
        return results
    # Sort by length of raw_latex descending
    sorted_r = sorted(results, key=lambda d: len(d['raw_latex']), reverse=True)
    kept = []
    kept_texts = []
    for r in sorted_r:
        rl = r['raw_latex'].strip()
        dominated = False
        for kt in kept_texts:
            if rl in kt or rl == kt:
                dominated = True
                break
        if not dominated:
            kept.append(r)
            kept_texts.append(rl)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    """
    Extracts theorem-like structures not caught by the base parser.
    Returns a list of dicts with keys:
      raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: property/Property environments -> proposition
    # ------------------------------------------------------------------
    for m in PATTERN_PROPERTY_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PROPERTY_ENV',
            'structure_type': 'proposition',
        })

    # ------------------------------------------------------------------
    # Rule B: Extra theorem-like environments not in base map
    # ------------------------------------------------------------------
    for m in PATTERN_EXTRA_THEOREM_ENVS.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env = m.group(1)
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        subtype = _subtype_from_env(env)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_EXTRA_THEOREM_ENVS',
            'structure_type': subtype,
        })

    # ------------------------------------------------------------------
    # Rule C: Optimization problems (align/equation with \max/\min + s.t.)
    # ------------------------------------------------------------------
    for m in PATTERN_OPTIMIZATION_PROBLEM_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        if not (_OPT_OBJECTIVE_RE.search(body) and _OPT_CONSTRAINT_RE.search(body)):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_OPTIMIZATION_PROBLEM_ENV',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule D: Labeled optimization problems (P_0), (LP), etc. in display math
    # ------------------------------------------------------------------
    for m in PATTERN_LABELED_PROBLEM_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        # Strip leading \label{...} before checking
        stripped = re.sub(r'^\s*\\label\{[^}]*\}\s*', '', body)
        if not _PROBLEM_LABEL_RE.match(stripped):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_LABELED_PROBLEM_ENV',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule E: Open-problem prose paragraphs
    # ------------------------------------------------------------------
    for m in PATTERN_OPEN_PROBLEM_PROSE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_OPEN_PROBLEM_PROSE',
            'structure_type': 'open_problem',
        })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    return _deduplicate(results)
