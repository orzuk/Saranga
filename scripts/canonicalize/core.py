"""
Core canonicalization logic.  Applies rules from rules.py in the
order documented in PIPELINE_ORDER at the bottom of that file.

Correctness contract: a canonical form may be incomplete (a rewrite is
skipped wherever it cannot be made safe), but it never changes what a
formula means. scripts/canonicalize/verify_meaning.py checks this
numerically on the corpus and on fuzzed formulas.
"""
from __future__ import annotations

import re
import json
from copy import deepcopy
from typing import Iterable

from . import rules as R


# ---------------------------------------------------------------------------
# Low-level TeX reading
# ---------------------------------------------------------------------------

# One control sequence: a backslash and a letter run, or a backslash and one
# other character (\\ , \{ , \, ...).
_CMD_RE = re.compile(r"\\(?:[A-Za-z]+|.)", re.S)
# The text so far ends with a command NAME (so a following letter would
# extend it): an odd backslash run, then letters.
_ENDS_WITH_CMD = re.compile(r"(?:^|[^\\])(?:\\\\)*\\[A-Za-z]+\Z")


def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _find_matching_brace(text: str, start: int) -> int:
    """Given index of '{', find index of matching '}'. Returns -1 if not found."""
    assert text[start] == "{"
    depth = 1
    i = start + 1
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _read_arg(text: str, i: int) -> int:
    """End index of the TeX argument starting at text[i:] (after spaces): a
    balanced {..} group, one control sequence, or one character. -1 if none."""
    j = _skip_ws(text, i)
    if j >= len(text) or text[j] in "}":
        return -1
    if text[j] == "{":
        e = _find_matching_brace(text, j)
        return -1 if e < 0 else e + 1
    if text[j] == "\\":
        m = _CMD_RE.match(text, j)
        return m.end() if m else -1
    return j + 1


def _arg_body(text: str, i: int, e: int) -> str:
    """The argument text[i:e] without its outer braces."""
    a = text[_skip_ws(text, i):e]
    return a[1:-1] if a.startswith("{") else a


def _read_opt(text: str, i: int) -> int:
    """End index of an optional [..] argument at text[i:] (after spaces), or i."""
    j = _skip_ws(text, i)
    if j >= len(text) or text[j] != "[":
        return i
    depth, k = 0, j + 1
    while k < len(text):
        c = text[k]
        if c == "\\":
            k += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "]" and depth <= 0:
            return k + 1
        k += 1
    return i


def _group_end(text: str, i: int) -> int:
    """Index of the '}' closing the group that text[i] is in (len(text) at top level)."""
    depth = 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return len(text)


# ---------------------------------------------------------------------------
# Math tokens, and the spans inside math that are not math
# ---------------------------------------------------------------------------
# Renaming, variable extraction and brace stripping all read math through
# `_math_tokens`, so they agree on what a symbol is. Kinds:
#   keep    not math, never touched: \text{..} (apart from $..$ inside it),
#           \mathrm{..}, \operatorname{..}, \mathbb{..}, \label{..},
#           \begin{array}{cc}, \\[2pt], \kern3pt, {\rm ...}
#   font    a font-styled symbol, \mathcal{F}; key \mathcal{F}
#   cmd     a control word, \alpha
#   letter  one Latin letter: in math, `ux` is u times x
#   other   anything else

_TEXT_CMDS = frozenset(r"""\text \textrm \textit \textbf \textsf \texttt \textnormal \textup
    \textmd \textsl \textsc \emph \mbox \hbox \fbox \intertext \shortintertext""".split())
# Their (first) argument is a name, a label, a colour or a dimension, not math.
_FIXED_ARG_CMDS = frozenset(r"""\mathbb \mathbbm \mathds \Bbb \mathrm \operatorname \label \ref
    \eqref \tag \hspace \vspace \mspace \color \textcolor \colorbox \cite \url \href
    \hyperref \raisebox \scalebox""".split())
# Old-style font and style switches: they act to the end of the group.
_SWITCH_CMDS = frozenset(r"""\rm \bf \it \sf \tt \cal \mit \sl \sc \em""".split())
_SYMBOL_FONT_CMDS = frozenset(r"""\mathcal \mathfrak \mathscr \mathbf \boldsymbol \bm \mathsf
    \mathit \pmb \frak \bold""".split())
_DIM_CMDS = frozenset(r"\kern \mkern \hskip \mskip \vskip \hglue \mspace".split())
_DIM_RE = re.compile(r"\s*[-+]?\s*(?:\d+\.?\d*|\.\d+)\s*(?:pt|mu|em|ex|cm|mm|in|bp|pc|dd|cc|sp)"
                     r"(?:\s*(?:plus|minus)\s*[-+]?\s*(?:\d+\.?\d*|\.\d+)\s*(?:pt|mu|em|ex|fil+))*")
# Environments whose \begin carries arguments that are not math.
_ENV_EXTRA_ARGS = {"array": 1, "subarray": 1, "tabular": 1, "tabular*": 2, "tabularx": 2,
                   "alignat": 1, "alignat*": 1, "alignedat": 1, "xalignat": 1, "xalignat*": 1,
                   "xxalignat": 1, "darray": 1, "smallmatrix": 0, "matrix*": 0, "pmatrix*": 0,
                   "bmatrix*": 0, "vmatrix*": 0, "Bmatrix*": 0, "Vmatrix*": 0}


def _env_end(text: str, i: int, name: str) -> int:
    """`text[i:]` follows \\begin or \\end: the end of the environment name and,
    for \\begin{array}{..}, \\begin{alignat}{N} and the like, of its arguments."""
    e = _read_arg(text, i)
    if e < 0:
        return i
    env = _arg_body(text, i, e).strip()
    if name == r"\begin" and env in _ENV_EXTRA_ARGS:
        e = _read_opt(text, e)
        for _ in range(_ENV_EXTRA_ARGS[env]):
            e2 = _read_arg(text, e)
            if e2 < 0 or text[_skip_ws(text, e)] != "{":
                break
            e = e2
    return e


def _linebreak_end(text: str, j: int) -> int:
    """`text[:j]` ends with \\\\: the end of its `*` and [2pt] argument."""
    if j < len(text) and text[j] == "*":
        j += 1
    return _read_opt(text, j)


def _font_key(name: str, body: str) -> str | None:
    """Canonical key of a font-styled symbol, or None when the argument is
    not a single symbol (\\mathbf{x+y} is read letter by letter)."""
    b = body.strip()
    if re.fullmatch(r"[A-Za-z]|\\[A-Za-z]+", b):
        return name + "{" + b + "}"
    return None


