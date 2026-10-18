#!/usr/bin/env python3
"""Fill `source_line_label` on algorithm_step nodes from the paper's own line numbers.

Pseudocode line numbers are not in the .tex source: LaTeX computes them when it
typesets the algorithm. Prose cites them ("in line 4 of Algorithm 2"), so a step
must carry the number the PDF prints, which `step_order` does not: merged or
skipped control lines make the two drift apart. This module replays the
numbering deterministically and matches each extracted step to its printed line.

It is part of the v6 extraction pipeline. The extraction agent's builder script
calls `fill_source_line_labels()` before the final write and must fix every
MERGED problem it reports. The LLM never fills `source_line_label` by hand.

Supported packages (the three found in the silver corpus):
  algorithmic    \\STATE \\IF ... \\ENDIF        numbered iff \\begin{algorithmic}[n], n >= 1
  algpseudocode  \\State \\If ... \\EndIf        same rule (algorithmicx)
  algorithm2e    \\; \\If{c}{body} \\ForAll ...  numbered iff [linesnumbered] or \\LinesNumbered

Where numbering cannot be determined (unnumbered environment, unknown package,
prose algorithm) the label stays null. That is correct, not a failure.

Usage:
    python3 src/algorithm_lines.py --tex paper.tex --json paper.json           # report only
    python3 src/algorithm_lines.py --tex paper.tex --json paper.json --write   # fill labels in place
Exit status 1 when a step spans more than one numbered line (MERGED), so a
builder script can assert on it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field

# ── Source normalisation (same mechanical cleanup the extraction spec permits) ──

_LABEL = re.compile(r"\\(?:label|index|nllabel)\s*\{[^{}]*\}")


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from latex_macros import strip_comments  # noqa: E402


def norm(s: str) -> str:
    """Canonical form for matching: no labels, braces or whitespace."""
    s = _LABEL.sub("", s)
    s = re.sub(r"\\\\(?:\[[^\]]*\])?", "", s)      # a trailing \\ line break is not content
    s = re.sub(r"[{}\s]", "", s)
    return s


# ── Data model ──────────────────────────────────────────────────────────────

@dataclass
class Line:
    number: int | None      # printed line number, None if not numbered
    kind: str               # state / if / else / end / repeat / until / return / ...
    content: str            # the line's text (condition for block headers)
    label: str | None = None  # \label / \nllabel key placed on this line
    start: int | None = None  # the line's verbatim span in the text given to
    end: int | None = None    #   find_blocks (None: printed but not in the source)
    parent: int | None = None  # index of the enclosing block header in Block.lines


def _trim(text: str, a: int, b: int) -> tuple[int, int]:
    """Shrink [a, b) to exclude surrounding whitespace and a trailing line break
    (\\\\ or \\;), which is layout, not content."""
    while a < b and text[a].isspace():
        a += 1
    while True:
        while b > a and text[b - 1].isspace():
            b -= 1
        if b - a >= 2 and text[b - 2:b] in ("\\\\", "\\;") and not (b - a >= 3 and text[b - 3] == "\\"):
            b -= 2
            continue
        return a, b


# Block structure, shared by both parsers: a header opens a block, else/elsif
# continues the open if-block, end/until closes it. The lines inside a block are
# its children; a header, an else and an end are siblings of each other.
_OPENS = {"if", "for", "while", "loop", "repeat", "function", "switch", "case", "begin"}


@dataclass
class Block:
    package: str            # algorithmic / algpseudocode / algorithm2e
    numbered: bool
    start: int              # offset of the environment in the comment-stripped source
    lines: list[Line] = field(default_factory=list)


def _brace_arg(s: str, i: int) -> tuple[str, int]:
    """Read one {...} argument starting at or after s[i]; return (content, end)."""
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s) or s[i] != "{":
        return "", i
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def _number(lines: list[Line], numbered: bool) -> list[Line]:
    # A header with children spans them: its span runs to the end of its last
    # descendant, so the header's step contains its body (the hierarchy rule).
    for ln in reversed(lines):
        if ln.parent is not None and ln.end is not None:
            p = lines[ln.parent]
            if p.end is not None and ln.end > p.end:
                p.end = ln.end
    n = 0
    for ln in lines:
        if ln.number == -1:          # sentinel: this kind of line is printed and counted
            n += 1
            ln.number = n if numbered else None
    return lines


def _take_label(text: str) -> tuple[str, str | None]:
    m = re.search(r"\\(?:label|nllabel)\s*\{([^{}]*)\}", text)
    return (_LABEL.sub("", text), m.group(1) if m else None)


# ── algorithmic / algpseudocode ─────────────────────────────────────────────

# command -> (kind, takes a {condition} argument)
_ALGX_LINE = {
    "state": ("state", False), "if": ("if", True), "elsif": ("else", True),
    "else": ("else", False), "for": ("for", True), "forall": ("for", True),
    "while": ("while", True), "repeat": ("repeat", False), "until": ("until", True),
    "loop": ("loop", False), "return": ("return", False), "print": ("state", False),
    "function": ("function", True), "procedure": ("function", True),
    "endif": ("end", False), "endfor": ("end", False), "endwhile": ("end", False),
    "endloop": ("end", False), "endfunction": ("end", False), "endprocedure": ("end", False),
}
_ALGX_UNNUMBERED = {"require", "ensure", "statex", "input", "output"}
# Exact spellings only: algorithmic is UPPERCASE (\\FORALL), algpseudocode is
# CamelCase (\\ForAll). Matching case-insensitively would read the math symbol
# \\forall as a loop line.
_ALGX_SPELLINGS = {"elsif": ["ELSIF", "ElsIf"], "forall": ["FORALL", "ForAll"],
                   "endif": ["ENDIF", "EndIf"], "endfor": ["ENDFOR", "EndFor"],
                   "endwhile": ["ENDWHILE", "EndWhile"], "endloop": ["ENDLOOP", "EndLoop"],
                   "endfunction": ["ENDFUNCTION", "EndFunction"],
                   "endprocedure": ["ENDPROCEDURE", "EndProcedure"]}
_ALGX_NAMES = {}
for _c in set(_ALGX_LINE) | _ALGX_UNNUMBERED:
    for _sp in _ALGX_SPELLINGS.get(_c, [_c.upper(), _c.capitalize()]):
        _ALGX_NAMES[_sp] = _c
_ALGX_TOKEN = re.compile(
    r"\\(" + "|".join(sorted(_ALGX_NAMES, key=len, reverse=True)) + r")(?![A-Za-z])")


def _parse_algorithmic(body: str, numbered: bool, noend: bool, package: str,
                       base: int = 0) -> list[Line]:
    lines: list[Line] = []
    stack: list[int] = []          # open block headers (indices into lines)
    toks = list(_ALGX_TOKEN.finditer(body))
    for k, m in enumerate(toks):
        cmd = _ALGX_NAMES[m.group(1)]
        end = toks[k + 1].start() if k + 1 < len(toks) else len(body)
        if cmd in _ALGX_UNNUMBERED:
            continue
        kind, has_cond = _ALGX_LINE[cmd]
        # algpseudocode's \Return is inline inside \State; algorithmic's \RETURN is a line
        if cmd == "return" and package == "algpseudocode":
            continue
        # where this line sits in the block structure (also for unprinted ends)
        if kind == "else":
            while stack and lines[stack[-1]].kind not in ("if", "else"):
                stack.pop()
            if stack:
                stack.pop()
        elif kind in ("end", "until"):
            if stack:
                stack.pop()
        parent = stack[-1] if stack else None
        if kind == "end" and noend:
            continue                   # closes its block, but is not a printed line
        if has_cond:
            cond, after = _brace_arg(body, m.end())
            if cmd in ("function", "procedure"):   # \Function{name}{args}
                args, after = _brace_arg(body, after)
                cond = cond + "(" + args + ")"
            text = cond
            a, b = m.start(), after                # a header keeps its command
        else:
            text = body[m.end():end]
            text = re.sub(r"\\(?:COMMENT|Comment)\s*\{[^{}]*\}", "", text)
            if kind == "state":
                a, b = _trim(body, m.end(), end)   # a statement without its \STATE
            elif kind == "return":
                a, b = _trim(body, m.start(), end)
            else:
                a, b = m.start(), m.end()          # \ELSE, \ENDIF, \REPEAT
        text, label = _take_label(text)
        if label is None:
            _, label = _take_label(body[m.end():end])
        lines.append(Line(-1, kind, text.strip(), label, base + a, base + b, parent))
        if kind in _OPENS or kind == "else":
            stack.append(len(lines) - 1)
    return _number(lines, numbered)


# ── algorithm2e ─────────────────────────────────────────────────────────────

_A2E_BLOCK = {  # macro -> kind; each takes {cond}{body}
    "For": "for", "ForAll": "for", "ForEach": "for", "While": "while",
    "If": "if", "uIf": "if", "ElseIf": "else", "uElseIf": "else",
    "Switch": "switch", "Case": "case", "uCase": "case",
}
_A2E_ONE_ARG_BLOCK = {"Else": "else", "uElse": "else", "Other": "case", "Begin": "begin"}
_A2E_ONE_LINE = {"lIf", "lFor", "lForAll", "lForEach", "lWhile", "lElseIf", "lCase"}
_A2E_IGNORE = {"KwIn", "KwOut", "KwData", "KwResult", "Input", "Output", "caption",
               "SetKwFunction", "SetKwProg", "SetKwInOut", "SetKwInput", "SetKw",
               "SetKwData", "SetAlgoLined", "SetAlgoNoLine", "SetAlgoVlined",
               "DontPrintSemicolon", "LinesNumbered", "LinesNumberedHidden",
               "SetAlgoNoEnd", "SetNlSty", "BlankLine", "tcp*", "tcc*", "Indp", "Indm"}
_A2E_CMD = re.compile(r"\\([A-Za-z]+\*?)")


def _parse_a2e(body: str, numbered: bool, comments_numbered: bool, base: int = 0) -> list[Line]:
    lines: list[Line] = []
    cur = {"parent": None}             # header of the block being walked

    def add(kind, text, label=None, a=None, b=None):
        if a is not None:
            a, b = _trim(body, a, b)
        lines.append(Line(-1, kind, text, label,
                          None if a is None else base + a, None if a is None else base + b,
                          cur["parent"]))
        return len(lines) - 1

    def flush(buf: list[str], span: list):
        text = "".join(buf)
        if text.strip():
            text, label = _take_label(text)
            if text.strip() or label:
                add("state", text.strip(), label, span[0], span[1])
        buf.clear()
        span[0] = None

    def inner_walk(header: int, off: int, content: str):
        saved = cur["parent"]
        cur["parent"] = header
        walk(content, off)
        cur["parent"] = saved

    def walk(s: str, off: int = 0):
        """`off` is the offset of s[0] in `body`."""
        buf: list[str] = []
        span: list = [None, None]
        i = 0

        def keep(c, at, upto):
            if span[0] is None:
                span[0] = off + at
            span[1] = off + upto
            buf.append(c)
        while i < len(s):
            if s.startswith("\\;", i):
                flush(buf, span)
                i += 2
                continue
            m = _A2E_CMD.match(s, i)
            if not m:
                keep(s[i], i, i + 1)
                i += 1
                continue
            name = m.group(1)
            j = m.end()

            def arg_at(pos):
                """(content, end, offset of content in s)"""
                p = pos
                while p < len(s) and s[p].isspace():
                    p += 1
                content, e = _brace_arg(s, pos)
                return content, e, p + 1
            if name in _A2E_BLOCK:
                flush(buf, span)
                cond, j, _ = arg_at(j)
                cond, label = _take_label(cond)
                h = add(_A2E_BLOCK[name], cond.strip(), label, off + i, off + j)
                inner, j, io = arg_at(j)
                inner_walk(h, off + io, inner)
            elif name == "eIf":
                flush(buf, span)
                cond, j, _ = arg_at(j)
                h = add("if", cond.strip(), None, off + i, off + j)
                then, j, to = arg_at(j)
                inner_walk(h, off + to, then)
                other, j2, oo = arg_at(j)
                # printed with no text of its own: its span starts at the else-branch's brace
                # and grows to its last child (_number), so the enclosing block spans it too
                e = add("else", "", None, off + oo - 1, off + oo)
                inner_walk(e, off + oo, other)
                j = j2
            elif name in _A2E_ONE_ARG_BLOCK:
                flush(buf, span)
                h = add(_A2E_ONE_ARG_BLOCK[name], "", None, off + i, off + j)
                inner, j, io = arg_at(j)
                inner_walk(h, off + io, inner)
            elif name == "Repeat":          # \Repeat{until-cond}{body}
                flush(buf, span)
                cond, j, co = arg_at(j)
                h = add("repeat", "", None, off + i, off + m.end())
                inner, j, io = arg_at(j)
                inner_walk(h, off + io, inner)
                add("until", cond.strip(), None, off + co, off + co + len(cond))
            elif name in _A2E_ONE_LINE or name in ("leIf", "lElse"):
                flush(buf, span)
                nargs = {"leIf": 3, "lElse": 1}.get(name, 2)
                parts = []
                for _ in range(nargs):
                    a, j = _brace_arg(s, j)
                    parts.append(a)
                text, label = _take_label(" ".join(parts))
                add("state", text.strip(), label, off + i, off + j)
            elif name in ("Return", "KwRet"):
                flush(buf, span)
                arg, j2 = _brace_arg(s, j)
                if not s[j:j2].strip().startswith("{"):   # \Return without braces: rest of the line
                    k = s.find("\\;", j)
                    nl = s.find("\n", j)
                    stop = min(x for x in (k, nl, len(s)) if x != -1)
                    arg, j2 = s[j:stop], stop
                text, label = _take_label(arg)
                add("return", text.strip(), label, off + i, off + j2)
                j = j2
            elif name in ("tcp", "tcc"):
                flush(buf, span)
                arg, j = _brace_arg(s, j)
                if comments_numbered:
                    add("comment", arg.strip(), None, off + i, off + j)
            elif name in _A2E_IGNORE:
                if name in ("KwIn", "KwOut", "KwData", "KwResult", "Input", "Output",
                            "caption", "SetKwFunction", "SetKwProg", "SetKwInOut",
                            "SetKwInput", "SetKw", "SetKwData", "tcp*", "tcc*"):
                    while j < len(s) and s[j] in " \t\n[":
                        if s[j] == "[":
                            j = s.find("]", j) + 1 or len(s)
                        else:
                            j += 1
                    for _ in range({"SetKwFunction": 2, "SetKwProg": 4, "SetKwInOut": 2,
                                    "SetKwInput": 2, "SetKw": 2, "SetKwData": 2}.get(name, 1)):
                        _, j = _brace_arg(s, j)
            else:
                keep(m.group(0), i, j)
            i = j
        flush(buf, span)

    walk(body)
    return _number(lines, numbered)


# ── Finding the algorithm blocks in a paper ─────────────────────────────────

def _packages(tex: str) -> dict[str, str]:
    """package name -> option string, for the algorithm packages loaded."""
    found = {}
    for opts, names in re.findall(r"\\usepackage\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}", tex):
        for name in names.split(","):
            name = name.strip()
            if name in ("algorithmic", "algpseudocode", "algorithmicx", "algorithm2e"):
                found[name] = opts or ""
    return found


def _drop_float_label(body: str) -> str:
    """Remove the algorithm's own caption and \\label, which label the float, not a line."""
    m = re.search(r"\\caption\s*(?:\[[^\]]*\])?", body)
    if m:
        _, end = _brace_arg(body, m.end())
        body = body[:m.start()] + " " * (end - m.start()) + body[end:]
    # same length: line offsets must still index the original text
    return re.sub(r"^\s*\\label\s*\{[^{}]*\}", lambda x: " " * len(x.group(0)), body)


