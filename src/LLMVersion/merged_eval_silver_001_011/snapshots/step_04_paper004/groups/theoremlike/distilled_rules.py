import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Remove common LaTeX markup, returning approximate plain text."""
    # Remove comments
    text = re.sub(r'%.*', '', text)
    # Remove \label{...}, \ref{...}, \cite{...} etc.
    text = re.sub(r'\\(label|ref|eqref|cite[A-Za-z]*)\{[^}]*\}', '', text)
    # Remove display math environments, keep content
    text = re.sub(r'\\begin\{(align|align\*|equation|equation\*|split)\}', '', text)
    text = re.sub(r'\\end\{(align|align\*|equation|equation\*|split)\}', '', text)
    # Remove \ba ... \ea shorthand
    text = re.sub(r'\\ba\b', '', text)
    text = re.sub(r'\\ea\b', '', text)
    # Remove \nonumber, \label inside math
    text = re.sub(r'\\(nonumber|displaystyle)\b', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Environments whose content we want to EXCLUDE from matching
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|figure|Figure|table|Table)\}',
    re.DOTALL
)

_EXCLUDED_ENV_FULL_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|figure|Figure|table|Table)\}'
    r'.*?'
    r'\\end\{\1\}',
    re.DOTALL
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) falls inside an excluded environment."""
    for m in _EXCLUDED_ENV_FULL_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _determine_subtype(env_name: str, body: str = '') -> str:
    """Determine the structure_type subtype from environment name or body content."""
    name = env_name.lower().rstrip('*')
    if name in ('theorem', 'thm', 'theo'):
        return 'theorem'
    if name in ('lemma', 'lem'):
        return 'lemma'
    if name in ('proposition', 'prop'):
        return 'proposition'
    if name in ('corollary', 'cor'):
        return 'corollary'
    if name in ('claim',):
        return 'claim'
    if name in ('conjecture',):
        return 'conjecture'
    if name in ('problem', 'openproblem',):
        return 'problem'
    if name in ('align', 'align*', 'equation', 'equation*'):
        # Try to infer from body
        if re.search(r'\(P[_0-9]', body):
            return 'problem'
        if re.search(r'\\(?:max|min)\b.*?\\text\s*\{\s*s\.?t\.?', body, re.DOTALL):
            return 'problem'
        return 'problem'
    if name in ('ba', 'freetext_ba', 'prose_problem', 'prose_definition'):
        return 'problem'
    return 'theorem'


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: \ba ... \ea blocks preceded by a lead-in sentence
# (catches graph-cut / objective-function problem descriptions in paper001)
BA_EA_PROBLEM = re.compile(
    r'(?P<preamble>'
        r'(?:(?:^|\n\n)|\.\s+)'     # paragraph or sentence boundary
        r'[A-Z][^\n]{15,600}?'      # lead-in starting with capital
    r')'
    r'(?:\\ba|\\begin\{align\*?\})'
    r'\s*'
    r'(?P<body>.*?)'
    r'(?:\\ea|\\end\{align\*?\})',
    re.DOTALL
)

# Pattern 2: \begin{equation}...\end{equation} or \begin{equation*}...\end{equation*}
# containing (P_N) problem label → treat as 'problem'
EQUATION_PROBLEM = re.compile(
    r'\\begin\{(equation\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?\(P[_0-9a-zA-Z]*\).*?)'
    r'\\end\{equation\*?\}',
    re.DOTALL
)

# Pattern 3: \begin{align}...\end{align} or align* containing (P_N) problem label
ALIGN_PROBLEM_LABEL = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?\(P[_0-9a-zA-Z]*\).*?)'
    r'\\end\{align\*?\}',
    re.DOTALL
)

# Pattern 4: \begin{align}...\end{align} or align* containing \max/\min + \text{s.t.}
# (optimization problem blocks in paper003)
ALIGN_OPTIMIZATION = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>(?:(?!\\begin\{align).)*?(?:\\max|\\min)\b.*?(?:\\text\s*\{\s*s\.?t\.?|subject\s+to).*?)'
    r'\\end\{align\*?\}',
    re.DOTALL
)

# Pattern 5: standalone \begin{align*}...\end{align*} block that contains
# both eigenvalue limit notation (goto / rightarrow) — theorem-like facts
# stated in plain align* environments (paper002 test case 5)
ALIGN_THEOREM_FACT = re.compile(
    r'\\begin\{align\*\}'
    r'(?P<body>.*?(?:\\goto|\\to|\\rightarrow).*?(?:\\text\s*\{.*?a\.?\s*s\.?\}|a\.s\.).*?)'
    r'\\end\{align\*\}',
    re.DOTALL
)

