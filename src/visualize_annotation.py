#!/usr/bin/env python3
"""Visualize a student annotation JSON as a DAG knowledge graph.

Usage:
    python visualize_annotation.py annotation.json [output.png]

Produces a layered DAG visualization with:
  - Topological depth for vertical positioning (foundations at top, results at bottom)
  - Compound boxes for theorems/lemmas showing assumptions and conclusions
  - Proof strategy collapsed into the parent theorem's box
  - Color-coded by node type
"""
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams['mathtext.fontset'] = 'cm'  # Computer Modern for math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import networkx as nx


# ── Colors ──────────────────────────────────────────────────────────────────
NODE_COLORS = {
    "definition":  {"header": "#27AE60", "body": "#D5F5E3"},
    "theorem":     {"header": "#C0392B", "body": "#FADBD8"},
    "lemma":       {"header": "#D35400", "body": "#F5CBA7"},
    "corollary":   {"header": "#943126", "body": "#F2D7D5"},
    "algorithm":   {"header": "#2471A3", "body": "#D4E6F1"},
    "equation":    {"header": "#5DADE2", "body": "#EBF5FB"},
    "proposition": {"header": "#B03A2E", "body": "#FADBD8"},
    "proof":       {"header": "#8E44AD", "body": "#E8DAEF"},
    "proof_step":  {"header": "#A569BD", "body": "#F4ECF7"},
    "claim":       {"header": "#E74C3C", "body": "#FDEDEC"},
}
DEFAULT_COLOR = {"header": "#566573", "body": "#EAECEE"}
PROOF_COLOR = "#E8DAEF"

# ── Layout constants (shared between draw_dag and draw_foundation_ghosts) ──
MIN_BOX_W = 3.0
MAX_BOX_W = 6.0
BOX_GAP_X = 0.5
LEVEL_GAP_Y = 5.0
HEADER_H = 0.45
LINE_H = 0.28
PADDING = 0.10
CHARS_PER_UNIT = 12


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

def _sanitize_math(text):
    """Replace unsupported LaTeX commands with matplotlib-compatible equivalents.

    Five passes:
      0. Collapse display-math markers `$$..$$` → `$..$` (mathtext doesn't
         support display mode, so treat as inline).
      1. Explicit literal substitutions in _LATEX_FIXES (\\R → \\mathbb{R}, etc.)
      2. Regex-based fixes in _LATEX_REGEX_FIXES (\\ge → \\geq, strip \\begin{}, etc.)
      3. Catch-all fallback: any \\command not in _KNOWN_MATHTEXT_COMMANDS
         gets wrapped in \\mathrm{} so unknown author macros render as
         upright text instead of crashing matplotlib mathtext.
      4. Dollar-balance check: if the text has an odd number of unescaped
         $ markers, math mode would be entered but never closed, crashing
         mathtext. Escape all $ in that case so the text renders as plain
         text with visible $ signs.
    """
    if not text:
        return text
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
    # 0c: collapse `$<whitespace>$` (adjacent math blocks separated only
    # by spaces) — these arise after stripping `\\\\` LaTeX line breaks
    # from inside math. mathtext can't handle the empty-content `$<space>$`.
    text = _re.sub(r'\$\s+\$', '', text)
    while '$$' in text:
        text = text.replace('$$', '')
    text = _balance_dollars(text)
    return text


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


def _display_width(text):
    """Estimate display width of text in characters, accounting for math.

    For math in $...$: strip LaTeX commands to estimate rendered character count,
    then apply a small multiplier (1.3x) for spacing/operators.
    E.g., '$\\mathbf{z}$' → rendered as 'z' (1 char), not 12 raw chars.
    """
    if not text or "$" not in text:
        return len(text) if text else 0
    width = 0
    i = 0
    while i < len(text):
        if text[i] == "$":
            j = text.find("$", i + 1)
            if j == -1:
                width += len(text[i:])
                break
            math_content = text[i+1:j]
            # Estimate rendered width by stripping commands to their visual output
            rendered = math_content
            # \command{arg} → arg (1 char for the result)
            rendered = _re.sub(r'\\(?:mathbf|mathrm|mathbb|mathcal|mathit|bm|'
                               r'boldsymbol|text|operatorname)\s*\{([^}]*)\}', r'\1', rendered)
            # \frac{a}{b} → a/b (roughly len(a)+len(b)+1)
            rendered = _re.sub(r'\\frac\s*\{([^}]*)\}\s*\{([^}]*)\}', r'\1/\2', rendered)
            # \sqrt{x} → √x
            rendered = _re.sub(r'\\sqrt\s*\{([^}]*)\}', r'V\1', rendered)
            # Greek letters: \alpha → α (1 char each)
            rendered = _re.sub(r'\\[a-zA-Z]+', 'X', rendered)
            # Subscript/superscript braces
            rendered = rendered.replace('{', '').replace('}', '')
            # Apply small multiplier for operator spacing
            rendered_len = len(rendered)
            if _re.search(r'\\frac|\\sum|\\prod|\\int', math_content):
                rendered_len = int(rendered_len * 1.5)  # fractions are wider
            else:
                rendered_len = int(rendered_len * 1.3)  # general math spacing
            width += max(rendered_len, 3)  # at least 3 chars for any math
            i = j + 1
        else:
            j = text.find("$", i)
            if j == -1:
                width += len(text[i:])
                break
            width += j - i
            i = j
    return width


def _has_tall_math(text):
    """Check if text contains math that renders taller than normal (fractions, sums, etc.)."""
    if not text or "$" not in text:
        return False
    return bool(_re.search(
        r'\\frac|\\sum|\\prod|\\int|\\iint|\\log_|\\lim_|\^{|_{.*{|'
        r'\\underset|\\overset|\\stackrel|\\binom|\\atop', text))


def _prepare_for_display(text):
    """Prepare text for matplotlib rendering: keep math in $...$, fix unsupported commands.

    - Text already in $...$ is sanitized (unsupported commands replaced)
    - Text with bare LaTeX notation (subscripts, Greek, etc.) gets wrapped in $...$
    - Truly unrenderable things fall back to their command name
    """
    if not text:
        return ""
    t = text

    # If text has $...$ already, just sanitize the math parts
    if "$" in t:
        return _sanitize_math(t)

    # Text without $: check if it contains math-like patterns
    # If so, try wrapping the whole thing (or parts) in $...$
    has_math = bool(_re.search(
        r'[_^{}\\]|>=|<=|!=|\balpha\b|\bbeta\b|\bgamma\b|\bdelta\b|'
        r'\btheta\b|\blambda\b|\bsigma\b|\bepsilon\b|\binfty\b|'
        r'\bforall\b|\bexists\b|\bsubset\b', t))

    if not has_math:
        return t  # plain text, no math

    # Has math-like notation but no $ delimiters.
    # Can't reliably auto-wrap arbitrary LaTeX fragments in $...$,
    # so fall back to clean plain text.
    return _to_display_text(t)


