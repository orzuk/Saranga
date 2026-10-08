"""
Rule dictionaries for LaTeX canonicalization.

Each RULES_* dictionary maps a source pattern (literal string or regex,
documented per category) to its canonical replacement. The pipeline in
core.py applies these in a fixed order; see PIPELINE_ORDER at the bottom
of this file.

Conventions:
  - Keys and values use Python raw strings (r"...") so a backslash in the
    source literal means one backslash, not two. E.g. r"\leq" is the
    5-character LaTeX command \leq, not \\leq.
  - "Literal" rules are applied as whole-word string replacement with
    a word-boundary check on the right side (prevents e.g. \leq
    accidentally matching inside \leqqqq).
  - "Regex" rules are compiled and applied with re.sub. Patterns are
    listed as tuples (pattern, replacement).

Add new rules as needed. The module auto-reloads rules on import.
"""

# ==========================================================================
# CATEGORY 0 -- RESERVED (never rename these as variables)
# ==========================================================================

# Mathematical constants (command form) that LOOK like variables but aren't.
CONSTANTS = {
    # Classical
    r"\pi", r"\e", r"\i", r"\infty",
    r"\imath", r"\jmath",
    r"\emptyset", r"\varnothing",
    r"\top", r"\bot",
    # Cardinals / ordinals
    r"\aleph", r"\beth",
}

# Single-letter math constants. These look like variables but carry
# canonical meanings in mathematical usage:
#     e  -- Euler's number (e ≈ 2.718...)
#     i  -- imaginary unit
#     j  -- sometimes imaginary unit (engineering)
# If a paper uses these as generic variables (rare), override via project
# config. By default they are NEVER renamed.
LETTER_CONSTANTS = {
    "e",
    "i",
    # "j",   # uncomment if engineering texts matter
}

# Greek command names -- the LaTeX commands that introduce Greek letters.
# These are treated as variable-candidates (unless also in CONSTANTS, which
# covers \pi). Everything else starting with \ is assumed to be an
# operator/relation/function and is NOT renamed.
GREEK_VARIABLE_COMMANDS = {
    # Lowercase Greek
    r"\alpha", r"\beta", r"\gamma", r"\delta", r"\epsilon", r"\zeta",
    r"\eta", r"\theta", r"\iota", r"\kappa", r"\lambda", r"\mu",
    r"\nu", r"\xi", r"\rho", r"\sigma", r"\tau", r"\upsilon",
    r"\phi", r"\chi", r"\psi", r"\omega",
    # Variant forms: variables of their own when a text keeps them apart
    r"\varepsilon", r"\vartheta", r"\varrho", r"\varsigma", r"\varphi",
    r"\varkappa", r"\varpi",
    # Uppercase (distinct-from-Latin ones)
    r"\Gamma", r"\Delta", r"\Theta", r"\Lambda", r"\Xi",
    r"\Sigma", r"\Upsilon", r"\Phi", r"\Psi", r"\Omega",
    # Note: \pi, \Pi are in CONSTANTS (pi is a canonical constant);
    # they are NOT variable-candidates.
    # Script/frak letters used as variables:
    # (add on demand -- these usually appear as \mathcal{X} or \mathfrak{g}
    #  which the extractor doesn't descend into yet)
}

# Standard function / operator names.
STANDARD_FUNCTIONS = {
    # Trig + hyperbolic
    r"\sin", r"\cos", r"\tan", r"\sec", r"\csc", r"\cot",
    r"\arcsin", r"\arccos", r"\arctan",
    r"\sinh", r"\cosh", r"\tanh", r"\coth",
    r"\sech", r"\csch",
    # Exponential / logarithm
    r"\exp", r"\log", r"\ln", r"\lg",
    # Limits / extrema
    r"\lim", r"\limsup", r"\liminf",
    r"\sup", r"\inf", r"\max", r"\min",
    r"\argmax", r"\argmin",
    # Linear algebra
    r"\det", r"\tr", r"\rank", r"\dim", r"\ker",
    r"\span", r"\null", r"\range", r"\image",
    # Number theory / arithmetic
    r"\gcd", r"\lcm", r"\mod",
    # Complex
    r"\Re", r"\Im", r"\arg",
    # Probability
    r"\Pr", r"\E", r"\Var", r"\Cov", r"\Cor",
    # Sums / products / integrals (big operators, already unique)
    r"\sum", r"\prod", r"\int", r"\oint", r"\iint", r"\iiint",
    r"\bigcup", r"\bigcap", r"\bigoplus", r"\bigotimes",
}

