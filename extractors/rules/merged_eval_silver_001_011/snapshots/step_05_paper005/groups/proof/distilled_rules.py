import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \subsection{Proof of ...} or \section{Proof of ...} heading style
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{(Proof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(.*?)'
    r'(?=\\(?:sub)*section|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 2: {\sc Proof of ...}. style (smallcaps-headed proofs)
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+Proof[^}]*\}\.?\s*'
    r'(.*?)'
    r'(?=\\begin\{|\{\\sc\s+Proof|\\section|\\subsection|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3: \emph{Proof of ...}. followed by content ending in \blacksquare/\qed/\square
BLACKSQUARE_PROOF_PATTERN = re.compile(
    r'\\emph\{Proof[^}]*\}\.?\s*'
    r'(.*?'
    r'(?:\\blacksquare|\\qed|\\square)'
    r'.*?)'
    r'(?=\n\s*\n|\\begin\{|\\section|\\subsection|\\end\{document\}|%%%%|\Z)',
    re.DOTALL
)

# Pattern to extract \ref targets from headers
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')

# Environments to check for exclusion
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX commands to produce readable plain text."""
    # Remove display math environments
    t = re.sub(r'\\begin\{(equation|align|gather|multline)\*?\}.*?\\end\{\1\*?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math
    t = re.sub(r'\$\$.*?\$\$', ' ', t, flags=re.DOTALL)
    t = re.sub(r'\$[^$]*\$', ' ', t, flags=re.DOTALL)
    # Remove \command{...} keeping inner text
    t = re.sub(r'\\(?:emph|textbf|textit|text|mathrm|mathbf|mathit|mathcal|hat|tilde|bar|vec|label|ref|cite|eqref|autoref|footnote)\{([^}]*)\}', r'\1', t)
    # Remove remaining \commands
    t = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?', ' ', t)
    # Remove braces
    t = re.sub(r'[{}]', ' ', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the span [start, end) is nested inside an excluded environment
    (proof, example, remark) in *text*.
    """
    prefix = text[:start]
    # Count open excluded envs before this position
    open_count = 0
    pos = 0
    while True:
        m = _EXCLUDED_ENVS.search(prefix, pos)
        if not m:
            break
        env_name = m.group(1)
        end_pattern = re.compile(r'\\end\{' + re.escape(env_name) + r'\}', re.IGNORECASE)
        end_m = end_pattern.search(prefix, m.end())
        if end_m:
            # This environment closes before our start — not enclosing
            pos = end_m.end()
        else:
            # Environment opens before our start but doesn't close before it
            open_count += 1
            pos = m.end()
    return open_count > 0


def _get_env_bodies(text: str) -> set:
    """
    Collect raw bodies already captured by the base \begin{proof}...\end{proof} extractor
    so we can deduplicate.
    """
    bodies = set()
    env_pattern = re.compile(
        r'\\begin\{(?:proof|Proof)\}'
        r'(?:\[[^\]]*\])?'
        r'(.*?)'
        r'\\end\{(?:proof|Proof)\}',
        re.DOTALL | re.IGNORECASE
    )
    for m in env_pattern.finditer(text):
        bodies.add(m.group(1))
    return bodies


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result's raw_latex, keeping longest."""
    if not results:
        return results
    # Sort by length descending
    results_sorted = sorted(results, key=lambda x: len(x['raw_latex']), reverse=True)
    kept = []
    for candidate in results_sorted:
        c_latex = candidate['raw_latex']
        dominated = False
        for keeper in kept:
            k_latex = keeper['raw_latex']
            if c_latex in k_latex or k_latex in c_latex:
                # Keep the longer one (already in `kept` if longer)
                if len(c_latex) <= len(k_latex):
                    dominated = True
                    break
        if not dominated:
            kept.append(candidate)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures not already caught by the base \begin{proof} extractor.
    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    env_bodies = _get_env_bodies(text)

    # ------------------------------------------------------------------
    # Rule 1: \subsection{Proof of ...} / \section{Proof of ...} headings
    # ------------------------------------------------------------------
    for match in SUBSECTION_PROOF_PATTERN.finditer(text):
        section_title = match.group(1).strip()
        body = match.group(2).strip() if match.group(2) else ''
        if not body:
            continue
        if body in env_bodies:
            continue
        if _inside_excluded_env(text, match.start(), match.end()):
            continue
        clean = _clean_latex(body)
        name = section_title
        result = {
            'raw_latex': body,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        }
        results.append(result)

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof of ...}. style
    # ------------------------------------------------------------------
    for match in SC_PROOF_PATTERN.finditer(text):
        body = match.group(1).strip() if match.group(1) else ''
        if not body:
            continue
        if body in env_bodies:
            continue
        if _inside_excluded_env(text, match.start(), match.end()):
            continue
        # Extract the header text (the {\sc ...} part)
        header_match = re.match(r'\{\\sc\s+(Proof[^}]*)\}', match.group(0))
        name = header_match.group(1).strip() if header_match else None
        clean = _clean_latex(body)
        result = {
            'raw_latex': body,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
        }
        results.append(result)

    # ------------------------------------------------------------------
    # Rule 3: \emph{Proof of ...}. ... \blacksquare/\qed/\square
    # ------------------------------------------------------------------
    for match in BLACKSQUARE_PROOF_PATTERN.finditer(text):
        full_match = match.group(0).strip()
        inner = match.group(1).strip() if match.group(1) else ''
        if not inner:
            continue
        # Skip if already captured by env-based extraction
        if inner in env_bodies or full_match in env_bodies:
            continue
        # Skip if the inner content is already dominated by an existing result
        already = any(
            inner in r['raw_latex'] or r['raw_latex'] in inner
            for r in results
        )
        if already:
            continue
        if _inside_excluded_env(text, match.start(), match.end()):
            continue
        # Use full match as raw_latex to preserve the \emph{Proof of ...} header
        raw = full_match
        clean = _clean_latex(inner)
        # Extract name from \emph{Proof of ...} header
        emph_header = re.match(r'\\emph\{(Proof[^}]*)\}', match.group(0))
        name = emph_header.group(1).strip() if emph_header else None
        result = {
            'raw_latex': raw,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'BLACKSQUARE_PROOF_PATTERN',
            'structure_type': 'proof',
        }
        results.append(result)

    # ------------------------------------------------------------------
    # Deduplicate overlapping matches across all rules
    # ------------------------------------------------------------------
    results = _deduplicate(results)

    return results