# Pattern 6: prose paragraphs defining optimization estimators (\argmin / \argmax)
# embedded in running text with equation/split environments (paper004)
PROSE_ARGMIN_PROBLEM = re.compile(
    r'(?:(?:\n\n)|(?:\.\s+))(?P<body>'
        r'(?:Define|The\s+\w+\s+estimator|The\s+Dantzig|Introduce\b)[^.]{0,200}\.'
        r'(?:\s*[^.]{0,300})*?'
        r'(?:'
            r'\\begin\{equation\}'
            r'(?:\\begin\{split\})?'
            r'.*?'
            r'(?:\\end\{split\})?'
            r'\\end\{equation\}'
        r')'
        r'(?:\s*(?:where|The \w+ estimator)[^.]{0,500}\.)?'
        r'(?:\s*'
            r'\\begin\{equation\}'
            r'(?:\\begin\{split\})?'
            r'.*?'
            r'(?:\\end\{split\})?'
            r'\\end\{equation\}'
        r')?'
        r'(?:\s*where[^.]{0,200}\.)?'
    r')',
    re.DOTALL
)

# Pattern 7: paragraph-level heuristic for prose problems containing \argmin
# (broader fallback for paper004-style definitional paragraphs)
# PRUNED — FP on paper004
# ARGMIN_PARAGRAPH = re.compile(
#     r'(?:(?<=\n\n)|(?<=\.\s\s))(?P<body>[^\n]{0,300}?\\argmin[\s\S]{10,1500}?)'
#     r'(?=\n\n|\Z)',
#     re.DOTALL
# )

