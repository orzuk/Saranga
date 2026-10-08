"""
Numerical differential testing of the canonicalizer: does a formula keep its
mathematical meaning?

For every math segment (from the corpus, or from a random fuzzer) we

  1. canonicalize it with a local rename map (`build_local_rename_map`);
  2. parse the original and the canonical form into SymPy, after a small,
     independent normalisation that only makes the LaTeX parseable (symbols
     are wrapped as `\\mathit{..}` atoms, sizing/spacing commands dropped, ...);
  3. evaluate both at random points, giving a symbol and its canonical name
     (V_k, or the merged Greek/ell form) the same value, and compare:
       - expressions: equal values within a relative tolerance;
       - relations and chains: the same multiset of atoms (op, lhs - rhs)
         after orienting > as <, and the same truth value. So `a \\geq b`
         and `b \\leq a` agree, `x^2 \\geq 0` and `x^0 \\leq 2` do not;
  4. for every disagreement, replay the pipeline phase by phase and name the
     first phase after which the meaning changes.

Anything the parser cannot read is SKIPPED and counted by reason; a skip is
never a pass. Complex values and evaluation errors make a point unusable, not
a violation.

Run (from the repo root):
    python3 -m scripts.canonicalize.verify_meaning                 # corpus + fuzz
    python3 -m scripts.canonicalize.verify_meaning --limit-papers 10 --n-fuzz 500
    python3 -m scripts.canonicalize.verify_meaning --no-corpus --n-fuzz 5000

Conventions (documented approximations):
  - \\quad / \\qquad separate two formulas on both sides (the canonicalizer keeps them);
  - \\ll, \\gg are read as <, >; \\lesssim, \\prec, ... as order relations with
    their own label, \\approx, \\sim, \\equiv, ... as symmetric relations; only the
    structure (which two sides are compared, in which direction) is checked;
  - `e` is Euler's number on both sides.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import signal
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import core
from . import rules as R

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPO / "corpus" / "silver" / "tex_pool"
DEFAULT_OUT = REPO / "out" / "canonicalize_verify" / "meaning_report.json"


# ---------------------------------------------------------------------------
# The pipeline, phase by phase (mirrors core._canonicalize_math_segment)
# ---------------------------------------------------------------------------
# Every phase looks its function up on `core` / `R` at call time, so a
# monkeypatched phase is replayed too. `check_drift` compares the replay with
# core._canonicalize_math_segment on every formula, so a change in core.py
# that this list does not follow shows up as drift, not as silence.

def split_delimiters(math_text: str):
    """Phase 0 of the pipeline: (inner, open, close), as core does it."""
    return core._split_delimiters(math_text)


# core.MATH_PHASES: (name, fn(text, ctx)); every fn looks its phase function
# up on `core` at call time.
PHASES = core.MATH_PHASES
RENAME_PHASE = len(PHASES) - 1


def replay(math_text: str, rename_map, variants):
    """[(phase name, inner text after that phase)], starting with phase 0."""
    inner, o, c = split_delimiters(math_text)
    ctx = {"rename_map": rename_map, "variants": variants}
    stages = [("0 delimiters/&/labels", inner)]
    for name, fn in PHASES:
        inner = fn(inner, ctx)
        stages.append((name, inner))
    return stages, o, c


# ---------------------------------------------------------------------------
# Making LaTeX parseable (independent of the canonicalizer)
# ---------------------------------------------------------------------------

_TOK_ORIG = re.compile(r"\\\\|\\[A-Za-z]+\*?|\\.|\d+(?:\.\d+)?|[A-Za-z]|\s+|.", re.S)
_TOK_CANON = re.compile(r"\\\\|\\[A-Za-z]+\*?|\\.|V\d+|\d+(?:\.\d+)?|[A-Za-z]|\s+|.", re.S)

_DROP = {r"\,", r"\;", r"\!", r"\:", r"\>", r"\ ", "\\\n", "\\\t", "~", "&", r"\thinspace",
         r"\medspace", r"\thickspace", r"\enspace", r"\negthinspace", r"\negmedspace",
         r"\negthickspace", r"\displaystyle", r"\textstyle", r"\scriptstyle", r"\limits",
         r"\nolimits", r"\middle", r"\nonumber", r"\notag", r"\hfill", r"\allowbreak",
         r"\nobreak", r"\mathstrut", r"\strut", r"\big", r"\Big", r"\bigg", r"\Bigg",
         r"\bigl", r"\bigr", r"\Bigl", r"\Bigr", r"\biggl", r"\biggr", r"\Biggl", r"\Biggr",
         r"\bigm", r"\Bigm", r"\biggm", r"\Biggm"}
_DROP_WITH_GROUP = {r"\label", r"\tag", r"\tag*", r"\hspace", r"\hspace*", r"\vspace",
                    r"\vspace*", r"\phantom", r"\hphantom", r"\vphantom"}
_REPLACE = {r"\lbrace": r"\{", r"\rbrace": r"\}", r"\lbrack": "[", r"\rbrack": "]",
            r"\lparen": "(", r"\rparen": ")", r"\vert": "|", r"\lvert": "|", r"\rvert": "|",
            r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\cfrac": r"\frac", r"\lt": "<", r"\gt": ">"}
_TEXT_CMDS = {r"\text", r"\textrm", r"\textnormal", r"\textit", r"\textbf", r"\textsf",
              r"\texttt", r"\textup", r"\mbox", r"\hbox", r"\intertext", r"\shortintertext",
              r"\ref", r"\eqref", r"\cite"}
_FONT_SYMBOL = {r"\mathcal", r"\mathfrak", r"\mathscr", r"\mathbf", r"\boldsymbol", r"\bm",
                r"\mathsf", r"\mathit"}
_FONT_FIXED = {r"\mathbb", r"\mathbbm", r"\mathds", r"\mathrm", r"\operatorname", r"\operatorname*"}
_ACCENTS = {r"\hat", r"\widehat", r"\bar", r"\overline", r"\tilde", r"\widetilde", r"\vec",
            r"\dot", r"\ddot", r"\check", r"\breve", r"\acute", r"\grave", r"\underline",
            r"\mathring", r"\overrightarrow"}
_SWITCHES = {r"\rm", r"\bf", r"\it", r"\sf", r"\tt", r"\cal", r"\mit", r"\sl", r"\sc", r"\em"}
_DECORATED_REL = {r"\overset", r"\underset", r"\stackrel", r"\mathrel"}
_SEPARATORS = {",", ";", r"\quad", r"\qquad", r"\implies", r"\Rightarrow", r"\Longrightarrow", r"\iff",
               r"\Leftrightarrow", r"\Longleftrightarrow", r"\wedge", r"\land", r"\vee", r"\lor",
               r"\forall", r"\exists", r"\impliedby", r"\Leftarrow"}

# relation token -> (label, kind): kind 'ord' (lhs - rhs op 0), 'sym' (symmetric)
_REL = {"=": ("=", "sym"), "<": ("<", "ord"), ">": (">", "ord"),
        r"\leq": ("<=", "ord"), r"\le": ("<=", "ord"), r"\leqslant": ("<=", "ord"),
        r"\leqq": ("<=", "ord"), r"\geq": (">=", "ord"), r"\ge": (">=", "ord"),
        r"\geqslant": (">=", "ord"), r"\geqq": (">=", "ord"),
        r"\ll": ("<", "ord"), r"\gg": (">", "ord"), r"\lneq": ("<", "ord"), r"\gneq": (">", "ord"),
        r"\lesssim": ("lesssim", "ord"), r"\gtrsim": ("gtrsim", "ord"),
        r"\prec": ("prec", "ord"), r"\succ": ("succ", "ord"),
        r"\preceq": ("preceq", "ord"), r"\succeq": ("succeq", "ord"),
        r"\neq": ("!=", "sym"), r"\ne": ("!=", "sym"), r"\approx": ("approx", "sym"),
        r"\sim": ("sim", "sym"), r"\simeq": ("simeq", "sym"), r"\equiv": ("equiv", "sym"),
        r"\cong": ("cong", "sym"), r"\asymp": ("asymp", "sym"), r"\propto": ("propto", "sym")}
# '>'-type label -> its '<'-type label (the atom is oriented as lhs - rhs < 0)
_ORIENT = {">": "<", ">=": "<=", "gtrsim": "lesssim", "succ": "prec", "succeq": "preceq"}
_TRUTH = {"<": lambda g: g < 0, "<=": lambda g: g <= 0, "lesssim": lambda g: g <= 0,
          "prec": lambda g: g < 0, "preceq": lambda g: g <= 0}

_ALLOWED_CMDS = {r"\frac", r"\sqrt", r"\cdot", r"\times", r"\div", r"\sin", r"\cos", r"\tan",
                 r"\sec", r"\csc", r"\cot", r"\sinh", r"\cosh", r"\tanh", r"\arcsin", r"\arccos",
                 r"\arctan", r"\exp", r"\log", r"\ln", r"\pi", r"\mathit", r"\{", r"\}",
                 r"\binom", r"\lfloor", r"\rfloor", r"\lceil", r"\rceil"}
# e: Euler's number. No standalone ".": numbers are single tokens (2.5), and
# parse_latex silently drops everything after a stray period ({a}/{b.} -> a).
_ALLOWED_CHARS = set("0123456789+-*/^_()[]{}|! e")
_OPEN = {"{", "(", "[", r"\{", r"\langle", r"\lfloor", r"\lceil"}
_CLOSE = {"}", ")", "]", r"\}", r"\rangle", r"\rfloor", r"\rceil"}

_GREEK = (set(R.GREEK_VARIABLE_COMMANDS) | set(R.RULES_GREEK_VARIANTS)
          | set(R.RULES_GREEK_VARIANTS.values()) | {r"\ell", r"\varpi"}) - {r"\pi"}
_UNICODE_GREEK = set(R.RULES_GREEK_UNICODE_TO_COMMAND) - {"π"}


def _merge_inverse():
    """canonical symbol -> the original symbols the literal rules map onto it."""
    inv = defaultdict(set)
    for table in (R.RULES_GREEK_UNICODE_TO_COMMAND, R.RULES_GREEK_VARIANTS, R.RULES_ELL):
        for k, v in table.items():
            inv[v].add(k)
    changed = True
    while changed:
        changed = False
        for v in list(inv):
            for k in list(inv[v]):
                extra = inv.get(k, set()) - inv[v]
                if extra:
                    inv[v] |= extra
                    changed = True
    return inv


class Skip(Exception):
    pass


@dataclass
class Ctx:
    rename_map: dict | None = None
    inv_map: dict = field(default_factory=dict)
    norm_keys: set = field(default_factory=set)
    orig_bases: set = field(default_factory=set)
    table: dict = field(default_factory=dict)          # symbol id -> sympy name
    merge_inv: dict = field(default_factory=dict)
    key_to_v: dict = field(default_factory=dict)
    canon_text: str = ""

    def name(self, sid: str) -> str:
        if sid not in self.table:
            i, s = len(self.table), ""
            while True:
                s = chr(97 + i % 26) + s
                i = i // 26 - 1
                if i < 0:
                    break
            self.table[sid] = "z" + s
        return self.table[sid]


def make_ctx(rename_map: dict | None) -> Ctx:
    ctx = Ctx(rename_map=rename_map, merge_inv=_merge_inverse())
    if rename_map:
        ctx.inv_map = {v: re.sub(r"\s+", "", k) for k, v in rename_map.items()}
        ctx.norm_keys = {re.sub(r"\s+", "", k) for k in rename_map}
        ctx.key_to_v = {re.sub(r"\s+", "", k): v for k, v in rename_map.items()}
    return ctx


def strip_outer(text: str) -> str:
    t = text.strip()
    m = re.match(r"\\begin\s*\{((?:" + core._DISPLAY_ENVS + r"|multline|gather)\*?)\}(.*)\\end\s*\{\1\}\Z",
                 t, re.S)
    if m:
        body = m.group(2)
        if m.group(1).startswith("alignat"):          # \begin{alignat}{3}: a column count
            body = re.sub(r"^\s*\{[^{}]*\}", "", body)
        return body
    for o, c in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$")):
        if t.startswith(o) and t.endswith(c) and len(t) >= len(o) + len(c):
            return t[len(o):len(t) - len(c)]
    return t


def _tokens(text: str, side: str):
    rx = _TOK_CANON if side == "canon_final" else _TOK_ORIG
    # \tfrac 1 \rho must be braced like \frac (brace_args), or parse_latex
    # silently drops the rest of the formula
    return [_FRAC_ALIAS.get(m.group(0), m.group(0)) for m in rx.finditer(text)]


_FRAC_ALIAS = {r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\cfrac": r"\frac"}


def _group_end(toks, i):
    """toks[i] == '{': index of the matching '}' (or -1)."""
    depth = 0
    for j in range(i, len(toks)):
        if toks[j] == "{":
            depth += 1
        elif toks[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _skip_ws(toks, i):
    while i < len(toks) and toks[i].isspace():
        i += 1
    return i


def _arg(toks, i):
    """One TeX argument starting at toks[i] (after spaces): (arg tokens, next index)."""
    i = _skip_ws(toks, i)
    if i >= len(toks):
        raise Skip("dangling command")
    if toks[i] == "{":
        j = _group_end(toks, i)
        if j < 0:
            raise Skip("unbalanced braces")
        return toks[i + 1:j], j + 1
    return [toks[i]], i + 1


_ARGC = {r"\frac": 2, r"\binom": 2, r"\sqrt": 1, r"\overset": 2, r"\underset": 2,
         r"\stackrel": 2, r"\mathrel": 1}


def _argc(t):
    if t in _ARGC:
        return _ARGC[t]
    if t in _ACCENTS or t in _FONT_SYMBOL or t in _FONT_FIXED or t in _TEXT_CMDS:
        return 1
    return 0


def _take(toks, i):
    """End index of the TeX argument starting at toks[i] (i at a non-space)."""
    if toks[i] == "{":
        e = _group_end(toks, i)
        if e < 0:
            raise Skip("unbalanced braces")
        return e + 1
    t, i = toks[i], i + 1
    if t == r"\sqrt":
        j = _skip_ws(toks, i)
        if j < len(toks) and toks[j] == "[":
            while j < len(toks) and toks[j] != "]":
                j += 1
            i = j + 1
    for _ in range(_argc(t)):
        j = _skip_ws(toks, i)
        if j >= len(toks):
            raise Skip("dangling command")
        i = _take(toks, j)
    return i


def brace_args(toks):
    """Make TeX's implicit arguments explicit: x^2y -> x^{2}y, \\sqrt[3]3 ->
    \\sqrt[3]{3}, \\frac12 -> \\frac{1}{2}, ^\\prime -> ^{\\prime}. Only the
    grouping TeX itself uses; nothing else changes."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        n = 1 if t in ("^", "_") else _ARGC.get(t, 0) if t in (r"\frac", r"\binom", r"\sqrt") else 0
        out.append(t)
        i += 1
        if not n:
            continue
        if t == r"\sqrt":
            j = _skip_ws(toks, i)
            if j < len(toks) and toks[j] == "[":
                k = j
                while k < len(toks) and toks[k] != "]":
                    k += 1
                out += brace_args(toks[i:k + 1])
                i = k + 1
        for _ in range(n):
            j = _skip_ws(toks, i)
            if j >= len(toks):
                break
            if re.fullmatch(r"\d+(?:\.\d+)?", toks[j]) and len(toks[j]) > 1:
                toks = toks[:j] + [toks[j][0], toks[j][1:]] + toks[j + 1:]   # \frac12, x^12
            e = _take(toks, j)
            if toks[j] == "{":
                out += ["{"] + brace_args(toks[j + 1:e - 1]) + ["}"]
            else:
                out += ["{"] + brace_args(toks[j:e]) + ["}"]
            i = e
    return out


