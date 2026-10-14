"""Shared LaTeX-to-plain-text cleaner for the rules-based parser and distilled rules.

All cleaning in the project should go through ``clean_latex_to_text`` so that
``clean_text`` / ``statement`` fields are consistent across base-regex and
distilled-rule extractions.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # src/
from latex_macros import strip_comments  # noqa: E402

# ── Pre-compiled patterns ────────────────────────────────────────────────────

# \label{...}, \ref{...}, \eqref{...}, \cite[...]{...}
_LABEL_RE = re.compile(r"\\label\s*\{[^}]*\}")
_REF_RE = re.compile(r"\\(?:eq)?ref\s*\{[^}]*\}")
_CITE_RE = re.compile(r"~?\\cite(?:\[[^\]]*\])?\s*\{[^}]*\}")

# \begin{...} / \end{...}
_BEGIN_END_RE = re.compile(r"\\(?:begin|end)\s*\{[^}]*\}")

# Formatting commands whose argument should be kept: \emph{X} -> X
_FMT_CMD_RE = re.compile(
    r"\\(?:emph|textbf|textit|textrm|textsf|texttt|textsl|text"
    r"|mathrm|mathbf|mathit|mathcal|mathscr|mathbb|mathfrak|mathsf"
    r"|operatorname)\s*\{([^}]*)\}"
)
# {\em X} / {\bf X} style
_FMT_BRACE_RE = re.compile(r"\{\\(?:em|it|bf|sl|rm)\s+([^}]*)\}")

# Simple spacing / layout commands (no arguments)
_SIMPLE_CMD_RE = re.compile(
    r"\\(?:par|noindent|newline|bigskip|medskip|smallskip"
    r"|quad|qquad|hfill|vfill|centering|maketitle"
    r"|qed|qedsymbol|blacksquare|displaystyle)\b"
)

# Generic \command — keep the command name as readable text
_GENERIC_CMD_RE = re.compile(r"\\([a-zA-Z]+)")

# Whitespace
_MULTI_SPACE_RE = re.compile(r"\s+")


def clean_latex_to_text(latex: str) -> str:
    """Best-effort LaTeX -> plain text cleaner.

    Design goals (in priority order):
      1. **Preserve math content** — variable names, operators, sub/superscripts
         remain readable.  ``$\\delta(G) > 3n/4$`` becomes ``delta(G) > 3n/4``,
         NOT ``[MATH]``.
      2. **Consistent** — the same function is used by the base regex parser
         AND all distilled-rule extractors.
      3. **Strip markup** — environments, labels, refs, cites, formatting
         commands are removed.
    """
    s = latex

    # 1. Strip comments
    s = strip_comments(s)

    # 2. Remove labels, refs, cites
    s = _LABEL_RE.sub("", s)
    s = _REF_RE.sub("", s)
    s = _CITE_RE.sub("", s)

    # 3. Remove \begin{...} / \end{...}
    s = _BEGIN_END_RE.sub("", s)

    # 4. Unwrap formatting commands (multiple passes for nesting)
    for _ in range(3):
        s = _FMT_CMD_RE.sub(r"\1", s)
    s = _FMT_BRACE_RE.sub(r"\1", s)

    # 5. Remove simple spacing/layout commands
    s = _SIMPLE_CMD_RE.sub(" ", s)

    # 6. Strip dollar-sign math delimiters but keep content
    s = s.replace("$", "")

    # 7. Replace remaining \command with command name (e.g. \delta -> delta)
    s = _GENERIC_CMD_RE.sub(r"\1", s)

    # 8. Remove stray braces
    s = s.replace("{", "").replace("}", "")

    # 9. Collapse whitespace
    s = _MULTI_SPACE_RE.sub(" ", s)

    return s.strip()