def find_blocks(tex: str) -> list[Block]:
    src = strip_comments(tex)
    pk = _packages(src)
    blocks: list[Block] = []
    algx = "algpseudocode" if ("algpseudocode" in pk or "algorithmicx" in pk) else "algorithmic"
    noend = "noend" in pk.get(algx, "")
    for m in re.finditer(r"\\begin\s*\{algorithmic\}(\[[^\]]*\])?(.*?)\\end\s*\{algorithmic\}", src, re.S):
        opt = (m.group(1) or "").strip("[]").strip()
        numbered = opt.isdigit() and int(opt) >= 1
        blocks.append(Block(algx, numbered, m.start(),
                            _parse_algorithmic(m.group(2), numbered, noend, algx, m.start(2))))
    if "algorithm2e" in pk:
        opts = pk["algorithm2e"]
        numbered = "linesnumbered" in opts or bool(re.search(r"\\LinesNumbered(?!Hidden)", src))
        comments_numbered = "commentsnumbered" in opts
        # [algo2e] renames the float to algorithm2e (to coexist with the algorithm package)
        env = r"(?:algorithm(?:2e)?\*?|procedure\*?|function\*?)"
        for m in re.finditer(r"\\begin\s*\{(" + env + r")\}(\[[^\]]*\])?(.*?)\\end\s*\{\1\}", src, re.S):
            body = m.group(3)
            if "\\begin{algorithmic}" in body:
                continue
            body = _drop_float_label(body)
            blocks.append(Block("algorithm2e", numbered, m.start(),
                                _parse_a2e(body, numbered, comments_numbered, m.start(3))))
    # A numbered list used as pseudocode inside an algorithm float: enumerate
    # prints 1, 2, 3 for its top-level items. An item of a nested list is a
    # child line of the item it sits under (unnumbered here), and that item's
    # span runs to the end of its last child.
    taken = {b.start for b in blocks}
    for m in re.finditer(r"\\begin\s*\{(algorithm(?:2e)?\*?)\}(.*?)\\end\s*\{\1\}", src, re.S):
        body = m.group(2)
        if "\\begin{algorithmic}" in body or any(m.start() == t for t in taken):
            continue
        em = re.search(r"\\begin\{enumerate\}(?:\[[^\]]*\])?(.*)\\end\{enumerate\}", body, re.S)
        if not em:
            continue
        lines, n = [], 0
        stack = [None]               # the line each open list's items belong to
        toks = list(re.finditer(r"\\begin\{(?:enumerate|itemize)\}|\\end\{(?:enumerate|itemize)\}|\\item\b", em.group(1)))
        for k, t in enumerate(toks):
            tok = t.group(0)
            if tok.startswith("\\begin"):
                stack.append(len(lines) - 1 if lines else None)
            elif tok.startswith("\\end"):
                if len(stack) > 1:
                    stack.pop()
            else:
                top = len(stack) == 1
                if top:
                    n += 1
                end = toks[k + 1].start() if k + 1 < len(toks) else len(em.group(1))
                text, label = _take_label(em.group(1)[t.end():end])
                text = re.sub(r"^\s*\[[^\]]*\]", "", text)
                g = m.start(2) + em.start(1)
                a, b = _trim(src, g + t.end(), g + end)
                lines.append(Line(n if top else None, "state", text.strip(), label, a, b, stack[-1]))
        _number(lines, True)
        if lines:
            blocks.append(Block("enumerate", True, m.start(), lines))
    blocks.sort(key=lambda b: b.start)
    return blocks


