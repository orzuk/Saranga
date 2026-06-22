import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup, leaving readable text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...}, \citeA{...}, \citeNP{...}
    text = re.sub(r'\\(?:label|ref|cite[A-Za-z]*)\{[^}]*\}', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|eqnarray|gather|multline)\*?\}.*?\\end\{(?:equation|align|eqnarray|gather|multline)\*?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*?\$', ' ', text)
    # Remove common formatting commands but keep content
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|textsf|texttt|mathbf|mathit|mathrm)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|it|rm|sf|tt|sc)\s+([^}]*)\}', r'\1', text)
    # Remove \noindent, \par, spacing commands
    text = re.sub(r'\\(?:noindent|par|smallskip|medskip|bigskip|vspace\{[^}]*\}|hspace\{[^}]*\})', ' ', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', ' ', text)
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose content we do not want to match inside
_EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|theorem|lemma|proposition|corollary|definition|algorithm)\}.*?\\end\{\1\}',
    re.DOTALL | re.IGNORECASE
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    for m in _EXCLUDED_ENVS.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Helper: determine structure_type from env name or keyword
# ---------------------------------------------------------------------------

def _structure_type_from_keyword(keyword: str) -> str:
    kw = keyword.strip().rstrip('*').lower()
    if kw in ('remark', 'note', 'observation'):
        return 'remark'
    if kw in ('example', 'illustration'):
        return 'example'
    if kw in ('assumption', 'assumptions'):
        return 'assumption'
    return 'theorem'


def _structure_type_from_env(env_name: str) -> str:
    env = env_name.strip().rstrip('*').lower()
    if env in ('remark', 'rem', 'note'):
        return 'remark'
    if env in ('example', 'exam', 'ex', 'illustration'):
        return 'example'
    if env in ('assumption', 'assumptions'):
        return 'assumption'
    return 'theorem'


# ---------------------------------------------------------------------------
# Pattern 1: \textbf{Remark...} or \textbf{Note...} inline (not in \begin/\end)
# Catches: paper011 style \textbf{Remark:} blocks
# ---------------------------------------------------------------------------

TEXTBF_REMARK_PATTERN = re.compile(
    r'\\textbf\s*\{(?P<keyword>Remark|Note|Observation)[^}]*\}\s*:?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\end\{|\\section|\\subsection|\\subsubsection|\\paragraph\{).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 2: {\bf Keyword.} ... inline bold remark (paper002 style)
# Catches: {\bf Remark.} body text
# ---------------------------------------------------------------------------

BFGROUP_REMARK_PATTERN = re.compile(
    r'\{\\bf\s+(?P<keyword>Remark|Note|Observation)[^}]*\}[.\s]*'
    r'(?P<body>(?:(?!\\begin\{|\\end\{|\\section|\\subsection|\\subsubsection).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 3: \noindent{\sc Remark[s]?.} single-paragraph style (paper004)
# ---------------------------------------------------------------------------

SC_REMARK_SINGLE_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+(?P<keyword>Remarks?|Notes?)\.?\}\s*'
    r'(?P<body>(?:(?!\\noindent|\\begin\{|\\section|\\subsection|\\subsubsection|\\appendix).)+)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 4: \noindent{\sc Remark[s]?.} followed by \begin{list}...\end{list}
# Extract each \item as a separate remark (paper004 style)
# ---------------------------------------------------------------------------

SC_REMARKS_LIST_OUTER_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}\s*'
    r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL | re.IGNORECASE
)

LIST_ITEM_SPLIT_PATTERN = re.compile(
    r'\\item\b(?P<body>.*?)(?=\\item\b|\\end\{list\})',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 5: \emph{Remark.} or \textit{Remark.} inline label (paper005)
# ---------------------------------------------------------------------------

EMPH_KEYWORD_PATTERN = re.compile(
    r'(?P<cmd>\\(?:emph|textit|textbf))\s*\{'
    r'(?P<keyword>Remark|Note|Observation|Example|Assumption)[^}]*\}\.?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\end\{|\\section|\\subsection|\\subsubsection|\n\s*\n).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 6: \begin{description} blocks with \item[Assumption ...] labels
# (paper004 style)
# ---------------------------------------------------------------------------

DESCRIPTION_ENV_PATTERN = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)

DESCRIPTION_ITEM_PATTERN = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|\Z)',
    re.DOTALL
)

