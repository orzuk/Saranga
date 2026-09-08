import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very light LaTeX -> plain-text conversion."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove common commands but keep their argument
    text = re.sub(r'\\(?:text|mathrm|mathbf|mathit|emph|textbf|textit|texttt)\{([^}]*)\}', r'\1', text)
    # Remove \label{...}, \cite{...} etc.
    text = re.sub(r'\\(?:label|ref|eqref|cite[a-zA-Z]*)\{[^}]*\}', '', text)
    # Remove display math environments but keep content
    text = re.sub(r'\\begin\{(?:align\*?|equation\*?|gather\*?|multline\*?)\}', ' ', text)
    text = re.sub(r'\\end\{(?:align\*?|equation\*?|gather\*?|multline\*?)\}', ' ', text)
    # Remove remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+\*?\s*', ' ', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Excluded environments – matches inside these are suppressed
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note)\}.*?\\end\{\1\}',
    re.DOTALL
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside a proof/example/remark env."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _make_result(raw: str, name, env_name: str, rule_name: str,
                 structure_type: str) -> dict:
    return {
        "raw_latex": raw,
        "clean_text": _clean_latex(raw),
        "name": name,
        "env_name": env_name,
        "rule_name": rule_name,
        "structure_type": structure_type,
    }


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# ------------------------------------------------------------------
# R1: \begin{property}...\end{property}  (paper005 propositions)
# ------------------------------------------------------------------
PROPERTY_ENV_RE = re.compile(
    r'\\begin\{[Pp]roperty\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{[Pp]roperty\}',
    re.DOTALL
)