def _symbol_like(t, side):
    return (t in _GREEK or t in _UNICODE_GREEK or (re.fullmatch(r"[A-Za-z]", t) and t != "e")
            or (side == "canon_final" and re.fullmatch(r"V\d+", t)))


# literal "spelling" rules: their correctness is verify_symbols' job, so a
# subscript key is compared after them (\\R^n and \\mathbb{R}^n index alike)
_SPELLING_TABLES = ("RULES_SPACING", "RULES_BRACKETS", "RULES_NUMBER_SETS", "RULES_OPERATORS",
                    "RULES_RELATIONS", "RULES_SET_RELATIONS", "RULES_ARROWS", "RULES_LOGIC",
                    "RULES_FUNCTION_ALIASES", "RULES_FRAC_ALIASES")


def _sub_key(body, side, ctx):
    """Identity of a subscript: its value if it is arithmetic (so {m+1},
    m{+}1 and \\frac{1}{2} vs 1/2 agree), else its normalised text."""
    sub = _symbolize(brace_args(body), side, ctx)
    try:
        if any(x[0] in ("sep", "row", "rel") for x in sub):
            raise Skip("")
        import sympy
        e = _side_to_sympy(sub, ctx)
        inv = {v: k for k, v in ctx.table.items()}
        return "=" + str(sympy.expand(e.xreplace({sy: sympy.Symbol(inv.get(sy.name, sy.name))
                                                  for sy in e.free_symbols})))
    except Skip:
        pass
    txt = " ".join(x[1] if x[0] in ("sym", "tok", "rel") else "," for x in sub)
    for tbl in _SPELLING_TABLES:
        txt = core._apply_literal_rules(txt, getattr(R, tbl))
    return re.sub(r"[\s{}]", "", txt)


