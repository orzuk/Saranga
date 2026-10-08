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

_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
_LABEL = re.compile(r"\\(?:label|index|nllabel)\s*\{[^{}]*\}")


def strip_comments(tex: str) -> str:
    return _COMMENT.sub("", tex)


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


def _parse_algorithmic(body: str, numbered: bool, noend: bool, package: str) -> list[Line]:
    lines: list[Line] = []
    toks = list(_ALGX_TOKEN.finditer(body))
    for k, m in enumerate(toks):
        cmd = _ALGX_NAMES[m.group(1)]
        end = toks[k + 1].start() if k + 1 < len(toks) else len(body)
        if cmd in _ALGX_UNNUMBERED:
            continue
        kind, has_cond = _ALGX_LINE[cmd]
        if kind == "end" and noend:
            continue
        # algpseudocode's \Return is inline inside \State; algorithmic's \RETURN is a line
        if cmd == "return" and package == "algpseudocode":
            continue
        if has_cond:
            cond, after = _brace_arg(body, m.end())
            if cmd in ("function", "procedure"):   # \Function{name}{args}
                args, after = _brace_arg(body, after)
                cond = cond + "(" + args + ")"
            text = cond
        else:
            text = body[m.end():end]
            text = re.sub(r"\\(?:COMMENT|Comment)\s*\{[^{}]*\}", "", text)
        text, label = _take_label(text)
        if label is None:
            _, label = _take_label(body[m.end():end])
        lines.append(Line(-1, kind, text.strip(), label))
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


def _parse_a2e(body: str, numbered: bool, comments_numbered: bool) -> list[Line]:
    lines: list[Line] = []

    def flush(buf: list[str]):
        text = "".join(buf)
        if text.strip():
            text, label = _take_label(text)
            if text.strip() or label:
                lines.append(Line(-1, "state", text.strip(), label))
        buf.clear()

    def walk(s: str):
        buf: list[str] = []
        i = 0
        while i < len(s):
            if s.startswith("\\;", i):
                flush(buf)
                i += 2
                continue
            m = _A2E_CMD.match(s, i)
            if not m:
                buf.append(s[i])
                i += 1
                continue
            name = m.group(1)
            j = m.end()
            if name in _A2E_BLOCK:
                flush(buf)
                cond, j = _brace_arg(s, j)
                cond, label = _take_label(cond)
                lines.append(Line(-1, _A2E_BLOCK[name], cond.strip(), label))
                inner, j = _brace_arg(s, j)
                walk(inner)
            elif name == "eIf":
                flush(buf)
                cond, j = _brace_arg(s, j)
                lines.append(Line(-1, "if", cond.strip()))
                then, j = _brace_arg(s, j)
                walk(then)
                lines.append(Line(-1, "else", ""))
                other, j = _brace_arg(s, j)
                walk(other)
            elif name in _A2E_ONE_ARG_BLOCK:
                flush(buf)
                lines.append(Line(-1, _A2E_ONE_ARG_BLOCK[name], ""))
                inner, j = _brace_arg(s, j)
                walk(inner)
            elif name == "Repeat":          # \Repeat{until-cond}{body}
                flush(buf)
                cond, j = _brace_arg(s, j)
                lines.append(Line(-1, "repeat", ""))
                inner, j = _brace_arg(s, j)
                walk(inner)
                lines.append(Line(-1, "until", cond.strip()))
            elif name in _A2E_ONE_LINE or name in ("leIf", "lElse"):
                flush(buf)
                nargs = {"leIf": 3, "lElse": 1}.get(name, 2)
                parts = []
                for _ in range(nargs):
                    a, j = _brace_arg(s, j)
                    parts.append(a)
                text, label = _take_label(" ".join(parts))
                lines.append(Line(-1, "state", text.strip(), label))
            elif name in ("Return", "KwRet"):
                flush(buf)
                arg, j2 = _brace_arg(s, j)
                if not s[j:j2].strip().startswith("{"):   # \Return without braces: rest of the line
                    k = s.find("\\;", j)
                    nl = s.find("\n", j)
                    stop = min(x for x in (k, nl, len(s)) if x != -1)
                    arg, j2 = s[j:stop], stop
                text, label = _take_label(arg)
                lines.append(Line(-1, "return", text.strip(), label))
                j = j2
            elif name in ("tcp", "tcc"):
                flush(buf)
                arg, j = _brace_arg(s, j)
                if comments_numbered:
                    lines.append(Line(-1, "comment", arg.strip()))
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
                buf.append(m.group(0))
            i = j
        flush(buf)

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
        body = body[:m.start()] + " " + body[end:]
    return re.sub(r"^\s*\\label\s*\{[^{}]*\}", " ", body)


def find_blocks(tex: str) -> list[Block]:
    src = strip_comments(tex)
    pk = _packages(src)
    blocks: list[Block] = []
    algx = "algpseudocode" if ("algpseudocode" in pk or "algorithmicx" in pk) else "algorithmic"
    noend = "noend" in pk.get(algx, "")
    for m in re.finditer(r"\\begin\{algorithmic\}(\[[^\]]*\])?(.*?)\\end\{algorithmic\}", src, re.S):
        opt = (m.group(1) or "").strip("[]").strip()
        numbered = opt.isdigit() and int(opt) >= 1
        blocks.append(Block(algx, numbered, m.start(),
                            _parse_algorithmic(m.group(2), numbered, noend, algx)))
    if "algorithm2e" in pk:
        opts = pk["algorithm2e"]
        numbered = "linesnumbered" in opts or bool(re.search(r"\\LinesNumbered(?!Hidden)", src))
        comments_numbered = "commentsnumbered" in opts
        env = r"(?:algorithm\*?|procedure\*?|function\*?)"
        for m in re.finditer(r"\\begin\{(" + env + r")\}(\[[^\]]*\])?(.*?)\\end\{\1\}", src, re.S):
            body = m.group(3)
            if "\\begin{algorithmic}" in body:
                continue
            body = _drop_float_label(body)
            blocks.append(Block("algorithm2e", numbered, m.start(),
                                _parse_a2e(body, numbered, comments_numbered)))
    # A numbered list used as pseudocode inside an algorithm float: enumerate
    # prints 1, 2, 3 for its top-level items (nested lists are not numbered here).
    taken = {b.start for b in blocks}
    for m in re.finditer(r"\\begin\{(algorithm\*?)\}(.*?)\\end\{\1\}", src, re.S):
        body = m.group(2)
        if "\\begin{algorithmic}" in body or any(m.start() == t for t in taken):
            continue
        em = re.search(r"\\begin\{enumerate\}(?:\[[^\]]*\])?(.*)\\end\{enumerate\}", body, re.S)
        if not em:
            continue
        lines, depth, n = [], 0, 0
        toks = list(re.finditer(r"\\begin\{(?:enumerate|itemize)\}|\\end\{(?:enumerate|itemize)\}|\\item\b", em.group(1)))
        for k, t in enumerate(toks):
            tok = t.group(0)
            if tok.startswith("\\begin"):
                depth += 1
            elif tok.startswith("\\end"):
                depth -= 1
            elif depth == 0:
                n += 1
                end = toks[k + 1].start() if k + 1 < len(toks) else len(em.group(1))
                text, label = _take_label(em.group(1)[t.end():end])
                text = re.sub(r"^\s*\[[^\]]*\]", "", text)
                lines.append(Line(n, "state", text.strip(), label))
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
        for s, sn in zip(steps, snorm):
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
