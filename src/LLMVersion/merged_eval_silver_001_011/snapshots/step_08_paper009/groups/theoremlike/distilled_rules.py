import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# \begin{property}...\end{property}  -> proposition
PROP_PROPERTY_RE = re.compile(
    r'\\begin\{([Pp]roperty)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# \begin{align}...\end{align} or \begin{align*}...\end{align*}
# containing \max or \min together with s.t. / subject to  -> problem
OPT_ALIGN_RE = re.compile(
    r'\\begin\{(align\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# \begin{equation}...\end{equation} containing (P_N) style labels -> problem
PROB_EQUATION_RE = re.compile(
    r'\\begin\{(equation\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    re.DOTALL
)

# \ba ... \ea blocks with a preceding preamble sentence -> problem (paper001 style)
# PRUNED — FP on paper001 | also 10 TP — review before uncommenting
# BA_BLOCK_RE = re.compile(
#     r'(?P<preamble>(?:[^\n]|\n(?!\n)){20,800}?)'
#     r'\\ba\s*(?P<math>.*?)\\ea',
#     re.DOTALL
# )

# Prose paragraphs containing \argmin -> problem (paper004 style)
ARGMIN_PROSE_RE = re.compile(
    r'(?:(?:^|\n\n))'
    r'(?P<body>[^\n].*?\\argmin[\s\S]*?)'
    r'(?=\n\n|\Z)',
    re.DOTALL
)

# Subsection-level implicit theorem prose (before \begin{algorithm}) -> theorem
# PRUNED — FP on paper001, paper002, paper005 +1 more | also 2 TP — review before uncommenting
# SUBSECTION_THEOREM_RE = re.compile(
#     r'\\subsection\*?\{(?P<secname>[^}]*)\}\s*'
#     r'(?P<body>(?:(?!\\begin\{|\\subsection\b|\\section\b).){60,}?)'
#     r'(?=\\begin\{|\\subsection\b|\\section\b|\Z)',
#     re.DOTALL
# )

# Prose paragraph: minimax/lower-bound theorem with equation* -> theorem
MINIMAX_THM_RE = re.compile(
    r'(?:Then\s+under\s+our\s+assumptions'
    r'|guarantees\s+for\s+.{0,120}?estimator)'
    r'.{0,600}?'
    r'\\begin\{equation\*\}.*?\\end\{equation\*\}',
    re.DOTALL
)

# "Our goal is to estimate" prose + \begin{equation}...\end{equation} -> problem
GOAL_ESTIMATE_RE = re.compile(
    r'Our\s+goal\s+is\s+to\s+estimate'
    r'.{0,800}?'
    r'\\begin\{equation\}.*?\\end\{equation\}',
    re.DOTALL
)

# "The goal of this paper is to" prose paragraph -> problem
PAPER_GOAL_RE = re.compile(
    r'The\s+goal\s+of\s+this\s+paper\s+is\s+to\b'
    r'.{0,1200}?'
    r'(?=\n\n|\\paragraph\b|\\(?:sub)*section\b|\Z)',
    re.DOTALL
)

# "Our goal is to predict" prose + \begin{equation*}...\end{equation*} -> problem
GOAL_PREDICT_RE = re.compile(
    r'Our\s+goal\s+is\s+to\s+predict'
    r'.{0,800}?'
    r'\\begin\{equation\*\}.*?\\end\{equation\*\}',
    re.DOTALL
)

# ---------------------------------------------------------------------------
# Excluded environments (skip matches fully inside these)
# ---------------------------------------------------------------------------

_EXCL_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note)\}'
    r'.*?'
    r'\\end\{\1\}',
    re.DOTALL
)

_OPT_MARKER_RE = re.compile(r'\\(?:max|min)\b', re.IGNORECASE)
_ST_MARKER_RE = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|\\text\s*\{\s*subject\s+to\s*\}|subject\s+to',
    re.IGNORECASE
)

