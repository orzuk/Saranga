"""LaTeX macro expansion and normalisation — shared, not visualisation-specific.

Papers define their own commands (`\\newcommand{\\Sc}{\\mathcal{S}}`), and the
corpus stores every statement as a VERBATIM span of the source, so those macros
survive into `statement`. Any consumer that has to interpret the text rather
than just store it — a renderer, a cross-paper matcher, a search index — needs
to resolve them first. Each paper's glossary is already on disk as
`metadata.macros` (`{name: {expansion, kind, arity}}`), written by
`scripts/build_macro_glossary.py` and merged in by `scripts/merge_macros.py`.

WHEN TO EXPAND — AND WHEN NOT TO
--------------------------------
Expansion is a DISPLAY/ANALYSIS-time operation, never a storage one. E143 in
the v6 register measured 341 colliding expansions and 473 colliding names
across the corpus: `\\e` means `\\begin{equation}`, `\\epsilon`, `\\eta` and
`\\mathbb{E}` in different papers, and `\\mathcal{C}` is written `Casimir` in
one paper and `Cir` in another. Expanding into the stored corpus would assert
that a Casimir element is a circle, and would break the verbatim audit.

So: expand a COPY, at the point of use.

  rendering        yes — matplotlib mathtext cannot know a paper's macros
  cross-paper text yes, but per-paper: expand each side with ITS OWN glossary
                   before comparing, never with a merged one
  storage          no

Revised 2026-10-08 (v6): extraction now runs on a PREPARED source
(latex_facts.prepare_source) in which each paper's own argument-free macros,
operators and \\ref wrappers are expanded with that paper's definitions, so the
stored statements contain `\\Gamma`, not the author's `\\gr`. That is per-paper
expansion, which the note above allows; the collision it warns about comes
from expanding with ANOTHER paper's glossary. What expansion drops is the hint
a macro's NAME carries (`\\Casimir`), which the glossary in `metadata.macros`
keeps. The verbatim audit checks statements against the prepared source.
Macros with arguments are still not expanded in storage.

Comparison is the subtle case. `\\Sc` in paper A and `\\Sc` in paper B may be
different objects; expanding each with its own glossary is what makes the two
texts commensurable. That is why this lives here rather than inside
`visualize_annotation.py`.
"""
from __future__ import annotations

import re

__all__ = ["expand_macros", "brace_normalize", "unwrap_transparent",
           "resolve_references", "strip_text_environments",
           "resolve_text_fonts",
           "strip_dimension_commands", "normalize_for_mathtext"]

# Math-font commands take exactly one argument. TeX lets you omit the braces
# and grabs the next single token, so `{\mathbb R}` == `\mathbb{R}` — valid
# LaTeX that matplotlib's mathtext rejects.
_FONT_CMDS = ("mathbb", "mathcal", "mathrm", "mathbf", "mathfrak", "mathsf",
              "mathtt", "mathit", "mathscr", "boldsymbol", "operatorname")

# The argument may be a single character (`\\mathbb R`) or another control
# sequence (`{\\mathbf \\H}`, where \\H is itself a paper macro).
#
# The two cases need DIFFERENT space rules. A control-sequence argument needs no
# separator at all — `\\mathbb\\A` is unambiguous, since `\\mathbb` ends at the
# `\\`. A single-character argument does: `\\mathbbR` is one control word named
# "mathbbR", not `\\mathbb` applied to `R`.
#
# Getting this wrong is not cosmetic. `\\mathbb\\A` with `\\A -> Alpha` must
# brace to `\\mathbb{\\A}` BEFORE expansion, giving `\\mathbb{Alpha}`. Requiring
# a space here meant it stayed unbraced, expanded to `\\mathbb Alpha`, and the
# final brace pass then grabbed one letter — `\\mathbb{A}lpha`.
_UNBRACED = re.compile(r"\\(%s)(?:\s*(\\[A-Za-z]+)|\s+([A-Za-z0-9]))"
                       % "|".join(_FONT_CMDS))

_MAX_DEPTH = 8          # nested macro definitions; also breaks \a -> \b -> \a

# Loops that rewrite ONE occurrence per pass need an occurrence bound, not a
# nesting bound. They were sharing _MAX_DEPTH, so a statement with more than 8
# `\ensuremath{}` wrappers kept the 9th onward verbatim — 180 strings across 55
# papers. Each pass strictly removes one command, so this terminates; the cap is
# only a runaway guard.
_MAX_PASSES = 2000

# Text ending in a control word, e.g. the `\in` of `\in\xmo`. See _splice.
_CS_TAIL = re.compile(r"\\[A-Za-z]+$")


def _splice(prefix, repl, suffix):
    """Concatenate three fragments, restoring the token boundary TeX implies.

    EVERY textual substitution in this module can weld a replacement onto the
    control word in front of it, because TeX ends a control word at the `\\` or
    `{` that a string-level splice removes:

        `\\geq\\underline{C}`  --unwrap-->  `\\geqC`     (an unknown command)
        `\\in\\xmo`            --expand-->  `\\inX...`   (likewise)

    The result renders as the literal text "geqC" or "inX". Every splice site
    goes through here rather than `+`, so the class is fixed once instead of
    per call site — the expander was fixed on its own first, and the identical
    bug then surfaced in the unwrapper.
    """
    if repl[:1].isalnum() and _CS_TAIL.search(prefix):
        return prefix + " " + repl + suffix
    return prefix + repl + suffix


def brace_normalize(text):
    """`\\mathbb R` -> `\\mathbb{R}`, for the one-token-argument idiom.

    91 of the 200 v5.1 silver papers use the unbraced form (4953 occurrences);
    some use it exclusively. Both render identically in TeX, so this is a
    normalisation, not a correction.
    """
    if not text:
        return text
    return _UNBRACED.sub(
        lambda m: "\\%s{%s}" % (m.group(1), m.group(2) or m.group(3)), str(text))


# Wrappers that carry no mathematical meaning: they exist to control MODE or
# spacing in real LaTeX. Macro expansions are full of them (`\integerset` ->
# `\ensuremath{\mathbb{N}}`), and mathtext does not implement them, so a
# perfectly-resolved macro can still fail to render. Unwrapping keeps the
# argument and drops the shell.
_TRANSPARENT = ("ensuremath", "mbox", "hbox", "underline", "norm", "abs")
_TRANSPARENT_RE = re.compile(r"\\(%s)\s*\{" % "|".join(_TRANSPARENT))


