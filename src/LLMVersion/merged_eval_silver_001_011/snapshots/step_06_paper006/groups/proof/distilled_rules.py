import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \section / \subsection whose title starts with "Proof"
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:(?:sub){0,2}section)\*?\s*\{(Proof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(.*?)'
    r'(?=\\(?:(?:sub){0,2}section)\*?\s*\{|\\end\{document\}|\Z)',
    re.DOTALL,
)

# Rule 2: {\sc Proof of ...}. style proofs
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+(Proof[^}]*)\}\.?\s*'
    r'(.*?)'
    r'(?=\{\\sc\s+Proof|\{\\textsc\s+Proof|\\begin\{(?:section|document)\}'
    r'|\\(?:(?:sub){0,2}section)\*?\s*\{|\\end\{document\}|\Z)',
    re.DOTALL,
)

# Rule 3: \emph{Proof ...} inline, terminated by \blacksquare / \qed / \square
BLACKSQUARE_PROOF_PATTERN = re.compile(
    r'(\\emph\{Proof[^}]*\}\.?\s*'
    r'.*?'
    r'(?:\\blacksquare|\\qed|\\square))'
    r'(?=\s*\$\$|\s*\n\s*\n|\s*\\begin\{|\s*\\(?:(?:sub){0,2}section)'
    r'|\s*\\end\{document\}|%%%%|\Z)',
    re.DOTALL,
)

# Environments to exclude (we skip matches that are entirely inside these)
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}.*?\\end\{\1\}',
    re.DOTALL,
)

# Helper: extract a \ref-like label from a string
_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref)\{([^}]+)\}')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text conversion."""
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|equation\*|align\*|split)[^}]*\}.*?'
                  r'\\end\{(?:equation|align|equation\*|align\*|split)[^}]*\}',
                  ' ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', ' ', text, flags=re.DOTALL)
    # Remove common LaTeX commands, keep their argument
    text = re.sub(r'\\(?:emph|textbf|textit|text|mathrm|mathbf|mathcal'
                  r'|label|ref|eqref|autoref|cite)\{([^}]*)\}', r'\1', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Normalise whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is fully inside an excluded env."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _spans_overlap(spans: List[tuple], start: int, end: int) -> bool:
    """Return True if [start, end) overlaps with any span already recorded."""
    for (s, e) in spans:
        if start < e and end > s:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    results: List[dict] = []
    used_spans: List[tuple] = []

    # Also collect raw_latex values already seen to avoid content duplicates
    seen_raw: set = set()

    # ------------------------------------------------------------------
    # Rule 1: section/subsection titled "Proof of ..."
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _spans_overlap(used_spans, start, end):
            continue

        section_title = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue

        # Deduplicate on content
        key = body[:200]
        if key in seen_raw:
            continue

        # Require the body to be non-trivial (at least 40 chars)
        if len(body) < 40:
            continue

        name = section_title
        clean = _clean_latex(body)

        result = {
            "raw_latex": body,
            "clean_text": clean,
            "name": name,
            "env_name": "distilled",
            "rule_name": "SUBSECTION_PROOF_PATTERN",
            "structure_type": "proof",
        }
        # Optionally tag with target theorem label
        ref_m = _REF_PATTERN.search(section_title)
        if ref_m:
            result["target_theorem_label"] = ref_m.group(1)

        results.append(result)
        used_spans.append((start, end))
        seen_raw.add(key)

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof of ...}. style
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _spans_overlap(used_spans, start, end):
            continue

        sc_title = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue

        key = body[:200]
        if key in seen_raw:
            continue

        if len(body) < 40:
            continue

        clean = _clean_latex(body)

        result = {
            "raw_latex": body,
            "clean_text": clean,
            "name": sc_title if sc_title else None,
            "env_name": "distilled",
            "rule_name": "SC_PROOF_PATTERN",
            "structure_type": "proof",
        }
        ref_m = _REF_PATTERN.search(sc_title)
        if ref_m:
            result["target_theorem_label"] = ref_m.group(1)

        results.append(result)
        used_spans.append((start, end))
        seen_raw.add(key)

    # ------------------------------------------------------------------
    # Rule 3: \emph{Proof ...} terminated by \blacksquare / \qed / \square
    # ------------------------------------------------------------------
    for m in BLACKSQUARE_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _spans_overlap(used_spans, start, end):
            continue

        full_match = m.group(1).strip()
        if not full_match:
            continue

        key = full_match[:200]
        if key in seen_raw:
            continue

        if len(full_match) < 40:
            continue

        # Extract the \emph{Proof ...} header to use as name
        header_m = re.match(r'\\emph\{([^}]*)\}', full_match)
        name = header_m.group(1).strip() if header_m else None

        # The "body" is everything after the \emph{...}. header
        if header_m:
            body = full_match[header_m.end():].lstrip('.').strip()
        else:
            body = full_match

        clean = _clean_latex(full_match)

        result = {
            "raw_latex": full_match,
            "clean_text": clean,
            "name": name,
            "env_name": "distilled",
            "rule_name": "BLACKSQUARE_PROOF_PATTERN",
            "structure_type": "proof",
        }
        if header_m:
            ref_m = _REF_PATTERN.search(header_m.group(0))
            if ref_m:
                result["target_theorem_label"] = ref_m.group(1)

        results.append(result)
        used_spans.append((start, end))
        seen_raw.add(key)

    return results