def _to_display_text(text):
    """Convert LaTeX-rich text to clean plain text for PNG display.

    Strips all LaTeX notation to produce readable text that won't break
    matplotlib. The JSON keeps the full LaTeX; this is display-only.
    """
    if not text:
        return ""
    t = text
    # Remove $...$ delimiters (keep content)
    t = t.replace("$", "")
    # Remove common LaTeX commands, keep their argument
    # \mathbb{R} -> R, \mathrm{Var} -> Var, \bm{x} -> x, etc.
    t = _re.sub(r'\\(?:mathbb|mathrm|mathcal|mathbf|mathit|bm|boldsymbol|'
                r'text|textit|textbf|emph|operatorname)\s*\{([^}]*)\}', r'\1', t)
    # \frac{a}{b} -> a/b
    t = _re.sub(r'\\frac\s*\{([^}]*)\}\s*\{([^}]*)\}', r'(\1)/(\2)', t)
    # \sqrt{x} -> sqrt(x)
    t = _re.sub(r'\\sqrt\s*\{([^}]*)\}', r'sqrt(\1)', t)
    # \left, \right, \big, \Big etc. -> nothing
    t = _re.sub(r'\\(?:left|right|big|Big|bigg|Bigg)([|()[\]{}.]?)', r'\1', t)
    # Subscripts/superscripts: x_{abc} -> x_abc, x^{abc} -> x^abc
    t = _re.sub(r'_\{([^}]*)\}', r'_\1', t)
    t = _re.sub(r'\^\{([^}]*)\}', r'^\1', t)
    # \| -> ||
    t = t.replace(r'\|', '||')
    # Common symbols
    t = t.replace(r'\leq', '<=').replace(r'\geq', '>=')
    t = t.replace(r'\le', '<=').replace(r'\ge', '>=')
    t = t.replace(r'\neq', '!=').replace(r'\ne', '!=')
    t = t.replace(r'\in', 'in').replace(r'\notin', 'not in')
    t = t.replace(r'\subset', 'subset').replace(r'\subseteq', 'subseteq')
    t = t.replace(r'\cup', 'U').replace(r'\cap', 'n')
    t = t.replace(r'\times', 'x').replace(r'\cdot', '*').replace(r'\cdots', '...')
    t = t.replace(r'\ldots', '...').replace(r'\dots', '...')
    t = t.replace(r'\infty', 'inf').replace(r'\infinity', 'inf')
    t = t.replace(r'\sum', 'sum').replace(r'\prod', 'prod')
    t = t.replace(r'\int', 'int').replace(r'\partial', 'd')
    t = t.replace(r'\nabla', 'grad').replace(r'\Delta', 'Delta')
    t = t.replace(r'\alpha', 'alpha').replace(r'\beta', 'beta')
    t = t.replace(r'\gamma', 'gamma').replace(r'\delta', 'delta')
    t = t.replace(r'\epsilon', 'eps').replace(r'\varepsilon', 'eps')
    t = t.replace(r'\theta', 'theta').replace(r'\lambda', 'lambda')
    t = t.replace(r'\mu', 'mu').replace(r'\sigma', 'sigma')
    t = t.replace(r'\rho', 'rho').replace(r'\phi', 'phi')
    t = t.replace(r'\eta', 'eta').replace(r'\kappa', 'kappa')
    t = t.replace(r'\pi', 'pi').replace(r'\omega', 'omega')
    t = t.replace(r'\Phi', 'Phi').replace(r'\Sigma', 'Sigma')
    t = t.replace(r'\Theta', 'Theta').replace(r'\Lambda', 'Lambda')
    t = t.replace(r'\ell', 'l').replace(r'\log', 'log').replace(r'\exp', 'exp')
    t = t.replace(r'\min', 'min').replace(r'\max', 'max')
    t = t.replace(r'\sup', 'sup').replace(r'\inf', 'inf')
    t = t.replace(r'\lim', 'lim').replace(r'\arg', 'arg')
    t = t.replace(r'\forall', 'forall').replace(r'\exists', 'exists')
    t = t.replace(r'\rightarrow', '->').replace(r'\to', '->')
    t = t.replace(r'\Rightarrow', '=>').replace(r'\implies', '=>')
    t = t.replace(r'\Leftrightarrow', '<=>').replace(r'\iff', '<=>')
    t = t.replace(r'\sim', '~').replace(r'\approx', '~=')
    t = t.replace(r'\quad', ' ').replace(r'\qquad', '  ')
    t = t.replace(r'\,', ' ').replace(r'\;', ' ').replace(r'\ ', ' ')
    # Remove any remaining backslash commands: \xxx -> xxx
    t = _re.sub(r'\\([a-zA-Z]+)', r'\1', t)
    # Clean up braces and extra spaces
    t = t.replace('{', '').replace('}', '')
    t = _re.sub(r'\s+', ' ', t).strip()
    return t


def _wrap(text, width=38):
    """Wrap text to width, never breaking inside $...$ math expressions.

    Strategy:
    1. Split into atomic tokens: each $...$ math block is one token,
       each word in non-math text is one token.
    2. Greedily accumulate tokens into lines, breaking when _display_width
       would exceed *width*.
    3. If a single $...$ token is wider than *width*, shorten it with
       _shorten (which never cuts inside math) so it fits.
    """
    if not text:
        return []
    # If no math, simple wrap
    if "$" not in text:
        return textwrap.wrap(text, width=width)

    # Split text into atomic tokens: $...$ blocks and individual words
    tokens = []
    i = 0
    while i < len(text):
        if text[i] == "$":
            # Find closing $
            j = text.find("$", i + 1)
            if j == -1:
                tokens.append(text[i:])
                break
            tokens.append(text[i:j+1])  # include both $
            i = j + 1
        else:
            # Find next $ or end
            j = text.find("$", i)
            if j == -1:
                chunk = text[i:]
            else:
                chunk = text[i:j]
            # Split non-math chunk into words (preserving spaces for joining)
            words = chunk.split(" ")
            for wi, w in enumerate(words):
                if w:
                    tokens.append(w)
                if wi < len(words) - 1:
                    tokens.append(" ")
            i = j if j != -1 else len(text)

    # If a single math token is wider than width, just keep it as-is.
    # It may overflow slightly, but that's better than breaking the LaTeX
    # or stripping to plain text. The box will accommodate it partially.
    # (Previously tried truncating, but cutting mid-\frac breaks rendering.)

    # Greedily accumulate tokens into lines
    lines = []
    current = ""
    for tok in tokens:
        if tok == " ":
            # Space: append to current line if there is content
            if current:
                current += " "
            continue
        candidate = current + tok if current and not current.endswith(" ") else current + tok
        if current and _display_width(candidate) > width:
            stripped = current.strip()
            if stripped:
                lines.append(stripped)
            current = tok
        else:
            current = candidate
    if current.strip():
        lines.append(current.strip())

    return lines


def _shorten(text, maxlen=80):
    """Shorten text, never cutting inside a $...$ math expression.

    If cutting would land inside an equation, drop the equation entirely
    rather than showing a partial formula.
    """
    if not text:
        return ""
    text = _sanitize_math(text)
    if len(text) <= maxlen:
        return text
    cut = maxlen - 3
    # Count $ signs before cut point; if odd, we're inside math
    n_dollars = text[:cut].count("$")
    if n_dollars % 2 == 1:
        # Inside math — find the opening $ of this equation and cut before it
        # Walk backwards from cut to find the last unmatched $
        last_dollar = text.rfind("$", 0, cut)
        if last_dollar > 0:
            cut = last_dollar  # cut before the equation starts
        else:
            cut = maxlen - 3  # fallback
    return text[:cut].rstrip() + "..."


# ── DAG computation ─────────────────────────────────────────────────────────
def compute_dag_depth(nodes, edges):
    """Compute longest-path depth for each node. Roots = depth 0."""
    adj = defaultdict(list)
    in_deg = defaultdict(int)
    node_ids = {n["id"] for n in nodes}

    for e in edges:
        s, t = e["source"], e["target"]
        if s in node_ids and t in node_ids:
            adj[s].append(t)
            in_deg[t] += 0  # ensure exists
            in_deg[s] += 0

    # recount
    in_deg = defaultdict(int)
    for e in edges:
        s, t = e["source"], e["target"]
        if s in node_ids and t in node_ids:
            in_deg[t] += 1

    depth = {nid: 0 for nid in node_ids}
    queue = [nid for nid in node_ids if in_deg[nid] == 0]

    while queue:
        nid = queue.pop(0)
        for tgt in adj[nid]:
            depth[tgt] = max(depth[tgt], depth[nid] + 1)
            in_deg[tgt] -= 1
            if in_deg[tgt] == 0:
                queue.append(tgt)

    return depth


def _section_sort_key(node):
    """Sort by section number, then by ID."""
    sec = node.get("section", "99")
    try:
        parts = [float(x) for x in sec.split(".")]
    except ValueError:
        parts = [99]
    return (parts, node["id"])


# ── Merge proofs into parent theorems ───────────────────────────────────────
def merge_proofs(nodes, edges):
    """Collapse proof nodes into their parent theorem.

    Returns:
      display_nodes: list of non-proof nodes, each with optional 'proof_info'
      display_edges: edges with proof endpoints redirected to theorem
      proof_map: {proof_id: theorem_id}
    """
    node_by_id = {n["id"]: n for n in nodes}
    proof_map = {}  # proof_id -> theorem_id

    for n in nodes:
        if n["type"] == "proof":
            # Support both "proves" and "parent" fields for linking to parent theorem
            target_id = n.get("proves") or n.get("parent") or ""
            if target_id in node_by_id:
                proof_map[n["id"]] = target_id

    # Also find proofs linked via "proves" edges (e.g., theorem -> proof edge)
    for e in edges:
        if e.get("type") == "proves":
            src, tgt = e["source"], e["target"]
            # Could be theorem->proof or proof->theorem depending on convention
            if src in node_by_id and node_by_id.get(tgt, {}).get("type") == "proof":
                if tgt not in proof_map:
                    proof_map[tgt] = src
            elif tgt in node_by_id and node_by_id.get(src, {}).get("type") == "proof":
                if src not in proof_map:
                    proof_map[src] = tgt

    # Attach proof info to parent theorem (reset first to avoid duplication on repeated calls)
    for n in nodes:
        if n.get("type") != "proof":
            node_by_id[n["id"]]["proof_info"] = []

    display_nodes = []
    for n in nodes:
        if n["id"] in proof_map:
            parent_id = proof_map[n["id"]]
            parent = node_by_id[parent_id]
            parent.setdefault("proof_info", [])
            parent["proof_info"].append(n.get("proof_strategy", ""))
            continue
        display_nodes.append(n)

    # Redirect edges: replace proof_id with its theorem_id
    display_edges = []
    seen = set()
    for e in edges:
        s = proof_map.get(e["source"], e["source"])
        t = proof_map.get(e["target"], e["target"])
        if s == t:
            continue  # skip self-loops from merging
        key = (s, t)
        if key not in seen:
            display_edges.append({"source": s, "target": t,
                                  "type": e.get("type", ""),
                                  "note": e.get("note", "")})
            seen.add(key)

    return display_nodes, display_edges, proof_map


# ── Foundation graph linking (shared by PNG and HTML) ────────────────────────

