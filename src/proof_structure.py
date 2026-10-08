#!/usr/bin/env python3
"""Proof structure the LaTeX states by syntax, and checks on extracted proof steps.

Detection (used by `latex_facts`, reported under each proof fact's `structure`):
  labels            where the author labels the argument: anchored Step/Case/Part,
                    (i)/(a) item labels, "1." after \\smallskip/\\par/a blank line,
                    prose items of a list inside the proof, \\textbf{..}/\\emph{..}
                    headings, Base case / Inductive step, nested \\begin{proof}
  claims            sentences that open an inline claim ("We claim", "Let us show")
  paragraph_breaks  blank-line breaks that follow a complete sentence (not the
                    layout breaks around displayed equations)

A label must sit at the start of a sentence (or line, or list item), outside
math, and not be a reference ("Step (i) of the construction"). Measured on the
v5.1 corpus: a sentence-final paragraph break coincides with a step start 75% of
the time, a break next to a display 49%, a mid-sentence break 33%.

Checks (used by `extraction_finalize`): every label starts a step; steps start
only at sentence boundaries, never inside math; a proof never has exactly one
step. Warnings: a step that is only an immediate sentence, steps on a proof of
at most two sentences, a step that is a lone "Let ..." sentence.
"""
from __future__ import annotations

import re

# ── Math regions ────────────────────────────────────────────────────────────

_DISPLAY_ENVS = (r"equation|align|gather|multline|eqnarray|displaymath|flalign|alignat|"
                 r"array|cases|split|aligned|gathered|matrix|pmatrix|bmatrix|vmatrix")
_MATH = re.compile(
    r"\$\$.*?\$\$"
    r"|(?<!\\)\$(?:\\.|[^$\\])+\$"
    r"|(?<!\\)\\\[.*?\\\]"          # \[ ... \]  (but not the line break \\[5pt])
    r"|(?<!\\)\\\(.*?\\\)"
    r"|\\begin\{(" + _DISPLAY_ENVS + r")\*?\}.*?\\end\{\1\*?\}"
    r"|\\overset\{[^{}]*\}",
    re.S)


def math_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _MATH.finditer(text)]


def _inside(pos: int, spans) -> bool:
    return any(a <= pos < b for a, b in spans)


def _strictly_inside(pos: int, spans) -> bool:
    """Inside a math span, not at its first character (a step may begin with math)."""
    return any(a < pos < b for a, b in spans)


# ── Sentence starts ─────────────────────────────────────────────────────────

_LEAD_CMDS = re.compile(r"(?:\\(?:par|smallskip|medskip|bigskip|noindent|newline)\b\s*"
                        r"|\\item\s*(?:\[[^\]]*\])?\s*|\\\\\*?(?:\[[^\]]*\])?\s*)+$")


# Markup that may sit right before a sentence start: an environment opener, a
# label, a counter, an argument-free command (\\bf, \\small), the opening brace of
# a wrapper (\\footnote{, a revision macro such as \\new{), a bare brace, or a
# short parenthesised run-in label ("(Injectivity)", "(2)").
_OPENER = re.compile(r"(?:\\begin\s*\{[^{}]*\}(?:\s*\[[^\]]*\])?|\\label\s*\{[^{}]*\}"
                     r"|\\setcounter\s*\{[^{}]*\}\s*\{[^{}]*\}|\\[a-zA-Z]+\*?\s*\{|\{|\\[,;:! ]|\\$"
                     r"|\\[a-zA-Z]+\*?(?![a-zA-Z{])|\((?:[^()$]|\$[^$]*\$){1,60}\))\s*$")


def _sentence_initial(text: str, pos: int) -> bool:
    """Is `pos` at the start of a sentence, line-label or list item?

    Also true when only opening markup (`_OPENER`) separates `pos` from such a start."""
    if text[pos:pos + 5] == "\\item":
        return True
    cut = pos
    while True:
        if _sentence_initial_at(text, cut):
            return True
        m = _OPENER.search(text[:cut].rstrip())
        if not m:
            return False
        cut = m.start()