def unwrap_transparent(text, max_depth=_MAX_PASSES):
    """`\\ensuremath{X}` -> `X`, `\\mbox{X}` -> `X`, nested included."""
    if not text:
        return text
    text = str(text)
    for _ in range(max_depth):
        m = _TRANSPARENT_RE.search(text)
        if not m:
            break
        arg, end = _read_group(text, m.end() - 1)
        text = _splice(text[:m.start()], arg, text[end:])
    return text


# Text-mode FONT SELECTORS. Unlike the wrappers above these do carry meaning —
# `\textsf{Push}` names an operation and `\textbf{X}` a distinguished object — so
# they get mapped rather than dropped. 6046 occurrences across the corpus, led by
# \emph (1753), \textbf (944) and \textit (582).
#
# The right answer depends on mode. Inside `$...$` there is an exact equivalent
# (\textsf -> \mathsf); outside, neither mathtext nor the panel can switch font
# mid-string, so the content is kept and the wrapper dropped. Leaving them alone
# was the bug: `\textsf{Push}{}` reached the reader verbatim.
_FONT_MAP = {
    "textbf": "mathbf", "bf": "mathbf",
    "textit": "mathit", "emph": "mathit", "it": "mathit",
    "texttt": "mathtt", "tt": "mathtt",
    "textsf": "mathsf", "sf": "mathsf",
    "textsc": "mathrm", "textrm": "mathrm", "textnormal": "mathrm",
    "rm": "mathrm", "sc": "mathrm", "sl": "mathit", "em": "mathit",
    # Declaration names occasionally used WITH braces (`\normalfont{x}`),
    # which _FONT_DECL deliberately skips via its (?!\s*\{) guard.
    "normalfont": "mathrm", "rmfamily": "mathrm", "upshape": "mathrm",
    "mdseries": "mathrm", "bfseries": "mathbf", "itshape": "mathit",
    "slshape": "mathit", "scshape": "mathrm", "ttfamily": "mathtt",
    "sffamily": "mathsf",
    "textup": "mathrm", "text": "mathrm", "uppercase": "mathrm",
}
_FONT_RE = re.compile(r"\\(%s)\s*\{" % "|".join(sorted(_FONT_MAP, key=len,
                                                       reverse=True)))
# `\textcolor{red}{X}` — two arguments; the colour is presentational, X is not.
_TEXTCOLOR_RE = re.compile(r"\\(?:textcolor|colorbox|fcolorbox)\s*\{")
# Argument-less mode switches. No braces to key on, so they need deleting
# outright; mathtext and MathJax both reject them.
_STYLE_SWITCH = re.compile(
    r"\\(?:text|display|script|scriptscript)style\b|\\(?:small|foot"
    r"notesize|large|Large|LARGE|huge|Huge|normalsize|tiny|scriptsize)\b")
# Old-style font DECLARATIONS: `{\em point-to-point shortest path (PPSP)}`,
# `{\bf x}`. These take no argument of their own — they switch font for the rest
# of the enclosing group — so the `\textbf{...}` handling above never matches
# them and the bare command survived into the output. Dropping the command
# keeps the group's text, which is the readable outcome in both modes.
#
# `(?![A-Za-z])` is load-bearing: without it `\it` would match inside `\item`.
# Longer names first so `\rmfamily` is not consumed as `\rm` + `family`.
_FONT_DECL = re.compile(
    r"\\(?:normalfont|bfseries|mdseries|itshape|slshape|scshape|upshape|"
    r"rmfamily|sffamily|ttfamily|em|it|bf|rm|sf|tt|sc|sl)(?![A-Za-z])(?!\s*\{)")
_FONT_DECL_GROUP = re.compile(
    r"\{\s*\\(?:normalfont|bfseries|mdseries|itshape|slshape|scshape|upshape|"
    r"rmfamily|sffamily|ttfamily|em|it|bf|rm|sf|tt|sc|sl)(?![A-Za-z])")
# Control space `\ `, italic correction `\/`, discretionary hyphen `\-`.
# `(resp.\ $w$)` is the common shape; the backslash reached the reader.
# `(?<!\\)` is essential: without it this matches the SECOND backslash of a row
# break `\\ `, rewriting it to `\ ` — i.e. the rule manufactures the very leak
# it exists to remove. That produced 4504 hits across 183 papers.
_CONTROL_SPACE = re.compile(r"(?<!\\)\\[ \t]")
_ZERO_WIDTH = re.compile(r"\\[/-]|\\hfill\b|\\noindent\b|\\linebreak\b|\\newline\b")
# `{}` is two different things. After a control word it is the standard idiom
# for ENDING that word — `\cap{}A_h` means `\cap` then `A_h` — so deleting it
# welds them into `\capA_h`, the same token-boundary failure as _splice. Only a
# standalone `{}` (e.g. what `\textsf{Push}{}` leaves behind) is noise.
_EMPTY_GROUP = re.compile(r"(\\[A-Za-z]+)?\{\s*\}")


def resolve_text_fonts(text, max_depth=_MAX_PASSES):
    """`\\textsf{Push}` -> `\\mathsf{Push}` in math, `Push` in text."""
    if not text:
        return text
    t = str(text)
    for _ in range(max_depth):
        m = _TEXTCOLOR_RE.search(t)
        if not m:
            break
        _colour, j = _read_group(t, m.end() - 1)     # discard the colour
        body, end = _read_group(t, j)
        t = _splice(t[:m.start()], body, t[end:])
    for _ in range(max_depth):
        m = _FONT_RE.search(t)
        if not m:
            break
        body, end = _read_group(t, m.end() - 1)
        if _in_math(t, m.start()):
            repl = "\\%s{%s}" % (_FONT_MAP[m.group(1)], body)
        else:
            repl = body
        t = _splice(t[:m.start()], repl, t[end:])
    # `{\em foo}` — the braces exist ONLY to scope the declaration, so they go
    # with it. Dropping just the command leaves `{ foo}`, and outside math a
    # brace is a literal character the reader would see.
    for _ in range(max_depth):
        m = _FONT_DECL_GROUP.search(t)
        if not m:
            break
        body, end = _read_group(t, m.start())
        t = _splice(t[:m.start()],
                    _FONT_DECL.sub("", body, count=1).strip(), t[end:])
    t = _FONT_DECL.sub("", t)
    t = _CONTROL_SPACE.sub(" ", t)
    t = _ZERO_WIDTH.sub("", t)
    t = _STYLE_SWITCH.sub("", t)
    return _EMPTY_GROUP.sub(
        lambda m: (m.group(1) + " ") if m.group(1) else "", t)