def _math_tokens(text: str) -> list:
    """[(start, end, kind, key)] covering `text` (a math string)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c != "\\":
            kind = "letter" if ("a" <= c <= "z" or "A" <= c <= "Z") else "other"
            out.append((i, i + 1, kind, c))
            i += 1
            continue
        m = _CMD_RE.match(text, i)
        if not m:                                   # a lone backslash at the end
            out.append((i, n, "other", c))
            break
        name, j = m.group(0), m.end()
        if name == "\\\\":
            e = _linebreak_end(text, j)
            out.append((i, e, "keep", name))
            i = e
            continue
        if not name[1:].isalpha():
            out.append((i, j, "other", name))
            i = j
            continue
        if name in _TEXT_CMDS:
            e = _read_arg(text, j)
            if e < 0:
                out.append((i, j, "keep", name))
                i = j
                continue
            out += _text_tokens(text, i, e)
            i = e
            continue
        if name in _FIXED_ARG_CMDS:
            k = j + 1 if j < n and text[j] == "*" else j   # \operatorname*, \tag*
            k = _read_opt(text, k) if name in (r"\hyperref", r"\raisebox") else k
            e = _read_arg(text, k)
            e = k if e < 0 else e
            out.append((i, e, "keep", name))
            i = e
            continue
        if name in (r"\begin", r"\end"):
            e = _env_end(text, j, name)
            out.append((i, e, "keep", name))
            i = e
            continue
        if name in _DIM_CMDS:
            d = _DIM_RE.match(text, j)
            e = d.end() if d else j
            if name == r"\mspace":
                e2 = _read_arg(text, j)
                e = e2 if e2 > 0 else e
            out.append((i, e, "keep", name))
            i = e
            continue
        if name in _SWITCH_CMDS:
            e = _group_end(text, j)
            out.append((i, e, "keep", name))
            i = e
            continue
        if name in _SYMBOL_FONT_CMDS:
            e = _read_arg(text, j)
            if e > 0:
                key = _font_key(name, _arg_body(text, j, e))
                if key is not None:
                    out.append((i, e, "font", key))
                    i = e
                    continue
                if re.fullmatch(r"\s*\{?\s*\d+\s*\}?\s*", text[j:e]):   # \mathbf{1}: a constant
                    out.append((i, e, "keep", name))
                    i = e
                    continue
            out.append((i, j, "other", name))        # complex argument: read it as math
            i = j
            continue
        out.append((i, j, "cmd", name))
        i = j
    return out


def _text_tokens(text: str, s: int, e: int) -> list:
    """Tokens of a \\text{..} span: the text is kept, but $..$ inside it is math."""
    out, pos = [], s
    for m in re.finditer(r"(?<!\\)\$((?:\\.|[^$\\])+)\$", text[s:e]):
        a, b = s + m.start(1), s + m.end(1)
        out.append((pos, a, "keep", "text"))
        out += [(a + x, a + y, k, key) for x, y, k, key in _math_tokens(text[a:b])]
        pos = b
    out.append((pos, e, "keep", "text"))
    return [t for t in out if t[1] > t[0]]


def _mask_kept(text: str):
    """Replace every non-math span by one placeholder character. Returns the
    masked text and a function that puts the spans back."""
    spans = [(s, e) for s, e, kind, _ in _math_tokens(text) if kind == "keep"]
    if not spans:
        return text, lambda t: t
    parts, pos, saved = [], 0, []
    for s, e in spans:
        parts.append(text[pos:s])
        parts.append(chr(0xF0000 + len(saved)))
        saved.append(text[s:e])
        pos = e
    parts.append(text[pos:])

    def restore(t: str) -> str:
        return re.sub("[\U000F0000-\U000FFFFD]", lambda m: saved[ord(m.group(0)) - 0xF0000], t)

    return "".join(parts), restore


# ---------------------------------------------------------------------------
# Rule application
# ---------------------------------------------------------------------------
# LaTeX commands (\R, \to, \cup) are matched WITH WORD BOUNDARIES so that \R
# does not match inside \Rightarrow, and \to not inside \top. A key never
# matches the second backslash of an escaped pair: in `\\ ` (a line break and a
# space) there is no `\ `. Plain str.replace is unsafe on both counts.

_LITERAL_PATTERNS: dict = {}


def _literal_pattern(k: str):
    p = _LITERAL_PATTERNS.get(k)
    if p is None:
        tail = r"(?![A-Za-z])" if k.startswith("\\") and k[-1].isalpha() else ""
        # `\\.` consumes every escaped pair that is not the key, left to right,
        # so a key can only start at an unescaped position.
        p = re.compile(r"(?P<k>" + re.escape(k) + ")" + tail + r"|\\.", re.S)
        _LITERAL_PATTERNS[k] = p
    return p


def _apply_literal_rules(text: str, mapping: dict) -> str:
    """Apply replacement rules with boundary-aware matching.

    - Keys that are control words (\\R, \\le) match only when NOT followed by
      another letter, so \\R does not match inside \\Rightarrow.
    - No key matches at an escaped position (`\\\\ ` holds no `\\ `).
    - A replacement never fuses with its neighbours into a new command:
      `\\alpha\\,x` becomes `\\alpha x`, not `\\alphax`.
    Longer keys are tried first so that, e.g., \\Rightarrow runs before \\R.
    """
    for k in sorted((k for k in mapping if mapping[k] != k), key=len, reverse=True):
        if k not in text:
            continue
        v = mapping[k]
        out, pos = [], 0
        for m in _literal_pattern(k).finditer(text):
            if m.group("k") is None:
                continue
            out.append(text[pos:m.start()])
            tail = "".join(out[-4:])[-64:]
            nxt = text[m.end():m.end() + 1]
            rep = v
            if _ENDS_WITH_CMD.search(tail) and (rep[:1].isalpha() or (not rep and nxt.isalpha())):
                rep = " " + rep
            if re.search(r"\\[A-Za-z]+\Z", rep) and nxt.isalpha():
                rep = rep + " "
            out.append(rep)
            pos = m.end()
        out.append(text[pos:])
        text = "".join(out)
    return text


def _rules(table: dict, allowed: dict | None) -> dict:
    """`table` without the conditional merges that are not allowed here
    (all of them are allowed when `allowed` is None)."""
    if allowed is None:
        return table
    return {k: v for k, v in table.items() if k not in R.CONDITIONAL_MERGES or k in allowed}


# ---------------------------------------------------------------------------
# Fraction rewrites (balanced-brace aware)
# ---------------------------------------------------------------------------

# After a fraction, these leave `a/b` unambiguous: a relation, a binary
# operator, punctuation, a closing bracket, or the end. Not `!` or `'`
# (\frac{a}{b}! is (a/b)!) and not `|` (it may open |x|).
_FRAC_SAFE_NEXT_CHARS = set("+-=<>,;:)]}&")
_FRAC_SAFE_NEXT_COMMANDS = {
    r"\leq", r"\geq", r"\le", r"\ge", r"\neq", r"\ne", r"\ll", r"\gg", r"\approx",
    r"\sim", r"\simeq", r"\equiv", r"\cong", r"\propto", r"\to", r"\in", r"\cdot",
    r"\times", r"\pm", r"\mp", r"\cup", r"\cap", r"\setminus", r"\quad", r"\qquad",
    r"\implies", r"\iff", r"\right", r"\}", r"\rangle", r"\\"}
# Before a fraction, these leave it unambiguous too (relations and operators).
_FRAC_SAFE_PREV_COMMANDS = _FRAC_SAFE_NEXT_COMMANDS - {r"\right"}


def _frac_needs_group(before: str, after: str) -> bool:
    """Would a bare `a/b` here be read differently from the fraction?

    `\\frac{a}{b}^2` must not become `a/b^2`, `x/\\frac{a}{b}` must not become
    `x/a/b`, `\\frac{1}{2}x` must not become `1/2x`, `10\\frac{3}{2}` must not
    become `103/2`, and `\\sqrt\\frac{a}{b}` must not become `\\sqrt{a}/{b}`.
    """
    b = before.rstrip()
    prev = b[-1:]
    if prev in ("/", "^", "_", "]", ".") or prev.isdigit():
        return True
    if _ENDS_WITH_CMD.search(b):
        cmd = re.search(r"\\[A-Za-z]+\Z", b).group(0)
        if cmd not in _FRAC_SAFE_PREV_COMMANDS:
            return True
    nxt = after.lstrip()
    if not nxt:
        return False
    if nxt[0] == "." and not nxt[1:2].isdigit():
        return False
    if nxt[0] in _FRAC_SAFE_NEXT_CHARS:
        return False
    if nxt[0] == "\\":
        m = re.match(r"\\(?:[A-Za-z]+|.)", nxt)
        return not (m and m.group(0) in _FRAC_SAFE_NEXT_COMMANDS)
    return True


def _rewrite_frac(text: str) -> str:
    """Rewrite \\frac{a}{b} -> {a}/{b}, handling nested braces and the
    brace-less form \\frac12.

    The result is wrapped in braces, {{a}/{b}}, wherever the neighbouring
    tokens would otherwise regroup it (see `_frac_needs_group`)."""
    out = []
    i = 0
    while i < len(text):
        if text[i] != "\\":
            out.append(text[i])
            i += 1
            continue
        m = _CMD_RE.match(text, i)
        if not m:
            out.append(text[i:])
            break
        if m.group(0) == r"\frac":
            j = _read_opt(text, m.end())          # \cfrac[l]{..}{..}: alignment only
            e1 = _read_arg(text, j)
            e2 = _read_arg(text, e1) if e1 > 0 else -1
            if e2 > 0:
                num = _rewrite_frac(_arg_body(text, j, e1))
                den = _rewrite_frac(_arg_body(text, e1, e2))
                frac = "{" + num + "}/{" + den + "}"
                if _frac_needs_group("".join(out)[-200:], text[e2:]):
                    frac = "{" + frac + "}"
                out.append(frac)
                i = e2
                continue
        out.append(m.group(0))
        i = m.end()
    return "".join(out)


def _rewrite_binom(text: str) -> str:
    """Rewrite \\binom{n}{k} -> C(n,k), balanced-brace aware."""
    out = []
    i = 0
    while i < len(text):
        if text.startswith(r"\binom", i):
            j = i + len(r"\binom")
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] == "{":
                n_end = _find_matching_brace(text, j)
                if n_end >= 0:
                    k = n_end + 1
                    while k < len(text) and text[k].isspace():
                        k += 1
                    if k < len(text) and text[k] == "{":
                        k_end = _find_matching_brace(text, k)
                        if k_end >= 0:
                            n_str = _rewrite_binom(text[j + 1 : n_end])
                            k_str = _rewrite_binom(text[k + 1 : k_end])
                            out.append("C(" + n_str + "," + k_str + ")")
                            i = k_end + 1
                            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _rewrite_exp(text: str) -> str:
    """Rewrite \\exp(x) -> e^{x}, with balanced parentheses, so \\exp(f(x))
    becomes e^{f(x)}. \\exp(x)^2 becomes {e^{x}}^2, keeping the grouping, and
    so does \\sqrt\\exp(x) (\\sqrt takes one token). Only the \\exp(...) form;
    \\exp{x} and \\exp x are left as written."""
    out, i = [], 0
    pat = re.compile(r"\\exp(?![A-Za-z])\s*\(")
    while i < len(text):
        if text[i] == "\\":
            m = pat.match(text, i)
            if m:
                depth, j = 1, m.end()
                while j < len(text) and depth:
                    depth += {"(": 1, ")": -1}.get(text[j], 0)
                    j += 1
                if depth == 0:
                    term = "e^{" + _rewrite_exp(text[m.end():j - 1]) + "}"
                    before = "".join(out)[-200:]
                    b = before.rstrip()
                    group = text[j:].lstrip()[:1] in ("^", "_") or b[-1:] in ("^", "_", "]")
                    if not group and _ENDS_WITH_CMD.search(b):
                        group = re.search(r"\\[A-Za-z]+\Z", b).group(0) not in _FRAC_SAFE_PREV_COMMANDS
                    if group:
                        term = "{" + term + "}"
                    elif _ENDS_WITH_CMD.search(before):
                        term = " " + term               # \cdot\exp(x) -> \cdot e^{x}
                    out.append(term)
                    i = j
                    continue
            c = _CMD_RE.match(text, i)
            tok = c.group(0) if c else text[i]
            out.append(tok)
            i += len(tok)
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _rewrite_ln_to_log(text: str) -> str:
    """\\ln -> \\log (canonical form for natural log). \\log_{10} stays."""
    return re.sub(R.LN_TO_LOG_PATTERN, R.LN_TO_LOG_REPLACEMENT, text)


def _rewrite_xarrows(text: str) -> str:
    """\\xrightarrow[b]{a} -> \\underset{b}{\\overset{a}{\\to}}: the arrow's labels
    are kept (an unlabelled one is just \\to). Same for \\xleftarrow."""
    out, i = [], 0
    pat = re.compile(r"\\x(rightarrow|leftarrow)(?![A-Za-z])")
    while True:
        m = pat.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        j, below = m.end(), ""
        k = _read_opt(text, j)
        if k > j:
            below = text[_skip_ws(text, j) + 1:k - 1]
            j = k
        e = _read_arg(text, j)
        if e < 0 or text[_skip_ws(text, j)] != "{":
            out.append(m.group(0))
            i = m.end()
            continue
        above = _rewrite_xarrows(_arg_body(text, j, e))
        res = r"\to" if m.group(1) == "rightarrow" else r"\leftarrow"
        if above.strip():
            res = r"\overset{" + above + "}{" + res + "}"
        if below.strip():
            res = r"\underset{" + _rewrite_xarrows(below) + "}{" + res + "}"
        out.append(res)
        i = e
    return "".join(out)


def _strip_overset_underset(text: str) -> str:
    """\\stackrel{X}{Y} -> \\overset{X}{Y}, which prints the same, and
    \\xrightarrow{X} -> \\overset{X}{\\to}.

    The decoration X is kept: X \\overset{d}{=} Y (equality in distribution)
    and \\overset{a.s.}{\\to} (almost sure convergence) are not = and \\to.
    """
    text = re.sub(r"(?<!\\)\\stackrel(?![A-Za-z])", lambda m: r"\overset", text)
    return _rewrite_xarrows(text)


# ---------------------------------------------------------------------------
# Inequality direction flip (isolated comparisons only)
# ---------------------------------------------------------------------------

_INEQ_OPS_TO_FLIP = ["\\geq", "\\leq", "\\gneq", "\\lneq", "\\gg", "\\ll",
                    "\\ggg", "\\lll", "\\succ", "\\prec", "\\succeq",
                    "\\preceq", ">", "<"]

# Operands we consider "simple enough to swap".
_SIMPLE_OPERAND = re.compile(
    r"""
    (?: \\[A-Za-z]+ (?:\{[^{}]*\})? )  # command like \alpha or \mathbb{R}
  | (?: [A-Za-z][A-Za-z0-9]* )         # variable like x, alpha, x0
  | (?: -? \d+ (?:\.\d+)? )            # number like 3 or -2.5
  | (?: \{ [^{}]* \} )                 # braced atom {x_1}
    """, re.VERBOSE)


_OPENERS = {"{", "(", "[", r"\{", r"\langle", r"\lceil", r"\lfloor", r"\lvert", r"\lVert"}
_CLOSERS = {"}", ")", "]", r"\}", r"\rangle", r"\rceil", r"\rfloor", r"\rvert", r"\rVert"}
# Where one formula ends and the next begins, inside one math segment.
_CLAUSE_SEPARATORS = {",", ";", "&", ":", r"\quad", r"\qquad", r"\mid", r"\colon",
                      r"\Rightarrow", r"\Leftarrow", r"\Leftrightarrow", r"\Longrightarrow",
                      r"\Longleftarrow", r"\Longleftrightarrow", r"\implies", r"\impliedby",
                      r"\iff", r"\land", r"\lor", r"\wedge", r"\vee", r"\forall", r"\exists",
                      r"\nexists", r"\text", r"\mbox", r"\textrm"}
_RELATIONS = {"<", ">", "=", r"\leq", r"\geq", r"\neq", r"\lneq", r"\gneq", r"\ll",
              r"\gg", r"\lll", r"\ggg", r"\prec", r"\succ", r"\preceq", r"\succeq",
              r"\lesssim", r"\gtrsim", r"\leqslant", r"\geqslant", r"\approx",
              r"\sim", r"\simeq", r"\cong", r"\equiv", r"\propto", r"\asymp",
              r"\in", r"\notin", r"\ni", r"\subset", r"\subseteq", r"\subsetneq",
              r"\supset", r"\supseteq", r"\supsetneq", r"\to", r"\mapsto",
              r"\perp", r"\parallel", r"\models", r"\vdash", r"\coloneqq",
              r"\triangleq", r"\doteq", r"\le", r"\ge", r"\ne"}
# Further relation symbols: a clause holding one of them besides a flippable
# relation is a chain and must not be flipped.
_MORE_RELATIONS = set(r"""\leqq \geqq \eqslantless \eqslantgtr \lessgtr \gtrless \lesseqgtr
    \gtreqless \lessapprox \gtrapprox \lnsim \gnsim \lneqq \gneqq \nleq \ngeq \nless \ngtr
    \nleqslant \ngeqslant \nleqq \ngeqq \preccurlyeq \succcurlyeq \precsim \succsim
    \precapprox \succapprox \nprec \nsucc \npreceq \nsucceq \sqsubset \sqsupset \sqsubseteq
    \sqsupseteq \Subset \Supset \subseteqq \supseteqq \subsetneqq \supsetneqq \nsubseteq
    \nsupseteq \varsubsetneq \varsupsetneq \nsubset \nsupset \owns \approxeq \thicksim
    \thickapprox \backsim \backsimeq \eqsim \nsim \ncong \bumpeq \Bumpeq \doteqdot \eqcirc
    \circeq \eqqcolon \coloneq \Coloneqq \nequiv \varpropto \dashv \vDash \Vdash \nvdash
    \nvDash \nmid \nparallel \divides \shortmid \smile \frown \bowtie \Join \lhd \rhd \unlhd
    \unrhd \lessdot \gtrdot \vartriangleleft \vartriangleright \trianglelefteq
    \trianglerighteq \ntriangleleft \ntriangleright \llless \gggtr \lt \gt \gets \leadsto
    \multimap \between \pitchfork \propto \asymp \sqsubsetneq \preceqq \succeqq \lneq
    \gneq \ggcurly \llcurly \eqdef \overset \underset \stackrel""".split())
_FLIPPED = {">": "<", r"\geq": r"\leq", r"\gneq": r"\lneq", r"\gg": r"\ll",
            r"\ggg": r"\lll", r"\succ": r"\prec", r"\succeq": r"\preceq",
            r"\gtrsim": r"\lesssim", r"\geqslant": r"\leqslant"}
_BINARY_OPS = {"+", "-", "*", "/", r"\cdot", r"\times", r"\pm", r"\mp", r"\cup", r"\cap",
               r"\setminus", r"\circ", r"\oplus", r"\otimes", r"\ominus", r"\odot",
               r"\bullet", r"\ast", r"\star", r"\div", r"\sqcup", r"\sqcap", r"\uplus"}


def _is_relation(tok: str) -> bool:
    return (tok in _RELATIONS or tok in _MORE_RELATIONS
            or bool(re.fullmatch(r"\\[A-Za-z]*(?:arrow|arrows|harpoon[a-z]*|mapsto)", tok)))


def _flip_tokens(text: str) -> list:
    """[(start, end, kind, tok)] for the flip, kind one of open, close, sep,
    row, rel, over, op, other. Whitespace is skipped."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c != "\\":
            kind = ("open" if c in "{([" else "close" if c in "})]" else
                    "sep" if c in ",;:&" else "rel" if c in "<>=" else
                    "op" if c in "+-*/" else "other")
            out.append((i, i + 1, kind, c))
            i += 1
            continue
        m = _CMD_RE.match(text, i)
        if not m:
            out.append((i, n, "other", c))
            break
        tok, j = m.group(0), m.end()
        if tok in ("\\\\", r"\cr", r"\crcr", r"\newline"):
            e = _linebreak_end(text, j) if tok == "\\\\" else j
            out.append((i, e, "row", tok))
            i = e
            continue
        if tok in _TEXT_CMDS or tok in _FIXED_ARG_CMDS and tok not in (
                r"\mathbb", r"\mathbbm", r"\mathds", r"\mathrm", r"\operatorname"):
            k = j + 1 if j < n and text[j] == "*" else j
            e = _read_arg(text, k)
            e = k if e < 0 else e
            out.append((i, e, "sep", tok))
            i = e
            continue
        if tok in (r"\begin", r"\end"):
            e = _env_end(text, j, tok)
            out.append((i, e, "sep", tok))
            i = e
            continue
        if tok in (r"\overset", r"\underset", r"\stackrel", r"\mathrel", r"\not"):
            e = _read_arg(text, j)
            if e > 0 and tok in (r"\overset", r"\underset", r"\stackrel"):
                e1, e = e, _read_arg(text, e)
                inner = text[e1:e] if e > 0 else ""
            else:
                inner = text[j:e] if e > 0 else ""
            if e < 0:
                out.append((i, j, "other", tok))
                i = j
                continue
            is_rel = tok in (r"\mathrel", r"\not") or any(
                k in ("rel", "sep") or _is_relation(t) for _, _, k, t in _flip_tokens(inner))
            out.append((i, e, "rel" if is_rel else "other", tok))
            i = e
            continue
        if tok in (r"\over", r"\atop", r"\choose", r"\above", r"\brack", r"\brace"):
            kind = "over"
        elif tok in _OPENERS:
            kind = "open"
        elif tok in _CLOSERS:
            kind = "close"
        elif tok in _CLAUSE_SEPARATORS:
            kind = "sep"
        elif _is_relation(tok):
            kind = "rel"
        elif tok in _BINARY_OPS:
            kind = "op"
        else:
            kind = "other"
        out.append((i, j, kind, tok))
        i = j
    return out


