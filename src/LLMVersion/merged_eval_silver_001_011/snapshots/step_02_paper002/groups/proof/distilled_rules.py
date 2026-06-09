import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Matches \section, \subsection, \subsubsection (starred or not) whose title
# starts with "Proof" (case-insensitive is NOT used here – LaTeX titles are
# typically capitalised).
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\s*\{(Proof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very lightweight LaTeX → plain-text cleaner (no project imports)."""
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|gather|multline)\*?\}.*?\\end\{(?:equation|align|gather|multline)\*?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$.*?\$', ' ', text, flags=re.DOTALL)
    # Remove common LaTeX commands but keep their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|text|mathrm|mathbf|mathit)\{([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})?', ' ', text)
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose contents we want to skip (avoid double-extraction)
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}',
    re.DOTALL,
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    # Check every excluded env opening before `start`; see if its matching
    # \end{...} comes after `start`.
    for m in _EXCLUDED_ENV_RE.finditer(text, 0, start):
        env_name = m.group(1)
        closing = re.search(re.escape(r'\end{' + env_name + '}'), text[m.end():])
        if closing and m.end() + closing.start() > start:
            return True
    return False


_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures from LaTeX source that are NOT already captured
    by the base \begin{proof}...\end{proof} extractor.

    Currently handles:
      - \\section / \\subsection / \\subsubsection{Proof of ...} blocks
    """
    results: List[dict] = []
    seen_spans: List[tuple] = []  # list of (start, end) to deduplicate

    def _overlaps(start: int, end: int) -> bool:
        for s, e in seen_spans:
            if start < e and end > s:
                return True
        return False

    # ------------------------------------------------------------------
    # Rule: section/subsection titled "Proof of ..."
    # ------------------------------------------------------------------
    for match in SUBSECTION_PROOF_PATTERN.finditer(text):
        span_start = match.start()
        span_end = match.end()

        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        section_title = match.group(1).strip()
        body = match.group(2).strip()

        if not body:
            continue

        clean_text = _clean_latex(body)

        # Try to pull a \ref label from the section title for linking
        ref_match = _HEADER_REF_PATTERN.search(section_title)
        target_label = ref_match.group(1) if ref_match else None

        entry: dict = {
            "raw_latex": body,
            "clean_text": clean_text,
            "name": section_title,
            "env_name": "distilled",
            "rule_name": "SUBSECTION_PROOF_PATTERN",
            "structure_type": "proof",
        }
        if target_label:
            entry["target_theorem_label"] = target_label

        results.append(entry)
        seen_spans.append((span_start, span_end))

    return results