def _sentence_initial_at(text: str, pos: int) -> bool:
    before = text[:pos]
    stripped = before.rstrip()
    if not stripped:
        return True
    if re.search(r"\n\s*\n\s*$", before):
        return True
    if _LEAD_CMDS.search(stripped + " ") or _LEAD_CMDS.search(stripped):
        return True
    # right after a heading: \section{...}, \subsection*{...}, \paragraph{...},
    # possibly followed by its \label{...}
    if re.search(r"\\(?:(?:sub)*section|paragraph|subparagraph|caption)\*?\s*"
                 r"\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}\s*(?:\\label\{[^{}]*\}\s*)*$", stripped):
        return True
    # A sentence may end inside a display or inline math: "... bounded.} \\end{equation}",
    # "... x.$". Peel closers, labels, \\nonumber, spacing macros and closing braces,
    # then look. Authors often omit the period after a display, so text after a
    # display that starts with a capital letter also starts a sentence.
    tail = re.compile(r"(?:\\end\{[a-zA-Z*]+\}|\\\]|\$\$?|\\(?:label|tag)\{[^{}]*\}"
                      r"|\\[a-zA-Z]+\*?|\\[,;! ]|\\\\|\\|[})\s~&])$")
    display_closer = re.compile(r"(?:\\end\{[a-zA-Z*]+\}|\\\]|\$\$)$")
    after_display = False
    prev = None
    while stripped and stripped != prev:
        prev = stripped
        after_display = after_display or bool(display_closer.search(stripped))
        stripped = tail.sub("", stripped).rstrip()
    if stripped and stripped[-1] in ".!?:":
        return True
    nxt = text[pos:pos + 12].lstrip()
    return after_display and bool(re.match(r"[A-Z]|\\begin|\\(?:item|textbf|emph)", nxt))


# ── Labels ──────────────────────────────────────────────────────────────────

_WRAP = r"(?:\{\s*)?(?:\\(?:textbf|emph|textit|textsc|texttt|textsf|textsl|textup|underline|bf|it|em|tt|sc)\s*\{?\s*)?"
_LABEL_PATTERNS = {
    "step":   _WRAP + r"Step\s*~?\(?\s*\d+[a-z]?\s*\)?\s*\}?\s*[.:)]",
    "case":   _WRAP + r"Case\s*~?\(?\s*(?:\d+|[ivx]+|[a-dA-D])\s*\)?\s*\}?\s*[.:)]",
    "case_math": _WRAP + r"Case\s*~?\$[^$]{1,40}\$\s*(?:[.:]\s*\}|\}\s*[.:]?|[.:])",
    "part":   _WRAP + r"Part\s*~?\(?\s*(?:\d+|[ivx]+|[a-d])\s*\)?\s*\}?\s*[.:)]",
    "induct": _WRAP + r"(?:Base case|Basis(?: step)?|Induction step|Inductive step)\s*\}?\s*[.:]",
    "heading": r"\\(?:textbf|emph|textit|texttt|textsf|textsl|underline)\s*\{[^{}$]{2,60}?[.:]?\s*\}\s*[.:]?",
    "heading_switch": r"\{\s*\\(?:it|bf|em|sc|sl)\b\s*[A-Z][^{}$]{1,58}?[.:]?\s*\}\s*[.:]?",
    "degree":  r"\$\s*\d+\s*\^\s*\{?\s*\\circ\s*\}?\s*\$\s*[.:)]?",
    "implication": (r"\(\s*(?:\d+|[ivx]+|[a-d])\s*\)\s*\$?\s*\\(?:Long|long)?(?:[Rr]ightarrow|[Ll]eftrightarrow|implies)"
                    r"\s*\$?\s*\(\s*(?:\d+|[ivx]+|[a-d])\s*\)\s*[.:]?"),
}
_PAREN = re.compile(r"\{?\((?:i{1,3}|iv|vi{0,3}|ix|x|[a-h]|\d)\)\}?(?=\s)")
_RUN_IN = re.compile(r"\((?=[A-Z])(?:[^().,$]|\$[^$]*\$){2,40}\)(?=\s+(?:[A-Z]|\$|\\))")
_NUMBERED = re.compile(r"(?:\\(?:smallskip|medskip|bigskip|par)\b\s*|\n\s*\n\s*"
                       r"|\\\\\*?(?:\[[^\]]*\])?\s*)(\d{1,2})\.\s")
