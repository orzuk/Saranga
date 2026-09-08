import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule 1: \subsection{Proof of ...} or \section{Proof of ...} followed by body
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{(Proof[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*'
    r'(.*?)'
    r'(?=\\(?:sub)*section|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 2: {\sc Proof of ...}. followed by body
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+(Proof[^}]*)\}\s*\.?\s*'
    r'(.*?)'
    r'(?=\\begin\{|\{\\sc\s+[Pp]roof|\\section|\\subsection|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3: \emph{Proof of ...} at start of line/paragraph (without \par\noindent)
INLINE_EMPH_PROOF_PATTERN = re.compile(
    r'(?:^|(?<=\n))[ \t]*\\emph\{(Proof[^}]*)\}'
    r'\.?\s*'
    r'(.*?)'
    r'(?=\\begin\{|\\emph\{[Pp]roof|\\section|\\subsection|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 4: Explicit \begin{proof}...\end{proof} (case-sensitive, fallback)
EXPLICIT_PROOF_PATTERN = re.compile(
    r'\\begin\{(proof|Proof)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?:proof|Proof)\}',
    flags=re.DOTALL
)

# Helper: detect excluded environments to avoid false positives inside them
_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(example|Example|remark|Remark|rem|note|verbatim|lstlisting)\}.*?'
    r'\\end\{\1\}',
    re.DOTALL
)

# Header \ref extractor
_HEADER_REF_PATTERN = re.compile(r'\\(?:ref|eqref|autoref|cref)\{([^}]+)\}')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very lightweight LaTeX -> plain-text cleaner."""
    # Remove common commands but keep their arguments
    text = re.sub(r'\\(?:emph|textbf|textit|mathrm|mathbf|mathit|text|mbox)\{([^}]*)\}', r'\1', text)
    # Remove labels, refs left-overs
    text = re.sub(r'\\(?:label|ref|eqref|autoref|cref|cite)\{[^}]*\}', '', text)
    # Remove display math delimiters
    text = re.sub(r'\$\$', ' ', text)
    text = re.sub(r'\$', ' ', text)
    # Remove \begin / \end
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove common macros with no args
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if [start, end) is contained within an excluded environment."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _overlaps(existing: List[dict], start: int, end: int) -> bool:
    """Return True if the interval [start, end) overlaps with any existing match."""
    for e in existing:
        es = e.get('_start', -1)
        ee = e.get('_end', -1)
        if es < end and ee > start:
            return True
    return False


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures from LaTeX source that are NOT already captured
    by the base \begin{proof}...\end{proof} environment extractor.

    Returns a list of dicts with keys:
        raw_latex, clean_text, name, env_name, rule_name, structure_type,
        _start, _end  (internal, for dedup — callers may ignore)
    """
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule 4 (explicit proof env, fallback) — catches any missed by base
    # ------------------------------------------------------------------
    for m in EXPLICIT_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(results, start, end):
            continue
        opt = m.group('opt')
        body = m.group('body').strip()
        if not body:
            continue
        name = opt.strip() if opt else None
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'EXPLICIT_PROOF_PATTERN',
            'structure_type': 'proof',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule 1: \subsection{Proof of ...} style
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(results, start, end):
            continue
        opt = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue
        # Try to find \ref in the section title for linking hint
        ref_m = _HEADER_REF_PATTERN.search(opt)
        name = opt
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof of ...}. style
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(results, start, end):
            continue
        header_text = m.group(1).strip()
        body = m.group(2).strip()
        if not body:
            continue
        ref_m = _HEADER_REF_PATTERN.search(header_text)
        name = header_text if header_text else None
        # The full match includes header; raw_latex = body only
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SC_PROOF_PATTERN',
            'structure_type': 'proof',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule 3: \emph{Proof of ...} inline (no \par\noindent)
    # ------------------------------------------------------------------
    for m in INLINE_EMPH_PROOF_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if _overlaps(results, start, end):
            continue
        opt_name = m.group(1).strip()
        inner_body = m.group(2).strip()
        # Include the \emph{...} header in raw_latex so callers see full proof
        full_raw = m.group(0).strip()
        if not inner_body:
            continue
        ref_m = _HEADER_REF_PATTERN.search(opt_name)
        name = opt_name if opt_name else None
        results.append({
            'raw_latex': full_raw,
            'clean_text': _clean_latex(full_raw),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'INLINE_EMPH_PROOF_PATTERN',
            'structure_type': 'proof',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Final dedup: sort by start, remove any remaining overlaps
    # ------------------------------------------------------------------
    results.sort(key=lambda x: x['_start'])
    deduped: List[dict] = []
    for r in results:
        if not _overlaps(deduped, r['_start'], r['_end']):
            deduped.append(r)

    for r in deduped:
        r.pop('_start', None)

    return deduped