# Standard number sets (canonical form).
NUMBER_SETS_CANONICAL = {
    r"\mathbb{R}", r"\mathbb{N}", r"\mathbb{Z}",
    r"\mathbb{Q}", r"\mathbb{C}", r"\mathbb{F}", r"\mathbb{P}",
    r"\mathbb{H}", r"\mathbb{K}",
}


# ==========================================================================
# CATEGORY 1 -- WHITESPACE / SPACING COMMAND REMOVAL
# (Applied first: drops all LaTeX spacing that doesn't affect semantics.)
# ==========================================================================

RULES_SPACING = {
    # Thin spaces
    r"\,": "",
    r"\!": "",
    r"\:": "",
    r"\;": "",
    r"\ ": " ",           # explicit space -> regular space
    # Large spaces. \quad is NOT a space: it separates two formulas
    # (x > 0 \quad y > 1); as a space they would fuse into x > 0 y > 1.
    r"\qquad": r"\quad",  # the same separator, only wider
    r"\thinspace": "",
    r"\enspace": "",
    r"\medspace": "",
    r"\thickspace": "",
    r"\negthinspace": "",
    r"\negmedspace": "",
    r"\negthickspace": "",
    # Non-breaking space
    "~": " ",
}


# ==========================================================================
# CATEGORY 2 -- BRACKET AND DELIMITER NORMALIZATION
# Strip \left, \right, and \big-family sizing.
# NOTE: these are LITERAL substitutions applied before anything else touches
# brackets. Once simplified, later passes can analyse { }, ( ), [ ] uniformly.
# ==========================================================================

RULES_BRACKETS = {
    # \left / \right pairs
    r"\left(":  "(",
    r"\right)": ")",
    r"\left[":  "[",
    r"\right]": "]",
    r"\left\{": r"\{",
    r"\right\}": r"\}",
    r"\left|":  "|",
    r"\right|": "|",
    r"\left\|": r"\|",
    r"\right\|": r"\|",
    r"\left<":  r"\langle",
    r"\right>": r"\rangle",
    r"\left\langle":  r"\langle",
    r"\right\rangle": r"\rangle",
    r"\left.":  "",
    r"\right.": "",
    # \big / \Big / \bigg / \Bigg sizing (as prefixes on brackets)
    r"\bigl":   "",
    r"\bigr":   "",
    r"\Bigl":   "",
    r"\Bigr":   "",
    r"\biggl":  "",
    r"\biggr":  "",
    r"\Biggl":  "",
    r"\Biggr":  "",
    r"\big":    "",
    r"\Big":    "",
    r"\bigg":   "",
    r"\Bigg":   "",
    # Math-mode brackets in wrapper form
    r"\lparen": "(",
    r"\rparen": ")",
    r"\lbrack": "[",
    r"\rbrack": "]",
    r"\lbrace": r"\{",
    r"\rbrace": r"\}",
}


# ==========================================================================
# CATEGORY 3 -- GREEK LETTERS: UNICODE -> COMMAND
# Normalize all Greek chars to the command form for consistency with text
# that uses \alpha, \beta, etc. (The reverse choice is equally valid; we
# pick command form because most mathematical LaTeX already uses it.)
# ==========================================================================