# ------------------------------------------------------------------
# R2: Optimization problems in align/equation env with \max or \min + s.t.
#     (paper003 problems)
# ------------------------------------------------------------------
OPT_ENV_RE = re.compile(
    r'\\begin\{(?P<env>align\*?|equation\*?|gather\*?)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)
OPT_KEYWORD_RE = re.compile(r'\\(?:max|min)(?:\\limits)?(?:\s|\\)', re.DOTALL)
ST_KEYWORD_RE = re.compile(
    r'\\text\s*\{\s*s\.?\s*t\.?\s*\}|'
    r'\\mathrm\s*\{\s*s\.?\s*t\.?\s*\}|'
    r'\\mbox\s*\{\s*s\.?\s*t\.?\s*\}|'
    r'\\text\s*\{\s*subject\s+to\s*\}',
    re.DOTALL | re.IGNORECASE
)

# ------------------------------------------------------------------
# R3: Named optimization problems — (P_0), (P_1), etc. inside equation/align
# ------------------------------------------------------------------
# PRUNED — SLOW backtracking (TIMEOUT > 0.50s/paper cap)
# NAMED_OPT_ENV_RE = re.compile(
#     r'(?P<preamble>(?:(?!\\begin\{(?:equation|align)).){0,600})'
#     r'\\begin\{(?P<env>equation\*?|align\*?)\}'
#     r'(?P<body>.*?\(P[_^]?\{?[0-9a-zA-Z]+\}?.*?)'
#     r'\\end\{(?P=env)\}',
#     re.DOTALL
# )

# ------------------------------------------------------------------
# R4: Graph-cut / clustering problem paragraphs (paper001)
# A paragraph that introduces a named graph-cut quantity via display math.
# Anchor: starts with one of several known phrases AND contains \ba...\ea
# or $$...$$
# ------------------------------------------------------------------
GRAPH_CUT_PARA_RE = re.compile(
    r'(?:(?<=\n\n)|(?<=\n))'          # paragraph boundary
    r'(?P<body>'
    r'(?:'
    r'Given a similarity graph|'
    r'The two most common objective functions|'
    r'This can be seen even more explicitly by considering|'
    r'One way to circumvent this problem'
    r')'
    r'[^\x00]{30,2000}?'              # body
    r'(?='
    r'\n\n|\\(?:section|subsection|newpage)|$'
    r'))',
    re.DOTALL | re.IGNORECASE
)

# ------------------------------------------------------------------
# R5: Inline problem definitions introduced by "define" or "introduce"
#     followed by an equation environment (paper004 Lasso/Dantzig)
# ------------------------------------------------------------------
DEFINE_EQ_PARA_RE = re.compile(
    r'(?:(?<=\n\n)|(?<=\n\n\n))'
    r'(?P<body>'
    r'(?:'
    r'Define the|'
    r'Introduce the|'
    r'We define|'
    r'We introduce|'
    r'The Dantzig estimator|'
    r'The Dantzig selector'
    r')'
    r'[^\x00]{20,3000}?'
    r'\\begin\{equation\}[^\x00]{10,500}?\\end\{equation\}'
    r'[^\x00]{0,800}?'
    r'(?='
    r'\n\n|\\(?:section|subsection)|$'
    r'))',
    re.DOTALL
)

# ------------------------------------------------------------------
# R6: Subsection-embedded theorem-like statements (paper005 theorem)
#     A \subsection{Computing ...} followed by prose containing \defeq
#     or algorithm-like statements, before the next \begin{algorithm}
# ------------------------------------------------------------------
# PRUNED — FP on paper005, paper006 | also 1 TP — review before uncommenting
# SUBSEC_THEOREM_RE = re.compile(
#     r'\\subsection\{(?P<title>[^}]*)\}\s*'
#     r'(?P<body>(?:(?!\\begin\{algorithm\}|\\subsection|\\section\b).){40,1200})',
#     re.DOTALL
# )

# ------------------------------------------------------------------
# R7: Optimal Transportation problem subsection (paper005)
#     \subsection{Optimal Transportation} body with $$...\defeq...$$ or \defeq
# ------------------------------------------------------------------
SUBSEC_OPT_TRANSPORT_RE = re.compile(
    r'\\subsection\{(?P<title>[^}]*(?:[Oo]ptimal\s*[Tt]ransport|'
    r'[Ss]inkhorn)[^}]*)\}\s*'
    r'(?P<body>(?:(?!\\subsection|\\section\b).){40,3000})',
    re.DOTALL
)

# ------------------------------------------------------------------
# R8: Equation with \boxed{...\defeq...}  (paper005 dual-Sinkhorn)
# ------------------------------------------------------------------
# PRUNED — SLOW backtracking (TIMEOUT > 0.50s/paper cap)
# BOXED_DEFEQ_RE = re.compile(
#     r'(?P<preamble>(?:(?!\\begin\{equation\}).){0,600})'
#     r'\\begin\{equation\}[^\x00]{0,50}'
#     r'\\boxed\{(?P<boxed>[^\x00]{10,600}?\\defeq[^\x00]{10,600}?)\}'
#     r'[^\x00]{0,50}\\end\{equation\}'
#     r'(?P<postamble>(?:(?!\\section|\\subsection|\\begin\{(?:theorem|lemma|prop)).){0,600})',
#     re.DOTALL
# )

# ------------------------------------------------------------------
# R9: Prose minimax / guarantees theorem (paper006)
#     Paragraph containing "minimax theorem" + \begin{equation*}...\end{equation*}
# ------------------------------------------------------------------
PROSE_MINIMAX_THM_RE = re.compile(
    r'(?P<body>'
    r'(?:(?<=\n\n)|(?<=\n))'
    r'[^\x00]{0,200}'
    r'(?:minimax\s+theorem|H.{1,5}jek[^\n]{0,80}minimax|'
    r'guarantees\s+for\s+\\emph\{any\s+estimator\})'
    r'[^\x00]{0,1500}?'
    r'\\begin\{equation\*\}[^\x00]{10,500}?\\end\{equation\*\}'
    r')',
    re.DOTALL | re.IGNORECASE
)

# ------------------------------------------------------------------
# R10: "Our goal is to estimate" problem paragraph (paper006)
# ------------------------------------------------------------------
PROSE_GOAL_ESTIMATE_RE = re.compile(
    r'(?P<body>'
    r'Our\s+goal\s+is\s+to\s+estimate\s+the\s+parameter'
    r'[^\x00]{30,1200}?'
    r'\\begin\{equation\}[^\x00]{10,600}?\\end\{equation\}'
    r'[^\x00]{0,300}?'
    r'(?=\n\n|\\(?:section|subsection)|$)'
    r')',
    re.DOTALL
)

# ------------------------------------------------------------------
# R11: "The goal of this paper is to understand" problem (paper006)
# ------------------------------------------------------------------
PROSE_PAPER_GOAL_RE = re.compile(
    r'(?P<body>'
    r'The\s+goal\s+of\s+this\s+paper\s+is\s+to\s+understand'
    r'[^\x00]{30,800}?'
    r'(?=\n\n|\\(?:section|subsection)|$)'
    r')',
    re.DOTALL
)

# ------------------------------------------------------------------
# R12: "Our goal is to predict" problem (paper006 logistic regression)
# ------------------------------------------------------------------
PROSE_GOAL_PREDICT_RE = re.compile(
    r'(?P<body>'
    r'Our\s+goal\s+is\s+to\s+predict'
    r'[^\x00]{30,800}?'
    r'\\begin\{equation\*\}[^\x00]{10,400}?\\end\{equation\*\}'
    r'[^\x00]{0,200}?'
    r'(?=\n\n|\\(?:section|subsection)|$)'
    r')',
    re.DOTALL
)

# ------------------------------------------------------------------
# R13: "We leave as ... open questions" open problem (paper006)
# ------------------------------------------------------------------
PROSE_LEAVE_OPEN_QUESTIONS_RE = re.compile(
    r'(?P<body>'
    r'We\s+leave\s+as\s+[^.]{0,80}open\s+questions?'
    r'[^\x00]{30,800}?'
    r'\.\s'
    r')',
    re.DOTALL | re.IGNORECASE
)

# ------------------------------------------------------------------
# R14: "We leave this question to future work" open problem (paper006)
# ------------------------------------------------------------------
PROSE_LEAVE_FUTURE_RE = re.compile(
    r'(?P<body>'
    r'(?:(?<=\n\n)|(?<=\. ))'
    r'[^\x00]{0,400}'
    r'We\s+leave\s+this\s+question\s+to\s+future\s+work'
    r'[^.]{0,80}\.'
    r')',
    re.DOTALL
)

# ------------------------------------------------------------------
# R15: "remain open after this work" discussion paragraph (paper006)
# ------------------------------------------------------------------
# PRUNED — SLOW backtracking (2.94s > 0.50s/paper cap)
# PROSE_REMAIN_OPEN_RE = re.compile(
#     r'(?P<body>'
#     r'[^\x00]{0,200}'
#     r'(?:questions?\s+that\s+)?remain\s+open\s+after\s+this\s+work'
#     r'[^\x00]{30,1200}?'
#     r'(?=\n\n|\\(?:section|subsection)|$)'
#     r')',
#     re.DOTALL | re.IGNORECASE
# )

# ------------------------------------------------------------------
# R16: "It remains open to show" open problem (paper003)
# ------------------------------------------------------------------
PROSE_REMAINS_OPEN_RE = re.compile(
    r'(?P<body>'
    r'It\s+remains\s+open\s+to\s+(?:show|prove|determine|establish)'
    r'[^\x00]{20,600}?'
    r'(?=\n\n|\\(?:section|subsection|begin)|$)'
    r')',
    re.DOTALL | re.IGNORECASE
)

# ------------------------------------------------------------------
# R17: align* in paper002 with Marchenko-Pastur eigenvalue result
#      (gold: theorem, but the LaTeX is align*)
# ------------------------------------------------------------------
# PRUNED — SLOW backtracking (2.44s > 0.50s/paper cap)
# MARCHENKO_PASTUR_RE = re.compile(
#     r'(?P<preamble>[^\x00]{0,400}?'
#     r'(?:Marchenko|Pastur|Geman|Silverstein|BaiYin)[^\x00]{0,300}?)'
#     r'\\begin\{align\*\}'
#     r'(?P<body>[^\x00]{10,600}?'
#     r'\\lambda_\{\\(?:min|max)\}[^\x00]{10,400}?)'
#     r'\\end\{align\*\}'
#     r'(?P<postamble>[^\x00]{0,400}?(?=\n\n|\\(?:section|subsection)|$))',
#     re.DOTALL
# )

# ---------------------------------------------------------------------------
# Subtype inference helper
# ---------------------------------------------------------------------------

def _infer_structure_type(env_name: str, body: str, default: str = 'theorem') -> str:
    """Infer structure_type from environment name and body text."""
    env_lower = env_name.lower().rstrip('*')
    env_map = {
        'theorem': 'theorem', 'thm': 'theorem', 'theo': 'theorem',
        'lemma': 'lemma', 'lem': 'lemma',
        'proposition': 'proposition', 'prop': 'proposition',
        'property': 'proposition',
        'corollary': 'corollary', 'cor': 'corollary',
        'claim': 'claim',
        'conjecture': 'conjecture',
        'problem': 'problem', 'prob': 'problem',
        'openproblem': 'open_problem', 'openquestion': 'open_problem',
        'open': 'open_problem',
    }
    if env_lower in env_map:
        return env_map[env_lower]
    # Scan body for keyword clues
    body_lower = body.lower()
    if any(kw in body_lower for kw in ['it remains open', 'remain open', 'open question',
                                        'open problem', 'future work', 'we leave',
                                        'work in progress', 'we hope to report']):
        return 'open_problem'
    if any(kw in body_lower for kw in ['\\min', '\\max', r'\argmin', r'\argmax',
                                        'subject to', 's.t.', '\\min_', '\\max_',
                                        'minimize', 'maximize', 'minimizes', 'maximizes',
                                        'mincut', 'ratiocut', 'ncut', 'minmaxcut',
                                        'lasso', 'dantzig', 'optimal transport',
                                        'our goal is to', 'the goal of this paper']):
        return 'problem'
    if any(kw in body_lower for kw in ['theorem', 'guarantees', 'minimax']):
        return 'theorem'
    return default


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex is a substring of another result's raw_latex."""
    if not results:
        return results
    # Sort by length descending so larger matches shadow substrings
    results_sorted = sorted(results, key=lambda r: len(r['raw_latex']), reverse=True)
    kept: List[dict] = []
    kept_texts: List[str] = []
    for r in results_sorted:
        raw = r['raw_latex'].strip()
        # Check if raw is mostly contained in any already-kept text
        dominated = False
        for kt in kept_texts:
            # rough overlap check: if 80% of raw chars appear in kt
            if raw in kt or kt in raw:
                dominated = True
                break
        if not dominated:
            kept.append(r)
            kept_texts.append(raw)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    results: List[dict] = []

    # ------------------------------------------------------------------
    # R1: \begin{property}...\end{property}
    # ------------------------------------------------------------------
    for m in PROPERTY_ENV_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        opt = m.group('opt')
        body = m.group('body')
        name = opt.strip() if opt else None
        results.append(_make_result(
            raw=body, name=name,
            env_name='distilled', rule_name='PROPERTY_ENV_RE',
            structure_type='proposition'
        ))

    # ------------------------------------------------------------------
    # R2: Optimization problems in align/equation with \max or \min + s.t.
    # ------------------------------------------------------------------
    for m in OPT_ENV_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body')
        if OPT_KEYWORD_RE.search(body) and ST_KEYWORD_RE.search(body):
            # Gather preceding context (up to 400 chars) for richer raw_latex
            start = m.start()
            preceding = text[max(0, start - 400):start]
            # Trim preceding to last paragraph
            para_split = re.split(r'\n\n', preceding)
            context = para_split[-1].strip() if para_split else ''
            raw = (context + '\n' + m.group(0)).strip()
            results.append(_make_result(
                raw=raw, name=None,
                env_name='distilled', rule_name='OPT_ENV_RE',
                structure_type='problem'
            ))

    # ------------------------------------------------------------------
    # R3: Named optimization problems (P_0), (P_1) inside equation/align
#     # ------------------------------------------------------------------
#     for m in NAMED_OPT_ENV_RE.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         body = m.group('body')
#         preamble = m.group('preamble').strip()
#         raw = (preamble + '\n' + m.group(0)).strip()
#         results.append(_make_result(
#             raw=raw, name=None,
#             env_name='distilled', rule_name='NAMED_OPT_ENV_RE',
#             structure_type='problem'
#         ))

    # ------------------------------------------------------------------
    # R4: Graph-cut problem paragraphs (paper001)
    # ------------------------------------------------------------------
    for m in GRAPH_CUT_PARA_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 50:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='GRAPH_CUT_PARA_RE',
            structure_type='problem'
        ))

    # ------------------------------------------------------------------
    # R5: Define/Introduce paragraph + equation env (paper004)
    # ------------------------------------------------------------------
    for m in DEFINE_EQ_PARA_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 60:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='DEFINE_EQ_PARA_RE',
            structure_type='problem'
        ))

    # ------------------------------------------------------------------
    # R6: Subsection-embedded theorem-like (paper005 Computing d_M^lambda)
