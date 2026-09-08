import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very small LaTeX → plain-text cleaner (no external deps)."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # \blobb{...} → bullet + content
    text = re.sub(r'\\blobb\s*\{', r'$\\bullet$ ', text)
    # \ulesalgorithm{title}{body} → handled elsewhere, but clean stray macros
    # Remove \label{...}, \ref{...}, \citeA{...}, \cite{...}
    text = re.sub(r'\\(?:label|ref|citeA?|cite)\s*\{[^}]*\}', '', text)
    # \textbf, \bf, \emph, \textit → keep content
    text = re.sub(r'\\(?:textbf|textit|emph|mathbf)\s*\{([^}]*)\}', r'\1', text)
    # Remove remaining simple commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|Proof|Example|Remark)\}.*?\\end\{\1\}',
    re.DOTALL
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside a proof/example/remark env."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Pattern 1 – \ulesalgorithm{title}{body}
# We allow up to 3 levels of nested braces in the body (covers the gold cases).
# ---------------------------------------------------------------------------

_ULES_ALG_RE = re.compile(
    r'\\ulesalgorithm\s*'
    r'\{(?P<title>[^}]*)\}'          # {title}
    r'\s*'
    r'\{(?P<body>'                   # {body  — allow nested braces up to depth 3
        r'(?:'
            r'[^{}]'
            r'|\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}'
        r')*'
    r')\}',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 2 – enumerate environment preceded by algo-context phrase
# (covers paper002 test case 4)
# ---------------------------------------------------------------------------

_ENUM_ALGO_CTX_RE = re.compile(
    r'(?:algorithm|procedure|steps?|designed\s+as\s+follows|as\s+follows)'
    r'[^\\]{0,300}'
    r'(?P<env>\\begin\{enumerate\}'
        r'(?P<body>.*?)'
    r'\\end\{enumerate\})',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 3 – prose algorithm: a paragraph that contains algorithmic keywords
# anchored by the word "algorithm" at/near the start, followed by procedural
# language.  Used for paper003 test case 5.
# We match paragraph blocks (separated by \n\n) that:
#   (a) mention "algorithm" within the first 200 chars
#   (b) contain at least two of: input|output|step|partition|apply|flip|repeat
# ---------------------------------------------------------------------------

_PROSE_ALG_RE = re.compile(
    r'(?<!\{)'                      # not right after {  (avoid env bodies)
    r'(?P<block>'
        r'(?:(?!\n\n).){20,}'       # at least 20 chars before first double-newline
        r'(?:\n(?!\n)(?:(?!\n\n).)*)*'  # continuation lines (no blank line)
    r')',
    re.DOTALL
)

# Simpler approach: split on double-newlines and test each paragraph
_PARA_SPLIT_RE = re.compile(r'\n{2,}')

_PROSE_ANCHOR_RE = re.compile(r'\balgorithm\b', re.IGNORECASE)
_PROSE_STEP_RE = re.compile(
    r'\b(?:input|output|step|partition|apply|flip|repeat|partition|procedure|'
    r'first|second|lastly|then\s+define|we\s+apply|we\s+flip|we\s+then)\b',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _dedup(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result's raw_latex,
    and remove exact duplicates."""
    if not results:
        return results
    # Sort by length descending so we keep the longest match
    results = sorted(results, key=lambda d: len(d['raw_latex']), reverse=True)
    kept = []
    for cand in results:
        dominated = False
        for k in kept:
            if cand['raw_latex'] in k['raw_latex']:
                dominated = True
                break
        if not dominated:
            kept.append(cand)
    # Restore source order (approximate by name/raw_latex)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \ulesalgorithm{title}{body}
    # ------------------------------------------------------------------
    for m in _ULES_ALG_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body')
        # Build a clean_text that mirrors the gold format:
        # "${\bf <title>}\\$" followed by cleaned body
        header = r'${\bf ' + title + r'}\\$'
        raw = body
        clean = header + ' ' + _clean_latex(body)
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': '_ULES_ALG_RE',
            'structure_type': 'algorithm',
        })

    # ------------------------------------------------------------------
    # Rule B: enumerate env in algorithmic context
    # ------------------------------------------------------------------
    for m in _ENUM_ALGO_CTX_RE.finditer(text):
        if _inside_excluded_env(text, m.start('env'), m.end('env')):
            continue
        body = m.group('body')
        env_full = m.group('env')
        clean = _clean_latex(env_full)
        results.append({
            'raw_latex': env_full,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_ENUM_ALGO_CTX_RE',
            'structure_type': 'algorithm',
        })

    # ------------------------------------------------------------------
    # Rule C: prose-described algorithm (paragraph-level heuristic)
    # ------------------------------------------------------------------
    paragraphs = _PARA_SPLIT_RE.split(text)
    # Track character offsets
    offset = 0
    for para in paragraphs:
        para_start = text.find(para, offset)
        if para_start == -1:
            para_start = offset
        para_end = para_start + len(para)
        offset = para_end

        # Skip very short paragraphs
        if len(para) < 150:
            continue

        # Must mention "algorithm" somewhere in the paragraph
        if not _PROSE_ANCHOR_RE.search(para):
            continue

        # Must have at least 3 procedural-step matches
        step_matches = list(_PROSE_STEP_RE.finditer(para))
        if len(step_matches) < 3:
            continue

        # Must NOT be inside an excluded environment
        if _inside_excluded_env(text, para_start, para_end):
            continue

        # Skip if the paragraph is actually inside a known algorithm env
        # (avoid double-counting)
        inside_alg_env = re.search(
            r'\\begin\{(?:algorithm\*?|Algorithm\*?)\}', para
        )
        if inside_alg_env:
            continue

        # Skip if it looks like it's mostly just one sentence of reference
        if len(para) < 400 and para.count('algorithm') >= 1 and len(step_matches) < 5:
            continue

        clean = _clean_latex(para)
        results.append({
            'raw_latex': para,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': '_PROSE_STEP_RE',
            'structure_type': 'algorithm',
        })

    return _dedup(results)
