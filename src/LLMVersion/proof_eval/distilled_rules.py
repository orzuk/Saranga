import re
from typing import List, Dict
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from latex_clean import clean_latex_to_text as _clean_latex


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Check if the span [start, end) is inside a theorem/lemma/definition/remark/example environment."""
    excluded_envs = [
        'theorem', 'Theorem', 'thm',
        'lemma', 'Lemma', 'lem',
        'proposition', 'Proposition', 'prop',
        'corollary', 'Corollary', 'cor',
        'definition', 'Definition', 'defn', 'dfn',
        'remark', 'Remark', 'rem',
        'example', 'Example',
        'claim', 'Claim',
    ]
    for env in excluded_envs:
        begin_pat = re.compile(r'\\begin\{' + re.escape(env) + r'\}', re.DOTALL)
        end_pat = re.compile(r'\\end\{' + re.escape(env) + r'\}', re.DOTALL)
        for bm in begin_pat.finditer(text):
            bpos = bm.start()
            if bpos >= start:
                break
            em = end_pat.search(text, bm.end())
            if em and em.end() > start and bpos < start:
                # The match start is inside this environment
                return True
    return False


# ==================== COMPILED PATTERNS ====================

# 1. Standard \begin{proof}...\end{proof} environments
_ENV_PROOF_PATTERN = re.compile(
    r'\\begin\{(proof|Proof)\}'
    r'(?:\s*\[([^\]]*)\])?'  # optional argument like \begin{proof}[Proof of Theorem 1]
    r'\s*'
    r'(.*?)'
    r'\\end\{(?:proof|Proof)\}',
    re.DOTALL
)

# 2. Inline proofs: \par\noindent\emph{Proof}. \newline ...
# The body runs until a proof-ending marker or the next structural element.
# We include \hfill\s*\qed variants, \qedref, and structural boundaries as terminators.
_INLINE_PROOF_PATTERN = re.compile(
    r'(\\par\s*\\noindent\s*\\emph\{Proof\}\s*\.?\s*(?:\\newline)?\s*)'
    r'(.*?)'
    r'(?=\\hfill\s*\\qed|\\qedref\{|'
    r'\\begin\{(?:theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop|'
    r'corollary|Corollary|cor|claim|Claim|definition|Definition|defn|dfn|'
    r'proof|Proof)\}|'
    r'\\par\s*\\noindent\s*\\emph\{Proof\}|'
    r'\\section\b|\\subsection\b|\\end\{document\}|\Z)',
    re.DOTALL
)

# Pattern for the trailing \hfill \qedref{...} or \hfill \qed etc.
_QEDREF_TRAIL = re.compile(
    r'\s*\\hfill\s*\\qedref\{[^}]*\}',
    re.DOTALL
)
_QED_TRAIL = re.compile(
    r'\s*\\hfill\s*\\qed(?:symbol)?\b',
    re.DOTALL
)

# 3. \proof ... \qed style (command-based, e.g. amsthm shorthand or custom)
_CMD_PROOF_QED_PATTERN = re.compile(
    r'(\\proof\b\s*)'
    r'(.*?)'
    r'(\\qed\b)',
    re.DOTALL
)

# 4. \proof ... fallback (runs to next structural boundary)
_CMD_PROOF_FALLBACK_PATTERN = re.compile(
    r'(\\proof\b\s*)'
    r'(.*?)'
    r'(?=\\begin\{(?:theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop|'
    r'corollary|Corollary|cor|claim|Claim|definition|Definition|defn|dfn|proof|Proof)\}|'
    r'\\section\b|\\subsection\b|\\end\{document\}|'
    r'\\(?:theorem|lemma|proposition|corollary|definition|remark|example)\b|\Z)',
    re.DOTALL
)

# 5. Section-level proofs: \section{Proof of ...}
_SECTION_PROOF_PATTERN = re.compile(
    r'(\\section\*?\s*\{\s*(Proof[^}]*)\}\s*)'
    r'(?:\\noindent\s*)?'
    r'(.*?)'
    r'(?=\\section\b|\\end\{document\}|\Z)',
    re.DOTALL
)

# Reference pattern in proof name
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref)\{([^}]*)\}')


def _overlaps(intervals: List, start: int, end: int) -> bool:
    """Check if [start, end) overlaps with any interval in the list."""
    for s, e in intervals:
        if start < e and end > s:
            return True
    return False


def extract_distilled_proof(text: str) -> List[Dict]:
    results = []
    captured_intervals = []  # (start, end) of captured spans for dedup
    captured_bodies = set()  # normalized bodies for content dedup

    def _add_result(raw_latex: str, name, span_start: int, span_end: int):
        """Add a result if not duplicated."""
        norm = raw_latex.strip()
        if not norm:
            return
        # Check overlap
        if _overlaps(captured_intervals, span_start, span_end):
            # Check if this is a substantial overlap (>50% overlap with existing)
            for s, e in captured_intervals:
                overlap_start = max(span_start, s)
                overlap_end = min(span_end, e)
                if overlap_end > overlap_start:
                    overlap_len = overlap_end - overlap_start
                    this_len = span_end - span_start
                    if overlap_len > 0.5 * this_len:
                        return
        # Content dedup
        if norm in captured_bodies:
            return
        clean = _clean_latex(norm)
        if not clean:
            return
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean,
            'name': name,
            'env_name': 'distilled',
        })
        captured_intervals.append((span_start, span_end))
        captured_bodies.add(norm)

    # Pattern 1 (standard \begin{proof}...\end{proof}) is already handled by
    # _extract_proofs in math_paper_parser.py — skip it to avoid duplicates.

    # === 2. Inline proofs: \par\noindent\emph{Proof} ... ===
    for m in _INLINE_PROOF_PATTERN.finditer(text):
        header = m.group(1)
        body = m.group(2)
        if not body.strip():
            continue
        # Try to capture the trailing \hfill \qedref{...} or \hfill \qed
        full_end = m.end()
        trail_match = _QEDREF_TRAIL.match(text, m.end())
        if not trail_match:
            trail_match = _QED_TRAIL.match(text, m.end())
        trailing = ''
        if trail_match:
            trailing = trail_match.group(0)
            full_end = trail_match.end()

        raw = header + body + trailing
        raw = raw.strip()
        if not raw:
            continue

        # Extract name from qedref if present
        name = None
        qedref_m = re.search(r'\\qedref\{([^}]*)\}', trailing)
        if qedref_m:
            name = qedref_m.group(1)

        _add_result(raw, name, m.start(), full_end)

    # === 3. Command-style \proof ... \qed ===
    for m in _CMD_PROOF_QED_PATTERN.finditer(text):
        header = m.group(1)
        body = m.group(2)
        qed = m.group(3)
        if not body.strip():
            continue
        raw = header + body + qed
        _add_result(raw.strip(), None, m.start(), m.end())

    # === 4. Command-style \proof fallback (no \qed found) ===
    for m in _CMD_PROOF_FALLBACK_PATTERN.finditer(text):
        header = m.group(1)
        body = m.group(2)
        if not body.strip():
            continue
        raw = header + body
        _add_result(raw.strip(), None, m.start(), m.end())

    # === 5. Section-level proofs ===
    for m in _SECTION_PROOF_PATTERN.finditer(text):
        section_header = m.group(1)
        section_title = m.group(2).strip()
        body = m.group(3)
        if not body.strip():
            continue
        raw = section_header + body
        raw = raw.strip()
        name = section_title

        # Check for ref in title
        ref_m = _HEADER_REF_PATTERN.search(section_title)
        if ref_m:
            name = section_title

        _add_result(raw, name, m.start(), m.end())

    return results
