"""
Core canonicalization logic.  Applies rules from rules.py in the
order documented in PIPELINE_ORDER at the bottom of that file.
"""
from __future__ import annotations

import re
import json
from copy import deepcopy
from typing import Iterable

from . import rules as R


# ---------------------------------------------------------------------------
# Rule application
# ---------------------------------------------------------------------------
# Key correctness point: LaTeX commands (\R, \to, \cup) must be matched
# WITH WORD BOUNDARIES so that \R does not match inside \Rightarrow,
# \to does not match inside \top, etc. Plain str.replace is unsafe.

def _apply_literal_rules(text: str, mapping: dict) -> str:
    """Apply replacement rules with boundary-aware matching.

    - Keys starting with "\\" (LaTeX commands): matched only when NOT
      followed by another letter. Prevents \\R matching inside \\Rightarrow.
    - Other keys: simple string replacement.
    Longer keys are tried first so that, e.g., \\Rightarrow runs before \\R.
    """
    # Split by whether key is a command form
    command_keys = sorted([k for k in mapping if k.startswith("\\")],
                          key=len, reverse=True)
    literal_keys = sorted([k for k in mapping if not k.startswith("\\")],
                          key=len, reverse=True)

    for k in command_keys:
        v = mapping[k]
        if k == v:
            continue
        # Build regex: escaped key followed by non-letter
        pat = re.compile(re.escape(k) + r"(?![A-Za-z])")
        # Use lambda to avoid backreference interpretation of backslashes in v
        text = pat.sub(lambda m, v=v: v, text)

    for k in literal_keys:
        v = mapping[k]
        if k == v:
            continue
        text = text.replace(k, v)

    return text


# ---------------------------------------------------------------------------
# Fraction rewrites (balanced-brace aware)
# ---------------------------------------------------------------------------

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


def _rewrite_frac(text: str) -> str:
    """Rewrite \\frac{a}{b} -> {a}/{b}, handling nested braces."""
    out = []
    i = 0
    while i < len(text):
        if text.startswith(r"\frac", i):
            # Skip \frac + optional whitespace + {
            j = i + len(r"\frac")
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] == "{":
                num_end = _find_matching_brace(text, j)
                if num_end >= 0:
                    k = num_end + 1
                    while k < len(text) and text[k].isspace():
                        k += 1
                    if k < len(text) and text[k] == "{":
                        den_end = _find_matching_brace(text, k)
                        if den_end >= 0:
                            num = text[j + 1 : num_end]
                            den = text[k + 1 : den_end]
                            # Recurse in case numerator or denominator has \frac
                            num = _rewrite_frac(num)
                            den = _rewrite_frac(den)
                            out.append("{" + num + "}/{" + den + "}")
                            i = den_end + 1
                            continue
        out.append(text[i])
        i += 1
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
    """Rewrite \\exp(x) -> e^{x}.  Only handles \\exp(...) form; \\exp{x}
    and \\exp x are left for the user to inspect."""
    return re.sub(R.EXP_PATTERN, R.EXP_REPLACEMENT, text)


def _rewrite_log_to_ln(text: str) -> str:
    """\\log (no subscript) -> \\ln.  \\log_{10} stays \\log_{10}."""
    return re.sub(R.LOG_TO_LN_PATTERN, r"\\ln", text)


def _strip_overset_underset(text: str) -> str:
    """\\overset{X}{Y} -> Y, similarly \\underset, \\stackrel.

    The decoration X (e.g., 'x \\to \\infty' in a limit) is stripped and
    only the main symbol Y is kept. Balanced-brace matching.
    """
    for cmd in R.OVERSET_COMMANDS:
        result = []
        i = 0
        while i < len(text):
            if text.startswith(cmd, i):
                j = i + len(cmd)
                while j < len(text) and text[j].isspace():
                    j += 1
                if j < len(text) and text[j] == "{":
                    x_end = _find_matching_brace(text, j)
                    if x_end >= 0:
                        k = x_end + 1
                        while k < len(text) and text[k].isspace():
                            k += 1
                        if k < len(text) and text[k] == "{":
                            y_end = _find_matching_brace(text, k)
                            if y_end >= 0:
                                # Keep Y, drop X. Recurse on Y in case it
                                # contains nested overset.
                                y_str = _strip_overset_underset(
                                    text[k + 1: y_end]
                                )
                                result.append(y_str)
                                i = y_end + 1
                                continue
            result.append(text[i])
            i += 1
        text = "".join(result)
    return text


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


