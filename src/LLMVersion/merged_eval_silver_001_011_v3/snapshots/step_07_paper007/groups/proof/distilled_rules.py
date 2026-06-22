import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text conversion (no external deps)."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common display-math environments
    text = re.sub(r'\\begin\{(equation|align|aligned|gather|multline)\*?\}.*?\\end\{\1\*?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', ' ', text)
    # Remove common commands but keep their arguments
    text = re.sub(r'\\(?:emph|textbf|textit|textsc|text|mathrm|mathbf|mathit)\{([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(\{[^}]*\})*', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose interior we want to exclude from outer matches
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|theorem|lemma|proposition|corollary|definition|example|remark)\}',
    re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is nested inside an excluded environment."""
    # Walk all excluded env openings that come before `start`
    for m in _EXCLUDED_ENVS.finditer(text, 0, start):
        env_name = m.group(1)
        closing = re.search(r'\\end\{' + re.escape(env_name) + r'\}', text[m.end():], re.IGNORECASE)
        if closing:
            env_end = m.end() + closing.end()
            if env_end > start:
                return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1 – \section or \subsection whose title begins with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\s*\*?\s*\{(?P<title>[Pp]roof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\s*\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL
)

# Rule 2 – {\sc Proof ...}. or \textsc{Proof ...}.
SC_PROOF_PATTERN = re.compile(
    r'(?:'
        r'\{\\sc\s+(?P<title1>[Pp]roof[^}]*)\}'
        r'|'
        r'\\textsc\{(?P<title2>[Pp]roof[^}]*)\}'
    r')'
    r'[.:\s]*'
    r'(?P<body>.*?)'
    r'(?=\\section|\\subsection|\\appendix|\\begin\{|\{\\sc\s+[Pp]roof|\\textsc\{[Pp]roof|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3 – standalone \emph{Proof ...} at paragraph start
STANDALONE_EMPH_PROOF_PATTERN = re.compile(
    r'(?:(?:^|\n\n|\r\n\r\n)[ \t]*)'
    r'\\emph\{(?P<title>[Pp]roof[^}]*)\}'
    r'[.:\s]*'
    r'(?P<body>.*?)'
    r'(?:'
        r'\\(?:blacksquare|square|qed)\b'
        r'|\$\s*\\(?:blacksquare|square|qed)\s*\$'
        r'|\\end\{(?:aligned|equation\*?|align\*?|gather\*?)\}\s*\$\$'
        r'|\\begin\{'
        r'|\\(?:section|subsection|subsubsection)\b'
        r'|\\end\{document\}'
        r'|\Z'
    r')',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Header-ref helper (mirror of base parser)
# ---------------------------------------------------------------------------
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    results: List[dict] = []
    seen_bodies: set = set()

    def _add(raw: str, name, rule_name: str):
        raw = raw.strip()
        if not raw or raw in seen_bodies:
            return
        seen_bodies.add(raw)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'proof',
        })

    # -----------------------------------------------------------------------
    # Rule 1 – section/subsection titled "Proof of ..."
    # -----------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, title if title else None, 'SUBSECTION_PROOF_PATTERN')

    # -----------------------------------------------------------------------
    # Rule 2 – {\sc Proof ...}. or \textsc{Proof ...}.
    # -----------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title1') or m.group('title2')
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, title.strip() if title else None, 'SC_PROOF_PATTERN')

    # -----------------------------------------------------------------------
    # Rule 3 – standalone \emph{Proof ...} paragraph
    # -----------------------------------------------------------------------
    for m in STANDALONE_EMPH_PROOF_PATTERN.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        _add(body, title if title else None, 'STANDALONE_EMPH_PROOF_PATTERN')

    # -----------------------------------------------------------------------
    # Deduplicate by overlap: keep only non-overlapping matches
    # (already handled by seen_bodies for identical text; structural
    # overlaps are inherently rare given the distinct anchors)
    # -----------------------------------------------------------------------
    return results
