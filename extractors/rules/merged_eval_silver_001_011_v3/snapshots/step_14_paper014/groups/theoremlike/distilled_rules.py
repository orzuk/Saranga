import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and return plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # Remove \cite{...} and \citep{...} etc.
    text = re.sub(r'\\cite[a-z]*\*?\{[^}]*\}', '', text)
    # Remove \ref{...} \eqref{...} \cref{...} \labelcref{...}
    text = re.sub(r'\\(?:eq|c|label)?ref\*?\{[^}]*\}', '', text)
    # Remove \begin{...} and \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math environments content markers but keep text
    text = re.sub(r'\\(?:left|right)[.()\[\]|\\]', '', text)
    # Remove common formatting commands but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb)\{([^}]*)\}', r'\1', text)
    # Remove remaining single-argument commands
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z@]+\*?', ' ', text)
    # Remove $ signs
    text = re.sub(r'\$+', '', text)
    # Remove { }
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose content should be excluded from extraction
_EXCLUDED_ENVS = ['proof', 'Proof', 'example', 'Example', 'remark', 'Remark',
                  'figure', 'table', 'verbatim', 'lstlisting']

_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(map(re.escape, _EXCLUDED_ENVS)) + r')\}',
    re.DOTALL | re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    # Collect all excluded env spans
    for m in _EXCLUDED_ENV_RE.finditer(text):
        env_name = m.group(1)
        env_start = m.start()
        # Find matching \end
        end_pattern = re.compile(
            r'\\end\{' + re.escape(env_name) + r'\}',
            re.IGNORECASE
        )
        end_m = end_pattern.search(text, m.end())
        if end_m:
            env_end = end_m.end()
            if env_start <= start and end <= env_end:
                return True
    return False


# ---------------------------------------------------------------------------
# Subtype mapping helpers
# ---------------------------------------------------------------------------

def _env_to_structure_type(env_name: str) -> str:
    """Map an environment name to a structure_type subtype."""
    name = env_name.lower().rstrip('*')
    _map = {
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
    return _map.get(name, 'theorem')


def _keyword_to_structure_type(word: str) -> str:
    """Map a leading keyword (e.g. 'Theorem', 'Lemma') to a structure_type."""
    w = word.lower().rstrip('s').rstrip('*').rstrip('.')
    _map = {
        'theorem': 'theorem',
        'lemma': 'lemma',
        'proposition': 'proposition',
        'corollary': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem',
        'open problem': 'open_problem',
        'open question': 'open_problem',
    }
    return _map.get(w, 'theorem')


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \begin{restatable}{<kind>}{<macro>}[opt] body \end{restatable}
RESTATABLE_PATTERN = re.compile(
    r'\\begin\{restatable\}'
    r'\{(?P<kind>[^}]+)\}'
    r'\{(?P<macro>[^}]*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{restatable\}',
    flags=re.DOTALL
)

# Rule 2: \begin{property}[opt] body \end{property}  -> proposition
PROPERTY_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<envname>[Pp]roperty)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}',
    flags=re.DOTALL
)

# Rule 3: Optimization problems inside equation/align/gather with \max or \min + s.t./subject to
OPT_PROBLEM_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<envname>(?:align|equation|gather)\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}',
    flags=re.DOTALL | re.IGNORECASE
)

_OPT_OBJ_RE = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_OPT_ST_RE  = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|'
    r'\\text\s*\{\s*subject\s+to\s*\}|'
    r'\bsubject\s+to\b',
    re.IGNORECASE
)

# Rule 4: Optimization problem with (P_N) / (P^N) label at start of equation/align
OPT_LABEL_PATTERN = re.compile(
    r'\\begin\{(?P<envname>(?:align|equation|gather)\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}',
    flags=re.DOTALL | re.IGNORECASE
)

_OPT_LABEL_BODY_RE = re.compile(
    r'^\s*(?:\\label\{[^}]*\}\s*)?'
    r'\((?:P|Q|OPT|LP|IP|SDP|NP|CP)(?:[_^]\{?[^\)\}]{0,15}\}?)?\)',
    re.IGNORECASE
)

