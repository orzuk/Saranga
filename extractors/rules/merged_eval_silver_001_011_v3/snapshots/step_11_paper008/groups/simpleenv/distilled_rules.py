import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup and return plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove display math environments
    text = re.sub(r'\\begin\{(?:equation|align|eqnarray|gather|multline|flalign|alignat)\*?\}.*?\\end\{(?:equation|align|eqnarray|gather|multline|flalign|alignat)\*?\}', ' ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*?\$', ' ', text, flags=re.DOTALL)
    # Remove common formatting commands
    text = re.sub(r'\\(?:textbf|textit|emph|textrm|textsc|texttt|mathbf|mathit|mathrm|mathcal|mathbb|mathfrak)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\{\\(?:bf|it|sc|rm|tt)\s+([^}]*)\}', r'\1', text)
    # Remove \label, \ref, \cite etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*|citeA|citeNP)\{[^}]*\}', '', text)
    # Remove \noindent, \par, spacing commands
    text = re.sub(r'\\(?:noindent|par|medskip|bigskip|smallskip|vspace|hspace)\s*(?:\{[^}]*\})?', ' ', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\s*(?:\{[^}]*\})*', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside a proof environment."""
    excluded = ['proof', 'Proof']
    for env in excluded:
        pattern = re.compile(
            r'\\begin\{' + re.escape(env) + r'\}.*?\\end\{' + re.escape(env) + r'\}',
            re.DOTALL
        )
        for m in pattern.finditer(text):
            if m.start() <= start and end <= m.end():
                return True
    return False


def _extract_label(text: str):
    """Extract \label{...} from text, return (label_str or None, text)."""
    m = re.search(r'\\label\{([^}]*)\}', text)
    if m:
        return m.group(1), text
    return None, text


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# 1. \noindent{\sc Remark[s]?.} ... body until next structural boundary
_SC_REMARK_SINGLE = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}\s*'
    r'(?P<body>(?:(?!\\noindent\s*\{\\sc|\\(?:section|subsection|subsubsection|chapter|appendix)\b|\\begin\{).)+)',
    re.DOTALL | re.IGNORECASE
)

# 2. \noindent{\sc Remarks.} followed by \begin{list}...\end{list} with \item entries
# PRUNED — FP on paper004
# _SC_REMARKS_LIST_BLOCK = re.compile(
#     r'\\noindent\s*\{\\sc\s+Remarks?\.?\}\s*'
#     r'(?P<list_env>\\begin\{list\}.*?\\end\{list\})',
#     re.DOTALL | re.IGNORECASE
# )
_LIST_ITEM = re.compile(
    r'\\item\s*(?P<body>.*?)(?=\\item\b|\\end\{list\})',
    re.DOTALL
)

# 3. \begin{description}...\item[Assumption/Remark/Example ...]...\end{description}
_DESCRIPTION_BLOCK = re.compile(
    r'\\begin\{description\}'
    r'(?P<body>.*?)'
    r'\\end\{description\}',
    re.DOTALL | re.IGNORECASE
)
_DESCRIPTION_ITEM = re.compile(
    r'\\item\[(?P<label>[^\]]*)\]\s*(?P<body>.*?)(?=\\item\[|\\end\{description\})',
    re.DOTALL
)

# 4. \noindent {\bf Assumption/Remark/Example N.} {\it body} pattern
_NOINDENT_BF_BLOCK = re.compile(
    r'\\noindent\s*'
    r'(?:\{\\bf\s+|\\textbf\{)'
    r'(?P<label>(?:Assumption|Remark|Example|Note|Observation)[^.}]*)'
    r'[.}]'
    r'[^{]*'
    r'(?:\{\\it\s+|\\textit\{|\\emph\{)?'
    r'(?P<body>.*?)'
    r'(?=\\noindent\b|\n\s*\n\s*\n|\\(?:section|subsection|subsubsection|chapter|appendix)\b|\\begin\{|$)',
    re.DOTALL
)

# 5. \textbf{Remark...} inline (not in env), body until next blank line or structural boundary
_TEXTBF_REMARK = re.compile(
    r'\\textbf\{(?P<keyword>Remark[s]?)[^}]*\}\s*:?\s*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b).)+)',
    re.DOTALL | re.IGNORECASE
)