def _resolve_foundation_path(foundation_path=None):
    """Find the best available foundation index path."""
    if foundation_path is not None:
        return foundation_path
    # Auto-detect from common locations
    candidates = [
        Path("/mnt/g/My Drive/Research/Automath/naturalproofs/clean_foundation.json"),
        Path("/sci/labs/orzuk/orzuk/projects/Authomathics/naturalproofs/clean_foundation.json"),
    ]
    # Also try via config.py DATA_DIR
    try:
        from config import DATA_DIR
        candidates.insert(0, Path(str(DATA_DIR)) / "naturalproofs" / "clean_foundation.json")
    except ImportError:
        pass
    for c in candidates:
        if c.exists():
            return str(c)
    return None  # will fall back to built-in WELL_KNOWN


def compute_foundation_links(nodes_raw, base_ids, foundation_path=None):
    """Compute foundation ghost map: foundation_name -> list of base node IDs.

    Shared by draw_dag (PNG rendering) and generate_interactive_html.

    Args:
        nodes_raw: list of all node dicts (including proofs, proof steps).
        base_ids: set of node IDs for base nodes (definitions, theorems, lemmas, etc.)
        foundation_path: path to clean_foundation.json, or None for auto-detect.

    Returns:
        (ghost_map, case1_matches):
            ghost_map: {foundation_name: [base_node_ids]} — for ghost node rendering
            case1_matches: {base_node_id: [foundation_names]} — for inline annotations
    """
    from link_to_foundation import build_foundation_index, link_paper

    fg_path = _resolve_foundation_path(foundation_path)
    fg_index = build_foundation_index(fg_path)
    matches = link_paper(nodes_raw, fg_index, min_term_len=5)

    ghost_map = {}   # foundation_name -> set of base node IDs
    case1 = {}       # base_node_id -> list of foundation names

    for m in matches:
        nid = m["node_id"]
        fname = m["foundation_name"]
        if nid in base_ids:
            # Direct match on a base node
            ghost_map.setdefault(fname, set()).add(nid)
            case1.setdefault(nid, []).append(fname)
        else:
            # Match on proof step — trace to parent base node
            parent = nid
            for nr in nodes_raw:
                if nr["id"] == parent:
                    if nr.get("parent_proof"):
                        for nr2 in nodes_raw:
                            if nr2["id"] == nr["parent_proof"] and nr2.get("proves"):
                                parent = nr2["proves"]
                                break
                        break
                    if nr.get("proves") and nr["proves"] in base_ids:
                        parent = nr["proves"]
                        break
            if parent in base_ids:
                ghost_map.setdefault(fname, set()).add(parent)
                case1.setdefault(parent, []).append(fname)

    # Convert sets to lists
    ghost_map = {k: sorted(v) for k, v in ghost_map.items()}
    case1 = {k: sorted(set(v)) for k, v in case1.items()}
    return ghost_map, case1


def draw_foundation_ghosts(ax, ghost_map, node_rect):
    """Draw foundation ghost nodes and their dashed edges on a matplotlib axes.

    Args:
        ax: matplotlib axes.
        ghost_map: {foundation_name: [base_node_ids]} from compute_foundation_links.
        node_rect: {node_id: (x, y, w, h)} from draw_dag layout.
    """
    if not ghost_map or not node_rect:
        return {}

    from matplotlib.patches import FancyArrowPatch

    all_tops = [by + bh for (bx, by, bw, bh) in node_rect.values()]
    ghost_y_top = max(all_tops) + LEVEL_GAP_Y * 0.8
    ghost_w = MIN_BOX_W * 1.1
    ghost_h = HEADER_H + LINE_H * 1.5 + PADDING
    ghost_names = sorted(ghost_map.keys())
    total_ghost_w = len(ghost_names) * ghost_w + (len(ghost_names) - 1) * BOX_GAP_X * 0.5
    ghost_start_x = -total_ghost_w / 2

    ghost_rects = {}
    for gi, gname in enumerate(ghost_names):
        gx = ghost_start_x + gi * (ghost_w + BOX_GAP_X * 0.5)
        gy = ghost_y_top

        # Ghost box (dashed gray)
        grect = FancyBboxPatch(
            (gx, gy - ghost_h), ghost_w, ghost_h,
            boxstyle="round,pad=0.05",
            facecolor="#E8E8E8", edgecolor="#777777",
            linewidth=1.5, linestyle=(0, (8, 6)),
            gid=f"ghost_box_{gi}",
        )
        ax.add_patch(grect)
        # Header bar
        gheader = FancyBboxPatch(
            (gx, gy - HEADER_H), ghost_w, HEADER_H,
            boxstyle="round,pad=0.05",
            facecolor="#777777", edgecolor="#777777",
            linewidth=0,
            gid=f"ghost_header_{gi}",
        )
        ax.add_patch(gheader)
        # Name text
        short_name = gname if len(gname) <= 22 else gname[:19] + "..."
        ax.text(gx + ghost_w / 2, gy - HEADER_H / 2, short_name,
                ha="center", va="center", fontsize=12, fontweight="bold",
                color="white", gid=f"ghost_text_{gi}")
        # References text
        refs_str = "→ " + ", ".join(ghost_map[gname])
        ax.text(gx + ghost_w / 2, gy - HEADER_H - LINE_H * 0.7, refs_str,
                ha="center", va="center", fontsize=10, color="#555",
                gid=f"ghost_refs_{gi}")

        ghost_rects[gname] = (gx, gy - ghost_h, ghost_w, ghost_h)

        # Dashed edges to target nodes
        for ti, target_id in enumerate(ghost_map[gname]):
            if target_id in node_rect:
                tx, ty, tw, th = node_rect[target_id]
                arrow = FancyArrowPatch(
                    (gx + ghost_w / 2, gy - ghost_h),
                    (tx + tw / 2, ty + th),
                    arrowstyle="-|>,head_length=0.8,head_width=0.35",
                    color="#999999", lw=1.5,
                    linestyle=(0, (8, 6)),  # 8pt dash, 6pt gap (more visible than "dashed")
                    connectionstyle="arc3,rad=0.05",
                    shrinkA=3, shrinkB=3,
                    gid=f"ghost_edge_{gi}_{ti}",
                )
                ax.add_patch(arrow)

    return ghost_rects


def draw_legend(ax, node_data, node_rect, show_foundation=False,
                has_ghosts=False, font_scale=1.0):
    """Draw the legend in the bottom-right, shifting right only if overlapping nodes."""
    legend_handles = []
    for ntype, cols in NODE_COLORS.items():
        if any(node_data[nid].get("type") == ntype for nid in node_data):
            legend_handles.append(
                mpatches.Patch(facecolor=cols["body"], edgecolor=cols["header"],
                               linewidth=1.5, label=ntype.title())
            )
    legend_handles.append(
        plt.Line2D([0], [0], color="#666666", lw=2.5, marker=">",
                   markersize=10, label="A supports B")
    )
    if show_foundation and has_ghosts:
        legend_handles.append(
            mpatches.Patch(facecolor="#E8E8E8", edgecolor="#777777",
                           linewidth=1.5, linestyle="dashed",
                           label="Foundation (ext.)")
        )

    if not node_rect:
        ax.legend(handles=legend_handles, loc="lower right",
                  fontsize=14 * font_scale, frameon=False,
                  title="Node types", title_fontsize=16 * font_scale)
        return

    # Compute legend size: ~15% of graph width, height depends on # items
    all_lefts = [bx for (bx, by, bw, bh) in node_rect.values()]
    all_rights = [bx + bw for (bx, by, bw, bh) in node_rect.values()]
    all_bottoms = [by for (bx, by, bw, bh) in node_rect.values()]
    all_tops = [by + bh for (bx, by, bw, bh) in node_rect.values()]

    graph_w = max(all_rights) - min(all_lefts)
    graph_h = max(all_tops) - min(all_bottoms)
    legend_w = graph_w * 0.15
    n_items = len(legend_handles)
    legend_h = n_items * LINE_H * 1.8 * font_scale + HEADER_H * 2 * font_scale

    # Position: bottom-right, legend bottom aligned with lowest node bottom
    legend_bottom = min(all_bottoms)
    legend_x = max(all_rights) - legend_w

    # Check overlap with nodes
    overlap = False
    for nid, (bx, by, bw, bh) in node_rect.items():
        node_right = bx + bw
        node_top = by + bh
        node_bottom = by
        if (node_right > legend_x - BOX_GAP_X and
            bx < legend_x + legend_w + BOX_GAP_X and
            node_top > legend_bottom and
            node_bottom < legend_bottom + legend_h):
            overlap = True
            break

    if overlap:
        legend_x = max(all_rights) + BOX_GAP_X * 2

    # Anchor legend by its bottom-left corner
    leg = ax.legend(handles=legend_handles, loc="lower left",
                    bbox_to_anchor=(legend_x, legend_bottom),
                    bbox_transform=ax.transData,
                    fontsize=14 * font_scale, frameon=False,
                    title="Node types", title_fontsize=16 * font_scale)


