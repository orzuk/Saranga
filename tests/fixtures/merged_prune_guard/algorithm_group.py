import re
from typing import List, Dict

try:
    from latex_clean import clean_latex_to_text as _clean_latex
except Exception:
    _clean_latex = lambda s: s


# Ordinal enumeration of methods described in prose ("The first one is based on ...").
_ORDINAL_METHOD_PROSE = re.compile(
    r"\b(?:The|A)\s+(?:first|second|third|fourth|fifth)\s+"
    r"(?:one|method|approach|variant|scheme)\s+(?:is|are)\s+(?:based\s+on|given\s+by|obtained\s+by)\b",
    re.IGNORECASE,
)

# Explicit "the following algorithm" lead-in, with no algorithm environment.
_FOLLOWING_ALGORITHM_LEADIN = re.compile(
    r"\b(?:we|We)\s+(?:consider|propose|present|use|describe|introduce)\s+the\s+following\s+"
    r"(?:\w+\s+){0,2}algorithm\b",
    re.IGNORECASE,
)

# Bold/emph-anchored algorithm headings in the first sentence of a paragraph.
_BOLD_ALGORITHM_HEAD = re.compile(
    r"\\(?:textbf|emph|textit)\{\s*(?:[^{}]{0,60}\s)?(?:algorithm|procedure)\s*[^{}]{0,60}\}",
    re.IGNORECASE,
)

# Procedural update cues: "each node ... updates its local variables", "the resulting iterations".
# PRUNED — FP on 1708.00522v2, 1712.00232v3 | also 1 TP — review before uncommenting
# _PROCEDURE_CUES = re.compile(
#     r"\b(?:we\s+(?:apply|update|run|iterate)|"
#     r"updates?\s+(?:its|their|the)\s+(?:local\s+)?variables?|"
#     r"the\s+(?:resulting\s+)?iterations?|"
#     r"can\s+be\s+executed)\b",
#     re.IGNORECASE,
# )
_PROCEDURE_CUES = re.compile(r'(?!x)x')  # PRUNED

# Explicit iterative update formula x^{k+1} = ... together with an iteration keyword.
_ITER_UPDATE = re.compile(r"[a-zA-Z]\^\{?k\s*\+\s*1\}?\s*=", re.IGNORECASE)
_ITER_WORDS = re.compile(r"\b(?:power\s+method|iterat\w*|update\w*|step)\b", re.IGNORECASE)

# Iterated procedure: a verb list ("compute ..., minimize ..., choose ...") ending in an
# iteration keyword, within one paragraph.
_ITERATIVE_PROSE = re.compile(
    r"(?:\b(?:compute|minimi[sz]e|choose|estimate|update|set|initiali[sz]e)\b[^.]{0,80}?,\s*){2,}"
    r"[^.]{0,80}?\b(?:iterate|repeat|until\s+convergence)\b",
    re.IGNORECASE | re.DOTALL,
)

# Procedural lead-in verb followed by a display-math block within the same paragraph.
_PROCEDURAL_LEAD = re.compile(
    r"\b(?:replace|compute|iterate|minimi[sz]e|estimate|update|initiali[sz]e)\b"
    r"[^.]{0,200}?\\\[|\\begin\{(?:equation|align)\*?\}",
    re.IGNORECASE | re.DOTALL,
)

# Numbered step references ("step~0", "step 3"); two or more distinct refs in one paragraph
# signal a step-structured procedure.
_STEP_REF = re.compile(r"\bstep\s*~?\s*\d+", re.IGNORECASE)

# "apply the <...> technique/method/procedure/algorithm" phrasing.
# PRUNED — FP on 1102.4533v1
# _APPLY_METHOD_PROSE = re.compile(
#     r"\bapply\w*\s+(?:the\s+)?[\w\s'\-]{0,40}?(?:technique|method|procedure|algorithm)\b",
#     re.IGNORECASE,
# )
_APPLY_METHOD_PROSE = re.compile(r'(?!x)x')  # PRUNED

# Method-substitution phrasing ("instead of using W one can analyze the algorithm with ...").
_METHOD_SUBST_PROSE = re.compile(
    r"\b(?:instead\s+of\s+using|one\s+can\s+analyze\s+the\s+algorithm\s+with)\b",
    re.IGNORECASE,
)