# 6. \textbf{Example...} inline (not in env)
# PRUNED — FP on paper006
# _TEXTBF_EXAMPLE = re.compile(
#     r'\\textbf\{(?P<keyword>Example[s]?)[^}]*\}\s*:?\s*'
#     r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b).)+)',
#     re.DOTALL | re.IGNORECASE
# )

# 7. \textbf{Assumption...} inline (not in env)
_TEXTBF_ASSUMPTION = re.compile(
    r'\\textbf\{(?P<keyword>Assumption[s]?)[^}]*\}\s*:?\s*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter)\b).)+)',
    re.DOTALL | re.IGNORECASE
)

# 8. \emph{Remark.} or \textit{Remark.} inline label
_EMPH_REMARK = re.compile(
    r'(?:\\emph|\\textit)\{(?P<keyword>Remark|Note|Observation)\.?\}\s*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph)\b|\n\s*\n).)+)',
    re.DOTALL | re.IGNORECASE
)

# 9. \emph{Example.} or \textit{Example.} inline label
_EMPH_EXAMPLE = re.compile(
    r'(?:\\emph|\\textit)\{(?P<keyword>Example|Illustration)\.?\}\s*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|paragraph)\b|\n\s*\n).)+)',
    re.DOTALL | re.IGNORECASE
)

# 10. {\bf Remark.} without \noindent prefix
_BF_REMARK_STANDALONE = re.compile(
    r'\{\\bf\s+(?P<keyword>Remark[s]?)\.?\}\s*'
    r'(?P<body>(?:(?!\\(?:begin|end|section|subsection|subsubsection|chapter)\b|\n\s*\n\s*\n).)+)',
    re.DOTALL | re.IGNORECASE
)

# 11. ^Remark. or ^Note. at start of paragraph (undecorated keyword)
_BARE_REMARK_PARA = re.compile(
    r'(?:^|\n\n)(?P<keyword>Remark|Note|Observation)\.\s+'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:begin|end|section|subsection|subsubsection|paragraph)\b).)+)',
    re.DOTALL
)

# 12. ^Example. at start of paragraph (undecorated keyword)
_BARE_EXAMPLE_PARA = re.compile(
    r'(?:^|\n\n)(?P<keyword>Example|Illustration)\.\s+'
    r'(?P<body>(?:(?!\n\s*\n|\\(?:begin|end|section|subsection|subsubsection|paragraph)\b).)+)',
    re.DOTALL
)