def _rows_continue(toks: list) -> bool:
    """Does any row of a multi-row block continue the previous one (a row
    that starts, or a row before one that ends, with a relation or an operator)?
    `a &\\leq b \\\\ &\\leq c` is one chain, not two formulas."""
    rows, cur, depth = [], [], 0
    for t in toks:
        if t[2] == "open":
            depth += 1
        elif t[2] == "close":
            depth = max(depth - 1, 0)
        if t[2] == "row" and depth == 0:
            rows.append(cur)
            cur = []
        else:
            cur.append(t)
    rows.append(cur)
    if len(rows) < 2:
        return False
    for k, row in enumerate(rows):
        sig = [t for t in row if t[2] != "sep"]
        if not sig:
            continue
        if k > 0 and sig[0][2] in ("rel", "op"):
            return True
        if k < len(rows) - 1 and sig[-1][2] in ("rel", "op"):
            return True
    return False


def _flip_inequalities(text: str) -> str:
    """Rewrite `lhs > rhs` as `rhs < lhs`, and likewise \\geq -> \\leq, \\gg -> \\ll, ...

    The WHOLE sides are swapped, so the meaning is kept: `x^2 \\geq 0` becomes
    `0 \\leq x^2`, never `x^0 \\leq 2`. A formula is flipped only when it has
    exactly one relation outside all brackets; chains (`a > b > c`) and mixed
    relations (`a \\geq b = c`, `a \\overset{(a)}{\\geq} b \\geq c`) are left as
    written. One math segment may hold several formulas (`x > 0, y > 1`, an
    align block); each is handled on its own, split at top-level commas, `&`,
    `\\\\` (with its [2pt]), `\\quad`, `\\text{...}` (with its argument),
    \\begin/\\end, logical connectives and the like. A block whose rows
    continue each other (`a &\\leq b \\\\ &\\leq c`) is not flipped at all, nor is
    a formula with a top-level \\over, or with unbalanced brackets.
    """
    toks = _flip_tokens(text)
    if _rows_continue(toks):
        return text
    clauses: list = []        # (start, end, top-level relations, unsafe)
    depth, start, rels, bad = 0, 0, [], False
    for ts, te, kind, tok in toks:
        if kind == "open":
            depth += 1
        elif kind == "close":
            if depth == 0:
                bad = True
            depth = max(depth - 1, 0)
        elif depth == 0 and kind in ("sep", "row"):
            clauses.append((start, ts, rels, bad))
            start, rels, bad = te, [], False
        elif depth == 0 and kind == "rel":
            rels.append((ts, te, tok))
        elif depth == 0 and kind == "over":
            bad = True
    clauses.append((start, len(text), rels, bad or depth > 0))

    out, pos = [], 0
    for cs, ce, rels, bad in clauses:
        if bad or len(rels) != 1 or rels[0][2] not in _FLIPPED:
            continue
        rs, re_, op = rels[0]
        lhs, rhs = text[cs:rs].strip(), text[re_:ce].strip()
        punct = re.search(r"(?:\s*(?<!\\)\.)+\Z", rhs)          # sentence punctuation
        if punct:
            rhs, punct = rhs[:punct.start()].rstrip(), punct.group(0)
        if not lhs or not rhs:
            continue
        lt, rt = _flip_tokens(lhs), _flip_tokens(rhs)
        if (lt and lt[0][2] == "op" and lt[0][3] not in ("+", "-")) or (rt and rt[-1][2] == "op"):
            continue
        seg = text[cs:ce]
        lead = seg[:len(seg) - len(seg.lstrip())]
        trail = seg[len(seg.rstrip()):]
        out.append(text[pos:cs])
        out.append(f"{lead}{rhs} {_FLIPPED[op]} {lhs}{punct or ''}{trail}")
        pos = ce
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Redundant brace removal
# ---------------------------------------------------------------------------