_REFERENCE_AFTER = re.compile(r"\s*(?:of|in)\s", re.I)
_CLAIM = re.compile(r"(?:We|I) claim|Claim\b|Let us (?:show|prove|check)|"
                    r"(?:First|Next|Now),? we (?:show|prove|check)|We show this by")


def _list_items(body: str, spans) -> list[int]:
    """\\item positions of the proof's TOP-LEVEL lists whose items are prose.

    A list nested inside a list item (e.g. a list of conditions inside one part
    of the argument) is content of that item, not the proof's structure."""
    toks = list(re.finditer(r"\\begin\{([A-Za-z]+\*?)\}|\\end\{([A-Za-z]+\*?)\}|\\item\b", body))
    # pass 1: which environments hold \item directly (list-like, whatever their name)
    stack, listy = [], set()
    for t in toks:
        if t.group(1):
            stack.append(t.group(1))
        elif t.group(2):
            if t.group(2) in stack:
                while stack and stack.pop() != t.group(2):
                    pass
        elif stack:
            listy.add(stack[-1])
    listy -= {"equation", "align", "proof", "array", "tabular", "cases"}
    # pass 2: items inside exactly one list-like environment
    out, stack = [], []
    for k, t in enumerate(toks):
        if t.group(1):
            stack.append(t.group(1))
        elif t.group(2):
            if t.group(2) in stack:
                while stack and stack.pop() != t.group(2):
                    pass
        elif sum(e in listy for e in stack) == 1 and stack and stack[-1] in listy:
            end = toks[k + 1].start() if k + 1 < len(toks) else len(body)
            text = re.sub(_MATH, " ", body[t.end():end])
            words = re.findall(r"[A-Za-z]{2,}", re.sub(r"\\[a-zA-Z]+", " ", text))
            if len(words) >= 4:
                out.append(t.start())
    return out


# Environments that are layout, lists or math inside a proof, not blocks of their own.
_LAYOUT_ENVS = {"enumerate", "itemize", "description", "compactenum", "compactitem", "inparaenum",
                "equation", "align", "gather", "multline", "eqnarray", "flalign", "alignat",
                "array", "cases", "split", "aligned", "gathered", "matrix", "pmatrix", "bmatrix",
                "tabular", "center", "flushleft", "flushright", "minipage", "small", "footnotesize",
                "figure", "table", "subequations", "displaymath", "math", "quote", "quotation"}


def _nested_blocks(body: str) -> list[tuple[int, int]]:
    """Spans of the blocks nested in a proof body (an inner proof, a quoted lemma
    or definition): the outermost `\\begin{X}...\\end{X}` whose X is not layout."""
    out, stack = [], []
    for m in re.finditer(r"\\(begin|end)\s*\{([A-Za-z]+)\*?\}", body):
        kind, name = m.group(1), m.group(2)
        if kind == "begin":
            stack.append((name, m.start()))
        elif stack and stack[-1][0] == name:
            n, a = stack.pop()
            if n not in _LAYOUT_ENVS and not any(x not in _LAYOUT_ENVS for x, _ in stack):
                out.append((a, m.end()))
    return out