# 13. \begin{remark*}...\end{remark*} and similar starred variants not in base map
_STARRED_REMARK = re.compile(
    r'\\begin\{(?P<env>remark\*|Remark\*|note\*|Note\*|observation\*|Observation\*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

# 14. \begin{example*}...\end{example*} starred variants
_STARRED_EXAMPLE = re.compile(
    r'\\begin\{(?P<env>example\*|Example\*|exmp\*|exmpl\*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

# 15. \begin{assumption*}...\end{assumption*} starred variants
_STARRED_ASSUMPTION = re.compile(
    r'\\begin\{(?P<env>assumption\*|Assumption\*|assumptions\*|Assumptions\*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

# 16. Additional environment names that map to example/remark/assumption
_EXTRA_ENV_REMARK = re.compile(
    r'\\begin\{(?P<env>rmk|Rmk|remark[0-9]+|obs|Obs)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

_EXTRA_ENV_EXAMPLE = re.compile(
    r'\\begin\{(?P<env>exmp|exmpl|running-?example|illustration|Illustration)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

_EXTRA_ENV_ASSUMPTION = re.compile(
    r'\\begin\{(?P<env>hyp|Hyp|hypothesis|Hypothesis|cond|Cond|condition|Condition)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Subtype determination helpers
# ---------------------------------------------------------------------------

_KEYWORD_TO_SUBTYPE: Dict[str, str] = {
    'remark': 'remark', 'remarks': 'remark', 'rmk': 'remark',
    'note': 'remark', 'notes': 'remark', 'observation': 'remark',
    'observations': 'remark', 'obs': 'remark',
    'example': 'example', 'examples': 'example', 'exmp': 'example',
    'exmpl': 'example', 'illustration': 'example',
    'assumption': 'assumption', 'assumptions': 'assumption',
    'hyp': 'assumption', 'hypothesis': 'assumption',
    'cond': 'assumption', 'condition': 'assumption',
}

def _subtype_from_keyword(kw: str) -> str:
    return _KEYWORD_TO_SUBTYPE.get(kw.lower().rstrip('*').strip(), 'remark')

def _subtype_from_label(label: str) -> str:
    label_l = label.lower()
    if re.search(r'\bassumption', label_l):
        return 'assumption'
    if re.search(r'\bexample|\billustration', label_l):
        return 'example'
    if re.search(r'\bremark|\bnote|\bobservation', label_l):
        return 'remark'
    return 'remark'

# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex spans overlap with a previously seen span."""
    seen_spans = []
    out = []
    for r in results:
        start = r.get('_start', -1)
        end = r.get('_end', -1)
        if start == -1:
            out.append(r)
            continue
        overlaps = False
        for s, e in seen_spans:
            if not (end <= s or start >= e):
                overlaps = True
                break
        if not overlaps:
            seen_spans.append((start, end))
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    def _make(raw: str, name, env_name: str, rule_name: str,
               structure_type: str, start: int, end: int) -> dict:
        return {
            'raw_latex': raw.strip(),
            'clean_text': _clean_latex(raw),
            'name': name,
            'env_name': 'distilled',
            'rule_name': rule_name,
            'structure_type': structure_type,
            '_start': start,
            '_end': end,
        }

    # ------------------------------------------------------------------
    # Rule: _SC_REMARK_SINGLE
    # \noindent{\sc Remark.} body (single paragraph, no list)
    # ------------------------------------------------------------------
    for m in _SC_REMARK_SINGLE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make(body, None, 'distilled', '_SC_REMARK_SINGLE',
                             'remark', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _SC_REMARKS_LIST_BLOCK
    # \noindent{\sc Remarks.} \begin{list}...\end{list} -> each \item is a remark
#     # ------------------------------------------------------------------
#     for list_m in _SC_REMARKS_LIST_BLOCK.finditer(text):
#         if _inside_excluded_env(text, list_m.start(), list_m.end()):
#             continue
#         list_body = list_m.group('list_env')
#         for item_m in _LIST_ITEM.finditer(list_body):
#             body = item_m.group('body').strip()
#             if not body:
#                 continue
#             # approximate source position
#             results.append(_make(body, None, 'distilled', '_SC_REMARKS_LIST_BLOCK',
#                                  'remark', list_m.start(), list_m.end()))

    # ------------------------------------------------------------------
    # Rule: _DESCRIPTION_BLOCK
    # \begin{description}\item[Assumption/Remark/Example N] body \end{description}
    # ------------------------------------------------------------------
    for desc_m in _DESCRIPTION_BLOCK.finditer(text):
        if _inside_excluded_env(text, desc_m.start(), desc_m.end()):
            continue
        block_body = desc_m.group('body')
        for item_m in _DESCRIPTION_ITEM.finditer(block_body):
            item_label = item_m.group('label').strip()
            item_body = item_m.group('body').strip()
            if not item_body:
                continue
            subtype = _subtype_from_label(item_label)
            # Only emit if it's one of our target subtypes
            if subtype not in ('remark', 'example', 'assumption'):
                continue
            results.append(_make(item_body, item_label if item_label else None,
                                 'distilled', '_DESCRIPTION_BLOCK',
                                 subtype, desc_m.start(), desc_m.end()))

    # ------------------------------------------------------------------
    # Rule: _NOINDENT_BF_BLOCK
    # \noindent {\bf Assumption/Remark/Example N.} {\it body}
    # ------------------------------------------------------------------
    for m in _NOINDENT_BF_BLOCK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        label_text = m.group('label').strip()
        body = m.group('body').strip()
        # Strip trailing closing brace from \it{...} wrapper
        body = re.sub(r'\}\s*$', '', body).strip()
        if not body:
            continue
        subtype = _subtype_from_label(label_text)
        if subtype not in ('remark', 'example', 'assumption'):
            continue
        results.append(_make(body, label_text, 'distilled', '_NOINDENT_BF_BLOCK',
                             subtype, m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _TEXTBF_REMARK
    # \textbf{Remark:} inline body
    # ------------------------------------------------------------------
    for m in _TEXTBF_REMARK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make(body, None, 'distilled', '_TEXTBF_REMARK',
                             'remark', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _TEXTBF_EXAMPLE
    # \textbf{Example:} inline body
#     # ------------------------------------------------------------------
#     for m in _TEXTBF_EXAMPLE.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         body = m.group('body').strip()
#         if not body:
#             continue
#         results.append(_make(body, None, 'distilled', '_TEXTBF_EXAMPLE',
#                              'example', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _TEXTBF_ASSUMPTION
    # \textbf{Assumption:} inline body
    # ------------------------------------------------------------------
    for m in _TEXTBF_ASSUMPTION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make(body, None, 'distilled', '_TEXTBF_ASSUMPTION',
                             'assumption', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _EMPH_REMARK
    # \emph{Remark.} or \textit{Remark.} inline label
    # ------------------------------------------------------------------
    for m in _EMPH_REMARK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make(body, None, 'distilled', '_EMPH_REMARK',
                             'remark', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _EMPH_EXAMPLE
    # \emph{Example.} or \textit{Example.} inline label
    # ------------------------------------------------------------------
    for m in _EMPH_EXAMPLE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make(body, None, 'distilled', '_EMPH_EXAMPLE',
                             'example', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _BF_REMARK_STANDALONE
    # {\bf Remark.} body (without \noindent)
    # ------------------------------------------------------------------
    for m in _BF_REMARK_STANDALONE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make(body, None, 'distilled', '_BF_REMARK_STANDALONE',
                             'remark', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _BARE_REMARK_PARA
    # Paragraph starting with "Remark." or "Note." undecorated
    # ------------------------------------------------------------------
    for m in _BARE_REMARK_PARA.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make(body, None, 'distilled', '_BARE_REMARK_PARA',
                             'remark', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _BARE_EXAMPLE_PARA
    # Paragraph starting with "Example." undecorated
    # ------------------------------------------------------------------
    for m in _BARE_EXAMPLE_PARA.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if not body:
            continue
        results.append(_make(body, None, 'distilled', '_BARE_EXAMPLE_PARA',
                             'example', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _STARRED_REMARK
    # \begin{remark*}...\end{remark*} and similar
    # ------------------------------------------------------------------
    for m in _STARRED_REMARK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        if not body:
            continue
        results.append(_make(body, opt.strip() if opt else None,
                             'distilled', '_STARRED_REMARK',
                             'remark', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _STARRED_EXAMPLE
    # \begin{example*}...\end{example*}
    # ------------------------------------------------------------------
    for m in _STARRED_EXAMPLE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        if not body:
            continue
        results.append(_make(body, opt.strip() if opt else None,
                             'distilled', '_STARRED_EXAMPLE',
                             'example', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _STARRED_ASSUMPTION
    # \begin{assumption*}...\end{assumption*}
    # ------------------------------------------------------------------
    for m in _STARRED_ASSUMPTION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        if not body:
            continue
        results.append(_make(body, opt.strip() if opt else None,
                             'distilled', '_STARRED_ASSUMPTION',
                             'assumption', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _EXTRA_ENV_REMARK
    # Non-standard remark environment names
    # ------------------------------------------------------------------
    for m in _EXTRA_ENV_REMARK.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        if not body:
            continue
        results.append(_make(body, opt.strip() if opt else None,
                             'distilled', '_EXTRA_ENV_REMARK',
                             'remark', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _EXTRA_ENV_EXAMPLE
    # Non-standard example environment names
    # ------------------------------------------------------------------
    for m in _EXTRA_ENV_EXAMPLE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        if not body:
            continue
        results.append(_make(body, opt.strip() if opt else None,
                             'distilled', '_EXTRA_ENV_EXAMPLE',
                             'example', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Rule: _EXTRA_ENV_ASSUMPTION
    # Non-standard assumption environment names
    # ------------------------------------------------------------------
    for m in _EXTRA_ENV_ASSUMPTION.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        opt = m.group('opt')
        if not body:
            continue
        results.append(_make(body, opt.strip() if opt else None,
                             'distilled', '_EXTRA_ENV_ASSUMPTION',
                             'assumption', m.start(), m.end()))

    # ------------------------------------------------------------------
    # Deduplicate and clean up internal keys
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