# ── Drawing ─────────────────────────────────────────────────────────────────
def draw_dag(nodes_raw, edges_raw, out_path, figsize=None, metadata=None,
             resolution="standard", show_legend=True, show_foundation=False,
             foundation_path=None):
    """Main entry: draw a layered DAG from student-format nodes/edges.

    resolution:
      "standard" — collapse proofs into theorem boxes, hide equations/proof_steps
      "full"     — show all nodes including proofs, equations, proof_steps as separate nodes

    show_foundation:
      If True, draw ghost nodes for external foundation dependencies above the
      main graph (gray dashed boxes with dashed arrows to paper nodes).
      Default False preserves the previous behaviour of hiding them in the PNG.

    foundation_path:
      Optional path to clean_foundation.json.  When *None* the code tries the
      default location (/mnt/g/My Drive/Research/Automath/naturalproofs/clean_foundation.json)
      and falls back to the built-in WELL_KNOWN dictionary.
    """
    if resolution == "full":
        # Full resolution: no merging, show everything
        nodes = list(nodes_raw)
        edges = list(edges_raw)
        proof_map = {}
    else:
        # Standard: collapse proofs AND filter out equations/proof_steps
        nodes, edges, proof_map = merge_proofs(nodes_raw, edges_raw)
        hidden_types = {"equation", "proof_step"}
        hidden_ids = {n["id"] for n in nodes if n.get("type") in hidden_types}
        nodes = [n for n in nodes if n.get("type") not in hidden_types]
        edges = [e for e in edges
                 if e["source"] not in hidden_ids and e["target"] not in hidden_ids]
    depth = compute_dag_depth(nodes, edges)

    # Group by depth level
    levels = defaultdict(list)
    for n in nodes:
        levels[depth[n["id"]]].append(n)

    # Sort within each level by section
    for d in levels:
        levels[d].sort(key=_section_sort_key)

    max_depth = max(levels.keys()) if levels else 0
    max_width = max(len(v) for v in levels.values()) if levels else 1

    # ── Box dimensions ──
    # Layout constants are module-level (shared with draw_foundation_ghosts)
    pass
    # CHARS_PER_UNIT defined at module level
    MAX_LINES_PER_SECTION = 3

    def _content_lines(n):
        """Get all content text lines for a node (for width estimation).

        Uses the same _prepare_for_display pipeline as the drawing code so
        width estimates are consistent with what gets rendered.
        """
        ntype = n.get("type", "")
        lines = []
        name = n.get("name") or ""
        lines.append(f"{n['id']}: {name}" if name else n['id'])
        if ntype in ("theorem", "lemma", "corollary", "proposition", "claim"):
            for a in (n.get("assumptions") or [])[:MAX_LINES_PER_SECTION]:
                lines.append(_shorten(_prepare_for_display(a), 60))
            for c in (n.get("conclusions") or [])[:MAX_LINES_PER_SECTION]:
                lines.append(_shorten(_prepare_for_display(c), 60))
            for ps in (n.get("proof_info") or []):
                if ps: lines.append(_shorten(_prepare_for_display(f"Proof: {ps}"), 60))
        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            for x in (n.get("input") or []): lines.append(_shorten(x, 60))
            for x in (n.get("output") or []): lines.append(_shorten(x, 60))
        else:
            raw = n.get("statement", "") or n.get("proof_strategy", "") or ""
            lines.append(_shorten(_prepare_for_display(raw), 150))
        return lines

    # ── First pass: compute each node's ideal width ──
    # Strategy: find the MINIMUM box width that fits all text.
    # 1. Start with a candidate width (based on content estimate, capped to MAX_BOX_W)
    # 2. Wrap all text to that width
    # 3. Binary-search downward for the tightest width where nothing overflows
    node_width = {}
    node_data = {}

    def _get_all_wrap_texts(n):
        """Get all texts that need wrapping for a node."""
        ntype = n.get("type", "")
        texts = []
        if ntype in ("theorem", "lemma", "corollary", "proposition", "claim"):
            for a in (n.get("assumptions") or [])[:MAX_LINES_PER_SECTION]:
                texts.append(_prepare_for_display(a))
            for c in (n.get("conclusions") or [])[:MAX_LINES_PER_SECTION]:
                texts.append(_prepare_for_display(c))
            for ps in (n.get("proof_info") or []):
                if ps:
                    texts.append(_prepare_for_display(f"Proof: {ps}"))
        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            for x in (n.get("input") or []):
                texts.append(_shorten(x, 100))
            for x in (n.get("output") or []):
                texts.append(_shorten(x, 100))
        else:
            raw = n.get("statement", "") or n.get("proof_strategy", "") or ""
            texts.append(_prepare_for_display(raw))
        return texts

    def _wrap_all_and_measure(texts, wrap_chars):
        """Wrap all texts to wrap_chars width and return max display width of resulting lines."""
        max_dw = 0
        for t in texts:
            lines = _wrap(t, wrap_chars) or [t[:wrap_chars] if t else ""]
            for line in lines:
                dw = _display_width(line)
                if dw > max_dw:
                    max_dw = dw
        return max_dw

    def _find_tight_width(n):
        """Find the minimum box width that fits all text without overflow."""
        texts = _get_all_wrap_texts(n)
        if not texts or all(not t for t in texts):
            return MIN_BOX_W

        name = n.get("name") or ""
        nid = n["id"]

        # Bullet prefix overhead: theorem/algorithm nodes render "• " before
        # each line (+2 display chars) plus the PADDING+0.1 indent
        ntype = n.get("type", "")
        has_bullets = ntype in ("theorem", "lemma", "corollary", "proposition",
                                "claim", "algorithm")
        bullet_extra = 2 if has_bullets else 0
        # chars_overhead: padding on both sides + bullet prefix
        chars_overhead = 4 + bullet_extra

        def _needed_w(max_dw):
            """Convert max display-width (chars) to data-unit width needed."""
            return (max_dw + bullet_extra) / CHARS_PER_UNIT + 2 * PADDING + 0.15

        def _header_w_for_box(w):
            """Header width needed given box width w (renderer shows more name
            chars for wider boxes). Header font is 14-bold ~25% wider than body.
            Cap name display to 30 chars to prevent runaway expansion."""
            header_chars = max(len(nid) + 4, int(w * CHARS_PER_UNIT) - 2)
            avail = max(6, header_chars - len(nid) - 2)
            avail = min(avail, 30)  # cap to prevent circular expansion
            shown = len(nid) + 2 + min(avail, len(name))
            HEADER_CPU = 9.0  # chars/unit for fontsize-14 bold
            return shown / HEADER_CPU + 2 * PADDING + 0.15

        # --- Step 1: find body width via binary search ---
        # Initial header estimate (30-char cap, before circular expansion)
        name_cap = min(len(name), 30)
        init_header_w = (len(nid) + 2 + name_cap) / 9.0 + 2 * PADDING + 0.15

        lo_w = max(MIN_BOX_W, init_header_w)
        hi_w = MAX_BOX_W

        # Check if even MAX_BOX_W is too narrow (math tokens wider than MAX)
        hi_chars = max(20, int(hi_w * CHARS_PER_UNIT) - chars_overhead)
        max_dw_at_hi = _wrap_all_and_measure(texts, hi_chars)
        needed_at_hi = _needed_w(max_dw_at_hi)
        if needed_at_hi > hi_w:
            body_w = min(needed_at_hi * 1.02, MAX_BOX_W * 1.5)
        else:
            # Binary search for minimum width where body text fits
            for _ in range(10):
                mid_w = (lo_w + hi_w) / 2
                mid_chars = max(20, int(mid_w * CHARS_PER_UNIT) - chars_overhead)
                max_dw = _wrap_all_and_measure(texts, mid_chars)
                needed = _needed_w(max_dw)
                if needed <= mid_w:
                    hi_w = mid_w
                else:
                    lo_w = mid_w
            body_w = hi_w * 1.01

        # --- Step 2: resolve header/body circular dependency ---
        # Given body_w, the renderer may show more name chars. Iterate to
        # convergence (typically 1-2 rounds).
        w = max(MIN_BOX_W, body_w)
        for _ in range(3):
            hw = _header_w_for_box(w)
            w_new = max(body_w, hw)
            if w_new <= w + 0.01:
                break
            w = w_new

        return max(MIN_BOX_W, w)

    for n in nodes:
        nid = n["id"]
        node_data[nid] = n
        node_width[nid] = _find_tight_width(n)

    # ── Second pass: compute heights and positions ──
    # Widths were already optimized in the first pass via _find_tight_width.
    node_pos = {}
    node_rect = {}

    for d in range(max_depth + 1):
        row = levels.get(d, [])
        # Compute row width using actual node widths
        row_width = sum(node_width[n["id"]] for n in row) + max(0, len(row) - 1) * BOX_GAP_X
        x_cursor = -row_width / 2

        for n in row:
            nid = n["id"]
            w = node_width[nid]
            wrap_w = max(20, int(w * CHARS_PER_UNIT) - 4)  # subtract margin for padding + bullet
            cy_top = -d * LEVEL_GAP_Y
            ntype = n.get("type", "")

            # Line height: tall math > inline math > plain text
            def _line_h(line):
                if _has_tall_math(line):
                    return LINE_H * 2.5
                elif "$" in str(line):
                    return LINE_H * 1.5
                return LINE_H

            if ntype in ("theorem", "lemma", "corollary", "proposition", "claim"):
                assumptions = n.get("assumptions", [])
                conclusions = n.get("conclusions", [])
                proof_strategies = n.get("proof_info", [])

                # Wrap each item to box width, then flatten
                assume_lines = []
                for a in assumptions[:MAX_LINES_PER_SECTION]:
                    assume_lines.extend(_wrap(_prepare_for_display(a), wrap_w) or [a[:wrap_w]])
                if len(assumptions) > MAX_LINES_PER_SECTION:
                    assume_lines.append(f"... +{len(assumptions)-MAX_LINES_PER_SECTION} more")
                conclude_lines = []
                for c in conclusions[:MAX_LINES_PER_SECTION]:
                    conclude_lines.extend(_wrap(_prepare_for_display(c), wrap_w) or [c[:wrap_w]])
                if len(conclusions) > MAX_LINES_PER_SECTION:
                    conclude_lines.append(f"... +{len(conclusions)-MAX_LINES_PER_SECTION} more")
                proof_lines = []
                for ps in proof_strategies:
                    if ps:
                        proof_lines.extend(_wrap(_prepare_for_display(f"Proof: {ps}"), wrap_w))

                assume_heights = sum(_line_h(l) for l in assume_lines) or LINE_H
                conclude_heights = sum(_line_h(l) for l in conclude_lines) or LINE_H
                n_proof = len(proof_lines)

                h = HEADER_H + PADDING
                h += assume_heights + PADDING
                h += conclude_heights + PADDING
                if n_proof > 0:
                    h += n_proof * LINE_H + PADDING
                h += PADDING
            elif ntype == "algorithm" and (n.get("input") or n.get("output")):
                in_lines = [_shorten(x, 100) for x in (n.get("input") or ["(none)"])]
                out_lines = [_shorten(x, 100) for x in (n.get("output") or ["(none)"])]
                h = HEADER_H + PADDING
                h += len(in_lines) * LINE_H + PADDING
                h += len(out_lines) * LINE_H + PADDING
                h += PADDING
            else:
                # Use statement, or name as fallback (e.g., proofs with descriptive names)
                raw = n.get("statement", "") or n.get("proof_strategy", "") or ""
                stmt = _prepare_for_display(raw)
                stmt_lines = _wrap(stmt, wrap_w)[:5]
                stmt_height = sum(_line_h(l) for l in stmt_lines) if stmt_lines else LINE_H
                h = HEADER_H + stmt_height + 2 * PADDING

            # Width was already optimized in the first pass (_find_tight_width).
            # No expansion needed here.

            node_pos[nid] = (x_cursor + w / 2, cy_top - h / 2)
            node_rect[nid] = (x_cursor, cy_top - h, w, h)
            x_cursor += w + BOX_GAP_X

    # ── Figure ── (auto-size based on content)
    if figsize is None:
        avg_w = sum(node_width.values()) / max(len(node_width), 1)
        fw = max(max_width * (avg_w + BOX_GAP_X) + 4, 16)
        fh = max((max_depth + 1) * LEVEL_GAP_Y + 4, 12)
        figsize = (fw, fh)

    # Scale factor for title/legend: scale with figure AREA so they look
    # consistent regardless of whether the figure is wide or tall.
    # Base: 16x12 = 192 sq inches. Use sqrt so scaling is moderate.
    import math
    _fig_area = figsize[0] * figsize[1]
    _font_scale = math.sqrt(_fig_area / 192.0)

    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Draw edges first (behind boxes) ──
    for e in edges:
        src, tgt = e["source"], e["target"]
        if src not in node_rect or tgt not in node_rect:
            continue
        sx, sy_bottom, sw, sh = node_rect[src]
        tx, ty_bottom, tw, th = node_rect[tgt]

        x0 = sx + sw / 2
        y0 = sy_bottom  # bottom of source
        x1 = tx + tw / 2
        y1 = ty_bottom + th  # top of target

        ax.annotate(
            "", xy=(x1, y1), xytext=(x0, y0),
            arrowprops=dict(
                arrowstyle="-|>,head_length=1.2,head_width=0.6",
                color="#333333",
                lw=2.5,
                connectionstyle="arc3,rad=0.08" if abs(x0 - x1) > 0.5 else "arc3,rad=0",
                shrinkA=3, shrinkB=3,
            ),
        )

    # ── Draw boxes ──
    for nid, (bx, by, bw, bh) in node_rect.items():
        n = node_data[nid]
        ntype = n.get("type", "")
        colors = NODE_COLORS.get(ntype, DEFAULT_COLOR)

        # Main box background (gid for SVG click handling)
        rect = FancyBboxPatch(
            (bx, by), bw, bh,
            boxstyle="round,pad=0.05",
            facecolor=colors["body"],
            edgecolor=colors["header"],
            linewidth=1.5,
            gid=f"node_{nid}",
        )
        ax.add_patch(rect)

        cursor_y = by + bh  # start from top

        # Header — truncate name to box width, but always show full node ID
        # Use ~9 chars/unit for bold header font (vs 12 for body font)
        name_str = n.get("name") or ""
        header_chars = max(len(nid) + 4, int(node_width.get(nid, 4.0) * 9) - 2)
        header_text = f"{nid}"
        if name_str:
            avail = max(6, header_chars - len(nid) - 2)
            header_text += f": {_shorten(name_str, avail)}"
        # Choose header font size to fit: shrink if header text is long
        header_fontsize = 14
        if len(header_text) > header_chars:
            header_fontsize = max(9, 14 * header_chars / len(header_text))

        header_rect = FancyBboxPatch(
            (bx, cursor_y - HEADER_H), bw, HEADER_H,
            boxstyle="round,pad=0.05",
            facecolor=colors["header"],
            edgecolor=colors["header"],
            linewidth=0,
        )
        ax.add_patch(header_rect)
        ax.text(bx + bw / 2, cursor_y - HEADER_H / 2, header_text,
                ha="center", va="center", fontsize=header_fontsize, fontweight="bold",
                color="white")
        cursor_y -= HEADER_H + PADDING

        # Line height helper — must match height computation exactly
        def _line_h_draw(line):
            if _has_tall_math(line):
                return LINE_H * 2.5
            elif "$" in line:
                return LINE_H * 1.5
            return LINE_H

        if ntype in ("theorem", "lemma", "corollary", "proposition", "claim"):
            # Wrap text to box width (same logic as height computation)
            dyn_wrap = max(20, int(node_width.get(nid, 4.0) * CHARS_PER_UNIT) - 4)
            assumptions = n.get("assumptions", [])
            a_lines = []
            for a in assumptions[:MAX_LINES_PER_SECTION]:
                a_lines.extend(_wrap(_prepare_for_display(a), dyn_wrap) or [a[:dyn_wrap]])
            if len(assumptions) > MAX_LINES_PER_SECTION:
                a_lines.append(f"... +{len(assumptions)-MAX_LINES_PER_SECTION} more")
            if not a_lines:
                a_lines = ["(none)"]

            conclusions = n.get("conclusions", [])
            c_lines = []
            for c in conclusions[:MAX_LINES_PER_SECTION]:
                c_lines.extend(_wrap(_prepare_for_display(c), dyn_wrap) or [c[:dyn_wrap]])
            if len(conclusions) > MAX_LINES_PER_SECTION:
                c_lines.append(f"... +{len(conclusions)-MAX_LINES_PER_SECTION} more")
            if not c_lines:
                c_lines = ["(none)"]

            # Assumptions
            ax.text(bx + PADDING, cursor_y, "Assume:",
                    ha="left", va="top", fontsize=13, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in a_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=12, color="#222",
                        fontstyle="italic")
                cursor_y -= _line_h_draw(line)

            cursor_y -= PADDING * 0.3

            # Divider line
            ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                    color=colors["header"], lw=0.5, alpha=0.4)

            # Conclusions
            ax.text(bx + PADDING, cursor_y, "Conclude:",
                    ha="left", va="top", fontsize=13, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in c_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=12, color="#222")
                cursor_y -= _line_h_draw(line)

            # Proof strategy (if merged)
            proof_strategies = n.get("proof_info", [])
            if proof_strategies:
                cursor_y -= PADDING * 0.2
                ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.1] * 2,
                        color="#999", lw=0.5, alpha=0.4)
                for ps in proof_strategies:
                    if ps:
                        for pline in _wrap(_prepare_for_display(f"Proof: {ps}"), dyn_wrap):
                            ax.text(bx + PADDING, cursor_y, pline,
                                    ha="left", va="top", fontsize=10.5,
                                    color="#444", fontstyle="italic")
                            cursor_y -= LINE_H

        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            # Algorithm with input/output
            dyn_wrap = max(20, int(node_width.get(nid, 4.0) * CHARS_PER_UNIT) - 4)
            in_lines = [_shorten(x, dyn_wrap) for x in (n.get("input") or ["(none)"])]
            out_lines = [_shorten(x, 70) for x in (n.get("output") or ["(none)"])]

            ax.text(bx + PADDING, cursor_y, "Input:",
                    ha="left", va="top", fontsize=13, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in in_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=12, color="#222")
                cursor_y -= LINE_H
            cursor_y -= PADDING * 0.3
            ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                    color=colors["header"], lw=0.5, alpha=0.4)
            ax.text(bx + PADDING, cursor_y, "Output:",
                    ha="left", va="top", fontsize=13, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in out_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=12, color="#222")
                cursor_y -= LINE_H

        else:
            # Simple box: wrap statement/name text to box width (up to 5 lines)
            dyn_wrap = max(20, int(node_width.get(nid, 4.0) * CHARS_PER_UNIT) - 4)
            raw = n.get("statement", "") or n.get("proof_strategy", "") or ""
            stmt = _prepare_for_display(raw)
            stmt_lines = _wrap(stmt, dyn_wrap)[:5]
            if not stmt_lines:
                stmt_lines = [""]
            for line in stmt_lines:
                ax.text(bx + PADDING, cursor_y, line,
                        ha="left", va="top", fontsize=12, color="#222")
                cursor_y -= _line_h_draw(line)

    # ── Ghost nodes (external foundation dependencies) ──
    _base_ids = set(node_data.keys())
    _ghost_map, _case1_matches = compute_foundation_links(
        nodes_raw, _base_ids, foundation_path=foundation_path)

    if show_foundation and _ghost_map:
        draw_foundation_ghosts(ax, _ghost_map, node_rect)

    # ── Misc/Orphan equations box ──
    # Count orphan equations from the FULL node list (before filtering)
    all_eq_nodes = [n for n in nodes_raw if n.get("type") == "equation"]
    orphan_eqs = [n for n in all_eq_nodes if n.get("context") == "orphan" or not n.get("context")]
    # Also count equations not connected to any displayed node
    displayed_ids = set(node_data.keys())
    edge_targets = set()
    for e in edges_raw:
        if e["source"] in displayed_ids:
            edge_targets.add(e["target"])
        if e["target"] in displayed_ids:
            edge_targets.add(e["source"])
    truly_orphan = [n for n in all_eq_nodes if n["id"] not in edge_targets and n["id"] not in displayed_ids]
    n_orphan = len(set(n["id"] for n in orphan_eqs + truly_orphan))

    if n_orphan > 0 and node_rect:
        # Position: same height as the bottom layer, to the right
        misc_w = MAX_BOX_W
        misc_h = HEADER_H + LINE_H + 2 * PADDING
        all_bottoms = [by for (bx, by, bw, bh) in node_rect.values()]
        all_rights = [bx + bw for (bx, by, bw, bh) in node_rect.values()]
        # Find the bottom-most row's top position
        bottom_y = min(all_bottoms)
        bottom_tops = [by + bh for (bx, by, bw, bh) in node_rect.values() if abs(by - bottom_y) < LEVEL_GAP_Y * 0.3]
        misc_top = max(bottom_tops) if bottom_tops else min(all_bottoms) + 1.0
        misc_y = misc_top - misc_h
        misc_x = max(all_rights) + BOX_GAP_X

        misc_rect = FancyBboxPatch(
            (misc_x, misc_y), misc_w, misc_h,
            boxstyle="round,pad=0.05",
            facecolor="#F2E6D9",
            edgecolor="#795548",
            linewidth=1.5,
            gid="node___orphan__",
        )
        ax.add_patch(misc_rect)

        header_rect = FancyBboxPatch(
            (misc_x, misc_y + misc_h - HEADER_H), misc_w, HEADER_H,
            boxstyle="round,pad=0.05",
            facecolor="#795548",
            edgecolor="#795548",
            linewidth=0,
        )
        ax.add_patch(header_rect)
        ax.text(misc_x + misc_w / 2, misc_y + misc_h - HEADER_H / 2,
                f"Misc ({n_orphan} equations)",
                ha="center", va="center", fontsize=14, fontweight="bold", color="white")
        ax.text(misc_x + misc_w / 2, misc_y + PADDING + LINE_H / 2,
                "Unconnected equations",
                ha="center", va="center", fontsize=10.5, color="#555")

    # ── Legend ──
    if show_legend:
        draw_legend(ax, node_data, node_rect, show_foundation=show_foundation,
                    has_ghosts=bool(_ghost_map), font_scale=_font_scale)

    # ── Title (from metadata if available) ──
    if metadata and metadata.get("chapter_title"):
        ch = metadata.get("chapter", "")
        title = f"Chapter {ch}: {metadata['chapter_title']} — Knowledge Graph"
    elif metadata and metadata.get("title"):
        title = f"{metadata['title']} — Knowledge Graph"
    else:
        title = "Knowledge Graph (DAG)"
    ax.set_title(title, fontsize=24 * _font_scale, fontweight="bold",
                  pad=20 * _font_scale)

    ax.autoscale()
    ax.margins(0.05)
    try:
        plt.tight_layout()
    except Exception:
        pass  # tight_layout can fail on complex math; savefig still works
    plt.savefig(str(out_path), dpi=200, bbox_inches="tight", facecolor="white")

    # Also save SVG if requested (for interactive HTML)
    svg_path = str(out_path).replace('.png', '.svg') if str(out_path).endswith('.png') else None
    if svg_path:
        # Set gid on each node rectangle for click handling
        for nid, (bx, by, bw, bh) in node_rect.items():
            # The FancyBboxPatch was already added; we tag it via node_rect for the HTML wrapper
            pass
        plt.savefig(svg_path, format='svg', bbox_inches="tight", facecolor="white")

    plt.close(fig)

    return len(nodes), len(edges), node_rect, node_data