def _resolve(tok: str, side: str, ctx: Ctx) -> str:
    """Symbol id: the ORIGINAL symbol a token stands for."""
    if side == "orig":
        ctx.orig_bases.add(tok)
        return tok
    if side == "canon_final" and re.fullmatch(r"V\d+", tok):
        return ctx.inv_map.get(tok, "?" + tok)
    fm = re.fullmatch(r"(\\[A-Za-z]+)\{(.*)\}", tok)
    if fm and fm.group(2) in ctx.merge_inv:
        cands = [tok] + [fm.group(1) + "{" + k + "}" for k in sorted(ctx.merge_inv[fm.group(2)])]
    else:
        cands = [tok] + sorted(ctx.merge_inv.get(tok, ()))
    present = [c for c in cands if c in ctx.orig_bases]
    sid = tok if tok in present or not present else present[0]
    if side == "canon_final" and sid == tok and len(present) > 1 and tok in ctx.norm_keys \
            and re.search(re.escape(ctx.key_to_v[tok]) + r"(?!\d)", ctx.canon_text):
        sid = next(c for c in present if c != tok)   # the real `l` was renamed; this is the merged \ell
    if side == "canon_final" and sid in ctx.norm_keys and re.search(
            re.escape(ctx.key_to_v[sid]) + r"(?!\d)", ctx.canon_text):
        # one original symbol split in two: renamed to V_k elsewhere, kept here
        return "UNRENAMED:" + sid
    return sid


def _symbolize(toks, side, ctx):
    """Tokens -> items: ('sym', id) | ('tok', t) | ('sep',) | ('row',) | ('rel', t)."""
    out, i, nest = [], 0, 0
    while i < len(toks):
        t = toks[i]
        if t.isspace():
            i += 1
            continue
        if t == "&" and nest > 0:          # a column of a nested cases/array
            out.append(("sep",))
            i += 1
            continue
        if t in _DROP:
            i += 1
            continue
        if t == "{":
            e = _group_end(toks, i)
            inner = [x for x in toks[i + 1:e] if not x.isspace()] if e > 0 else []
            if len(inner) == 1 and inner[0] in ("+", "-", r"\cdot", r"\times"):
                toks = toks[:i] + inner + toks[e + 1:]    # {+}: an ordinary +
                continue
            k = _skip_ws(toks, e + 1) if e > 0 else len(toks)
            font_sym = len(inner) in (2, 4) and inner[0] in _FONT_SYMBOL and (
                len(inner) == 2 or (inner[1], inner[3]) == ("{", "}"))   # {\mathcal D}
            if (len(inner) == 1 and _symbol_like(inner[0], side) or font_sym) and k < len(toks) \
                    and toks[k] in ("_", "'"):
                toks = toks[:i] + inner + toks[k:]       # {X}_c is X_c
                continue
        if t in (r"\left", r"\right"):
            i = _skip_ws(toks, i + 1)
            if i < len(toks) and toks[i] == ".":
                i += 1
            elif i < len(toks) and toks[i] in "<>":
                out.append(("tok", r"\langle" if toks[i] == "<" else r"\rangle"))
                i += 1
            continue
        if t in _DROP_WITH_GROUP:
            _, i = _arg(toks, i + 1)
            continue
        if t == "\\\\" or t == r"\cr":
            i += 1
            if i < len(toks) and toks[i] == "*":
                i += 1
            j = _skip_ws(toks, i)
            if j < len(toks) and toks[j] == "[":
                k = j
                while k < len(toks) and toks[k] != "]":
                    k += 1
                i = k + 1
            out.append(("row",))
            continue
        t = _REPLACE.get(t, t)
        if t in (r"\begin", r"\end"):                    # nested cases/array/matrix
            nest += 1 if t == r"\begin" else -1
            _, i = _arg(toks, i + 1)
            j = _skip_ws(toks, i)
            if t == r"\begin" and j < len(toks) and toks[j] == "{" and re.fullmatch(
                    r"[lcr|@{}\s]*", "".join(toks[j:_group_end(toks, j) + 1])[1:-1] or "x"):
                _, i = _arg(toks, j)                      # array column spec
            out.append(("sep",))
            continue
        if t in _TEXT_CMDS:
            _, i = _arg(toks, i + 1)
            out.append(("sep",))
            continue
        if t in _SWITCHES:                      # {\rm supp}: a fixed name to the group end
            j, depth = i + 1, 0
            while j < len(toks) and not (toks[j] == "}" and depth == 0):
                depth += {"{": 1, "}": -1}.get(toks[j], 0)
                j += 1
            out.append(("tok", t + "{" + "".join(x for x in toks[i + 1:j] if not x.isspace()) + "}"))
            i = j
            continue
        if t in _SEPARATORS:
            out.append(("sep",))
            i += 1
            continue
        if t in _DECORATED_REL:
            if t != r"\mathrel":
                _, i = _arg(toks, i + 1)
            body, i = _arg(toks, i)
            body = [b for b in body if not b.isspace()]
            if len(body) == 1 and _REPLACE.get(body[0], body[0]) in _REL:
                out.append(("rel", _REPLACE.get(body[0], body[0])))
            else:
                out.append(("tok", t))           # unsupported
            continue
        if t in _REL:
            out.append(("rel", t))
            i += 1
            continue
        sym = None
        if t in _FONT_SYMBOL:
            body, i = _arg(toks, i + 1)
            content = "".join(b for b in body if not b.isspace())
            nb = [b for b in body if not b.isspace()]
            if (len(nb) == 2 or len(nb) == 4 and (nb[1], nb[3]) == ("{", "}")) and nb[0] in _FONT_SYMBOL:
                content = nb[0] + "{" + nb[-2 if len(nb) == 4 else 1] + "}"   # \boldsymbol{\mathfrak{n}}
                if side == "canon_final" and re.fullmatch(r"V\d+", nb[-2 if len(nb) == 4 else 1]):
                    content = nb[0] + "{" + _resolve(nb[-2 if len(nb) == 4 else 1], side, ctx) + "}"
                body = [content]
                nb = body
            if len(nb) > 1:
                # \boldsymbol{\frac{1}{q}}, \mathbf{x+y}: styling of a formula,
                # read as the formula itself
                toks = toks[:i] + ["{"] + body + ["}"] + toks[i:]
                continue
            if side == "canon_final" and re.fullmatch(r"V\d+", content):
                sym = _resolve(content, side, ctx)
                sym = t + "{" + sym + "}"
            else:
                sym = _resolve(t + "{" + content + "}", side, ctx)
        elif t in _FONT_FIXED:
            body, i = _arg(toks, i + 1)
            out.append(("tok", t + "{" + "".join(body) + "}"))
            continue
        elif t in _ACCENTS:
            body, i = _arg(toks, i + 1)
            inner = _symbolize(body, side, ctx)
            if len(inner) == 1 and inner[0][0] == "sym":
                sym = t + "{" + inner[0][1] + "}"
            else:
                out.append(("tok", t))
                continue
        elif t in _GREEK or t in _UNICODE_GREEK or (re.fullmatch(r"[A-Za-z]", t) and t != "e"):  # noqa
            sym = _resolve(t, side, ctx)
            i += 1
        elif side == "canon_final" and re.fullmatch(r"V\d+", t):
            # longest prefix that the map knows: V12 may be V1 followed by 2
            for L in range(len(t), 1, -1):
                if t[:L] in ctx.inv_map:
                    break
            sym = _resolve(t[:L], side, ctx)
            if t[L:]:
                toks = toks[:i + 1] + [t[L:]] + toks[i + 1:]
            i += 1
        else:
            out.append(("tok", t))
            i += 1
            continue
        # postfix: primes and subscripts fold into the symbol
        while True:
            j = _skip_ws(toks, i)
            if j < len(toks) and toks[j] == "'":
                sym, i = sym + "'", j + 1
            elif j < len(toks) and toks[j] == "^" and _skip_ws(toks, j + 1) < len(toks) \
                    and toks[_skip_ws(toks, j + 1)] == "{" \
                    and (lambda g: g and all(x == r"\prime" for x in g))(
                        [x for x in toks[_skip_ws(toks, j + 1) + 1:max(_group_end(toks, _skip_ws(toks, j + 1)), 0)]
                         if not x.isspace()]):
                k = _skip_ws(toks, j + 1)
                e = _group_end(toks, k)
                sym, i = sym + "'" * sum(1 for x in toks[k:e] if x == r"\prime"), e + 1
            elif j < len(toks) and toks[j] == "_":
                body, i = _arg(toks, j + 1)
                sym = sym + "_{" + _sub_key(body, side, ctx) + "}"
            else:
                break
        out.append(("sym", sym))
    return out