def _read_group(s, i):
    """Read one macro argument starting at s[i]. Returns (arg, next_index).

    Handles `{...}` with nesting, and the bare-token form TeX allows.
    """
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s):
        return "", i
    if s[i] != "{":
        # bare token: a control sequence counts as one token, else one char
        if s[i] == "\\":
            m = re.match(r"\\[A-Za-z]+", s[i:])
            if m:
                return m.group(0), i + m.end()
        return s[i], i + 1
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{" and (j == i or s[j - 1] != "\\"):
            depth += 1
        elif s[j] == "}" and s[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)          # unbalanced; take the rest


def _substitute(expansion, args):
    """Fill `#1`, `#2`, ... in a macro body."""
    out = expansion
    for k, a in enumerate(args, 1):
        out = out.replace("#%d" % k, a)
    return out


def expand_macros(text, macros, max_depth=_MAX_DEPTH):
    """Expand a paper's own macros in `text`.

    `macros` is the paper's `metadata.macros`: `{name: {"expansion": str,
    "arity": int, ...}}`. Names are stored WITHOUT the leading backslash.

    Longest name first, so `\\Sc` never eats the prefix of `\\Scale`. Repeats
    until stable or `max_depth`, which also bounds mutually recursive
    definitions rather than hanging on them. Unknown commands are left alone —
    this resolves what the paper defined, it does not invent anything.
    """
    if not text or not macros:
        return text
    text = str(text)
    names = sorted(macros, key=len, reverse=True)
    if not names:
        return text
    pattern = re.compile(r"\\(%s)(?![A-Za-z])"
                         % "|".join(re.escape(n) for n in names))

    for _ in range(max_depth):
        out, i, changed = [], 0, False
        tail = ""                      # last few chars already emitted
        while True:
            m = pattern.search(text, i)
            if not m:
                out.append(text[i:])
                break
            seg = text[i:m.start()]
            out.append(seg)
            if seg:
                tail = seg[-16:]
            spec = macros[m.group(1)] or {}
            body = spec.get("expansion", "") if isinstance(spec, dict) else str(spec)
            arity = int(spec.get("arity", 0)) if isinstance(spec, dict) else 0
            j = m.end()
            args = []
            # LaTeX's optional first argument. `\newcommand{\limGs}[1][G]{...}`
            # declares arity 1, but bare `\limGs` supplies NOTHING and falls
            # back to `G`; only `\limGs[H]` overrides it. Treating that argument
            # as mandatory made the expander read the next token instead — for
            # `$x\in\limGs$` that is the closing `$`, which both broke math mode
            # and produced an unbalanced brace.
            opt_default = (spec.get("optional_default")
                           if isinstance(spec, dict) else None)
            n_mandatory = arity
            if opt_default is not None:
                k = j
                while k < len(text) and text[k].isspace():
                    k += 1
                if k < len(text) and text[k] == "[":
                    end = text.find("]", k)
                    if end != -1:
                        args.append(text[k + 1:end])
                        j = end + 1
                    else:
                        args.append(opt_default)
                else:
                    args.append(opt_default)
                n_mandatory = max(0, arity - 1)
            for _a in range(n_mandatory):
                arg, j = _read_group(text, j)
                args.append(arg)
            sub = _substitute(body, args)
            # TeX tokenises `\in\xmo` as TWO control words, so expanding
            # `\xmo` -> `X^{-\omega}` must not glue them into `\inX^{-\omega}`:
            # `\inX` is an unknown command and renders as the literal text
            # "inX". Restore the boundary the tokeniser implied.
            if sub[:1].isalnum() and _CS_TAIL.search(tail):
                out.append(" ")          # same rule as _splice; see there
            out.append(sub)
            if sub:
                tail = sub[-16:]
            i = j
            changed = True
        text = "".join(out)
        if not changed:
            break
    return text


# Spacing commands that take a dimension rather than a braced argument.
# `\\kern-1pt` and friends are invisible in output but fatal to mathtext.
_DIMEN_CMD = re.compile(r"\\(?:kern|hskip|vskip|hspace\*?|vspace\*?)\s*"
                        r"(?:\{[^}]*\}|-?[\d.]+\s*(?:pt|em|ex|mm|cm|in|bp|sp))?")


def strip_dimension_commands(text):
    """Drop `\\kern-1pt`-style spacing; it carries no meaning for a reader."""
    return _DIMEN_CMD.sub("", str(text)) if text else text


# ---------------------------------------------------------------------------
# Cross-references
# ---------------------------------------------------------------------------
# Statements are verbatim spans, so they keep the paper's `\ref`/`\cite` — 26102
# of them across the 200 v5.1 papers (`\cite` in 191 of them, `\ref` in 187).
# The bibliography and the \label definitions live in parts of the .tex we never
# extracted, so nothing downstream can resolve them: MathJax renders an
# undefined \ref or \eqref as the literal string `???`, and mathtext just draws
# the command name.
#
# The key is the only information actually present, and it usually carries the
# meaning anyway (`thm:main`, `eq:bound`, `Knuth77`), so surface it and mark it
# as a reference rather than dropping it — dropping would silently delete the
# fact that the sentence pointed somewhere.
_CITE_CMDS = ("cite", "citep", "citet", "citeauthor", "citeyear", "citealp",
              "citealt", "cites", "nocite", "fullcite", "textcite", "parencite")
_REF_CMDS = ("eqref", "cref", "Cref", "autoref", "pageref", "vref", "ref")
# `\cite[p.~5]{a,b}` — one or two optional args, then the mandatory key list.
_CITE_RE = re.compile(r"\\(?:%s)\*?\s*(?:\[[^\]]*\]){0,2}\s*\{([^}]*)\}"
                      % "|".join(_CITE_CMDS))
# `ref` last in the alternation so `\eqref` is never matched as `\e`+`ref`; the
# (?![A-Za-z]) guard stops `\reflect` being read as `\ref`.
_REF_RE = re.compile(r"\\(?:%s)(?![A-Za-z])\*?\s*\{([^}]*)\}"
                     % "|".join(_REF_CMDS))
_LABEL_RE = re.compile(r"\\label\s*\{[^}]*\}")
# LaTeX's non-breaking space. Both mathtext and MathJax draw it as a literal
# `~`, and `Knuth~[Knuth77]` is the common shape once citations resolve, so
# normalise it to a plain space. `\~` (the tilde accent) is left alone.
_NBSP = re.compile(r"(?<!\\)~")


_UNESCAPED_DOLLAR = re.compile(r"(?<!\\)\$")


def _in_math(text, pos):
    """Is offset `pos` inside a `$...$` span? (odd number of `$` before it)"""
    return len(_UNESCAPED_DOLLAR.findall(text, 0, pos)) % 2 == 1


def _safe_key(k, in_math):
    """Escape `_` ONLY in math mode.

    Inside `$...$` a bare `_` is a subscript (two of them raise "double
    subscript"), so it must be escaped. In ordinary text it needs nothing, and
    escaping anyway is what turned `mult_n_self_sim` into the very noisy
    `mult\\_n\\_self\\_sim` on screen. References are overwhelmingly in text.
    """
    k = k.strip()
    return k.replace("_", r"\_") if in_math else k


def _fmt_keys(m, open_c, close_c, whole):
    in_math = _in_math(whole, m.start())
    keys = [_safe_key(k, in_math) for k in m.group(1).split(",") if k.strip()]
    return "%s%s%s" % (open_c, ", ".join(keys), close_c) if keys else ""


# ---------------------------------------------------------------------------
# LaTeX environments
# ---------------------------------------------------------------------------
# A statement span often carries the environment it was cut from, so the text
# still contains `\begin{lemma}`, `\begin{proof}`, `\begin{itemize}`. MathJax's
# TeX input implements only MATH environments and reports anything else as
# "unknown environment 'lemma'" right in the panel. Measured over the 200 v5.1
# papers: 1889 occurrences of 64 distinct non-math environments.
#
# Listing all 64 would rot, so invert it — name the environments that must
# SURVIVE (math, handled downstream) and the ones worth replacing wholesale
# (diagrams and floats, whose content is not readable text), then unwrap
# everything else. A new environment in some future paper is unwrapped by
# default, which is the safe outcome.
_MATH_ENVS = {
    "equation", "align", "eqnarray", "gather", "multline",
    "split", "aligned", "gathered", "array", "matrix", "pmatrix", "bmatrix",
    "Bmatrix", "vmatrix", "Vmatrix", "cases", "numcases", "smallmatrix",
    "flalign", "alignat", "subarray",
}
_MATH_ENVS |= {e + "*" for e in _MATH_ENVS}

# LaTeX2e primitives that MathJax does NOT define, so leaving them intact would
# produce the same "unknown environment" error as \begin{lemma}. `displaymath`
# is just `\[..\]`, so re-delimit it; `subequations` is a numbering wrapper, so
# unwrapping it (the default) leaves the real equations inside untouched.
_INLINE_MATH_ENVS = {"displaymath", "math"}

# Content is graphics or tabular layout: unwrapping would dump coordinate soup
# into the panel, so collapse the whole block to a marker instead.
_OPAQUE_ENVS = {
    "tikzcd": "diagram", "tikzpicture": "diagram", "xy": "diagram",
    "CD": "diagram", "ytableau": "diagram", "picture": "diagram",
    "pspicture": "diagram", "diagram": "diagram", "scope": "diagram",
    "tabular": "table", "tabularx": "table", "table": "table",
    "figure": "figure", "algorithmic": "algorithm", "algorithm": "algorithm",
}

_LIST_ENVS = {"itemize", "enumerate", "description", "compactitem",
              "compactenum", "enumroman", "rlist", "longlist", "inparaenum"}

# Innermost \begin{X}...\end{X}: no nested \begin of the SAME name inside.
_ENV_RE = re.compile(
    r"\\begin\{([A-Za-z*]+)\}\s*(?:\[[^\]]*\])?(?:\{[^}]*\})?"
    r"((?:(?!\\begin\{\1\}).)*?)"
    r"\\end\{\1\}", re.S)
_ITEM_RE = re.compile(r"\\item\s*(?:\[[^\]]*\])?\s*")
_ORPHAN_RE = re.compile(r"\\(?:begin|end)\{([A-Za-z*]+)\}\s*(?:\[[^\]]*\])?")


def strip_text_environments(text, max_depth=_MAX_DEPTH):
    """Unwrap non-math LaTeX environments; MathJax only understands math ones."""
    if not text or "\\begin{" not in text:
        return text
    t = str(text)

    def _sub(m):
        name, body = m.group(1), m.group(2)
        if name in _MATH_ENVS:
            return m.group(0)                       # leave for the math path
        if name in _INLINE_MATH_ENVS:
            return " $%s$ " % body.strip()
        base = _OPAQUE_ENVS.get(name)
        if base:
            return " [%s] " % base
        if name in _LIST_ENVS:
            return " " + _ITEM_RE.sub(" • ", body).strip() + " "
        return " " + body.strip() + " "             # plain wrapper: keep content

    for _ in range(max_depth):                      # inside-out for nesting
        new = _ENV_RE.sub(_sub, t)
        if new == t:
            break
        t = new

    # Orphans: a statement is a SPAN of the source, so it routinely opens an
    # environment whose \end fell outside the extracted range (or vice versa).
    # The paired rule above needs both halves, leaving ~216 unmatched markers
    # corpus-wide. Drop the bare marker and keep the text around it.
    t = _ORPHAN_RE.sub(lambda m: m.group(0) if m.group(1) in _MATH_ENVS else " ", t)
    return t


def resolve_references(text):
    """`\\cite{Knuth77}` -> `[Knuth77]`, `\\ref{thm:main}` -> `(thm:main)`.

    `\\label{...}` is dropped: it defines an anchor rather than pointing at one,
    so it has no reading value once the numbering is gone.
    """
    if not text:
        return text
    text = _LABEL_RE.sub("", str(text))
    text = _CITE_RE.sub(lambda m: _fmt_keys(m, "[", "]", text), text)
    text = _REF_RE.sub(lambda m: _fmt_keys(m, "(", ")", text), text)
    return text


def normalize_for_mathtext(text, macros=None):
    """Everything a matplotlib-mathtext consumer needs, in one call.

    ORDER MATTERS. TeX grabs the *unexpanded* token as a one-token argument,
    so `{\\mathbf \\H}` means `\\mathbf{\\H}` and only then does `\\H` expand.
    Expanding first turns it into `{\\mathbf \\ensuremath{\\mathrm{H}}}`, where
    brace-normalising grabs `\\ensuremath` alone and orphans its argument —
    producing `\\mathbf{\\mathrm}{H}`, which is not what the paper wrote.

    So: brace-normalise first (while macros are still single tokens), then
    expand, then unwrap, then brace-normalise again to catch unbraced forms
    that the expansions themselves introduced.

    References are resolved AFTER expansion, because papers hide them inside
    their own macros (`\\ifLongCites{\\cite{Knuth77}}{Knuth~\\cite{Knuth77}}`),
    and BEFORE the transparent-wrapper pass, since `\\cite` shows up inside
    `\\mbox{}` often enough to matter.
    """
    text = brace_normalize(text)
    text = expand_macros(text, macros or {})
    text = strip_text_environments(text)
    text = resolve_references(text)
    text = resolve_text_fonts(text)
    text = unwrap_transparent(text)
    text = strip_dimension_commands(text)
    text = _NBSP.sub(" ", text or "")
    return brace_normalize(text)


# ===========================================================================
# matplotlib-mathtext safety layer
# ===========================================================================
# Moved here from visualize_annotation.py. mathtext implements a SUBSET of TeX,
# so a string that is valid LaTeX still has to be rewritten before it can be
# drawn. That rewrite is not a rendering concern: scripts/audit_mathtext.py
# needs it to predict failures, and cross-paper comparison needs it to compare
# like with like. Keeping the tables in the renderer forced those callers to
# import visualize_annotation (and, with it, matplotlib figure machinery) just
# to reach a dict.
#
# visualize_annotation re-exports every name below, so existing references to
# _LATEX_FIXES / _sanitize_math keep working unchanged.

import re as _re  # noqa: E402  — the moved code uses this alias throughout

# ── Text helpers ────────────────────────────────────────────────────────────
# LaTeX commands not supported by matplotlib mathtext — replace with equivalents
# ONLY replace commands that matplotlib mathtext CANNOT render.
# Tested: \mathbb, \mathcal, \mathrm, \mathbf, \operatorname, \text,
# \boldsymbol, \triangleq, Greek letters, \nabla, \frac, \sum, \int,
# \prod, \log, \sim, \in, \leq, \geq, \forall, \exists ALL WORK.
_LATEX_FIXES = {
    # These FAIL in matplotlib and need replacement:
    r"\bm": r"\mathbf",                  # \bm not supported
    r"\lVert": r"\|", r"\rVert": r"\|",  # \lVert/\rVert not supported
    # \Vert AFTER \lVert/\rVert: this table is applied as literal str.replace
    # in insertion order, so those two must already be gone or `\lVert` would
    # match as `\l` + `Vert`.
    r"\Vert": r"\|", r"\vert": r"|",
    r"\coloneqq": r":=",                 # \coloneqq not supported
    r"\pmod": r"\mathrm{mod}",           # \pmod not supported
    r"\defeq": r":=",                    # \defeq (custom) → :=
    r"\eqdef": r":=",                    # \eqdef (custom) → :=
    # Common author-defined number-set shorthands (\R, \Z, \N, \Q, \C):
    r"\R": r"\mathbb{R}",
    r"\Z": r"\mathbb{Z}",
    r"\N": r"\mathbb{N}",
    r"\Q": r"\mathbb{Q}",
    r"\C": r"\mathbb{C}",
    # Common author shortcuts:
    r"\eps": r"\varepsilon",
    r"\hdots": r"\ldots",
    r"\dotsc": r"\ldots",
    r"\dotsb": r"\cdots",
    # Text-style commands matplotlib mathtext does NOT support
    # (it knows \text but not \textbf/\textit/\texttt/etc.):
    r"\textbf": r"\mathbf",
    r"\textit": r"\mathit",
    r"\texttt": r"\mathtt",
    r"\textsf": r"\mathsf",
    r"\textsc": r"\mathrm",
    r"\textnormal": r"\mathrm",
    r"\emph": r"\mathit",
    # ── Added 2026-08 from scripts/audit_mathtext.py, which parses every math
    # block in the corpus through mathtext in-process. Each replacement below
    # was checked: the left side genuinely fails, the right side genuinely
    # parses. \le / \ge alone accounted for 1253 rejected blocks across 22 of
    # the first 40 papers — mathtext knows \leq and \geq but not the short
    # forms, which is not obvious from any docs.
    # NOTE: \le / \ge are deliberately NOT here. _LATEX_FIXES is applied as
    # literal substring replacement, so a "\le" -> "\leq" entry rewrites an
    # existing "\leq" into "\leqq" and "\leqslant" into "\leqqslant".
    # _LATEX_REGEX_FIXES already handles them with a negative lookahead.
    r"\Bbb": r"\mathbb",                  # old AMS spelling of \mathbb
    r"\EuScript": r"\mathcal",
    r"\dvtx": r":",                       # AMS journal class colon
    r"\diagdown": r"\backslash",
    r"\varDelta": r"\Delta", r"\varGamma": r"\Gamma",
    r"\varSigma": r"\Sigma", r"\varOmega": r"\Omega",
    r"\varPhi": r"\Phi", r"\varLambda": r"\Lambda",
    # Sizing prefixes: mathtext has no \bigl family; plain delimiters render.
    r"\bigl": "", r"\bigr": "", r"\Bigl": "", r"\Bigr": "",
    r"\biggl": "", r"\biggr": "", r"\Biggl": "", r"\Biggr": "",
    r"\bigm": "", r"\Bigm": "",
    r"\limits": "", r"\nolimits": "",
    # Sizing delimiters — not supported standalone, replace with plain:
    r"\big|": "|", r"\Big|": "|", r"\bigg|": "|",
    r"\big(": "(", r"\Big(": "(", r"\big)": ")", r"\Big)": ")",
    r"\bigg(": "(", r"\Bigg(": "(", r"\bigg)": ")", r"\Bigg)": ")",
}

# Whitelist of LaTeX commands matplotlib mathtext supports natively. Any
# \command NOT in this set gets wrapped in \mathrm{...} as a graceful
# fallback so that rendering doesn't crash on author-defined macros.
# Keep this list LARGE enough to avoid false positives (which render as
# weird upright text); err toward inclusion.
_KNOWN_MATHTEXT_COMMANDS = frozenset({
    # Font/style — note: matplotlib mathtext supports \text{} but NOT
    # \textbf/\textit/\texttt/etc. Those map to \mathbf/\mathit/\mathtt
    # via the explicit _LATEX_FIXES table above.
    'mathbb', 'mathcal', 'mathrm', 'mathbf', 'mathit', 'mathsf', 'mathtt',
    'boldsymbol', 'bm', 'text', 'operatorname',
    # Greek lower:
    'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'varepsilon', 'zeta', 'eta',
    'theta', 'vartheta', 'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi',
    'pi', 'varpi', 'rho', 'varrho', 'sigma', 'varsigma', 'tau', 'upsilon',
    'phi', 'varphi', 'chi', 'psi', 'omega',
    # Greek upper:
    'Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta',
    'Theta', 'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi', 'Omicron',
    'Pi', 'Rho', 'Sigma', 'Tau', 'Upsilon', 'Phi', 'Chi', 'Psi', 'Omega',
    # Operators:
    'frac', 'sqrt', 'sum', 'prod', 'int', 'iint', 'iiint', 'oint',
    'bigcup', 'bigcap', 'bigsqcup',
    'lim', 'liminf', 'limsup', 'inf', 'sup', 'min', 'max', 'arg',
    'log', 'ln', 'exp', 'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
    'sinh', 'cosh', 'tanh', 'arcsin', 'arccos', 'arctan',
    'det', 'dim', 'gcd', 'ker', 'deg', 'hom',
    # Relations:
    'in', 'notin', 'ni', 'subset', 'supset', 'subseteq', 'supseteq',
    'subsetneq', 'supsetneq', 'cap', 'cup', 'setminus', 'emptyset',
    'leq', 'geq', 'neq', 'leqq', 'geqq', 'leqslant', 'geqslant',
    'lneq', 'gneq', 'approx', 'sim', 'simeq', 'asymp',
    'equiv', 'cong', 'propto', 'parallel', 'perp', 'mid', 'nmid',
    'lessgtr', 'gtrless', 'lll', 'ggg',
    # Logic:
    'forall', 'exists', 'nexists', 'land', 'lor', 'neg', 'lnot',
    # Arrows:
    'to', 'gets', 'mapsto', 'rightarrow', 'leftarrow', 'leftrightarrow',
    'Rightarrow', 'Leftarrow', 'Leftrightarrow',
    'longrightarrow', 'longleftarrow', 'longleftrightarrow',
    'hookrightarrow', 'hookleftarrow', 'rightharpoonup', 'leftharpoonup',
    # Basic:
    'pm', 'mp', 'times', 'div', 'cdot', 'cdots', 'ldots', 'vdots', 'ddots',
    'partial', 'nabla', 'infty', 'aleph', 'hbar',
    'oplus', 'ominus', 'otimes', 'odot', 'star', 'ast', 'circ',
    'dagger', 'ddagger', 'top', 'bot',
    # Modifiers:
    'tilde', 'hat', 'widetilde', 'widehat', 'bar', 'overline', 'underline',
    'dot', 'ddot', 'vec', 'check', 'breve', 'acute', 'grave',
    'overbrace', 'underbrace', 'overrightarrow', 'overleftarrow',
    # Brackets/sizing (handled separately by regex, but include for safety):
    'left', 'right', 'big', 'Big', 'bigg', 'Bigg',
    # Misc:
    'binom', 'choose', 'atop', 'over', 'pmod', 'mod',
    'ell', 'wp', 'Re', 'Im', 'imath', 'jmath',
    'square', 'blacksquare', 'triangle', 'triangledown',
    'angle', 'sphericalangle', 'measuredangle',
    'sharp', 'flat', 'natural',
    'spadesuit', 'clubsuit', 'heartsuit', 'diamondsuit',
    'triangleq', 'rtimes', 'ltimes', 'between',
    'quad', 'qquad', 'thinspace',
    # Colors / spacing — passed through as no-ops by mathtext typically:
    'displaystyle', 'textstyle', 'scriptstyle', 'scriptscriptstyle',
    'limits', 'nolimits',
    # newcommand (not math but appears in raw_text dumps).
    # NOTE: 'begin', 'end', 'item', 'label', 'ref', 'cite' are handled by
    # _LATEX_REGEX_FIXES (stripped or replaced) BEFORE this whitelist runs,
    # so they're intentionally NOT in this set.
    'newcommand', 'renewcommand',
})

# Regex-based fixes: commands like \ge that are prefixes of valid commands (\geq)
# Must use regex with word boundary to avoid breaking \geq -> \geqq
import re as _re
_LATEX_REGEX_FIXES = [
    (_re.compile(r'\\leqslant\b'), r'\\leq'),
    (_re.compile(r'\\geqslant\b'), r'\\geq'),
    (_re.compile(r'\\ge(?!q)'), r'\\geq'),
    (_re.compile(r'\\le(?!q|ft)'), r'\\leq'),
    (_re.compile(r'\\ne(?!g|wcommand|q)'), r'\\neq'),
    # \left( → (, \right) → ), \left[ → [, etc.
    (_re.compile(r'\\left\s*([(\[|.])'), r'\1'),
    (_re.compile(r'\\right\s*([)\]|.])'), r'\1'),
    # Strip LaTeX environment markers — mathtext cannot parse them and they
    # have no rendering meaning inside a math snippet anyway:
    (_re.compile(r'\\begin\s*\{[^}]*\}'), ''),
    (_re.compile(r'\\end\s*\{[^}]*\}'), ''),
    # Convert \item to bullet (mathtext-safe) so list items render readably:
    (_re.compile(r'\\item\b'), '• '),
    # Strip cross-reference / metadata commands with one brace argument:
    (_re.compile(r'\\(?:label|ref|cite|caption|tag|eqref|cref|nameref)\s*\{[^}]*\}'), ''),
    # Strip stand-alone \\ (line breaks inside math snippets break mathtext):
    (_re.compile(r'\\\\(?![A-Za-z])'), ' '),
    # Escaped special chars that mathtext doesn't recognize. Note re.sub
    # replacement strings: a literal & in the replacement needs to NOT be
    # `\&` (which would mean the matched group), use a plain `&`.
    (_re.compile(r'\\&'), '&'),                   # \& → &
    (_re.compile(r'\\%'), '%'),                   # \% → %
    (_re.compile(r'\\#'), '#'),                   # \# → #
    # Accent / modifier commands without braces — mathtext requires \bar{A}
    # but author LaTeX often writes \bar A. Convert single-letter forms:
    #   \bar A   →  \bar{A}
    #   \hat x   →  \hat{x}
    # Apply for each modifier we know mathtext accepts.
    (_re.compile(r'\\(bar|hat|tilde|dot|ddot|vec|check|breve|acute|grave|widetilde|widehat|overline|underline)\s+([A-Za-z])\b'),
     r'\\\1{\2}'),
]


def _fallback_unknown_commands(text):
    """For any \\command whose name is NOT in _KNOWN_MATHTEXT_COMMANDS, wrap
    it in \\mathrm{} so it renders as upright text instead of crashing
    matplotlib's mathtext parser.

    This handles author-defined macros like \\Lun, \\Lsym, \\charfct, \\Ncut
    that appear in faithful LaTeX-source extractions but aren't in the paper
    preamble we have access to.
    """
    if not text:
        return text

    def replace(m):
        cmd = m.group(1)
        if cmd in _KNOWN_MATHTEXT_COMMANDS:
            return m.group(0)
        return r'\mathrm{' + cmd + '}'
    return _re.sub(r'\\([A-Za-z]+)', replace, text)

def sanitize_for_mathtext(text, macros=None):
    """Make `text` safe to hand to matplotlib mathtext.

    `macros` is the paper's own glossary (`metadata.macros`), resolved first —
    passed EXPLICITLY rather than read from a module global. The renderer used
    to keep the glossary in a module-level `_CURRENT_MACROS` that draw_dag set
    per paper, which meant any other caller (the audit, cross-paper comparison)
    silently inherited whichever paper the renderer happened to touch last.

    Six passes:
      0. Collapse display-math markers `$$..$$` → `$..$` (mathtext doesn't
         support display mode, so treat as inline).
      1. Explicit literal substitutions in _LATEX_FIXES (\\R → \\mathbb{R}, etc.)
      2. Regex-based fixes in _LATEX_REGEX_FIXES (\\ge → \\geq, strip \\begin{}, etc.)
      3. Catch-all fallback: any \\command not in _KNOWN_MATHTEXT_COMMANDS
         gets wrapped in \\mathrm{} so unknown author macros render as
         upright text instead of crashing matplotlib mathtext.
      4. Backslash restoration inside `$..$`: bare math-name tokens like
         Sigma, sum, in (where Opus / cleaned-up extractions stripped the
         backslash) get the backslash put back so mathtext renders them
         as symbols (Σ, ∑, ∈) rather than upright text.
      5. Dollar-balance check: if the text has an odd number of unescaped
         $ markers, math mode would be entered but never closed, crashing
         mathtext. Escape all $ in that case so the text renders as plain
         text with visible $ signs.
    """
    if not text:
        return text
    # Paper macros FIRST: an unexpanded `\Sc` is an unknown command, so pass 3
    # below would wrap it as \mathrm{Sc} and the reader would see the macro name
    # instead of the symbol it stands for.
    text = normalize_for_mathtext(text, macros)
    # 0a: collapse display math (mathtext doesn't support $$..$$)
    while '$$' in text:
        text = text.replace('$$', '$')
    # 0b: replace embedded newlines with spaces. mathtext parses the
    # full string before line-splitting, so a `\n` between two $..$ blocks
    # makes the parser see them as one combined token, often crashing.
    text = text.replace('\n', ' ').replace('\r', ' ')
    for old, new in _LATEX_FIXES.items():
        text = text.replace(old, new)
    for pattern, repl in _LATEX_REGEX_FIXES:
        text = pattern.sub(repl, text)
    text = _fallback_unknown_commands(text)
    # 0c: collapse `$$` (empty math content) — but DO NOT collapse
    # `$ $` boundaries between adjacent math blocks ($X$ $Y$ stays as
    # two separate blocks, NOT merged into $XY$). Earlier versions of
    # this code collapsed `\$\s+\$` aggressively, which incorrectly
    # merged neighbors.
    while '$$' in text:
        text = text.replace('$$', '')
    text = _restore_bare_math_names(text)
    text = _balance_dollars(text)
    # Final safety: actually try to parse the math; on failure, strip $..$
    # so the text renders as plain unstyled string instead of crashing.
    text = _strip_math_on_error(text)
    return text


# Bare math-name tokens that should become backslash commands inside $..$.
# Restricted to $..$ so we don't break English prose containing the same
# words ("Sigma" the proper noun, "in" the preposition, etc.).
_BARE_MATH_NAMES = [
    # Greek letters (lowercase)
    'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'varepsilon', 'zeta', 'eta',
    'theta', 'vartheta', 'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi',
    'pi', 'varpi', 'rho', 'varrho', 'sigma', 'varsigma', 'tau', 'upsilon',
    'phi', 'varphi', 'chi', 'psi', 'omega',
    # Greek letters (uppercase)
    'Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta',
    'Theta', 'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi',
    'Pi', 'Rho', 'Sigma', 'Tau', 'Upsilon', 'Phi', 'Chi', 'Psi', 'Omega',
    # Operators
    'sum', 'prod', 'int', 'iint', 'oint',
    'lim', 'liminf', 'limsup', 'inf', 'sup', 'min', 'max', 'arg',
    'log', 'ln', 'exp',
    'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
    'sinh', 'cosh', 'tanh', 'arcsin', 'arccos', 'arctan',
    'det', 'dim', 'gcd', 'ker',
    # Relations / set theory
    'in', 'notin', 'ni', 'subset', 'subseteq', 'supset', 'supseteq',
    'cap', 'cup', 'emptyset',
    'forall', 'exists', 'nexists',
    'leq', 'geq', 'neq',
    'to', 'mapsto', 'rightarrow', 'leftarrow', 'Rightarrow', 'Leftarrow',
    # Misc
    'infty', 'partial', 'nabla', 'ell',
    'cdot', 'cdots', 'ldots', 'times', 'div',
    'pm', 'mp', 'mid',
]
# One combined regex for performance. The lookbehind ensures we don't
# match continuation of another identifier ("inflate" doesn't become
# "\inflate") or already-prefixed commands ("\sigma" stays as "\sigma").
# Use [a-zA-Z0-9] (NOT \w) for boundaries because \w includes `_` — but
# `_` is the LaTeX subscript marker, so we WANT `Sigma_d` to match
# `Sigma` (the underscore is the boundary, not a continuation char).
_BARE_MATH_NAMES_RE = _re.compile(
    r'(?<![a-zA-Z0-9\\])(' + '|'.join(sorted(_BARE_MATH_NAMES, key=len, reverse=True)) + r')(?![a-zA-Z0-9])'
)


def _restore_bare_math_names(text):
    """Inside `$..$` blocks, prefix bare math-name tokens (Sigma, sum, in,
    ...) with a backslash so matplotlib mathtext renders them as symbols.

    Operates ONLY inside `$..$` regions — leaves English prose alone, so
    the proper-noun "Sigma" outside math stays as "Sigma" and the
    preposition "in" outside math stays as "in".
    """
    if not text or '$' not in text:
        return text
    out = []
    i = 0
    while i < len(text):
        if text[i] == '$':
            j = text.find('$', i + 1)
            if j == -1:
                out.append(text[i:])
                break
            content = text[i + 1:j]
            content = _BARE_MATH_NAMES_RE.sub(r'\\\1', content)
            out.append('$' + content + '$')
            i = j + 1
        else:
            j = text.find('$', i)
            if j == -1:
                out.append(text[i:])
                break
            out.append(text[i:j])
            i = j
    return ''.join(out)


def _balance_dollars(text):
    """If `text` has an odd number of unescaped `$` markers, escape them
    all so matplotlib mathtext doesn't enter unterminated math mode and
    crash. Returns text unchanged if balance is even."""
    if not text:
        return text
    # Count `$` not preceded by a backslash
    n_unescaped = 0
    for i, c in enumerate(text):
        if c == '$' and (i == 0 or text[i - 1] != '\\'):
            n_unescaped += 1
    if n_unescaped % 2 == 0:
        return text
    # Odd number → escape them all
    return _re.sub(r'(?<!\\)\$', r'\\$', text)


# Lazy mathtext parser for the safety check in _strip_math_on_error
_MATHTEXT_PARSER = None


def _can_render_math(text):
    """Try parsing each `$..$` block with mathtext. Return True if all
    blocks parse cleanly, False if any fails."""
    if not text or '$' not in text:
        return True
    global _MATHTEXT_PARSER
    if _MATHTEXT_PARSER is None:
        try:
            from matplotlib.mathtext import MathTextParser
            _MATHTEXT_PARSER = MathTextParser('agg')
        except Exception:
            return True   # if we can't even import, give up checking
    try:
        # Validate each $..$ block
        for match in _re.finditer(r'\$([^$]*)\$', text):
            content = match.group(0)
            if len(content) > 2:    # has content between dollars
                _MATHTEXT_PARSER.parse(content, dpi=100, prop=None)
        return True
    except Exception:
        return False


def _strip_math_on_error(text):
    """If `text` would crash mathtext, strip all `$..$` markers (keeping
    the inner content as plain text). Last-resort fallback."""
    if _can_render_math(text):
        return text
    # Strip $ but keep content
    return _re.sub(r'\$([^$]*)\$', r'\1', text)


# ── Reading a paper's macro definitions ─────────────────────────────────────
# (moved here from scripts/build_macro_glossary.py, so the glossary, the
# extraction preprocessing in latex_facts.py and the expander share one reader)

# Definition forms. Each yields (name, rest-of-string-index) and we then read a
# brace-balanced body, because expansions routinely contain nested braces and a
# length-capped regex would truncate them.
FORMS = [
    # \newcommand{\foo}[2][opt]{body} / \newcommand\foo{body}
    # The SECOND bracket is LaTeX's optional-argument DEFAULT, and dropping it
    # is not cosmetic: `\newcommand{\limGs}[1][G]{\mathcal{X}_{#1}}` declares
    # one argument that is OPTIONAL, so bare `\limGs` means `\mathcal{X}_{G}`.
    # Recording it as plain arity=1 makes an expander read the next token as a
    # mandatory argument and swallow whatever follows — usually the closing `$`.
    re.compile(r'\\(?:new|renew|provide)command\*?\s*\{?\\(?P<name>[A-Za-z@]+)\}?\s*'
               r'(?:\[(?P<nargs>\d+)\])?\s*(?:\[(?P<opt>[^\]]*)\])?\s*\{'),
    # \def\foo{body}  /  \def\foo#1{body}
    re.compile(r'\\(?:e|g|x)?def\s*\\(?P<name>[A-Za-z@]+)\s*(?:#\d)*\s*\{'),
    # \DeclareMathOperator{\foo}{body} — see OPERATOR_FORM below
    re.compile(r'\\DeclareMathOperator\*?\s*\{\\(?P<name>[A-Za-z@]+)\}\s*\{'),
    # \newenvironment{foo}{begin}{end} — name has no backslash
    re.compile(r'\\(?:new|renew)environment\*?\s*\{(?P<name>[A-Za-z@*]+)\}\s*'
               r'(?:\[\d+\])?\s*\{'),
]

STRUCT = re.compile(r'\\(label|index|textbf|emph|textit|section|subsection|'
                    r'paragraph|begin|end|item|footnote|caption|ref|eqref|cite|'
                    r'ignorespaces|noindent|medskip|smallskip|vspace)\b')
PRESENT = re.compile(r'\\(textcolor|color|colorbox|hl|st|sout|uline)\b')


def strip_comments(src):
    """Drop % comments (respecting \\%) so definitions inside comments are ignored."""
    return re.sub(r'(?<!\\)%.*', '', src)


def balanced_body(src, open_idx):
    """Read a brace-balanced body starting at the '{' at open_idx."""
    depth, i, n = 0, open_idx, len(src)
    while i < n:
        c = src[i]
        if c == '\\':                      # skip escaped char
            i += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return src[open_idx + 1:i], i + 1
        i += 1
    return None, n                          # unbalanced — give up on this one


def classify(expansion):
    if PRESENT.search(expansion):
        return "presentational"
    if STRUCT.search(expansion):
        return "structural"
    return "notational"


def _is_operator(form):
    return 'DeclareMathOperator' in form.pattern


def read_definitions(src, clean=True, spans=False):
    """name -> {expansion, kind, arity[, optional_default][, form, span]}.

    The one reader of a paper's macro definitions (\\newcommand, \\def,
    \\DeclareMathOperator, \\newenvironment). Later definitions win
    (\\renewcommand). `clean=False` for text whose comments are already gone;
    `spans=True` adds `form` ('command', 'def', 'operator', 'environment'),
    `span`, the (start, end) of the whole definition in `src`, and `spans`,
    the spans of every definition of that name (a paper may repeat one).
    """
    if clean:
        src = strip_comments(src)
    out = {}
    for fi, form in enumerate(FORMS):
        for m in form.finditer(src):
            name = m.group('name')
            body, end = balanced_body(src, m.end() - 1)
            if body is None:
                continue
            arity = len(set(re.findall(r'#(\d)', body)))
            expansion = re.sub(r'\s+', ' ', body).strip()
            # \DeclareMathOperator{\eq}{eq} means "typeset `eq` as an OPERATOR
            # NAME", i.e. upright. Storing the bare `eq` loses that: in math
            # mode it sets as the product of two italic variables, e * q. The
            # renderer cannot recover the intent afterwards, so record it here.
            if _is_operator(form) and re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', expansion or ''):
                expansion = r'\mathrm{%s}' % expansion
            rec = {
                "expansion": expansion,
                "kind": classify(body),
                "arity": arity,
            }
            # Present (even empty) => the first argument is optional.
            gd = m.groupdict()
            if gd.get("opt") is not None:
                rec["optional_default"] = gd["opt"]
                if gd.get("nargs"):
                    rec["arity"] = int(gd["nargs"])
            if spans:
                rec["form"] = ("command", "def", "operator", "environment")[fi]
                rec["span"] = (m.start(), end)
                rec["spans"] = out.get(name, {}).get("spans", []) + [(m.start(), end)]
            out[name] = rec
    # \newcommand\phif\varphi: a body of one control word, without braces
    for m in re.finditer(r"\\(?:new|renew|provide)command\*?\s*\\(?P<name>[A-Za-z@]+)"
                         r"\s*(?P<body>\\[A-Za-z@]+)(?![A-Za-z@{\[])", src):
        rec = {"expansion": m.group("body"), "kind": classify(m.group("body")), "arity": 0}
        if spans:
            rec["form"] = "command"
            rec["span"] = (m.start(), m.end())
            rec["spans"] = out.get(m.group("name"), {}).get("spans", []) + [(m.start(), m.end())]
        out[m.group("name")] = rec
    return out