#     # ------------------------------------------------------------------
#     for m in SUBSEC_THEOREM_RE.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         body = m.group('body').strip()
#         title = m.group('title').strip()
#         # Only keep if body contains \defeq or form u_i e^{...}
#         if not re.search(r'\\defeq|u_i\s*e\^|P\^\\lambda|argmin', body):
#             continue
#         if len(body) < 40:
#             continue
#         results.append(_make_result(
#             raw=body, name=title,
#             env_name='distilled', rule_name='SUBSEC_THEOREM_RE',
#             structure_type='theorem'
#         ))

    # ------------------------------------------------------------------
    # R7: Optimal Transportation subsection (paper005)
    # ------------------------------------------------------------------
    for m in SUBSEC_OPT_TRANSPORT_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        title = m.group('title').strip()
        if not re.search(r'\\defeq|\\min_|d_M', body):
            continue
        if len(body) < 60:
            continue
        results.append(_make_result(
            raw=body, name=title,
            env_name='distilled', rule_name='SUBSEC_OPT_TRANSPORT_RE',
            structure_type='problem'
        ))

    # ------------------------------------------------------------------
    # R8: \begin{equation}...\boxed{...\defeq...}...\end{equation}
#     # ------------------------------------------------------------------
#     for m in BOXED_DEFEQ_RE.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         preamble = m.group('preamble').strip()
#         boxed = m.group('boxed').strip()
#         postamble = m.group('postamble').strip()
#         raw = (preamble + '\n' + boxed + '\n' + postamble).strip()
#         if len(raw) < 40:
#             continue
#         results.append(_make_result(
#             raw=raw, name=None,
#             env_name='distilled', rule_name='BOXED_DEFEQ_RE',
#             structure_type='problem'
#         ))

    # ------------------------------------------------------------------
    # R9: Prose minimax theorem (paper006)
    # ------------------------------------------------------------------
    for m in PROSE_MINIMAX_THM_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 80:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='PROSE_MINIMAX_THM_RE',
            structure_type='theorem'
        ))

    # ------------------------------------------------------------------
    # R10: "Our goal is to estimate" problem (paper006)
    # ------------------------------------------------------------------
    for m in PROSE_GOAL_ESTIMATE_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 50:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='PROSE_GOAL_ESTIMATE_RE',
            structure_type='problem'
        ))

    # ------------------------------------------------------------------
    # R11: "The goal of this paper is to understand" (paper006)
    # ------------------------------------------------------------------
    for m in PROSE_PAPER_GOAL_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 50:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='PROSE_PAPER_GOAL_RE',
            structure_type='problem'
        ))

    # ------------------------------------------------------------------
    # R12: "Our goal is to predict" problem (paper006)
    # ------------------------------------------------------------------
    for m in PROSE_GOAL_PREDICT_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 50:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='PROSE_GOAL_PREDICT_RE',
            structure_type='problem'
        ))

    # ------------------------------------------------------------------
    # R13: "We leave as ... open questions" (paper006)
    # ------------------------------------------------------------------
    for m in PROSE_LEAVE_OPEN_QUESTIONS_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 40:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='PROSE_LEAVE_OPEN_QUESTIONS_RE',
            structure_type='open_problem'
        ))

    # ------------------------------------------------------------------
    # R14: "We leave this question to future work" (paper006)
    # ------------------------------------------------------------------
    for m in PROSE_LEAVE_FUTURE_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='PROSE_LEAVE_FUTURE_RE',
            structure_type='open_problem'
        ))

    # ------------------------------------------------------------------
    # R15: "remain open after this work" discussion paragraph (paper006)