@dataclass
class Piece:
    kind: str                     # 'expr' | 'rel' | 'skip'
    sides: list = field(default_factory=list)      # sympy exprs
    ops: list = field(default_factory=list)        # relation labels
    reason: str = ""
    text: str = ""


def _split_rows(items):
    rows, cur = [], []
    for it in items:
        if it[0] == "row":
            rows.append(cur)
            cur = []
        else:
            cur.append(it)
    rows.append(cur)
    rows = [r for r in rows if r]
    joined = []
    for r in rows:   # a row that starts with a relation or an operator continues the last
        if joined and (r[0][0] == "rel" or (r[0][0] == "tok" and r[0][1] in ("+", "-", r"\cdot", r"\times"))):
            joined[-1] = joined[-1] + r
        else:
            joined.append(r)
    return joined


def _split_pieces(row):
    pieces, cur, depth = [], [], 0
    for it in row:
        if it[0] == "tok" and it[1] in _OPEN:
            depth += 1
        elif it[0] == "tok" and it[1] in _CLOSE:
            depth = max(depth - 1, 0)
        elif depth > 0 and it[0] in ("tok", "sep") and it[1:] in ((",",), (";",), ()):
            it = ("tok", r"\tuple")     # f(x, y), (a, b], {1, 2}: no numeric reading
        if depth == 0 and (it[0] == "sep" or (it[0] == "tok" and it[1] in (",", ";"))):
            pieces.append(cur)
            cur = []
        else:
            cur.append(it)
    pieces.append(cur)
    # trailing sentence punctuation is not part of the formula
    out = []
    for p in pieces:
        while p and p[-1] == ("tok", "."):
            p = p[:-1]
        if p:
            out.append(p)
    return out


_PARSE_CACHE: dict = {}


def _parse(latex: str):
    if latex in _PARSE_CACHE:
        r = _PARSE_CACHE[latex]
    else:
        from sympy.parsing.latex import parse_latex
        try:
            r = parse_latex(latex)
        except Exception as e:  # noqa: BLE001 -- the parser raises many kinds
            r = Skip("parse error")
        if len(_PARSE_CACHE) < 200000:
            _PARSE_CACHE[latex] = r
    if isinstance(r, Skip):
        raise Skip(str(r))
    return r


def _side_to_sympy(items, ctx):
    import sympy
    parts = []
    for it in items:
        if it[0] == "sym":
            parts.append(r"\mathit{" + ctx.name(it[1]) + "}")
        elif it[0] == "tok":
            t = it[1]
            if t == r"\tuple":
                raise Skip("comma inside brackets (arguments/tuple)")
            if t == r"\innerrel":
                raise Skip("relation inside brackets")
            if t.startswith("\\") and t not in _ALLOWED_CMDS:
                raise Skip("unsupported command " + re.sub(r"\{.*", "", t, flags=re.S).strip())
            if not t.startswith("\\") and not all(ch in _ALLOWED_CHARS for ch in t):
                raise Skip("unsupported character " + t)
            parts.append(t)
    if not parts:
        raise Skip("empty side")
    latex = " ".join(parts)
    if parts[-1] in ("+", "-", "*", "/", "^", "_"):
        raise Skip("dangling operator")          # parse_latex drops it: {\gamma*} -> \gamma
    if re.search(r"\^\s*\{?\s*\*", latex):
        raise Skip("star superscript")           # parse_latex reads 1/{a^{*}} as 1
    expr = _parse(latex)
    if not isinstance(expr, sympy.Expr):
        raise Skip("parse error")
    names = set(ctx.table.values()) | {"e", "pi"}
    stray = [s for s in expr.free_symbols if s.name not in names]
    if stray:
        raise Skip("stray symbol")
    for cls in ("Integral", "Sum", "Product", "Limit", "Derivative"):
        if expr.has(getattr(sympy, cls)):
            raise Skip("contains " + cls)
    from sympy.core.function import AppliedUndef
    if expr.atoms(AppliedUndef):
        raise Skip("undefined function")
    # parse_latex builds \\log_2 x as an unevaluated log(x, 2), and E**log(x, 2)
    # then auto-simplifies to x (a SymPy artefact); spell the base out first.
    expr = expr.replace(lambda a: isinstance(a, sympy.log) and len(a.args) == 2,
                        lambda a: sympy.log(a.args[0]) / sympy.log(a.args[1]))
    return expr.xreplace({sympy.Symbol("e"): sympy.E, sympy.Symbol("pi"): sympy.pi})


