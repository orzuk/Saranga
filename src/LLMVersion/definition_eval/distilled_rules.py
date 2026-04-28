import re
from typing import List, Dict

# ============================================================
# Helper: clean LaTeX to plain text
# ============================================================

def _clean_latex(text: str) -> str:
    """Strip LaTeX commands to produce a simplified plain-text version."""
    s = text
    # Remove comments
    s = re.sub(r'(?<!\\)%.*', '', s)
    # Remove \label{...}
    s = re.sub(r'\\label\{[^}]*\}', '', s)
    # Replace \emph{X}, \textit{X}, \textbf{X}, \textsl{X}, \textrm{X}, \text{X} with X
    s = re.sub(r'\\(?:emph|textit|textbf|textsl|textrm|text|mathrm|mathbf|mathit|mathcal|mathbb|mathfrak|operatorname)\{([^}]*)\}', r'\1', s)
    # Replace {\em X} or {\it X} or {\bf X} or {\sl X} with X
    s = re.sub(r'\{\\(?:em|it|bf|sl|rm)\s+([^}]*)\}', r'\1', s)
    # Remove \cite{...}
    s = re.sub(r'~?\\cite\{[^}]*\}', '', s)
    # Remove \ref{...}, \eqref{...}
    s = re.sub(r'\\(?:eq)?ref\{[^}]*\}', '', s)
    # Remove \begin{...} and \end{...}
    s = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', s)
    # Remove common commands with no argument
    s = re.sub(r'\\(?:noindent|bigskip|medskip|smallskip|quad|qquad|hfill|vfill|centering|maketitle|par)\b', '', s)
    # Remove \command (single backslash commands without braces)
    s = re.sub(r'\\[a-zA-Z]+\b\s*', ' ', s)
    # Remove remaining braces
    s = re.sub(r'[{}]', '', s)
    # Collapse whitespace
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


# ============================================================
# Helper: check if a position is inside an excluded environment
# ============================================================