RULES_GREEK_UNICODE_TO_COMMAND = {
    # Lowercase
    "α": r"\alpha",    "β": r"\beta",     "γ": r"\gamma",   "δ": r"\delta",
    # Each character maps to the command that prints it; whether the variant
    # forms then merge is decided by RULES_GREEK_VARIANTS (only when a text
    # does not use both forms as different symbols).
    "ε": r"\varepsilon", "ϵ": r"\epsilon", "ζ": r"\zeta",    "η": r"\eta",
    "θ": r"\theta",    "ϑ": r"\vartheta", "ι": r"\iota",    "κ": r"\kappa",
    "λ": r"\lambda",   "μ": r"\mu",       "ν": r"\nu",      "ξ": r"\xi",
    "π": r"\pi",       "ϖ": r"\varpi",    "ρ": r"\rho",     "ϱ": r"\varrho",
    "σ": r"\sigma",    "ς": r"\varsigma", "τ": r"\tau",     "υ": r"\upsilon",
    "φ": r"\varphi",   "ϕ": r"\phi",      "χ": r"\chi",     "ψ": r"\psi",
    "ω": r"\omega",
    # Uppercase (only distinct-from-Latin ones need a command)
    "Γ": r"\Gamma",    "Δ": r"\Delta",    "Θ": r"\Theta",   "Λ": r"\Lambda",
    "Ξ": r"\Xi",       "Π": r"\Pi",       "Σ": r"\Sigma",   "Υ": r"\Upsilon",
    "Φ": r"\Phi",      "Ψ": r"\Psi",      "Ω": r"\Omega",
}

# Greek command variants that collapse to the plain form -- but only in a text
# that does not use both forms. A paper may write \phi and \varphi for two
# different functions; merging them there would identify two symbols.
RULES_GREEK_VARIANTS = {
    r"\varepsilon": r"\epsilon",
    r"\vartheta":   r"\theta",
    # NOT \varpi -> \pi: \varpi is a variable, \pi the constant.
    r"\varrho":     r"\rho",
    r"\varsigma":   r"\sigma",
    r"\varphi":     r"\phi",
    r"\varkappa":   r"\kappa",
}


# ==========================================================================
# CONDITIONAL MERGES
# source -> (target, blockers): the source is merged into the target only in
# a text whose math uses none of the blockers (core._greek_variants_for), and
# never when a rename map renames the source or the target. The blockers are
# the target and the other spellings that print differently from the source.
# ==========================================================================
_IMPLIES_BLOCKERS = {r"\implies", r"\Longrightarrow", "\u27f9"}          # long double arrow
_IFF_BLOCKERS = {r"\iff", r"\Longleftrightarrow", "\u27fa"}
CONDITIONAL_MERGES = {
    **{k: (v, {v}) for k, v in RULES_GREEK_VARIANTS.items()},
    # l_1 and \ell_1 are the same space; but a text with both a length l and
    # an index \ell keeps them apart.
    r"\ell": ("l", {"l"}),
    # => and ==> both mean implication, but => also denotes weak convergence
    # (X_n => X); a text that uses both lengths keeps them apart.
    r"\Rightarrow": (r"\implies", _IMPLIES_BLOCKERS),
    "\u21d2": (r"\implies", _IMPLIES_BLOCKERS),
    r"\Leftrightarrow": (r"\iff", _IFF_BLOCKERS),
    "\u21d4": (r"\iff", _IFF_BLOCKERS),
}


# ==========================================================================
# CATEGORY 4 -- NUMBER-SET NOTATION UNIFICATION
# All common encodings of R, N, Z, Q, C, F -> \mathbb{·}.
# Not \mathbf{X} or \mathcal{X}: a bold or calligraphic capital is usually a
# matrix, a vector or a family (\mathbf{Z} a design matrix, \mathcal{R} a
# range or a ring), not a number set.
# ==========================================================================

RULES_NUMBER_SETS = {
    # Reals
    r"\R":          r"\mathbb{R}",
    r"\reals":      r"\mathbb{R}",
    r"\Reals":      r"\mathbb{R}",
    r"\mathds{R}":  r"\mathbb{R}",
    # Naturals
    r"\N":          r"\mathbb{N}",
    r"\Naturals":   r"\mathbb{N}",
    r"\mathds{N}":  r"\mathbb{N}",
    # Integers
    r"\Z":          r"\mathbb{Z}",
    r"\Integers":   r"\mathbb{Z}",
    r"\mathds{Z}":  r"\mathbb{Z}",
    # Rationals
    r"\Q":          r"\mathbb{Q}",
    r"\Rationals":  r"\mathbb{Q}",
    r"\mathds{Q}":  r"\mathbb{Q}",
    # Complexes
    r"\C":          r"\mathbb{C}",
    r"\Complexes":  r"\mathbb{C}",
    r"\mathds{C}":  r"\mathbb{C}",
    # Finite field F_q sometimes written \F_q
    r"\F":          r"\mathbb{F}",
    r"\mathds{F}":  r"\mathbb{F}",
}