_DESCRIPTION_LABEL_KIND = [
    (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
    (re.compile(r'\bNotes?\b', re.IGNORECASE), 'remark'),
]

# ---------------------------------------------------------------------------
# Pattern 7: \noindent {\bf Assumption N.} {\it body} (paper004)
# ---------------------------------------------------------------------------

NOINDENT_BF_ASSUMPTION_PATTERN = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>Assumptions?[^.}]*)[.}]*\s*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>(?:(?!\\noindent|\\begin\{|\\section|\\subsection|\\subsubsection).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 8: \paragraph{Example ...} blocks (paper013 style)
# ---------------------------------------------------------------------------

PARAGRAPH_EXAMPLE_PATTERN = re.compile(
    r'\\paragraph\{(?P<title>(?:Example|Illustration)[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection|\\subsection|\\section|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 9: \paragraph{Remark ...} blocks
# ---------------------------------------------------------------------------

PARAGRAPH_REMARK_PATTERN = re.compile(
    r'\\paragraph\{(?P<title>(?:Remark|Note|Observation)[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection|\\subsection|\\section|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 10: \paragraph{Assumption ...} blocks
# ---------------------------------------------------------------------------

PARAGRAPH_ASSUMPTION_PATTERN = re.compile(
    r'\\paragraph\{(?P<title>(?:Assumption)[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection|\\subsection|\\section|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 11: \section{Example...} or \subsection{Example...} (paper014)
# ---------------------------------------------------------------------------

SECTION_EXAMPLE_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{(?P<title>(?:Example|Illustration)[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 12: \section{Remark...} or \subsection{Remark...}
# ---------------------------------------------------------------------------

SECTION_REMARK_PATTERN = re.compile(
    r'\\(?:sub)*section\*?\{(?P<title>(?:Remark|Note|Observation)[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Pattern 13: standalone paragraph starting with "Remark." or "Note." at line start
# ---------------------------------------------------------------------------

INLINE_PARAGRAPH_REMARK_PATTERN = re.compile(
    r'(?:^|\n)(?P<keyword>Remark|Note|Observation)\.\s+'
    r'(?P<body>(?:(?!\n\s*\n|\\begin\{|\\section|\\subsection).)+)',
    re.DOTALL | re.MULTILINE
)

# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex overlaps with a longer already-kept result."""
    # Sort by length descending so longer matches are preferred
    results_sorted = sorted(results, key=lambda x: len(x['raw_latex']), reverse=True)
    kept = []
    kept_texts = set()
    for r in results_sorted:
        # Use first 80 chars as a fingerprint to detect near-duplicates
        fp = r['raw_latex'].strip()[:80]
        if fp in kept_texts:
            continue
        kept_texts.add(fp)
        kept.append(r)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule 1: \textbf{Remark/Note/Observation...} inline ---
    for m in TEXTBF_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        keyword = m.group('keyword')
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'TEXTBF_REMARK_PATTERN',
            'structure_type': _structure_type_from_keyword(keyword),
        })

    # --- Rule 2: {\bf Remark.} inline bold ---
    for m in BFGROUP_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        keyword = m.group('keyword')
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BFGROUP_REMARK_PATTERN',
            'structure_type': _structure_type_from_keyword(keyword),
        })

    # --- Rule 3: \noindent{\sc Remark[s].} single paragraph ---
    for m in SC_REMARK_SINGLE_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        keyword = m.group('keyword')
        body = m.group('body').strip()
        if not body:
            continue
        # Skip if body starts with \begin{list} (handled by Rule 4)
        if re.match(r'\s*\\begin\{list\}', body):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SC_REMARK_SINGLE_PATTERN',
            'structure_type': _structure_type_from_keyword(keyword),
        })

    # --- Rule 4: \noindent{\sc Remarks.} + \begin{list}...\end{list} items ---
    for outer_m in SC_REMARKS_LIST_OUTER_PATTERN.finditer(text):
        if _inside_excluded_env(text, outer_m.start(), outer_m.end()):
            continue
        list_body = outer_m.group('list_env')
        for item_m in LIST_ITEM_SPLIT_PATTERN.finditer(list_body):
            body = item_m.group('body').strip()
            if not body:
                continue
            results.append({
                'raw_latex': body,
                'clean_text': _clean_latex(body),
                'name': None,
                'env_name': 'distilled',
                'rule_name': 'SC_REMARKS_LIST_OUTER_PATTERN',
                'structure_type': 'remark',
            })

    # --- Rule 5: \emph{Keyword.} or \textit{Keyword.} inline ---
    for m in EMPH_KEYWORD_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        keyword = m.group('keyword')
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'EMPH_KEYWORD_PATTERN',
            'structure_type': _structure_type_from_keyword(keyword),
        })

    # --- Rule 6: \begin{description} with \item[Assumption/Remark/Example...] ---
    for desc_m in DESCRIPTION_ENV_PATTERN.finditer(text):
        if _inside_excluded_env(text, desc_m.start(), desc_m.end()):
            continue
        block = desc_m.group('body')
        for item_m in DESCRIPTION_ITEM_PATTERN.finditer(block):
            item_label = item_m.group('label').strip()
            item_body = item_m.group('body').strip()
            # Strip trailing \end{description} artifacts
            item_body = re.sub(r'\\end\{description\}\s*$', '', item_body).strip()
            if not item_body:
                continue
            matched_kind = None
            for pat, kind in _DESCRIPTION_LABEL_KIND:
                if pat.search(item_label):
                    matched_kind = kind
                    break
            if matched_kind is None:
                continue
            results.append({
                'raw_latex': item_body,
                'clean_text': _clean_latex(item_body),
                'name': item_label if item_label else None,
                'env_name': 'distilled',
                'rule_name': 'DESCRIPTION_ENV_PATTERN',
                'structure_type': matched_kind,
            })

    # --- Rule 7: \noindent {\bf Assumption N.} {\it body} ---
    for m in NOINDENT_BF_ASSUMPTION_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        # Strip trailing closing brace from \it{...} if present
        body = re.sub(r'\}\s*$', '', body).strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': label_text if label_text else None,
            'env_name': 'distilled',
            'rule_name': 'NOINDENT_BF_ASSUMPTION_PATTERN',
            'structure_type': 'assumption',
        })

    # --- Rule 8: \paragraph{Example ...} blocks ---
    for m in PARAGRAPH_EXAMPLE_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_EXAMPLE_PATTERN',
            'structure_type': 'example',
        })

    # --- Rule 9: \paragraph{Remark ...} blocks ---
    for m in PARAGRAPH_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_REMARK_PATTERN',
            'structure_type': 'remark',
        })

    # --- Rule 10: \paragraph{Assumption ...} blocks ---
    for m in PARAGRAPH_ASSUMPTION_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_ASSUMPTION_PATTERN',
            'structure_type': 'assumption',
        })

    # --- Rule 11: \section{Example...} / \subsection{Example...} ---
    for m in SECTION_EXAMPLE_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'SECTION_EXAMPLE_PATTERN',
            'structure_type': 'example',
        })

    # --- Rule 12: \section{Remark...} / \subsection{Remark...} ---
    for m in SECTION_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'SECTION_REMARK_PATTERN',
            'structure_type': 'remark',
        })

    # --- Rule 13: standalone "Remark. " or "Note. " at line start ---
    for m in INLINE_PARAGRAPH_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        keyword = m.group('keyword')
        body = m.group('body').strip()
        if not body:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'INLINE_PARAGRAPH_REMARK_PATTERN',
            'structure_type': _structure_type_from_keyword(keyword),
        })

    return _deduplicate(results)