_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>proof|theorem|lemma|corollary|proposition|example)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is fully inside a proof/theorem/lemma/etc environment."""
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        env_start = m.start()
        env_end = m.end()
        if start >= env_start and end <= env_end:
            return True
    return False


# ============================================================
# Display math helpers — used to avoid truncation at periods inside math
# ============================================================

# Matches display math environments and inline display constructs
_DISPLAY_MATH_ENV = re.compile(
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline|displaymath|eqnarray|flalign|alignat)\*?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline|displaymath|eqnarray|flalign|alignat)\*?\}'
    r'|'
    r'\\\[.*?\\\]'
    r'|'
    r'\$\$.*?\$\$'
    r')',
    re.DOTALL
)


def _get_paragraph_at(text: str, pos: int) -> tuple:
    """Get the paragraph (delimited by blank lines) containing position pos.
    Returns (para_text, para_start, para_end)."""
    # Find paragraph boundaries (double newline)
    # Search backward for \n\n
    para_start = text.rfind('\n\n', 0, pos)
    if para_start == -1:
        para_start = 0
    else:
        para_start += 2  # skip the \n\n
    
    # Search forward for \n\n
    para_end = text.find('\n\n', pos)
    if para_end == -1:
        para_end = len(text)
    
    return text[para_start:para_end], para_start, para_end


# ============================================================
# Notation/definition environment pattern
# ============================================================

_NOTATION_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>notation|Notation|convention|Convention|terminology|Terminology)\}'
    r'(?:\[(?P<title>[^\]]*)\])?\s*'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)

# ============================================================
# Module-level compiled patterns for inline definitions
# ============================================================

# Keywords that signal mathematical/definitional content in "Let X be..." patterns
_DEFINITION_KEYWORDS = re.compile(
    r'\b(?:set|function|map|mapping|sequence|matrix|space|operator|'
    r'define|denote|notation|collection|family|class|group|ring|field|'
    r'graph|path|tree|partition|permutation|morphism|homomorphism|category|'
    r'module|algebra|filter|polynomial|coloring|labeling|orientation|'
    r'subgraph|network|metric|measure|norm|topology|bundle|sheaf|'
    r'functor|diagram|complex|chain|lattice|order|relation|structure|'
    r'manifold|variety|scheme|ideal|subspace|subalgebra|subgroup|'
    r'representation|character|vector|tensor|form|section|fiber|'
    r'cocycle|coboundary|resolution|extension|covering|quotient)\b',
    re.IGNORECASE
)

# P1: \textit{X} (ABBR) is a/an/the ... — term introduction via italics/bold/emph
# Captures through end of paragraph or multiple sentences up to \n\n
_P1_TEXTIT_IS = re.compile(
    r'(?P<full>'
    r'(?:\\textit|\\textbf|\\emph)\{(?P<name>[^}]{1,100})\}'
    r'(?:\s*\([^)]{1,80}\))?'          # optional abbreviation in parens
    r'(?:\s*~?\\cite\{[^}]*\})?'       # optional citation
    r'\s+is\s+(?:a|an|the)\s+'
    r'(?:(?!\n\n).)*'                   # everything up to paragraph boundary
    r')',
    re.DOTALL
)

# P2: "can be defined as follows:" or "is defined as follows:" + equation env + optional where clause
_P2_DEFINED_AS_FOLLOWS = re.compile(
    r'(?P<full>'
    r'(?P<preamble>(?:(?!\n\n).){1,300}?)'
    r'\s+(?:can\s+be\s+|is\s+)?defined\s+as\s+follows\s*:\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\})'
    r'(?:\s*,?\s*where\s+(?:(?!\n\n).)*)?'
    r')',
    re.DOTALL
)

# P3: "is defined by/as:" + equation env + optional where clause
_P3_DEFINED_BY_EQ = re.compile(
    r'(?P<full>'
    r'(?P<preamble>(?:(?!\n\n).){1,300}?)'
    r'(?:,\s*which\s+is|\s+is|\s+are)\s+defined\s+'
    r'(?:(?:for|in)\s+(?:(?!\n\n).){1,150}?\s+)?'
    r'(?:by|as)\s*:?\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\})'
    r'(?:\s*,?\s*where\s+(?:(?!\n\n).)*)?'
    r')',
    re.DOTALL
)

# P4: "A/An \emph{X} ... consists of / is a ... " — definitional introduction with emphasized term
# Captures the sentence and any following sentences in the same paragraph that continue the definition
_P4_EMPH_DEF = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=\n)|(?<=\.\s)|(?<=\.\n))\s*'
    r'(?:A|An|The)\s+'
    r'(?P<name>\\(?:emph|textit|textbf)\{[^}]+\}'
    r'(?:\s*\$[^$]*\$)?)'
    r'(?:(?!\n\n).){0,500}?'
    r'(?:consists?\s+of|is\s+(?:a\s+|an\s+|the\s+|obtained\s+|defined\s+)?)'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL | re.MULTILINE
)

# P5: "X is/are \emph{Y} if/when ..." — definition via emphasized term with conditional
_P5_IS_EMPH_IF = re.compile(
    r'(?P<full>'
    r'(?:(?:^|(?<=\n)|(?<=\.\s)|(?<=\.\n))\s*)?'
    r'(?P<subject>(?:(?!\n\n).){1,200}?)'
    r'\s+(?:is|are)\s+'
    r'\\(?:emph|textit|textbf)\{(?P<name>[^}]{1,80}?)\}\s*'
    r'(?:if|when|whenever|provided)\s+'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)

# P6: "is called a/an {\em Y}" or "is called a \emph{Y}" — passive definitional language
_P6_IS_CALLED = re.compile(
    r'(?P<full>'
    r'(?P<subject>(?:(?!\n\n).){1,200}?)'
    r'\s+is\s+(?:called|said\s+to\s+be)\s+'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:'
    r'\{\\(?:em|it|bf)\s+(?P<name1>[^}]+)\}'
    r'|'
    r'\\(?:emph|textit|textbf)\{(?P<name2>[^}]+)\}'
    r')'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)

# P7: "Let X be the category/set/..." with definition keywords
_P7_LET_BE = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=\n)|(?<=\.\s)|(?<=\.\n))\s*'
    r'[Ll]et\s+'
    r'(?P<name>\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})?)'
    r'\s+be\s+'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL | re.MULTILINE
)

# P8: "denote X as/by ..." or "Given ..., denote X as ..."
_P8_DENOTE = re.compile(
    r'(?P<full>'
    r'(?:(?:(?!\n\n).){0,250}?)'
    r'(?:(?:[Ww]e\s+)?(?:also\s+)?)?'
    r'(?:[Dd]enote|[Ww]rite)\s+'
    r'(?P<name>(?:\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})?|[A-Z][A-Za-z/]*)'
    r'(?:\s*(?:\$[^$]+\$|\\[a-zA-Z]+(?:\{[^}]*\})?)){0,3})'
    r'\s*(?:as|by|to\s+be|for)\s+'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)

# P9: "let us write X to denote ..."
_P9_WRITE_DENOTE = re.compile(
    r'(?P<full>'
    r'(?:[Ll]et\s+us|[Ww]e)\s+'
    r'(?:write|denote|use)\s+'
    r'(?P<name>(?:(?!\n\n).){1,150}?)'
    r'\s+(?:to\s+denote|to\s+mean|for)\s+'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)

# P10: "the definition of X. \begin{align*}...\end{align*}"
_P10_RECALL_DEF = re.compile(
    r'(?P<full>'
    r'(?:[Ww]e\s+(?:recall|give|provide|state|introduce)\s+(?:here\s+)?)?'
    r'[Tt]he\s+definition\s+of\s+(?:the\s+|a\s+|an\s+)?'
    r'(?P<name>(?:(?!\n\n)[^.]){1,80}?)'
    r'\s*\.\s*'
    r'(?:'
    r'\\begin\{(?:align|equation|gather|displaymath|multline|eqnarray|flalign)\*?\}'
    r'.*?'
    r'\\end\{(?:align|equation|gather|displaymath|multline|eqnarray|flalign)\*?\}'
    r'|'
    r'\\\[.*?\\\]'
    r'|'
    r'\$\$.*?\$\$'
    r')'
    r')',
    re.DOTALL
)

# P11: "(Let us) consider/introduce the [noun] X defined by/as ..."
_P11_CONSIDER_DEFINED = re.compile(
    r'(?P<full>'
    r'(?:[Ll]et\s+us\s+)?(?:consider|introduce)\s+'
    r'(?:the\s+)?'
    r'(?:map|function|set|space|operator|sequence|matrix|mapping|quantity|'
    r'variable|transformation|measure|metric|norm|field|family|class|'
    r'functional|form|object|structure)\s+'
    r'(?P<name>(?:\$[^$]+\$|[A-Za-z\\{}_^]+))'
    r'(?:(?!\n\n).){0,300}?'
    r'\s+defined\s+(?:by|as)'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)

# P12: "X can be written as / expressed as / is given by" followed by display math
_P12_WRITTEN_AS = re.compile(
    r'(?P<full>'
    r'(?:(?:^|(?<=\n)|(?<=\.\s)|(?<=\.\n))\s*)?'
    r'(?:(?:(?!\n\n).){1,200}?)'
    r'\s+(?:can\s+be\s+(?:written|expressed|represented)|is\s+given)\s+(?:as|by)\s*'
    r'(?:'
    r'\\begin\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\}'
    r'|'
    r'\\\[.*?\\\]'
    r'|'
    r'\$\$.*?\$\$'
    r')'
    r'(?:\s*,?\s*where\s+(?:(?!\n\n).)*)?'
    r')',
    re.DOTALL | re.MULTILINE
)

# P13: Paragraph with multiple \emph{} definitions and display math
# Catches blocks like: "An \emph{orientation} ... An orientation ... is \emph{acyclic} if ..."
_P13_EMPH_BLOCK = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=\n\n))'
    r'(?=(?:(?!\n\n).)*\\(?:emph|textit|textbf)\{)'  # must contain \emph in first line area
    r'(?:An?\s+|The\s+)'
    r'(?:(?!\n\n).)*'                                  # rest of paragraph
    r')',
    re.DOTALL | re.MULTILINE
)

# P14: The \emph{X} to $\omega$ ... is the ... defined by ...
_P14_EMPH_DEFINED_BY = re.compile(
    r'(?P<full>'
    r'[Tt]he\s+\\(?:emph|textit|textbf)\{(?P<name>[^}]{1,80})\}'
    r'(?:(?!\n\n).){0,300}?'
    r'(?:defined\s+(?:by|as)|:=)'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)


# ============================================================
# Main extraction function
# ============================================================

def extract_distilled_definition(text: str) -> List[dict]:
    """Extract definition structures from LaTeX source text.
    
    Returns a list of dicts with keys: raw_latex, clean_text, name, env_name.
    """
    results = []
    used_spans = []  # list of (start, end) tuples for deduplication
    
    def _overlaps(start: int, end: int) -> bool:
        """Check if a span significantly overlaps with already captured spans."""
        for s, e in used_spans:
            # Compute overlap
            overlap_start = max(start, s)
            overlap_end = min(end, e)
            if overlap_start < overlap_end:
                overlap_len = overlap_end - overlap_start
                span_len = end - start
                existing_len = e - s
                # If either span contains more than 50% overlap
                if overlap_len > 0.5 * span_len or overlap_len > 0.5 * existing_len:
                    return True
        return False
    
    def _add_result(match_obj, start_offset: int, name: str = None, raw: str = None):
        """Add a result if it doesn't overlap with existing results and isn't in excluded env."""
        if raw is None:
            raw = match_obj.group('full')
        
        if match_obj is not None:
            abs_start = start_offset + match_obj.start()
            abs_end = start_offset + match_obj.end()
        else:
            abs_start = start_offset
            abs_end = start_offset + len(raw)
        
        # Skip if inside excluded environment
        if _inside_excluded_env(text, abs_start, abs_end):
            return False
        
        # Skip if overlaps
        if _overlaps(abs_start, abs_end):
            return False
        
        # Skip very short matches (likely false positives)
        stripped = raw.strip()
        if len(stripped) < 30:
            return False
        
        used_spans.append((abs_start, abs_end))
        results.append({
            'raw_latex': raw.strip(),
            'clean_text': _clean_latex(raw),
            'name': name.strip() if name else None,
            'env_name': 'distilled',
        })
        return True
    
    def _extract_name_from_match(m, name_keys=('name', 'name1', 'name2')):
        for k in name_keys:
            try:
                val = m.group(k)
                if val:
                    return val.strip()
            except IndexError:
                continue
        return None
    
    # ---- Phase 0: Notation/Convention environments ----
    for m in _NOTATION_ENV_PATTERN.finditer(text):
        body = m.group('body').strip()
        name = m.group('title')
        _add_result(None, m.start(), name=name, raw=m.group(0))
    
    # ---- Phase 1: Subsection-heading-introduced definitions ----
    # Pattern: \subsection{Term Name}\n\n <definition paragraph>
    # This is common for e.g. \subsection{Shapley Additive Explanation}\n\n \textit{...} is a ...
    _subsection_def = re.compile(
        r'\\subsection\{(?P<secname>[^}]+)\}\s*\n\s*\n'
        r'(?P<full>(?:(?!\n\n(?=\\(?:sub)?section)).)+)',
        re.DOTALL
    )
    for m in _subsection_def.finditer(text):
        body = m.group('full').strip()
        # Only accept if body contains definitional signals
        if (re.search(r'\\(?:emph|textit|textbf)\{', body) or
            re.search(r'(?:is\s+(?:a|an|the)\s+|consists?\s+of|defined\s+)', body)):
            # For the SHAP case: capture up to end of paragraph block (allowing multiple equations)
            # Extend to capture subsequent equation blocks and where clauses
            extended = body
            _add_result(None, m.start('full'), name=m.group('secname'), raw=extended)
    
    # ---- Phase 2: Inline patterns ----
    
    # P1: \textit{X} (ABBR) is a method/technique...
    for m in _P1_TEXTIT_IS.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # P2: "defined as follows:" + equation
    for m in _P2_DEFINED_AS_FOLLOWS.finditer(text):
        _add_result(m, 0, name=None)
    
    # P3: "is defined by/as:" + equation
    for m in _P3_DEFINED_BY_EQ.finditer(text):
        _add_result(m, 0, name=None)
    
    # P4: "A/An \emph{X} ... consists of / is a ..."
    for m in _P4_EMPH_DEF.finditer(text):
        name = _extract_name_from_match(m)
        # Clean the name: strip \emph{...} wrapper
        if name:
            cleaned_name = re.sub(r'\\(?:emph|textit|textbf)\{([^}]+)\}', r'\1', name)
            name = cleaned_name.strip()
        _add_result(m, 0, name=name)
    
    # P5: "X is/are \emph{Y} if ..."
    for m in _P5_IS_EMPH_IF.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # P6: "is called a {\em Y}" or "is called a \emph{Y}"
    for m in _P6_IS_CALLED.finditer(text):
        name = _extract_name_from_match(m, ('name1', 'name2'))
        _add_result(m, 0, name=name)
    
    # P7: "Let X be the ..." with definition keywords
    for m in _P7_LET_BE.finditer(text):
        full = m.group('full')
        if _DEFINITION_KEYWORDS.search(full):
            name = m.group('name')
            _add_result(m, 0, name=name)
    
    # P8: "denote X as ..."
    for m in _P8_DENOTE.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # P9: "let us write X to denote ..."
    for m in _P9_WRITE_DENOTE.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # P10: "the definition of X. \begin{align*}..."
    for m in _P10_RECALL_DEF.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # P11: "consider the map X defined by ..."
    for m in _P11_CONSIDER_DEFINED.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # P12: "X can be written as ..." + display math
    for m in _P12_WRITTEN_AS.finditer(text):
        _add_result(m, 0, name=None)
    
    # P14: "The \emph{X} ... defined by ..."
    for m in _P14_EMPH_DEFINED_BY.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # ---- Phase 3: Multi-sentence emph blocks ----
    # Look for paragraphs that start with "A/An" and contain multiple \emph definitions
    # This catches test cases 5 (k-coloring) and 6 (orientation, acyclic, compatible)
    _para_split = re.compile(r'\n\s*\n')
    paragraphs = _para_split.split(text)
    offset = 0
    for para in paragraphs:
        para_start = text.find(para, offset)
        if para_start == -1:
            para_start = offset
        offset = para_start + len(para)
        
        stripped = para.strip()
        if not stripped:
            continue
        
        # Count \emph occurrences
        emph_count = len(re.findall(r'\\(?:emph|textit|textbf)\{', stripped))
        
        if emph_count >= 2:
            # Check if starts with definitional pattern
            if re.match(r'\s*(?:A|An|The)\s+', stripped):
                # Check for definitional content
                has_def_signal = bool(re.search(
                    r'(?:consists?\s+of|is\s+(?:a\s+|an\s+|the\s+|obtained|defined)|'
                    r'are\s+(?:called|said)|(?:if|when)\s+)',
                    stripped
                ))
                if has_def_signal:
                    # Extract the name from first \emph
                    first_emph = re.search(r'\\(?:emph|textit|textbf)\{([^}]+)\}', stripped)
                    name = first_emph.group(1) if first_emph else None
                    _add_result(None, para_start, name=name, raw=stripped)
        
        # Also check for single \emph paragraphs that look definitional
        elif emph_count == 1:
            # "A directed graph ... is \emph{strongly connected} if ..."
            if re.match(r'\s*(?:A|An|The)\s+', stripped):
                if re.search(r'(?:is|are)\s+\\(?:emph|textit|textbf)\{[^}]+\}\s*(?:if|when|whenever)', stripped):
                    first_emph = re.search(r'\\(?:emph|textit|textbf)\{([^}]+)\}', stripped)
                    name = first_emph.group(1) if first_emph else None
                    _add_result(None, para_start, name=name, raw=stripped)
    
    # ---- Phase 4: "A coloring c and an orientation..." type definitions that span a paragraph ----
    # with display math in the middle and \emph
    _intercompat_pattern = re.compile(
        r'(?P<full>'
        r'(?:A|An)\s+(?:(?!\n\n).){1,100}'
        r'\\(?:emph|textit|textbf)\{(?P<name>[^}]+)\}'
        r'\s+if\s+'
        r'(?:(?!\n\n).)*'
        r'(?:\\\[.*?\\\]|\\begin\{(?:equation|align)\*?\}.*?\\end\{(?:equation|align)\*?\})'
        r'(?:(?!\n\n).)*'
        r')',
        re.DOTALL
    )
    for m in _intercompat_pattern.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # ---- Phase 5: Catch "Shapley Additive Explanation" style ----
    # \textit{X} (ABBR)~\cite{...} is a method ... with multiple equation environments
    # This extends P1 to capture content across multiple equation blocks
    _p1_extended = re.compile(
        r'(?P<full>'
        r'(?:\\textit|\\textbf|\\emph)\{(?P<name>[^}]{1,100})\}'
        r'(?:\s*\([^)]{1,80}\))?'
        r'(?:\s*~?\\cite\{[^}]*\})?'
        r'\s+is\s+(?:a|an|the)\s+'
        r'(?:(?!\n\n).)*'
        r'(?:\n(?!\n)(?:(?!\n\n).)*)*'  # allow crossing single newlines, stop at double
        r')',
        re.DOTALL
    )
    for m in _p1_extended.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # ---- Phase 6: Extended "defined as follows" that captures where clause across lines ----
    _p2_extended = re.compile(
        r'(?P<full>'
        r'(?:(?!\n\n).){1,400}?'
        r'(?:can\s+be\s+|is\s+)?defined\s+as\s+follows\s*:\s*'
        r'\\begin\{(?:equation|align|gather|multline)\*?\}'
        r'.*?'
        r'\\end\{(?:equation|align|gather|multline)\*?\}'
        r'(?:\s*,?\s*where\s+(?:(?!\n\n).)*)?'
        r')',
        re.DOTALL
    )
    for m in _p2_extended.finditer(text):
        _add_result(m, 0, name=None)
    
    # ---- Phase 7: "Given ... denote ... as ..." single sentence across paragraph ----
    _given_denote = re.compile(
        r'(?P<full>'
        r'(?:^|(?<=\n\n))\s*'
        r'Given\s+(?:(?!\n\n).){1,300}?'
        r'(?:denote|write)\s+'
        r'(?P<name>\$[^$]+\$|[A-Z][^,]{0,60}?)'
        r'\s+(?:as|by)\s+'
        r'(?:(?!\n\n).)*'
        r')',
        re.DOTALL | re.MULTILINE
    )
    for m in _given_denote.finditer(text):
        name = m.group('name')
        _add_result(m, 0, name=name)
    
    # Final deduplication: if two results have nearly identical raw_latex, keep the longer one
    if len(results) > 1:
        deduped = []
        results_sorted = sorted(results, key=lambda r: len(r['raw_latex']), reverse=True)
        kept_texts = []
        for r in results_sorted:
            is_dup = False
            for kept in kept_texts:
                # Check if one is a substring of another
                if r['raw_latex'] in kept or kept in r['raw_latex']:
                    is_dup = True
                    break
                # Check character overlap
                shorter = min(len(r['raw_latex']), len(kept))
                longer = max(len(r['raw_latex']), len(kept))
                if shorter > 0.7 * longer:
                    # Check if they share a large common prefix
                    common = 0
                    for c1, c2 in zip(r['raw_latex'], kept):
                        if c1 == c2:
                            common += 1
                        else:
                            break
                    if common > 0.5 * shorter:
                        is_dup = True
                        break
            if not is_dup:
                deduped.append(r)
                kept_texts.append(r['raw_latex'])
        results = deduped
    
    return results
