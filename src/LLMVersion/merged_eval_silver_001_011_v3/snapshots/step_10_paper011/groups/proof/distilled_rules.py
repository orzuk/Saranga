import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \subsection{Proof of ...} or \section{Proof of ...} style proofs
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:(?:sub)*section)\s*\*?\s*\{[^}]*\bProof\b[^}]*\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:(?:sub)*section)\s*\*?\s*\{|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule 2: {\sc Proof ...}. or \textsc{Proof ...}. style proofs
SC_PROOF_PATTERN = re.compile(
    r'(?:\{\\sc\s+Proof[^}]*\}|\\textsc\{Proof[^}]*\})'
    r'[.:]?\s*'
    r'(?P<body>.*?)'
    r'(?=\\(?:section|subsection|subsubsection|appendix)\b'
    r'|\{\\sc\s+Proof'
    r'|\\textsc\{Proof'
    r'|\\begin\{(?:proof|Proof)\}'
    r'|\\end\{document\}'
    r'|\Z)',
    re.DOTALL
)

# Rule 3: standalone \emph{Proof ...} or \emph{Proof of ...} at paragraph boundary
STANDALONE_EMPH_PROOF_PATTERN = re.compile(
    r'(?:^|(?<=\n\n)|(?<=\n)[ \t]*)'
    r'\\emph\{Proof[^}]*\}'
    r'[.:]?\s*'
    r'(?P<body>.*?)'
    r'(?:'
        r'\\(?:blacksquare|square|qed)\b'
        r'|\\end\{(?:aligned|equation\*?|align\*?|gather\*?)\}\s*\$\$'
        r'|\\section\b'
        r'|\\subsection\b'
        r'|\\subsubsection\b'
        r'|\\begin\{(?:proof|Proof|theorem|Theorem|lemma|Lemma|definition|Definition|remark|Remark)\}'
        r'|\\end\{document\}'
        r'|\Z'
    r')',
    re.DOTALL | re.MULTILINE
)

# Rule 4: nested-environment-aware proof extraction for \begin{proof}...\end{proof}
# handles bodies that consist primarily of nested \begin...\end blocks
NESTED_PROOF_PATTERN = re.compile(
    r'\\begin\{(proof|Proof)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>'
        r'(?:'
            r'\\begin\{[^}]+\}.*?\\end\{[^}]+\}'
            r'|'
            r'(?!\\end\{(?:proof|Proof)\})[\s\S]'
        r')*'
    r')'
    r'\\end\{(?:proof|Proof)\}',
    re.DOTALL | re.IGNORECASE
)

# Environments to exclude matches from (we don't want to re-extract things
# already inside these or to extract proofs that are sub-parts of other envs
# in an undesirable way)
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|verbatim|lstlisting|minted|comment)\}',
    re.DOTALL
)

_LATEX_CMD_PATTERN = re.compile(
    r'\\[a-zA-Z]+\*?(?:\{[^}]*\}|\[[^\]]*\])*'
)

_DISPLAY_MATH_PATTERN = re.compile(
    r'\$\$.*?\$\$|\\\[.*?\\\]|\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Minimal LaTeX -> plain text conversion."""
    if not text:
        return ""
    # Remove display math environments
    result = _DISPLAY_MATH_PATTERN.sub(' [MATH] ', text)
    # Remove inline math
    result = re.sub(r'\$[^$]*\$', ' [MATH] ', result)
    # Remove common LaTeX commands but keep their text arguments
    result = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb|operatorname)\{([^}]*)\}', r'\1', result)
    # Remove remaining LaTeX commands
    result = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*', ' ', result)
    # Remove leftover braces and special chars
    result = re.sub(r'[{}\\]', ' ', result)
    # Normalise whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the span [start, end) is inside an excluded environment
    (e.g. verbatim, lstlisting, comment).
    """
    excluded = {'verbatim', 'lstlisting', 'minted', 'comment'}
    # Find all \begin{env} before `start`
    depth: Dict[str, int] = {}
    begin_pattern = re.compile(r'\\begin\{([^}]+)\}')
    end_pattern = re.compile(r'\\end\{([^}]+)\}')

    before = text[:start]
    for m in begin_pattern.finditer(before):
        env = m.group(1)
        if env in excluded:
            depth[env] = depth.get(env, 0) + 1
    for m in end_pattern.finditer(before):
        env = m.group(1)
        if env in excluded:
            depth[env] = depth.get(env, 0) - 1

    for env, d in depth.items():
        if d > 0:
            return True
    return False


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result's raw_latex,
    or which are exact/near duplicates."""
    if not results:
        return results
    # Sort by length descending so we keep longer ones preferentially
    sorted_results = sorted(results, key=lambda x: len(x['raw_latex']), reverse=True)
    kept = []
    kept_texts = []
    for r in sorted_results:
        raw = r['raw_latex'].strip()
        # Check for overlap: if this raw_latex is substantially contained in a kept one
        is_dup = False
        for kt in kept_texts:
            if raw in kt or kt in raw:
                is_dup = True
                break
            # Check for high similarity by comparing first 200 chars
            if raw[:200] == kt[:200] and abs(len(raw) - len(kt)) < 50:
                is_dup = True
                break
        if not is_dup and raw:
            kept.append(r)
            kept_texts.append(raw)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures NOT already caught by the base _extract_proofs method.
    Returns a list of dicts with keys:
      raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []

    # Track bodies already found (to avoid duplicates across rules)
    seen_bodies: set = set()

    # ------------------------------------------------------------------
    # Rule 1: \section{Proof of ...} / \subsection{Proof of ...}
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        body_key = body[:300]
        if body_key in seen_bodies:
            continue
        seen_bodies.add(body_key)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof ...}. or \textsc{Proof ...}.
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        body_key = body[:300]
        if body_key in seen_bodies:
            continue
        seen_bodies.add(body_key)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 3: standalone \emph{Proof ...} at paragraph boundary
    # ------------------------------------------------------------------
    for m in STANDALONE_EMPH_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        body_key = body[:300]
        if body_key in seen_bodies:
            continue
        # Extract optional "Proof of ..." header text for name
        header_match = re.match(r'\\emph\{(Proof[^}]*)\}', m.group(0))
        name = header_match.group(1).strip() if header_match else None
        seen_bodies.add(body_key)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'STANDALONE_EMPH_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 4: nested-environment-aware \begin{proof}...\end{proof}
    # (fallback for proofs whose body is primarily nested environments)
    # ------------------------------------------------------------------
    # Collect bodies already caught by base method via simple pattern
    base_proof_simple = re.compile(
        r'\\begin\{proof\}(?:\[[^\]]*\])?.*?\\end\{proof\}',
        re.DOTALL | re.IGNORECASE
    )
    base_bodies: set = set()
    for m in base_proof_simple.finditer(text):
        body = m.group(0)
        base_bodies.add(body[:300])

    for m in NESTED_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        opt_name = m.group('opt')
        if not body:
            continue
        # Skip if already caught by base
        full_match_key = m.group(0)[:300]
        if full_match_key in base_bodies:
            continue
        body_key = body[:300]
        if body_key in seen_bodies:
            continue
        seen_bodies.add(body_key)
        name = opt_name.strip() if opt_name else None
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'NESTED_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    return _deduplicate(results)