def detect(body: str, nested_proof_offsets: list[int] = ()) -> dict:
    """Structure of one proof body. Offsets are relative to `body`.

    A label inside a nested block (an inner proof, a quoted lemma or definition)
    belongs to that block: the outer proof sees the block as one step."""
    spans = math_spans(body)
    blocks = _nested_blocks(body)
    labels = []

    def add(kind, pos, end):
        if _inside(pos, spans) or _REFERENCE_AFTER.match(body, end):
            return
        if any(a < pos < b for a, b in blocks):
            return
        if any(abs(pos - l["offset"]) < 3 for l in labels):
            return
        labels.append({"kind": kind, "offset": pos, "text": body[pos:end].strip()[:40]})

    for kind, pat in _LABEL_PATTERNS.items():
        for m in re.finditer(pat, body):
            if _sentence_initial(body, m.start()):
                if kind == "heading" and re.match(r"\\(?:textbf|emph)\s*\{\s*(?:Proof|Remark|Note)\b", body[m.start():]):
                    continue
                add(kind, m.start(), m.end())
    paren = [m for m in _PAREN.finditer(body)
             if _sentence_initial(body, m.start()) and not _inside(m.start(), spans)]
    if len({m.group(0) for m in paren}) >= 2:
        for m in paren:
            add("item_label", m.start(), m.end())
    run_in = [m for m in _RUN_IN.finditer(body)
              if _sentence_initial(body, m.start()) and not _inside(m.start(), spans)]
    if len(run_in) >= 2:
        for m in run_in:
            add("run_in", m.start(), m.end())
    numbered = list(_NUMBERED.finditer(body))
    if len(numbered) >= 2:
        for m in numbered:
            add("numbered", m.start(1), m.end())
    for pos in _list_items(body, spans):
        add("list_item", pos, pos + 5)
    for pos in nested_proof_offsets:
        labels.append({"kind": "nested_proof", "offset": pos, "text": "\\begin{proof}"})
    labels.sort(key=lambda l: l["offset"])

    claims = [{"offset": m.start(), "text": body[m.start():m.start() + 40]}
              for m in _CLAIM.finditer(body)
              if _sentence_initial(body, m.start()) and not _inside(m.start(), spans)]

    breaks = []
    for m in re.finditer(r"\n[ \t]*\n\s*", body):
        before, after = body[:m.start()].rstrip(), body[m.end():]
        if not before or not after.strip():
            continue
        layout = bool(re.search(r"(\\end\{[a-zA-Z*]+\}|\\\]|\$\$)$", before)
                      or re.match(r"(\\begin\{|\\\[|\$\$)", after))
        if not layout and before[-1] in ".!?:":
            breaks.append(m.end())
    return {"labels": labels, "claims": claims, "paragraph_breaks": breaks}


# ── Checks on extracted steps ───────────────────────────────────────────────

_IMMEDIATE = re.compile(
    r"\b(?:clear(?:ly)?|obvious(?:ly)?|trivial(?:ly)?|immediate(?:ly)?|at once|easy|easily|"
    r"straightforward|tautological|by inspection|similarly|a similar argument|"
    r"the same argument|as above|we can verify|left to the reader)\b"
    r"|^(?:This|which) (?:completes|finishes|proves|concludes)", re.I)
_INTRO = re.compile(r"^(?:Let|Take|Consider|Define|Fix|Denote|Set)\b")
_DISPLAY_IN = re.compile(r"\$\$|(?<!\\)\\\[|\\begin\{(?:equation|align|gather|multline|eqnarray|displaymath)")
_CLOSING = re.compile(r"^(?:This|which|That)\s+(?:completes|finishes|proves|concludes)\b|^\\qed\b", re.I)
_CASE_OPENER = re.compile(r"^\s*(?:So\s+)?(?:first\s+)?(?:Suppose|Assume|If|Let us assume|Base case|Basis|"
                          r"Conversely|Otherwise|Else|Now suppose|Suppose now)\b")
# an induction base case ("The case $k=1$ is obvious", "For $n=0$ ...") is never immediate
_BASE_CASE = re.compile(r"^\s*(?:(?:In|For|When)\s+)?(?:the\s+)?(?:base\s+case|initial\s+case"
                        r"|case\s+(?:of\s+|where\s+)?\$[^$]{1,30}=\s*[012]\s*\$"
                        r"|\$[^$]{1,20}=\s*[012]\s*\$)", re.I)


def _norm_map(text: str) -> tuple[str, list[int]]:
    """Text without \\label/\\index and whitespace, plus each kept char's raw offset."""
    drop = [(m.start(), m.end()) for m in re.finditer(r"\\(?:label|index)\s*\{[^{}]*\}", text)]
    out, idx, d = [], [], 0
    for i, ch in enumerate(text):
        while d < len(drop) and i >= drop[d][1]:
            d += 1
        if d < len(drop) and drop[d][0] <= i < drop[d][1]:
            continue
        if not ch.isspace():
            out.append(ch)
            idx.append(i)
    return "".join(out), idx