def _strip_redundant_braces(text: str) -> str:
    """Repeatedly apply brace-stripping patterns until fixpoint.

    Skips braces that are arguments to LaTeX commands (\\mathbb{R},
    \\mathbf{X}) via negative lookbehind in the rule pattern, and never
    touches the non-math spans (\\begin{array}{l}, \\text{..}, labels).
    """
    masked, restore = _mask_kept(text)
    prev = None
    while prev != masked:
        prev = masked
        for pat, repl in R.REDUNDANT_BRACE_PATTERNS:
            masked = re.sub(pat, repl, masked)
    return restore(masked)


def _normalize_bracket_inner_space(text: str) -> str:
    """After \\left/\\right stripping, remove spaces right after ( [ { and
    right before ) ] }."""
    for pat, repl in R.BRACKET_INNER_SPACE_PATTERNS:
        text = re.sub(pat, repl, text)
    return text


# ---------------------------------------------------------------------------
# Prose-math segmentation (minimal version — does not use pylatexenc yet)
# ---------------------------------------------------------------------------

_DISPLAY_ENVS = r"equation|displaymath|align|eqnarray|gather|multline|flalign|alignat"
# Multi-line environments whose top-level & are alignment points only.
_ALIGN_ENVS = {"align", "eqnarray", "flalign", "alignat"}
_MATH_DELIM_PATTERN = re.compile(
    r"""
    (?P<env>      \\begin\s*\{(?P<envname>""" + _DISPLAY_ENVS + r""")\*?\} .*? \\end\s*\{(?P=envname)\*?\} )
  | (?P<display1> (?<!\\)\$\$ .*? \$\$ )
  | (?P<display2> (?<!\\)\\\[ .*? \\\] )
  | (?P<inline>   (?<!\\)\$ (?:\\.|[^\$\\])+ \$ )
    """, re.VERBOSE | re.DOTALL)


