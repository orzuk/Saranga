import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section or \subsection whose title starts with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\s*\*?\s*\{[^}]*\bProof[^}]*\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule 2: {\sc Proof ...} or \textsc{Proof ...} style header
SC_PROOF_PATTERN = re.compile(
    r'(?:\{\\sc\s+Proof[^}]*\}|\\textsc\{Proof[^}]*\})\.?\s*'
    r'(.*?)'
    r'(?=\\section|\\subsection|\\appendix|\{\\sc\s+Proof|\\textsc\{Proof'
    r'|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3: standalone \emph{Proof ...} not preceded by \par\noindent
STANDALONE_EMPH_PROOF_PATTERN = re.compile(
    r'\\emph\{Proof[^}]*\}'
    r'[.:]?\s*'
    r'(.*?)'
    r'(?:'
        r'\\(?:blacksquare|square|qed)'
        r'|(?:\\end\{(?:aligned|align\*?|equation\*?|gather\*?)\}\s*\$\$)'
        r'|\\begin\{'
        r'|\\(?:section|subsection|subsubsection)\s*[\*{]'
        r'|\\end\{document\}'
        r'|\Z'
    r')',
    re.DOTALL
)

# Excluded environments — matches inside these are skipped
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|theorem|Theorem'
    r'|lemma|Lemma|proposition|Proposition|corollary|Corollary)\}',
    re.DOTALL
)

# Header \ref pattern to extract target theorem label
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')

# Simple latex cleaner — strips common commands for clean_text
_LATEX_CMD_RE = re.compile(
    r'\\(?:label|ref|eqref|autoref|cite|textbf|textit|emph|text'
    r'|mathbf|mathit|mathrm|mathbb|mathcal|mathsf|operatorname'
    r'|left|right|big|Big|bigg|Bigg'
    r'|quad|qquad|noindent|par|newline|hspace|vspace'
    r')\s*(?:\{[^}]*\})?'
)
_DISPLAY_MATH_RE = re.compile(r'\$\$.*?\$\$|\\\[.*?\\\]', re.DOTALL)
_INLINE_MATH_RE = re.compile(r'\$[^$]*\$')
_LATEX_ENV_RE = re.compile(r'\\(?:begin|end)\{[^}]*\}')
_LATEX_GENERIC_CMD_RE = re.compile(r'\\[A-Za-z]+\*?(?:\{[^}]*\})*')
_WHITESPACE_RE = re.compile(r'\s+')


def _clean_latex(text: str) -> str:
    """Minimal LaTeX → plain-text conversion."""
    t = _DISPLAY_MATH_RE.sub(' [math] ', text)
    t = _INLINE_MATH_RE.sub(' [math] ', t)
    t = _LATEX_CMD_RE.sub(' ', t)
    t = _LATEX_ENV_RE.sub(' ', t)
    t = _LATEX_GENERIC_CMD_RE.sub(' ', t)
    t = t.replace('{', '').replace('}', '')
    t = _WHITESPACE_RE.sub(' ', t)
    return t.strip()


def _build_excluded_spans(text: str) -> List[tuple]:
    """
    Return list of (start, end) spans for known proof/theorem/example/remark
    environments so we can skip matches that fall inside them.
    """
    spans = []
    env_re = re.compile(
        r'\\begin\{(proof|Proof|example|Example|remark|Remark'
        r'|theorem|Theorem|lemma|Lemma|proposition|Proposition'
        r'|corollary|Corollary)\}'
        r'.*?'
        r'\\end\{\1\}',
        re.DOTALL
    )
    for m in env_re.finditer(text):
        spans.append((m.start(), m.end()))
    return spans


def _inside_excluded_env(start: int, end: int, excluded_spans: List[tuple]) -> bool:
    """Return True if [start, end) overlaps any excluded span."""
    for es, ee in excluded_spans:
        if start >= es and end <= ee:
            return True
        # partial overlap also excluded
        if start < ee and end > es:
            return True
    return False


def _overlaps_existing(start: int, end: int, seen: List[tuple]) -> bool:
    for ss, se in seen:
        if start < se and end > ss:
            return True
    return False


def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures missed by the base parser:
      1. \\section/\\subsection{Proof of ...} blocks
      2. {\\sc Proof ...} or \\textsc{Proof ...} style headers
      3. Standalone \\emph{Proof ...} paragraphs

    Returns list of dicts with keys:
      raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    excluded_spans = _build_excluded_spans(text)
    seen_spans: List[tuple] = []

    # ------------------------------------------------------------------
    # Rule 1: \(sub)*section{Proof of ...} body
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        start, end = m.start(), m.end()
        if _inside_excluded_env(start, end, excluded_spans):
            continue
        if _overlaps_existing(start, end, seen_spans):
            continue
        seen_spans.append((start, end))
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof ...}. body  or  \textsc{Proof ...}. body
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        body = m.group(1).strip()
        if not body:
            continue
        start, end = m.start(), m.end()
        if _inside_excluded_env(start, end, excluded_spans):
            continue
        if _overlaps_existing(start, end, seen_spans):
            continue
        seen_spans.append((start, end))
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 3: \emph{Proof ...} standalone (NOT preceded by \par\noindent)
    # ------------------------------------------------------------------
    # Collect positions already matched by the \par\noindent\emph{Proof} style
    # (approximation: any \emph{Proof} directly after \par\noindent)
    par_noindent_re = re.compile(
        r'\\par\s*\\noindent\s*\\emph\{Proof[^}]*\}',
        re.IGNORECASE
    )
    par_noindent_positions = set()
    for m in par_noindent_re.finditer(text):
        par_noindent_positions.add(m.start())

    for m in STANDALONE_EMPH_PROOF_PATTERN.finditer(text):
        body = m.group(1).strip()
        if not body:
            continue
        start, end = m.start(), m.end()

        # Skip if this is actually a \par\noindent\emph{Proof} match
        # (covered by base parser).  We check if any par_noindent match
        # is within 60 chars before our match start.
        skip = False
        for pos in par_noindent_positions:
            if 0 <= start - pos <= 60:
                skip = True
                break
        if skip:
            continue

        if _inside_excluded_env(start, end, excluded_spans):
            continue
        if _overlaps_existing(start, end, seen_spans):
            continue

        # Extract optional header name from \emph{Proof...}
        header_match = re.match(r'\\emph\{(Proof[^}]*)\}', text[start:])
        name = header_match.group(1).strip() if header_match else None

        # Try to find target theorem label in the header
        extra: Dict[str, str] = {}
        if header_match:
            hr = _HEADER_REF_PATTERN.search(header_match.group(1))
            if hr:
                extra['_target_theorem_label'] = hr.group(1)

        seen_spans.append((start, end))
        entry = {
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'STANDALONE_EMPH_PROOF_PATTERN',
            'structure_type': 'proof',
        }
        entry.update(extra)
        results.append(entry)

    return results
