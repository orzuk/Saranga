"""Regression tests for src/latex_macros.py.

Runs without pytest:  python3 tests/test_latex_macros.py

Every case here is a defect that reached a rendered page. The token-boundary
group is the reason this file exists: the same bug was fixed in expand_macros,
declared done, and then surfaced again in unwrap_transparent a few hours later,
because each textual splice site had its own `+` concatenation. They now all go
through _splice, and these cases pin that.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from latex_macros import (normalize_for_mathtext, expand_macros,   # noqa: E402
                          brace_normalize, resolve_references,
                          resolve_text_fonts, strip_text_environments)

FAILS = []


def check(got, want, why):
    if got != want:
        FAILS.append("%-46s\n     got  %r\n     want %r" % (why, got, want))


# ── Token boundaries: TeX ends a control word at `\` or `{`, a string splice
#    does not. Every substitution site can weld the replacement onto whatever
#    control word precedes it.
XMO = {"xmo": {"expansion": r"X^{-\omega}", "arity": 0}}
check(normalize_for_mathtext(r"$\in\xmo$", XMO), r"$\in X^{-\omega}$",
      "expand: macro after a control word")
check(normalize_for_mathtext(r"$\geq\underline{C}$", {}), r"$\geq C$",
      "unwrap: transparent wrapper after a control word")
check(normalize_for_mathtext(r"$\in\mbox{Foo}$", {}), r"$\in Foo$",
      "unwrap: mbox after a control word")
check(normalize_for_mathtext(r"$x\underline{C}$", {}), r"$xC$",
      "no space when the prefix is NOT a control word")
check(expand_macros(r"x\xmo", XMO), r"xX^{-\omega}",
      "no space after a plain letter")

# ── Optional arguments. `[1][G]` is ONE argument that is OPTIONAL, so bare use
#    supplies nothing; treating it as mandatory ate the closing `$`.
LIMGS = {"limGs": {"expansion": r"\mathcal{X}_{#1}", "arity": 1,
                   "optional_default": "G"}}
check(normalize_for_mathtext(r"$x\in\limGs$", LIMGS), r"$x\in\mathcal{X}_{G}$",
      "optional arg: default used, `$` not consumed")
check(normalize_for_mathtext(r"$\limGs[H]$", LIMGS), r"$\mathcal{X}_{H}$",
      "optional arg: explicit value overrides")

# ── Font commands take one token; braces vs space are NOT interchangeable.
A = {"A": {"expansion": "Alpha", "arity": 0}}
check(normalize_for_mathtext(r"$\mathbb\A$", A), r"$\mathbb{Alpha}$",
      "font cmd + control-seq arg braces BEFORE expansion")
check(brace_normalize(r"$\mathbb R$"), r"$\mathbb{R}$", "font cmd + bare letter")
check(brace_normalize(r"$\mathbbR$"), r"$\mathbbR$",
      "no space: `\\mathbbR` is one control word, must not be split")

# ── Cross-references: keep the key, escape `_` only inside math.
check(resolve_references(r"see \cite{a_b, c:d}"), "see [a_b, c:d]",
      "cite keys unescaped in text")
check(resolve_references(r"$f(\ref{eq:a_b})$"), r"$f(eq:a\_b)$",
      "ref key escaped inside math; no second pair of parentheses")
check(resolve_references(r"under \eqref{eq:x} and (\ref{eq:y})", {"eq:x": "EP1"}),
      "under (EP1) and (eq:y)", "eqref adds parentheses; known labels show the node id")
check(resolve_references(r"\label{x}gone"), "gone", "label dropped")
check(resolve_references(r"\reflect{x}"), r"\reflect{x}",
      "`\\reflect` is not `\\ref`")

# ── Text environments: MathJax knows only math ones.
check(strip_text_environments(r"\begin{lemma}text\end{lemma}").strip(), "text",
      "theorem-like env unwrapped")
check(strip_text_environments(r"\begin{equation}x\end{equation}"),
      r"\begin{equation}x\end{equation}", "math env left for the math path")
check(strip_text_environments(r"\begin{itemize}\item a\item b\end{itemize}").strip(),
      "• a • b", "list env bulleted")
check(strip_text_environments(r"\begin{lemma}dangling").strip(), "dangling",
      "orphan \\begin dropped (spans are cut mid-environment)")

# ── Font selectors: mapped in math, unwrapped in text; declarations take their
#    scoping braces with them.
check(resolve_text_fonts(r"$\textsf{Push}$"), r"$\mathsf{Push}$",
      "font selector mapped inside math")
check(resolve_text_fonts(r"\textsf{Push}{} and \emph{x}"), "Push and x",
      "font selector unwrapped in text, empty group dropped")
check(resolve_text_fonts(r"{\em foo bar} baz").strip(), "foo bar baz",
      "declaration form drops its scoping braces")
check(resolve_text_fonts(r"\begin{itemize}\item a\end{itemize}"),
      r"\begin{itemize}\item a\end{itemize}",
      "`\\item` must survive the `\\it` declaration rule")
check(resolve_text_fonts(r"(resp.\ $w$)"), "(resp. $w$)", "control space")

if FAILS:
    print("FAILED %d:" % len(FAILS))
    for f in FAILS:
        print("  " + f)
    sys.exit(1)
print("all latex_macros regression checks pass")