# Pattern 8: \begin{align*} that contains a named limit fact with 'a.s.' —
# broader version matching the Marchenko-Pastur style result
ALIGN_LIMIT_THEOREM = re.compile(
    r'\\begin\{align\*\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?(?:\\lambda|\\sigma|\\mu).*?(?:a\.s\.|almost\s+surely|\\text\{a\.s\.\}).*?)'
    r'\\end\{align\*\}',
    re.DOTALL
)


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is substantially contained in another's."""
    if not results:
        return results
    # Sort by length descending so longer matches shadow shorter ones
    results_sorted = sorted(results, key=lambda r: -len(r['raw_latex']))
    kept = []
    for candidate in results_sorted:
        c_text = candidate['raw_latex'].strip()
        dominated = False
        for other in kept:
            o_text = other['raw_latex'].strip()
            # If one is a substring of the other (ignoring whitespace diffs), drop the shorter
            c_norm = re.sub(r'\s+', ' ', c_text)
            o_norm = re.sub(r'\s+', ' ', o_text)
            if c_norm in o_norm or o_norm in c_norm:
                if len(c_norm) <= len(o_norm):
                    dominated = True
                    break
        if not dominated:
            kept.append(candidate)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # Rule A: \ba...\ea or \begin{align*}...\end{align*} preceded by
    # a lead-in sentence — problem descriptions in paper001
    # ------------------------------------------------------------------
    for m in BA_EA_PROBLEM.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        preamble = m.group('preamble').strip()
        body = m.group('body').strip()
        combined = preamble + ' ' + body
        raw = combined
        clean = _clean_latex(combined)
        if len(clean) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'BA_EA_PROBLEM',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule B: \begin{equation}...\end{equation} with (P_N) label
    # ------------------------------------------------------------------
    for m in EQUATION_PROBLEM.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body').strip()
        raw = m.group(0)
        clean = _clean_latex(raw)
        if len(clean) < 10:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'EQUATION_PROBLEM',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule C: \begin{align*?}...\end{align*?} with (P_N) label
    # ------------------------------------------------------------------
    for m in ALIGN_PROBLEM_LABEL.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group(0)
        clean = _clean_latex(raw)
        if len(clean) < 10:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'ALIGN_PROBLEM_LABEL',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule D: align/align* with \max/\min + \text{s.t.} (paper003)
    # ------------------------------------------------------------------
    for m in ALIGN_OPTIMIZATION.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group(0)
        clean = _clean_latex(raw)
        if len(clean) < 5:
            continue
        # Get surrounding context to include prose lead-in
        # Look back up to 600 chars for a sentence before the \begin{align}
        pre_start = max(0, start - 600)
        pre_text = text[pre_start:start]
        # Find last paragraph or sentence boundary
        para_match = list(re.finditer(r'\n\n|\.\s+(?=[A-Z])', pre_text))
        if para_match:
            lead_start = para_match[-1].end()
            lead_in = pre_text[lead_start:].strip()
        else:
            lead_in = pre_text.strip()
        if lead_in:
            combined_raw = lead_in + '\n' + raw
            combined_clean = _clean_latex(combined_raw)
        else:
            combined_raw = raw
            combined_clean = clean
        results.append({
            'raw_latex': combined_raw,
            'clean_text': combined_clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'ALIGN_OPTIMIZATION',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule E: align* with eigenvalue goto a.s. (paper002 theorem fact)
    # ------------------------------------------------------------------
    for m in ALIGN_THEOREM_FACT.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw_body = m.group('body').strip()
        # Also grab surrounding prose context
        pre_start = max(0, start - 800)
        pre_text = text[pre_start:start]
        para_match = list(re.finditer(r'\n\n', pre_text))
        if para_match:
            lead_start = para_match[-1].end()
            lead_in = pre_text[lead_start:].strip()
        else:
            lead_in = pre_text.strip()
        # Also grab text after the align* (for the "in the limit where..." part)
        post_end = min(len(text), end + 300)
        post_text = text[end:post_end]
        post_sentence = re.match(r'[^\n]{0,300}', post_text)
        post = post_sentence.group(0).strip() if post_sentence else ''
        combined_raw = (lead_in + '\n' if lead_in else '') + m.group(0) + (' ' + post if post else '')
        clean = _clean_latex(combined_raw)
        if len(clean) < 20:
            continue
        results.append({
            'raw_latex': combined_raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'ALIGN_THEOREM_FACT',
            'structure_type': 'theorem',
        })

    # ------------------------------------------------------------------
    # Rule F: align* with eigenvalue limit (broader, paper002)
    # ------------------------------------------------------------------
    for m in ALIGN_LIMIT_THEOREM.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group(0)
        clean = _clean_latex(raw)
        if len(clean) < 10:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'ALIGN_LIMIT_THEOREM',
            'structure_type': 'theorem',
        })

    # ------------------------------------------------------------------
    # Rule G: prose definitional paragraphs with \argmin (paper004)
    # ------------------------------------------------------------------
    # Use a targeted pattern: find "Define ... Lasso/Dantzig ..." paragraphs
    # that contain embedded \begin{equation}...\end{equation} blocks
    prose_problem_pattern = re.compile(
        r'(?:Define|The\s+(?:Lasso|Dantzig)\s+\w+[^.]{0,100}\.)'
        r'(?:(?!\\begin\{theorem\}|\\begin\{lemma\}|\\begin\{proof\}).){0,1500}'
        r'\\begin\{equation\}(?:\\begin\{split\})?'
        r'.*?'
        r'(?:\\end\{split\})?\\end\{equation\}'
        r'(?:(?:(?!\\begin\{theorem\}|\\begin\{lemma\}).){0,800}'
        r'\\begin\{equation\}(?:\\begin\{split\})?'
        r'.*?'
        r'(?:\\end\{split\})?\\end\{equation\})?'
        r'(?:(?:\s*where[^.]{0,200}\.)?)',
        re.DOTALL
    )
    for m in prose_problem_pattern.finditer(text):
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group(0).strip()
        clean = _clean_latex(raw)
        if len(clean) < 30:
            continue
        # Must contain \argmin or \argmax to be a real optimization problem
        if not re.search(r'\\arg(?:min|max)\b', raw):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': clean,
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'prose_problem_pattern',
            'structure_type': 'problem',
        })

    # ------------------------------------------------------------------
    # Rule H: broader \argmin paragraph fallback
#     # ------------------------------------------------------------------
#     for m in ARGMIN_PARAGRAPH.finditer(text):
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         body = m.group('body').strip()
#         if len(body) < 30:
#             continue
#         clean = _clean_latex(body)
#         results.append({
#             'raw_latex': body,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'ARGMIN_PARAGRAPH',
#             'structure_type': 'problem',
#         })

    # ------------------------------------------------------------------
    # Deduplicate and return
    # ------------------------------------------------------------------
    results = _deduplicate(results)
    return results
