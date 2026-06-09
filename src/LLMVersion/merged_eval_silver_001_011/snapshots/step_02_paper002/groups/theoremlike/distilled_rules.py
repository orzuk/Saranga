import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX markup, leaving readable text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite... etc.
    text = re.sub(r'\\(label|ref|eqref|cite[A-Za-z]*|citeNP|citeA)\{[^}]*\}', '', text)
    # Remove \begin{...} / \end{...}
    text = re.sub(r'\\(begin|end)\{[^}]*\}', '', text)
    # Remove display math environments markers
    text = re.sub(r'\\(ba|ea|bb|eb)\b', '', text)
    # Replace \\ with space
    text = re.sub(r'\\\\', ' ', text)
    # Remove & alignment markers
    text = re.sub(r'&', ' ', text)
    # Collapse remaining lone backslash-commands (keep their argument if any)
    text = re.sub(r'\\[A-Za-z*]+\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[A-Za-z*]+', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Normalise whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments whose content we must NOT treat as theorem-like
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|exam|ex|remark|Remark|rem|note)\}',
    re.DOTALL
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start,end) is inside a proof/example/remark env."""
    # Find all excluded env opens before 'start'
    for m in _EXCLUDED_ENV_RE.finditer(text, 0, start):
        env = m.group(1)
        close_pat = re.compile(
            r'\\end\{' + re.escape(env) + r'\}',
            re.DOTALL
        )
        cm = close_pat.search(text, m.end())
        if cm and cm.start() >= end:
            return True
        if cm and cm.start() < start:
            continue
        if not cm:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: \ba...\ea blocks preceded by a problem-signalling preamble
# (free-text problems in paper001)
# PRUNED — FP on paper001 | also 5 TP — review before uncommenting
# FREETEXT_BA_EA_PROBLEM = re.compile(
#     r'(?<!\$)(?<!\w)'           # not inside math
#     r'(?P<preamble>'
#     r'(?:[^\n]|\n(?!\n)){30,800}?'   # non-blank lines forming the preamble
#     r'(?:mincut|partition|cut|objective function|cluster|RatioCut|Ratiocut|Ncut|MinmaxCut|'
#     r'minimize|minimizes|criterion|approach|consists in|defined as|definitions are)'
#     r'[^\n]{0,400}?'
#     r')\s*\n?\s*%?\s*\n?\s*'   # optional comment/whitespace bridge
#     r'\\ba\s*(?P<body>.*?)\\ea',
#     re.DOTALL | re.IGNORECASE
# )

# Pattern 2: equation environments containing (P_N) problem definitions
EQUATION_PROBLEM = re.compile(
    r'\\begin\{(?P<env>equation\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'\s*(?P<body>.*?\(P[_0-9A-Za-z]*\).*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)

# Pattern 3: align/align* environments containing (P_N) problem definitions
ALIGN_PROBLEM = re.compile(
    r'\\begin\{(?P<env>align\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'\s*(?P<body>.*?\(P[_0-9A-Za-z]*\).*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)

# Pattern 4: align* environments with eigenvalue/RMT content (paper002 theorem)
ALIGN_STAR_THEOREM = re.compile(
    r'\\begin\{(?P<env>align\*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'\s*(?P<body>.*?(?:\\lambda|\\goto|eigenval|isometry)[^\\]*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)

# Pattern 5: align environments with eigenvalue/RMT content (paper002 theorem)
ALIGN_THEOREM = re.compile(
    r'\\begin\{(?P<env>align\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'\s*(?P<body>.*?(?:\\lambda_\{\\min\}|\\lambda_\{\\max\}|\\goto)[^\\]*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Subtype resolution
# ---------------------------------------------------------------------------

_SUBTYPE_MAP = {
    'theorem': 'theorem',
    'thm': 'theorem',
    'theo': 'theorem',
    'lemma': 'lemma',
    'lem': 'lemma',
    'proposition': 'proposition',
    'prop': 'proposition',
    'corollary': 'corollary',
    'cor': 'corollary',
    'claim': 'claim',
    'conjecture': 'conjecture',
    'problem': 'problem',
    'openproblem': 'problem',
}

def _resolve_subtype(env_name: str, body: str) -> str:
    key = env_name.rstrip('*').lower()
    if key in _SUBTYPE_MAP:
        return _SUBTYPE_MAP[key]
    # Try to detect from body/preamble text
    for word, subtype in [
        ('theorem', 'theorem'), ('lemma', 'lemma'),
        ('proposition', 'proposition'), ('corollary', 'corollary'),
        ('claim', 'claim'), ('conjecture', 'conjecture'),
        ('problem', 'problem'),
    ]:
        if re.search(r'\b' + word + r'\b', body, re.IGNORECASE):
            return subtype
    return 'theorem'


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex span overlaps a previously accepted one."""
    kept = []
    for r in sorted(results, key=lambda x: x.get('_start', 0)):
        start = r.get('_start', 0)
        end = r.get('_end', start + len(r['raw_latex']))
        overlaps = False
        for k in kept:
            ks = k.get('_start', 0)
            ke = k.get('_end', ks + len(k['raw_latex']))
            if start < ke and end > ks:
                overlaps = True
                break
        if not overlaps:
            kept.append(r)
    # Remove internal keys before returning
    for r in kept:
        r.pop('_start', None)
        r.pop('_end', None)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: Free-text \ba...\ea problems (paper001 style)
#     # ------------------------------------------------------------------
#     for m in FREETEXT_BA_EA_PROBLEM.finditer(text):
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         preamble = m.group('preamble').strip()
#         body = m.group('body').strip()
#         raw = preamble + '\n' + body
#         clean = _clean_latex(raw)
#         results.append({
#             'raw_latex': raw,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'FREETEXT_BA_EA_PROBLEM',
#             'structure_type': 'problem',
#             '_start': start,
#             '_end': end,
#         })

    # ------------------------------------------------------------------
    # Rule B: equation environments with (P_N) — problems (paper002)
    # ------------------------------------------------------------------
    for m in EQUATION_PROBLEM.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        raw = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'EQUATION_PROBLEM',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule C: align/align* environments with (P_N) — problems (paper002)
    # ------------------------------------------------------------------
    for m in ALIGN_PROBLEM.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        raw = m.group(0)
        clean = _clean_latex(body)
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'ALIGN_PROBLEM',
            'structure_type': 'problem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule D: align* environments with eigenvalue content — theorems (paper002)
    # ------------------------------------------------------------------
    for m in ALIGN_STAR_THEOREM.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        raw = m.group(0)
        clean = _clean_latex(body)
        # Only emit if body is not also matched as a problem
        if re.search(r'\(P[_0-9A-Za-z]*\)', body):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'ALIGN_STAR_THEOREM',
            'structure_type': 'theorem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule E: align environments with lambda_min/lambda_max/goto content
    # ------------------------------------------------------------------
    for m in ALIGN_THEOREM.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        raw = m.group(0)
        clean = _clean_latex(body)
        # Skip if already a problem match
        if re.search(r'\(P[_0-9A-Za-z]*\)', body):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'ALIGN_THEOREM',
            'structure_type': 'theorem',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    return _deduplicate(results)