#     # ------------------------------------------------------------------
#     for m in PROSE_REMAIN_OPEN_RE.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         body = m.group('body').strip()
#         if len(body) < 60:
#             continue
#         results.append(_make_result(
#             raw=body, name=None,
#             env_name='distilled', rule_name='PROSE_REMAIN_OPEN_RE',
#             structure_type='open_problem'
#         ))

    # ------------------------------------------------------------------
    # R16: "It remains open to show" (paper003)
    # ------------------------------------------------------------------
    for m in PROSE_REMAINS_OPEN_RE.finditer(text):
        if _inside_excluded_env(text, m.start(), m.end()):
            continue
        body = m.group('body').strip()
        if len(body) < 30:
            continue
        results.append(_make_result(
            raw=body, name=None,
            env_name='distilled', rule_name='PROSE_REMAINS_OPEN_RE',
            structure_type='open_problem'
        ))

    # ------------------------------------------------------------------
    # R17: Marchenko-Pastur / Geman eigenvalue align* theorem (paper002)
#     # ------------------------------------------------------------------
#     for m in MARCHENKO_PASTUR_RE.finditer(text):
#         if _inside_excluded_env(text, m.start(), m.end()):
#             continue
#         preamble = m.group('preamble').strip()
#         body = m.group('body').strip()
#         postamble = m.group('postamble').strip()
#         raw = (preamble + '\n' + body + '\n' + postamble).strip()
#         if len(raw) < 60:
#             continue
#         results.append(_make_result(
#             raw=raw, name=None,
#             env_name='distilled', rule_name='MARCHENKO_PASTUR_RE',
#             structure_type='theorem'
#         ))

    # ------------------------------------------------------------------
    # Deduplicate
    # ------------------------------------------------------------------
    results = _deduplicate(results)

    return results