def _segment(text: str):
    """Yield (kind, text) pairs where kind is 'math' or 'prose'.

    Temporary simple implementation: uses regex for $..$, $$..$$, \\[..\\].
    A future version should use pylatexenc.latexwalker for robustness
    against nested environments and \\begin{equation}..\\end{equation}.
    """
    pos = 0
    for m in _MATH_DELIM_PATTERN.finditer(text):
        start = m.start()
        if start > pos:
            yield "prose", text[pos:start]
        yield "math", m.group(0)
        pos = m.end()
    if pos < len(text):
        yield "prose", text[pos:]


def _drop_alignment_marks(inner: str) -> str:
    """Drop the top-level & of an align-type block (layout only). The & of a
    nested matrix, array or cases are column separators and stay. Where the &
    sat between \\\\ and [, it becomes {} so the [..] is not read as the
    line break's optional argument."""
    out, i, nest, depth = [], 0, 0, 0
    while i < len(inner):
        c = inner[i]
        if c == "\\":
            m = _CMD_RE.match(inner, i)
            tok = m.group(0) if m else c
            if tok == r"\begin":
                nest += 1
            elif tok == r"\end":
                nest = max(nest - 1, 0)
            out.append(tok)
            i += len(tok)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(depth - 1, 0)
        elif c == "&" and nest == 0 and depth == 0:
            before = "".join(out).rstrip()
            if re.search(r"(?:^|[^\\])(?:\\\\)*\\\\\*?\Z", before) and inner[i + 1:].lstrip()[:1] == "[":
                out.append("{}")
            else:
                out.append(" ")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _split_delimiters(math_text: str):
    """Phase 0: (inner, open, close). Delimiters that mean the same thing get
    one canonical form: every single-line display ($$..$$, \\[..\\], equation,
    equation*, displaymath) becomes \\[..\\], and every multi-line display
    (align, eqnarray, flalign, alignat, starred or not) becomes align."""
    env = re.match(r"\\begin\s*\{(" + _DISPLAY_ENVS + r")\*?\}(.*)\\end\s*\{\1\*?\}\Z", math_text, re.S)
    if env:
        name, inner = env.group(1), env.group(2)
        if name == "alignat":                     # \begin{alignat}{3}: a column count
            inner = re.sub(r"\A\s*\{[^{}]*\}", "", inner)
        if name in ("equation", "displaymath"):
            delim_open, delim_close = r"\[", r"\]"
        else:
            canon = {"eqnarray": "align", "flalign": "align", "alignat": "align"}.get(name, name)
            delim_open, delim_close = f"\\begin{{{canon}}}", f"\\end{{{canon}}}"
        inner = re.sub(r"\\(?:label|tag)\*?\{[^{}]*\}|\\(?:nonumber|notag)(?![A-Za-z])", "", inner)
        if name in _ALIGN_ENVS:
            inner = _drop_alignment_marks(inner)
        return inner, delim_open, delim_close
    if math_text.startswith("$$") and math_text.endswith("$$"):
        return math_text[2:-2], r"\[", r"\]"
    if math_text.startswith(r"\[") and math_text.endswith(r"\]"):
        return math_text[2:-2], r"\[", r"\]"
    if math_text.startswith("$") and math_text.endswith("$"):
        return math_text[1:-1], "$", "$"
    return math_text, "", ""


