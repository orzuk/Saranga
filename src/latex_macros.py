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

Comparison is the subtle case. `\\Sc` in paper A and `\\Sc` in paper B may be
different objects; expanding each with its own glossary is what makes the two
texts commensurable. That is why this lives here rather than inside
`visualize_annotation.py`.
"""
from __future__ import annotations

import re

__all__ = ["expand_macros", "brace_normalize", "unwrap_transparent",
           "normalize_for_mathtext"]

# Math-font commands take exactly one argument. TeX lets you omit the braces
# and grabs the next single token, so `{\mathbb R}` == `\mathbb{R}` — valid
# LaTeX that matplotlib's mathtext rejects.
_FONT_CMDS = ("mathbb", "mathcal", "mathrm", "mathbf", "mathfrak", "mathsf",
              "mathtt", "mathit", "mathscr", "boldsymbol", "operatorname")

# The argument may be a single character (`\\mathbb R`) or another control
# sequence (`{\\mathbf \\H}`, where \\H is itself a paper macro).
_UNBRACED = re.compile(r"\\(%s)\s+(\\[A-Za-z]+|[A-Za-z0-9])" % "|".join(_FONT_CMDS))

_MAX_DEPTH = 8          # nested macro definitions; also breaks \a -> \b -> \a


def brace_normalize(text):
    """`\\mathbb R` -> `\\mathbb{R}`, for the one-token-argument idiom.

    91 of the 200 v5.1 silver papers use the unbraced form (4953 occurrences);
    some use it exclusively. Both render identically in TeX, so this is a
    normalisation, not a correction.
    """
    if not text:
        return text
    return _UNBRACED.sub(r"\\\1{\2}", str(text))


# Wrappers that carry no mathematical meaning: they exist to control MODE or
# spacing in real LaTeX. Macro expansions are full of them (`\integerset` ->
# `\ensuremath{\mathbb{N}}`), and mathtext does not implement them, so a
# perfectly-resolved macro can still fail to render. Unwrapping keeps the
# argument and drops the shell.
_TRANSPARENT = ("ensuremath", "mbox", "hbox", "text", "textnormal")
_TRANSPARENT_RE = re.compile(r"\\(%s)\s*\{" % "|".join(_TRANSPARENT))


def unwrap_transparent(text, max_depth=_MAX_DEPTH):
    """`\\ensuremath{X}` -> `X`, `\\mbox{X}` -> `X`, nested included."""
    if not text:
        return text
    text = str(text)
    for _ in range(max_depth):
        m = _TRANSPARENT_RE.search(text)
        if not m:
            break
        arg, end = _read_group(text, m.end() - 1)
        text = text[:m.start()] + arg + text[end:]
    return text


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
        while True:
            m = pattern.search(text, i)
            if not m:
                out.append(text[i:])
                break
            out.append(text[i:m.start()])
            spec = macros[m.group(1)] or {}
            body = spec.get("expansion", "") if isinstance(spec, dict) else str(spec)
            arity = int(spec.get("arity", 0)) if isinstance(spec, dict) else 0
            j = m.end()
            args = []
            for _a in range(arity):
                arg, j = _read_group(text, j)
                args.append(arg)
            out.append(_substitute(body, args))
            i = j
            changed = True
        text = "".join(out)
        if not changed:
            break
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
    """
    text = brace_normalize(text)
    text = expand_macros(text, macros or {})
    text = unwrap_transparent(text)
    return brace_normalize(text)
