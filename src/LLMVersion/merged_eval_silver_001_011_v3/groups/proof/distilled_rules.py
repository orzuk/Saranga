import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their arguments
    text = re.sub(r'\\(?:emph|textbf|textit|textrm|textsf|texttt|mathrm|mathbf|mathit)\{([^}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite, \cref, \autoref etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite|citet|citep|cref|autoref|autoref)\{[^}]*\}', '', text)
    # Remove begin/end of environments
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math delimiters
    text = re.sub(r'\$\$|\\\[|\\\]', '', text)
    # Remove inline math (simple heuristic)
    text = re.sub(r'\$[^$]*\$', '[math]', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


_EXCLUDED_ENVS = [
    'proof', 'theorem', 'lemma', 'proposition', 'corollary',
    'definition', 'example', 'remark', 'algorithm',
]

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Return True if the span [start, end) is nested inside one of the excluded
    environments in the prefix of *text*.  We do a lightweight bracket scan on
    the text preceding the candidate span.
    """
    prefix = text[:start]
    for env in _EXCLUDED_ENVS:
        # count unmatched \begin{env} vs \end{env} before this position
        begins = len(re.findall(r'\\begin\{' + re.escape(env) + r'\}', prefix, re.IGNORECASE))
        ends = len(re.findall(r'\\end\{' + re.escape(env) + r'\}', prefix, re.IGNORECASE))
        if begins > ends:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-level compiled patterns (rule_name == variable name)
# ---------------------------------------------------------------------------

# Rule 1: \subsection{Proof of ...} or \section{Proof of ...}
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\s*\*?\s*\{[^}]*\bProof\b[^}]*\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule 2: {\sc Proof of ...}. body
SC_PROOF_PATTERN = re.compile(
    r'\{\\sc\s+Proof[^}]*\}\.?\s*'
    r'(?P<body>.*?)'
    r'(?=\\section|\\subsection|\\appendix|\\begin\{|\{\\sc\s+Proof|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 3: \emph{Proof of ...} or \emph{Proof.} at paragraph boundary
STANDALONE_EMPH_PROOF_PATTERN = re.compile(
    r'(?:(?:^|\n\n|\n[ \t]*\n)[ \t]*)'
    r'\\emph\{Proof[^}]*\}'
    r'[.:]?\s*'
    r'(?P<body>.*?)'
    r'(?='
        r'\\(?:blacksquare|square|qed)'
        r'|\\begin\{'
        r'|\\(?:section|subsection|subsubsection)\b'
        r'|\\end\{document\}'
        r'|\n[ \t]*\n'
        r'|\Z'
    r')',
    re.DOTALL
)

# Rule 4 (section with derivation/proof title — broad)
SECTION_DERIVATION_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{[^}]*\b(?:derivation|proof|proofs|derivations)\b[^}]*\}'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section\b|\\end\{document\}|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule 5: \section{Solution of ...} / \section{Derivation of ...} / \section{Proof of ...}
SECTION_SOLUTION_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{\s*(?:Proof|Solution|Derivation|Verification)\b[^}]*\}'
    r'\s*(?:\\label\{[^}]*\})?\s*'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section\b|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 6: "A proof is as follows." / "The proof is as follows." inline
INLINE_PROOF_AS_FOLLOWS_PATTERN = re.compile(
    r'(?:(?:^|\n\n|\n[ \t]*\n)[ \t]*)'
    r'(?:[Aa]\s+|[Tt]he\s+)?[Pp]roof\s+is\s+as\s+follows\.?\s*'
    r'(?P<body>.*?)'
    r'(?=\n[ \t]*\n|\\par\b|\\begin\{|\\section\b|\\subsection\b|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 7: Inline "Derivation of ...: " or "Proof: " paragraph header
INLINE_DERIVATION_COLON_PATTERN = re.compile(
    r'(?:(?:^|\n\n|\n[ \t]*\n)[ \t]*)'
    r'(?:[A-Z][a-zA-Z]*\s+)?(?:Derivation|Proof|Justification|Verification)(?:\s+of\s+[^:\n]{0,80})?'
    r':\s*\n?'
    r'(?P<body>.*?)'
    r'(?=\n[ \t]*\n|\\par\b|\\section\b|\\subsection\b|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 8: \textsc{Proof of ...} (textsc variant of sc_proof)
TEXTSC_PROOF_PATTERN = re.compile(
    r'\\textsc\{Proof[^}]*\}\.?\s*'
    r'(?P<body>.*?)'
    r'(?=\\section\b|\\subsection\b|\\appendix\b|\\begin\{|\\textsc\{Proof|\\end\{document\}|\Z)',
    re.DOTALL
)

# Rule 9: \textbf{Proof} or \textbf{Proof of ...} inline
TEXTBF_PROOF_PATTERN = re.compile(
    r'\\textbf\{Proof[^}]*\}[.:]?\s*'
    r'(?P<body>.*?)'
    r'(?='
        r'\\(?:blacksquare|square|qed)'
        r'|\n[ \t]*\n'
        r'|\\par\b'
        r'|\\begin\{'
        r'|\\(?:section|subsection)\b'
        r'|\\end\{document\}'
        r'|\Z'
    r')',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or b_end <= a_start)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[dict]:
    results: List[dict] = []
    seen_spans: List[tuple] = []   # (start, end)
    seen_bodies: set = set()

    def _add(raw_latex: str, name, rule_name: str, span_start: int, span_end: int):
        raw_latex = raw_latex.strip()
        if not raw_latex:
            return
        if raw_latex in seen_bodies:
            return
        # Dedup by span overlap
        for ss, se in seen_spans:
            if _spans_overlap(span_start, span_end, ss, se):
                # Keep longer match
                if (span_end - span_start) <= (se - ss):
                    return
        # Remove superseded shorter span
        to_remove = []
        for i, (ss, se) in enumerate(seen_spans):
            if _spans_overlap(span_start, span_end, ss, se):
                to_remove.append(i)
        for i in reversed(to_remove):
            seen_spans.pop(i)
            results.pop(i)

        seen_spans.append((span_start, span_end))
        seen_bodies.add(raw_latex)
        results.append({
            'raw_latex': raw_latex,
            'clean_text': _clean_latex(raw_latex),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': 'proof',
        })

    # ------------------------------------------------------------------
    # Rule 1: subsection/section titled "Proof of ..."
    # ------------------------------------------------------------------
    for m in SUBSECTION_PROOF_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Extract optional name from section title
        title_m = re.match(r'\\(?:sub)*section\s*\*?\s*\{([^}]*)\}', m.group(0))
        name = title_m.group(1).strip() if title_m else None
        _add(body, name, 'SUBSECTION_PROOF_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule 2: {\sc Proof ...}
    # ------------------------------------------------------------------
    for m in SC_PROOF_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _add(body, None, 'SC_PROOF_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule 8 (textsc variant)
    # ------------------------------------------------------------------
    for m in TEXTSC_PROOF_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _add(body, None, 'TEXTSC_PROOF_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule 3: \emph{Proof ...} at paragraph start
    # ------------------------------------------------------------------
    for m in STANDALONE_EMPH_PROOF_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Extract name from header
        hdr_m = re.match(r'\\emph\{([^}]*)\}', m.group(0).strip())
        name = hdr_m.group(1).strip() if hdr_m else None
        _add(body, name, 'STANDALONE_EMPH_PROOF_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule 9: \textbf{Proof ...}
    # ------------------------------------------------------------------
    for m in TEXTBF_PROOF_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        hdr_m = re.match(r'\\textbf\{([^}]*)\}', m.group(0).strip())
        name = hdr_m.group(1).strip() if hdr_m else None
        _add(body, name, 'TEXTBF_PROOF_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule 4: section with derivation/proof in title (must have math)
    # ------------------------------------------------------------------
    for m in SECTION_DERIVATION_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if not re.search(r'\\begin\{(?:align|equation|gather|multline)\*?\}', body):
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title_m = re.match(r'\\(?:sub)*section\*?\{([^}]*)\}', m.group(0))
        name = title_m.group(1).strip() if title_m else None
        _add(body, name, 'SECTION_DERIVATION_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule 5: section titled Solution/Derivation/Proof/Verification
    # ------------------------------------------------------------------
    for m in SECTION_SOLUTION_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title_m = re.match(r'\\(?:sub)*section\*?\{([^}]*)\}', m.group(0))
        name = title_m.group(1).strip() if title_m else None
        _add(body, name, 'SECTION_SOLUTION_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule 6: "A/The proof is as follows."
    # ------------------------------------------------------------------
    for m in INLINE_PROOF_AS_FOLLOWS_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        _add(body, None, 'INLINE_PROOF_AS_FOLLOWS_PATTERN', m.start(), m.end())

    # ------------------------------------------------------------------
    # Rule 7: "Derivation of ...: " / "Proof: " paragraph header
    # ------------------------------------------------------------------
    for m in INLINE_DERIVATION_COLON_PATTERN.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        # Only include if body contains math or is non-trivially long
        if len(body) < 30 and not re.search(r'\\begin\{|\\frac|\$', body):
            continue
        _add(body, None, 'INLINE_DERIVATION_COLON_PATTERN', m.start(), m.end())

    return results