# ---------------------------------------------------------------------------
# Variable extraction and rename
# ---------------------------------------------------------------------------

# All identifiers that must NEVER be renamed (constants, function names,
# number sets, standard names).
_NEVER_RENAME = (
    R.CONSTANTS
    | R.STANDARD_FUNCTIONS
    | R.NUMBER_SETS_CANONICAL
)


# Within a math string, the candidate variable tokens are
#   - single Latin letters except LETTER_CONSTANTS (e, i), one by one: a
#     letter run `ux` outside \text/\mathrm/\operatorname is the product u x;
#   - Greek commands (\alpha, \beta) that aren't constants;
#   - font-styled symbols (\mathcal{F}, \mathbf{x}): a calligraphic or bold
#     letter is a variable, but a different one from the plain letter.
# Inside \mathbb, \mathrm, \text, \operatorname nothing is a variable:
# \mathbb{R} is the reals, not a variable R.
_FONT_FIXED = r"mathbb|mathbbm|mathds|mathrm|operatorname\*?|text|textrm|textit|textbf|mbox"
_FONT_SYMBOL = r"mathcal|mathfrak|mathscr|mathbf|boldsymbol|bm|mathsf|mathit"


def _scan_variables(math_text: str):
    """(variables in first-occurrence order, norm letters used with a script)."""
    order, seen, scripted = [], set(), set()
    for s, e, kind, key in _math_tokens(math_text):
        if kind == "letter":
            if key in R.LETTER_CONSTANTS:
                continue
            if key in R.NORM_LETTERS and math_text[_skip_ws(math_text, e):][:1] in ("_", "^"):
                scripted.add(key)
        elif kind == "cmd":
            if key not in R.GREEK_VARIABLE_COMMANDS or key in _NEVER_RENAME:
                continue
        elif kind != "font":
            continue
        if key not in seen:
            seen.add(key)
            order.append(key)
    return order, scripted


def _extract_variables(math_text: str) -> list[str]:
    """Return a list of candidate variable names in first-occurrence order.

    Recognises as variables:
      - single Latin letters except LETTER_CONSTANTS (e, i, ...)
      - Greek command names in GREEK_VARIABLE_COMMANDS
      - font-styled single symbols (\\mathcal{F}, \\mathbf{x})

    Treats as non-variables (never renamed):
      - Commands in CONSTANTS, STANDARD_FUNCTIONS, NUMBER_SETS_CANONICAL
      - Any other LaTeX command (relations, operators, arrows, logic, ...)
      - Letters listed in LETTER_CONSTANTS
      - l and L when the text uses them with a script anywhere (l_1, L^2:
        norm names); they are then kept everywhere, never renamed in one
        place and kept in another.

    v1 does NOT distinguish function names from generic variables; f in
    f(x) is tagged as VAR, not FN.
    """
    order, scripted = _scan_variables(math_text)
    return [v for v in order if v not in scripted]


