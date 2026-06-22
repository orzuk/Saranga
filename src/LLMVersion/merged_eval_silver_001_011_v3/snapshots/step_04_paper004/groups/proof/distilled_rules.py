import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section or \subsection whose title begins with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:(?:sub){0,2}section)\s*\*?\s*\{[^}]*[Pp]roof[^}]*\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:(?:sub){0,2}section)\s*\*?\s*\{|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL,
)

# Rule 2: {\sc Proof...} or \textsc{Proof...} informal proof header
SC_PROOF_PATTERN = re.compile(
    r'(?:'
    r'\{\\sc\s+[Pp]roof[^}]*\}'
    r'|'
    r'\\textsc\{[Pp]roof[^}]*\}'
    r')'
    r'\.?\s*'
    r'(?P<body>.*?)'
    r'(?='
    r'\\(?:(?:sub){0,2}section)\s*\*?\s*\{'
    r'|\\appendix'
    r'|\\begin\s*\{'
    r'|\{\\sc\s+[Pp]roof'
    r'|\\textsc\{[Pp]roof'
    r'|\\end\s*\{\s*document\s*\}'
    r'|\Z'
    r')',
    re.DOTALL,
)

# Environments to exclude (we don't want to re-extract from inside these)
_EXCLUDED_ENVS = re.compile(
    r'\\begin\s*\{\s*(?:proof|Proof|verbatim|lstlisting|comment)\s*\}',
    re.DOTALL,
)

_LATEX_CMD = re.compile(
    r'\\(?:label|ref|eqref|cite|bibitem|index)\{[^}]*\}'
    r'|\\[a-zA-Z]+'
    r'|\{|\}'
    r'|~'
)

_WHITESPACE = re.compile(r'\s+')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very lightweight LaTeX → plain-text conversion."""
    t = _LATEX_CMD.sub(' ', text)
    t = _WHITESPACE.sub(' ', t)
    return t.strip()


def _build_excluded_ranges(text: str):
    """
    Return a list of (start, end) ranges that are inside excluded environments
    (proof, verbatim, etc.).  We use a simple begin/end scanner.
    """
    ranges = []
    env_pattern = re.compile(
        r'\\begin\s*\{\s*(?P<env>proof|Proof|verbatim|lstlisting|comment)\s*\}'
        r'.*?'
        r'\\end\s*\{\s*(?P=env)\s*\}',
        re.DOTALL,
    )
    for m in env_pattern.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def _inside_excluded_env(start: int, end: int, excluded_ranges) -> bool:
    """Return True if [start, end) overlaps any excluded range."""
    for (es, ee) in excluded_ranges:
        if start < ee and end > es:
            return True
    return False


def _overlaps(start: int, end: int, seen: list) -> bool:
    """Return True if [start, end) substantially overlaps any already-seen span."""
    for (ss, se) in seen:
        overlap = min(end, se) - max(start, ss)
        if overlap > 50:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[Dict]:
    results: List[Dict] = []
    excluded_ranges = _build_excluded_ranges(text)
    seen_spans: list = []  # list of (start, end) for deduplication
    seen_bodies: set = set()

    # -----------------------------------------------------------------------
    # Rule 1: Section/subsection titled "Proof of ..."
    # -----------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _overlaps(start, end, seen_spans):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        if body in seen_bodies:
            continue

        # Extract optional name from section title
        title_match = re.search(
            r'\\(?:(?:sub){0,2}section)\s*\*?\s*\{([^}]*)\}',
            m.group(0),
        )
        name = title_match.group(1).strip() if title_match else None

        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })
        seen_spans.append((start, end))
        seen_bodies.add(body)

    # -----------------------------------------------------------------------
    # Rule 2: {\sc Proof...} or \textsc{Proof...} informal header
    # -----------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(start, end, excluded_ranges):
            continue
        if _overlaps(start, end, seen_spans):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        if body in seen_bodies:
            continue

        # Try to extract a name from the {\sc Proof of ...} header
        header_match = re.search(
            r'(?:\{\\sc\s+|\\textsc\{)([^}]+)\}',
            m.group(0),
        )
        name = header_match.group(1).strip() if header_match else None

        clean = _clean_latex(body)
        results.append({
            'raw_latex': body,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
        })
        seen_spans.append((start, end))
        seen_bodies.add(body)

    return results
