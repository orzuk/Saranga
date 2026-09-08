import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section or \subsection whose title starts with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{(Proof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(.*?)'
    r'(?=\\(?:sub)*section|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 2: {\sc Proof ...}. style
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+(Proof[^}]*)\}\.?\s*'
    r'(.*?)'
    r'(?=\\begin\{|\{\\sc\s+Proof|\\section|\\subsection|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3: \emph{Proof ...}. style ending with \blacksquare / \qed / \square
BLACKSQUARE_PROOF_PATTERN = re.compile(
    r'(\\emph\{Proof[^}]*\}\.?\s*)'
    r'(.*?'
    r'(?:\\blacksquare|\\qed|\\square)'
    r'.*?)'
    r'(?=\n\s*\n|\\begin\{|\\section|\\subsection|\\end\{document\}|%%%%|\Z)',
    re.DOTALL
)

# Helper: header \ref pattern
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')

# Excluded environments (base already handles proof/Proof)
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very small LaTeX-to-plain-text cleaner."""
    # Remove comments
    t = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their arguments
    t = re.sub(r'\\(?:emph|textbf|textit|mathrm|mathbf|mathit|text)\{([^}]*)\}', r'\1', t)
    # Remove labels, refs (keep the label text for readability)
    t = re.sub(r'\\(?:label|ref|eqref|autoref|cite)\{([^}]*)\}', r'\1', t)
    # Remove display math markers
    t = re.sub(r'\$\$|\\[\[\]]', ' ', t)
    # Remove remaining commands
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    # Remove braces
    t = re.sub(r'[{}]', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    # Find all \begin{excluded} ... \end{excluded} spans before end
    env_pattern = re.compile(
        r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}'
        r'.*?'
        r'\\end\{\1\}',
        re.DOTALL
    )
    for m in env_pattern.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _overlaps(new_start: int, new_end: int, seen: list) -> bool:
    """Return True if [new_start, new_end) overlaps any interval in seen."""
    for (s, e) in seen:
        if new_start < e and new_end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures NOT already caught by the base _extract_proofs
    method (which handles \\begin{proof}...\\end{proof} and
    \\par\\noindent\\emph{Proof} patterns).

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type
    """
    results: List[dict] = []
    seen_spans: list = []  # list of (start, end) tuples for dedup

    # ------------------------------------------------------------------
    # Rule 1 — \(sub)section{Proof of ...} headed proofs
    # ------------------------------------------------------------------
    for match in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = match.start(), match.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, seen_spans):
            continue

        section_title = match.group(1).strip()
        body = match.group(2).strip()
        if not body:
            continue

        name = section_title
        # Try to extract \ref target from title
        ref_m = _HEADER_REF_PATTERN.search(section_title)
        target_label = ref_m.group(1) if ref_m else None

        entry = {
            "raw_latex": body,
            "clean_text": _clean_latex(body),
            "name": name,
            "env_name": "distilled",
            "rule_name": "SUBSECTION_PROOF_PATTERN",
            "structure_type": "proof",
        }
        if target_label:
            entry["target_theorem_label"] = target_label

        results.append(entry)
        seen_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 2 — {\sc Proof of ...}. style
    # ------------------------------------------------------------------
    for match in SC_PROOF_PATTERN.finditer(text):
        start, end = match.start(), match.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, seen_spans):
            continue

        sc_title = match.group(1).strip()
        body = match.group(2).strip()
        if not body:
            continue

        entry = {
            "raw_latex": body,
            "clean_text": _clean_latex(body),
            "name": sc_title if sc_title else None,
            "env_name": "distilled",
            "rule_name": "SC_PROOF_PATTERN",
            "structure_type": "proof",
        }
        ref_m = _HEADER_REF_PATTERN.search(sc_title)
        if ref_m:
            entry["target_theorem_label"] = ref_m.group(1)

        results.append(entry)
        seen_spans.append((start, end))

    # ------------------------------------------------------------------
    # Rule 3 — \emph{Proof ...}. ... \blacksquare style
    # ------------------------------------------------------------------
    for match in BLACKSQUARE_PROOF_PATTERN.finditer(text):
        start, end = match.start(), match.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(start, end, seen_spans):
            continue

        emph_header = match.group(1).strip()  # e.g. \emph{Proof of Theorem~\ref{...}}.
        inner_body = match.group(2).strip()

        if not inner_body:
            continue

        # raw_latex = full match (header + body) so gold text is preserved
        raw_latex = (emph_header + " " + inner_body).strip()

        name_m = re.search(r'\\emph\{([^}]*)\}', emph_header)
        name = name_m.group(1).strip() if name_m else None

        entry = {
            "raw_latex": raw_latex,
            "clean_text": _clean_latex(raw_latex),
            "name": name,
            "env_name": "distilled",
            "rule_name": "BLACKSQUARE_PROOF_PATTERN",
            "structure_type": "proof",
        }
        ref_m = _HEADER_REF_PATTERN.search(emph_header)
        if ref_m:
            entry["target_theorem_label"] = ref_m.group(1)

        results.append(entry)
        seen_spans.append((start, end))

    return results
