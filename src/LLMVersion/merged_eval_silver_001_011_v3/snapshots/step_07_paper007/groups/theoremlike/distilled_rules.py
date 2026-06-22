import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and return cleaner plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # Remove \cite{...}, \citep{...}, \citet{...} etc.
    text = re.sub(r'\\cite[a-z]*\{[^}]*\}', '', text)
    # Remove \ref{...}, \eqref{...}
    text = re.sub(r'\\(?:eq)?ref\{[^}]*\}', '', text)
    # Remove \footnote{...} (shallow)
    text = re.sub(r'\\footnote\{[^}]*\}', '', text)
    # Unwrap \text{...}, \textbf{...}, \textit{...}, \emph{...}
    text = re.sub(r'\\(?:text(?:bf|it|rm|sf|tt)?|emph|mathbf|mathit|mathrm)\{([^}]*)\}', r'\1', text)
    # Remove display math environments leaving their content
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}(.*?)\\end\{(?:equation|align|gather|multline)\*?\}',
                  r' \1 ', text, flags=re.DOTALL)
    # Remove \[ ... \] and $ ... $
    text = re.sub(r'\\\[.*?\\\]', ' ... ', text, flags=re.DOTALL)
    text = re.sub(r'\$\$.*?\$\$', ' ... ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', '...', text)
    # Remove remaining LaTeX commands with arguments
    text = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', '', text)
    # Remove remaining LaTeX commands (no args)
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments to treat as "excluded" — matches inside these are suppressed
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|figure|table|lstlisting|verbatim)\*?\}',
    re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    prefix = text[:start]
    for m in _EXCLUDED_ENV_RE.finditer(prefix):
        env = m.group(1)
        end_tag = re.compile(
            r'\\end\{' + re.escape(env) + r'\*?\}',
            re.IGNORECASE
        )
        end_m = end_tag.search(text, m.end())
        if end_m and end_m.start() >= end:
            return True
    return False


# ---------------------------------------------------------------------------
# Subtype resolution
# ---------------------------------------------------------------------------

_SUBTYPE_MAP = {
    'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
    'lemma': 'lemma', 'lem': 'lemma',
    'proposition': 'proposition', 'prop': 'proposition', 'property': 'proposition',
    'corollary': 'corollary', 'cor': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'problem': 'problem',
    'open_problem': 'open_problem', 'openproblem': 'open_problem',
    'openquestion': 'open_problem', 'open': 'open_problem',
}

_KEYWORD_SUBTYPE_RE = re.compile(
    r'\b(theorem|lemma|proposition|corollary|claim|conjecture|problem|open\s+problem|open\s+question)\b',
    re.IGNORECASE
)


