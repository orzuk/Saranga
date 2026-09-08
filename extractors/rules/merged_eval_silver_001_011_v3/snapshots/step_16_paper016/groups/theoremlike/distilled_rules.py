import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \cref{...}, \eqref{...}
    text = re.sub(r'\\(?:label|ref|cref|eqref|cite|citep|citet|labelcref)\{[^}]*\}', '', text)
    # Remove \textbf{...}, \emph{...}, \textit{...}, \text{...} but keep content
    text = re.sub(r'\\(?:textbf|emph|textit|textrm|textsc|text|mathrm|mathbf|mathit)\{([^}]*)\}', r'\1', text)
    # Remove display math environments but keep content
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}(.*?)\\end\{(?:equation|align|gather|multline)\*?\}',
                  r' \1 ', text, flags=re.DOTALL)
    # Remove inline math markers
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$.*?\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\{[^}]*\})*', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments whose interior we want to exclude matches from
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|note|exercise|Exercise)\}.*?\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if [start, end) falls entirely inside an excluded environment."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _determine_structure_type(env_name: str, fallback: str = 'theorem') -> str:
    """Map an environment name to a canonical structure_type."""
    normalized = re.sub(r'\*$', '', env_name.strip().lower())
    mapping = {
        'theorem': 'theorem',
        'thm': 'theorem',
        'theo': 'theorem',
        'lemma': 'lemma',
        'lem': 'lemma',
        'proposition': 'proposition',
        'prop': 'proposition',
        'property': 'proposition',
        'corollary': 'corollary',
        'cor': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem',
        'openproblem': 'open_problem',
        'openquestion': 'open_problem',
        'open_problem': 'open_problem',
        'open': 'open_problem',
    }
    return mapping.get(normalized, fallback)


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# --- Rule A: \begin{restatable}{<kind>}{<macro>} ... \end{restatable} ---
RESTATABLE_ENV_PATTERN = re.compile(
    r'\\begin\{restatable\s*\}'
    r'\s*\{(?P<kind>[^}]+)\}'
    r'\s*\{(?P<macro>[^}]*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{restatable\s*\}',
    flags=re.DOTALL | re.IGNORECASE
)

# --- Rule B: \begin{property} ... \end{property} (maps to proposition) ---
PROPERTY_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<envname>property|Property)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}',
    flags=re.DOTALL
)

# --- Rule C: equation/align environments with optimization objective + constraint ---
# Catches: \begin{align}...\max or \min ... \text{s.t.}...\end{align}
OPTIMIZATION_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<envname>align\*?|gather\*?|equation\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=envname)\}',
    flags=re.DOTALL | re.IGNORECASE
)
_OPT_OBJ_RE = re.compile(r'\\(?:max|min|inf|sup|argmin|argmax)\b', re.IGNORECASE)
_OPT_ST_RE = re.compile(
    r'\\text\s*\{\s*(?:s\.?\s*t\.?|subject\s+to)\s*\}'
    r'|\\mathrm\s*\{\s*s\.?\s*t\.?\s*\}'
    r'|\bsubject\s+to\b',
    re.IGNORECASE
)

# --- Rule D: Prose open-problem detection ---
# "We leave ... as (an) open question(s)/problem(s)"
PROSE_OPEN_LEAVE_PATTERN = re.compile(
    r'(?:^|(?<=\n\n))'
    r'(?P<body>'
    r'[A-Z][^\n]{0,600}?'
    r'\bwe\s+leave\b[^\n]{0,400}?'
    r'\bopen\s+(?:question|problem)s?\b'
    r'[^\n]*(?:\n(?!\n)[^\n]*)*'
    r')',
    flags=re.MULTILINE | re.IGNORECASE
)

# "remain(s) open" pattern
PROSE_REMAIN_OPEN_PATTERN = re.compile(
    r'(?:^|(?<=\n\n))'
    r'(?P<body>'
    r'[A-Z][^\n]{0,600}?'
    r'\bremains?\s+open\b'
    r'[^\n]*(?:\n(?!\n)[^\n]*)*'
    r')',
    flags=re.MULTILINE | re.IGNORECASE
)

# "leave ... to/for future work" pattern
PROSE_FUTURE_WORK_PATTERN = re.compile(
    r'(?:^|(?<=\n\n))'
    r'(?P<body>'
    r'[A-Z][^\n]{0,600}?'
    r'\bwe\s+leave\b[^\n]{0,300}?'
    r'\b(?:to|for)\s+future\s+work\b'
    r'[^\n]*(?:\n(?!\n)[^\n]*)*'
    r')',
    flags=re.MULTILINE | re.IGNORECASE
)

# Open problems paragraph inside discussion/conclusion/future-work sections
# that contain interrogative sentences
PROSE_OPEN_PROBLEM_SECTION_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*'
    r'(?:open\s*(?:problem|question)s?|discussion|conclusion|future\s*work|remark)'
    r'[^}]*\}'
    r'(?P<section_body>.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    flags=re.DOTALL | re.IGNORECASE
)