# Environments inside which matches are not reported.
_EXCLUDED_ENV_NAMES = ("proof", "example", "remark", "examp", "remarks", "exercise")
_EXCLUDED_ENV_RE = re.compile(
    r"\\begin\{(" + "|".join(_EXCLUDED_ENV_NAMES) + r")\*?\}.*?\\end\{\1\*?\}",
    re.DOTALL,
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """True if the span [start, end) lies inside a proof/example/remark-like environment."""
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


def _paragraph_bounds(text: str, pos: int):
    """Return (start, end) of the paragraph containing pos, split on blank lines."""
    start = text.rfind("\n\n", 0, pos)
    start = 0 if start == -1 else start + 2
    end = text.find("\n\n", pos)
    end = len(text) if end == -1 else end
    return start, end


def _first_sentence_end(text: str, start: int, limit: int) -> int:
    """Index of the end of the first sentence after start (period not inside math is approximated)."""
    window = text[start:min(limit, len(text))]
    m = re.search(r"[.!?](?=\s|$)", window)
    return start + (m.end() if m else len(window))


def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []
    seen_spans = []

    def _overlaps(s: int, e: int) -> bool:
        return any(not (e <= a or s >= b) for a, b in seen_spans)

    def _emit(rule_name: str, start: int, end: int):
        if end <= start or _overlaps(start, end):
            return
        if _inside_excluded_env(text, start, end):
            return
        raw = text[start:end].strip()
        if not raw:
            return
        seen_spans.append((start, end))
        results.append({
            "raw_latex": raw,
            "clean_text": _clean_latex(raw),
            "name": None,
            "env_name": "distilled",
            "rule_name": rule_name,
            "structure_type": "algorithm",
        })

    # Rule: ordinal method enumeration in prose -> whole paragraph.
    for m in _ORDINAL_METHOD_PROSE.finditer(text):
        p_start, p_end = _paragraph_bounds(text, m.start())
        _emit("_ORDINAL_METHOD_PROSE", p_start, p_end)

    # Rule: "we consider the following ... algorithm" lead-in -> paragraph containing it.
    for m in _FOLLOWING_ALGORITHM_LEADIN.finditer(text):
        p_start, p_end = _paragraph_bounds(text, m.start())
        _emit("_FOLLOWING_ALGORITHM_LEADIN", p_start, p_end)

    # Rule: bold/emph algorithm heading in a paragraph's first sentence -> that paragraph.
    for m in _BOLD_ALGORITHM_HEAD.finditer(text):
        p_start, p_end = _paragraph_bounds(text, m.start())
        first_end = _first_sentence_end(text, p_start, p_end)
        if m.start() < first_end:
            _emit("_BOLD_ALGORITHM_HEAD", p_start, p_end)

    # Rule: procedural update cues in prose (opt-in, long paragraphs only).
#     for m in _PROCEDURE_CUES.finditer(text):
#         p_start, p_end = _paragraph_bounds(text, m.start())
#         if p_end - p_start > 200:
#             _emit("_PROCEDURE_CUES", p_start, p_end)

    pass  # PRUNED: body commented out
    # Rule: explicit iterative update formula plus iteration keyword in the same paragraph.
    for m in _ITER_UPDATE.finditer(text):
        p_start, p_end = _paragraph_bounds(text, m.start())
        if _ITER_WORDS.search(text[p_start:p_end]):
            _emit("_ITER_UPDATE", p_start, p_end)

    # Rule: verb list ending in an iteration keyword -> paragraph.
    for m in _ITERATIVE_PROSE.finditer(text):
        p_start, p_end = _paragraph_bounds(text, m.start())
        _emit("_ITERATIVE_PROSE", p_start, p_end)

    # Rule: procedural lead-in verb followed by a display-math block -> paragraph.
    for m in _PROCEDURAL_LEAD.finditer(text):
        p_start, p_end = _paragraph_bounds(text, m.start())
        _emit("_PROCEDURAL_LEAD", p_start, p_end)

    # Rule: two or more distinct numbered-step references in one paragraph -> paragraph.
    for p_match in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):
        para = p_match.group(0)
        distinct = {re.sub(r"[\s~]", "", s.lower()) for s in _STEP_REF.findall(para)}
        if len(distinct) >= 2:
            _emit("_STEP_REF", p_match.start(), p_match.end())

    # Rule: "apply the ... technique/method" phrasing in prose.
#     for m in _APPLY_METHOD_PROSE.finditer(text):
#         p_start, p_end = _paragraph_bounds(text, m.start())
#         _emit("_APPLY_METHOD_PROSE", p_start, p_end)

    pass  # PRUNED: body commented out
    # Rule: method-substitution / variant phrasing in prose.
    for m in _METHOD_SUBST_PROSE.finditer(text):
        p_start, p_end = _paragraph_bounds(text, m.start())
        _emit("_METHOD_SUBST_PROSE", p_start, p_end)

    results.sort(key=lambda d: text.find(d["raw_latex"][:50]))
    return results