# ── Matching steps to printed lines ─────────────────────────────────────────

_CONTROL_WORDS = re.compile(
    r"^(?:\\?(?:STATE|State|IF|If|ELSIF|ElsIf|ElseIf|ELSE|Else|FOR|For|FORALL|ForAll|"
    r"WHILE|While|REPEAT|Repeat|UNTIL|Until|RETURN|Return))?\s*"
    r"(?:if|else\s*if|else|for\s*all|for\s*each|for|while|repeat|until|return)?\b",
    re.I)


def _step_text(statement: str) -> str:
    return norm(_CONTROL_WORDS.sub("", statement.strip(), count=1))


def _line_text(content: str) -> str:
    """A printed line, normalised exactly like a step (same control-word stripping)."""
    return norm(_CONTROL_WORDS.sub("", content.strip(), count=1))


def _covers(step_n: str, line_n: str) -> bool:
    if not line_n:
        return False
    if len(line_n) < 4:
        return step_n == line_n
    return line_n in step_n


def _steps_of(graph: dict, alg_id: str) -> list[dict]:
    """All algorithm_step nodes under `alg_id`, any nesting depth, in document order."""
    kids: dict[str, list[dict]] = {}
    for n in graph["nodes"]:
        if n.get("type") == "algorithm_step" and n.get("parent_id"):
            kids.setdefault(n["parent_id"], []).append(n)
    out: list[dict] = []

    def rec(pid):
        for n in sorted(kids.get(pid, []), key=lambda x: x.get("step_order") or 0):
            out.append(n)
            rec(n["id"])
    rec(alg_id)
    return out