def _sentences(text: str) -> int:
    def sub(m):        # a display that ends a sentence keeps its period
        inner = re.sub(r"(\\end\{[a-zA-Z*]+\}|\\\]|\$\$?|\\(?:label|tag)\{[^{}]*\}|\s)+$", "", m.group(0))
        return " X. " if inner.endswith(".") else " X "
    plain = _MATH.sub(sub, text)
    return max(1, len([s for s in re.split(r"(?<=[.!?:])\s+(?=[A-Z\\])", plain.strip()) if s.strip()]))


def check_steps(body: str, structure: dict, steps: list[dict]) -> tuple[list[str], list[str]]:
    """Errors and warnings for the proof_steps (all depths) of one proof.

    `steps` are the step nodes; their statements are verbatim spans of `body`.
    """
    errors, warnings = [], []
    required = [lab for lab in structure["labels"] if lab["kind"] != "nested_proof"]
    if not steps:
        if len(required) >= 2:                # a single label alone is one move: zero steps
            errors.append(f"author labels present ({len(required)}) but no proof_steps")
        return errors, warnings
    if len(steps) == 1:
        errors.append("exactly one proof_step: a one-move proof gets zero steps")
    # the same at every level: a step with one child would be that child
    n_children: dict = {}
    for s in steps:
        n_children[s.get("parent_id")] = n_children.get(s.get("parent_id"), 0) + 1
    for s in steps:
        if n_children.get(s["id"]) == 1:
            errors.append(f"{s['id']}: exactly one child step; give it none or at least two")
    norm, idx = _norm_map(body)
    spans = math_spans(body)
    starts, setups = {}, []
    for s in steps:
        key = re.sub(r"\s+", "", re.sub(r"\\(?:label|index)\s*\{[^{}]*\}", "", s.get("statement") or ""))
        i = norm.find(key[:40]) if key else -1
        if i < 0:
            continue                      # verbatim errors are reported elsewhere
        pos = idx[i]
        starts[s["id"]] = pos
        if s.get("subclass") == "setup":
            j = norm.find(key, i)
            if j >= 0:
                setups.append((pos, idx[j + len(key) - 1] + 1))
        if _strictly_inside(pos, spans):
            errors.append(f"{s['id']}: step starts inside math")
        elif not _sentence_initial(body, pos) and not any(
                abs(pos - l["offset"]) <= 12 for l in structure["labels"]):
            prev = body[:pos].rstrip()[-1:] or " "
            # A lowercase start ("and by Theorem", "where", "is a ...") is a certain
            # continuation; a capitalised one after unusual markup may be a false alarm.
            certain = prev != ";" and not re.match(r"\s*[A-Z]", body[pos:pos + 3])
            (errors if certain else warnings).append(
                f"{s['id']}: step starts mid-sentence (after {prev!r})")
        st = s.get("statement") or ""
        at_label = any(abs(pos - l["offset"]) <= 12 for l in structure["labels"])
        has_display = bool(_DISPLAY_IN.search(st))
        has_ref = bool(re.search(r"\\(?:ref|eqref|cite|autoref|cref)", st))
        closing = bool(_CLOSING.search(st))
        immediate = (closing or (_IMMEDIATE.search(st) and not has_ref)) and not has_display
        if (immediate and not at_label and len(st) < 200 and not _CASE_OPENER.match(st)
                and not _BASE_CASE.match(st)):
            errors.append(f"{s['id']}: step is an immediate sentence (attach it to a neighbour)")
        if (_INTRO.match(st) and _sentences(st) == 1 and len(steps) > 1
                and not has_display and not has_ref):
            errors.append(f"{s['id']}: lone introduction sentence (join it to the next step)")
    for lab in required:                      # a nested proof sits inside a setup step (rule 10)
        if any(a < lab["offset"] < b for a, b in setups):
            continue                          # inside a quoted restatement (rule 5)
        if not any(abs(p - lab["offset"]) <= 12 for p in starts.values()):
            errors.append(f"author label {lab['text']!r} ({lab['kind']}) does not start a step")
    if _sentences(body) <= 2 and not structure["labels"]:
        errors.append("steps on a proof of at most two sentences (expected zero)")
    return errors, warnings
