import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section or \subsection (with any level of 'sub') whose title
# begins with the word "Proof" (case-insensitive).  Body runs until the
# next sectioning command or \end{document}.
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\s*\*?\s*\{[^}]*\bProof\b[^}]*\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Rule 2: {\sc Proof ...} or \textsc{Proof ...} style header (small-caps).
SC_PROOF_PATTERN = re.compile(
    r'(?:'
    r'\{\\sc\s+Proof[^}]*\}'
    r'|\\textsc\{Proof[^}]*\}'
    r')'
    r'\.?\s*'
    r'(?P<body>.*?)'
    r'(?='
    r'\\section|\\subsection|\\appendix'
    r'|\{\\sc\s+Proof|\\textsc\{Proof'
    r'|\\begin\{'
    r'|\\end\{document\}'
    r'|\Z'
    r')',
    re.DOTALL,
)

# Rule 3: standalone \emph{Proof ...} at the start of a paragraph.
# Body ends at a QED marker, next display math block end, next environment,
# next sectioning command, or end of document.
STANDALONE_EMPH_PROOF_PATTERN = re.compile(
    r'(?:(?:\A|\n[ \t]*\n)[ \t]*)'        # start of text or blank-line paragraph break
    r'(?P<header>\\emph\{Proof[^}]*\})'    # \emph{Proof} or \emph{Proof of ...}
    r'[.:]?\s*'
    r'(?P<body>.*?)'
    r'(?:'
    r'\\(?:blacksquare|square|qed)'
    r'|\\end\{(?:aligned|align\*?|equation\*?|gather\*?)\}\s*\$\$'
    r'|\\begin\{'
    r'|\\(?:section|subsection|subsubsection)'
    r'|\\end\{document\}'
    r'|\Z'
    r')',
    re.DOTALL,
)

# Environments to exclude (proof bodies that live inside these are already
# handled by the base extractor).
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|theorem|Theorem'
    r'|lemma|Lemma|proposition|Proposition|corollary|Corollary)\}',
    re.IGNORECASE,
)

_LATEX_CMD_PATTERN = re.compile(
    r'\\(?:'
    r'(?:text(?:bf|it|rm|sc|sf|tt|normal)|mathrm|mathbf|mathit|mathcal'
    r'|mathbb|mathfrak|emph|underline|overline|widehat|widetilde'
    r'|hat|tilde|bar|vec|dot|ddot|acute|grave|check|breve|label'
    r'|ref|eqref|autoref|cite|citep|citet|footnote|footnotetext'
    r'|caption|index|vspace|hspace|vskip|hskip|noindent|medskip'
    r'|bigskip|smallskip|newline|linebreak|pagebreak|centering'
    r'|raggedright|raggedleft|normalsize|small|large|Large|LARGE'
    r'|huge|Huge|tiny|scriptsize|footnotesize|normalfont)'
    r')\{([^}]*)\}'
    r'|\\[a-zA-Z]+'
    r'|\\[^a-zA-Z]',
    re.DOTALL,
)

_DISPLAY_MATH_PATTERN = re.compile(
    r'\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{(?:equation|align|gather|multline)'
    r'\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}',
    re.DOTALL,
)

_INLINE_MATH_PATTERN = re.compile(r'\$[^$\n]+?\$')

_WHITESPACE_PATTERN = re.compile(r'\s+')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Best-effort conversion of LaTeX snippet to plain text."""
    # Remove display math
    text = _DISPLAY_MATH_PATTERN.sub(' [MATH] ', text)
    # Remove inline math
    text = _INLINE_MATH_PATTERN.sub(' [MATH] ', text)
    # Strip LaTeX commands but keep their arguments where sensible
    text = _LATEX_CMD_PATTERN.sub(r' \2 ', text)
    # Remove remaining backslash commands
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove leftover braces and special chars
    text = re.sub(r'[{}]', ' ', text)
    text = re.sub(r'[~%]', ' ', text)
    # Collapse whitespace
    text = _WHITESPACE_PATTERN.sub(' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the span [start, end) is inside an environment that the
    base extractor already handles (proof, example, theorem, …).
    """
    # Walk through all excluded-env openings before `start`
    depth: Dict[str, int] = {}
    for m in _EXCLUDED_ENV_PATTERN.finditer(text, 0, start):
        env = m.group(1).lower()
        depth[env] = depth.get(env, 0) + 1

    # Count closings before `start`
    close_pat = re.compile(
        r'\\end\{(proof|Proof|example|Example|remark|Remark|theorem|Theorem'
        r'|lemma|Lemma|proposition|Proposition|corollary|Corollary)\}',
        re.IGNORECASE,
    )
    for m in close_pat.finditer(text, 0, start):
        env = m.group(1).lower()
        depth[env] = depth.get(env, 0) - 1

    return any(v > 0 for v in depth.values())


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a duplicate or substring of another."""
    seen: List[str] = []
    out: List[dict] = []
    for r in results:
        rl = r['raw_latex'].strip()
        if not rl:
            continue
        if any(rl == s or rl in s or s in rl for s in seen):
            continue
        seen.append(rl)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures not caught by the base _extract_proofs method.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule 1 – \[sub…]section{Proof of …} style
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = m.span()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 2 – {\sc Proof …} / \textsc{Proof …} header
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        start, end = m.span()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 3 – standalone \emph{Proof …} paragraph
    # ------------------------------------------------------------------
    for m in STANDALONE_EMPH_PROOF_PATTERN.finditer(text):
        start, end = m.span()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        # Extract optional "Proof of ..." name from header
        header = m.group('header')
        name_m = re.search(r'\\emph\{(Proof[^}]*)\}', header)
        name = name_m.group(1).strip() if name_m else None
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'STANDALONE_EMPH_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    return _deduplicate(results)