# ==========================================================================
# CATEGORY 5 -- MULTIPLICATION / DIVISION OPERATORS
# All multiplication-sense symbols -> literal '*'.
# Division: \div -> '/'.  (Fractions are handled separately below.)
# ==========================================================================

RULES_OPERATORS = {
    # NOT unified: \star vs * -- x^\star (an optimum) and x^* (an adjoint or
    # conjugate) often appear in the same paper with different meanings.
    # \div -> / is always division
    r"\div":   "/",
    # NOT unified (context-dependent — distinct math operations):
    #   \cdot  = dot product (vectors) OR scalar multiplication
    #   \times = cross product (vectors) OR Cartesian product (sets) OR multiplication
    #   \ast   = convolution OR adjoint OR multiplication
    # Keep each as its own token; embeddings learn contextual equivalence.
    # ± / ∓: keep as-is (distinct semantics)
}


# ==========================================================================
# CATEGORY 6 -- RELATION NORMALIZATION
# Equality/inequality/comparison: unify short and long commands.
# ==========================================================================

RULES_RELATIONS = {
    # Inequality
    r"\le":       r"\leq",
    r"\ge":       r"\geq",
    r"\ne":       r"\neq",
    r"\notequal": r"\neq",
    # Equivalence
    r"\equiv":    r"\equiv",    # keep distinct from =
    r"\approx":   r"\approx",
    r"\sim":      r"\sim",
    r"\simeq":    r"\simeq",
    r"\cong":     r"\cong",
    r"\propto":   r"\propto",
    # Parallel / perpendicular
    r"\parallel": r"\parallel",
    r"\perp":     r"\perp",
    # Order-theoretic
    r"\prec":     r"\prec",
    r"\preceq":   r"\preceq",
    r"\succ":     r"\succ",
    r"\succeq":   r"\succeq",
}


# ==========================================================================
# CATEGORY 7 -- SET THEORY RELATIONS
# Keep \subset vs \subseteq distinct (mean different things in different
# texts). Unify cup/cap/setminus styles.
# ==========================================================================

RULES_SET_RELATIONS = {
    r"\in":         r"\in",
    r"\notin":      r"\notin",
    r"\subset":     r"\subset",
    r"\subseteq":   r"\subseteq",
    r"\subsetneq":  r"\subsetneq",
    r"\supset":     r"\supset",
    r"\supseteq":   r"\supseteq",
    r"\supsetneq":  r"\supsetneq",
    r"\cup":        r"\cup",
    r"\cap":        r"\cap",
    r"\setminus":   r"\setminus",
    r"\smallsetminus": r"\setminus",
    r"\sqcup":      r"\sqcup",
    r"\sqcap":      r"\sqcap",
    r"\bigcup":     r"\bigcup",
    r"\bigcap":     r"\bigcap",
}


# ==========================================================================
# CATEGORY 8 -- ARROWS
# ==========================================================================

RULES_ARROWS = {
    r"\rightarrow":         r"\to",
    r"\longrightarrow":     r"\to",
    r"\leftarrow":          r"\leftarrow",
    r"\longleftarrow":      r"\leftarrow",
    r"\leftrightarrow":     r"\leftrightarrow",
    r"\longleftrightarrow": r"\leftrightarrow",
    r"\Rightarrow":         r"\implies",
    r"\Longrightarrow":     r"\implies",
    r"\Leftarrow":          r"\Leftarrow",
    r"\Leftrightarrow":     r"\iff",
    r"\Longleftrightarrow": r"\iff",
    r"\mapsto":             r"\mapsto",
    r"\longmapsto":         r"\mapsto",
    r"\hookrightarrow":     r"\hookrightarrow",
    r"\hookleftarrow":      r"\hookleftarrow",
    r"\twoheadrightarrow":  r"\twoheadrightarrow",
    r"\rightharpoonup":     r"\rightharpoonup",
    # \xrightarrow{f} -> \overset{f}{\to} (core._rewrite_xarrows): the label stays.
    # Unicode
    "→": r"\to",
    "⇒": r"\implies",
    "⇔": r"\iff",
    "↔": r"\leftrightarrow",
    "↦": r"\mapsto",
}


# ==========================================================================
# CATEGORY 9 -- LOGIC SYMBOLS
# ==========================================================================

