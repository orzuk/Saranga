import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and return plain text approximation."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|eqnarray|gather|multline|split|array|matrix)[*]?\}.*?\\end\{(?:equation|align|eqnarray|gather|multline|split|array|matrix)[*]?\}', ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*?\$', ' [MATH] ', text, flags=re.DOTALL)
    # Remove common LaTeX commands
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|mathcal|mathbb|mathsf|operatorname|widehat|widetilde|overline|underline|hat|tilde|bar|vec|dot|ddot)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:label|ref|eqref|cite|citeA|citeNP|citealt|citep|citet|Cref|cref|autoref|pageref|vref)\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:footnote|footnotemark|footnotetext)\{[^}]*\}', '', text)
    text = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', text)
    text = re.sub(r'[{}]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments to exclude (matches inside these are suppressed)
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|figure|table|algorithm|lstlisting|verbatim|tikzpicture)\}',
    re.IGNORECASE
)

_EXCLUDED_ENV_FULL_RE = re.compile(
    r'\\begin\{(?:proof|figure|table|algorithm|lstlisting|verbatim|tikzpicture)\}.*?'
    r'\\end\{(?:proof|figure|table|algorithm|lstlisting|verbatim|tikzpicture)\}',
    re.DOTALL | re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_FULL_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _determine_subtype(env_name_or_keyword: str) -> str:
    """Determine structure_type from an environment name or keyword."""
    s = env_name_or_keyword.lower().rstrip('*').strip()
    if s in ('remark', 'rem', 'note', 'observation', 'remarks'):
        return 'remark'
    if s in ('example', 'exam', 'ex', 'illustration', 'exmp', 'exmpl',
             'running-example', 'runningexample', 'experiment', 'numerical',
             'simulation', 'case', 'scenario'):
        return 'example'
    if s in ('assumption', 'assumptions', 'assump', 'hyp', 'hypothesis'):
        return 'assumption'
    return 'theorem'


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Rule A: \textbf{Remark:} or \textbf{Remark.} or \textbf{Remark}
# inline remarks not wrapped in \begin/\end environments
TEXTBF_REMARK_PATTERN = re.compile(
    r'\\textbf\{Remarks?[.:]?\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\begin\{|\\end\{|\\section|\\subsection|\\subsubsection|\\paragraph\b).)+)',
    re.DOTALL
)

# Rule B: {\bf Remark.} or {\bf Remarks.} — older LaTeX style
BF_REMARK_PATTERN = re.compile(
    r'\{\\bf\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\begin\{|\\end\{|\\section|\\subsection|\\subsubsection|\\noindent\s*\{\\(?:bf|sc)).)+)',
    re.DOTALL
)

# Rule C: \noindent{\sc Remark[s]?.} style remarks (paper004 pattern)
SC_REMARK_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\(?:section|subsection|subsubsection|chapter|noindent|appendix|end\{document\})).)+)',
    re.DOTALL | re.IGNORECASE
)

# Rule D: \noindent{\sc Remark[s]?.} followed by \begin{list}...\end{list}
# Extract each \item as a separate remark
SC_REMARKS_LIST_PATTERN = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}'
    r'[.\s]*'
    r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL | re.IGNORECASE
)

LIST_ITEM_SPLIT_PATTERN = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item|\\end\{list\}|\Z)',
    re.DOTALL
)

# Rule E: \emph{Remark.} or \textit{Remark.} inline label pattern
EMPH_REMARK_PATTERN = re.compile(
    r'(?P<cmd>\\(?:emph|textit))\{Remarks?\.?\}'
    r'[\s~]*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph)\b|\n\s*\n).)+)',
    re.DOTALL
)

# Rule F: \emph{Example.} or \textit{Example.} or \textbf{Example.} inline label
# PRUNED — FP on paper006
# EMPH_EXAMPLE_PATTERN = re.compile(
#     r'(?P<cmd>\\(?:emph|textit|textbf))\{Examples?\.?\}'
#     r'[\s~]*'
#     r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph)\b|\n\s*\n).)+)',
#     re.DOTALL
# )

# Rule G: \emph{Assumption.} or \textbf{Assumption.} inline label
EMPH_ASSUMPTION_PATTERN = re.compile(
    r'(?P<cmd>\\(?:emph|textit|textbf))\{Assumptions?\.?\}'
    r'[\s~]*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph)\b|\n\s*\n).)+)',
    re.DOTALL
)