# Rule 5: Open problem in prose – "We leave ... open question(s)" or "remain(s) open"
OPEN_PROBLEM_LEAVE_PATTERN = re.compile(
    r'(?:(?:^|\n)[ \t]*)'
    r'(?P<body>'
    r'(?:We\s+leave\b[^\n]{0,500}?(?:open\s+(?:question|problem)s?)[^\n]*)'
    r'(?:\n(?!\n)[^\n]*)*'
    r')',
    flags=re.MULTILINE | re.IGNORECASE
)

# Rule 6: Open problem – "leave ... to/for future work"
FUTURE_WORK_PATTERN = re.compile(
    r'(?:(?:^|\n)[ \t]*)'
    r'(?P<body>'
    r'(?:[^\n]{0,300}?\bWe\s+leave\b[^\n]{0,300}?'
    r'(?:to|for)\s+future\s+work[^\n]*)'
    r'(?:\n(?!\n)[^\n]*)*'
    r')',
    flags=re.MULTILINE | re.IGNORECASE
)

# Rule 7: Open problem – "remain(s) open" in a paragraph (≥80 chars)
# PRUNED — FP on paper003, paper007, paper008 +1 more | also 2 TP — review before uncommenting
# REMAIN_OPEN_PATTERN = re.compile(
#     r'(?:(?:^|\n\n)[ \t]*)'
#     r'(?P<body>'
#     r'[^\n]{10,}'
#     r'(?:remain(?:s)?\s+open\b|open\s+(?:question|problem)s?)[^\n]{0,400}'
#     r'(?:\n(?!\n)[^\n]*)*'
#     r')',
#     flags=re.MULTILINE | re.IGNORECASE
# )

# Rule 8: Prose sentences with interrogative questions inside open-problem sections
OPEN_SECTION_HEADING_RE = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*'
    r'(?:open\s*(?:problem|question)s?|discussion|conclusion|future\s*work)'
    r'[^}]*\}',
    flags=re.IGNORECASE
)