_P_LABEL_RE = re.compile(r'\(P[_0-9\w]*\)', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain text conversion."""
    s = text
    # Remove comments
    s = re.sub(r'%[^\n]*', '', s)
    # Remove common commands but keep their argument
    s = re.sub(r'\\(?:text|mathrm|mathbf|mathit|mathcal|operatorname|emph|textit|textbf)\{([^}]*)\}', r'\1', s)
    # Remove labels
    s = re.sub(r'\\label\{[^}]*\}', '', s)
    # Remove \nonumber, \qquad, \quad
    s = re.sub(r'\\(?:nonumber|qquad|quad)\b', ' ', s)
    # Remove \\ line break
    s = re.sub(r'\\\\', ' ', s)
    # Remove display math environments markers
    s = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', s)
    # Collapse whitespace
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the interval [start, end) is fully inside an excluded environment."""
    for m in _EXCL_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _opt_name_from_opt(opt: str | None) -> str | None:
    if opt:
        return opt.strip() or None
    return None


def _make_result(raw_latex: str, name, env_name: str, rule_name: str,
                 structure_type: str) -> dict:
    return {
        "raw_latex": raw_latex,
        "clean_text": _clean_latex(raw_latex),
        "name": name,
        "env_name": env_name,
        "rule_name": rule_name,
        "structure_type": structure_type,
    }


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []  # list of (start, end, dict)
    spans: List[tuple] = []   # (start, end) for dedup

    def _add(start: int, end: int, d: dict):
        if _inside_excluded_env(text, start, end):
            return
        # Check overlap with existing spans
        for s, e in spans:
            # If significant overlap, skip
            overlap = min(end, e) - max(start, s)
            if overlap > 20:
                return
        spans.append((start, end))
        results.append(d)

    # ------------------------------------------------------------------
    # Rule: PROP_PROPERTY_RE  -> proposition
    # ------------------------------------------------------------------
    for m in PROP_PROPERTY_RE.finditer(text):
        env = m.group(1)
        opt = m.group("opt")
        body = m.group("body")
        raw = m.group(0)
        _add(
            m.start(), m.end(),
            _make_result(raw, _opt_name_from_opt(opt), "distilled",
                         "PROP_PROPERTY_RE", "proposition")
        )

    # ------------------------------------------------------------------
    # Rule: OPT_ALIGN_RE -> problem (optimization problems with s.t.)
    # ------------------------------------------------------------------
    for m in OPT_ALIGN_RE.finditer(text):
        body = m.group("body")
        if _OPT_MARKER_RE.search(body) and _ST_MARKER_RE.search(body):
            raw = m.group(0)
            _add(
                m.start(), m.end(),
                _make_result(raw, None, "distilled", "OPT_ALIGN_RE", "problem")
            )

    # ------------------------------------------------------------------
    # Rule: PROB_EQUATION_RE -> problem (equation with (P_N) label)
    # ------------------------------------------------------------------
    for m in PROB_EQUATION_RE.finditer(text):
        body = m.group("body")
        if _P_LABEL_RE.search(body):
            raw = m.group(0)
            opt = m.group("opt")
            _add(
                m.start(), m.end(),
                _make_result(raw, _opt_name_from_opt(opt), "distilled",
                             "PROB_EQUATION_RE", "problem")
            )

    # ------------------------------------------------------------------
    # Rule: BA_BLOCK_RE -> problem (\ba...\ea blocks with preamble)
#     # ------------------------------------------------------------------
#     for m in BA_BLOCK_RE.finditer(text):
#         preamble = m.group("preamble")
#         math = m.group("math")
#         raw = preamble.strip() + "\n\\ba\n" + math + "\\ea"
#         _add(
#             m.start(), m.end(),
#             _make_result(raw, None, "distilled", "BA_BLOCK_RE", "problem")
#         )

    # ------------------------------------------------------------------
    # Rule: ARGMIN_PROSE_RE -> problem (prose with \argmin)
    # ------------------------------------------------------------------
    for m in ARGMIN_PROSE_RE.finditer(text):
        body = m.group("body").strip()
        if len(body) < 40:
            continue
        _add(
            m.start(), m.end(),
            _make_result(body, None, "distilled", "ARGMIN_PROSE_RE", "problem")
        )

    # ------------------------------------------------------------------
    # Rule: MINIMAX_THM_RE -> theorem
    # ------------------------------------------------------------------
    for m in MINIMAX_THM_RE.finditer(text):
        raw = m.group(0)
        _add(
            m.start(), m.end(),
            _make_result(raw, None, "distilled", "MINIMAX_THM_RE", "theorem")
        )

    # ------------------------------------------------------------------
    # Rule: GOAL_ESTIMATE_RE -> problem
    # ------------------------------------------------------------------
    for m in GOAL_ESTIMATE_RE.finditer(text):
        raw = m.group(0)
        _add(
            m.start(), m.end(),
            _make_result(raw, None, "distilled", "GOAL_ESTIMATE_RE", "problem")
        )

    # ------------------------------------------------------------------
    # Rule: PAPER_GOAL_RE -> problem
    # ------------------------------------------------------------------
    for m in PAPER_GOAL_RE.finditer(text):
        raw = m.group(0).strip()
        if len(raw) < 30:
            continue
        _add(
            m.start(), m.start() + len(raw),
            _make_result(raw, None, "distilled", "PAPER_GOAL_RE", "problem")
        )

    # ------------------------------------------------------------------
    # Rule: GOAL_PREDICT_RE -> problem
    # ------------------------------------------------------------------
    for m in GOAL_PREDICT_RE.finditer(text):
        raw = m.group(0)
        _add(
            m.start(), m.end(),
            _make_result(raw, None, "distilled", "GOAL_PREDICT_RE", "problem")
        )

    # ------------------------------------------------------------------
    # Rule: SUBSECTION_THEOREM_RE -> theorem
    # (only if the subsection body looks like a theorem statement)
    # ------------------------------------------------------------------
    _THM_SIGNAL_RE = re.compile(
        r'(?:unique|solution|is\s+necessarily|holds\s+with\s+high\s+probability'
        r'|can\s+be\s+computed|we\s+have\s+that|converges|satisfies)',
        re.IGNORECASE
    )
#     for m in SUBSECTION_THEOREM_RE.finditer(text):
#         body = m.group("body").strip()
#         if len(body) < 60:
#             continue
#         if not _THM_SIGNAL_RE.search(body):
#             continue
#         _add(
#             m.start(), m.end(),
#             _make_result(body, m.group("secname").strip() or None,
#                          "distilled", "SUBSECTION_THEOREM_RE", "theorem")
#         )

    return results
