import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup, leaving readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \eqref{...}, \autoref{...}
    text = re.sub(r'\\(?:label|ref|eqref|autoref|cite|bibitem)\{[^}]*\}', '', text)
    # Remove common formatting commands but keep their argument
    text = re.sub(r'\\(?:emph|textbf|textit|mathrm|mathbf|mathit|text|operatorname)\{([^}]*)\}', r'\1', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}', ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', ' [MATH] ', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})?', ' ', text)
    text = re.sub(r'[{}]', '', text)
    # Normalise whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments that should not contain extracted proofs from section headers
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|example|remark|theorem|lemma|proposition|corollary|claim|definition)\}',
    re.IGNORECASE
)
_EXCLUDED_ENV_END_PATTERN = re.compile(
    r'\\end\{(proof|example|remark|theorem|lemma|proposition|corollary|claim|definition)\}',
    re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the span [start, end) sits inside a LaTeX environment
    that should not be re-extracted (proof, example, remark, …).
    """
    prefix = text[:start]
    opens = len(_EXCLUDED_ENV_PATTERN.findall(prefix))
    closes = len(_EXCLUDED_ENV_END_PATTERN.findall(prefix))
    return opens > closes


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Matches  \subsection{Proof of …}  or  \section{Proof of …}  (starred ok)
# followed by an optional \label{} and then the body up to the next
# \section / \subsection or \end{document} / end-of-string.
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\s*\{(Proof[^}]*)\}'   # section title starting with "Proof"
    r'(?:\s*\\label\{[^}]*\})?'                   # optional \label immediately after
    r'\s*(.*?)'                                    # body (lazy)
    r'(?=\\(?:sub)*section|\\end\{document\}|\Z)',
    re.DOTALL
)

# Ref pattern used to extract target theorem label from section title
_HEADER_REF_PATTERN = re.compile(
    r'\\(?:ref|eqref|autoref|cref)\{([^}]+)\}'
)

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof blocks that live under \\section{Proof …} or
    \\subsection{Proof …} headings — gaps not covered by the base
    \\begin{proof}…\\end{proof} extractor.
    """
    results: List[dict] = []
    seen_bodies: set = set()

    # Collect bodies already captured by explicit proof environments so we
    # don't double-count them.
    existing_env_pattern = re.compile(
        r'\\begin\{[Pp]roof\}(?:\[[^\]]*\])?(.*?)\\end\{[Pp]roof\}',
        re.DOTALL
    )
    env_bodies = {m.group(1) for m in existing_env_pattern.finditer(text)}

    for match in SUBSECTION_PROOF_PATTERN.finditer(text):
        section_title = match.group(1).strip()
        body = match.group(2).strip()

        if not body:
            continue

        # Skip if this body duplicates an explicit proof environment
        if body in env_bodies:
            continue

        # Deduplication among our own results
        body_key = body[:200]  # use a prefix as cheap key
        if body_key in seen_bodies:
            continue

        # Sanity: the section title must start with "Proof"
        if not section_title.lower().startswith('proof'):
            continue

        # Don't extract if the match starts inside another excluded env
        if _inside_excluded_env(text, match.start(), match.end()):
            continue

        seen_bodies.add(body_key)

        clean = _clean_latex(body)

        # Try to pull a \ref target from the section title
        name: str = section_title
        ref_match = _HEADER_REF_PATTERN.search(section_title)
        target_label = ref_match.group(1) if ref_match else None

        entry: dict = {
            'raw_latex': body,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        }
        if target_label:
            entry['target_theorem_label'] = target_label

        results.append(entry)

    return results