def _extract_math_only(text: str) -> str:
    """Extract only the math: $..$, $$..$$, \\[..\\] and display environments.
    (Environment names, labels and the like are skipped by `_math_tokens`.)"""
    return " ".join(segment for kind, segment in _segment(text) if kind == "math")


def build_local_rename_map(text: str) -> dict:
    """Build a rename map for a single text fragment, first-occurrence order.
    Only extracts variables from math regions (not prose letters)."""
    math_only = _extract_math_only(text)
    variables = _extract_variables(math_only)
    return {
        var: f"{R.VAR_PREFIX}{i + 1}"
        for i, var in enumerate(variables)
    }


def build_paper_rename_map(paper_json: dict) -> dict:
    """Build a rename map for all nodes in a paper, first-occurrence order
    across the entire paper."""
    seen: set[str] = set()
    order: list[str] = []
    scripted: set[str] = set()

    def _add(text):
        o, s = _scan_variables(_extract_math_only(text))
        scripted.update(s)
        for var in o:
            if var not in seen:
                seen.add(var)
                order.append(var)

    # Iterate nodes in a stable order: node-id sorted
    nodes = paper_json.get("nodes", {})
    if isinstance(nodes, dict):
        node_iter = [nodes[k] for k in sorted(nodes.keys())]
    else:
        node_iter = list(nodes)

    for node in node_iter:
        for field in ("name", "statement", "raw_latex"):
            val = node.get(field, "") or ""
            if isinstance(val, list):
                val = " ".join(val)
            _add(val)
        # also process lists
        for field in ("assumptions", "conclusions"):
            items = node.get(field) or []
            if isinstance(items, list):
                for item in items:
                    _add(item or "")

    order = [v for v in order if v not in scripted]
    return {
        var: f"{R.VAR_PREFIX}{i + 1}"
        for i, var in enumerate(order)
    }


