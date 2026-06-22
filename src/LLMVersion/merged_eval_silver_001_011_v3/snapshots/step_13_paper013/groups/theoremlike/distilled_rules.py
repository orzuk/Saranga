import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text cleaner."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # Remove common formatting macros but keep their argument
    text = re.sub(r'\\(?:text|textbf|textit|emph|mathrm|mathbf|mathcal|mathbb|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove \cite, \ref, \eqref, \cref, \labelcref
    text = re.sub(r'\\(?:cite|ref|eqref|cref|labelcref|citep|citet)\{[^}]*\}', '', text)
    # Remove \footnote{...}
    text = re.sub(r'\\footnote\{[^}]*\}', '', text)
    # Remove display math environments (keep content)
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}', ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math $...$
    text = re.sub(r'\$[^$]*\$', '[MATH]', text)
    # Remove leftover LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})*', ' ', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments whose interior we want to exclude from matching
_EXCLUDED_ENVS = ['proof', 'Proof', 'example', 'Example', 'remark', 'Remark',
                  'algorithm', 'figure', 'table', 'lstlisting', 'verbatim']
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENVS)) + r')\}.*?\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another, or identical."""
    if not results:
        return results
    # Sort by length descending so larger spans come first
    results = sorted(results, key=lambda d: -len(d['raw_latex']))
    kept = []
    seen_spans: List[tuple] = []
    for d in results:
        pos = d.get('_pos', -1)
        length = len(d['raw_latex'])
        overlap = False
        for (s, e) in seen_spans:
            # check character-level overlap
            if not (pos + length <= s or pos >= e):
                overlap = True
                break
        if not overlap:
            kept.append(d)
            seen_spans.append((pos, pos + length))
    return kept


def _make_result(raw_latex: str, env_name: str, rule_name: str,
                 structure_type: str, name=None, pos: int = 0) -> dict:
    return {
        'raw_latex': raw_latex,
        'clean_text': _clean_latex(raw_latex),
        'name': name,
        'env_name': env_name,
        'rule_name': rule_name,
        'structure_type': structure_type,
        '_pos': pos,
    }


# ---------------------------------------------------------------------------
# Subtype resolver
# ---------------------------------------------------------------------------

_SUBTYPE_ENV_MAP = {
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

def _subtype_from_env(env_name: str) -> str:
    key = env_name.lower().rstrip('*')
    return _SUBTYPE_ENV_MAP.get(key, 'theorem')


# ---------------------------------------------------------------------------
# Rule 1: \begin{restatable}{<kind>}{<macro>} ... \end{restatable}
# ---------------------------------------------------------------------------

RESTATABLE_PATTERN = re.compile(
    r'\\begin\{restatable\}'
    r'\{(?P<kind>[^}]+)\}'
    r'\{(?P<macro>[^}]*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{restatable\}',
    flags=re.DOTALL
)


# ---------------------------------------------------------------------------
# Rule 2: \begin{property}[opt] ... \end{property}
# (maps to 'proposition')
# ---------------------------------------------------------------------------

PROPERTY_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>[Pp]roperty)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    flags=re.DOTALL
)


# ---------------------------------------------------------------------------
# Rule 3: Optimization problems inside equation/align environments
# whose body begins with a (P_...) / (Q_...) / (LP) / (SDP) / (OPT) label
# ---------------------------------------------------------------------------

OPTIMIZATION_LABEL_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>equation|align|gather)\*?\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\*?\}',
    flags=re.DOTALL | re.IGNORECASE
)

_OPT_LABEL_RE = re.compile(
    r'^\s*(?:\\label\{[^}]*\}\s*)?'
    r'\((?:P|Q|LP|IP|SDP|OPT|NLP|QP|QCQP)(?:[_^]\{?[^\)\}\s]{0,12}\}?)?\)',
    re.IGNORECASE
)

_OPT_OBJECTIVE_RE = re.compile(
    r'\\(?:max|min|argmax|argmin|operatorname\{(?:max|min|arg\s*max|arg\s*min)\})\b',
    re.IGNORECASE
)

