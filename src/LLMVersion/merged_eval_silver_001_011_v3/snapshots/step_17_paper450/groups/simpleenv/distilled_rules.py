import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup to produce readable plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \cref{...}, etc.
    text = re.sub(r'\\(?:label|ref|cref|Cref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove \begin{...} and \end{...}
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math environments (equation, align, etc.) - simplified
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove common formatting commands but keep their argument
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb)\{([^}]*)\}', r'\1', text)
    # Remove \noindent, \medskip, \bigskip, etc.
    text = re.sub(r'\\(?:noindent|medskip|bigskip|smallskip|vspace|hspace)\b[^\n]*', '', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})*', ' ', text)
    # Remove leftover braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Excluded environments: inside these we do not want to extract remarks/examples/assumptions
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop|corollary|Corollary|cor|algorithm|table|figure)\}',
    re.IGNORECASE
)

_EXCLUDED_ENV_FULL_RE = re.compile(
    r'\\begin\{(proof|Proof|theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|prop|corollary|Corollary|cor|algorithm|table|figure)\}.*?\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_FULL_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _infer_structure_type(env_name_or_keyword: str) -> str:
    """Infer structure_type from an environment name or leading keyword."""
    s = env_name_or_keyword.lower().rstrip('*').rstrip('s')  # normalize plurals
    if s in ('remark', 'note', 'observation', 'rem'):
        return 'remark'
    if s in ('example', 'exam', 'ex', 'illustration', 'experiment', 'numerical',
             'simulation', 'case', 'scenario'):
        return 'example'
    if s in ('assumption', 'assum', 'asmp', 'hyp', 'hypothesis'):
        return 'assumption'
    return 'remark'


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result, and exact duplicates."""
    if not results:
        return results
    # Sort by length descending so larger spans come first
    results = sorted(results, key=lambda r: len(r['raw_latex']), reverse=True)
    seen_texts = []
    deduped = []
    for r in results:
        raw = r['raw_latex'].strip()
        dominated = False
        for seen in seen_texts:
            if raw in seen or seen in raw:
                dominated = True
                break
        if not dominated:
            deduped.append(r)
            seen_texts.append(raw)
    for r in deduped:
        r.pop('_start', None)

    return deduped


# ---------------------------------------------------------------------------
# Pattern 1: \textbf{Remark[s]?[:.}]} inline (not in \begin/\end)
# Catches: \textbf{Remark:}, \textbf{Remark.}, \textbf{Remark}
# ---------------------------------------------------------------------------

TEXTBF_REMARK_RE = re.compile(
    r'\\textbf\{(Remark|Note|Observation)s?[.:]?\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:sub)*section\*?\{|\\paragraph\{).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 2: {\bf Remark.} or {\bf Remarks.} inline bold keyword
# Catches: {\bf Remark.} body, {\sc Remark.} body
# ---------------------------------------------------------------------------

BF_KEYWORD_REMARK_RE = re.compile(
    r'\{\\(?:bf|sc|it)\s+(Remark|Note|Observation)s?\.?\}'
    r'\s*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:sub)*section\*?\{|\\paragraph\{|\n\s*\n\s*\n).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 3: \noindent{\sc Remark[s]?.} body (until next structural boundary)
# ---------------------------------------------------------------------------

SC_NOINDENT_REMARK_RE = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:sub)*section\*?\{|\\noindent\s*\{\\sc|\\appendix|\\paragraph\{).)+)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 4: \noindent{\sc Remarks.} followed by \begin{list}...\end{list}
# Each \item in the list is a separate remark
# ---------------------------------------------------------------------------

SC_REMARKS_LIST_RE = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL | re.IGNORECASE
)

LIST_ITEM_RE = re.compile(
    r'\\item\b[^\\]*(?P<body>.*?)(?=\\item\b|\\end\{list\})',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 5: \begin{description} with \item[Assumption ...] labels
# ---------------------------------------------------------------------------

DESCRIPTION_ENV_RE = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)

DESCRIPTION_ITEM_RE = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]'
    r'(?P<body>.*?)(?=\\item\[|\Z)',
    re.DOTALL
)

_DESCRIPTION_KIND_PATTERNS = [
    (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bNotes?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
]

# ---------------------------------------------------------------------------
# Pattern 6: \noindent {\bf Assumption N.} {\it body} style
# ---------------------------------------------------------------------------

NOINDENT_BF_ASSUMPTION_RE = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>Assumptions?[^.}]*)'
    r'(?:\.|\.?\})'
    r'\s*'
    r'(?:\{\\it\s+|\{\\em\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>(?:(?!\n\s*\n\s*\n|\\noindent|\\begin\{|\\section|\\subsection).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 7: \emph{Keyword.} or \textit{Keyword.} inline labeled paragraphs
# ---------------------------------------------------------------------------

INLINE_EMPH_LABEL_RE = re.compile(
    r'(?:\\emph|\\textit|\\textbf)'
    r'\{(?P<keyword>Remark|Note|Observation|Example|Assumption)s?\.?\}'
    r'\s*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:sub)*section\*?\{|\\paragraph\{|\n\s*\n\s*\n).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 8: \paragraph{Example[^}]*} body until next paragraph/section
# ---------------------------------------------------------------------------

PARAGRAPH_EXAMPLE_RE = re.compile(
    r'\\paragraph\{'
    r'(?P<title>(?:Example|Illustration)[^}]*)'
    r'\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\{|\\subsection\{|\\section\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 9: \paragraph{Remark[^}]*} body until next paragraph/section
# ---------------------------------------------------------------------------

PARAGRAPH_REMARK_RE = re.compile(
    r'\\paragraph\{'
    r'(?P<title>(?:Remark|Note|Observation)[^}]*)'
    r'\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\{|\\subsection\{|\\section\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 10: \paragraph{Assumption[^}]*} body until next paragraph/section
# ---------------------------------------------------------------------------

PARAGRAPH_ASSUMPTION_RE = re.compile(
    r'\\paragraph\{'
    r'(?P<title>(?:Assumption|Hypothesis)[^}]*)'
    r'\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\{|\\subsection\{|\\section\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 11: \section or \subsection titled "Example[s]..." extracts body
# ---------------------------------------------------------------------------

SECTION_EXAMPLE_RE = re.compile(
    r'\\(?:sub)*section\*?'
    r'\{(?P<title>(?:Example|Illustration)[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section\*?\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 12: \section or \subsection titled "Remark[s]..." extracts body
# ---------------------------------------------------------------------------

SECTION_REMARK_RE = re.compile(
    r'\\(?:sub)*section\*?'
    r'\{(?P<title>(?:Remark|Note|Observation)[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section\*?\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 13: \section or \subsection titled "Assumption[s]..." extracts body
# ---------------------------------------------------------------------------

SECTION_ASSUMPTION_RE = re.compile(
    r'\\(?:sub)*section\*?'
    r'\{(?P<title>(?:Assumption|Hypothesis)[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section\*?\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 14: \textbf{Remark:} or \textbf{Note:} multi-paragraph variant
# (terminates at section/environment boundary, not at blank line)
# ---------------------------------------------------------------------------

TEXTBF_REMARK_MULTIPARA_RE = re.compile(
    r'\\textbf\{(?P<keyword>Remark|Note|Observation)s?[:.}][}]?\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:sub)*section\*?\{|\\paragraph\{).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 15: \textbf{Example[s]?[:.}]} inline
# ---------------------------------------------------------------------------

TEXTBF_EXAMPLE_RE = re.compile(
    r'\\textbf\{(?P<keyword>Example|Illustration)s?[.:]?\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:sub)*section\*?\{|\\paragraph\{).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 16: \textbf{Assumption[s]?[:.}]} inline
# ---------------------------------------------------------------------------

TEXTBF_ASSUMPTION_RE = re.compile(
    r'\\textbf\{(?P<keyword>Assumption|Hypothesis)s?[.:]?\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:sub)*section\*?\{|\\paragraph\{).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 17: {\bf Example N.} {\it body} style
# ---------------------------------------------------------------------------

BF_EXAMPLE_NUMBERED_RE = re.compile(
    r'\{\\(?:bf|sc)\s+(?P<label>Examples?\s+\d*[.:]?)\}'
    r'\s*'
    r'(?:\{\\it\s+|\{\\em\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>(?:(?!\n\s*\n\s*\n|\\noindent|\\begin\{|\\section|\\subsection).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 18: {\bf Assumption N.} {\it body} style (numbered, no \noindent)
# ---------------------------------------------------------------------------

BF_ASSUMPTION_NUMBERED_RE = re.compile(
    r'\{\\(?:bf|sc)\s+(?P<label>Assumptions?\s*\d*[.:]?)\}'
    r'\s*'
    r'(?:\{\\it\s+|\{\\em\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>(?:(?!\n\s*\n\s*\n|\\noindent|\\begin\{|\\section|\\subsection).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    def make_result(raw_latex: str, clean: str, name, env_name: str,
                    rule_name: str, structure_type: str) -> dict:
        return {
            'raw_latex': raw_latex.strip(),
            'clean_text': clean.strip(),
            'name': name,
            'env_name': env_name,
            'rule_name': rule_name,
            'structure_type': structure_type,
        }

    # --- Rule: TEXTBF_REMARK_RE ---
    for m in TEXTBF_REMARK_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        kw = m.group(1)
        results.append(make_result(
            body, _clean_latex(body), None, 'distilled',
            'TEXTBF_REMARK_RE', _infer_structure_type(kw)
        ))

    # --- Rule: BF_KEYWORD_REMARK_RE ---
    for m in BF_KEYWORD_REMARK_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        kw = m.group(1)
        results.append(make_result(
            body, _clean_latex(body), None, 'distilled',
            'BF_KEYWORD_REMARK_RE', _infer_structure_type(kw)
        ))

    # --- Rule: SC_NOINDENT_REMARK_RE ---
    for m in SC_NOINDENT_REMARK_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), None, 'distilled',
            'SC_NOINDENT_REMARK_RE', 'remark'
        ))

    # --- Rule: SC_REMARKS_LIST_RE (each \item is a separate remark) ---
    for list_match in SC_REMARKS_LIST_RE.finditer(text):
        if _inside_excluded_env(text, list_match.start(), list_match.end()):
            continue
        list_body = list_match.group('list_env')
        for item_match in LIST_ITEM_RE.finditer(list_body):
            body = item_match.group('body').strip()
            # Also include text after \item keyword up to next \item
            full_item_text = item_match.group(0).replace('\\item', '', 1).strip()
            body = full_item_text if full_item_text else body
            if len(body) < 10:
                continue
            results.append(make_result(
                body, _clean_latex(body), None, 'distilled',
                'SC_REMARKS_LIST_RE', 'remark'
            ))

    # --- Rule: DESCRIPTION_ENV_RE (with label-based kind inference) ---
    for desc_match in DESCRIPTION_ENV_RE.finditer(text):
        if _inside_excluded_env(text, desc_match.start(), desc_match.end()):
            continue
        block = desc_match.group('body')
        for item_match in DESCRIPTION_ITEM_RE.finditer(block):
            item_label = item_match.group('label').strip()
            item_body = item_match.group('body').strip()
            if len(item_body) < 10:
                continue
            kind = None
            for pat, k in _DESCRIPTION_KIND_PATTERNS:
                if pat.search(item_label):
                    kind = k
                    break
            if kind is None:
                continue
            results.append(make_result(
                item_body, _clean_latex(item_body), item_label, 'distilled',
                'DESCRIPTION_ENV_RE', kind
            ))

    # --- Rule: NOINDENT_BF_ASSUMPTION_RE ---
    for m in NOINDENT_BF_ASSUMPTION_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        # Strip trailing closing brace from {\it ...} if present
        body = re.sub(r'\}\s*$', '', body).strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), label_text, 'distilled',
            'NOINDENT_BF_ASSUMPTION_RE', 'assumption'
        ))

    # --- Rule: INLINE_EMPH_LABEL_RE ---
    for m in INLINE_EMPH_LABEL_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('keyword')
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), None, 'distilled',
            'INLINE_EMPH_LABEL_RE', _infer_structure_type(kw)
        ))

    # --- Rule: PARAGRAPH_EXAMPLE_RE ---
    for m in PARAGRAPH_EXAMPLE_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), title, 'distilled',
            'PARAGRAPH_EXAMPLE_RE', 'example'
        ))

    # --- Rule: PARAGRAPH_REMARK_RE ---
    for m in PARAGRAPH_REMARK_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), title, 'distilled',
            'PARAGRAPH_REMARK_RE', 'remark'
        ))

    # --- Rule: PARAGRAPH_ASSUMPTION_RE ---
    for m in PARAGRAPH_ASSUMPTION_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), title, 'distilled',
            'PARAGRAPH_ASSUMPTION_RE', 'assumption'
        ))

    # --- Rule: SECTION_EXAMPLE_RE ---
    for m in SECTION_EXAMPLE_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        results.append(make_result(
            body, _clean_latex(body), title, 'distilled',
            'SECTION_EXAMPLE_RE', 'example'
        ))

    # --- Rule: SECTION_REMARK_RE ---
    for m in SECTION_REMARK_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        results.append(make_result(
            body, _clean_latex(body), title, 'distilled',
            'SECTION_REMARK_RE', 'remark'
        ))

    # --- Rule: SECTION_ASSUMPTION_RE ---
    for m in SECTION_ASSUMPTION_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if len(body) < 20:
            continue
        results.append(make_result(
            body, _clean_latex(body), title, 'distilled',
            'SECTION_ASSUMPTION_RE', 'assumption'
        ))

    # --- Rule: TEXTBF_REMARK_MULTIPARA_RE ---
    # (Superset of TEXTBF_REMARK_RE; kept for multi-paragraph variant)
    for m in TEXTBF_REMARK_MULTIPARA_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        kw = m.group('keyword')
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), None, 'distilled',
            'TEXTBF_REMARK_MULTIPARA_RE', _infer_structure_type(kw)
        ))

    # --- Rule: TEXTBF_EXAMPLE_RE ---
    for m in TEXTBF_EXAMPLE_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), None, 'distilled',
            'TEXTBF_EXAMPLE_RE', 'example'
        ))

    # --- Rule: TEXTBF_ASSUMPTION_RE ---
    for m in TEXTBF_ASSUMPTION_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), None, 'distilled',
            'TEXTBF_ASSUMPTION_RE', 'assumption'
        ))

    # --- Rule: BF_EXAMPLE_NUMBERED_RE ---
    for m in BF_EXAMPLE_NUMBERED_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        body = re.sub(r'\}\s*$', '', body).strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), label_text, 'distilled',
            'BF_EXAMPLE_NUMBERED_RE', 'example'
        ))

    # --- Rule: BF_ASSUMPTION_NUMBERED_RE ---
    for m in BF_ASSUMPTION_NUMBERED_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        body = re.sub(r'\}\s*$', '', body).strip()
        if len(body) < 10:
            continue
        results.append(make_result(
            body, _clean_latex(body), label_text, 'distilled',
            'BF_ASSUMPTION_NUMBERED_RE', 'assumption'
        ))

    return _deduplicate(results)