def _classify_and_merge(nodes, edges):
    """Merge proofs into parent theorems. Separate equations/proof_steps."""
    node_by_id = {n["id"]: n for n in nodes}

    proof_map = {}
    for n in nodes:
        if n.get("type") != "proof" and n["id"] in node_by_id:
            node_by_id[n["id"]]["proof_info"] = []
    for n in nodes:
        if n.get("type") == "proof" and n.get("proves") and n["proves"] in node_by_id:
            proof_map[n["id"]] = n["proves"]
            parent = node_by_id[n["proves"]]
            parent.setdefault("proof_info", [])
            if n.get("proof_strategy"):
                parent["proof_info"].append(n["proof_strategy"])

    base_nodes, proof_steps, equations, orphan_eqs = [], [], [], []
    has_edge = set()
    for e in edges:
        has_edge.add(e["source"])
        has_edge.add(e["target"])

    for n in nodes:
        if n["id"] in proof_map:
            continue
        if n["type"] == "proof_step":
            proof_steps.append(n)
        elif n["type"] == "equation":
            if n["id"] in has_edge:
                equations.append(n)
            else:
                orphan_eqs.append(n)
        else:
            base_nodes.append(n)

    base_ids = {n["id"] for n in base_nodes}
    base_edges = []
    seen = set()
    for e in edges:
        s = proof_map.get(e["source"], e["source"])
        t = proof_map.get(e["target"], e["target"])
        if s == t or s not in base_ids or t not in base_ids:
            continue
        key = (s, t)
        if key not in seen:
            base_edges.append({"source": s, "target": t})
            seen.add(key)

    step_chains = {}
    for ps in proof_steps:
        parent = ps.get("parent_proof", "")
        thm_id = proof_map.get(parent, parent)
        step_chains.setdefault(thm_id, []).append(ps)

    eq_map = {}
    for eq in equations:
        for e in edges:
            if e["source"] == eq["id"] and e["target"] in base_ids:
                eq_map.setdefault(e["target"], []).append(eq)
            if e["target"] == eq["id"] and e["source"] in base_ids:
                eq_map.setdefault(e["source"], []).append(eq)

    return base_nodes, base_edges, step_chains, eq_map, orphan_eqs


