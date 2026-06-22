import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section or \subsection whose title begins with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:(?:sub){0,2}section)\s*\*?\s*\{[^}]*\bProof\b[^}]*\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:(?:sub){0,2}section)\s*\*?\s*\{|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Rule 2: {\sc Proof ...} or \textsc{Proof ...} informal proof headers
SC_PROOF_PATTERN = re.compile(
    r'(?:'
    r'\{\\sc\s+Proof[^}]*\}'
    r'|\\textsc\{Proof[^}]*\}'
    r')'
    r'\.?\s*'
    r'(?P<body>.*?)'
    r'(?='
    r'\\(?:sub)*section'
    r'|\\appendix'
    r'|\\begin\s*\{'
    r'|\{\\sc\s+Proof'
    r'|\\textsc\{Proof'
    r'|\\end\s*\{\s*document\s*\}'
    r'|\Z'
    r')',
    re.DOTALL,
)

# Rule 3: standalone \emph{Proof ...} at paragraph start
STANDALONE_EMPH_PROOF_PATTERN = re.compile(
    r'(?:(?:\A|\n[ \t]*\n)[ \t]*)'
    r'(?P<header>\\emph\{Proof[^}]*\})'
    r'[.:]?\s*'
    r'(?P<body>.*?)'
    r'(?='
    r'\\(?:blacksquare|square|qed)\b'
    r'|\\end\s*\{\s*(?:aligned|equation\*?|align\*?|gather\*?)\s*\}\s*\$\$'
    r'|\\begin\s*\{'
    r'|\\(?:sub)*section\b'
    r'|\\end\s*\{\s*document\s*\}'
    r'|\Z'
    r')',
    re.DOTALL,
)

# Environments to exclude (proof bodies must not come from inside these)
_EXCLUDED_ENVS = re.compile(
    r'\\begin\s*\{(proof|Proof|theorem|lemma|proposition|corollary|example|remark)\*?\}',
    re.IGNORECASE,
)

_CLEAN_CMD = re.compile(
    r'\\(?:label|ref|cite|eqref|autoref|footnote|textbf|textit|emph|mathrm|mathbf'
    r'|mathit|mathcal|mathbb|text|mbox|hbox|vspace|hspace|noindent|medskip'
    r'|smallskip|bigskip|newline|linebreak|centering|raggedright|raggedleft'
    r'|normalsize|small|large|Large|tiny|scriptsize|footnotesize|normalfont'
    r'|rm|bf|it|tt|sf|sc)\b'
    r'\s*(?:\[[^\]]*\])?\s*(?:\{([^{}]*)\})?',
    re.DOTALL,
)
_CLEAN_MATH_DISPLAY = re.compile(r'\$\$.*?\$\$|\\\[.*?\\\]', re.DOTALL)
_CLEAN_MATH_INLINE = re.compile(r'\$[^$]*\$|\\\(.*?\\\)', re.DOTALL)
_CLEAN_BRACES = re.compile(r'\{([^{}]*)\}')
_CLEAN_BACKSLASH = re.compile(r'\\[a-zA-Z@]+\s*')
_CLEAN_WHITESPACE = re.compile(r'\s+')


def _clean_latex(text: str) -> str:
    """Convert LaTeX source to approximate plain text."""
    t = _CLEAN_MATH_DISPLAY.sub(' [MATH] ', text)
    t = _CLEAN_MATH_INLINE.sub(' [MATH] ', t)
    # Replace known commands, keeping their argument text where present
    def _cmd_repl(m):
        inner = m.group(1)
        return (' ' + inner + ' ') if inner else ' '
    t = _CLEAN_CMD.sub(_cmd_repl, t)
    # Strip remaining braces keeping content
    for _ in range(5):
        t = _CLEAN_BRACES.sub(r'\1', t)
    t = _CLEAN_BACKSLASH.sub(' ', t)
    t = _CLEAN_WHITESPACE.sub(' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) sits inside an excluded environment."""
    prefix = text[:start]
    for m in _EXCLUDED_ENVS.finditer(prefix):
        env = m.group(1)
        close_pat = re.compile(
            r'\\end\s*\{\s*' + re.escape(env) + r'\s*\}',
            re.IGNORECASE,
        )
        close = close_pat.search(text, m.end())
        if close and close.start() >= end:
            return True
    return False


def _overlaps(new_start: int, new_end: int, seen: List[tuple]) -> bool:
    for (s, e) in seen:
        if new_start < e and new_end > s:
            return True
    return False


def extract_distilled_proof(text: str) -> List[dict]:
    results: List[dict] = []
    seen_spans: List[tuple] = []
    # track bodies to avoid exact duplicates
    seen_bodies: set = set()

    # ------------------------------------------------------------------
    # Rule 1 – section/subsection titled "Proof of ..."
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, seen_spans):
            continue
        body = m.group('body').strip()
        if not body or body in seen_bodies:
            continue
        seen_spans.append((start, end))
        seen_bodies.add(body)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 2 – {\sc Proof ...} or \textsc{Proof ...} headers
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, seen_spans):
            continue
        body = m.group('body').strip()
        if not body or body in seen_bodies:
            continue
        seen_spans.append((start, end))
        seen_bodies.add(body)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 3 – standalone \emph{Proof ...} at paragraph start
    # ------------------------------------------------------------------
    for m in STANDALONE_EMPH_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, seen_spans):
            continue
        body = m.group('body').strip()
        if not body or body in seen_bodies:
            continue
        # Extract optional name from the \emph{Proof ...} header
        header = m.group('header')
        name_m = re.match(r'\\emph\{Proof\s+(?:of\s+)?([^}]+)\}', header, re.IGNORECASE)
        name = name_m.group(1).strip() if name_m else None
        seen_spans.append((start, end))
        seen_bodies.add(body)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'STANDALONE_EMPH_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    return results