def prepare(text: str, side: str, ctx: Ctx):
    """LaTeX -> list of Piece. side: 'orig', 'canon' (intermediate stage) or
    'canon_final' (after the rename phase: V_k tokens)."""
    if side == "canon_final":
        ctx.canon_text = text
    try:
        items = _symbolize(brace_args(_tokens(strip_outer(text), side)), side, ctx)
    except Skip as e:
        return [Piece("skip", reason=str(e))]
    except RecursionError:
        return [Piece("skip", reason="too deep")]
    pieces = []
    for row in _split_rows(items):
        for p in _split_pieces(row):
            sides, ops, cur, depth = [], [], [], 0
            for it in p:
                if it[0] == "tok" and it[1] in _OPEN:
                    depth += 1
                elif it[0] == "tok" and it[1] in _CLOSE:
                    depth = max(depth - 1, 0)
                if it[0] == "rel" and depth > 0:
                    cur.append(("tok", r"\innerrel"))
                    continue
                if it[0] == "rel":
                    sides.append(cur)
                    ops.append(_REL[it[1]][0])
                    cur = []
                else:
                    cur.append(it)
            sides.append(cur)
            txt = " ".join(x[1] if len(x) > 1 else x[0] for x in p)
            try:
                exprs = [_side_to_sympy(s, ctx) for s in sides]
            except Skip as e:
                pieces.append(Piece("skip", reason=str(e), text=txt))
                continue
            pieces.append(Piece("rel" if ops else "expr", exprs, ops, text=txt))
    return pieces


# ---------------------------------------------------------------------------
# Numerical comparison
# ---------------------------------------------------------------------------

N_POINTS = 6
MAX_ATTEMPTS = 40
RTOL = 1e-7


def _close(a, b):
    return abs(a - b) <= RTOL * max(1.0, abs(a), abs(b))


def _evaluate(expr, subs):
    import sympy
    try:
        v = complex(sympy.N(expr.xreplace(subs), 20))
    except Exception:  # noqa: BLE001
        return None
    if not (math.isfinite(v.real) and math.isfinite(v.imag)):
        return None
    return v


def _draw(names, rng, positive):
    import sympy
    vals = {}
    for n in sorted(names):
        if positive:
            x = rng.uniform(0.2, 3.0)
        else:
            r = rng.random()
            x = (rng.choice([-3, -2, -1, 1, 2, 3]) if r < 0.25 else
                 rng.uniform(0.1, 3.0) if r < 0.5 else rng.uniform(-3.0, 3.0))
        vals[n] = x
    return vals, {sympy.Symbol(n): sympy.Float(x, 20) for n, x in vals.items()}


def _atoms(piece, values):
    """[(label, kind, g)] with g = lhs - rhs oriented so the label is '<'-type."""
    out = []
    for k, op in enumerate(piece.ops):
        a, b = values[k], values[k + 1]
        kind = "sym" if op in ("=", "!=") or op not in _TRUTH and op not in _ORIENT else "ord"
        if op in _ORIENT:
            out.append((_ORIENT[op], kind, b - a))
        else:
            out.append((op, kind, a - b))
    return out


