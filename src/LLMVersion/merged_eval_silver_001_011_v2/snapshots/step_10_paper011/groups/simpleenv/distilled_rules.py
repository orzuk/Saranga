import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Minimal LaTeX -> plain text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands, keeping their arguments
    text = re.sub(r'\\(?:textbf|textit|emph|text|mathrm|mathbf|mathit|noindent)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:label|ref|eqref|cite[A-Za-z]*)\{[^}]*\}', '', text)
    text = re.sub(r'\\(?:sc|bf|it|rm|tt)\b\s*', '', text)
    # Remove \begin/\end of math environments
    text = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', text)
    # Remove display math delimiters
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', '[MATH]', text)
    # Remove leftover braces from commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', text)
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Environments to exclude (matches inside these will be dropped)
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|theorem|lemma|proposition|corollary|claim|definition|algorithm|figure|table)\}',
    re.IGNORECASE
)
_EXCLUDED_ENV_CLOSE_RE = re.compile(
    r'\\end\{(proof|theorem|lemma|proposition|corollary|claim|definition|algorithm|figure|table)\}',
    re.IGNORECASE
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside an excluded environment."""
    # Count opens and closes before start
    before = text[:start]
    opens = len(_EXCLUDED_ENV_RE.findall(before))
    closes = len(_EXCLUDED_ENV_CLOSE_RE.findall(before))
    depth = opens - closes
    return depth > 0


# ---------------------------------------------------------------------------
# Pattern 1: \textbf{Remark...} inline bold remark (paper011 style)
# ---------------------------------------------------------------------------
TEXTBF_REMARK_RE = re.compile(
    r'\\textbf\{Remark[s]?[:\s.]*\}\s*(?P<body>.*?)(?=\n\s*\n\s*\n|\n\s*\n\s*\\(?:begin|end|section|subsection|paragraph|textbf)|\\begin\{|\\end\{(?!equation|align|array)|\\section|\\subsection|\Z)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 2: {\bf Remark.} style bold remark (paper002 style)
# ---------------------------------------------------------------------------
BF_REMARK_RE = re.compile(
    r'\{\\bf\s+Remarks?\.?\}\s*(?P<body>.*?)(?=\n\s*\n\s*\n|\n\s*\n\s*\\(?:section|subsection|begin)|\\(?:sub)*section\{|\\begin\{(?!equation|align|array|split|gather|multline)|\Z)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 3: \noindent{\sc Remark[s].} single block (paper004 style)
# ---------------------------------------------------------------------------
SC_REMARK_SINGLE_RE = re.compile(
    r'\\noindent\s*\{\\sc\s+Remark\.?\}\s*(?P<body>.*?)(?=\n\s*\n\s*\\(?:section|subsection|noindent|begin|appendix)|\n\s*\n\s*\n|\\(?:sub)*section\{|\Z)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 4: \noindent{\sc Remarks.} followed by \begin{list}...\end{list}
#            (paper004 style list of remarks)
# ---------------------------------------------------------------------------
SC_REMARKS_LIST_RE = re.compile(
    r'\\noindent\s*\{\\sc\s+Remarks?\.?\}[.:]?\s*(?P<list>\\begin\{list\}.*?\\end\{list\})',
    re.DOTALL
)
ITEM_SPLIT_RE = re.compile(r'\\item\s*')

# ---------------------------------------------------------------------------
# Pattern 5: \begin{description} with \item[Assumption ...] (paper004 style)
# ---------------------------------------------------------------------------
DESCRIPTION_ENV_RE = re.compile(
    r'\\begin\{description\}(.*?)\\end\{description\}',
    re.DOTALL
)
DESC_ASSUMPTION_ITEM_RE = re.compile(
    r'\\item\s*\[(?:Assumption|assumption)[^\]]*\]\s*(?P<body>.*?)(?=\\item\s*\[|\Z)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 6: \emph{Remark.} inline italic remark (paper005 style)
# ---------------------------------------------------------------------------
EMPH_REMARK_RE = re.compile(
    r'\\emph\{Remarks?\.?\}\.?\s*(?P<body>.*?)(?=\n\s*\n\s*\n|\n\s*\n\s*\\(?:begin|end|section|subsection)|\\begin\{(?!equation|align|array|split|gather|multline)|\Z)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 7: "We remark that" inline prose remark (paper006 style)
# ---------------------------------------------------------------------------
WE_REMARK_RE = re.compile(
    r'(?<!\w)We remark that\s+(?P<body>(?:(?!\n\s*\n).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 8: Bare paragraph remark after \\ (double newline context, paper001)
#            Specifically between \\\\ and next %\section or \subsubsection
#            These are floating recommendation/observation paragraphs.
# ---------------------------------------------------------------------------
# For paper001: paragraphs that are clearly "remark-like" standalone prose
# between \\\\\n\n ... \n\n% or \subsubsection
# We require the paragraph to not start with a LaTeX command.
BARE_DOUBLE_SLASH_REMARK_RE = re.compile(
    r'\\\\\s*\n\s*\n\s*(?P<body>(?:[A-Z][^\\%\n][^\n]*(?:\n(?![ \t]*\n)[^\n]*)*))(?=\s*\n\s*\n)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Pattern 9: Post-proof standalone paragraph remark (paper002 style)
# ---------------------------------------------------------------------------
POST_PROOF_REMARK_RE = re.compile(
    r'\\end\{proof\}\s*\n\s*\n(?P<body>(?:(?!\\(?:begin|end)\{|\\(?:sub)*section|\n\s*\n).)+)',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring duplicate or span overlaps."""
    if not results:
        return results
    # Sort by length descending (prefer longer/more complete matches)
    results = sorted(results, key=lambda x: len(x['raw_latex']), reverse=True)
    seen_texts = []
    out = []
    for r in results:
        body = r['raw_latex'].strip()
        if not body or len(body) < 30:
            continue
        # Check if this text is already covered by a previously accepted result
        duplicate = False
        for seen in seen_texts:
            # Overlap: if 80%+ of this body appears in a longer seen body
            if body in seen or seen in body:
                duplicate = True
                break
            # Fuzzy: first 80 chars match
            if len(body) > 80 and len(seen) > 80 and body[:80] == seen[:80]:
                duplicate = True
                break
        if not duplicate:
            out.append(r)
            seen_texts.append(body)
    return out


# ---------------------------------------------------------------------------
# Subtype classifier
# ---------------------------------------------------------------------------

def _classify_subtype(env_name: str, body: str, default: str = 'remark') -> str:
    env_lower = env_name.lower().rstrip('*')
    if 'assumption' in env_lower:
        return 'assumption'
    if 'example' in env_lower or 'exam' in env_lower:
        return 'example'
    if 'remark' in env_lower or 'note' in env_lower:
        return 'remark'
    # Check body for markers
    body_start = body[:200].lower()
    if 'assumption' in body_start:
        return 'assumption'
    if 'example' in body_start:
        return 'example'
    if 'remark' in body_start:
        return 'remark'
    return default


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule: TEXTBF_REMARK_RE — \textbf{Remark:} ... (paper011 style)
    # ------------------------------------------------------------------
    for m in TEXTBF_REMARK_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'TEXTBF_REMARK_RE',
            'structure_type': 'remark',
        })

    # ------------------------------------------------------------------
    # Rule: BF_REMARK_RE — {\bf Remark.} ... (paper002 style)
    # ------------------------------------------------------------------
    for m in BF_REMARK_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BF_REMARK_RE',
            'structure_type': 'remark',
        })

    # ------------------------------------------------------------------
    # Rule: SC_REMARK_SINGLE_RE — \noindent{\sc Remark.} (paper004 style, single)
    # ------------------------------------------------------------------
    for m in SC_REMARK_SINGLE_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'SC_REMARK_SINGLE_RE',
            'structure_type': 'remark',
        })

    # ------------------------------------------------------------------
    # Rule: SC_REMARKS_LIST_RE — \noindent{\sc Remarks.} \begin{list}...\end{list}
    #        Split on \item (paper004 style list)
    # ------------------------------------------------------------------
    for block_m in SC_REMARKS_LIST_RE.finditer(text):
        start = block_m.start()
        if _inside_excluded_env(text, start, block_m.end()):
            continue
        list_block = block_m.group('list')
        # Remove \begin{list}...first arg...second arg preamble before first \item
        parts = ITEM_SPLIT_RE.split(list_block)
        for part in parts[1:]:  # skip preamble
            # Each part runs until the next \item (already split)
            body = part.strip()
            # Remove trailing \end{list}
            body = re.sub(r'\\end\{list\}\s*$', '', body).strip()
            if not body or len(body) < 20:
                continue
            results.append({
                'raw_latex': body,
                'clean_text': _clean_latex(body),
                'name': None,
                'env_name': 'distilled',
                'rule_name': 'SC_REMARKS_LIST_RE',
                'structure_type': 'remark',
            })

    # ------------------------------------------------------------------
    # Rule: DESCRIPTION_ENV_RE — \begin{description} with \item[Assumption ...]
    #        (paper004 assumption style)
    # ------------------------------------------------------------------
    for block_m in DESCRIPTION_ENV_RE.finditer(text):
        start = block_m.start()
        if _inside_excluded_env(text, start, block_m.end()):
            continue
        block_body = block_m.group(1)
        for item_m in DESC_ASSUMPTION_ITEM_RE.finditer(block_body):
            body = item_m.group('body').strip()
            if not body or len(body) < 20:
                continue
            results.append({
                'raw_latex': body,
                'clean_text': _clean_latex(body),
                'name': None,
                'env_name': 'distilled',
                'rule_name': 'DESCRIPTION_ENV_RE',
                'structure_type': 'assumption',
            })

    # ------------------------------------------------------------------
    # Rule: EMPH_REMARK_RE — \emph{Remark.} ... (paper005 style)
    # ------------------------------------------------------------------
    for m in EMPH_REMARK_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'EMPH_REMARK_RE',
            'structure_type': 'remark',
        })

    # ------------------------------------------------------------------
    # Rule: WE_REMARK_RE — "We remark that ..." prose (paper006 style)
    # ------------------------------------------------------------------
    for m in WE_REMARK_RE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        # Reconstruct the full sentence including the signal phrase
        body = ('We remark that ' + m.group('body')).strip()
        if not body or len(body) < 30:
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'WE_REMARK_RE',
            'structure_type': 'remark',
        })

    # ------------------------------------------------------------------
    # Rule: POST_PROOF_REMARK_RE — standalone paragraph after \end{proof}
    #        (paper002 style)
    # ------------------------------------------------------------------
    for m in POST_PROOF_REMARK_RE.finditer(text):
        start, end = m.start(), m.end()
        body = m.group('body').strip()
        if not body or len(body) < 40:
            continue
        # Only accept if it doesn't look like it belongs to a theorem env
        if _inside_excluded_env(text, start, end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'POST_PROOF_REMARK_RE',
            'structure_type': 'remark',
        })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    return _deduplicate(results)