def _resolve_subtype(env_name: str, text_fragment: str = '') -> str:
    key = env_name.lower().rstrip('*')
    if key in _SUBTYPE_MAP:
        return _SUBTYPE_MAP[key]
    # Try to infer from text
    m = _KEYWORD_SUBTYPE_RE.search(text_fragment)
    if m:
        word = m.group(1).lower().replace(' ', '_')
        return _SUBTYPE_MAP.get(word, 'theorem')
    return 'theorem'


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose spans overlap, keeping the first encountered."""
    kept = []
    used_spans = []
    for r in results:
        s = r.get('_start', 0)
        e = r.get('_end', s + len(r.get('raw_latex', '')))
        overlaps = any(not (e <= us or s >= ue) for us, ue in used_spans)
        if not overlaps:
            used_spans.append((s, e))
            kept.append(r)
    # Remove internal span keys
    for r in kept:
        r.pop('_start', None)
        r.pop('_end', None)
    return kept


# ---------------------------------------------------------------------------
# Rule 1 — Non-standard / custom theorem-like environments
# (property, Property, result, Result, fact, Fact, observation, Observation,
#  criterion, Criterion, hypothesis, Hypothesis, question, Question, notation, Notation)
# ---------------------------------------------------------------------------

CUSTOM_THEOREM_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>'
    r'property|Property|'
    r'result|Result|'
    r'fact|Fact|'
    r'observation|Observation|'
    r'criterion|Criterion|'
    r'hypothesis|Hypothesis|'
    r'question|Question'
    r')\*?}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\*?}',
    re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Rule 2 — Optimization problems in equation/align environments
# Body contains \min or \max together with s.t./subject to marker
# ---------------------------------------------------------------------------

OPT_PROBLEM_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>equation|align|gather|multline)\*?}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\*?}',
    re.DOTALL | re.IGNORECASE
)

_OPT_OBJECTIVE_RE = re.compile(r'\\(?:min|max)\b', re.IGNORECASE)
_OPT_CONSTRAINT_RE = re.compile(
    r'\\text\s*\{\s*s(?:\.|ubject)?\s*\.?\s*t\.?\s*\}|'
    r'\bsubject\s+to\b|'
    r'\\text\s*\{\s*subject\s+to\s*\}',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Rule 3 — Prose open-problem paragraphs
# "We leave ... (as an) open question/problem"
# "remain(s) open"
# "leave ... to/for future work"
# ---------------------------------------------------------------------------

PROSE_OPEN_PROBLEM_PATTERN = re.compile(
    r'(?:(?<=\n\n)|(?<=\n)|(?:^))'
    r'(?P<body>'
    r'(?:'
    # Signal A: "We leave ... open question/problem"
    r'(?:We\s+leave\b[^\n]{0,400}?open\s+(?:question|problem)s?)'
    r'|'
    # Signal B: "remain(s) open"
    r'(?:[A-Z][^\n]{0,400}?remain\s+open\b[^\n]{0,300})'
    r'|'
    # Signal C: "leave ... to/for future work"
    r'(?:We\s+leave\b[^\n]{0,400}?(?:to|for)\s+future\s+work\b[^\n]{0,200})'
    r'|'
    # Signal D: explicit "open question/problem" as subject at para start
    r'(?:(?:An?|The|One)\s+(?:intriguing\s+|interesting\s+|natural\s+|important\s+)?'
    r'open\s+(?:question|problem)\b[^\n]{0,400})'
    r')'
    r'(?:[^\n]*\n(?!\n)[^\n]*){0,4}'  # allow multi-line, stop at blank line
    r')'
    r'(?=\n\n|\n?\\(?:section|subsection|paragraph|end)|$)',
    re.MULTILINE | re.DOTALL
)


# ---------------------------------------------------------------------------
# Rule 4 — Prose theorem-like statements introduced by bold/emph keywords
# e.g. \textbf{Theorem} or \emph{Theorem} outside a named environment
# ---------------------------------------------------------------------------

PROSE_BOLD_THEOREM_PATTERN = re.compile(
    r'\\(?:textbf|emph|textit)\s*\{'
    r'(?P<kw>Theorem|Lemma|Proposition|Corollary|Claim|Conjecture|Problem|Fact|Result)'
    r'(?:\s+[^}]{0,60})?'
    r'\}'
    r'(?P<body>'
    r'[^\n]{0,30}'             # optional text on same line after keyword
    r'(?:\n(?!\n)[^\n]*){0,8}' # up to 8 continuation lines
    r')'
    r'(?=\n\n|\n?\\(?:section|subsection|paragraph)|$)',
    re.MULTILINE
)


# ---------------------------------------------------------------------------
# Rule 5 — Prose "informal" theorem statements via leading keyword + colon
# e.g.  "Theorem (informal): ..."  or "Theorem 1 (Main Result)."
# outside any begin/end block
# ---------------------------------------------------------------------------

PROSE_KEYWORD_COLON_PATTERN = re.compile(
    r'(?:^|(?<=\n\n))'
    r'(?P<kw>Theorem|Lemma|Proposition|Corollary|Claim|Conjecture|Problem)'
    r'(?:\s*\([^)]{0,80}\))?'   # optional parenthetical label
    r'\s*[:\.]'
    r'(?P<body>'
    r'[^\n]{0,600}'
    r'(?:\n(?!\n)[^\n]{0,300}){0,6}'
    r')',
    re.MULTILINE
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule 1: Custom / non-standard theorem-like environments ---------------
    for m in CUSTOM_THEOREM_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        env = m.group('env')
        opt = m.group('opt')
        body = m.group('body')
        subtype = _resolve_subtype(env, body)
        results.append({
            'raw_latex': m.group(0),
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'CUSTOM_THEOREM_ENV_PATTERN',
            'structure_type': subtype,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule 2: Optimization problems in equation/align environments ----------
    for m in OPT_PROBLEM_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if not (_OPT_OBJECTIVE_RE.search(body) and _OPT_CONSTRAINT_RE.search(body)):
            continue
        results.append({
            'raw_latex': m.group(0),
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPT_PROBLEM_ENV_PATTERN',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule 3: Prose open-problem paragraphs ---------------------------------
    for m in PROSE_OPEN_PROBLEM_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_OPEN_PROBLEM_PATTERN',
            'structure_type': 'open_problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule 4: Bold/emph keyword theorem-like statements ---------------------
    for m in PROSE_BOLD_THEOREM_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('kw')
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        subtype = _resolve_subtype(kw)
        results.append({
            'raw_latex': m.group(0),
            'clean_text': _clean_latex(m.group(0)),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_BOLD_THEOREM_PATTERN',
            'structure_type': subtype,
            '_start': m.start(),
            '_end': m.end(),
        })

    # --- Rule 5: Prose keyword-colon statements --------------------------------
    for m in PROSE_KEYWORD_COLON_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('kw')
        body = m.group('body').strip()
        if len(body) < 15:
            continue
        subtype = _resolve_subtype(kw)
        results.append({
            'raw_latex': m.group(0),
            'clean_text': _clean_latex(m.group(0)),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_KEYWORD_COLON_PATTERN',
            'structure_type': subtype,
            '_start': m.start(),
            '_end': m.end(),
        })

    # Sort by position then deduplicate overlapping spans
    results.sort(key=lambda r: r.get('_start', 0))
    results = _deduplicate(results)

    return results