def compare_pieces(po: Piece, pc: Piece, seed: int):
    """None if the meaning agrees, a dict describing the violation, or
    ('skip', reason)."""
    if po.kind == "skip":
        return ("skip", po.reason)
    if pc.kind == "skip":
        return ("skip", "canonical: " + pc.reason)
    if po.kind != pc.kind:
        return {"kind": "structure", "detail": f"{po.kind} became {pc.kind}"}
    names = set()
    for e in po.sides + pc.sides:
        names |= {s.name for s in e.free_symbols}
    rng = random.Random(seed)
    good, complex_seen, asym = [], 0, 0
    for attempt in range(MAX_ATTEMPTS):
        if len(good) >= N_POINTS:
            break
        vals, subs = _draw(names, rng, positive=attempt >= MAX_ATTEMPTS // 2)
        vo = [_evaluate(e, subs) for e in po.sides]
        vc = [_evaluate(e, subs) for e in pc.sides]
        if any(v is None for v in vo) or any(v is None for v in vc):
            if all(v is not None for v in vo) != all(v is not None for v in vc):
                asym += 1
            continue
        if any(abs(v.imag) > 1e-12 * max(1.0, abs(v)) for v in vo + vc):
            complex_seen += 1
            continue
        good.append((vals, [v.real for v in vo], [v.real for v in vc]))
    if len(good) < 3:
        if asym:
            return ("skip", "domain differs (one side undefined)")
        return ("skip", "complex values" if complex_seen else "no valid evaluation points")
    if po.kind == "expr":
        for vals, vo, vc in good:
            if not _close(vo[0], vc[0]):
                return {"kind": "value", "point": vals, "orig_value": vo[0], "canon_value": vc[0]}
        return None
    # relations: matching atoms, then the truth value of the whole chain
    ao = [_atoms(po, vo) for _, vo, _ in good]
    ac = [_atoms(pc, vc) for _, _, vc in good]
    for (vals, vo, vc), xo, xc in zip(good, ao, ac):
        to = all(_TRUTH[l](g) if k == "ord" and l in _TRUTH else True for l, k, g in xo)
        tc = all(_TRUTH[l](g) if k == "ord" and l in _TRUTH else True for l, k, g in xc)
        near = any(abs(g) < 1e-9 for _, _, g in xo + xc)
        if to != tc and not near:
            return {"kind": "truth", "point": vals, "orig_value": to, "canon_value": tc}
    if len(po.ops) != len(pc.ops):
        return {"kind": "relation", "detail": f"{po.ops} became {pc.ops}", "point": good[0][0]}
    used = set()
    for i in range(len(po.ops)):
        found = False
        for j in range(len(pc.ops)):
            if j in used or ao[0][i][0] != ac[0][j][0]:
                continue
            same = all(_close(a[i][2], c[j][2]) for a, c in zip(ao, ac))
            if not same and ao[0][i][1] == "sym":
                same = all(_close(a[i][2], -c[j][2]) for a, c in zip(ao, ac))
            if same:
                used.add(j)
                found = True
                break
        if not found:
            return {"kind": "relation", "detail": f"atom {ao[0][i][0]} of {po.ops} has no "
                    f"counterpart in {pc.ops}", "point": good[0][0],
                    "orig_value": [a[2] for a in ao[0]], "canon_value": [c[2] for c in ac[0]]}
    return None


def compare(orig_text: str, canon_text: str, side: str, ctx: Ctx, seed: int):
    """Compare two LaTeX strings. Returns (status, info, n_pieces):
    status in 'ok', 'violation', 'skip'."""
    ctx.table, ctx.orig_bases = {}, set()
    po = prepare(orig_text, "orig", ctx)
    pc = prepare(canon_text, side, ctx)
    if not po:
        return "skip", "no math content", 0
    if len(po) == 1 and po[0].kind == "skip":
        return "skip", po[0].reason, 0
    if all(p.kind == "skip" for p in po):
        return "skip", Counter(p.reason for p in po).most_common(1)[0][0], 0
    if len(po) != len(pc):
        if len(pc) == 1 and pc[0].kind == "skip" and not pc[0].text:
            return "skip", "canonical: " + pc[0].reason, 0
        return "violation", {"kind": "structure", "piece": None,
                             "detail": f"{len(po)} formula pieces became {len(pc)}",
                             "orig_pieces": [p.text for p in po],
                             "canon_pieces": [p.text for p in pc]}, 0
    skips, checked = [], 0
    for k, (a, b) in enumerate(zip(po, pc)):
        r = compare_pieces(a, b, seed * 1000 + k)
        if isinstance(r, tuple):
            skips.append(r[1])
        elif r is not None:
            r["piece"] = k
            r["orig_piece"], r["canon_piece"] = a.text, b.text
            if "point" in r:
                inv = {v: k2 for k2, v in ctx.table.items()}
                r["point"] = {inv.get(n, n): round(x, 6) for n, x in r["point"].items()}
            return "violation", r, checked
        else:
            checked += 1
    if checked == 0:
        return "skip", Counter(skips).most_common(1)[0][0], 0
    return "ok", skips, checked


# ---------------------------------------------------------------------------
# One formula end to end
# ---------------------------------------------------------------------------

def check_formula(formula: str, seed: int = 0) -> dict:
    rmap = core.build_local_rename_map(formula)
    variants = core._greek_variants_for(formula, rmap)
    canonical = core.canonicalize_text(formula, rename_map=rmap)
    stages, o, c = replay(formula, rmap, variants)
    replayed = re.sub(r"\s+", " ", o + stages[-1][1] + c).strip()
    res = {"formula": formula, "canonical": canonical, "rename_map": rmap,
           "drift": replayed != canonical,
           # TeX takes ONE token as an unbraced script: x^{y} -> x^y -> V1^V2,
           # which TeX reads as V1^{V}2. This verifier reads V_k as one atom.
           "unbraced_v_script": bool(re.search(r"(?<!\\)[\^_]V\d", canonical))}   # not \_ (text)
    ctx = make_ctx(rmap)
    status, info, n = compare(formula, canonical, "canon_final", ctx, seed)
    res["status"], res["pieces_checked"] = status, n
    if status == "skip":
        res["reason"] = info
    elif status == "ok":
        res["piece_skips"] = info
    else:
        res["violation"] = info
        res["phase"], res["stage_text"] = locate_phase(formula, stages, rmap, seed)
        res["bug_class"] = classify(res)
    return res


def classify(res: dict) -> str:
    """A best-effort root-cause label for a violation (for grouping only)."""
    ph, f, v = res["phase"], res["formula"], res["violation"]
    before = dict(res.get("_stages", []))
    point = v.get("point") or {}
    if ph.startswith("18"):
        un = {k.split(":", 1)[1] for k in point if k.startswith("UNRENAMED:")} | {
            m for m in re.findall(r"UNRENAMED:(\w)", json.dumps(v))}
        if un and all(u[:1] in R.NORM_LETTERS for u in un):
            return "rename: l/L followed by _ or ^ kept as a norm name while bare l/L is renamed"
        return "rename: a letter next to another letter (xy, _{ij}, h^{-1}gh) is not renamed"
    if re.search(r"\\end\s+\{", f):
        return "segment: \\end {env} with a space is not recognised; prose is swallowed into the math"
    if ph.startswith("0"):
        if re.search(r"\\\\\*?\s*&\s*\[", f):
            return "delimiters: dropping & after \\\\ makes a following [..] an optional argument of \\\\"
        if "alignat" in f:
            return "delimiters: \\begin{alignat}{N} column count becomes content N"
        if re.search(r"\\begin\{[^}]*\}.*&.*\\end", strip_outer(f), re.S):
            return "delimiters: & inside a nested matrix/array/cases is dropped, fusing columns (1&-1 -> 1 -1)"
        return "delimiters: other"
    if ph.startswith("1 "):
        return "spacing: the \\  rule eats the 2nd backslash of a line break \\\\ followed by space"
    if ph.startswith("15"):
        if re.search(r"\\\\\s*\[", f):
            return "flip: a line-break spacing argument \\\\[2pt] is swapped in as an operand"
        if re.search(r"\\(overset|underset|stackrel|mathrel)", f):
            return "flip: a relation inside \\overset/\\stackrel is not counted, so a chain is flipped"
        if re.search(r"\\(text\w*|mbox|hbox)\s*\{", f):
            return "flip: the clause boundary at \\text/\\mbox does not include its argument"
        if "\\\\" in f:
            return "flip: a chain or expression continued on the next row is flipped row by row"
        if re.search(r"[.,;]\s*(\$|\\\]|\\end\{)", f.strip()) and not re.search(
                r"[.,;]\s*(\$|\\\]|\\end\{)", res["canonical"].strip()):
            return "flip: trailing sentence punctuation is swapped into the formula (a > b. -> b. < a)"
        return "flip: other"
    if ph.startswith("14b frac"):
        stage = res.get("stage_text", "")
        if re.search(r"\}!", stage) or re.search(r"/[^ ]*!", res["canonical"]):
            return "frac: \\frac{a}{b}! -> a/b! (! is treated as a safe next character)"
        if re.search(r"\}\s*\|", stage) or "|" in res["canonical"]:
            return "frac: \\frac{a}{b}|x| -> a/b|x| (| is treated as a closing bar)"
        return "frac: other"
    if ph.startswith("16 ") and re.search(r"\\begin\{array\}[A-Z]", res["canonical"]):
        return "braces: array column spec {l} is unbraced and renamed (\\begin{array}{l} -> \\begin{array}V1)"
    if ph.startswith("16 "):
        if re.search(r"\\[A-Za-z]+_?\\[A-Za-z]{2,}", res["canonical"]) or re.search(
                r"_\\[A-Za-z]+[A-Za-z]", res.get("stage_text", "")):
            return "braces: {\\cmd} unbraced before a letter makes a new command (x_{\\alpha}d -> x_\\alphad)"
        if re.search(r"\d\{\d", f.replace(" ", "")) or re.search(r"\d\\[dt]?frac\{\d", f.replace(" ", "")):
            return "braces: digits fuse (10\\frac{3}{2} -> 10{3}/{2} -> 103/2)"
        return "braces: other"
    if ph.startswith("4 "):
        return "greek variant merge"
    return ph


def locate_phase(formula, stages, rmap, seed):
    """First phase after which the meaning differs from the original."""
    unparsed = []
    for k, (name, text) in enumerate(stages):
        final = k == len(stages) - 1
        ctx = make_ctx(rmap if final else None)
        status, info, _ = compare(formula, text, "canon_final" if final else "canon", ctx, seed)
        if status == "violation":
            note = f" (stages {unparsed[0]}..{unparsed[-1]} unparseable)" if unparsed else ""
            return name + note, text
        unparsed = unparsed + [name] if status == "skip" else []
    return "unlocated", stages[-1][1]


def _timeout(signum, frame):
    raise TimeoutError


def _worker(job):
    formula, seed, source = job
    try:
        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(20)
        r = check_formula(formula, seed)
    except TimeoutError:
        r = {"formula": formula, "status": "skip", "reason": "timeout", "drift": False}
    except Exception as e:  # noqa: BLE001 -- report, never crash the run
        r = {"formula": formula, "status": "skip", "reason": f"verifier error {type(e).__name__}",
             "drift": False}
    finally:
        signal.alarm(0)
    r["source"] = source
    return r


# ---------------------------------------------------------------------------
# Corpus collection
# ---------------------------------------------------------------------------

def collect_corpus(corpus_dir: Path, limit: int | None):
    sys.path.insert(0, str(REPO / "src"))
    from latex_facts import clean_source
    files = sorted(corpus_dir.glob("*.tex"))[:limit] if limit else sorted(corpus_dir.glob("*.tex"))
    occ = []
    for f in files:
        tex = clean_source(f.read_text(encoding="utf-8", errors="replace"))
        b = tex.find(r"\begin{document}")
        if b >= 0:
            tex = tex[b:]
        for kind, seg in core._segment(tex):
            if kind == "math" and seg.strip():
                occ.append((seg, f.stem))
    return files, occ


# ---------------------------------------------------------------------------
# Fuzzer
# ---------------------------------------------------------------------------

_FUZZ_VARS = ["x", "y", "z", "a", "b", "n", r"\alpha", r"\theta", r"\lambda", "t"]


class Fuzzer:
    def __init__(self, seed):
        self.r = random.Random(seed)

    def tree(self, depth):
        r = self.r
        if depth <= 0 or r.random() < 0.25:
            return ("num", r.choice([1, 2, 3, 5, 10])) if r.random() < 0.3 else ("var", r.choice(_FUZZ_VARS))
        op = r.choice(["+", "-", "*", "*", "/", "/", "^", "exp", "log", "ln", "sin", "cos", "sqrt",
                       "neg", "fact", "abs"])
        if op in ("+", "-", "*", "/"):
            return (op, self.tree(depth - 1), self.tree(depth - 1))
        if op == "^":
            e = ("num", r.choice([2, 3])) if r.random() < 0.6 else self.tree(depth - 2)
            return ("^", self.tree(depth - 1), e)
        if op == "fact":
            return ("fact", ("var", r.choice(_FUZZ_VARS)) if r.random() < 0.6 else
                    ("/", ("var", r.choice(_FUZZ_VARS)), ("var", r.choice(_FUZZ_VARS))))
        return (op, self.tree(depth - 1))

    # -- rendering ------------------------------------------------------
    def paren(self, s):
        return self.r.choice(["(" + s + ")", r"\left(" + s + r"\right)", r"\bigl(" + s + r"\bigr)",
                              r"\Big(" + s + r"\Big)"])

    def brace(self, s):
        return "{" + s + "}" if self.r.random() < 0.2 else s

    def sp(self):
        return self.r.choice(["", "", "", " ", r"\,", r"\;", r"\!", r"\ ", "~"])

    def render(self, t, ctx_prec=0):
        """ctx_prec: 0 top, 1 additive operand, 2 multiplicative operand,
        3 power base / function argument."""
        r = self.r
        k = t[0]
        if k == "num":
            return str(t[1])
        if k == "var":
            if r.random() < 0.15:                 # subscripted symbols: x_1, x_{\alpha}, a_{n+1}
                sub = r.choice(["1", "{1}", "{2}", r"{\alpha}", "{n+1}", "i", "{k}"])
                return t[1] + "_" + sub
            return t[1]
        if k in ("+", "-"):
            right = self.render(t[2], 2 if k == "-" else 1)
            s = self.render(t[1], 1) + " " + k + self.sp() + " " + right
            return self.paren(s) if ctx_prec >= 2 else self.brace(s)
        if k == "*":
            mul = r.choice([r" \cdot ", r" \times ", " ", ""])
            left, right = self.render(t[1], 2), self.render(t[2], 2 if mul.strip() else 3)
            if mul == "" and (re.search(r"\\[A-Za-z]+$", left) or re.match(r"\d", right)):
                mul = " "                          # \alpha x must keep its space; x 2 is not x2
            s = left + mul + right
            return self.paren(s) if ctx_prec >= 3 or (ctx_prec == 2 and not mul.strip()) else s
        if k == "/":
            style = r.choice([r"\frac", r"\dfrac", r"\tfrac", "/"])
            if style == "/":
                s = self.render(t[1], 2) + " / " + self.render(t[2], 3)
                return self.paren(s) if ctx_prec >= 2 else s
            s = style + "{" + self.render(t[1]) + "}{" + self.render(t[2]) + "}"
            return self.paren(s) if ctx_prec >= 3 and r.random() < 0.5 else s
        if k == "^":
            base = self.render(t[1], 3)
            if t[1][0] == "/" and base.startswith("\\") and r.random() < 0.5:
                pass                      # \frac{a}{b}^2: TeX reads it as (a/b)^2
            elif t[1][0] not in ("num", "var"):
                base = self.paren(base) if not base.startswith(("(", r"\left", r"\big", r"\Big")) else base
            ex = self.render(t[2])
            ex = ex if len(ex) == 1 and r.random() < 0.5 else "{" + ex + "}"
            return base + "^" + ex
        if k == "neg":
            s = "-" + self.render(t[1], 2)
            return self.paren(s) if ctx_prec >= 1 else s
        if k == "fact":
            if t[1][0] == "/":
                return r"\frac{" + self.render(t[1][1]) + "}{" + self.render(t[1][2]) + "}!"
            return self.render(t[1], 3) + "!"
        if k == "abs":
            a = self.render(t[1])
            return r.choice(["|" + a + "|", r"\left|" + a + r"\right|", r"\lvert " + a + r"\rvert "])
        if k == "exp":
            a = self.render(t[1])
            return r.choice([r"\exp(" + a + ")", r"\exp\left(" + a + r"\right)", "e^{" + a + "}"]) \
                if ctx_prec < 3 else self.paren(r"\exp(" + a + ")")
        if k == "sqrt":
            return r.choice([r"\sqrt{" + self.render(t[1]) + "}", r"\sqrt[3]{" + self.render(t[1]) + "}"])
        # log, ln, sin, cos
        a = self.paren(self.render(t[1]))
        cmd = {"log": r.choice([r"\log", r"\log_{2}", r"\log_2"]), "ln": r"\ln",
               "sin": r"\sin", "cos": r"\cos"}[k]
        s = cmd + a
        return self.paren(s) if ctx_prec >= 3 else s

    def relation_sym(self, direction):
        r = self.r
        return r.choice({"ge": [r"\geq", r"\ge", r"\geqslant"], "gt": [">", r"\gg"],
                         "le": [r"\leq", r"\le", r"\leqslant"], "lt": ["<", r"\ll"],
                         "eq": ["="], "ne": [r"\neq", r"\ne"]}[direction])

    def formula(self):
        r = self.r
        kind = r.random()
        depth = r.choice([1, 2, 2, 3, 3, 4])
        if kind < 0.3:
            body = self.render(self.tree(depth))
        elif kind < 0.75:
            n = 1 if r.random() < 0.7 else 2
            parts = [self.render(self.tree(depth))]
            for _ in range(n):
                rel = self.relation_sym(r.choice(["ge", "gt", "le", "lt", "eq", "ne"]))
                if r.random() < 0.08:
                    rel = r"\overset{(a)}{" + rel + "}"
                parts += [" " + rel + " ", self.render(self.tree(depth))]
            body = "".join(parts)
            if r.random() < 0.12:
                body += r.choice([r" \text{ for } ", r" \textnormal{ for } ", r", \quad ",
                                  r" \quad\text{if } ", r" \mbox{ for all } "]) + \
                        self.render(self.tree(1)) + (r" \geq 0" if r.random() < 0.5 else "")
            if r.random() < 0.05:
                body += r.choice([r" \textit{ a.e.}", r"\text{ a.s.}"])
            if r.random() < 0.1:
                body += r.choice([".", ","])
        else:  # aligned rows
            rows = []
            lhs = self.render(self.tree(depth))
            for i in range(r.choice([2, 3])):
                rel = self.relation_sym(r.choice(["ge", "le", "eq", "gt"]))
                rhs = self.render(self.tree(depth))
                rows.append((lhs if i == 0 else "") + " &" + rel + " " + rhs)
                if r.random() < 0.15:                 # the right side continues on the next row
                    rows.append(r"&\quad + " + self.render(self.tree(1), 1))
                if r.random() < 0.3:
                    lhs = self.render(self.tree(depth))
                    rows[-1] += r"\\ " + lhs + " &= " + self.render(self.tree(depth))
            sep = r.choice([r" \\ ", r"\\", r" \\[2pt] ", r"\\" + "\n"])
            env = r.choice(["align*", "align", "eqnarray*", "alignat*"])
            arg = "{2}" if env == "alignat*" else ""
            return rf"\begin{{{env}}}{arg}" + sep.join(rows) + rf"\end{{{env}}}"
        o, c = r.choice([("$", "$"), ("$$", "$$"), (r"\[", r"\]"),
                         (r"\begin{equation*}", r"\end{equation*}"),
                         (r"\begin{equation}", r"\end{equation}")])
        return o + body + c


def fuzz_formulas(n: int, seed: int):
    f = Fuzzer(seed)
    return [f.formula() for _ in range(n)]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _serve(conn):
    while True:
        job = conn.recv()
        if job is None:
            return
        conn.send(_worker(job))


def run(jobs, workers, hard_timeout: float = 60.0):
    """Check every job in `workers` processes. A formula that runs past
    `hard_timeout` (e.g. SymPy expanding 10^{10^{10}} exactly, in C, where
    SIGALRM cannot interrupt it) has its worker killed and replaced, and is
    recorded as skipped ('timeout (worker killed)')."""
    if workers <= 1:
        return [_worker(j) for j in jobs]
    import multiprocessing as mp
    import time
    from multiprocessing.connection import wait
    ctx = mp.get_context("fork")

    def spawn():
        a, b = ctx.Pipe()
        p = ctx.Process(target=_serve, args=(b,), daemon=True)
        p.start()
        return {"proc": p, "conn": a, "job": None, "t": 0.0}

    pool = [spawn() for _ in range(workers)]
    results, todo = [None] * len(jobs), list(enumerate(jobs))[::-1]
    pending = 0
    while todo or pending:
        for w in pool:
            if w["job"] is None and todo:
                w["job"], w["t"] = todo.pop(), time.time()
                w["conn"].send(w["job"][1])
                pending += 1
        busy = [w["conn"] for w in pool if w["job"] is not None]
        for c in wait(busy, timeout=1.0):
            w = next(w for w in pool if w["conn"] is c)
            results[w["job"][0]] = c.recv()
            w["job"] = None
            pending -= 1
        now = time.time()
        for k, w in enumerate(pool):
            if w["job"] is not None and now - w["t"] > hard_timeout:
                formula, _, source = w["job"][1]
                results[w["job"][0]] = {"formula": formula, "status": "skip", "drift": False,
                                        "reason": "timeout (worker killed)", "source": source}
                w["proc"].kill()
                pool[k] = spawn()
                pending -= 1
    for w in pool:
        try:
            w["conn"].send(None)
        except (BrokenPipeError, OSError):
            pass
        w["proc"].join(timeout=5)
    return results


def summarise(label, results, occurrences=None):
    n = len(results)
    status = Counter(r["status"] for r in results)
    reasons = Counter(r["reason"] for r in results if r["status"] == "skip")
    coarse = Counter(re.sub(r"^(canonical: )?(unsupported command|unsupported character).*",
                            r"\1\2", r["reason"]) for r in results if r["status"] == "skip")
    cmds = Counter(r["reason"].split()[-1] for r in results
                   if r["status"] == "skip" and "unsupported command" in r["reason"])
    viol = [r for r in results if r["status"] == "violation"]
    by_phase = Counter(re.sub(r" \(stages.*", "", r["phase"]) for r in viol)
    by_class = Counter(r.get("bug_class", "?") for r in viol)
    drift = sum(1 for r in results if r.get("drift"))
    vscript = [r for r in results if r.get("unbraced_v_script")]
    pieces = sum(r.get("pieces_checked", 0) for r in results)
    s = {"label": label, "unique_formulas": n, "occurrences": occurrences,
         "checked_ok": status["ok"], "violations": status["violation"], "skipped": status["skip"],
         "pieces_checked": pieces, "skip_reasons": dict(coarse.most_common()),
         "skip_reasons_detail": dict(reasons.most_common(40)),
         "top_unsupported_commands": dict(cmds.most_common(25)),
         "violations_by_phase": dict(by_phase.most_common()), "replay_drift": drift,
         "violations_by_class": dict(by_class.most_common()),
         "class_examples": {c: [(r["formula"][:200], r["canonical"][:200], r["violation"].get("point"))
                                for r in viol if r.get("bug_class") == c][:3] for c in by_class},
         "unbraced_v_script": len(vscript),
         "unbraced_v_script_examples": [(r["formula"][:150], r["canonical"][:150]) for r in vscript[:10]]}
    print(f"\n=== {label} ===")
    if occurrences is not None:
        print(f"formula occurrences collected: {occurrences}")
    print(f"unique formulas: {n}  checked OK: {status['ok']}  VIOLATIONS: {status['violation']}  "
          f"skipped: {status['skip']}  (formula pieces compared: {pieces})")
    print(f"replay drift (phase list != core pipeline): {drift}")
    print(f"canonical forms with an unbraced V_k script (x^{{y}} -> V1^V2, TeX reads V1^{{V}}2): "
          f"{len(vscript)}" + (f", e.g. {vscript[0]['formula'][:60]!r} -> {vscript[0]['canonical'][:60]!r}"
                               if vscript else ""))
    print("skipped, by reason:")
    for k, v in coarse.most_common():
        print(f"  {v:7d}  {k}")
    if cmds:
        print("  most common unsupported commands: " +
              ", ".join(f"{k} ({v})" for k, v in cmds.most_common(12)))
    print("violations by phase:")
    for k, v in by_phase.most_common():
        print(f"  {v:7d}  {k}")
    print("violations by root cause (heuristic label):")
    for k, v in by_class.most_common():
        print(f"  {v:7d}  {k}")
    for ph in by_phase:
        ex = [r for r in viol if r["phase"].startswith(ph)][:3]
        print(f"  -- {ph}:")
        for r in ex:
            v = r["violation"]
            print(f"     {r['formula'][:110]!r}")
            print(f"       -> {r['canonical'][:110]!r}  [{v['kind']}] "
                  f"point={v.get('point')} orig={v.get('orig_value')} canon={v.get('canon_value')}"
                  f"{' ' + v['detail'] if 'detail' in v else ''}"[:400])
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--limit-papers", type=int, default=None)
    ap.add_argument("--no-corpus", action="store_true")
    ap.add_argument("--n-fuzz", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    report = {"summaries": [], "violations": [], "drift": []}
    if not args.no_corpus:
        files, occ = collect_corpus(args.corpus, args.limit_papers)
        first_src = {}
        for seg, src in occ:
            first_src.setdefault(seg, src)
        jobs = [(seg, i, src) for i, (seg, src) in enumerate(first_src.items())]
        print(f"corpus: {len(files)} papers, {len(occ)} math segments, {len(jobs)} unique")
        res = run(jobs, args.workers)
        report["summaries"].append(summarise(f"corpus ({len(files)} papers)", res, len(occ)))
        report["violations"] += [r for r in res if r["status"] == "violation"]
        report["drift"] += [r for r in res if r.get("drift")][:200]
    if args.n_fuzz:
        fz = fuzz_formulas(args.n_fuzz, args.seed)
        res = run([(f, i, "fuzz") for i, f in enumerate(fz)], args.workers)
        report["summaries"].append(summarise(f"fuzz (n={args.n_fuzz}, seed={args.seed})", res))
        report["violations"] += [r for r in res if r["status"] == "violation"]
        report["drift"] += [r for r in res if r.get("drift")][:200]

    for r in report["violations"]:
        r.pop("piece_skips", None)
        r.setdefault("paper", r.get("source"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(f"\nJSON report: {args.out}  ({len(report['violations'])} violations)")
    return report


if __name__ == "__main__":
    main()