def generate_interactive_html(data, svg_path, html_path):
    """Wrap an SVG figure in an interactive HTML page with click-to-expand detail panel."""
    import json as _json
    from html import escape as _esc

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    metadata = data.get("metadata", {})

    base_nodes, base_edges, step_chains, eq_map, orphan_eqs = _classify_and_merge(nodes, edges)

    # Foundation graph linking (shared computation with draw_dag)
    base_ids = {n["id"] for n in base_nodes}
    case2_ghosts, case1_matches = compute_foundation_links(nodes, base_ids)

    # Build detail data
    js_details = {}
    for n in base_nodes:
        nid = n["id"]
        js_details[nid] = {
            "name": n.get("name", ""),
            "type": n.get("type", ""),
            "section": n.get("section", ""),
            "statement": n.get("statement", ""),
            "assumptions": n.get("assumptions", []),
            "conclusions": n.get("conclusions", []),
            "proof_info": n.get("proof_info", []),
            "input": n.get("input", []),
            "output": n.get("output", []),
            "steps": [{"id": s["id"], "statement": s.get("statement","")}
                      for s in step_chains.get(nid, [])],
            "equations": [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section",""),
                          "context": e.get("context",""), "parent_step": e.get("parent_step","")}
                          for e in eq_map.get(nid, [])],
        }

    js_orphans = [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section","")}
                  for e in orphan_eqs]

    ch = metadata.get("chapter", "")
    ch_title = metadata.get("chapter_title", "")
    title = f"Chapter {ch}: {ch_title}" if ch_title else "Knowledge Graph"

    # Read SVG content
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    # Make node rects clickable by adding onclick via regex
    import re
    def _add_onclick(m):
        nid = m.group(1)
        return 'id="node_' + nid + '" onclick="showDetail(\'' + nid + '\')" style="cursor:pointer;"'
    svg_content = re.sub(r'id="node_([^"]+)"', _add_onclick, svg_content)

    # Add foundation links to detail data
    for nid, fnames in case1_matches.items():
        if nid in js_details:
            js_details[nid]["foundation_links"] = list(set(fnames))

    details_json = _json.dumps(js_details, ensure_ascii=True)
    orphans_json = _json.dumps(js_orphans, ensure_ascii=True)
    ghosts_json = _json.dumps(case2_ghosts, ensure_ascii=True)
    case1_json = _json.dumps(case1_matches, ensure_ascii=True)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<script>MathJax = {{tex: {{inlineMath: [['$','$']]}}, startup: {{typeset: false}}}};</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; background: #fafafa; }}