# Rule H: \begin{description}...\item[Assumption ...]...\end{description}
DESCRIPTION_ENV_PATTERN = re.compile(
    r'\\begin\{description\}'
    r'(?P<desc_body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)

DESCRIPTION_ITEM_PATTERN = re.compile(
    r'\\item\[(?P<item_label>[^\]]*)\]\s*(?P<item_body>.*?)(?=\\item\[|\\end\{description\}|\Z)',
    re.DOTALL
)

# Rule I: \noindent {\bf Assumption N.} {\it body.} pattern
NOINDENT_BF_ASSUMPTION_PATTERN = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>Assumptions?\s*[^.}]*)'
    r'(?:\.?\}|\.)'
    r'[^{\\]*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>.*?)'
    r'(?=\\noindent|\\(?:section|subsection|subsubsection|paragraph)\b|\n{3,}|\\begin\{(?:theorem|lemma|proposition|corollary|definition|proof)\}|$)',
    re.DOTALL
)

# Rule J: \paragraph{Example ...} blocks (paper013 pattern)
PARAGRAPH_EXAMPLE_PATTERN = re.compile(
    r'\\paragraph\{(?P<title>Example[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\{|\\subsection\{|\\section\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule K: \paragraph{Remark ...} blocks
PARAGRAPH_REMARK_PATTERN = re.compile(
    r'\\paragraph\{(?P<title>Remarks?[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\{|\\subsection\{|\\section\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule L: \paragraph{Assumption ...} blocks
PARAGRAPH_ASSUMPTION_PATTERN = re.compile(
    r'\\paragraph\{(?P<title>Assumptions?[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\subsubsection\{|\\subsection\{|\\section\{|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule M: \section{Example...} or \subsection{Example...} section-level examples
SECTION_EXAMPLE_PATTERN = re.compile(
    r'\\(?:sub)*section\*?'
    r'\{(?P<title>Examples?[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Rule N: \noindent{\sc Remark...} followed by list — already above (SC_REMARKS_LIST_PATTERN)
# Additional: standalone \noindent\textbf{Remark...} variant
NOINDENT_TEXTBF_REMARK_PATTERN = re.compile(
    r'\\noindent\s*'
    r'\\textbf\{Remarks?[.:]?\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\(?:section|subsection|subsubsection|noindent|begin\{|end\{document\})).)+)',
    re.DOTALL | re.IGNORECASE
)

# Rule O: \textbf{Remark:} multi-paragraph variant (terminates at section/begin)
TEXTBF_REMARK_MULTIPARA_PATTERN = re.compile(
    r'\\textbf\{Remarks?[.:]?\}'
    r'\s*:?\s*'
    r'(?P<body>(?:(?!\\begin\{(?:theorem|lemma|proposition|corollary|definition|proof|remark|example|assumption)\}|\\(?:section|subsection|subsubsection|chapter)\b).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Keyword-to-kind helper for description items
# ---------------------------------------------------------------------------

_DESC_LABEL_KIND_PATTERNS = [
    (re.compile(r'\bAssumptions?\b', re.IGNORECASE), 'assumption'),
    (re.compile(r'\bRemarks?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bNotes?\b', re.IGNORECASE), 'remark'),
    (re.compile(r'\bExamples?\b', re.IGNORECASE), 'example'),
]


def _kind_from_desc_label(label: str) -> str:
    for pat, kind in _DESC_LABEL_KIND_PATTERNS:
        if pat.search(label):
            return kind
    return None


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _dedup(results: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the one that appears first."""
    if not results:
        return results
    # Sort by start position
    results.sort(key=lambda x: x.get('_start', 0))
    deduped = []
    last_end = -1
    for r in results:
        start = r.get('_start', 0)
        end = r.get('_end', start + len(r.get('raw_latex', '')))
        if start >= last_end:
            deduped.append(r)
            last_end = end
        else:
            # Keep the one with more content (longer raw_latex)
            if len(r.get('raw_latex', '')) > len(deduped[-1].get('raw_latex', '')):
                deduped[-1] = r
                last_end = end
    # Remove internal position keys
    for r in deduped:
        r.pop('_start', None)
        r.pop('_end', None)
    return deduped


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \textbf{Remark:} / \textbf{Remark.} (single-para)
    # Use the multi-paragraph variant as the primary rule
    # ------------------------------------------------------------------
    seen_spans = set()

    for m in TEXTBF_REMARK_MULTIPARA_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        span = (start, end)
        if span in seen_spans:
            continue
        seen_spans.add(span)
        body = m.group('body').strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'TEXTBF_REMARK_MULTIPARA_PATTERN',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule B: {\bf Remark.} style
    # ------------------------------------------------------------------
    for m in BF_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BF_REMARK_PATTERN',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule C: \noindent{\sc Remark[s]?.} style (single block, not list)
    # Only if NOT followed immediately by \begin{list}
    # ------------------------------------------------------------------
    for m in SC_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        # Skip if the body starts with a list environment (handled by Rule D)
        if body.lstrip().startswith(r'\begin{list}'):
            continue
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SC_REMARK_PATTERN',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule D: \noindent{\sc Remarks?.} + \begin{list}...\end{list}
    # Extract each \item as a separate remark
    # ------------------------------------------------------------------
    for list_m in SC_REMARKS_LIST_PATTERN.finditer(text):
        list_start = list_m.start()
        if _inside_excluded_env(text, list_start, list_m.end()):
            continue
        list_body = list_m.group('list_env')
        for item_m in LIST_ITEM_SPLIT_PATTERN.finditer(list_body):
            body = item_m.group('body').strip()
            if not body or len(body) < 10:
                continue
            results.append({
                'raw_latex': body,
                'clean_text': _clean_latex(body),
                'name': None,
                'env_name': 'distilled',
                'rule_name': 'SC_REMARKS_LIST_PATTERN',
                'structure_type': 'remark',
                '_start': list_start,
                '_end': list_m.end(),
            })

    # ------------------------------------------------------------------
    # Rule E: \emph{Remark.} / \textit{Remark.} inline label
    # ------------------------------------------------------------------
    for m in EMPH_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'EMPH_REMARK_PATTERN',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule F: \emph{Example.} / \textit{Example.} / \textbf{Example.}
#     # ------------------------------------------------------------------
#     for m in EMPH_EXAMPLE_PATTERN.finditer(text):
#         start, end = m.start(), m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         body = m.group('body').strip()
#         if not body or len(body) < 10:
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'EMPH_EXAMPLE_PATTERN',
#             'structure_type': 'example',
#             '_start': start,
#             '_end': end,
#         })

    # ------------------------------------------------------------------
    # Rule G: \emph{Assumption.} / \textbf{Assumption.} inline
    # ------------------------------------------------------------------
    for m in EMPH_ASSUMPTION_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'EMPH_ASSUMPTION_PATTERN',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule H: \begin{description}...\item[...]...\end{description}
    # Extract items whose label matches assumption/remark/example keywords
    # ------------------------------------------------------------------
    for desc_m in DESCRIPTION_ENV_PATTERN.finditer(text):
        desc_start = desc_m.start()
        if _inside_excluded_env(text, desc_start, desc_m.end()):
            continue
        desc_body = desc_m.group('desc_body')
        for item_m in DESCRIPTION_ITEM_PATTERN.finditer(desc_body):
            item_label = item_m.group('item_label').strip()
            item_body = item_m.group('item_body').strip()
            if not item_body or len(item_body) < 5:
                continue
            kind = _kind_from_desc_label(item_label)
            if kind is None:
                # Check if it looks like an assumption by default
                # (description items about assumptions may use varied labels)
                if re.search(r'\bAssumption\b', item_label, re.IGNORECASE):
                    kind = 'assumption'
                else:
                    continue
            results.append({
                'raw_latex': item_body,
                'clean_text': _clean_latex(item_body),
                'name': item_label if item_label else None,
                'env_name': 'distilled',
                'rule_name': 'DESCRIPTION_ENV_PATTERN',
                'structure_type': kind,
                '_start': desc_start,
                '_end': desc_m.end(),
            })

    # ------------------------------------------------------------------
    # Rule I: \noindent {\bf Assumption N.} {\it body} pattern
    # ------------------------------------------------------------------
    for m in NOINDENT_BF_ASSUMPTION_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        # Strip trailing closing brace from \it{...} if present
        body = re.sub(r'\}\s*$', '', body).strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': label_text if label_text else None,
            'env_name': 'distilled',
            'rule_name': 'NOINDENT_BF_ASSUMPTION_PATTERN',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule J: \paragraph{Example ...} blocks
    # ------------------------------------------------------------------
    for m in PARAGRAPH_EXAMPLE_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_EXAMPLE_PATTERN',
            'structure_type': 'example',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule K: \paragraph{Remark ...} blocks
    # ------------------------------------------------------------------
    for m in PARAGRAPH_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_REMARK_PATTERN',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule L: \paragraph{Assumption ...} blocks
    # ------------------------------------------------------------------
    for m in PARAGRAPH_ASSUMPTION_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PARAGRAPH_ASSUMPTION_PATTERN',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule M: \section{Example...} / \subsection{Example...}
    # ------------------------------------------------------------------
    for m in SECTION_EXAMPLE_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'SECTION_EXAMPLE_PATTERN',
            'structure_type': 'example',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Rule N: \noindent\textbf{Remark...} variant
    # ------------------------------------------------------------------
    for m in NOINDENT_TEXTBF_REMARK_PATTERN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body or len(body) < 10:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'NOINDENT_TEXTBF_REMARK_PATTERN',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    return _dedup(results)