# Rule 9: Prose paragraph + enumerate/itemize that is introduced by "problem(s)" keyword
PROSE_PROBLEM_ENUM_PATTERN = re.compile(
    r'(?:(?:^|\n)[ \t]*(?P<leadin>[^\n]*?\bproblems?\b[^\n]*))\n'
    r'(?P<body>\\begin\{(?:enumerate|itemize)\}.*?\\end\{(?:enumerate|itemize)\})',
    flags=re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _dedup(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, preferring longer raw_latex."""
    results.sort(key=lambda d: (d.get('_start', 0), -len(d.get('raw_latex', ''))))
    out = []
    last_end = -1
    for r in results:
        s = r.get('_start', 0)
        e = r.get('_end', s + len(r.get('raw_latex', '')))
        if s >= last_end:
            out.append(r)
            last_end = e
    # Strip internal tracking keys
    for r in out:
        r.pop('_start', None)
        r.pop('_end', None)
    return out


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Pattern: RESTATABLE_PATTERN
    # \begin{restatable}{theorem/lemma/...}{macro}[opt] body \end{restatable}
    # ------------------------------------------------------------------
    _RESTATABLE_KIND_MAP = {
        'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
        'lemma': 'lemma', 'lem': 'lemma',
        'proposition': 'proposition', 'prop': 'proposition',
        'corollary': 'corollary', 'cor': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem',
        'open_problem': 'open_problem',
    }
    _THEOREM_LIKE_KINDS = {
        'theorem', 'lemma', 'proposition', 'corollary', 'claim',
        'conjecture', 'problem', 'open_problem',
    }
    for m in RESTATABLE_PATTERN.finditer(text):
        inner_kind_raw = m.group('kind').strip().lower().rstrip('*')
        kind = _RESTATABLE_KIND_MAP.get(inner_kind_raw)
        if kind is None or kind not in _THEOREM_LIKE_KINDS:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        body = m.group('body')
        name = opt.strip() if opt else None
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'RESTATABLE_PATTERN',
            'structure_type': kind,
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Pattern: PROPERTY_ENV_PATTERN
    # \begin{property/Property}[opt] body \end{property/Property} -> proposition
    # ------------------------------------------------------------------
    for m in PROPERTY_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        body = m.group('body')
        name = opt.strip() if opt else None
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'PROPERTY_ENV_PATTERN',
            'structure_type': 'proposition',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Pattern: OPT_PROBLEM_ENV_PATTERN
    # equation/align/gather containing \max or \min + subject-to marker
    # ------------------------------------------------------------------
    for m in OPT_PROBLEM_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if _OPT_OBJ_RE.search(body) and _OPT_ST_RE.search(body):
            raw = m.group(0)
            results.append({
                'raw_latex': raw,
                'clean_text': _clean_latex(body),
                'name': None,
                'env_name': 'distilled',
                'rule_name': 'OPT_PROBLEM_ENV_PATTERN',
                'structure_type': 'problem',
                '_start': m.start(),
                '_end': m.end(),
            })

    # ------------------------------------------------------------------
    # Pattern: OPT_LABEL_PATTERN
    # equation/align/gather whose body starts with (P_N) / (Q_k) etc.
    # ------------------------------------------------------------------
    for m in OPT_LABEL_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        # Strip leading \label{} before checking for (P...) token
        stripped = re.sub(r'^\s*\\label\{[^}]*\}\s*', '', body, count=1)
        if _OPT_LABEL_BODY_RE.match(stripped):
            raw = m.group(0)
            results.append({
                'raw_latex': raw,
                'clean_text': _clean_latex(body),
                'name': None,
                'env_name': 'distilled',
                'rule_name': 'OPT_LABEL_PATTERN',
                'structure_type': 'problem',
                '_start': m.start(),
                '_end': m.end(),
            })

    # ------------------------------------------------------------------
    # Pattern: OPEN_PROBLEM_LEAVE_PATTERN
    # Prose paragraph starting with "We leave ... open question(s)"
    # ------------------------------------------------------------------
    for m in OPEN_PROBLEM_LEAVE_PATTERN.finditer(text):
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
            'rule_name': 'OPEN_PROBLEM_LEAVE_PATTERN',
            'structure_type': 'open_problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Pattern: FUTURE_WORK_PATTERN
    # Prose paragraph: "We leave ... to/for future work"
    # ------------------------------------------------------------------
    for m in FUTURE_WORK_PATTERN.finditer(text):
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'FUTURE_WORK_PATTERN',
            'structure_type': 'open_problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Pattern: REMAIN_OPEN_PATTERN
    # Prose paragraph containing "remain(s) open" or "open question(s)"
#     # ------------------------------------------------------------------
#     for m in REMAIN_OPEN_PATTERN.finditer(text):
#         body = m.group('body').strip()
#         if len(body) < 80:
#             continue
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'REMAIN_OPEN_PATTERN',
#             'structure_type': 'open_problem',
#             '_start': m.start(),
#             '_end': m.end(),
#         })

    # ------------------------------------------------------------------
    # Pattern: OPEN_SECTION_HEADING_RE + interrogative paragraphs
    # Paragraphs with '?' inside open-problem/discussion/conclusion sections
    # ------------------------------------------------------------------
    for sec_m in OPEN_SECTION_HEADING_RE.finditer(text):
        sec_start = sec_m.end()
        # Find next section heading
        next_sec = re.search(r'\\(?:sub)*section\*?\{', text[sec_start:])
        sec_end = sec_start + next_sec.start() if next_sec else len(text)
        section_text = text[sec_start:sec_end]
        paragraphs = re.split(r'\n{2,}', section_text)
        pos = sec_start
        for para in paragraphs:
            stripped = para.strip()
            if '?' in stripped and len(stripped) >= 80:
                if not _inside_excluded_env(text, pos, pos + len(para)):
                    results.append({
                        'raw_latex': stripped,
                        'clean_text': _clean_latex(stripped),
                        'name': None,
                        'env_name': 'distilled',
                        'rule_name': 'OPEN_SECTION_HEADING_RE',
                        'structure_type': 'open_problem',
                        '_start': pos,
                        '_end': pos + len(para),
                    })
            pos += len(para) + 2

    # ------------------------------------------------------------------
    # Pattern: PROSE_PROBLEM_ENUM_PATTERN
    # Prose sentence mentioning "problem(s)" immediately before enumerate/itemize
    # ------------------------------------------------------------------
    for m in PROSE_PROBLEM_ENUM_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        leadin = m.group('leadin').strip()
        raw = leadin + '\n' + body
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_PROBLEM_ENUM_PATTERN',
            'structure_type': 'problem',
            '_start': m.start(),
            '_end': m.end(),
        })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    return _dedup(results)