_OPT_CONSTRAINT_RE = re.compile(
    r'(?:\\text\s*\{\s*s\.?\s*t\.?\s*\}|\\text\s*\{\s*subject\s+to\s*\}'
    r'|\\subjectto\b|\\st\b'
    r'|subject\s+to)',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Rule 4: Open-problem paragraphs after open/discussion/future-work sections
# ---------------------------------------------------------------------------

OPEN_SECTION_HEADING_RE = re.compile(
    r'\\(?:sub)*section\*?\s*\{[^}]*'
    r'(?:open\s*(?:problem|question)s?|discussion|conclusion|future\s*work|open\s+issues?)'
    r'[^}]*\}',
    flags=re.IGNORECASE
)

_OPEN_PROBLEM_SIGNALS = re.compile(
    r'(?:remain(?:s)?\s+open\b'
    r'|we\s+leave\b[^.]{0,300}?(?:open\s+question|future\s+work|future\s+research)'
    r'|open\s+(?:question|problem)s?\b'
    r'|leave\s+(?:this|these|it|them)\s+(?:question|problem|issue)'
    r'|an?\s+(?:interesting|natural|important)\s+(?:open\s+)?(?:problem|question)'
    r'|(?:does|can|is\s+it\s+possible|whether)\b[^?]{0,300}\?)',
    re.IGNORECASE | re.DOTALL
)


# ---------------------------------------------------------------------------
# Rule 5: Prose open-problem markers (general, document-wide)
# ---------------------------------------------------------------------------

# PRUNED — FP on paper002, paper003, paper007 | also 1 TP — review before uncommenting
# OPEN_PROBLEM_PROSE_PATTERN = re.compile(
#     r'(?:We\s+leave\b[^.]{0,400}?(?:open|future\s+work|future\s+research)[^.]*\.'
#     r'|[Ii]t\s+(?:remains?|is\s+still)\s+(?:an?\s+)?open\b[^.]{0,300}\.'
#     r'|[Aa]n?\s+(?:open|interesting|natural|important)\s+(?:problem|question)'
#     r'[^.]{0,300}\.)',
#     re.DOTALL
# )


# ---------------------------------------------------------------------------
# Rule 6: Named theorem-like environments NOT in BASE_ENV_KIND_MAP
# (catches custom env names that semantically map to known types)
# Additional aliases
# ---------------------------------------------------------------------------

EXTRA_ENV_ALIASES: Dict[str, str] = {
    'property':    'proposition',
    'Property':    'proposition',
    'fact':        'proposition',
    'Fact':        'proposition',
    'observation': 'proposition',
    'Observation': 'proposition',
    'notation':    'definition',
    'Notation':    'definition',
    'hypothesis':  'conjecture',
    'Hypothesis':  'conjecture',
    'question':    'open_problem',
    'Question':    'open_problem',
    'openquestion': 'open_problem',
    'OpenQuestion': 'open_problem',
    'openproblem':  'open_problem',
    'OpenProblem':  'open_problem',
}

_EXTRA_ENV_NAMES = list(EXTRA_ENV_ALIASES.keys())

EXTRA_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>' + '|'.join(map(re.escape, _EXTRA_ENV_NAMES)) + r')\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    flags=re.DOTALL
)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule: \begin{restatable}{<kind>}{<macro>} ... \end{restatable}
    # ------------------------------------------------------------------
    for m in RESTATABLE_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        inner_kind = m.group('kind').strip().lower().rstrip('*')
        structure_type = _SUBTYPE_ENV_MAP.get(inner_kind)
        if structure_type is None:
            continue
        opt = m.group('opt')
        body = m.group('body')
        raw = m.group(0)
        name = opt.strip() if opt else None
        results.append(_make_result(raw, 'distilled', 'RESTATABLE_PATTERN',
                                    structure_type, name=name, pos=m.start()))

    # ------------------------------------------------------------------
    # Rule: \begin{property}...\end{property} -> proposition
    # ------------------------------------------------------------------
    for m in PROPERTY_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        raw = m.group(0)
        name = opt.strip() if opt else None
        results.append(_make_result(raw, 'distilled', 'PROPERTY_ENV_PATTERN',
                                    'proposition', name=name, pos=m.start()))

    # ------------------------------------------------------------------
    # Rule: Extra environment aliases not in base map
    # ------------------------------------------------------------------
    for m in EXTRA_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        env = m.group('env')
        structure_type = EXTRA_ENV_ALIASES.get(env, 'theorem')
        opt = m.group('opt')
        raw = m.group(0)
        name = opt.strip() if opt else None
        results.append(_make_result(raw, 'distilled', 'EXTRA_ENV_PATTERN',
                                    structure_type, name=name, pos=m.start()))

    # ------------------------------------------------------------------
    # Rule: Optimization problems inside equation/align with (P_...) labels
    # ------------------------------------------------------------------
    for m in OPTIMIZATION_LABEL_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        stripped = re.sub(r'^\s*\\label\{[^}]*\}\s*', '', body, count=1)
        if _OPT_LABEL_RE.match(stripped):
            raw = m.group(0)
            results.append(_make_result(raw, 'distilled',
                                        'OPTIMIZATION_LABEL_ENV_PATTERN',
                                        'problem', pos=m.start()))
        elif _OPT_OBJECTIVE_RE.search(body) and _OPT_CONSTRAINT_RE.search(body):
            raw = m.group(0)
            results.append(_make_result(raw, 'distilled',
                                        'OPTIMIZATION_LABEL_ENV_PATTERN',
                                        'problem', pos=m.start()))

    # ------------------------------------------------------------------
    # Rule: Open problems in open/discussion/conclusion/future-work sections
    # ------------------------------------------------------------------
    for sec_match in OPEN_SECTION_HEADING_RE.finditer(text):
        sec_start = sec_match.end()
        # Find next section heading to bound the search
        next_sec = re.search(r'\\(?:sub)*section\*?\s*\{', text[sec_start:])
        sec_end = sec_start + next_sec.start() if next_sec else len(text)
        section_text = text[sec_start:sec_end]

        # Split into paragraphs
        paragraphs = re.split(r'\n{2,}', section_text)
        pos = sec_start
        for para in paragraphs:
            stripped = para.strip()
            # Filter: must have substantial content and open-problem signal
            if (len(stripped) > 80
                    and _OPEN_PROBLEM_SIGNALS.search(stripped)
                    and not re.match(r'^\s*\\', stripped)):  # skip pure LaTeX commands
                results.append(_make_result(
                    stripped, 'distilled', 'OPEN_SECTION_HEADING_RE',
                    'open_problem', pos=pos))
            pos += len(para) + 2

    # ------------------------------------------------------------------
    # Rule: General prose open-problem markers (document-wide)
#     # ------------------------------------------------------------------
#     for m in OPEN_PROBLEM_PROSE_PATTERN.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         raw = m.group(0).strip()
#         if len(raw) < 60:
#             continue
#         results.append(_make_result(raw, 'distilled', 'OPEN_PROBLEM_PROSE_PATTERN',
#                                     'open_problem', pos=m.start()))

    # ------------------------------------------------------------------
    # Remove private _pos key before returning (after dedup)
    # ------------------------------------------------------------------
    deduped = _deduplicate(results)
    for d in deduped:
        d.pop('_pos', None)

    for r in deduped:
        r.pop('_start', None)

    return deduped