def _flip_inequalities(text: str) -> str:
    """Rewrite (simple_lhs > simple_rhs) -> (simple_rhs < simple_lhs) and
    similar for \\geq -> \\leq. Only flips when both sides are simple atoms
    to avoid changing meaning in complex contexts.
    """
    # Map of op -> its reverse
    flip_map = {
        ">": "<", "<": "<",  # > flips; < already canonical
        r"\geq": r"\leq", r"\leq": r"\leq",
        r"\gneq": r"\lneq", r"\lneq": r"\lneq",
        r"\gg": r"\ll", r"\ll": r"\ll",
        r"\ggg": r"\lll", r"\lll": r"\lll",
        r"\succ": r"\prec", r"\prec": r"\prec",
        r"\succeq": r"\preceq", r"\preceq": r"\preceq",
    }

    def try_flip(match):
        lhs, op, rhs = match.group(1), match.group(2), match.group(3)
        canonical_op = flip_map.get(op, op)
        # If op is already the canonical form, no change
        if canonical_op == op:
            return match.group(0)
        return f"{rhs.strip()} {canonical_op} {lhs.strip()}"

    # Build the alternation of simple-operand with the ops we care about.
    # Only flip >-family and succ-family (reverse direction).
    simple_operand = _SIMPLE_OPERAND.pattern
    op_alts = r"(?:\\geq|\\gneq|\\ggg|\\gg|\\succeq|\\succ|>)"
    pattern = re.compile(
        r"(" + simple_operand + r")\s*(" + op_alts + r")\s*(" + simple_operand + r")",
        re.VERBOSE,
    )
    return pattern.sub(try_flip, text)


# ---------------------------------------------------------------------------
# Redundant brace removal
# ---------------------------------------------------------------------------

def _strip_redundant_braces(text: str) -> str:
    """Repeatedly apply brace-stripping patterns until fixpoint.

    Skips braces that are arguments to LaTeX commands (\\mathbb{R},
    \\mathbf{X}) via negative lookbehind in the rule pattern.
    """
    prev = None
    while prev != text:
        prev = text
        for pat, repl in R.REDUNDANT_BRACE_PATTERNS:
            text = re.sub(pat, repl, text)
    return text


def _normalize_bracket_inner_space(text: str) -> str:
    """After \\left/\\right stripping, remove spaces right after ( [ { and
    right before ) ] }."""
    for pat, repl in R.BRACKET_INNER_SPACE_PATTERNS:
        text = re.sub(pat, repl, text)
    return text


# ---------------------------------------------------------------------------
# Prose-math segmentation (minimal version — does not use pylatexenc yet)
# ---------------------------------------------------------------------------