#header {{ background: #2c3e50; color: white; padding: 10px 24px; display: flex; align-items: center; justify-content: space-between; }}
#header h1 {{ margin: 0; font-size: 18px; }}
#header .hint {{ font-size: 12px; color: #aaa; font-style: italic; margin-left: 12px; }}
#controls button {{ padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; background: #34495e; color: white; margin-left: 8px; }}
#controls button:hover {{ background: #4a6785; }}
.legend {{ display: flex; gap: 14px; flex-wrap: wrap; padding: 8px 24px; background: #f5f5f5; border-bottom: 1px solid #eee; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 12px; }}
.legend-color {{ width: 16px; height: 16px; border-radius: 3px; border: 1.5px solid #777; }}
#main {{ display: flex; height: calc(100vh - 82px); }}
#svg-container {{ flex: 1; overflow: auto; padding: 10px; cursor: grab; }}
#svg-container svg {{ transform-origin: 0 0; }}
#detail-panel {{ width: 0; overflow-y: auto; background: white; border-left: 1px solid #ddd; transition: width 0.3s; }}
#detail-panel.open {{ width: 380px; padding: 16px; }}
.detail-section {{ margin-bottom: 12px; }}
.detail-section h4 {{ margin: 0 0 6px; color: #444; font-size: 13px; text-transform: uppercase; }}
.step-item {{ background: #f0f0f0; border-left: 3px solid #839192; padding: 6px 10px; font-size: 13px; margin-bottom: 4px; border-radius: 0 3px 3px 0; }}
.step-arrow {{ text-align: center; color: #aaa; font-size: 14px; }}
.eq-item {{ background: #d4e6f1; border-left: 3px solid #5dade2; padding: 6px 10px; font-size: 13px; margin-bottom: 4px; border-radius: 0 3px 3px 0; }}
.orphan-item {{ background: #fef9e7; border-left: 3px solid #f39c12; padding: 6px 10px; font-size: 13px; margin-bottom: 4px; }}
#orphan-panel {{ position: fixed; bottom: 16px; right: 16px; background: white; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); max-width: 350px; max-height: 400px; overflow-y: auto; display: none; padding: 12px; z-index: 100; }}
#orphan-toggle {{ display: none; }}
/* Hover effect on clickable node rects */
[id^="node_"]:hover {{ filter: brightness(0.90); }}
.ghost-node {{ display: inline-block; margin: 4px 8px; padding: 8px 14px; background: #E0E0E0; border: 1.5px solid #757575; border-radius: 5px; font-size: 13px; color: #333; cursor: pointer; vertical-align: top; white-space: normal; max-width: 220px; }}
.ghost-node:hover {{ background: #BDBDBD; }}
.ghost-node .ghost-label {{ font-weight: bold; font-size: 13px; }}
.ghost-node .ghost-refs {{ font-size: 11px; color: #666; margin-top: 3px; }}
</style>
</head>
<body>
<div id="header">
  <h1>{_esc(title)}<span class="hint">— click nodes for detailed description</span></h1>
  <div id="controls">
    <button onclick="resetView()">Reset</button>
    <button onclick="zoomIn()">Zoom +</button>
    <button onclick="zoomOut()">Zoom -</button>
    <button onclick="zoomFit()">Fit</button>
  </div>
</div>
<div class="legend">
  <div class="legend-item"><div class="legend-color" style="background:#D5F5E3;border-color:#27AE60;"></div>Definition</div>
  <div class="legend-item"><div class="legend-color" style="background:#FADBD8;border-color:#C0392B;"></div>Theorem</div>
  <div class="legend-item"><div class="legend-color" style="background:#F5CBA7;border-color:#D35400;"></div>Lemma</div>
  <div class="legend-item"><div class="legend-color" style="background:#F2D7D5;border-color:#943126;"></div>Corollary</div>
  <div class="legend-item"><div class="legend-color" style="background:#D4E6F1;border-color:#2471A3;"></div>Algorithm</div>
  <div class="legend-item" style="margin-left:12px;"><span style="font-size:18px;color:#555;">&#8594;</span> A supports B</div>
  <div class="legend-item" style="margin-left:12px;"><button onclick="toggleGhosts()" id="ghost-btn" style="padding:4px 12px;border:1.5px solid #757575;border-radius:4px;background:#E0E0E0;cursor:pointer;font-size:12px;color:#333;">Show external dependencies</button></div>
</div>
<div id="main">
  <div id="svg-container">{svg_content}</div>
  <div id="detail-panel"></div>
</div>
<button id="orphan-toggle" onclick="toggleOrphans()">{len(js_orphans)} orphan eq{"s" if len(js_orphans) != 1 else ""}</button>
<div id="orphan-panel"><h3>Unconnected Equations</h3><div id="orphan-list"></div></div>
<script>
var DETAILS = {details_json};
var ORPHANS = {orphans_json};
var GHOSTS = {ghosts_json};
var CASE1 = {case1_json};

var _lastDetailNode = null;
function showDetail(nodeId) {{
  var panel = document.getElementById("detail-panel");
  // Toggle: click same node again to close
  if (_lastDetailNode === nodeId && panel.className === "open") {{
    panel.className = "";
    panel.innerHTML = "";
    _lastDetailNode = null;
    return;
  }}
  _lastDetailNode = nodeId;
  // Special case: orphan/misc node
  if (nodeId === '__orphan__') {{
    var h = '<h3 style="margin:0 0 8px;font-size:16px;">Misc: Unconnected Equations</h3>';
    h += '<div style="font-size:12px;color:#888;margin-bottom:10px;">Equations not linked to any theorem or proof step</div>';
    ORPHANS.forEach(function(e) {{
      h += '<div class="eq-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>';
    }});
    if (ORPHANS.length === 0) h += '<div style="color:#888;">No orphan equations.</div>';
    panel.innerHTML = h;
    panel.className = "open";
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([panel]).catch(function(){{}});
    return;
  }}
  var d = DETAILS[nodeId];
  if (!d) return;
  var h = '<h3 style="margin:0 0 8px;font-size:16px;">' + esc(nodeId) + ': ' + esc(d.name || d.type) + '</h3>';
  h += '<div style="font-size:12px;color:#888;margin-bottom:4px;">' + d.type + (d.section ? ' (Sec ' + d.section + ')' : '') + '</div>';
  // Foundation graph link badge (Case 1: known result)
  if (d.foundation_links && d.foundation_links.length > 0) {{
    h += '<div style="display:inline-block;padding:2px 8px;background:#E3F2FD;border:1px solid #2471A3;border-radius:3px;font-size:11px;color:#2471A3;margin-bottom:8px;">&#128218; Known result: ' + d.foundation_links.map(esc).join(', ') + '</div>';
  }}
  // Pre-build equation maps by context
  var eqsByCtx = {{statement:[], assumption:[], conclusion:[], orphan:[]}};
  var eqsByStep = {{}};
  if (d.equations) {{
    d.equations.forEach(function(e) {{
      if (e.parent_step) {{
        if (!eqsByStep[e.parent_step]) eqsByStep[e.parent_step] = [];
        eqsByStep[e.parent_step].push(e);
      }} else if (e.context && eqsByCtx[e.context]) {{
        eqsByCtx[e.context].push(e);
      }} else {{
        eqsByCtx.orphan.push(e);
      }}
    }});
  }}
  var eqTag = function(e) {{ return '<span style="color:#2471A3;font-size:11px;"> (' + e.id + ')</span>'; }};
  var eqBlock = function(e) {{ return '<div style="margin:2px 0 2px 12px;padding:3px 8px;background:#EBF5FB;border-left:2px solid #5DADE2;font-size:12px;">' + esc(e.id) + ': ' + esc(e.statement) + '</div>'; }};

  // Statement + inline statement equations
  if (d.statement) {{
    h += '<div class="detail-section"><h4>Statement</h4><div style="font-size:14px;">' + esc(d.statement) + '</div>';
    eqsByCtx.statement.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  // Assumptions + inline assumption equations
  if ((d.assumptions && d.assumptions.length > 0) || eqsByCtx.assumption.length > 0) {{
    h += '<div class="detail-section"><h4>Assumptions</h4>';
    if (d.assumptions) d.assumptions.forEach(function(a) {{ h += '<div style="font-size:13px;padding:2px 0 2px 10px;">&bull; ' + esc(a) + '</div>'; }});
    eqsByCtx.assumption.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  // Conclusions + inline conclusion equations
  if ((d.conclusions && d.conclusions.length > 0) || eqsByCtx.conclusion.length > 0) {{
    h += '<div class="detail-section"><h4>Conclusions</h4>';
    if (d.conclusions) d.conclusions.forEach(function(c) {{ h += '<div style="font-size:13px;padding:2px 0 2px 10px;">&bull; ' + esc(c) + '</div>'; }});
    eqsByCtx.conclusion.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  // Proof strategy
  if (d.proof_info && d.proof_info.length > 0) {{
    h += '<div class="detail-section"><h4>Proof Strategy</h4>';
    d.proof_info.forEach(function(p) {{
      if (Array.isArray(p)) {{
        p.forEach(function(item) {{ h += '<div style="font-size:13px;font-style:italic;">&bull; ' + esc(item) + '</div>'; }});
      }} else {{
        h += '<div style="font-size:13px;font-style:italic;">' + esc(p) + '</div>';
      }}
    }});
    h += '</div>';
  }}
  // Algorithm input/output
  if (d.input && d.input.length > 0) {{
    h += '<div class="detail-section"><h4>Input</h4>';
    d.input.forEach(function(x) {{ h += '<div style="font-size:13px;">&bull; ' + esc(x) + '</div>'; }});
    h += '</div>';
  }}
  if (d.output && d.output.length > 0) {{
    h += '<div class="detail-section"><h4>Output</h4>';
    d.output.forEach(function(x) {{ h += '<div style="font-size:13px;">&bull; ' + esc(x) + '</div>'; }});
    h += '</div>';
  }}
  // Proof steps with inline equations
  if (d.steps && d.steps.length > 0) {{
    h += '<div class="detail-section"><h4>Proof Steps (' + d.steps.length + ')</h4>';
    d.steps.forEach(function(s, i) {{
      h += '<div class="step-item"><strong>' + s.id + '</strong>: ' + esc(s.statement);
      if (eqsByStep[s.id]) {{
        eqsByStep[s.id].forEach(function(e) {{ h += eqBlock(e); }});
      }}
      h += '</div>';
      if (i < d.steps.length - 1) h += '<div class="step-arrow">&#8595;</div>';
    }});
    h += '</div>';
  }}
  // Orphan equations (collapsible)
  if (eqsByCtx.orphan.length > 0) {{
    h += '<div class="detail-section"><h4 style="cursor:pointer;" onclick="toggleEqPanel(this)">Unplaced Equations (' + eqsByCtx.orphan.length + ') &#9660;</h4>';
    h += '<div style="display:none;">';
    eqsByCtx.orphan.forEach(function(e) {{
      h += '<div class="eq-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>';
    }});
    h += '</div></div>';
  }}
  panel.innerHTML = h;
  panel.className = "open";
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([panel]).catch(function(){{}});
}}
function resetView() {{
  document.getElementById("detail-panel").className = "";
  document.getElementById("detail-panel").innerHTML = "";
}}
function toggleOrphans() {{
  var p = document.getElementById("orphan-panel");
  if (p.style.display === "block") {{ p.style.display = "none"; return; }}
  var h = "";
  ORPHANS.forEach(function(e) {{ h += '<div class="orphan-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>'; }});
  document.getElementById("orphan-list").innerHTML = h;
  p.style.display = "block";
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([p]).catch(function(){{}});
}}
// Ghost nodes (external dependencies)
function toggleGhosts() {{
  var svgEl = document.querySelector("#svg-container svg");
  var ghostEls = svgEl ? svgEl.querySelectorAll('[id^="ghost_"]') : [];
  var btn = document.getElementById("ghost-btn");
  var isShowing = btn.dataset.showing === "1";
  if (!isShowing) {{
    btn.dataset.showing = "1";
    btn.textContent = "Hide external dependencies";
    ghostEls.forEach(function(el) {{ el.style.display = ""; }});
  }} else {{
    btn.dataset.showing = "0";
    btn.textContent = "Show external dependencies";
    ghostEls.forEach(function(el) {{ el.style.display = "none"; }});
  }}
}}
function showGhostDetail(nameOrEl) {{
  var name = (typeof nameOrEl === 'string') ? nameOrEl : nameOrEl;
  var panel = document.getElementById("detail-panel");
  var refs = GHOSTS[name] || [];
  var h = '<h3 style="margin:0 0 8px;font-size:16px;">' + esc(name) + '</h3>';
  h += '<div style="font-size:12px;color:#795548;margin-bottom:10px;">External dependency (from Foundation Graph)</div>';
  h += '<div class="detail-section"><h4>Referenced by</h4>';
  refs.forEach(function(nid) {{
    var d = DETAILS[nid];
    var label = d ? (nid + ': ' + (d.name || d.type)) : nid;
    h += '<div style="font-size:13px;padding:2px 0 2px 10px;cursor:pointer;color:#2471A3;" data-nid="' + nid + '" onclick="showDetail(this.dataset.nid)">&bull; ' + esc(label) + '</div>';
  }});
  h += '</div>';
  panel.innerHTML = h;
  panel.className = "open";
}}


function toggleEqPanel(el) {{
  var panel = el.nextElementSibling;
  if (panel) panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}}
function esc(t) {{ return t ? t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") : ""; }}

// Hide ghost elements on load (wait for SVG to render)
window.addEventListener("load", function() {{
  var svgEl = document.querySelector("#svg-container svg");
  if (svgEl) {{
    // Hide all ghost elements (boxes, headers, text, refs, edges)
    var all = svgEl.querySelectorAll('[id^="ghost_"]');
    all.forEach(function(el) {{ el.style.display = "none"; }});
  }}
}});

var currentZoom = 1.0;
var svgEl = document.querySelector("#svg-container svg");
function applyZoom() {{
  if (svgEl) svgEl.style.transform = "scale(" + currentZoom + ")";
}}
function zoomIn() {{ currentZoom = Math.min(currentZoom * 1.3, 5.0); applyZoom(); }}
function zoomOut() {{ currentZoom = Math.max(currentZoom / 1.3, 0.2); applyZoom(); }}
function zoomFit() {{ currentZoom = 1.0; applyZoom(); }}

// Mouse wheel zoom on the SVG container
document.getElementById("svg-container").addEventListener("wheel", function(e) {{
  e.preventDefault();
  if (e.deltaY < 0) {{ currentZoom = Math.min(currentZoom * 1.1, 5.0); }}
  else {{ currentZoom = Math.max(currentZoom / 1.1, 0.2); }}
  applyZoom();
}}, {{passive: false}});
</script>
</body>
</html>"""

    Path(html_path).write_text(html, encoding="utf-8")
    return len(base_nodes)


# ── CLI ─────────────────────────────────────────────────────────────────────
def resolve_paths(args_list):
    """Resolve a list of paths/globs/directories to JSON files."""
    import glob as _glob
    files = []
    for arg in args_list:
        p = Path(arg)
        if p.is_dir():
            files.extend(sorted(p.glob("*.json")))
        elif "*" in arg or "?" in arg:
            files.extend(sorted(Path(m) for m in _glob.glob(arg)))
        elif p.is_file():
            files.append(p)
        else:
            print(f"WARNING: '{arg}' not found, skipping.")
    return files


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Visualize knowledge graph annotation(s) as DAG images.",
        epilog="Examples:\n"
               "  python visualize_annotation.py annotation.json\n"
               "  python visualize_annotation.py papers/gold/\n"
               "  python visualize_annotation.py 'papers/gold/paper*.json'\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="+", help="JSON file(s), directory, or glob pattern")
    parser.add_argument("-o", "--output", default=None, help="Output PNG path (single file only)")
    parser.add_argument("--resolution", choices=["standard", "full"], default="standard",
                        help="standard: collapse proofs, hide equations. full: show all nodes.")
    parser.add_argument("--show-foundation", action="store_true",
                        help="Include foundation graph ghost nodes in the PNG output")
    parser.add_argument("--foundation-path", default=None,
                        help="Path to clean_foundation.json (default: auto-detect)")
    parser.add_argument("--html", action="store_true",
                        help="Also generate interactive HTML for each file")
    parser.add_argument("--html-only", action="store_true",
                        help="Generate only interactive HTML (no PNG)")
    args = parser.parse_args()

    files = resolve_paths(args.input)
    if not files:
        print("No JSON files found.")
        sys.exit(1)

    do_html = args.html or args.html_only
    do_png = not args.html_only

    for i, input_path in enumerate(files):
        if len(files) > 1:
            print(f"\n[{i+1}/{len(files)}] {input_path.name}")

        if args.output and len(files) == 1:
            output_path = Path(args.output)
        else:
            output_path = input_path.with_suffix(".png")

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        if not nodes:
            print(f"  WARNING: No 'nodes' found in {input_path.name}, skipping.")
            continue

        metadata = data.get("metadata", {})

        if do_png:
            result = draw_dag(nodes, edges, output_path, metadata=metadata,
                              resolution=args.resolution,
                              show_foundation=args.show_foundation,
                              foundation_path=args.foundation_path)
            n_nodes, n_edges = result[0], result[1]
            print(f"  -> {output_path} ({n_nodes} nodes, {n_edges} edges)")

        if do_html:
            import os
            svg_only_path = str(output_path).replace('.png', '_nolegend.svg')
            draw_dag(nodes, edges, svg_only_path.replace('.svg', '.png'), metadata=metadata,
                     resolution=args.resolution, show_legend=False,
                     show_foundation=True,
                     foundation_path=args.foundation_path)
            html_path = input_path.with_suffix(".html")
            n_html = generate_interactive_html(data, svg_only_path, str(html_path))
            for tmp in [svg_only_path, svg_only_path.replace('.svg', '.png')]:
                if os.path.exists(tmp):
                    os.remove(tmp)
            print(f"  -> {html_path} ({n_html} clickable nodes)")

    if len(files) > 1:
        print(f"\nDone: {len(files)} graphs generated.")


if __name__ == "__main__":
    main()