RULES_LOGIC = {
    r"\lor":       r"\vee",
    r"\land":      r"\wedge",
    r"\lnot":      r"\neg",
    r"\wedge":     r"\wedge",
    r"\vee":       r"\vee",
    r"\neg":       r"\neg",
    r"\forall":    r"\forall",
    r"\exists":    r"\exists",
    r"\nexists":   r"\nexists",
    r"\top":       r"\top",
    r"\bot":       r"\bot",
    # Unicode
    "∀": r"\forall",
    "∃": r"\exists",
    "∧": r"\wedge",
    "∨": r"\vee",
    "¬": r"\neg",
    "⊤": r"\top",
    "⊥": r"\bot",
}


# ==========================================================================
# CATEGORY 10 -- FUNCTION NAME ALIASES
# ==========================================================================

# \ell -> l  (unify "ell_1 norm" with "l_1 norm")
# Both notations are standard; some authors use \ell for aesthetic reasons.
RULES_ELL = {
    r"\ell": "l",
}

# Letters that are norm-space names when followed by subscript/superscript.
# l_1, l_2, l_p, l_\infty, L^2, L^p — these are concept names, NOT variables.
# Bare l or L (no subscript) IS treated as a variable and gets renamed.
# Applied at the rename step: if letter is in NORM_LETTERS and followed by _ or ^,
# the rename is suppressed for that occurrence.
NORM_LETTERS = {"l", "L"}

RULES_FUNCTION_ALIASES = {
    r"\tg":     r"\tan",
    r"\ctg":    r"\cot",
    r"\arctg":  r"\arctan",
    r"\arcctg": r"\arccot",
    # NOT aliased, each has a common different meaning: \ch (the Chern
    # character), \th (the thorn character, or a macro for theta), \sh and
    # \cth by symmetry with them; \Exp (often an expectation macro); \Log
    # and \Ln (the principal branch of the complex logarithm).
    # exp(x) -> e^x and \log -> \ln (when no subscript): applied as regex in
    # core.py, not as literals here, because they need word boundaries and
    # subscript detection.
}


# ==========================================================================
# CATEGORY 11 -- MATH ENVIRONMENT ALIASES
# Treat starred / unstarred / eqnarray variants as equivalent.
# ==========================================================================

RULES_ENVIRONMENTS = {
    r"\begin{equation*}":  r"\begin{equation}",
    r"\end{equation*}":    r"\end{equation}",
    r"\begin{align*}":     r"\begin{align}",
    r"\end{align*}":       r"\end{align}",
    r"\begin{gather*}":    r"\begin{gather}",
    r"\end{gather*}":      r"\end{gather}",
    r"\begin{eqnarray}":   r"\begin{align}",
    r"\end{eqnarray}":     r"\end{align}",
    r"\begin{eqnarray*}":  r"\begin{align}",
    r"\end{eqnarray*}":    r"\end{align}",
    r"\begin{multline*}":  r"\begin{multline}",
    r"\end{multline*}":    r"\end{multline}",
}


# ==========================================================================
# CATEGORY 12 -- REGEX-BASED REWRITES (order-sensitive)
# Apply after all literal rules above. Pattern is raw-string regex.
# ==========================================================================

# Fraction: \frac{a}{b} -> {a}/{b}   (keep braces so later parse is safe)
# Also \dfrac, \tfrac -> \frac then the frac rule.
RULES_FRAC_ALIASES = {
    r"\dfrac": r"\frac",
    r"\tfrac": r"\frac",
    r"\cfrac": r"\frac",
}

# Regex pattern for \frac{a}{b}. Greedy-safe via balanced-brace matching below.
# Applied via a dedicated function in core.py; listed here as documentation.
FRAC_PATTERN = r"\\frac\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}"
FRAC_REPLACEMENT = r"{\1}/{\2}"

# \binom{n}{k} -> C(n,k): NOT APPLIED. C(n,k) reads as a function of a
# variable C and collides with any C the paper uses; \binom stays.
BINOM_PATTERN = r"\\binom\s*\{([^{}]*)\}\s*\{([^{}]*)\}"
BINOM_REPLACEMENT = r"C(\1,\2)"