_MATH_DELIM_PATTERN = re.compile(
    r"""
    (?P<display1> \$\$ .*? \$\$ )
  | (?P<display2> \\\[ .*? \\\] )
  | (?P<inline>   \$ [^\$]+ \$ )
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


# Within a math string, identify candidate variable tokens:
#   - single letters: a, b, x, Y, z, ...
#   - Greek commands: \alpha, \beta (that aren't constants)
#   - subscripted variables: a_i (base = a, subscript index = i)
#
# Indices (e.g. the 'i' in a_i, or the 'n' in \sum_{n=0}^N) are candidates
# for renaming to IDX1, IDX2, ...
#
# We treat \alpha, \beta, etc. as VAR-class unless they appear in CONSTANTS.

_TOKEN_PATTERN = re.compile(
    r"""
    (?P<cmd> \\[A-Za-z]+ )
  | (?P<letter> [A-Za-z] )
  | (?P<number> \d+ (?:\.\d+)? )
  | (?P<brace_open> \{ )
  | (?P<brace_close> \} )
  | (?P<op> [+\-*/^_=<>|~!]+ )
  | (?P<lparen> \( )
  | (?P<rparen> \) )
  | (?P<comma> , )
  | (?P<ws> \s+ )
  | (?P<other> . )
    """, re.VERBOSE | re.DOTALL)


def _extract_variables(math_text: str) -> list[str]:
    """Return a list of candidate variable names in first-occurrence order.

    Recognises as variables:
      - single Latin letters except LETTER_CONSTANTS (e, i, ...)
      - Greek command names in GREEK_VARIABLE_COMMANDS

    Treats as non-variables (never renamed):
      - Commands in CONSTANTS, STANDARD_FUNCTIONS, NUMBER_SETS_CANONICAL
      - Any other LaTeX command (relations, operators, arrows, logic, ...)
      - Letters listed in LETTER_CONSTANTS

    v1 does NOT distinguish function names from generic variables; f in
    f(x) is tagged as VAR, not FN. Future work: inspect for f(...) call
    patterns and tag f as FN-class.
    """
    seen: set[str] = set()
    order: list[str] = []
    for m in _TOKEN_PATTERN.finditer(math_text):
        tok = m.group(0)
        if m.group("cmd"):
            # Only Greek-letter commands count as variables; everything else
            # is an operator/relation/function and is left alone.
            if tok not in R.GREEK_VARIABLE_COMMANDS:
                continue
            if tok in _NEVER_RENAME:
                continue
            if tok in seen:
                continue
            seen.add(tok)
            order.append(tok)
        elif m.group("letter"):
            if tok in R.LETTER_CONSTANTS:
                continue
            if tok in seen:
                continue
            seen.add(tok)
            order.append(tok)
        # numbers / operators / braces / whitespace / commas -> ignore
    return order


def _extract_math_only(text: str) -> str:
    """Extract only the content inside $..$ / $$...$$ delimiters."""
    parts = []
    for kind, segment in _segment(text):
        if kind == "math":
            parts.append(segment)
    return " ".join(parts)


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
            math_only = _extract_math_only(val)
            for var in _extract_variables(math_only):
                if var not in seen:
                    seen.add(var)
                    order.append(var)
        # also process lists
        for field in ("assumptions", "conclusions"):
            items = node.get(field) or []
            if isinstance(items, list):
                for item in items:
                    for var in _extract_variables(item or ""):
                        if var not in seen:
                            seen.add(var)
                            order.append(var)

    return {
        var: f"{R.VAR_PREFIX}{i + 1}"
        for i, var in enumerate(order)
    }


def _apply_rename_in_math(math_text: str, rename_map: dict) -> str:
    """Apply rename map inside a math segment, respecting token boundaries.

    Uses a SINGLE-PASS regex alternation so that replacement tokens (V1, V2)
    don't get re-renamed by subsequent rules. This prevents the cascade bug
    where \\epsilon -> V19 and then V in V19 matches 'V' -> V27 giving V2719.
    """
    if not rename_map:
        return math_text

    # Build ONE regex with all alternatives, longest first.
    # Each alternative has its own boundary constraints.
    alternatives = []
    # Map from regex-group-name -> replacement
    group_map = {}
    for idx, (src, dst) in enumerate(rename_map.items()):
        gname = f"g{idx}"
        if src.startswith("\\"):
            # Command: escape + not followed by letter
            alt = f"(?P<{gname}>{re.escape(src)})(?![A-Za-z])"
        elif src in R.NORM_LETTERS:
            # Norm-space letters (l, L): only rename when NOT followed by
            # _ or ^ (which would make it l_1, L^2 etc. = a norm name).
            alt = f"(?<![A-Za-z\\\\])(?P<{gname}>{re.escape(src)})(?![A-Za-z_^])"
        else:
            # Letter: not preceded by letter/backslash, not followed by letter
            alt = f"(?<![A-Za-z\\\\])(?P<{gname}>{re.escape(src)})(?![A-Za-z])"
        alternatives.append(alt)
        group_map[gname] = dst

    if not alternatives:
        return math_text

    # Sort by source length descending (longest match wins in alternation)
    items = sorted(zip(alternatives, rename_map.keys()), key=lambda x: len(x[1]), reverse=True)
    combined = "|".join(alt for alt, _ in items)
    pattern = re.compile(combined)

    def _replacer(m):
        for gname, dst in group_map.items():
            if m.group(gname) is not None:
                return dst
        return m.group(0)  # fallback: no change

    return pattern.sub(_replacer, math_text)


# ---------------------------------------------------------------------------
# The top-level pipeline
# ---------------------------------------------------------------------------

def _canonicalize_math_segment(math_text: str, rename_map: dict | None) -> str:
    """Apply all math-level rules to a single math segment (with $..$ still
    on the outside)."""
    # Strip the delimiters for processing, remember which kind.
    if math_text.startswith("$$") and math_text.endswith("$$"):
        inner = math_text[2:-2]
        delim_open, delim_close = "$$", "$$"
    elif math_text.startswith(r"\[") and math_text.endswith(r"\]"):
        inner = math_text[2:-2]
        delim_open, delim_close = r"\[", r"\]"
    elif math_text.startswith("$") and math_text.endswith("$"):
        inner = math_text[1:-1]
        delim_open, delim_close = "$", "$"
    else:
        inner = math_text
        delim_open, delim_close = "", ""

    # Phase 1 -- whitespace / spacing command strip
    inner = _apply_literal_rules(inner, R.RULES_SPACING)

    # Phase 2 -- bracket normalization (strip \left, \right, \big*, \Big*)
    inner = _apply_literal_rules(inner, R.RULES_BRACKETS)

    # Phase 3-4 -- Greek
    inner = _apply_literal_rules(inner, R.RULES_GREEK_UNICODE_TO_COMMAND)
    inner = _apply_literal_rules(inner, R.RULES_GREEK_VARIANTS)

    # Phase 5 -- number set canonicalization
    inner = _apply_literal_rules(inner, R.RULES_NUMBER_SETS)

    # Phase 6-8 -- operators, relations, set relations
    inner = _apply_literal_rules(inner, R.RULES_OPERATORS)
    inner = _apply_literal_rules(inner, R.RULES_RELATIONS)
    inner = _apply_literal_rules(inner, R.RULES_SET_RELATIONS)

    # Phase 9-10 -- arrows, logic
    inner = _apply_literal_rules(inner, R.RULES_ARROWS)
    inner = _apply_literal_rules(inner, R.RULES_LOGIC)

    # Phase 10b -- ell -> l unification
    inner = _apply_literal_rules(inner, R.RULES_ELL)

    # Phase 11 -- function name aliases
    inner = _apply_literal_rules(inner, R.RULES_FUNCTION_ALIASES)

    # Phase 12 -- environment aliases
    inner = _apply_literal_rules(inner, R.RULES_ENVIRONMENTS)

    # Phase 13 -- fraction aliases (\dfrac, \tfrac -> \frac)
    inner = _apply_literal_rules(inner, R.RULES_FRAC_ALIASES)

    # Phase 14a -- \overset / \underset / \stackrel stripping
    inner = _strip_overset_underset(inner)

    # Phase 14b -- regex rewrites (fractions, binomials, exp, log)
    inner = _rewrite_frac(inner)
    inner = _rewrite_binom(inner)
    inner = _rewrite_exp(inner)
    inner = _rewrite_log_to_ln(inner)

    # Phase 15 -- inequality direction normalization
    inner = _flip_inequalities(inner)

    # Phase 16 -- redundant brace removal
    inner = _strip_redundant_braces(inner)

    # Phase 16b -- normalize space inside brackets
    inner = _normalize_bracket_inner_space(inner)

    # Phase 17 -- collapse whitespace
    inner = re.sub(R.WHITESPACE_COLLAPSE_PATTERN, R.WHITESPACE_COLLAPSE_REPLACEMENT, inner).strip()

    # Phase 18 -- variable alpha-rename (if map provided)
    if rename_map is not None:
        inner = _apply_rename_in_math(inner, rename_map)

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
    for kind, segment in _segment(text):
        if kind == "math":
            out_parts.append(_canonicalize_math_segment(segment, rename_map))
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