def _apply_rename_in_math(math_text: str, rename_map: dict) -> str:
    """Apply rename map inside a math segment, token by token.

    Every occurrence of a mapped symbol is renamed, letters inside letter runs
    included (`ux` is u times x); nothing inside \\text, \\mathrm,
    \\operatorname, \\begin{array}{..} and the like is touched. A renamed token
    that is a script is braced (x^y -> V1^{V2}: TeX reads V1^V2 as V1^{V}2),
    and one followed by a digit is spaced (x2 -> V1 2, not V12). Replacements
    are made in one pass, so V1, V2 are never renamed again.
    """
    if not rename_map:
        return math_text
    out, pos, last = [], 0, ""
    for s, e, kind, key in _math_tokens(math_text):
        new = rename_map.get(key) if kind in ("letter", "cmd", "font") else None
        if new is None:
            continue
        out.append(math_text[pos:s])
        before = ("".join(out[-3:]) if out else "")
        if before.rstrip().endswith(("^", "_")) and not re.search(
                r"(?:^|[^\\])(?:\\\\)*\\[\^_]\Z", before.rstrip()):
            new = "{" + new + "}"
        elif _ENDS_WITH_CMD.search(before):
            new = " " + new                      # \cdot\alpha -> \cdot V1, not \cdotV1
        if math_text[e:e + 1].isdigit():
            new = new + " "
        out.append(new)
        pos = e
    out.append(math_text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------
# The top-level pipeline
# ---------------------------------------------------------------------------

def _used_symbols(text: str) -> set:
    """Every symbol the math of `text` uses (commands, letters, characters)."""
    t = _apply_literal_rules(_extract_math_only(text), R.RULES_GREEK_UNICODE_TO_COMMAND)
    return {key for _, _, kind, key in _math_tokens(t) if kind != "keep"}


def _greek_variants_for(text: str, rename_map: dict | None = None) -> dict:
    """The conditional merges that are safe in `text` (see
    rules.CONDITIONAL_MERGES): \\varphi -> \\phi only if the text does not also
    use \\phi as a different symbol, \\ell -> l only if it does not use l,
    \\Rightarrow -> \\implies only if it does not use the long arrow. With a
    rename map, a merge whose source or target the map renames is skipped:
    the source is renamed anyway, and a merged target would take the name of
    a different symbol from elsewhere in the map's scope."""
    used = _used_symbols(text)
    allowed = {}
    for k, (v, blockers) in R.CONDITIONAL_MERGES.items():
        if used & blockers:
            continue
        if rename_map and (k in rename_map or v in rename_map):
            continue
        allowed[k] = v
    return allowed


# The math phases, in order: (name, fn(text, ctx)). ctx holds 'rename_map'
# and 'variants' (the allowed conditional merges). Each phase looks its
# function up at call time, so a monkeypatched phase is used.
# verify_meaning replays exactly this list.
MATH_PHASES = [
    ("1 spacing (RULES_SPACING)", lambda s, ctx: _apply_literal_rules(s, R.RULES_SPACING)),
    # strip \left, \right, \big*, \Big*
    ("2 brackets (RULES_BRACKETS)", lambda s, ctx: _apply_literal_rules(s, R.RULES_BRACKETS)),
    ("3 greek unicode", lambda s, ctx: _apply_literal_rules(s, R.RULES_GREEK_UNICODE_TO_COMMAND)),
    ("4 greek variants", lambda s, ctx: _apply_literal_rules(
        s, _rules(R.RULES_GREEK_VARIANTS, ctx["variants"]))),
    ("5 number sets", lambda s, ctx: _apply_literal_rules(s, R.RULES_NUMBER_SETS)),
    ("6 operators", lambda s, ctx: _apply_literal_rules(s, R.RULES_OPERATORS)),
    ("7 relations", lambda s, ctx: _apply_literal_rules(s, R.RULES_RELATIONS)),
    ("8 set relations", lambda s, ctx: _apply_literal_rules(s, R.RULES_SET_RELATIONS)),
    ("9 arrows", lambda s, ctx: _apply_literal_rules(s, _rules(R.RULES_ARROWS, ctx["variants"]))),
    ("10 logic", lambda s, ctx: _apply_literal_rules(s, R.RULES_LOGIC)),
    ("10b ell", lambda s, ctx: _apply_literal_rules(s, _rules(R.RULES_ELL, ctx["variants"]))),
    ("11 function aliases", lambda s, ctx: _apply_literal_rules(s, R.RULES_FUNCTION_ALIASES)),
    ("12 environments", lambda s, ctx: _apply_literal_rules(s, R.RULES_ENVIRONMENTS)),
    # \dfrac, \tfrac -> \frac
    ("13 frac aliases", lambda s, ctx: _apply_literal_rules(s, R.RULES_FRAC_ALIASES)),
    # \stackrel -> \overset, \xrightarrow{f} -> \overset{f}{\to}
    ("14a overset/stackrel", lambda s, ctx: _strip_overset_underset(s)),
    # (\binom -> C(n,k) and \ln -> \log are NOT applied: see rules.py)
    ("14b frac rewrite", lambda s, ctx: _rewrite_frac(s)),
    ("14b exp rewrite", lambda s, ctx: _rewrite_exp(s)),
    ("15 inequality flip", lambda s, ctx: _flip_inequalities(s)),
    ("16 redundant braces", lambda s, ctx: _strip_redundant_braces(s)),
    ("16b bracket inner space", lambda s, ctx: _normalize_bracket_inner_space(s)),
    ("17 whitespace collapse", lambda s, ctx: re.sub(
        R.WHITESPACE_COLLAPSE_PATTERN, R.WHITESPACE_COLLAPSE_REPLACEMENT, s).strip()),
    ("18 variable rename", lambda s, ctx: _apply_rename_in_math(s, ctx["rename_map"])
        if ctx["rename_map"] is not None else s),
]


def _canonicalize_math_segment(math_text: str, rename_map: dict | None,
                               variants: dict | None = None) -> str:
    """Apply all math-level rules to a single math segment (with $..$ still
    on the outside)."""
    inner, delim_open, delim_close = _split_delimiters(math_text)
    ctx = {"rename_map": rename_map, "variants": variants}
    for _, phase in MATH_PHASES:
        inner = phase(inner, ctx)
    return f"{delim_open}{inner}{delim_close}"


def _canonicalize_prose_segment(prose_text: str, use_prose_rewrites: bool,
                                rename_map: dict | None) -> str:
    """Apply prose-level rules (optional) and any inline $ math inside."""
    # Note: inline $..$ should already be segmented out at the top level,
    # so this sees only pure prose.
    if use_prose_rewrites:
        # Case-insensitive substring replace, longer keys first
        text = prose_text
        for src in sorted(R.RULES_PROSE.keys(), key=len, reverse=True):
            pat = re.compile(re.escape(src), re.IGNORECASE)
            text = pat.sub(R.RULES_PROSE[src], text)
        prose_text = text

    # Collapse whitespace
    prose_text = re.sub(r"\s+", " ", prose_text)
    return prose_text


def canonicalize_text(text: str,
                      rename_map: dict | None = None,
                      prose_rewrites: bool = False) -> str:
    """Canonicalize a mixed prose+math string.

    Args:
        text:           Input LaTeX/prose string.
        rename_map:     Optional variable rename map to apply in math
                        segments. If None, no renaming is done.
        prose_rewrites: If True, apply RULES_PROSE to prose segments.
                        Default False (prose left alone except whitespace).

    Returns:
        Canonicalized string.
    """
    if not text:
        return ""
    out_parts = []
    variants = _greek_variants_for(text, rename_map)
    for kind, segment in _segment(text):
        if kind == "math":
            out_parts.append(_canonicalize_math_segment(segment, rename_map, variants))
        else:
            out_parts.append(_canonicalize_prose_segment(segment, prose_rewrites, rename_map))
    result = "".join(out_parts)
    # Final whitespace collapse
    return re.sub(r"\s+", " ", result).strip()


# ---------------------------------------------------------------------------
# Paper-level pipeline
# ---------------------------------------------------------------------------

_FIELDS_TO_CANONICALIZE_STRING = ["name", "statement", "raw_latex"]
_FIELDS_TO_CANONICALIZE_LIST   = ["assumptions", "conclusions"]


def _canonicalize_node(node: dict, rename_map_paper: dict,
                       rename_map_local: dict | None,
                       prose_rewrites: bool,
                       suffix: str) -> dict:
    """Return a new node with _canonical_<suffix> fields added."""
    out = deepcopy(node)
    for fname in _FIELDS_TO_CANONICALIZE_STRING:
        raw = out.get(fname, "")
        if not isinstance(raw, str):
            continue
        rmap = rename_map_local if rename_map_local is not None else rename_map_paper
        out[f"{fname}_canonical_{suffix}"] = canonicalize_text(
            raw, rename_map=rmap, prose_rewrites=prose_rewrites
        )
    for fname in _FIELDS_TO_CANONICALIZE_LIST:
        items = out.get(fname) or []
        if not isinstance(items, list):
            continue
        rmap = rename_map_local if rename_map_local is not None else rename_map_paper
        out[f"{fname}_canonical_{suffix}"] = [
            canonicalize_text(it, rename_map=rmap, prose_rewrites=prose_rewrites)
            for it in items
        ]
    return out


def canonicalize_paper(paper_json: dict,
                       prose_rewrites: bool = False) -> dict:
    """Produce a new paper JSON with two layers of canonicalization
    added to every node:

        <field>_canonical_paper : renames are paper-wide consistent
        <field>_canonical_local : renames are first-occurrence within the node
        variable_rename_map_paper : the paper-wide map used
        variable_rename_map_local_<node_id> : per-node map

    Args:
        paper_json:     A paper-graph JSON (nodes + edges).
        prose_rewrites: If True, normalize prose phrasing too.

    Returns:
        New JSON dict (original untouched).
    """
    result = deepcopy(paper_json)
    paper_map = build_paper_rename_map(paper_json)
    result["variable_rename_map_paper"] = paper_map

    nodes = result.get("nodes", {})

    def _process_node(node):
        combined = ""
        for fname in _FIELDS_TO_CANONICALIZE_STRING:
            v = node.get(fname, "")
            if isinstance(v, str):
                combined += " " + v
        for fname in _FIELDS_TO_CANONICALIZE_LIST:
            items = node.get(fname) or []
            if isinstance(items, list):
                combined += " " + " ".join(str(x) for x in items)
        local_map = build_local_rename_map(combined)

        new_node = _canonicalize_node(
            node, paper_map, paper_map, prose_rewrites, "paper"
        )
        new_node = _canonicalize_node(
            new_node, paper_map, local_map, prose_rewrites, "local"
        )
        new_node["variable_rename_map_local"] = local_map
        return new_node

    if isinstance(nodes, dict):
        result["nodes"] = {
            node_id: _process_node(node)
            for node_id, node in nodes.items()
        }
    elif isinstance(nodes, list):
        result["nodes"] = [_process_node(node) for node in nodes]

    return result


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def _cli():
    import argparse
    ap = argparse.ArgumentParser(
        description="Canonicalize a paper JSON (adds _canonical_paper / _canonical_local fields)."
    )
    ap.add_argument("input", help="Path to paperN_gold.json")
    ap.add_argument("-o", "--output", help="Path to write canonical JSON (default: input with _canonical suffix)")
    ap.add_argument("--prose-rewrites", action="store_true",
                    help="Apply prose rewrites (Suppose -> Let, etc.)")
    args = ap.parse_args()

    with open(args.input) as f:
        paper = json.load(f)
    result = canonicalize_paper(paper, prose_rewrites=args.prose_rewrites)
    out_path = args.output or args.input.replace(".json", "_canonical.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    _cli()