# exp(x) -> e^{x}
EXP_PATTERN = r"\\exp\s*\(([^)]*)\)"
EXP_REPLACEMENT = r"e^{\1}"

# \ln -> \log: NOT APPLIED. In computer science \log is base 2, and a paper
# that writes both (\log_2 n = \ln n / \ln 2) would become a false identity.
LN_TO_LOG_PATTERN = r"\\ln(?![A-Za-z])"
LN_TO_LOG_REPLACEMENT = r"\\log"

# \stackrel{X}{Y} -> \overset{X}{Y} (the same output). The decoration X is
# KEPT: X \overset{d}{=} Y (equal in distribution) and X_n
# \overset{a.s.}{\to} X (almost sure convergence) mean something else than
# = and \to.
OVERSET_COMMANDS = [r"\overset", r"\underset", r"\stackrel"]

# Multiplication clean-up: multiple spaces/tabs -> single space
WHITESPACE_COLLAPSE_PATTERN = r"\s+"
WHITESPACE_COLLAPSE_REPLACEMENT = " "


# ==========================================================================
# CATEGORY 13 -- INEQUALITY DIRECTION NORMALIZATION
# Rewrite A > B as B < A, A \geq B as B \leq A.
# Applied via a parse-aware function in core.py (regex can't safely swap
# complex operands). This dict documents the direction mapping.
# ==========================================================================

RULES_INEQUALITY_FLIP = {
    r">":         r"<",
    r"\geq":      r"\leq",
    r"\ge":       r"\leq",
    r"\gneq":     r"\lneq",
    r"\gg":       r"\ll",
    r"\ggg":      r"\lll",
    r"\succ":     r"\prec",
    r"\succeq":   r"\preceq",
    r"\supset":   r"\subset",    # turn off this line if \subset/\supset are used asymmetrically
    r"\supseteq": r"\subseteq",
}


# ==========================================================================
# CATEGORY 14 -- REDUNDANT BRACE / PARENTHESIS REMOVAL
# After all rewrites, strip grouping that isn't needed.
# Rules:
#   {x}      -> x              when x is a single atom (variable, constant, number)
#   ({x})    -> (x)            when x is a single atom
#   (x)      -> x              when x is a single atom AND parens are not an
#                              argument list (distinguish from function calls)
# Applied by a dedicated function in core.py; listed here for documentation.
# ==========================================================================

# Style switches and commands that take arguments or act on what follows:
# {\displaystyle} or {\rm} unbraced would change everything after them.
_KEEP_BRACED = (r"rm|bf|it|sf|tt|cal|mit|sl|sc|em|frak|Bbb|bold|displaystyle|textstyle|"
                r"scriptstyle|scriptscriptstyle|limits|nolimits|left|right|middle|over|atop|"
                r"choose|above|not|big|Big|bigg|Bigg|bigl|bigr|Bigl|Bigr|biggl|biggr|Biggl|Biggr|"
                r"color|tiny|small|large|Large|normalsize|footnotesize|scriptsize|huge|Huge")

REDUNDANT_BRACE_PATTERNS = [
    # {x} where x is a single letter, digit or command.
    # CRITICAL: negative lookbehind (?<![A-Za-z\\]) prevents stripping
    # braces that are arguments to a LaTeX command, e.g. \mathbb{R} --
    # the `b` before `{` is a letter, so the lookbehind rejects the match.
    # Same for \mathbf{X}, \mathcal{F}, etc.
    (r"(?<![A-Za-z\\])\{([A-Za-z])\}",   r"\1"),
    # a digit only when no digit or point touches it: 10{3}/2 is not 103/2
    (r"(?<![A-Za-z\\0-9.])\{([0-9])\}(?![0-9.])",   r"\1"),
    # a command only when no letter follows: x_{\alpha}d is not x_\alphad
    (r"(?<![A-Za-z\\])\{(\\(?!(?:" + _KEEP_BRACED + r")(?![A-Za-z]))[A-Za-z]+)\}(?![A-Za-z])", r"\1"),
    # {{x}} -> {x}  (not \{{x}}, and not when x ends in an escaping backslash)
    (r"(?<!\\)\{\{([^{}]*[^{}\\])\}\}",                   r"{\1}"),
]