def fill_source_line_labels(graph: dict, tex: str) -> dict:
    """Set `source_line_label` (and `label`, if empty) on every algorithm_step.

    Mutates `graph`. Returns a report:
      matched    steps given a printed line number
      merged     steps whose span covers more than one numbered line (must be fixed)
      unmatched  steps under a numbered block that match no line
      uncovered  numbered lines no step covers (informational)
    """
    blocks = [b for b in find_blocks(tex) if b.lines]
    report = {"blocks": len(blocks), "numbered_blocks": sum(b.numbered for b in blocks),
              "matched": [], "merged": [], "unmatched": [], "uncovered": []}
    for step in (n for n in graph["nodes"] if n.get("type") == "algorithm_step"):
        step["source_line_label"] = None
    used: set[int] = set()
    for alg in (n for n in graph["nodes"] if n.get("type") == "algorithm"):
        steps = _steps_of(graph, alg["id"])
        if not steps:
            continue
        snorm = [_step_text(s.get("statement") or "") for s in steps]
        # The block this algorithm came from: the one whose lines its steps cover most.
        best, best_score = None, 0
        for bi, b in enumerate(blocks):
            if bi in used:
                continue
            score = sum(any(_covers(sn, _line_text(l.content)) for sn in snorm) for l in b.lines)
            if score > best_score:
                best, best_score = bi, score
        if best is None:
            continue
        used.add(best)
        b = blocks[best]
        if not b.numbered:
            continue
        covered: set[int] = set()
        children = {s["id"] for s in steps}
        last = 0
        # A step whose statement IS a line's span (as pseudocode_steps builds
        # them) is that line: match it exactly, before any approximate matching.
        src = strip_comments(tex)
        exact, taken = {}, set()
        spans = [(k, norm(src[l.start:l.end])) for k, l in enumerate(b.lines) if l.start is not None]
        for st in steps:
            stn = norm(st.get("statement") or "")
            for k, t in spans:
                if k not in taken and t == stn:
                    taken.add(k)
                    exact[st["id"]] = b.lines[k]
                    break
        for s, sn in zip(steps, snorm):
            if s["id"] in exact:
                ln = exact[s["id"]]
                if ln.number:
                    s["source_line_label"] = str(ln.number)
                    if ln.label and not s.get("label"):
                        s["label"] = ln.label
                    covered.add(ln.number)
                    last = ln.number
                    report["matched"].append((s["id"], ln.number))
                continue
            # Steps are in document order, so a step's line comes after the previous
            # step's. This separates repeated lines (two identical loop headers).
            hit = [l for l in b.lines if l.number and l.number > last
                   and _covers(sn, _line_text(l.content))]
            # A block-header step may contain its children's lines; only the lines
            # not claimed by a descendant step count against it.
            own = [l for l in hit
                   if not any(t is not s and t.get("parent_id") in children | {s["id"]}
                              and _covers(_step_text(t.get("statement") or ""), _line_text(l.content))
                              for t in steps)]
            lines = own or hit[:1]
            if not lines:
                report["unmatched"].append(s["id"])
                continue
            first = lines[0]
            last = first.number
            s["source_line_label"] = str(first.number)
            if first.label and not s.get("label"):
                s["label"] = first.label
            covered.update(l.number for l in hit)
            report["matched"].append((s["id"], first.number))
            if len(own) > 1:
                report["merged"].append((s["id"], [l.number for l in own]))
        for l in b.lines:
            if l.number and l.number not in covered and l.kind != "end":
                report["uncovered"].append((alg["id"], l.number, l.content[:60]))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tex", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--write", action="store_true", help="write labels back into --json")
    args = ap.parse_args()
    tex = open(args.tex, encoding="utf-8", errors="replace").read()
    graph = json.load(open(args.json, encoding="utf-8"))
    rep = fill_source_line_labels(graph, tex)
    print(f"blocks: {rep['blocks']} ({rep['numbered_blocks']} numbered); "
          f"steps labelled: {len(rep['matched'])}; merged: {len(rep['merged'])}; "
          f"unmatched: {len(rep['unmatched'])}; uncovered lines: {len(rep['uncovered'])}")
    for sid, nums in rep["merged"]:
        print(f"  MERGED    {sid} covers printed lines {nums}: split it, one step per line")
    for sid in rep["unmatched"]:
        print(f"  UNMATCHED {sid}: no printed line found for this step's text")
    for aid, num, txt in rep["uncovered"]:
        print(f"  UNCOVERED {aid} line {num}: {txt}")
    if args.write:
        tmp = args.json + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=1)
        os.replace(tmp, args.json)
    sys.exit(1 if rep["merged"] else 0)


if __name__ == "__main__":
    main()