# An enumeration of problems introduced by a sentence containing 'problems' or 'problem'
PROSE_ENUMERATE_PROBLEM_PATTERN = re.compile(
    r'(?P<leadin>[^\n]*?\bproblems?\b[^\n]*)\n'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    flags=re.DOTALL | re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is fully contained in another result's raw_latex,
    and remove exact duplicates by (raw_latex, rule_name)."""
    seen = set()
    unique = []
    for r in results:
        key = (r['raw_latex'][:120], r['rule_name'])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    # Remove short results whose text is a substring of a longer result
    final = []
    all_raw = [r['raw_latex'] for r in unique]
    for i, r in enumerate(unique):
        dominated = False
        for j, other_raw in enumerate(all_raw):
            if i != j and r['raw_latex'] in other_raw and len(r['raw_latex']) < len(other_raw):
                dominated = True
                break
        if not dominated:
            final.append(r)
    return final


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # -----------------------------------------------------------------------
    # Rule A: restatable environments
    # -----------------------------------------------------------------------
    for m in RESTATABLE_ENV_PATTERN.finditer(text):
        kind_raw = m.group('kind').strip()
        structure_type = _determine_structure_type(kind_raw)
        # Only keep theorem-like subtypes
        if structure_type not in {'theorem', 'lemma', 'proposition', 'corollary',
                                   'claim', 'conjecture', 'problem', 'open_problem'}:
            continue
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        opt = m.group('opt')
        name = opt.strip() if opt else (m.group('macro').strip() or None)
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': 'RESTATABLE_ENV_PATTERN',
            'structure_type': structure_type,
        })

    # -----------------------------------------------------------------------
    # Rule B: property environments -> proposition
    # -----------------------------------------------------------------------
    for m in PROPERTY_ENV_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        opt = m.group('opt')
        name = opt.strip() if opt else None
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'PROPERTY_ENV_PATTERN',
            'structure_type': 'proposition',
        })

    # -----------------------------------------------------------------------
    # Rule C: equation/align environments that look like optimization problems
    # -----------------------------------------------------------------------
    for m in OPTIMIZATION_ENV_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        # Must have an optimization objective AND a constraint keyword
        if not (_OPT_OBJ_RE.search(body) and _OPT_ST_RE.search(body)):
            continue
        raw = m.group(0)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'OPTIMIZATION_ENV_PATTERN',
            'structure_type': 'problem',
        })

    # -----------------------------------------------------------------------
    # Rule D1: "we leave ... open question/problem" prose paragraphs
    # -----------------------------------------------------------------------
    for m in PROSE_OPEN_LEAVE_PATTERN.finditer(text):
        body = m.group('body').strip()
        if len(body) < 60:
            continue
        start = m.start()
        if _inside_excluded_env(text, start, start + len(body)):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_OPEN_LEAVE_PATTERN',
            'structure_type': 'open_problem',
        })

    # -----------------------------------------------------------------------
    # Rule D2: "remains open" prose paragraphs
    # -----------------------------------------------------------------------
    for m in PROSE_REMAIN_OPEN_PATTERN.finditer(text):
        body = m.group('body').strip()
        if len(body) < 60:
            continue
        start = m.start()
        if _inside_excluded_env(text, start, start + len(body)):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_REMAIN_OPEN_PATTERN',
            'structure_type': 'open_problem',
        })

    # -----------------------------------------------------------------------
    # Rule D3: "leave ... to/for future work" prose paragraphs
    # -----------------------------------------------------------------------
    for m in PROSE_FUTURE_WORK_PATTERN.finditer(text):
        body = m.group('body').strip()
        if len(body) < 60:
            continue
        start = m.start()
        if _inside_excluded_env(text, start, start + len(body)):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_FUTURE_WORK_PATTERN',
            'structure_type': 'open_problem',
        })

    # -----------------------------------------------------------------------
    # Rule D4: Open-problem section paragraphs containing interrogative sentences
    # -----------------------------------------------------------------------
    for sec_m in PROSE_OPEN_PROBLEM_SECTION_PATTERN.finditer(text):
        sec_body = sec_m.group('section_body')
        sec_start = sec_m.start('section_body')
        # Split section body into paragraphs
        paragraphs = re.split(r'\n{2,}', sec_body)
        pos = sec_start
        for para in paragraphs:
            stripped = para.strip()
            # Must contain at least one '?' and be of meaningful length
            if '?' in stripped and len(stripped) > 80:
                abs_start = pos
                abs_end = pos + len(para)
                if not _inside_excluded_env(text, abs_start, abs_end):
                    results.append({
                        'raw_latex': stripped,
                        'clean_text': _clean_latex(stripped),
                        'name': None,
                        'env_name': 'distilled',
                        'rule_name': 'PROSE_OPEN_PROBLEM_SECTION_PATTERN',
                        'structure_type': 'open_problem',
                    })
            pos += len(para) + 2  # +2 for the double-newline separator

    # -----------------------------------------------------------------------
    # Rule E: enumerate blocks introduced by a "problems" sentence
    # -----------------------------------------------------------------------
    for m in PROSE_ENUMERATE_PROBLEM_PATTERN.finditer(text):
        body = m.group('body').strip()
        leadin = m.group('leadin').strip()
        # Skip if the leadin looks like it's inside a proof or just mentions 'no problem'
        if re.search(r'\bno\s+problem\b|\bthese\s+problems\b|\bfollowing\s+problems\b',
                     leadin, re.IGNORECASE):
            # Still allow 'following problems' as a valid intro
            pass
        if len(body) < 60:
            continue
        start = m.start()
        if _inside_excluded_env(text, start, start + len(body)):
            continue
        full_raw = leadin + '\n' + body
        results.append({
            'raw_latex': full_raw,
            'clean_text': _clean_latex(full_raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROSE_ENUMERATE_PROBLEM_PATTERN',
            'structure_type': 'problem',
        })

    # -----------------------------------------------------------------------
    # Deduplicate and return
    # -----------------------------------------------------------------------
    return _deduplicate(results)