# Space inside brackets: ( a + b ) -> (a + b), { x + 1 } -> {x + 1}
# Apply after bracket normalization.
BRACKET_INNER_SPACE_PATTERNS = [
    (r"\(\s+",   "("),   # "( x" -> "(x"
    (r"\s+\)",   ")"),   # "x )" -> "x)"
    (r"\[\s+",   "["),
    (r"\s+\]",   "]"),
    (r"\\\{\s+", r"\{"),  # LaTeX set brace \{
    (r"\s+\\\}", r"\}"),
    # Generic braces { ... } -- these are grouping delimiters
    (r"\{\s+", "{"),
    (r"\s+\}", "}"),
]


# ==========================================================================
# CATEGORY 15 -- PROSE REWRITES (LIGHT, OFF BY DEFAULT)
# Apply only when canonicalize_text(..., prose_rewrites=True).
# Risk: destroys author-chosen phrasing that may carry meaning.
# Case-insensitive substring match.
# ==========================================================================

# WARNING: these change meaning in ordinary sentences ("we have not shown" ->
# "then not shown", substrings inside longer words). Nothing turns them on.
RULES_PROSE = {
    # Hypothesis introduction
    "suppose that": "let",
    "suppose":      "let",
    "assume that":  "let",
    "assume":       "let",
    "given that":   "let",
    "given":        "let",
    # Conclusion introduction
    "it follows that": "then",
    "we have that":    "then",
    "we obtain":       "then",
    "we have":         "then",
    "hence":           "then",
    "therefore":       "then",
    "thus":            "then",
    "consequently":    "then",
    # Quantifier phrasing
    "for every":       "for all",
    "for any":         "for all",
    "for each":        "for all",
    "there is a":      "there exists",
    "there is an":     "there exists",
    "there are":       "there exist",
    "there exist a":   "there exists",
    "there exist an":  "there exists",
    # Existence
    "can be found":    "exists",
    # Equality intros
    "equals":          "=",
    "is equal to":     "=",
}


# ==========================================================================
# VARIABLE RENAMING SENTINELS
# Used by core.py when building local / paper-wide rename maps.
# ==========================================================================

# Each variable found in math gets mapped to one of:
#   VAR1, VAR2, ...  for generic variables
#   FN1, FN2, ...    for function names
#   IDX1, IDX2, ...  for index / summation dummies
# Chosen to be all-caps (rare in real math) and contain no backslash
# (won't conflict with LaTeX commands).

VAR_PREFIX   = "V"   # V1, V2, ...  (if original had V, it gets renamed too, so no conflict)
FUNC_PREFIX  = "F"
INDEX_PREFIX = "I"


# ==========================================================================
# PIPELINE ORDER (read by core.py)
# ==========================================================================
# Phases:
#   1.  Spacing strip              (RULES_SPACING)
#   2.  Bracket normalization      (RULES_BRACKETS)
#   3.  Greek unicode -> command   (RULES_GREEK_UNICODE_TO_COMMAND)
#   4.  Greek command variants     (RULES_GREEK_VARIANTS)
#   5.  Number-set unification     (RULES_NUMBER_SETS)
#   6.  Operator unification       (RULES_OPERATORS)
#   7.  Relation normalization     (RULES_RELATIONS)
#   8.  Set-relation normalization (RULES_SET_RELATIONS)
#   9.  Arrow normalization        (RULES_ARROWS)
#  10.  Logic symbols              (RULES_LOGIC)
#  11.  Function aliases           (RULES_FUNCTION_ALIASES)
#  12.  Environment aliases        (RULES_ENVIRONMENTS)
#  13.  Fraction aliases           (RULES_FRAC_ALIASES)
#  14.  Regex rewrites             (FRAC_PATTERN, EXP_PATTERN, BINOM_PATTERN)
#  15.  Inequality direction flip  (custom function; uses RULES_INEQUALITY_FLIP)
#  16.  Redundant brace removal    (custom function; uses REDUNDANT_BRACE_PATTERNS)
#  17.  Whitespace collapse        (regex)
#  18.  Variable alpha-rename      (custom function; uses VAR_PREFIX)
#  19.  (Optional) Prose rewrites  (RULES_PROSE)
#
# Order matters: bracket stripping must precede fraction rewrites so that
# \frac{\left(a\right)}{\left(b\right)} can simplify cleanly.
# ==========================================================================
