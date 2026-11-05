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
import re as _re
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


# Edges with confidence below this are drawn faded (e.g. low-confidence
# term_reuse links at 0.3). Overridable via --min-confidence on the CLI.
LOW_CONF_THRESHOLD = 0.5
# When True, low-confidence edges are dropped entirely instead of faded
# (set by --hide-low-confidence).
HIDE_LOW_CONF = False

# ── Colors ──────────────────────────────────────────────────────────────────
NODE_COLORS = {
    "definition":  {"header": "#27AE60", "body": "#D5F5E3"},
    "theorem":     {"header": "#C0392B", "body": "#FADBD8"},
    "lemma":       {"header": "#D35400", "body": "#F5CBA7"},
    "corollary":   {"header": "#943126", "body": "#F2D7D5"},
    "algorithm":   {"header": "#2471A3", "body": "#D4E6F1"},
    "equation":    {"header": "#5DADE2", "body": "#EBF5FB"},
    "proposition": {"header": "#B03A2E", "body": "#FADBD8"},
    "property":    {"header": "#B03A2E", "body": "#FADBD8"},   # same as proposition
    "proof":       {"header": "#8E44AD", "body": "#E8DAEF"},
    "proof_step":  {"header": "#A569BD", "body": "#F4ECF7"},
    "claim":       {"header": "#E74C3C", "body": "#FDEDEC"},
    "example":     {"header": "#E67E22", "body": "#FAE5D3"},   # orange
    "remark":      {"header": "#117A65", "body": "#A2D9CE"},   # teal
    "problem":     {"header": "#7D3C98", "body": "#E8DAEF"},   # darker purple
    "conjecture":  {"header": "#B9770E", "body": "#FCF3CF"},   # gold
    "algorithm_step": {"header": "#5DADE2", "body": "#EBF5FB"},
    "open_problem":   {"header": "#B7950B", "body": "#FCF3CF"},
    "assumption":     {"header": "#5D6D7E", "body": "#EAEDED"},
}


def _gen_name_from_node(n):
    """Last-resort label generator from a node's type + index."""
    typ = (n.get("type") or "").lower()
    idx = n.get("index") or "?"
    prefix = {
        "theorem": "T", "lemma": "L", "proposition": "P", "corollary": "C",
        "claim": "Cl", "conjecture": "Cj", "definition": "D", "proof": "Pr",
        "equation": "E", "algorithm": "A", "problem": "Q",
        "example": "Ex", "remark": "R", "open_problem": "OQ",
    }.get(typ, "N")
    return f"{prefix}{idx}"


def _normalize_schema(data, source_path=None):
    """Normalize a loaded paper graph to the canonical schema (schema A).

    Fallback to schema B (parse_batch.py: 'label', 'clean_text', 'raw_latex',
    '[MATH]' placeholders). Modifies data in place and returns it.
    """
    # `proves` is a string in 1216 of 1236 proof nodes across the corpus, but
    # one paper writes it as a one-element list. Four separate call sites did
    # `node["proves"] in some_dict`, which raises TypeError on a list. Coerce
    # once here rather than guarding each reader.
    for _n in (data.get("nodes") or []):
        if isinstance(_n, dict) and isinstance(_n.get("proves"), (list, tuple)):
            _n["proves"] = _n["proves"][0] if _n["proves"] else None

    # Resolve the paper's own macros HERE, not in draw_dag, because
    # generate_interactive_html() reads data["nodes"] directly — so the SVG
    # boxes were getting resolved text while the HTML side panel still showed
    # raw `\eq`, `\col`, `\rn`. Doing it once at load covers both.
    # Per-paper on purpose: `\rn` is \mathbb{R}^n in one paper, \real^N in
    # another and \mathbb{R}_n in a third (E143).
    try:
        _macros = (data.get("metadata") or {}).get("macros") or {}
        if data.get("nodes"):
            data["nodes"] = _resolve_nodes(data["nodes"], _macros)
        _md = data.get("metadata")
        if isinstance(_md, dict):
            from latex_macros import normalize_for_mathtext as _nfm
            for _f in ("title", "subtitle"):
                if isinstance(_md.get(_f), str):
                    _md[_f] = _nfm(_md[_f], _macros)
    except Exception as _e:
        print("  [warn] macro resolution skipped: %s" % _e)

    import re as _re_local
    nodes = data.get("nodes", []) or []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        stmt = n.get("statement") or ""
        raw  = n.get("raw_latex") or ""
        if raw and "[MATH]" in stmt and "[MATH]" not in raw:
            cleaned = _re_local.sub(r'^\s*\\label\{[^}]*\}\s*', '', raw)
            cleaned = _re_local.sub(r'\s+', ' ', cleaned).strip()
            if cleaned:
                n["statement"] = cleaned
                stmt = cleaned
        if not n.get("statement_clean"):
            ct = n.get("clean_text") or ""
            if ct and "[MATH]" not in ct:
                n["statement_clean"] = ct
            elif stmt and "[MATH]" not in stmt:
                n["statement_clean"] = stmt
        if not n.get("name"):
            n["name"] = n.get("label") or n.get("id") or _gen_name_from_node(n)
        for fld in ("assumptions", "conclusions"):
            arr = n.get(fld)
            if isinstance(arr, list) and arr:
                n[fld] = [s for s in arr
                          if isinstance(s, str) and "[MATH]" not in s]
    md = data.get("metadata")
    if isinstance(md, dict):
        if not md.get("title"):
            md["title"] = (md.get("paper_id") or
                          (source_path.stem if source_path else "(untitled)"))
        data["metadata"] = md
    return data


def _as_text(v, sep=", "):
    """Coerce a list-or-string node field to a single display string.

    Mirror of `_as_list`, for the fields that are rendered as text. The v5.1
    schema makes `proof_strategy` a LIST of strategy labels
    (["construction", "compactness", ...]); earlier formats wrote a free-text
    string, and the rules parser writes the proof body itself. All three must
    render, so lists are joined rather than assumed away — passing a list to
    `.strip()` is what used to raise
    `AttributeError: 'list' object has no attribute 'strip'` on 190 of the 200
    v5.1 silver papers.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return sep.join(str(x).strip() for x in v
                        if x is not None and str(x).strip())
    return str(v)


def _as_list(v):
    """Coerce a list-or-string node field to a list of strings."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, list):
        return v
    return [str(v)]
DEFAULT_COLOR = {"header": "#566573", "body": "#EAECEE"}
PROOF_COLOR = "#E8DAEF"

# ── Raster budget ──
# Caps PNG pixels so memory stays bounded regardless of node count. Purely a
# rasterisation setting — it does not affect layout, and SVG/HTML ignore it.
PNG_DPI = 100            # 12pt text -> 16.7 px, comfortably readable.
                         # 200 gave 33 px: ~3x more than any eye needs,
                         # at 4x the pixels. Unlike a photograph there is
                         # a hard ceiling on useful resolution here — the
                         # content is text and rectangles, so once glyph
                         # edges are crisp, extra dpi stores nothing new.
MIN_PNG_DPI = 40         # never go below this, however large the figure
MAX_RASTER_PX = 100_000_000   # ~0.4 GB RGBA before tight-bbox double render


# ── Edge colour by type ──────────────────────────────────────────────────
# Every edge used to be drawn the same dark grey (only `resolves` and
# low-confidence differed), so a reader could not tell a proof link from a
# dependency without clicking. Colours follow the semantic grouping in
# src/edge_types.py: dependencies blue-grey, the "settles it" family warm,
# the pedagogical family green, foundation links faint.
EDGE_COLORS = {
    "uses":        "#455A64",   # generic dependency (the default, most common)
    "generalizes": "#00796B",   # subtypes of uses — same family, distinguishable
    "specializes": "#00838F",
    "proves":      "#6A1B9A",   # establishes the target
    "resolves":    "#1976D2",   # kept from the previous hard-coded value
    "illustrates": "#2E7D32",   # pedagogical
    "tests":       "#558B2F",
    "grounded_to": "#9E9E9E",   # foundation link, deliberately faint
}
DEFAULT_EDGE_COLOR = "#333333"


def edge_type_color(etype):
    """Colour for an edge type, falling back to the historical dark grey."""
    return EDGE_COLORS.get(str(etype or "uses"), DEFAULT_EDGE_COLOR)

# ── Layout constants (shared between draw_dag and draw_foundation_ghosts) ──
MIN_BOX_W = 3.0
MAX_BOX_W = 6.0
BOX_GAP_X = 0.5
LEVEL_GAP_Y = 5.0
HEADER_H = 0.45
LINE_H = 0.28
PADDING = 0.10

# ── The data-unit ↔ inch contract ──────────────────────────────────────────
# Layout is done in data units; fonts are sized in POINTS, which are absolute.
# So every chars-per-unit constant below is only meaningful once inches-per-
# data-unit is fixed. draw_dag pins it: the figure is sized strictly
# proportionally at IN_PER_UNIT, with the margin bought in data units.
IN_PER_UNIT = 0.8        # inches of canvas per data unit, inside the axes
AXES_FRAC = 0.96         # fraction of the figure the axes occupy
MARGIN_IN = 2.0          # total whitespace margin, in inches

# How many characters of text fit in one data unit, per font role. MEASURED,
# not derived: render a paper, take each text artist's true window extent and
# divide _display_width(s) by its width in data units. At IN_PER_UNIT=0.8 the
# medians are 9.6 (body 12pt) and 7.1 (header 14pt bold); these are the p10s,
# so ~90% of lines fit with room to spare and the rest lean on the slack in
# _needed_w. The old values (12 and 9.0) were ~27% too optimistic — they had
# been calibrated when the canvas was effectively 1.0 in/unit.
CHARS_PER_UNIT = 9.2
HEADER_CPU = 6.8         # 14pt bold is ~35% wider per character than 12pt
HEADER_NAME_MAX = 30     # cap on the name shown in a header, in characters


def _header_text_for_box(nid, name, w):
    """The header string actually drawn in a box of data-unit width `w`.

    Returns `(text, header_chars)`. Used by BOTH the width solver and the
    renderer, because when they disagreed the header could not fit its own box:
    the solver assumed CHARS_PER_UNIT and capped the name at HEADER_NAME_MAX,
    while the renderer hardcoded 9 chars/unit and applied no cap at all — so
    every wide box drew a longer header than had been measured for it.
    """
    header_chars = max(len(nid) + 4, int(w * HEADER_CPU) - 2)
    if not name:
        return nid, header_chars
    avail = min(max(6, header_chars - len(nid) - 2), HEADER_NAME_MAX)
    return "%s: %s" % (nid, _shorten(name, avail)), header_chars


# ── Semantic zoom (level of detail) ──────────────────────────────────────
# A 188-node paper is a ~116x46 inch figure. Fitting it to a window puts body
# text at well under a pixel, so zooming out gave an unreadable smear and
# zooming in lost the structure — you could never see shape and content at once.
#
# Geometric zoom scales pixels; SEMANTIC zoom changes what is drawn. Body lines
# are tagged here so the page can drop them below the size at which they could
# be read anyway, leaving labelled boxes and edges — the structure — legible at
# any scale. Nothing is removed from the SVG, only hidden, so a reader who zooms
# in gets the detail back.
#
# 12pt body text renders at 16 CSS px at zoom 1 (matplotlib writes px and pt at
# the 96/72 ratio), so it stops being readable at roughly zoom 0.5. That is the
# threshold the page uses.
_LOD_SEQ = [0]


def _lod_body(artist):
    """Tag a text artist as body-tier detail, hidden when zoomed far out."""
    try:
        artist.set_gid("lodbody_%d" % _LOD_SEQ[0])
        _LOD_SEQ[0] += 1
    except Exception:
        pass
    return artist


def _fit_fontsize(line, avail_units, base=12, floor=7.0):
    """Shrink a body line that cannot fit its box, rather than let it spill.

    Wrapping alone cannot bound line width: a display equation is one
    unbreakable token, so `_wrap` has nowhere to break
    `\\min_\\mathbf{x}\\{f(\\mathbf{x})\\}` and the line runs past the box edge
    however narrow the wrap width. Scaling the font is the same last-resort the
    header has always used, and it is layout-safe — the line COUNT is unchanged,
    so the box height computed earlier still holds.
    """
    if not line or avail_units <= 0:
        return base
    # Deliberately more pessimistic than CHARS_PER_UNIT. That constant is the
    # p10 of the measured distribution, so ~10% of lines are genuinely wider
    # than it predicts — and those are exactly the lines that reach this
    # function. Costs nothing for lines that already fit, since the shrink only
    # applies once `est` exceeds the available width.
    est = _display_width(line) / (CHARS_PER_UNIT * 0.92)
    if est <= avail_units:
        return base
    return max(floor, base * avail_units / est)


# ── Text helpers ────────────────────────────────────────────────────────────
# The matplotlib-mathtext safety layer (the fix tables, the supported-command
# whitelist, the unknown-command fallback and the dollar-balance repair) moved
# to latex_macros.py. It is not a rendering concern: scripts/audit_mathtext.py
# predicts failures with it and cross-paper comparison needs the same rewrite
# to compare like with like, and neither should have to import a figure module
# to reach a dict. Re-exported so every existing reference keeps working.
import latex_macros                                              # noqa: E402
from latex_macros import (                                       # noqa: E402
    _LATEX_FIXES, _LATEX_REGEX_FIXES, _KNOWN_MATHTEXT_COMMANDS,
    _BARE_MATH_NAMES, _fallback_unknown_commands,
    _restore_bare_math_names, _balance_dollars, _can_render_math,
    _strip_math_on_error, sanitize_for_mathtext,
)

def _statement_render_source(n):
    """Pick the best statement text for MathJax rendering in the side panel.

    statement / statement_clean are de-TeX'd for matching ($ delimiters and
    command backslashes stripped) so they won't render. Prefer raw_latex when
    it still carries TeX (a $ or a backslash command); strip stray \\label{...}
    and collapse whitespace. Falls back to statement otherwise.
    """
    raw = _as_text(n.get("raw_latex")).strip()
    stmt = _as_text(n.get("statement"))
    src = raw if _re.search(r'[$\\]', raw) else stmt
    src = latex_macros.display_tex(src)                 # text commands, anchors and drawings outside the math
    src = _re.sub(r'[ \t\r\f\v]+', ' ', src).strip()
    return src



_CURRENT_MACROS = {}
_LAST_CYCLE_EDGES = []




def _sanitize_math(text):
    """Renderer-side wrapper: sanitize with the paper currently being drawn.

    draw_dag sets `_CURRENT_MACROS` before laying out each paper. Binding it
    here keeps that global confined to the renderer rather than letting the
    shared module read it — an audit run would otherwise inherit whichever
    paper was drawn last.
    """
    # mathtext needs braces: \mathcal E -> \mathcal{E}
    text = _re.sub(r"\\(math(?:cal|bb|bf|rm|frak|scr|sf|it))\s+([A-Za-z0-9])", r"\\\1{\2}", text or "")
    return sanitize_for_mathtext(text, _CURRENT_MACROS)


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


# Display-math delimiters. An equation node's statement is usually a whole
# display block, which carries no `$`, so the has_math branch below used to send
# it to _to_display_text and draw it as a backslash-littered plain string —
# `\[H(\sigma_1,\ldots)\,:=\,\min_\mathbf{x}...` on one unbreakable line, far
# wider than its box. mathtext has no display mode, but the CONTENT is ordinary
# math, so re-delimit it as inline math and let it render.
_DISPLAY_ENVS = ("equation", "align", "eqnarray", "gather", "multline",
                 "displaymath", "split", "aligned")
_DISPLAY_PATTERNS = [
    _re.compile(r"\$\$(.+?)\$\$", _re.S),
    _re.compile(r"\\\[(.+?)\\\]", _re.S),
    _re.compile(r"\\begin\{(?:%s)\*?\}(.+?)\\end\{(?:%s)\*?\}"
                % ("|".join(_DISPLAY_ENVS), "|".join(_DISPLAY_ENVS)), _re.S),
]
# Alignment/row separators are layout, not content, and mathtext rejects them.
_ALIGN_JUNK = _re.compile(r"\\\\|&|\\notag\b|\\nonumber\b|\\qedhere\b")


def _inline_display_math(text):
    """`\\[ x \\]`, `$$x$$`, `\\begin{equation} x \\end{equation}` -> `$x$`."""
    if not text:
        return text
    t = str(text)
    for pat in _DISPLAY_PATTERNS:
        t = pat.sub(lambda m: "$%s$" % _ALIGN_JUNK.sub(" ", m.group(1)).strip(), t)
    return t


# Prose detection, so we only try whole-string math wrapping on things that are
# actually formulas. Setting an English sentence in math mode would render every
# word in italic math font with the spaces collapsed — worse than the plain-text
# fallback it replaces. LaTeX command names are removed first so `\varrho` and
# `\mathbb` don't read as words.
_TEX_CMD_RE = _re.compile(r"\\[A-Za-z]+")
_PROSE_WORD_RE = _re.compile(r"[A-Za-z]{4,}")


def _looks_like_formula(text):
    """True if `text` is a bare formula rather than prose containing notation."""
    if not text:
        return False
    if not _re.search(r"[\\_^=]", text):        # no math signal at all
        return False
    # TWO words, not one: formulas legitimately contain the odd bare function
    # name (`Erfc(...)`, `Var`, `Cov`), and disqualifying on a single word sent
    # 765 real equations down the strip-to-plain-text path. Prose has many.
    return len(_PROSE_WORD_RE.findall(_TEX_CMD_RE.sub(" ", text))) < 2


def _prepare_for_display(text):
    """Prepare text for matplotlib rendering: keep math in $...$, fix unsupported commands.

    - Text already in $...$ is sanitized (unsupported commands replaced)
    - Text with bare LaTeX notation (subscripts, Greek, etc.) gets wrapped in $...$
    - Truly unrenderable things fall back to their command name
    """
    if not text:
        return ""
    t = _inline_display_math(text)

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

    # Has math-like notation but no $ delimiters. Historically this gave up and
    # stripped the LaTeX to plain text, which turns a displayed equation into
    # unreadable pseudo-text — `\mathbb{T}_b(x)=\mathbb{E}[\mathbf{t}_b^{x,r}]`
    # came out as `T_b(x)=E[t_b^x,r]`. That hit 5.0% of all text items (1950 of
    # 38875), mostly equation bodies stored WITHOUT their `\begin{...}` wrapper,
    # so _inline_display_math above never saw a delimiter to key on.
    #
    # We can do better than guessing: wrap the whole thing as math and ask
    # mathtext whether it actually parses. _sanitize_math already ends in
    # _strip_math_on_error, so a candidate that fails comes back with its `$`
    # removed — surviving `$` IS the accept signal. Strictly better than the
    # old behaviour: anything that fails lands on exactly the old fallback.
    if _looks_like_formula(t):
        as_math = _sanitize_math("$%s$" % _ALIGN_JUNK.sub(" ", t).strip())
        if "$" in as_math:
            return as_math
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
    """Longest-path depth of each node; roots = depth 0."""
    return graph_checks.depths(nodes, edges)[0]


def _natural_key(s):
    """Sort key that orders embedded integers numerically: EP2 < EP10.

    v6 ids are {PREFIX}{seq} (TP3, PSP12) and v5.1 ids were {PREFIX}{paper}.{seq}
    (TP1.3); a plain string sort put EP10 before EP2 in both.
    """
    return [(0, int(t), "") if t.isdigit() else (1, 0, t)
            for t in _re.findall(r"\d+|\D+", str(s or ""))]


def _section_sort_key(node):
    """Sort by section number, then by ID.

    Sections are written "2 The main result" / "3.1 Setup" (the number, then
    the title), so only the leading dotted number is parsed. Splitting the
    whole string on "." failed on every titled section and sent all of them
    to 99.
    """
    m = _re.match(r"\s*(\d+(?:\.\d+)*)", str(node.get("section") or ""))
    parts = [float(x) for x in m.group(1).split(".")] if m else [99]
    return (parts, _natural_key(node["id"]))


# ── Containment (parent_id) ─────────────────────────────────────────────────
# `parent_id` is containment, not dependency. Up to v5.1 it was set only on
# proof_step / algorithm_step (child of a proof / algorithm). From v6 it is
# also set on Level-1 nodes (an equation inside a proof step or theorem, a
# claim or lemma stated inside a proof), and a step can sit inside another
# step (a loop body, a sub-claim). The viewer shows it as containment: folded
# nodes go into the panel of the nearest node that is drawn, and nodes that
# are drawn get a link to the node they live in.
def _parent_ref(n):
    """Id of the node containing `n`: `parent_id`, or the older field names."""
    return (n or {}).get("parent_id") or (n or {}).get("parent_proof") \
        or (n or {}).get("parent") or ""


def _host_resolver(node_by_id, proof_map, shown_ids):
    """Return host(nid): the nearest node in `shown_ids` that contains nid.

    Walks up `parent_id`, and from a proof to the result it proves
    (`proof_map`), so a step nested three deep inside the proof of a claim
    stated inside another proof still finds the box it belongs to. A shown
    node is its own host. None when the chain ends without reaching one.
    """
    def host(nid):
        seen = set()
        cur = nid
        while cur and cur not in shown_ids and cur not in seen:
            seen.add(cur)
            cur = proof_map.get(cur) or _parent_ref(node_by_id.get(cur))
        return cur if cur in shown_ids else None
    return host



def _split_proof_into_steps(body):
    """Split a proof body into (label, text) pseudo-steps via Part markers
    or a math-aware paragraph/display-eq split."""
    if not body:
        return []
    part_re = _re.compile(r'\bPart\s*\(?(\d+)\)?', _re.IGNORECASE)
    def_verbs = _re.compile(
        r'\s+(?:is|are|can|follows|holds|will|gives|shows|implies)\b',
        _re.IGNORECASE)
    part_hits = []
    for m in part_re.finditer(body):
        tail = body[m.end():m.end() + 12]
        if tail.startswith(':') or tail.startswith('.') or def_verbs.match(tail):
            part_hits.append(m)
    pieces = []
    if len(part_hits) >= 2:
        for i, m in enumerate(part_hits):
            end = part_hits[i + 1].start() if i + 1 < len(part_hits) else len(body)
            chunk = body[m.end():end].strip(" :.\t\n\\")
            chunk = _re.sub(r'\s+', ' ', chunk).strip(' &\t\n')
            if chunk:
                pieces.append((f"Part ({m.group(1)})", chunk))
        return pieces

    math_open  = _re.compile(r'\\(?:ba\b|begin\{(?:align\*?|eqnarray\*?|gather\*?|equation\*?|array|matrix|aligned)\})')
    math_close = _re.compile(r'\\(?:ea\b|end\{(?:align\*?|eqnarray\*?|gather\*?|equation\*?|array|matrix|aligned)\})')
    split_pat  = _re.compile(r'\\\\|\\par\b|\n\s*\n')

    top_breaks = []
    depth = 0
    i = 0
    while i < len(body):
        mo = math_open.match(body, i)
        if mo:
            depth += 1
            i = mo.end()
            continue
        mc = math_close.match(body, i)
        if mc:
            depth = max(0, depth - 1)
            i = mc.end()
            continue
        if depth == 0:
            ms = split_pat.match(body, i)
            if ms:
                top_breaks.append((i, ms.end()))
                i = ms.end()
                continue
        i += 1

    math_ends = []
    depth = 0
    i = 0
    while i < len(body):
        mo = math_open.match(body, i)
        if mo:
            depth += 1
            i = mo.end()
            continue
        mc = math_close.match(body, i)
        if mc:
            depth = max(0, depth - 1)
            if depth == 0 and mc.end() < len(body):
                math_ends.append(mc.end())
            i = mc.end()
            continue
        i += 1

    cuts = []
    for (s, e) in top_breaks:
        cuts.append((s, e))
    for s in math_ends:
        if any(abs(s - cs) <= 3 or (cs <= s <= ce) for (cs, ce) in cuts):
            continue
        cuts.append((s, s))
    cuts.sort()

    raw_pieces = []
    last = 0
    for (cs, ce) in cuts:
        raw_pieces.append(body[last:cs])
        last = ce
    raw_pieces.append(body[last:])

    cleaned = []
    for p in raw_pieces:
        p = _re.sub(r'\s+', ' ', p).strip(' &\t\n')
        if p and len(p) >= 8:
            cleaned.append(p)
    if len(cleaned) >= 2 and not math_open.search(cleaned[-1]) \
            and len(cleaned[-1]) < 160:
        cleaned[-2] = cleaned[-2] + ' ' + cleaned[-1]
        cleaned.pop()
    for p in cleaned:
        pieces.append(("", p))
    return pieces


# ── Merge proofs into parent theorems ───────────────────────────────────────
def split_cycle_edges(nodes, edges):
    """Split `edges` into (acyclic, back_edges) without discarding anything.

    The layered layout needs a DAG, and the extraction spec has been satisfying
    that by DELETING the offending edge (E120) — irreversibly, and invisibly,
    which is exactly why its prevalence could never be measured. Forward
    references ("see Remark 3 below") are normal mathematical writing, so the
    dependency is real; only the drawing cannot accommodate it.

    Separating the two concerns fixes that: storage keeps every edge, the VIEWER
    drops the minimum needed to layer, and what it dropped stays visible as a
    count and a toggle instead of vanishing.

    Deterministic: nodes are visited in input order and edges sorted, so the
    same graph always yields the same back set.
    """
    adj = defaultdict(list)
    for i, e in enumerate(edges):
        adj[e.get("source")].append((e.get("target"), i))
    for k in adj:
        adj[k].sort()

    WHITE, GREY, BLACK = 0, 1, 2
    color = defaultdict(int)
    back = set()

    for start in [n["id"] for n in nodes]:
        if color[start] != WHITE:
            continue
        stack = [(start, iter(adj.get(start, ())))]
        color[start] = GREY
        while stack:
            node, it = stack[-1]
            advanced = False
            for tgt, idx in it:
                if color[tgt] == GREY:      # edge into the current path = cycle
                    back.add(idx)
                    continue
                if color[tgt] == WHITE:
                    color[tgt] = GREY
                    stack.append((tgt, iter(adj.get(tgt, ()))))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
    keep = [e for i, e in enumerate(edges) if i not in back]
    drop = [e for i, e in enumerate(edges) if i in back]
    return keep, drop


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
            # `proves` is a string in 1216 of 1236 proof nodes, but one paper
            # (1212.6243v1) writes it as a one-element list. A list is
            # unhashable, so the membership test below raised TypeError.
            target_id = n.get("proves") or n.get("parent") or ""
            if isinstance(target_id, (list, tuple)):
                target_id = target_id[0] if target_id else ""
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
            node_by_id[n["id"]]["proof_step_count"] = 0

    # Count proof_step nodes per theorem. Resolved through the containment
    # chain, so steps nested inside steps (v6) count toward the theorem too.
    _host = _host_resolver(node_by_id, proof_map, {
        n["id"] for n in nodes if n["id"] not in proof_map
        and n.get("type") not in ("proof_step", "algorithm_step", "equation")})
    for n in nodes:
        if n.get("type") != "proof_step":
            continue
        thm_id = _host(n["id"])
        if thm_id in node_by_id and node_by_id[thm_id].get("type") != "proof":
            node_by_id[thm_id]["proof_step_count"] = (
                node_by_id[thm_id].get("proof_step_count", 0) + 1)

    # Stash proof bodies so we can estimate synthesized step counts for
    # rules-mode JSONs that lack proof_step children.
    _proof_bodies_for_synth = defaultdict(list)

    display_nodes = []
    for n in nodes:
        if n["id"] in proof_map:
            parent_id = proof_map[n["id"]]
            parent = node_by_id[parent_id]
            parent.setdefault("proof_info", [])
            body = (_as_text(n.get("proof_strategy")) or _as_text(n.get("clean_text"))
                    or _as_text(n.get("statement"))).strip()
            if body:
                parent["proof_info"].append(body)
            synth_src = (_as_text(n.get("raw_latex")) or _as_text(n.get("clean_text"))
                         or _as_text(n.get("statement"))).strip()
            if synth_src:
                _proof_bodies_for_synth[parent_id].append(synth_src)
            continue
        display_nodes.append(n)

    # For rules-mode (no proof_step children), estimate steps by splitting
    # each proof body. Tier2's proof_step_count is already set, so skip.
    for thm_id, bodies in _proof_bodies_for_synth.items():
        if node_by_id[thm_id].get("proof_step_count", 0) > 0:
            continue
        total = 0
        for body in bodies:
            total += len(_split_proof_into_steps(body))
        if total > 0:
            node_by_id[thm_id]["proof_step_count"] = total

    # Redirect edges: replace proof_id with its theorem_id
    display_map = {}
    order = []
    for e in edges:
        s = proof_map.get(e["source"], e["source"])
        t = proof_map.get(e["target"], e["target"])
        if s == t:
            continue  # skip self-loops from merging
        key = (s, t)
        conf = e.get("confidence", 1.0)
        if key not in display_map:
            display_map[key] = {"source": s, "target": t,
                                "type": e.get("type", ""),
                                "note": e.get("note", ""),
                                "confidence": conf,
                                "backward": bool(e.get("backward")),
                                "mention": bool(e.get("mention"))}
            order.append(key)
            continue
        # A merged edge is backward (or a mention) only if every edge merged
        # into it is.
        display_map[key]["backward"] &= bool(e.get("backward"))
        display_map[key]["mention"] &= bool(e.get("mention"))
        if conf > display_map[key].get("confidence", 1.0):
            # keep the strongest evidence when several edges merge to (s, t)
            display_map[key]["confidence"] = conf
            display_map[key]["type"] = e.get("type", "")

    display_edges = [display_map[k] for k in order]
    return display_nodes, display_edges, proof_map


# ── Foundation graph linking (shared by PNG and HTML) ────────────────────────

def _resolve_foundation_path(foundation_path=None):
    """Find the best available foundation index path.

    Port #6 (51K-term with_books index): we look for
    ``clean_foundation_with_books.json`` ahead of ``clean_foundation.json``,
    matching HEAD's preference. Upstream ``link_to_foundation.link_paper``
    has an unescaped-regex bug on backslashed LaTeX terms in the larger
    index, so we wrap the call in compute_foundation_links with try/except
    and fall back to the built-in WELL_KNOWN on failure.
    """
    if foundation_path is not None:
        return foundation_path
    # Auto-detect from common locations — with_books preferred (Port #6).
    candidates = [
        Path("/mnt/g/My Drive/Research/Automath/naturalproofs/clean_foundation_with_books.json"),
        Path("/mnt/g/My Drive/Research/Automath/naturalproofs/clean_foundation.json"),
        Path("/sci/labs/orzuk/orzuk/projects/Authomathics/naturalproofs/clean_foundation_with_books.json"),
        Path("/sci/labs/orzuk/orzuk/projects/Authomathics/naturalproofs/clean_foundation.json"),
        # Mac local (pre-rename Authomathics_data, where the 20MB index lives)
        Path.home() / "Datasets/Authomathics_data/foundation/clean_foundation_with_books.json",
        Path.home() / "Datasets/Authomathics_data/foundation/clean_foundation.json",
        Path.home() / "Datasets/Authomathics_data/naturalproofs/clean_foundation_with_books.json",
        Path.home() / "Datasets/Authomathics_data/naturalproofs/clean_foundation.json",
    ]
    # Also try via config.py — prefer NATURALPROOFS_DIR (resolves new
    # foundation/naturalproofs layout); fall back to DATA_DIR/naturalproofs.
    try:
        from config import NATURALPROOFS_DIR  # type: ignore
        candidates.insert(0, Path(str(NATURALPROOFS_DIR)) / "clean_foundation_with_books.json")
        candidates.insert(1, Path(str(NATURALPROOFS_DIR)) / "clean_foundation.json")
    except ImportError:
        pass
    try:
        from config import DATA_DIR
        data_dir = Path(str(DATA_DIR)) / "naturalproofs"
        candidates.insert(0, data_dir / "clean_foundation_with_books.json")
        candidates.insert(1, data_dir / "clean_foundation.json")
    except ImportError:
        pass
    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except OSError:
            continue
    return None  # will fall back to built-in WELL_KNOWN


def compute_foundation_links(nodes_raw, base_ids, foundation_path=None):
    """Compute foundation ghost map: foundation_name -> list of base node IDs.

    Shared by draw_dag (PNG rendering) and generate_interactive_html.

    Args:
        nodes_raw: list of all node dicts (including proofs, proof steps).
        base_ids: set of node IDs for base nodes (definitions, theorems, lemmas, etc.)
        foundation_path: path to clean_foundation.json, or None for auto-detect.

    Returns:
        (ghost_map, case1_matches, ghost_meta):
            ghost_map: {foundation_name: [base_node_ids]} — for ghost node rendering
            case1_matches: {base_node_id: [foundation_names]} — for inline annotations
            ghost_meta: {foundation_name: {"source": str, "is_book": bool,
                                            "book_label": str}}
                        — per-ghost provenance, used to differentiate book vs.
                          mathlib/proofwiki/herald entries in the renderer.
    """
    from link_to_foundation import build_foundation_index, link_paper
    try:
        from link_to_foundation import _build_automaton  # type: ignore
    except ImportError:
        _build_automaton = None  # type: ignore

    fg_path = _resolve_foundation_path(foundation_path)
    try:
        fg_index = build_foundation_index(fg_path)
        ac, term_map = (None, None)
        if _build_automaton is not None:
            try:
                ac, term_map = _build_automaton(fg_index, min_term_len=5)
            except Exception:
                ac, term_map = (None, None)
        matches = link_paper(nodes_raw, fg_index, min_term_len=5,
                             automaton=ac, term_map=term_map)
    except Exception as _re_err:
        # Upstream link_paper has an unescaped-regex bug on the larger
        # with_books index (LaTeX terms like \lambda). Fall back to None
        # (built-in WELL_KNOWN list inside build_foundation_index).
        print(f"[link] WARNING: foundation linking failed ({_re_err}); falling back to built-in list.")
        fg_index = build_foundation_index(None)
        try:
            matches = link_paper(nodes_raw, fg_index, min_term_len=5)
        except Exception:
            matches = []

    ghost_map = {}   # foundation_name -> set of base node IDs
    case1 = {}       # base_node_id -> list of foundation names
    ghost_meta = {}  # foundation_name -> {source, is_book, book_label}

    for m in matches:
        nid = m["node_id"]
        fname = m["foundation_name"]
        # Record provenance once per foundation name
        if fname not in ghost_meta:
            src = m.get("foundation_source", "") or ""
            ghost_meta[fname] = {
                "source":     src,
                "is_book":    src.startswith("book:"),
                "book_label": m.get("foundation_book_label", "") or "",
            }
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
                                if isinstance(parent, (list, tuple)):
                                    parent = parent[0] if parent else None
                                break
                        break
                    _pv = nr.get("proves")
                    if isinstance(_pv, (list, tuple)):
                        _pv = _pv[0] if _pv else None
                    if _pv and _pv in base_ids:
                        parent = _pv
                        break
            if parent in base_ids:
                ghost_map.setdefault(fname, set()).add(parent)
                case1.setdefault(parent, []).append(fname)

    # Convert sets to lists
    ghost_map = {k: sorted(v) for k, v in ghost_map.items()}
    case1 = {k: sorted(set(v)) for k, v in case1.items()}
    return ghost_map, case1, ghost_meta


def draw_foundation_ghosts(ax, ghost_map, node_rect, ghost_meta=None):
    """Draw foundation ghost nodes and their dashed edges on a matplotlib axes.

    Args:
        ax: matplotlib axes.
        ghost_map: {foundation_name: [base_node_ids]} from compute_foundation_links.
        node_rect: {node_id: (x, y, w, h)} from draw_dag layout.
        ghost_meta: optional {foundation_name: {"source", "is_book", "book_label"}}
            — used to differentiate book entries (dotted border, warmer fill,
            "BookLabel: <name>" header) from mathlib/proofwiki/herald entries.
    """
    if not ghost_map or not node_rect:
        return {}

    if ghost_meta is None:
        ghost_meta = {}

    from matplotlib.patches import FancyArrowPatch

    all_tops = [by + bh for (bx, by, bw, bh) in node_rect.values()]
    all_lefts = [bx for (bx, by, bw, bh) in node_rect.values()]
    all_rights = [bx + bw for (bx, by, bw, bh) in node_rect.values()]
    ghost_y_top = max(all_tops) + LEVEL_GAP_Y * 0.8
    ghost_w = MIN_BOX_W * 1.1
    ghost_h = HEADER_H + LINE_H * 1.5 + PADDING
    ghost_step_x = ghost_w + BOX_GAP_X * 0.5
    ghost_step_y = ghost_h + LEVEL_GAP_Y * 0.25
    ghost_names = sorted(ghost_map.keys())
    # Wrap ghost row into multiple rows so the foundation overlay never makes
    # the overall data extent wider than the main graph. With set_aspect equal,
    # a wider overlay scales the whole figure down → squashed main boxes.
    main_w = (max(all_rights) - min(all_lefts)) if all_rights else 0
    if main_w > 0 and ghost_step_x > 0:
        per_row = max(1, int(main_w // ghost_step_x))
    else:
        per_row = max(1, len(ghost_names))

    ghost_rects = {}
    for gi, gname in enumerate(ghost_names):
        row = gi // per_row
        col = gi % per_row
        row_count = min(per_row, len(ghost_names) - row * per_row)
        row_total_w = row_count * ghost_w + (row_count - 1) * BOX_GAP_X * 0.5
        row_start_x = -row_total_w / 2
        gx = row_start_x + col * ghost_step_x
        # Higher row index → drawn higher above the main graph
        gy = ghost_y_top + row * ghost_step_y

        meta = ghost_meta.get(gname, {}) or {}
        is_book = bool(meta.get("is_book"))
        book_label = meta.get("book_label", "") or ""

        # Visual style depends on origin (book vs mathlib/proofwiki/herald)
        if is_book:
            body_color = "#FFF8E1"   # warm cream
            edge_color = "#A1887F"
            header_color = "#8D6E63"
            line_style = (0, (1, 2))  # dotted
        else:
            body_color = "#E8E8E8"   # cool gray (existing)
            edge_color = "#777777"
            header_color = "#777777"
            line_style = (0, (8, 6))  # dashed (existing)

        # Use a "ghostbook_" prefix for book entries so the JS / CSS layer can
        # style them differently. The shared "ghost" toggle handler still
        # picks them up via the [id^="ghost"] selector used at runtime.
        gid_prefix = "ghostbook" if is_book else "ghost"

        # Ghost box
        grect = FancyBboxPatch(
            (gx, gy - ghost_h), ghost_w, ghost_h,
            boxstyle="round,pad=0.05",
            facecolor=body_color, edgecolor=edge_color,
            linewidth=1.5, linestyle=line_style,
            gid=f"{gid_prefix}_box_{gi}",
        )
        ax.add_patch(grect)
        # Header bar
        gheader = FancyBboxPatch(
            (gx, gy - HEADER_H), ghost_w, HEADER_H,
            boxstyle="round,pad=0.05",
            facecolor=header_color, edgecolor=header_color,
            linewidth=0,
            gid=f"{gid_prefix}_header_{gi}",
        )
        ax.add_patch(gheader)
        # Name text — book entries get "Label: <name>" prefix
        display_name = f"{book_label}: {gname}" if (is_book and book_label) else gname
        short_name = display_name if len(display_name) <= 22 else display_name[:19] + "..."
        ax.text(gx + ghost_w / 2, gy - HEADER_H / 2, short_name,
                ha="center", va="center", fontsize=12, fontweight="bold",
                color="white", gid=f"{gid_prefix}_text_{gi}")
        # References text
        refs_str = "→ " + ", ".join(ghost_map[gname])
        ax.text(gx + ghost_w / 2, gy - HEADER_H - LINE_H * 0.7, refs_str,
                ha="center", va="center", fontsize=10, color="#555",
                gid=f"{gid_prefix}_refs_{gi}")

        ghost_rects[gname] = (gx, gy - ghost_h, ghost_w, ghost_h)

        # Dashed (mathlib) or dotted (book) edges to target nodes.
        edge_color_arrow = "#8D6E63" if is_book else "#999999"
        edge_linestyle = (0, (3, 3)) if is_book else (0, (8, 6))
        for ti, target_id in enumerate(ghost_map[gname]):
            if target_id in node_rect:
                tx, ty, tw, th = node_rect[target_id]
                arrow = FancyArrowPatch(
                    (gx + ghost_w / 2, gy - ghost_h),
                    (tx + tw / 2, ty + th),
                    arrowstyle="-|>,head_length=0.8,head_width=0.35",
                    color=edge_color_arrow, lw=1.5,
                    linestyle=edge_linestyle,
                    connectionstyle="arc3,rad=0.05",
                    shrinkA=3, shrinkB=3,
                    gid=f"{gid_prefix}_edge_{gi}_{ti}",
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
from node_types import ID_SHORT as _ID_SHORT  # noqa: E402
import graph_checks  # noqa: E402
_ID_RE = _re.compile(r"^(%s)(\d+)$" % "|".join(sorted(_ID_SHORT, key=len, reverse=True)))


def display_id(nid, number=None):
    """`TP5` -> "Thm 5", `PSP12` -> "Step 12" (display only; same table as dispId in the JS).
    With the paper's own number, "Thm 1.1" (what a \\ref to the node should read as)."""
    m = _ID_RE.match(str(nid))
    return "%s %s" % (_ID_SHORT[m.group(1)], number or m.group(2)) if m else str(nid)


def _resolve_nodes(nodes, macros):
    """Resolve paper macros + brace-normalise every text field, on a COPY.

    mathtext parses lazily at savefig() time, so sanitising inside
    _sanitize_math only covers the paths that happen to call it — text reaching
    an artist any other way still blew up during rendering. Doing it once here,
    before layout, means there is exactly one place where a paper's LaTeX
    becomes mathtext-safe. Never mutates the caller's data.
    """
    from latex_macros import normalize_for_mathtext as _norm
    # One list, not a str list plus a list list: `input`/`output` occur as
    # BOTH shapes in the corpus, and splitting by shape is what let them fall
    # through. Each of these is either drawn on the figure or shipped to the
    # HTML side panel, so each has to be resolved.
    FIELDS = ("statement", "statement_short", "name", "clean_text", "raw_latex",
              "genus", "definiendum", "label", "proof_strategy",
              "origin_citation", "assumptions", "conclusions", "differentia",
              "input", "output", "section")

    # \ref{eq:x} / \eqref{eq:x} show the id of the node carrying that label
    # (EP1), not the raw key.
    labels = {}
    for n in nodes:
        for k in str(n.get("label") or "").split(","):
            if k.strip() and n.get("id"):
                labels.setdefault(k.strip(), display_id(n["id"], n.get("number")))

    def _resolve(v):
        if isinstance(v, str):
            return _norm(v, macros, labels) if v else v
        if isinstance(v, list):
            return [_resolve(x) for x in v]
        return v

    def _resolve_math(v):
        # An equation node stores a bare formula, with no `$` around it; wrap it
        # so the normaliser knows it is math (`\mbox{ versus}` -> `\text{ versus}`).
        if isinstance(v, str) and v and "$" not in v:
            r = _norm("$" + v + "$", macros, labels)
            if r.startswith("$") and r.endswith("$"):
                return r[1:-1]
        return _resolve(v)

    out = []
    for n in nodes:
        m = dict(n)
        for f in FIELDS:
            if f in m:
                eq = n.get("type") == "equation" and f in ("statement", "raw_latex")
                m[f] = _resolve_math(m[f]) if eq else _resolve(m[f])
        out.append(m)
    return out


def draw_dag(nodes_raw, edges_raw, out_path, figsize=None, metadata=None,
             resolution="standard", show_legend=True, show_foundation=False,
             foundation_path=None, show_extras=True, write_png=True,
             show_title=True):
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

    write_png:
      When True (default) rasterize and save a PNG at out_path (the original
      behaviour).  When False, skip the PNG entirely and only write the sibling
      SVG -- used by the interactive-HTML path, which embeds the SVG and never
      needs the PNG.  Skipping avoids a huge Agg pixel-buffer allocation on
      large graphs (the source of both the slow render and the OOM there).

    show_extras:
      Accepted for API compatibility with callers (op_visualize) that request
      example/remark/cited_result nodes in the SVG.  In "standard" resolution
      these node types are always drawn already; the HTML toggle buttons hide
      them via JS, so this flag is currently a no-op kept to avoid a TypeError.
    """
    # Paper-local macros, so mathtext can resolve \Sc, \GL, \PP ... They ride
    # along in metadata.macros (see scripts/merge_macros.py); a paper without
    # them simply expands nothing.
    global _CURRENT_MACROS
    _CURRENT_MACROS = (metadata or {}).get("macros") or {}
    try:
        nodes_raw = _resolve_nodes(nodes_raw, _CURRENT_MACROS)
        # The title is drawn too, and carries macros just like a statement.
        if isinstance(metadata, dict):
            from latex_macros import normalize_for_mathtext as _norm
            metadata = dict(metadata)
            for _f in ("title", "subtitle"):
                if isinstance(metadata.get(_f), str):
                    metadata[_f] = _norm(metadata[_f], _CURRENT_MACROS)
    except Exception as _e:
        print("  [warn] macro resolution skipped: %s" % _e)

    if resolution == "full":
        # Full resolution: no merging, show everything
        nodes = list(nodes_raw)
        edges = list(edges_raw)
        proof_map = {}
    else:
        # Standard: collapse proofs AND filter out equations/proof_steps/algorithm_steps
        nodes, edges, proof_map = merge_proofs(nodes_raw, edges_raw)
        hidden_types = {"equation", "proof_step", "algorithm_step"}
        hidden_ids = {n["id"] for n in nodes if n.get("type") in hidden_types}
        nodes = [n for n in nodes if n.get("type") not in hidden_types]
        edges = [e for e in edges
                 if e["source"] not in hidden_ids and e["target"] not in hidden_ids]
    if HIDE_LOW_CONF:
        edges = [e for e in edges if float(e.get("confidence", 1.0) or 1.0) >= LOW_CONF_THRESHOLD]
    # Keep cycle-causing edges OUT of the layout but IN the data. draw_dag
    # stores them so the HTML can offer them as a toggle rather than silently
    # losing them, which is the failure mode E120 records.
    # v6 marks a real dependency that points against paper order with
    # `backward: true`; the graph is acyclic only once those are set aside.
    # They are held out of the LAYERING (depth) but still drawn, dash-dotted,
    # together with any further edge split_cycle_edges must hold out.
    # A `mention` edge only refers to its source ("as in Theorem 1"); it is
    # drawn, thin and light, but plays no part in the layering either.
    _backward = [e for e in edges if e.get("backward") or e.get("mention")]
    edges, _cycle_edges = split_cycle_edges(
        nodes, [e for e in edges if not (e.get("backward") or e.get("mention"))])
    _cycle_edges = _backward + _cycle_edges
    global _LAST_CYCLE_EDGES
    _LAST_CYCLE_EDGES = _cycle_edges
    if _cycle_edges:
        print("  [layout] %d edge(s) held out of the layered view "
              "(%d marked backward, %d to break cycles); drawn dash-dotted"
              % (len(_cycle_edges), len(_backward),
                 len(_cycle_edges) - len(_backward)))
    depth = compute_dag_depth(nodes, edges)

    # Group by depth level
    levels = defaultdict(list)
    for n in nodes:
        levels[depth[n["id"]]].append(n)

    # Sort within each level by section (initial heuristic)
    for d in levels:
        levels[d].sort(key=_section_sort_key)

    max_depth = max(levels.keys()) if levels else 0
    max_width = max(len(v) for v in levels.values()) if levels else 1

    # ── Box dimensions ──
    # Layout constants are module-level (shared with draw_foundation_ghosts)
    pass
    # CHARS_PER_UNIT defined at module level
    MAX_LINES_PER_SECTION = 3

    from node_types import PROVABLE as _THEOREM_LIKE

    def _theorem_has_inline_content(n):
        """True if a theorem-like node has assume/conclude to render;
        otherwise it falls through to the statement-only branch."""
        return bool(_as_list(n.get("assumptions"))
                    or _as_list(n.get("conclusions")))

    def _proof_indicator(n):
        """Compact 'X proofs, Y steps' label for the box; full prose
        stays in the side-panel Proof Strategy section."""
        n_steps = int(n.get("proof_step_count") or 0)
        n_proofs = len([p for p in (n.get("proof_info") or []) if p])
        if n_proofs == 0 and n_steps == 0:
            return ""
        parts = []
        if n_proofs > 0:
            parts.append(f"{n_proofs} proof{'s' if n_proofs != 1 else ''}")
        if n_steps > 0:
            parts.append(f"{n_steps} step{'s' if n_steps != 1 else ''}")
        return ", ".join(parts)

    def _content_lines(n):
        """Get all content text lines for a node (for width estimation).

        Uses the same _prepare_for_display pipeline as the drawing code so
        width estimates are consistent with what gets rendered.
        """
        ntype = n.get("type", "")
        lines = []
        name = n.get("name") or ""
        lines.append(f"{n['id']}: {name}" if name else n['id'])
        if ntype in _THEOREM_LIKE and _theorem_has_inline_content(n):
            for a in _as_list(n.get("assumptions"))[:MAX_LINES_PER_SECTION]:
                lines.append(_shorten(_prepare_for_display(a), 60))
            for c in _as_list(n.get("conclusions"))[:MAX_LINES_PER_SECTION]:
                lines.append(_shorten(_prepare_for_display(c), 60))
            _pl = _proof_indicator(n)
            if _pl: lines.append(_pl)
        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            for x in _as_list(n.get("input")): lines.append(_shorten(x, 60))
            for x in _as_list(n.get("output")): lines.append(_shorten(x, 60))
        else:
            raw = _as_text(n.get("statement")) or _as_text(n.get("proof_strategy"))
            lines.append(_shorten(_prepare_for_display(raw), 150))
            if ntype in _THEOREM_LIKE:
                _pl = _proof_indicator(n)
                if _pl: lines.append(_pl)
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
        if ntype in _THEOREM_LIKE and _theorem_has_inline_content(n):
            for a in _as_list(n.get("assumptions"))[:MAX_LINES_PER_SECTION]:
                texts.append(_shorten(_prepare_for_display(a), 60))
            for c in _as_list(n.get("conclusions"))[:MAX_LINES_PER_SECTION]:
                texts.append(_shorten(_prepare_for_display(c), 60))
            _pl = _proof_indicator(n)
            if _pl:
                texts.append(_pl)
        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            for x in _as_list(n.get("input")):
                texts.append(_shorten(x, 100))
            for x in _as_list(n.get("output")):
                texts.append(_shorten(x, 100))
        else:
            raw = _as_text(n.get("statement")) or _as_text(n.get("proof_strategy"))
            texts.append(_prepare_for_display(raw))
            if ntype in _THEOREM_LIKE:
                _pl = _proof_indicator(n)
                if _pl:
                    texts.append(_pl)
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
            text, _ = _header_text_for_box(nid, name, w)
            return len(text) / HEADER_CPU + 2 * PADDING + 0.15

        # --- Step 1: find body width via binary search ---
        # Initial header estimate (30-char cap, before circular expansion)
        name_cap = min(len(name), 30)
        init_header_w = (len(nid) + 2 + name_cap) / HEADER_CPU + 2 * PADDING + 0.15

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

        # Floor theorem-branch width so each shortened item fits unwrapped
        # (binary search above measures wrapped sub-lines, not item length).
        if ntype in _THEOREM_LIKE and _theorem_has_inline_content(n):
            longest_item = max((_display_width(t) for t in texts), default=0)
            body_w = max(body_w, _needed_w(longest_item))

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

            if ntype in _THEOREM_LIKE and _theorem_has_inline_content(n):
                assumptions = _as_list(n.get("assumptions"))
                conclusions = _as_list(n.get("conclusions"))

                # Shorten each item to one wrapped line; cap section items.
                assume_lines = []
                for a in assumptions[:MAX_LINES_PER_SECTION]:
                    short = _shorten(_prepare_for_display(a), 60)
                    assume_lines.extend(_wrap(short, wrap_w) or [short[:wrap_w]])
                if len(assumptions) > MAX_LINES_PER_SECTION:
                    assume_lines.append(f"... +{len(assumptions)-MAX_LINES_PER_SECTION} more")
                conclude_lines = []
                for c in conclusions[:MAX_LINES_PER_SECTION]:
                    short = _shorten(_prepare_for_display(c), 60)
                    conclude_lines.extend(_wrap(short, wrap_w) or [short[:wrap_w]])
                if len(conclusions) > MAX_LINES_PER_SECTION:
                    conclude_lines.append(f"... +{len(conclusions)-MAX_LINES_PER_SECTION} more")
                _proof_label = _proof_indicator(n)

                assume_heights = sum(_line_h(l) for l in assume_lines) or LINE_H
                conclude_heights = sum(_line_h(l) for l in conclude_lines) or LINE_H
                n_proof = 1 if _proof_label else 0

                h = HEADER_H + PADDING
                h += assume_heights + PADDING
                h += conclude_heights + PADDING
                if n_proof > 0:
                    h += n_proof * LINE_H + PADDING
                h += PADDING
            elif ntype == "algorithm" and (n.get("input") or n.get("output")):
                in_lines = [_shorten(x, 100) for x in (_as_list(n.get("input")) or ["(none)"])]
                out_lines = [_shorten(x, 100) for x in (_as_list(n.get("output")) or ["(none)"])]
                h = HEADER_H + PADDING
                h += len(in_lines) * LINE_H + PADDING
                h += len(out_lines) * LINE_H + PADDING
                h += PADDING
            else:
                # Use statement, or name as fallback (e.g., proofs with descriptive names)
                raw = _as_text(n.get("statement")) or _as_text(n.get("proof_strategy"))
                stmt = _prepare_for_display(raw)
                stmt_lines = _wrap(stmt, wrap_w)[:5]
                stmt_height = sum(_line_h(l) for l in stmt_lines) if stmt_lines else LINE_H
                h = HEADER_H + stmt_height + 2 * PADDING
                if ntype in _THEOREM_LIKE and _proof_indicator(n):
                    h += LINE_H + PADDING  # proof indicator line

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
    _held_ids = {id(e) for e in _cycle_edges}
    for e in edges + _cycle_edges:
        src, tgt = e["source"], e["target"]
        if src not in node_rect or tgt not in node_rect:
            continue
        sx, sy_bottom, sw, sh = node_rect[src]
        tx, ty_bottom, tw, th = node_rect[tgt]

        x0 = sx + sw / 2
        y0 = sy_bottom  # bottom of source
        x1 = tx + tw / 2
        y1 = ty_bottom + th  # top of target
        if id(e) in _held_ids and sy_bottom < ty_bottom:
            # Held-out edge whose source was laid out BELOW its target: run
            # from the source's top to the target's bottom, not through both.
            y0, y1 = sy_bottom + sh, ty_bottom

        # Port #7: `resolves` edges (v2 schema) — dashed line and distinct color.
        _etype = (e.get("type") or e.get("relation") or "").lower()
        _is_resolves = (_etype == "resolves")
        # Low-confidence edges (e.g. term_reuse, confidence 0.3) are drawn faded
        # so the high-confidence skeleton (proves/ref/structural) stands out.
        _conf = e.get("confidence", 1.0)
        try:
            _conf = float(_conf)
        except (TypeError, ValueError):
            _conf = 1.0
        _low_conf = _conf < LOW_CONF_THRESHOLD
        _arrow_kwargs = dict(
            arrowstyle="-|>,head_length=1.2,head_width=0.6",
            color=("#C0C0C0" if _low_conf else edge_type_color(_etype)),
            lw=1.0 if _low_conf else 2.5,
            alpha=0.4 if _low_conf else 1.0,
            connectionstyle="arc3,rad=0.08" if abs(x0 - x1) > 0.5 else "arc3,rad=0",
            shrinkA=3, shrinkB=3,
        )
        if e.get("mention"):
            # A reference, not a dependency: thin, light, short dashes.
            _arrow_kwargs.update(color="#9FA8DA", lw=1.0, alpha=0.8,
                                 linestyle=(0, (2, 2)),
                                 connectionstyle="arc3,rad=0.15")
        elif id(e) in _held_ids:
            # Backward / cycle-breaking edge: dash-dot (resolves already owns
            # plain dashes, low confidence owns dots), and bowed so an arrow
            # running back up the layers does not hide under forward ones.
            _arrow_kwargs["linestyle"] = (0, (6, 2, 1, 2))
            _arrow_kwargs["connectionstyle"] = "arc3,rad=0.25"
        elif _is_resolves:
            _arrow_kwargs["linestyle"] = "--"
        elif _low_conf:
            _arrow_kwargs["linestyle"] = (0, (1, 2))  # dotted
        ann = ax.annotate(
            "", xy=(x1, y1), xytext=(x0, y0),
            arrowprops=_arrow_kwargs,
        )
        # Tag the edge so JS toggles can hide/show it. Use a sanitized id.
        try:
            _safe_src = str(src).replace(" ", "_")
            _safe_tgt = str(tgt).replace(" ", "_")
            ann.arrow_patch.set_gid(f"edge_{_safe_src}__to__{_safe_tgt}")
        except Exception:
            pass

    # ── Draw boxes ──
    # Track which patches/texts/lines belong to each node so we can bulk-tag
    # them with a `node_<nid>__elemN` gid suffix after rendering. This lets
    # the HTML toggle code hide every element of a node via attribute selector.
    def _safe_nid(nid):
        return str(nid).replace(" ", "_")

    for nid, (bx, by, bw, bh) in node_rect.items():
        n = node_data[nid]
        ntype = n.get("type", "")
        colors = NODE_COLORS.get(ntype, DEFAULT_COLOR)

        # Snapshot artist counts so we can later identify per-node artists
        _patches_start = len(ax.patches)
        _texts_start = len(ax.texts)
        _lines_start = len(ax.lines)

        # Main box background (gid for SVG click handling)
        # Cited prior results (origin="external") are drawn dashed and paler.
        # They are hidden by default and appear via the "Cited Results" toggle,
        # at which point they were indistinguishable from the paper's own
        # contributions — the one distinction a reader most needs, since it is
        # what separates "this paper proved it" from "this paper invokes it".
        _is_external = (n.get("origin", "paper") == "external")
        rect = FancyBboxPatch(
            (bx, by), bw, bh,
            boxstyle="round,pad=0.05",
            facecolor=colors["body"],
            edgecolor=colors["header"],
            linewidth=2.0 if _is_external else 1.5,
            linestyle=(0, (6, 3)) if _is_external else "solid",
            alpha=0.9 if _is_external else 1.0,
            gid=f"node_{nid}",
        )
        ax.add_patch(rect)

        cursor_y = by + bh  # start from top

        # Header — truncate name to box width, but always show full node ID
        # Use ~9 chars/unit for bold header font (vs 12 for body font)
        name_str = n.get("name") or ""
        header_text, header_chars = _header_text_for_box(
            nid, name_str, node_width.get(nid, 4.0))
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
        # Proof indicator — small yellow badge in the top-right corner of the
        # header for theorem-like nodes that have proof_info merged in.
        _has_proof = (ntype in ("theorem", "lemma", "corollary", "proposition", "claim")
                      and bool(n.get("proof_info")))
        if _has_proof:
            from matplotlib.patches import Circle
            # 0.18 made the badge 0.13in across on a 74in-wide figure —
            # sub-pixel at fit-to-window zoom, which reads as 'no badge'.
            _badge_r = HEADER_H * 0.30
            _badge_cx = bx + bw - _badge_r * 1.6
            _badge_cy = cursor_y - HEADER_H / 2
            _safe_nid_for_badge = str(nid).replace(" ", "_")
            badge = Circle((_badge_cx, _badge_cy), _badge_r,
                           facecolor="#FFD54F", edgecolor="#5D4037",
                           linewidth=0.8, zorder=5,
                           gid=f"node_{_safe_nid_for_badge}__proofbadge")
            ax.add_patch(badge)
            # zorder above the circle: text defaults to 3, the badge patch is
            # 5, so the asterisk was being painted BEHIND its own badge.
            ax.text(_badge_cx, _badge_cy, "*",
                    ha="center", va="center", fontsize=max(9, header_fontsize * 0.85),
                    fontweight="bold", color="#5D4037", zorder=6,
                    gid=f"node_{_safe_nid_for_badge}__proofbadgetext")
        cursor_y -= HEADER_H + PADDING

        # Line height helper — must match height computation exactly
        def _line_h_draw(line):
            if _has_tall_math(line):
                return LINE_H * 2.5
            elif "$" in line:
                return LINE_H * 1.5
            return LINE_H

        if ntype in _THEOREM_LIKE and _theorem_has_inline_content(n):
            # Wrap text to box width (same logic as height computation)
            dyn_wrap = max(20, int(node_width.get(nid, 4.0) * CHARS_PER_UNIT) - 4)
            assumptions = _as_list(n.get("assumptions"))
            a_lines = []
            for a in assumptions[:MAX_LINES_PER_SECTION]:
                short = _shorten(_prepare_for_display(a), 60)
                a_lines.extend(_wrap(short, dyn_wrap) or [short[:dyn_wrap]])
            if len(assumptions) > MAX_LINES_PER_SECTION:
                a_lines.append(f"... +{len(assumptions)-MAX_LINES_PER_SECTION} more")
            if not a_lines:
                a_lines = ["(none)"]

            conclusions = _as_list(n.get("conclusions"))
            c_lines = []
            for c in conclusions[:MAX_LINES_PER_SECTION]:
                short = _shorten(_prepare_for_display(c), 60)
                c_lines.extend(_wrap(short, dyn_wrap) or [short[:dyn_wrap]])
            if len(conclusions) > MAX_LINES_PER_SECTION:
                c_lines.append(f"... +{len(conclusions)-MAX_LINES_PER_SECTION} more")
            if not c_lines:
                c_lines = ["(none)"]

            # Assumptions
            _lod_body(ax.text(bx + PADDING, cursor_y, "Assume:",
                    ha="left", va="top", fontsize=13, fontweight="bold", color="#333"))
            cursor_y -= LINE_H * 0.7
            for line in a_lines:
                _lod_body(ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top",
                        fontsize=_fit_fontsize(f"• {line}", bw - 2 * PADDING - 0.1),
                        color="#222",
                        fontstyle="italic"))
                cursor_y -= _line_h_draw(line)

            cursor_y -= PADDING * 0.3

            # Divider line
            ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                    color=colors["header"], lw=0.5, alpha=0.4)

            # Conclusions
            _lod_body(ax.text(bx + PADDING, cursor_y, "Conclude:",
                    ha="left", va="top", fontsize=13, fontweight="bold", color="#333"))
            cursor_y -= LINE_H * 0.7
            for line in c_lines:
                _lod_body(ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top",
                        fontsize=_fit_fontsize(f"• {line}", bw - 2 * PADDING - 0.1),
                        color="#222"))
                cursor_y -= _line_h_draw(line)

            _proof_label = _proof_indicator(n)
            if _proof_label:
                cursor_y -= PADDING * 0.2
                ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.1] * 2,
                        color="#999", lw=0.5, alpha=0.4)
                ax.text(bx + PADDING, cursor_y, _proof_label,
                        ha="left", va="top", fontsize=10.5,
                        color="#444", fontstyle="italic")
                cursor_y -= LINE_H

        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            # Algorithm with input/output
            dyn_wrap = max(20, int(node_width.get(nid, 4.0) * CHARS_PER_UNIT) - 4)
            in_lines = [_shorten(x, dyn_wrap) for x in (_as_list(n.get("input")) or ["(none)"])]
            out_lines = [_shorten(x, 70) for x in (_as_list(n.get("output")) or ["(none)"])]

            _lod_body(ax.text(bx + PADDING, cursor_y, "Input:",
                    ha="left", va="top", fontsize=13, fontweight="bold", color="#333"))
            cursor_y -= LINE_H * 0.7
            for line in in_lines:
                _lod_body(ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top",
                        fontsize=_fit_fontsize(f"• {line}", bw - 2 * PADDING - 0.1),
                        color="#222"))
                cursor_y -= LINE_H
            cursor_y -= PADDING * 0.3
            ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                    color=colors["header"], lw=0.5, alpha=0.4)
            _lod_body(ax.text(bx + PADDING, cursor_y, "Output:",
                    ha="left", va="top", fontsize=13, fontweight="bold", color="#333"))
            cursor_y -= LINE_H * 0.7
            for line in out_lines:
                _lod_body(ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top",
                        fontsize=_fit_fontsize(f"• {line}", bw - 2 * PADDING - 0.1),
                        color="#222"))
                cursor_y -= LINE_H

        else:
            # Simple box: wrap statement/name text to box width (up to 5 lines)
            dyn_wrap = max(20, int(node_width.get(nid, 4.0) * CHARS_PER_UNIT) - 4)
            raw = _as_text(n.get("statement")) or _as_text(n.get("proof_strategy"))
            stmt = _prepare_for_display(raw)
            stmt_lines = _wrap(stmt, dyn_wrap)[:5]
            if not stmt_lines:
                stmt_lines = [""]
            for line in stmt_lines:
                _lod_body(ax.text(bx + PADDING, cursor_y, line,
                        ha="left", va="top",
                        fontsize=_fit_fontsize(line, bw - 2 * PADDING),
                        color="#222"))
                cursor_y -= _line_h_draw(line)
            if ntype in _THEOREM_LIKE:
                _proof_label = _proof_indicator(n)
                if _proof_label:
                    cursor_y -= PADDING * 0.2
                    ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.1] * 2,
                            color="#999", lw=0.5, alpha=0.4)
                    ax.text(bx + PADDING, cursor_y, _proof_label,
                            ha="left", va="top", fontsize=10.5,
                            color="#444", fontstyle="italic")
                    cursor_y -= LINE_H

        # Bulk-tag this node's artists with a per-node gid so the HTML JS
        # can hide/show every element of the node via attribute selector.
        _safe = _safe_nid(nid)
        # Skip the body rect (index _patches_start) — it already has gid="node_<nid>"
        for i, p in enumerate(ax.patches[_patches_start + 1:len(ax.patches)]):
            if p.get_gid() is None:
                p.set_gid(f"node_{_safe}__patch{i}")
        for i, t in enumerate(ax.texts[_texts_start:len(ax.texts)]):
            if t.get_gid() is None:
                t.set_gid(f"node_{_safe}__text{i}")
            elif t.get_gid().startswith("lodbody_"):
                # Body lines must carry the node prefix too, or hiding the node
                # (external, nested, aux, backbone toggles) leaves its text floating.
                t.set_gid(f"node_{_safe}__{t.get_gid()}")
        for i, ln in enumerate(ax.lines[_lines_start:len(ax.lines)]):
            if ln.get_gid() is None:
                ln.set_gid(f"node_{_safe}__line{i}")

    # ── Containment links ──
    # A drawn node that lives inside another (v6: a claim stated inside a proof
    # step, a lemma inside a proof; full resolution: a step inside its proof)
    # is tied to the box it lives in by a grey dotted line with no arrowhead —
    # containment, not a dependency. Drawn under the boxes, centre to centre,
    # so only the gap between them shows. Tagged as part of the CHILD, so the
    # HTML toggles hide it together with the child.
    _host = _host_resolver({n["id"]: n for n in nodes_raw}, proof_map,
                           set(node_rect))
    for nid in node_rect:
        _par = _parent_ref(node_data[nid])
        _cont = _host(_par) if _par else None
        if not _cont or _cont == nid:
            continue
        (cx, cy, cw, ch_), (bx, by, bw, bh) = node_rect[_cont], node_rect[nid]
        ax.plot([cx + cw / 2, bx + bw / 2], [cy + ch_ / 2, by + bh / 2],
                color="#7F8C8D", lw=2.0, linestyle=(0, (1, 1.5)), alpha=0.9,
                zorder=0.5, gid=f"node_{_safe_nid(nid)}__nestlink")

    # ── Ghost nodes (external foundation dependencies) ──
    _base_ids = set(node_data.keys())
    _ghost_map, _case1_matches, _ghost_meta = compute_foundation_links(
        nodes_raw, _base_ids, foundation_path=foundation_path)

    if show_foundation and _ghost_map:
        draw_foundation_ghosts(ax, _ghost_map, node_rect, ghost_meta=_ghost_meta)

    # ── Misc/Orphan equations box ──
    # Count orphan equations from the FULL node list (before filtering), with
    # the classification that builds the HTML orphan list this box opens (on
    # copies: it annotates the nodes). It used to count every equation without
    # a `context` field — which no current schema writes — so the box said
    # "Misc (48 equations)" and then listed 20.
    n_orphan = sum(1 for n in _classify_and_merge([dict(n) for n in nodes_raw],
                                                  edges_raw)[4]
                   if n["id"] not in node_data)

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
    if show_title:
        # Cap the scale. _font_scale grows with sqrt(figure AREA), which on a
        # 116x46in paper reaches 5.3 — a 127pt title with 105pt of padding,
        # about 3.2 inches stacked above the axes, far more than the margin
        # reserved below it, so the glyphs were sliced off at the top edge.
        _title_scale = min(_font_scale, 1.5)
        ax.set_title(title, fontsize=24 * _title_scale, fontweight="bold",
                     pad=20 * _title_scale)

    ax.autoscale()
    ax.margins(0.05)
    # Re-fit figsize to the actual post-autoscale data aspect so the
    # foundation-ghost row can't squash the axes horizontally.
    _xlim = ax.get_xlim(); _ylim = ax.get_ylim()
    _x_rng = max(_xlim) - min(_xlim)
    _y_rng = max(_ylim) - min(_ylim)
    if _x_rng > 0 and _y_rng > 0:
        # Size STRICTLY proportionally, and buy the margin in data units.
        #
        # This used to be `_x_rng * 0.8 + 2`. That `+ 2` is a fixed number of
        # INCHES, so inches-per-data-unit came out as 0.768 + 1.92/_x_rng —
        # 0.96 on a 10-unit graph but 0.785 on a 115-unit one. Text is wrapped
        # in data units against CHARS_PER_UNIT, a single constant, so the
        # wrapping could only be right at one graph size: small papers fitted
        # and large ones spilled ~27% past the box edge, which is exactly the
        # reported overflow. Adding the margin to the LIMITS instead keeps
        # inches-per-unit pinned at IN_PER_UNIT for every paper.
        _pad_u = MARGIN_IN / IN_PER_UNIT / 2.0          # per side
        ax.set_xlim(min(_xlim) - _pad_u, max(_xlim) + _pad_u)
        ax.set_ylim(min(_ylim) - _pad_u, max(_ylim) + _pad_u)
        _xs, _ys = _x_rng + 2 * _pad_u, _y_rng + 2 * _pad_u
        fig.set_size_inches(_xs * IN_PER_UNIT / AXES_FRAC,
                            _ys * IN_PER_UNIT / AXES_FRAC)
    ax.set_position([(1 - AXES_FRAC) / 2, (1 - AXES_FRAC) / 2,
                     AXES_FRAC, AXES_FRAC])
    # The PNG raster is an Agg pixel buffer of ~(fw*dpi)x(fh*dpi)x4 bytes, which
    # blows up (time + memory) on large figures. Callers that only need the SVG
    # (interactive HTML) pass write_png=False to skip it entirely.
    if write_png:
        # Bound the raster, NOT the layout. Figure size is computed in inches
        # from content and can reach 200+ inches on a large paper; at a fixed
        # dpi=200 that is a 700-megapixel, multi-GB Agg buffer (and
        # bbox_inches="tight" renders it twice). Lowering dpi changes only
        # pixel density: composition, proportions and text wrapping are all
        # computed in inches/points, so the picture is identical — verified by
        # downscaling a dpi=200 render to the dpi=50 size (mean pixel
        # difference 3.9/255, all of it antialiasing). SVG is unaffected: it is
        # vector and takes no dpi.
        _w_in, _h_in = fig.get_size_inches()
        _dpi = PNG_DPI
        _px = (_w_in * _dpi) * (_h_in * _dpi)
        if _px > MAX_RASTER_PX:
            _dpi = max(MIN_PNG_DPI, int(_dpi * (MAX_RASTER_PX / _px) ** 0.5))
        plt.savefig(str(out_path), dpi=_dpi, bbox_inches="tight", facecolor="white")

    # Also save SVG if requested (for interactive HTML).
    # No bbox_inches="tight": for wide-aspect figures it shrinks the saved
    # SVG ~3x relative to figsize, squashing per-box pixel budget.
    svg_path = str(out_path).replace('.png', '.svg') if str(out_path).endswith('.png') else None
    if svg_path:
        plt.savefig(svg_path, format='svg', facecolor="white")

    plt.close(fig)

    return len(nodes), len(edges), node_rect, node_data


def _classify_and_merge(nodes, edges):
    """Merge proofs into parent theorems. Separate equations/proof_steps.
    v2: also fold algorithm_step nodes into their parent algorithm."""
    node_by_id = {n["id"]: n for n in nodes}

    proof_map = {}
    for n in nodes:
        if n.get("type") != "proof" and n["id"] in node_by_id:
            node_by_id[n["id"]]["proof_info"] = []
    for n in nodes:
        _pv = n.get("proves")
        if isinstance(_pv, (list, tuple)):        # one paper writes ["TP1.2"]
            _pv = _pv[0] if _pv else None
        if n.get("type") == "proof" and _pv and _pv in node_by_id:
            proof_map[n["id"]] = _pv
            parent = node_by_id[_pv]
            parent.setdefault("proof_info", [])
            # LLM extraction writes the proof body to `proof_strategy`; the
            # rules parser writes it to `statement`/`clean_text`. Accept any
            # non-empty form so the `*` badge + side-panel work for both.
            body = (_as_text(n.get("proof_strategy")) or _as_text(n.get("clean_text"))
                    or _as_text(n.get("statement"))).strip()
            if body:
                parent["proof_info"].append(body)
            # The proof node itself, for the side panel: since v5.1
            # proof_strategy is a list of labels, and statement_short / rigor /
            # confidence say more than the joined labels in proof_info.
            parent.setdefault("proofs", []).append({
                "id": n["id"], "name": n.get("name", ""),
                "proof_strategy": _as_list(n.get("proof_strategy")),
                "statement_short": n.get("statement_short", ""),
                "rigor": n.get("rigor", ""),
                "confidence": n.get("confidence")})

    base_nodes, proof_steps, algorithm_steps, equations, orphan_eqs = [], [], [], [], []
    has_edge = set()
    for e in edges:
        has_edge.add(e["source"])
        has_edge.add(e["target"])

    for n in nodes:
        if n["id"] in proof_map:
            continue
        if n["type"] == "proof_step":
            proof_steps.append(n)
        elif n["type"] == "algorithm_step":
            algorithm_steps.append(n)
        elif n["type"] == "equation":
            if n["id"] in has_edge or _parent_ref(n):
                equations.append(n)
            else:
                orphan_eqs.append(n)
        else:
            base_nodes.append(n)

    base_ids = {n["id"] for n in base_nodes}
    host = _host_resolver(node_by_id, proof_map, base_ids)

    # Edges that pointed at a proof are rewritten to the result it proves, and
    # edges at an algorithm_step to the algorithm box holding it (at any
    # nesting depth). Edges at proof steps and equations are not drawn.
    def _redirect(nid):
        nid = proof_map.get(nid, nid)
        if node_by_id.get(nid, {}).get("type") == "algorithm_step":
            nid = host(nid) or nid
        return nid

    base_edges = []
    seen = {}
    for e in edges:
        s = _redirect(e["source"])
        t = _redirect(e["target"])
        if s == t or s not in base_ids or t not in base_ids:
            continue
        key = (s, t)
        if key not in seen:
            seen[key] = {"source": s, "target": t,
                         "type": e.get("type", "uses"),
                         "backward": bool(e.get("backward")),
                         "mention": bool(e.get("mention")),
                         "confidence": e.get("confidence", 1.0)}
            base_edges.append(seen[key])
        else:
            # Backward (or a mention) only if every edge merged into (s, t) is.
            seen[key]["backward"] &= bool(e.get("backward"))
            seen[key]["mention"] &= bool(e.get("mention"))

    # Steps go to the box that contains them, through any number of
    # step-in-step / proof-in-step levels, and are listed as a TREE: each step
    # is followed by the steps nested in it, with its nesting depth.
    _step_ids = {s["id"] for s in proof_steps + algorithm_steps}
    _kids = defaultdict(list)
    for s in proof_steps + algorithm_steps:
        _kids[_parent_ref(s)].append(s)
    _by_order = lambda s: (s.get("step_order") or 0, _natural_key(s.get("id")))
    step_chains = {}

    def _walk(container, depth, hid):
        for s in sorted(_kids.get(container, []), key=_by_order):
            step_chains.setdefault(hid, []).append(
                dict(s, depth=depth,
                     parent_step=_parent_ref(s) if _parent_ref(s) in _step_ids else ""))
            _walk(s["id"], depth + 1, hid)

    for container in sorted((c for c in _kids if c not in _step_ids), key=_natural_key):
        hid = host(container)
        if hid:
            _walk(container, 0, hid)
    _has_real_steps = {c for c in _kids if c not in _step_ids}

    # Synthesize pseudo proof-steps for rules-mode JSONs: those have a single
    # `proof` node carrying the whole body in `statement`/`clean_text`, with
    # no `proof_step` children. Split on the proof's own Part-markers (or
    # paragraph breaks as a fallback) so the side panel can show a
    # Decomposition section like for LLM outputs. All proofs of the same
    # theorem are appended, with the proof id stored in `subclass` so the
    # reader can tell which proof a step came from.
    # Count how many distinct proofs target each theorem (so we know whether
    # to tag steps with their parent proof id).
    proof_count_for_thm = {}
    for n in nodes:
        if n.get("type") == "proof" and n.get("proves") in base_ids:
            proof_count_for_thm[n["proves"]] = proof_count_for_thm.get(n["proves"], 0) + 1
    seen_proofs = set()
    for n in nodes:
        if n.get("type") != "proof" or not n.get("proves"):
            continue
        if n["id"] in seen_proofs:
            continue
        seen_proofs.add(n["id"])
        thm_id = n["proves"]
        if thm_id not in base_ids or n["id"] in _has_real_steps:
            continue        # only for proofs WITHOUT extracted steps (rules mode)
        # Prefer raw_latex (consistent LaTeX) so we can reliably detect math
        # environments before splitting; fall back to clean_text / statement.
        body = (_as_text(n.get("raw_latex")) or _as_text(n.get("clean_text"))
                or _as_text(n.get("statement"))).strip()
        if not body:
            continue
        pieces = _split_proof_into_steps(body)
        if not pieces:
            continue
        proof_id = n["id"]
        existing = len(step_chains.get(thm_id, []))
        # Only tag the proof id when the theorem has more than one proof.
        proof_tag = proof_id if proof_count_for_thm.get(thm_id, 0) > 1 else ""
        for i, (label, body_piece) in enumerate(pieces):
            step_chains.setdefault(thm_id, []).append({
                "id":              f"{proof_id}_s{i+1}",
                "statement":       body_piece,
                "statement_clean": body_piece,
                "name":            label,
                "subclass":        proof_tag,
                "step_order":      existing + i + 1,
                "type":            "proof_step",
                "parent_proof":    proof_id,
            })

    # Drawn nodes that live inside another drawn node (v6: a claim stated in a
    # proof step, a lemma inside a proof). Stashed on the nodes like
    # proof_info, so the side panel can show "inside X" / "contains Y".
    for n in base_nodes:
        n["contains"] = []
    for n in base_nodes:
        _par = _parent_ref(n)
        _cont = host(_par) if _par else None
        n["inside"] = _cont if _cont and _cont != n["id"] else ""
        if n["inside"]:
            node_by_id[n["inside"]]["contains"].append(
                {"id": n["id"], "name": n.get("name", ""), "type": n.get("type", ""),
                 "parent": _par})

    # Equations with a parent (v6) go to the box that contains them, placed
    # under the step / proof / statement they sit in. Those without one are
    # attached to every drawn node they share an edge with — or, when the
    # edge is to a step or proof, to the box containing it (under that step).
    # One with neither is an orphan; before, an equation linked only to steps
    # was in no list at all.
    eq_map = {}
    for eq in equations:
        _par = _parent_ref(eq)
        if _par:
            hid = host(eq["id"])
            if not hid:
                orphan_eqs.append(eq)
                continue
            _ptype = node_by_id.get(_par, {}).get("type")
            eq_map.setdefault(hid, []).append(dict(
                eq,
                parent_step=_par if _par in _step_ids else "",
                context=("statement" if _par == hid else
                         "proof" if _ptype == "proof" else
                         "" if _par in _step_ids else eq.get("context", ""))))
            continue
        _at = {}                      # host -> step it was reached through
        for e in edges:
            for a, b in ((e["source"], e["target"]), (e["target"], e["source"])):
                hid = host(b) if a == eq["id"] else None
                if hid and (hid not in _at or not _at[hid]):
                    _at[hid] = b if b in _step_ids else ""
        for hid, step in _at.items():
            eq_map.setdefault(hid, []).append(dict(eq, parent_step=step) if step else eq)
        if not _at:
            orphan_eqs.append(eq)

    return base_nodes, base_edges, step_chains, eq_map, orphan_eqs



# Edge types compose along a path, and a type-blind transitive reduction is
# therefore wrong. Following the rule Tao's format states — "generalization o
# generalization stays a generalization; any dependence in the path dominates" —
# a path is a `generalizes` relation only if EVERY edge on it is `generalizes`;
# mix in one plain `uses` and the whole path is only a `uses`.
#
# Two consequences the previous version got wrong:
#   * a `generalizes` edge whose only alternative path mixes in a plain `uses`
#     is NOT implied, and was being hidden anyway. (The converse does hold: an
#     all-`generalizes` path DOES imply a `uses` edge, because edge_types.py
#     declares generalizes/specializes to be subtypes of uses.)
#   * `proves` / `illustrates` / `resolves` / `tests` are not
#     transitive at all — a proof of a proof is not a proof of the conclusion —
#     so they can never be implied, and were being hidden by any parallel path.
_DEPENDENCY_EDGE_TYPES = ("uses", "generalizes", "specializes")


def _implied_edges(base_nodes, base_edges, safe_eid):
    """Gids of edges reachable by a longer path OF THE SAME COMPOSED TYPE."""
    try:
        import networkx as _nx
    except Exception:
        return []
    ids = {n["id"] for n in base_nodes}

    def _typed(pred):
        g = _nx.DiGraph()
        g.add_nodes_from(ids)
        for e in base_edges:
            a, b = e.get("source"), e.get("target")
            if a in ids and b in ids and a != b and pred(str(e.get("type") or "uses")):
                g.add_edge(a, b)
        return g

    # `uses` is implied by ANY dependency path; the subtypes only by a path made
    # entirely of themselves.
    graphs = {
        "uses": _typed(lambda t: t in _DEPENDENCY_EDGE_TYPES),
        "generalizes": _typed(lambda t: t == "generalizes"),
        "specializes": _typed(lambda t: t == "specializes"),
    }
    out = []
    for e in base_edges:
        a, b = e.get("source"), e.get("target")
        t = str(e.get("type") or "uses")
        g = graphs.get(t)
        if g is None or a not in ids or b not in ids or a == b:
            continue            # non-transitive type, or dangling: never implied
        if not g.has_edge(a, b):
            continue
        g.remove_edge(a, b)     # is it still reachable WITHOUT this edge?
        try:
            redundant = _nx.has_path(g, a, b)
        except Exception:
            redundant = False
        g.add_edge(a, b)
        if redundant:
            out.append("edge_%s__to__%s" % (safe_eid(a), safe_eid(b)))
    return sorted(set(out))


def generate_interactive_html(data, svg_path, html_path):
    """Wrap an SVG figure in an interactive HTML page with click-to-expand detail panel."""
    import json as _json
    from html import escape as _esc

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    metadata = data.get("metadata", {})

    base_nodes, base_edges, step_chains, eq_map, orphan_eqs = _classify_and_merge(nodes, edges)

    # Port #4: classify nodes for the 3-toggle panel.
    AUX_TYPES = {"example", "remark"}
    aux_node_ids = sorted({n["id"] for n in base_nodes if n.get("type") in AUX_TYPES})
    ext_node_ids = sorted({n["id"] for n in base_nodes if n.get("origin", "paper") == "external"})

    # Bug 1 fix: build node_id → [edge gids touching this node]. Edge gids in
    # the SVG are tagged as f"edge_<safe_src>__to__<safe_tgt>" by draw_dag.
    # When the JS toggle hides a node, it iterates this map and also hides
    # every incident edge so we don't leave dangling arrows.
    def _safe_eid(s):
        return str(s).replace(" ", "_")
    node_to_edges = {}
    low_conf_edge_gids = []
    for e in base_edges:
        s, t = e["source"], e["target"]
        gid = f"edge_{_safe_eid(s)}__to__{_safe_eid(t)}"
        node_to_edges.setdefault(s, []).append(gid)
        node_to_edges.setdefault(t, []).append(gid)
        try:
            if float(e.get("confidence", 1.0) or 1.0) < LOW_CONF_THRESHOLD:
                low_conf_edge_gids.append(gid)
        except (TypeError, ValueError):
            pass
    low_conf_edge_gids = sorted(set(low_conf_edge_gids))

    # ── Density reduction ────────────────────────────────────────────────
    # Half the corpus (108/200 papers) exceeds 100 nodes, and the graphs are
    # genuinely hard to read at that size. Three reductions were measured over
    # all 200 papers; two of them pay, and they are exposed as toggles rather
    # than applied unconditionally so nothing is silently hidden.
    #
    #   implied edges (transitive reduction)  -24.5% of edges
    #   backbone (definitions + theorem-like)  keeps 36.7% of nodes
    #
    # Splitting by connected component — the obvious third idea — does NOT pay:
    # the median paper has ONE component, and the largest component holds 100%
    # of the nodes at both the median and the 90th percentile.
    # Backward edges (v6 `backward: true`, plus whatever else must be held out
    # to break a cycle — the same split draw_dag makes): drawn dash-dotted,
    # toggleable, and kept out of the transitive reduction, where an edge
    # running against the layering would make forward edges look "implied".
    _forward, _held = split_cycle_edges(
        base_nodes, [e for e in base_edges if not (e.get("backward") or e.get("mention"))])
    _held = [e for e in base_edges if e.get("backward") or e.get("mention")] + _held
    backward_edge_gids = sorted({f"edge_{_safe_eid(e['source'])}__to__{_safe_eid(e['target'])}"
                                 for e in _held if not e.get("mention")})
    mention_edge_gids = sorted({f"edge_{_safe_eid(e['source'])}__to__{_safe_eid(e['target'])}"
                                for e in base_edges if e.get("mention")})
    implied_edge_gids = _implied_edges(base_nodes, _forward, _safe_eid)
    nested_node_ids = sorted(n["id"] for n in base_nodes if n.get("inside"))

    _BACKBONE_TYPES = {"definition", "theorem", "lemma", "proposition",
                       "corollary", "claim", "conjecture"}
    nonbackbone_node_ids = sorted(n["id"] for n in base_nodes
                                  if n.get("type") not in _BACKBONE_TYPES)

    # Foundation graph linking (shared computation with draw_dag)
    base_ids = {n["id"] for n in base_nodes}
    case2_ghosts, case1_matches, ghost_meta = compute_foundation_links(nodes, base_ids)
    # Counts split: foundation ghost subsets (mathlib/proofwiki vs textbook)
    n_ghost_book = sum(1 for n, m in ghost_meta.items()
                       if n in case2_ghosts and m.get("is_book"))
    n_ghost_other = sum(1 for n, m in ghost_meta.items()
                        if n in case2_ghosts and not m.get("is_book"))
    n_ghost_total = n_ghost_book + n_ghost_other
    # Lists of ghost element id-prefixes per subset, so the JS toggles can
    # show/hide just the mathlib-or-herald vs book sub-set selectively.
    ghost_names_sorted = sorted(case2_ghosts.keys())
    ghost_book_indices = []
    ghost_other_indices = []
    for gi, gname in enumerate(ghost_names_sorted):
        meta = ghost_meta.get(gname, {}) or {}
        if meta.get("is_book"):
            ghost_book_indices.append(gi)
        else:
            ghost_other_indices.append(gi)

    # Build detail data
    js_details = {}
    # Map base_node id -> proof_info (from any proofs already merged in
    # _classify_and_merge). Also expose step_info (alias of `steps` for the
    # HEAD-style side-panel template).
    for n in base_nodes:
        nid = n["id"]
        _steps = [{"id": s["id"], "statement": s.get("statement",""),
                   "statement_clean": s.get("statement_clean",""),
                   "statement_short": s.get("statement_short",""),
                   "name": s.get("name",""), "subclass": s.get("subclass",""),
                   "step_order": s.get("step_order", 0),
                   "type": s.get("type",""),
                   # v6: nesting (step inside step) and per-step metadata
                   "depth": s.get("depth", 0), "parent_step": s.get("parent_step", ""),
                   "source_line_label": s.get("source_line_label", ""),
                   "rigor": s.get("rigor", ""), "confidence": s.get("confidence")}
                  for s in step_chains.get(nid, [])]
        js_details[nid] = {
            "name": n.get("name", ""),
            "type": n.get("type", ""),
            "section": n.get("section", ""),
            "statement": n.get("statement", ""),
            # TeX-faithful render source for the Statement panel. statement/
            # statement_clean are de-TeX'd for matching ($ and command backslashes
            # stripped) and won't MathJax-render, so prefer raw_latex when it
            # carries TeX. Computed here to avoid JS-regex-in-f-string escaping.
            "statement_render": _statement_render_source(n),
            # Port #4: plain-text summary (HEAD's "Plain-Text Summary" panel).
            "statement_clean": n.get("statement_clean", ""),
            # Short summary: `statement_short` (v5.1+); older files only had
            # statement_clean, which _normalize_schema fills from statement.
            "statement_short": n.get("statement_short", ""),
            "rigor": n.get("rigor", ""),
            "confidence": n.get("confidence"),
            "tags": _as_list(n.get("tags")),
            "inside": n.get("inside", ""),
            "contains": n.get("contains", []),
            "proofs": n.get("proofs", []),
            # Port #1/#2: external-cited badge in side panel.
            "origin": n.get("origin", "paper"),
            "origin_citation": n.get("origin_citation", ""),
            "assumptions": n.get("assumptions", []),
            "conclusions": n.get("conclusions", []),
            # a definition's structure (genus + differentia), shown as its reading
            "genus": n.get("genus", ""),
            "differentia": _as_list(n.get("differentia")),
            "proof_info": n.get("proof_info", []),
            "input": n.get("input", []),
            "output": n.get("output", []),
            "steps": _steps,
            # Port #5: HEAD-style "Decomposition" panel reads from step_info.
            "step_info": _steps,
            "equations": [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section",""),
                          "context": e.get("context",""), "parent_step": e.get("parent_step", "")}
                          for e in eq_map.get(nid, [])],
        }
    # Folded node -> the drawn box whose panel shows it, so links to steps,
    # equations and proofs (e.g. from extraction notes) open the right panel.
    folded_host = {}
    for nid, d in js_details.items():
        for x in d["steps"] + d["equations"] + d.get("proofs", []):
            folded_host.setdefault(x["id"], nid)
    # Has-proof toggle (#1.a): collect ids of theorem-like nodes that
    # actually carry proof_info — these are the highlightable targets.
    _has_proof_node_ids = sorted({
        nid for nid, d in js_details.items()
        if d.get("type") in ("theorem", "lemma", "corollary", "proposition", "claim")
        and (d.get("proof_info") or d.get("step_info"))
    })

    js_orphans = [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section","")}
                  for e in orphan_eqs]

    ch = metadata.get("chapter", "")
    ch_title = metadata.get("chapter_title", "")
    if ch_title:
        title = f"Chapter {ch}: {ch_title}"
    else:
        title = metadata.get("title") or "Knowledge Graph"

    # Links back to the source article, so a node can be checked against the
    # paper it was extracted from. arXiv serves the LaTeX source at /e-print/.
    # Old-style ids ("math/9410211") work in the same URL shapes as new ones.
    _aid = str(metadata.get("arxiv_id") or "").strip()
    if not _aid and _re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", Path(html_path).stem):
        _aid = Path(html_path).stem   # v6 metadata may omit it; files are named by it
    source_links = ""
    if _aid:
        _u = "https://arxiv.org/%s/" + _esc(_aid)
        source_links = (
            '<div id="srclinks"><span class="aid">%s</span>'
            '<a href="%s" target="_blank" rel="noopener">abstract</a>'
            '<a href="%s" target="_blank" rel="noopener">PDF</a>'
            '<a href="%s" target="_blank" rel="noopener">LaTeX source</a></div>'
            % (_esc(_aid), _u % "abs", _u % "pdf", _u % "e-print"))

    # Read SVG content
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    # Convert matplotlib's `width=Xpt height=Ypt` to absolute pixels; without
    # this browsers responsively-fit the inline SVG to the flex container.
    import re as _re_svg
    def _pt_to_px(m):
        return f'{m.group(1)}{float(m.group(2)) * 4.0 / 3.0:.0f}px"'
    svg_content = _re_svg.sub(r'(\swidth=")([\d.]+)pt"', _pt_to_px, svg_content, count=1)
    svg_content = _re_svg.sub(r'(\sheight=")([\d.]+)pt"', _pt_to_px, svg_content, count=1)

    # Make node rects clickable by adding onclick via regex.
    # Only match the body-rect gid `node_<nid>` (no `__` separator) — the
    # per-node sub-artist gids `node_<nid>__patch0` etc. exist purely so the
    # toggle JS can find every artist of a node; they must NOT be clickable.
    import re
    def _add_onclick(m):
        nid = m.group(1)
        return 'id="node_' + nid + '" onclick="showDetail(\'' + nid + '\')" style="cursor:pointer;"'
    svg_content = re.sub(r'id="node_((?:(?!__)[^"])+)"', _add_onclick, svg_content)

    # Add foundation links to detail data
    for nid, fnames in case1_matches.items():
        if nid in js_details:
            js_details[nid]["foundation_links"] = list(set(fnames))

    # Paper-level extraction metadata for the "Paper info" panel (v6:
    # paper_style list, extraction_notes [{category, nodes, note}],
    # extraction_comment). The bulky `labels` / `macros` maps are left out.
    paper_info = {k: metadata[k] for k in (
        "model", "effort", "prompt_version", "extraction_date", "annotator",
        "paper_style", "extraction_comment", "extraction_notes",
        "rigor_nonformal_count", "unresolved_refs") if metadata.get(k) not in (None, "", [], {})}
    paper_info["paper_style"] = _as_list(paper_info.get("paper_style"))
    paper_info["extraction_notes"] = [x for x in _as_list(paper_info.get("extraction_notes"))
                                      if isinstance(x, dict)]
    _style_chips = "".join('<span class="chip">%s</span>' % _esc(str(s).replace("_", " "))
                           for s in paper_info["paper_style"])
    n_notes = len(paper_info["extraction_notes"])

    details_json = _json.dumps(js_details, ensure_ascii=True)
    orphans_json = _json.dumps(js_orphans, ensure_ascii=True)
    ghosts_json = _json.dumps(case2_ghosts, ensure_ascii=True)
    case1_json = _json.dumps(case1_matches, ensure_ascii=True)

    present_types = []
    seen = set()
    for n in base_nodes:
        t = n.get("type", "")
        if t and t not in seen and t in NODE_COLORS:
            seen.add(t)
            present_types.append(t)
    legend_items = "\n".join(
        f'  <div class="legend-item"><div class="legend-color" style="background:{NODE_COLORS[t]["body"]};border-color:{NODE_COLORS[t]["header"]};"></div>{t.replace("_"," ").title()}</div>'
        for t in present_types
    )
    # Foundation legend swatches — only include the kinds we actually have.
    foundation_legend_items = ""
    if n_ghost_other:
        foundation_legend_items += (
            '  <div class="legend-item">'
            '<div class="legend-color" style="background:#E8E8E8;border:1.5px dashed #777;"></div>'
            'Foundation: mathlib / herald'
            '</div>\n'
        )
    if n_ghost_book:
        foundation_legend_items += (
            '  <div class="legend-item">'
            '<div class="legend-color" style="background:#FFF8E1;border:1.5px dotted #8D6E63;"></div>'
            'Foundation: book (Gowers / Higham / Func.An.)'
            '</div>\n'
        )

    # Port #5: shared math macros (mirrors HEAD's KATEX_MACROS, adapted for MathJax v3).
    # MathJax `tex.macros` keys are the command name without backslash; values are
    # the expansion. Backslashes in values must be doubled so that the resulting
    # JSON survives the JS string literal.
    _mj_macros_dict = {
        "R": r"\mathbb{R}", "N": r"\mathbb{N}", "Z": r"\mathbb{Z}",
        "Q": r"\mathbb{Q}", "C": r"\mathbb{C}", "F": r"\mathbb{F}",
        "E": r"\mathbb{E}", "P": r"\mathbb{P}",
        "Var": r"\operatorname{Var}", "Cov": r"\operatorname{Cov}",
        "Cor": r"\operatorname{Cor}", "KL":  r"\operatorname{KL}",
        "indep": r"\perp\!\!\!\perp",
        "Tr": r"\operatorname{Tr}", "tr": r"\operatorname{tr}",
        "rk": r"\operatorname{rank}", "rank": r"\operatorname{rank}",
        "diag": r"\operatorname{diag}", "Span": r"\operatorname{Span}",
        "Hom": r"\operatorname{Hom}", "End": r"\operatorname{End}",
        "Aut": r"\operatorname{Aut}", "Hess": r"\operatorname{Hess}",
        "sgn": r"\operatorname{sgn}", "spec": r"\operatorname{spec}",
        "supp": r"\operatorname{supp}", "vol": r"\operatorname{vol}",
        "diam": r"\operatorname{diam}",
        "poly": r"\operatorname{poly}", "polylog": r"\operatorname{polylog}",
        "Lsym": r"L_{\mathrm{sym}}", "Lrw": r"L_{\mathrm{rw}}",
        "Lun":  r"L_1",
        "Cut":     r"\operatorname{Cut}",
        "Ncut":    r"\operatorname{Ncut}",
        "charfct": r"\mathbf{1}",
        "T":      r"\top",
        "defeq":  r"\stackrel{\mathrm{def}}{=}",
        "eqdef":  r"\stackrel{\mathrm{def}}{=}",
        # mathdots-package macro that MathJax doesn't define natively
        # (\vdots and \ddots are already built in).
        "hdots":  r"\ldots",
        "bx": r"\mathbf{x}", "by": r"\mathbf{y}", "bz": r"\mathbf{z}",
        "bw": r"\mathbf{w}", "bu": r"\mathbf{u}", "bv": r"\mathbf{v}",
        "bA": r"\mathbf{A}", "bB": r"\mathbf{B}", "bX": r"\mathbf{X}",
        "bY": r"\mathbf{Y}", "bZ": r"\mathbf{Z}",
        "bepsilon": r"\boldsymbol{\epsilon}", "btheta":   r"\boldsymbol{\theta}",
        "bmu":      r"\boldsymbol{\mu}",      "bSigma":   r"\boldsymbol{\Sigma}",
        "bm": [r"\boldsymbol{#1}", 1],          # the bm package
        # blackboard-bold packages (bbm, dsfont) MathJax lacks: plain \mathbb
        "mathbbm": [r"\mathbb{#1}", 1], "mathbbmss": [r"\mathbb{#1}", 1], "mathds": [r"\mathbb{#1}", 1],
        "ensuremath": [r"#1", 1],
        "qedhere": "", "qed": "",
        # commands of other packages (amstex, physics, nicefrac, graphicx, hyperref, xspace, mathtools, ...)
        # that MathJax lacks: the nearest MathJax form, or the content alone
        "bold": [r"\boldsymbol{#1}", 1], "pmb": [r"\boldsymbol{#1}", 1], "mathbbold": [r"\mathbb{#1}", 1],
        "mathdutchcal": [r"\mathcal{#1}", 1], "mathssf": [r"\mathsf{#1}", 1], "euscr": [r"\mathscr{#1}", 1],
        "EuScript": [r"\mathscr{#1}", 1], "mathlarger": ["#1", 1], "mathsmaller": ["#1", 1],
        "Tilde": [r"\widetilde{#1}", 1], "Bar": [r"\overline{#1}", 1], "Hat": [r"\widehat{#1}", 1],
        "widecheck": [r"\check{#1}", 1], "underbar": [r"\underline{#1}", 1],
        "underaccent": [r"\underset{#1}{#2}", 2], "accentset": [r"\overset{#1}{#2}", 2],
        "dag": r"\dagger", "ddag": r"\ddagger", "vcentcolon": r"\mathrel{:}", "enskip": r"\enspace",
        "nicefrac": [r"{}^{#1}\!/\!{}_{#2}", 2], "sfrac": [r"{}^{#1}\!/\!{}_{#2}", 2],
        "operatornamewithlimits": [r"\operatorname*{#1}", 1],
        "dd": r"\mathrm{d}", "qty": [r"\left(#1\right)", 1], "abs": [r"\left\lvert #1\right\rvert", 1],
        "norm": [r"\left\lVert #1\right\rVert", 1], "mqty": [r"\begin{matrix}#1\end{matrix}", 1],
        "smqty": [r"\begin{smallmatrix}#1\end{smallmatrix}", 1], "pdv": [r"\frac{\partial #1}{\partial #2}", 2],
        "xspace": "", "fam": "", "protect": "", "phantomsection": "", "selectfont": "", "allowbreak": "",
        "break": "", "medskip": "", "smallskip": "", "bigskip": "", "noindent": "", "begingroup": "", "endgroup": "",
        "delimsize": "", "nobreak": "", "relax": "",
        "texorpdfstring": ["#1", 2], "scalebox": ["#2", 2], "resizebox": ["#3", 3], "rotatebox": ["#2", 2],
        "raisebox": ["#2", 2], "adjustbox": ["#2", 2], "scaleto": ["#1", 2], "smashoperator": ["#1", 1],
        "makebox": [r"\text{#2}", 2, ""], "parbox": [r"\text{#2}", 2], "lefteqn": ["#1", 1],
        "intertext": [r"\text{#1}", 1], "textsuperscript": [r"^{\text{#1}}", 1], "textcircled": [r"(#1)", 1],
        "setlength": ["", 2], "index": ["", 1], "refstepcounter": ["", 1], "pushQED": ["", 1],
        "hyperref": ["#2", 2, ""], "hypertarget": ["#2", 2], "hyperlink": ["#2", 2],
        "L": r"\text{Ł}", "l": r"\text{ł}", "i": r"\imath", "j": r"\jmath", "Sha": r"\text{Ш}",
        "fint": r"{\int\!\!\!\!\!\!-}", "Mod": [r"\;(\mathrm{mod}\ #1)", 1], "addtocounter": ["", 2],
        "normalfont": "", "footnotesize": "", "scriptsize": "", "small": "", "large": "", "Large": "",
        "offinterlineskip": "", "mathpalette": ["#2", 2],
        "on": [r"\operatorname{#1}", 1], "bgroup": "", "egroup": "", "aftergroup": "",
        # stmaryrd / cmll symbols MathJax lacks
        "with": r"\mathbin{\&}", "parr": r"\mathbin{\unicode{x214B}}", "llbracket": r"[\![", "rrbracket": r"]\!]",
        "llparenthesis": r"(\!|", "rrparenthesis": r"|\!)", "varoast": r"\circledast", "bigsqcap": r"\mathop{\Large\sqcap}",
        "sslash": r"\mathbin{\unicode{x2AFD}}", "fatsemi": r"\mathbin{\unicode{x2A1F}}", "lightning": r"\unicode{x21AF}",
        "mapsfrom": r"\mathrel{\unicode{x21A4}}", "Mapsto": r"\mathrel{\unicode{x2907}}", "Mapsfrom": r"\mathrel{\unicode{x2906}}",
        "oblong": r"\unicode{x25AF}", "obar": r"\mathbin{\unicode{x233D}}", "talloblong": r"\unicode{x2AFE}",
        "Lbag": r"\unicode{x27C5}", "Rbag": r"\unicode{x27C6}", "boxbar": r"\mathbin{\unicode{x25EB}}",
    }
    for _i in range(26):
        _L = chr(65 + _i)
        _mj_macros_dict["c" + _L] = r"\mathcal{" + _L + r"}"
    _mj_macros_json = _json.dumps(_mj_macros_dict)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<script>MathJax = {{loader: {{load: ['[tex]/boldsymbol']}}, tex: {{packages: {{'[+]': ['boldsymbol']}}, inlineMath: [['$','$'], ['\\\\(','\\\\)']], displayMath: [['$$','$$'], ['\\\\[','\\\\]']], macros: {_mj_macros_json}}}, startup: {{typeset: false}}}};</script>
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
#svg-container svg.lod-far [id*="__lodbody_"] {{ display: none; }}
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
/* Port #4: 3-button toggle panel (Foundation / Examples & Remarks / Cited Results) */
.toggle-panel {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-left: 12px; padding: 4px 8px; background: #ECEFF1; border: 1px solid #CFD8DC; border-radius: 6px; }}
.toggle-panel .toggle-label {{ font-size: 11px; color: #555; font-weight: bold; text-transform: uppercase; margin-right: 4px; }}
.toggle-btn {{ padding: 4px 12px; border: 1.5px solid #757575; border-radius: 4px; background: #E0E0E0; cursor: pointer; font-size: 12px; color: #333; }}
.toggle-btn:hover {{ background: #BDBDBD; }}
.toggle-btn[data-showing="1"] {{ background: #2E7D32; color: white; border-color: #1B5E20; }}
.toggle-btn[disabled] {{ opacity: 0.4; cursor: not-allowed; background: #EEE; color: #333; border-color: #BDBDBD; }}
.node-aux-shown {{ opacity: 0.75; }}
#srclinks {{ margin: 2px 0 6px; font-size: 12px; color: #666; }}
#srclinks .aid {{ font-family: monospace; margin-right: 10px; color: #333; }}
#srclinks a {{ margin-right: 10px; color: #0645ad; text-decoration: none; }}
#srclinks a:hover {{ text-decoration: underline; }}
.chip {{ display: inline-block; padding: 1px 7px; margin: 0 4px 2px 0; border-radius: 9px; background: #ECEFF1; border: 1px solid #B0BEC5; font-size: 11px; color: #37474F; }}
#header .chip {{ background: #3d566e; border-color: #5d7a96; color: #e0e6eb; }}
.badge {{ display: inline-block; padding: 1px 6px; margin-right: 4px; border-radius: 3px; font-size: 11px; border: 1px solid #999; color: #444; background: #f7f7f7; }}
.badge.rigor-heuristic, .badge.rigor-conjectural {{ background: #FFEBEE; border-color: #C62828; color: #B71C1C; }}
.badge.rigor-semi_formal, .badge.rigor-numerical {{ background: #FFF8E1; border-color: #F9A825; color: #6D4C00; }}
.nodelink {{ color: #2471A3; cursor: pointer; }}
.nodelink:hover {{ text-decoration: underline; }}
.step-item details > summary {{ cursor: pointer; font-size: 11px; color: #666; }}
.note-item {{ background: #FFFDE7; border-left: 3px solid #FBC02D; padding: 6px 10px; font-size: 12px; margin-bottom: 4px; }}
</style>
</head>
<body>
<div id="header">
  <h1>{_esc(title)}<span class="hint">— click nodes for detailed description</span></h1>
  {source_links}<span id="paper-style">{_style_chips}</span>
  <div id="controls">
    <button onclick="showPaperInfo()" title="Extraction metadata: paper style, extractor comment and notes">Paper info{(' (%d notes)' % n_notes) if n_notes else ''}</button>
    <button onclick="resetView()">Reset</button>
    <button onclick="zoomIn()">Zoom +</button>
    <button onclick="zoomOut()">Zoom -</button>
    <button onclick="zoomFit()">Fit</button>
    <span id="lod-note" style="margin-left:10px;font-size:13px;font-weight:bold;color:#C0392B;"></span>
  </div>
</div>
<div class="legend">
{legend_items}
  <div class="legend-item" style="margin-left:12px;"><span style="font-size:18px;color:#555;">&#8594;</span> A supports B</div>
  <div class="legend-item"><svg width="30" height="10"><line x1="0" y1="5" x2="30" y2="5" stroke="#455A64" stroke-width="2" stroke-dasharray="6,2,1,2"/></svg> backward reference</div>
  <div class="legend-item"><svg width="30" height="10"><line x1="0" y1="5" x2="30" y2="5" stroke="#9FA8DA" stroke-width="1.5" stroke-dasharray="2,2"/></svg> mention (refers to, does not rely on)</div>
  <div class="legend-item"><svg width="30" height="10"><line x1="0" y1="5" x2="30" y2="5" stroke="#7F8C8D" stroke-width="2" stroke-dasharray="1,1.5"/></svg> stated inside</div>
  <div class="legend-item"><span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:#FFD54F;border:1px solid #5D4037;text-align:center;font-weight:bold;font-size:11px;color:#5D4037;line-height:12px;">*</span>&nbsp;has proof (click)</div>
{foundation_legend_items}  <div class="toggle-panel" id="toggle-panel">
    <span class="toggle-label">Toggle:</span>
    <button class="toggle-btn" id="ghost-btn" onclick="toggleGhosts()"{(' disabled' if not n_ghost_total else '')}>Foundations ({n_ghost_total})</button>
    <button class="toggle-btn" id="aux-btn" data-showing="1" onclick="toggleAux()"{(' disabled' if not aux_node_ids else '')}>Examples &amp; Remarks ({len(aux_node_ids)})</button>
    <button class="toggle-btn" id="ext-btn" onclick="toggleExternal()"{(' disabled' if not ext_node_ids else '')}>Cited Results ({len(ext_node_ids)})</button>
    <button class="toggle-btn" id="lowconf-btn" data-showing="1" onclick="toggleLowConf()"{(' disabled' if not low_conf_edge_gids else '')}>Low-confidence edges ({len(low_conf_edge_gids)})</button>
    <button class="toggle-btn" id="implied-btn" data-showing="1" onclick="toggleImplied()"{(' disabled' if not implied_edge_gids else '')} title="Edges also reachable by a longer path — redundant for reading the dependency structure">Implied edges ({len(implied_edge_gids)})</button>
    <button class="toggle-btn" id="backbone-btn" data-showing="1" onclick="toggleBackbone()"{(' disabled' if not nonbackbone_node_ids else '')} title="Show only definitions and theorem-like results">Backbone only</button>
    <button class="toggle-btn" id="backward-btn" data-showing="1" onclick="toggleBackward()"{(' disabled' if not backward_edge_gids else '')} title="Dependencies that point against paper order (dash-dotted)">Backward edges ({len(backward_edge_gids)})</button>
    <button class="toggle-btn" id="mention-btn" data-showing="1" onclick="toggleMention()"{(' disabled' if not mention_edge_gids else '')} title="References that do not rely on the source (thin, light dashes)">Mentions ({len(mention_edge_gids)})</button>
    <button class="toggle-btn" id="nested-btn" data-showing="1" onclick="toggleNested()"{(' disabled' if not nested_node_ids else '')} title="Results stated inside a proof or another result; hiding collapses them into the box that contains them (listed in its panel)">Nested results ({len(nested_node_ids)})</button>
  </div>
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
// Port #4: aux (example/remark) and ext (external-origin) node id lists.
var AUX_NODE_IDS = {_json.dumps(aux_node_ids, ensure_ascii=True)};
var EXT_NODE_IDS = {_json.dumps(ext_node_ids, ensure_ascii=True)};
var LOW_CONF_EDGE_GIDS = {_json.dumps(low_conf_edge_gids, ensure_ascii=True)};
var IMPLIED_EDGE_GIDS = {_json.dumps(implied_edge_gids, ensure_ascii=True)};
var NONBACKBONE_NODE_IDS = {_json.dumps(nonbackbone_node_ids, ensure_ascii=True)};
// Port #1: has-proof targets (theorem-like with non-empty proof_info).
var HAS_PROOF_NODE_IDS = {_json.dumps(_has_proof_node_ids, ensure_ascii=True)};
// Port #1: foundation ghost-element index lists split by source.
var GHOST_BOOK_INDICES = {_json.dumps(ghost_book_indices, ensure_ascii=True)};
var GHOST_OTHER_INDICES = {_json.dumps(ghost_other_indices, ensure_ascii=True)};
// Bug 1 fix: incident-edge map so hiding a node also hides edges touching it.
var NODE_TO_EDGES = {_json.dumps(node_to_edges, ensure_ascii=True)};
var BACKWARD_EDGE_GIDS = {_json.dumps(backward_edge_gids, ensure_ascii=True)};
var MENTION_EDGE_GIDS = {_json.dumps(mention_edge_gids, ensure_ascii=True)};
var NESTED_NODE_IDS = {_json.dumps(nested_node_ids, ensure_ascii=True)};
var PAPER_INFO = {_json.dumps(paper_info, ensure_ascii=True)};
var FOLDED_HOST = {_json.dumps(folded_host, ensure_ascii=True)};

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
      h += '<div class="eq-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + eqTex(e.statement) + '</div>';
    }});
    if (ORPHANS.length === 0) h += '<div style="color:#888;">No orphan equations.</div>';
    panel.innerHTML = h;
    panel.className = "open";
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([panel]).catch(function(){{}});
    return;
  }}
  var d = DETAILS[nodeId];
  if (!d) return;
  var h = '<h3 style="margin:0 0 8px;font-size:16px;">' + esc(dispId(nodeId)) + ': ' + esc(d.name || d.type) + '</h3>';
  h += '<div style="font-size:12px;color:#888;margin-bottom:4px;">' + d.type + (d.section ? ' (Sec ' + esc(d.section) + ')' : '') + '</div>';
  // v6 node metadata: rigor, confidence, tags; and where the node is stated.
  var meta = rigorBadge(d.rigor) + confBadge(d.confidence);
  (d.tags || []).forEach(function(t) {{ meta += '<span class="chip">' + esc(String(t)) + '</span>'; }});
  if (meta) h += '<div style="margin-bottom:6px;">' + meta + '</div>';
  if (d.inside) {{
    var via = '';
    var host = DETAILS[d.inside];
    (host && host.contains || []).forEach(function(c) {{
      if (c.id === nodeId && c.parent && c.parent !== d.inside) via = ' (in ' + esc(c.parent) + ')';
    }});
    h += '<div style="font-size:12px;margin-bottom:6px;">Stated inside ' + nodeLink(d.inside) + via + '</div>';
  }}
  // Origin badge — paper (default) or external (cited prior result)
  if (d.origin === "external") {{
    var citeStr = d.origin_citation ? (' &mdash; ' + esc(d.origin_citation)) : '';
    h += '<div style="display:inline-block;padding:2px 8px;background:#FFF3E0;border:1px dashed #E65100;border-radius:3px;font-size:11px;color:#BF360C;margin-bottom:8px;">External (cited prior result)' + citeStr + '</div>';
  }}
  // Foundation graph link badge (Case 1: known result)
  if (d.foundation_links && d.foundation_links.length > 0) {{
    h += '<div style="display:inline-block;padding:2px 8px;background:#E3F2FD;border:1px solid #2471A3;border-radius:3px;font-size:11px;color:#2471A3;margin-bottom:8px;">&#128218; Known result: ' + d.foundation_links.map(esc).join(', ') + '</div>';
  }}
  // Pre-build equation maps by context
  var eqsByCtx = {{statement:[], assumption:[], conclusion:[], proof:[], orphan:[]}};
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
  var eqBlock = function(e) {{ return '<div style="margin:2px 0 2px 12px;padding:3px 8px;background:#EBF5FB;border-left:2px solid #5DADE2;font-size:12px;">' + esc(dispId(e.id)) + ': ' + eqTex(e.statement) + '</div>'; }};

  // Statement + inline statement equations.
  // Prefer raw_latex (TeX intact -> MathJax can typeset). statement/statement_clean
  // are de-TeX'd for matching ($ and command backslashes stripped) and won't render.
  var stmtSrc = d.statement_render || d.statement || '';
  if (stmtSrc) {{
    h += '<div class="detail-section"><h4>Statement</h4><div style="font-size:14px;">' + esc(stmtSrc) + '</div>';
    eqsByCtx.statement.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  if (d.type === 'definition') {{
    var gl = defGloss(d);
    if (gl) h += '<div class="detail-section"><h4>Reads as</h4><div style="font-size:13px;">' + gl + '</div></div>';
  }}
  // Short summary: statement_short, or (older files) a statement_clean that
  // actually differs from the statement.
  var summary = d.statement_short || (d.statement_clean !== d.statement ? d.statement_clean : '');
  if (summary) {{
    h += '<div class="detail-section"><h4>Summary</h4><div style="font-size:13px;">' + esc(summary) + '</div></div>';
  }}
  // Assumptions + inline assumption equations
  if ((d.assumptions && d.assumptions.length > 0) || eqsByCtx.assumption.length > 0) {{
    h += '<div class="detail-section"><h4>Assumptions</h4>';
    if (d.assumptions) d.assumptions.forEach(function(a) {{ h += listItem(a); }});
    eqsByCtx.assumption.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  // Conclusions + inline conclusion equations
  if ((d.conclusions && d.conclusions.length > 0) || eqsByCtx.conclusion.length > 0) {{
    h += '<div class="detail-section"><h4>Conclusions</h4>';
    if (d.conclusions) d.conclusions.forEach(function(c) {{ h += listItem(c); }});
    eqsByCtx.conclusion.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  // Proofs: one entry per merged proof node (name, strategy labels, rigor,
  // summary); the joined proof_info strings remain the fallback.
  if (d.proofs && d.proofs.length > 0) {{
    h += '<div class="detail-section"><h4>Proof' + (d.proofs.length > 1 ? 's (' + d.proofs.length + ')' : '') + '</h4>';
    d.proofs.forEach(function(p) {{
      h += '<div class="step-item"><strong>' + esc(dispId(p.id)) + (p.name ? ': ' + esc(p.name) : '') + '</strong> ';
      (p.proof_strategy || []).forEach(function(s) {{ h += '<span class="chip">' + esc(String(s)) + '</span>'; }});
      h += rigorBadge(p.rigor) + confBadge(p.confidence);
      if (p.statement_short) h += '<div style="font-size:12px;color:#444;margin-top:2px;">' + esc(p.statement_short) + '</div>';
      h += '</div>';
    }});
    eqsByCtx.proof.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }} else if (d.proof_info && d.proof_info.length > 0) {{
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
  // Proof / algorithm steps with inline equations. v2: algorithm_step folded
  // into parent algorithm; render same panel but title by parent type.
  // Port #5: heading mirrors HEAD's "Decomposition (N steps)" wording.
  // v6 steps nest (a loop body, a sub-claim): each step's children are drawn
  // inside it, indented, behind a collapse/expand toggle. Results stated in a
  // step (d.contains with parent = that step) are listed under it.
  var containsByParent = {{}};
  (d.contains || []).forEach(function(c) {{
    (containsByParent[c.parent] = containsByParent[c.parent] || []).push(c);
  }});
  var placed = {{}};
  if (d.steps && d.steps.length > 0) {{
    var stepIds = {{}};
    d.steps.forEach(function(s) {{ stepIds[s.id] = true; }});
    var kidsOf = {{}};
    d.steps.forEach(function(s) {{
      var p = (s.parent_step && stepIds[s.parent_step]) ? s.parent_step : '';
      (kidsOf[p] = kidsOf[p] || []).push(s);
    }});
    var renderSteps = function(parent) {{
      var out = '';
      var kids = kidsOf[parent] || [];
      kids.forEach(function(s, i) {{
        placed[s.id] = true;
        var ord = (s.step_order || (i + 1));
        var label = s.name ? esc(s.name) : esc(s.id ? dispId(s.id) : ('Step ' + ord));
        var full = s.statement_clean || s.statement || '';
        out += '<div class="step-item"><strong>' + ord + '. ' + label + '</strong>';
        if (s.subclass) {{
          out += ' <span style="font-size:11px;font-style:italic;color:#666;">[' + esc(s.subclass) + ']</span>';
        }}
        if (s.source_line_label) out += ' <span class="badge">line ' + esc(String(s.source_line_label)) + '</span>';
        out += rigorBadge(s.rigor) + confBadge(s.confidence);
        if (s.statement_short) {{
          out += '<div style="font-size:12px;color:#444;margin-top:2px;">' + esc(s.statement_short) + '</div>';
          if (full) out += '<details><summary>full text</summary><div style="font-size:12px;color:#444;">' + esc(full) + '</div></details>';
        }} else if (full) {{
          out += '<div style="font-size:12px;color:#444;margin-top:2px;">' + esc(full) + '</div>';
        }}
        (eqsByStep[s.id] || []).forEach(function(e) {{ out += eqBlock(e); }});
        (containsByParent[s.id] || []).forEach(function(c) {{
          placed[c.id] = true;
          out += '<div style="font-size:12px;margin:3px 0 0 8px;">&#8627; states ' + nodeLink(c.id, dispId(c.id) + ': ' + (c.name || c.type)) + '</div>';
        }});
        if (kidsOf[s.id]) {{
          out += '<div style="font-size:11px;color:#2471A3;cursor:pointer;margin-top:3px;" onclick="toggleStepKids(this)">&#9662; ' + kidsOf[s.id].length + ' sub-step' + (kidsOf[s.id].length > 1 ? 's' : '') + '</div>';
          out += '<div style="margin-left:10px;margin-top:4px;">' + renderSteps(s.id) + '</div>';
        }}
        out += '</div>';
        if (i < kids.length - 1) out += '<div class="step-arrow">&#8595;</div>';
      }});
      return out;
    }};
    h += '<div class="detail-section"><h4>Decomposition (' + d.steps.length + (d.steps.length === 1 ? ' step' : ' steps') + ')</h4>' + renderSteps('') + '</div>';
  }}
  // Equations whose step was not rendered, proof equations without a proof
  // entry, and contained results not placed under a step: never drop them.
  Object.keys(eqsByStep).forEach(function(k) {{ if (!placed[k]) eqsByCtx.orphan = eqsByCtx.orphan.concat(eqsByStep[k]); }});
  if (!(d.proofs && d.proofs.length)) eqsByCtx.orphan = eqsByCtx.orphan.concat(eqsByCtx.proof);
  var looseContains = (d.contains || []).filter(function(c) {{ return !placed[c.id]; }});
  if (looseContains.length > 0) {{
    h += '<div class="detail-section"><h4>Contains</h4>';
    looseContains.forEach(function(c) {{
      h += '<div style="font-size:13px;padding:2px 0 2px 10px;">&bull; ' + nodeLink(c.id, dispId(c.id) + ': ' + (c.name || c.type)) + (c.parent !== nodeId ? ' <span style="color:#888;">(in ' + esc(c.parent) + ')</span>' : '') + '</div>';
    }});
    h += '</div>';
  }}
  // Extraction notes that name this node (v6 metadata.extraction_notes).
  var myNotes = (PAPER_INFO.extraction_notes || []).filter(function(x) {{ return (x.nodes || []).indexOf(nodeId) >= 0; }});
  if (myNotes.length > 0) {{
    h += '<div class="detail-section"><h4>Extractor notes</h4>';
    myNotes.forEach(function(x) {{ h += noteBlock(x); }});
    h += '</div>';
  }}
  // Orphan equations (collapsible)
  if (eqsByCtx.orphan.length > 0) {{
    h += '<div class="detail-section"><h4 style="cursor:pointer;" onclick="toggleEqPanel(this)">Unplaced Equations (' + eqsByCtx.orphan.length + ') &#9660;</h4>';
    h += '<div style="display:none;">';
    eqsByCtx.orphan.forEach(function(e) {{
      h += '<div class="eq-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + eqTex(e.statement) + '</div>';
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
  ORPHANS.forEach(function(e) {{ h += '<div class="orphan-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + eqTex(e.statement) + '</div>'; }});
  document.getElementById("orphan-list").innerHTML = h;
  p.style.display = "block";
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([p]).catch(function(){{}});
}}
// Ghost nodes (Foundation) — selector covers both "ghost_*" and "ghostbook_*"
// so a single toggle hides/shows the entire foundation overlay (mathlib AND book).
function toggleGhosts() {{
  var svgEl = document.querySelector("#svg-container svg");
  var ghostEls = svgEl ? svgEl.querySelectorAll('[id^="ghost"]') : [];
  var btn = document.getElementById("ghost-btn");
  var isShowing = btn.dataset.showing === "1";
  if (!isShowing) {{
    btn.dataset.showing = "1";
    ghostEls.forEach(function(el) {{ el.style.display = ""; }});
    // Reflect subset toggles to "on" too.
    var mb = document.getElementById("ghost-mathlib-btn");
    var bb = document.getElementById("ghost-book-btn");
    if (mb && !mb.disabled) mb.dataset.showing = "1";
    if (bb && !bb.disabled) bb.dataset.showing = "1";
  }} else {{
    btn.dataset.showing = "0";
    ghostEls.forEach(function(el) {{ el.style.display = "none"; }});
    var mb = document.getElementById("ghost-mathlib-btn");
    var bb = document.getElementById("ghost-book-btn");
    if (mb && !mb.disabled) mb.dataset.showing = "0";
    if (bb && !bb.disabled) bb.dataset.showing = "0";
  }}
}}

// Port #1: Foundation subset toggles. Show/hide ghost elements whose gid
// suffix matches the subset's index list. Indices come from
// GHOST_BOOK_INDICES (book entries) / GHOST_OTHER_INDICES (mathlib/herald).
function _toggleGhostSubset(btnId, indices, prefix) {{
  var svgEl = document.querySelector("#svg-container svg");
  if (!svgEl) return;
  var btn = document.getElementById(btnId);
  if (!btn || btn.disabled) return;
  var nextShowing = !(btn.dataset.showing === "1");
  btn.dataset.showing = nextShowing ? "1" : "0";
  indices.forEach(function(gi) {{
    // Box, header, text, refs for this ghost
    ["box", "header", "text", "refs"].forEach(function(kind) {{
      var el = svgEl.querySelector('[id="' + prefix + '_' + kind + '_' + gi + '"]');
      if (el) el.style.display = nextShowing ? "" : "none";
    }});
    // Edges: <prefix>_edge_<gi>_<ti> — match all by gi prefix scan.
    var edges = svgEl.querySelectorAll('[id^="' + prefix + '_edge_' + gi + '_"]');
    edges.forEach(function(e) {{ e.style.display = nextShowing ? "" : "none"; }});
  }});
}}
function toggleGhostsMathlib() {{
  // Mathlib/proofwiki/herald entries use the "ghost" prefix.
  _toggleGhostSubset("ghost-mathlib-btn", GHOST_OTHER_INDICES, "ghost");
}}
function toggleGhostsBook() {{
  // Book entries use the "ghostbook" prefix.
  _toggleGhostSubset("ghost-book-btn", GHOST_BOOK_INDICES, "ghostbook");
}}

// Port #1: "Has proof" toggle — highlight theorem-like nodes with a non-empty
// proof_info by toggling a CSS class on the body rect.
function toggleHasProof() {{
  var btn = document.getElementById("has-proof-btn");
  if (!btn || btn.disabled) return;
  var nextShowing = !(btn.dataset.showing === "1");
  btn.dataset.showing = nextShowing ? "1" : "0";
  var svgEl = document.querySelector("#svg-container svg");
  if (!svgEl) return;
  HAS_PROOF_NODE_IDS.forEach(function(nid) {{
    var safeNid = String(nid).replace(/ /g, "_");
    var body = svgEl.querySelector('[id="node_' + safeNid + '"]');
    if (!body) return;
    var pathEl = body.tagName === "path" ? body : body.querySelector("path");
    if (!pathEl) return;
    if (nextShowing) {{
      pathEl.setAttribute("data-prev-stroke", pathEl.getAttribute("stroke") || "");
      pathEl.setAttribute("data-prev-strokewidth", pathEl.getAttribute("stroke-width") || "");
      pathEl.setAttribute("stroke", "#5D4037");
      pathEl.setAttribute("stroke-width", "3");
    }} else {{
      pathEl.setAttribute("stroke", pathEl.getAttribute("data-prev-stroke") || "");
      pathEl.setAttribute("stroke-width", pathEl.getAttribute("data-prev-strokewidth") || "");
    }}
  }});
}}

// Port #4: Generic helper to hide/show a set of nodes by id.
// Bug 1 fix: also hide/show every edge incident to the toggled nodes via
// NODE_TO_EDGES, so we don't leave dangling arrows pointing into empty space.
function _setNodeVisibility(nodeIds, visible, extraClass) {{
  var svgEl = document.querySelector("#svg-container svg");
  if (!svgEl) return;
  var edgeGids = {{}};  // collect unique edge gids touching any toggled node
  nodeIds.forEach(function(nid) {{
    var safeNid = String(nid).replace(/ /g, "_");
    var body = svgEl.querySelector('[id="node_' + safeNid + '"]');
    if (body) {{
      body.style.display = visible ? "" : "none";
      if (extraClass) {{
        if (visible) body.classList.add(extraClass); else body.classList.remove(extraClass);
      }}
    }}
    var sibs = svgEl.querySelectorAll('[id^="node_' + safeNid + '__"]');
    sibs.forEach(function(el) {{
      el.style.display = visible ? "" : "none";
    }});
    var incident = NODE_TO_EDGES[nid] || [];
    incident.forEach(function(g) {{ edgeGids[g] = true; }});
  }});
  Object.keys(edgeGids).forEach(function(g) {{
    var el = svgEl.querySelector('[id="' + g + '"]');
    if (el) el.style.display = visible ? "" : "none";
  }});
}}

// Examples & Remarks toggle
function toggleAux() {{
  var btn = document.getElementById("aux-btn");
  if (btn.disabled) return;
  var nextShowing = !(btn.dataset.showing === "1");
  btn.dataset.showing = nextShowing ? "1" : "0";
  _setNodeVisibility(AUX_NODE_IDS, nextShowing, "node-aux-shown");
}}

// Low-confidence edges (e.g. term_reuse, confidence 0.3) — already drawn faded;
// this toggle hides/shows them entirely to reveal the high-confidence skeleton.
function toggleLowConf() {{
  var btn = document.getElementById("lowconf-btn");
  if (btn.disabled) return;
  var nextShowing = !(btn.dataset.showing === "1");
  btn.dataset.showing = nextShowing ? "1" : "0";
  var svgEl = document.querySelector("#svg-container svg");
  if (!svgEl) return;
  LOW_CONF_EDGE_GIDS.forEach(function(gid) {{
    var el = svgEl.querySelector('[id="' + gid + '"]');
    if (el) el.style.display = nextShowing ? "" : "none";
  }});
}}

// Cited Results (External) toggle — also applies dashed border when shown,
// matching HEAD's visual differentiation of external nodes.
function toggleExternal() {{
  var btn = document.getElementById("ext-btn");
  if (btn.disabled) return;
  var nextShowing = !(btn.dataset.showing === "1");
  btn.dataset.showing = nextShowing ? "1" : "0";
  _setNodeVisibility(EXT_NODE_IDS, nextShowing);
  var svgEl = document.querySelector("#svg-container svg");
  if (!svgEl) return;
  EXT_NODE_IDS.forEach(function(nid) {{
    var safeNid = String(nid).replace(/ /g, "_");
    var body = svgEl.querySelector('[id="node_' + safeNid + '"]');
    if (!body) return;
    var pathEl = body.tagName === "path" ? body : body.querySelector("path");
    if (!pathEl) return;
    if (nextShowing) {{
      pathEl.setAttribute("stroke-dasharray", "6,3");
      pathEl.setAttribute("stroke-width", "2");
    }} else {{
      pathEl.removeAttribute("stroke-dasharray");
      pathEl.removeAttribute("stroke-width");
    }}
  }});
}}
function showGhostDetail(nameOrEl) {{
  var name = (typeof nameOrEl === 'string') ? nameOrEl : nameOrEl;
  var panel = document.getElementById("detail-panel");
  var refs = GHOSTS[name] || [];
  var h = '<h3 style="margin:0 0 8px;font-size:16px;">' + esc(name) + '</h3>';
  var gd = (typeof GHOST_DEFS !== 'undefined' && GHOST_DEFS[name]) || null;
  if (gd) {{
    // A grounded concept: the textbook definitions it is made of, each from its book.
    h += '<div style="font-size:12px;color:#795548;margin-bottom:10px;">Foundation concept' + (gd.kind ? ' (' + esc(gd.kind) + ')' : '') +
         (gd.books && gd.books.length ? ' in ' + gd.books.length + (gd.books.length > 1 ? ' sources' : ' source') : '') +
         (gd.terms && gd.terms.length ? ' &middot; matched on &ldquo;' + gd.terms.map(esc).join('&rdquo;, &ldquo;') + '&rdquo;' : '') + '</div>';
    if (gd.defs && gd.defs.length) {{
      // The best-ranked definition (build.py def_rank) is shown; the other books' versions open on request.
      var more = gd.defs.length - 1;
      h += '<div class="detail-section"><h4>Definition' + (more ? ' <span style="font-weight:normal;color:#888;">(' + esc(gd.defs[0].book) + ')</span>' : '') + '</h4>';
      gd.defs.forEach(function(d, i) {{
        var gl = defGloss(d);
        h += '<div class="gdef' + (i ? ' gdef-more' : '') + '" style="font-size:13px;padding:4px 0 6px 10px;border-left:3px solid #D7CCC8;margin-bottom:6px;' + (i ? 'display:none;' : '') + '">' +
             '<div style="font-size:11px;color:#8D6E63;margin-bottom:2px;">' + esc(d.book) + (d.where ? ' <span style="color:#aaa;">' + esc(d.where) + '</span>' : '') + '</div>' +
             '<div>' + esc(d.statement) + '</div>' +
             (gl ? '<div style="font-size:12px;color:#555;margin-top:3px;">reads as ' + gl + '</div>' : '') +
             (d.weak ? '<div style="font-size:11px;color:#B71C1C;margin-top:3px;">This sentence uses the term rather than defining it.</div>' : '') + '</div>';
      }});
      if (more) h += '<a href="#" class="gdef-toggle" style="font-size:12px;color:#2471A3;" onclick="return toggleGhostDefs(this)">' +
                     'Show all ' + gd.defs.length + ' sources</a>';
      h += '</div>';
    }} else {{
      h += '<div style="font-size:12px;color:#888;margin-bottom:10px;">No definition text in the concept record.</div>';
    }}
  }} else {{
    h += '<div style="font-size:12px;color:#795548;margin-bottom:10px;">External dependency (from Foundation Graph)</div>';
  }}
  h += '<div class="detail-section"><h4>Referenced by</h4>';
  refs.forEach(function(nid) {{
    var d = DETAILS[nid];
    var label = d ? (dispId(nid) + ': ' + (d.name || d.type)) : dispId(nid);
    h += '<div style="font-size:13px;padding:2px 0 2px 10px;cursor:pointer;color:#2471A3;" data-nid="' + nid + '" onclick="showDetail(this.dataset.nid)">&bull; ' + esc(label) + '</div>';
  }});
  h += '</div>';
  panel.innerHTML = h;
  panel.className = "open";
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([panel]).catch(function () {{}});   // TeX in the definitions
}}


function toggleGhostDefs(a) {{
  var sec = a.parentNode, open = a.textContent.indexOf('Show') === 0;
  sec.querySelectorAll('.gdef-more').forEach(function (d) {{ d.style.display = open ? '' : 'none'; }});
  a.textContent = open ? 'Show one source' : a.textContent.replace('Show one source', 'Show all');
  if (open) {{ a.textContent = 'Show one source'; if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([sec]).catch(function () {{}}); }}
  else a.textContent = 'Show all ' + sec.querySelectorAll('.gdef').length + ' sources';
  return false;
}}
function toggleEqPanel(el) {{
  var panel = el.nextElementSibling;
  if (panel) panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}}
function esc(t) {{ return t ? t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") : ""; }}
// An assumption or conclusion: a bullet and the text, or a display formula on its own line.
function listItem(t) {{
  t = String(t || '').trim(); if (!t) return '';
  var display = /^(\\$\\$[\\s\\S]*\\$\\$|\\\\\\[[\\s\\S]*\\\\\\])$/.test(t);
  return '<div style="font-size:13px;padding:2px 0 2px 10px;">' + (display ? '' : '&bull; ') + esc(t) + '</div>';
}}
// The structured reading of a definition, from its genus and differentia: "a matching: contains all nodes".
function defGloss(d) {{
  var g = d.genus; if (Array.isArray(g)) g = g.join(', ');
  var df = (d.differentia || []).map(function (x) {{ return String(x); }}).filter(Boolean);
  if (!g && !df.length) return '';
  var head = g ? (/^(an?|the)\\s/i.test(String(g)) ? '' : 'a ') + esc(String(g)) : '';
  return head + (head && df.length ? ': ' : '') + df.map(esc).join('; ');
}}
function escAttr(t) {{ return esc(String(t || "")).replace(/"/g, "&quot;"); }}
// An equation node's statement is bare TeX (no $): display it as math.
function eqTex(t) {{ t = String(t || "").trim(); if (!t || t.indexOf("$") >= 0) return esc(t); if (/^\\\\begin\\{{(equation|align|gather|multline|eqnarray|flalign|alignat)\\*?\\}}[\\s\\S]*\\\\end\\{{\\1\\*?\\}}$/.test(t)) return esc(t); t = t.replace(/\\\\(nonumber|notag)(?![A-Za-z])/g, ""); var top = t.replace(/\\\\begin\\{{([a-z]+\\*?)\\}}[\\s\\S]*?\\\\end\\{{\\1\\}}/g, ""); if (/&|\\\\\\\\/.test(top)) t = "\\\\begin{{aligned}}" + t + "\\\\end{{aligned}}"; return "$$" + esc(t) + "$$"; }}
// v6 side-panel helpers.
function rigorBadge(r) {{
  return r ? '<span class="badge rigor-' + escAttr(r) + '" title="rigor">' + esc(String(r).replace(/_/g, '-')) + '</span>' : '';
}}
function confBadge(c) {{
  if (c === null || c === undefined || c === '' || isNaN(Number(c))) return '';
  return '<span class="badge" title="extractor confidence">conf ' + Number(c).toFixed(2) + '</span>';
}}
// Display names for node ids: TP5 -> "Thm 5", PSP12 -> "Step 12". Display only;
// the stored ids (and every link and hash) keep the extraction's prefixes.
var ID_SHORT = {_json.dumps(_ID_SHORT)};
function dispId(id) {{
  var m = /{_ID_RE.pattern}/.exec(String(id));
  return m ? ID_SHORT[m[1]] + ' ' + m[2] : String(id);
}}
// Link to a node's panel. Folded nodes (steps, equations, proofs) open the
// panel of the box that contains them.
function nodeLink(id, label) {{
  var target = DETAILS[id] ? id : FOLDED_HOST[id];
  if (!target) return esc(label || dispId(id));
  return '<span class="nodelink" data-nid="' + escAttr(target) + '" onclick="showDetail(this.dataset.nid)">' + esc(label || dispId(id)) + '</span>';
}}
function noteBlock(x) {{
  var h = '<div class="note-item"><span class="chip">' + esc(String(x.category || 'note').replace(/_/g, ' ')) + '</span>';
  (x.nodes || []).forEach(function(n, i) {{ h += (i ? ', ' : '') + nodeLink(n); }});
  return h + '<div style="margin-top:3px;">' + esc(x.note || '') + '</div></div>';
}}
function toggleStepKids(el) {{
  var box = el.nextElementSibling;
  if (!box) return;
  var hide = box.style.display !== 'none';
  box.style.display = hide ? 'none' : '';
  el.innerHTML = (hide ? '&#9656; ' : '&#9662; ') + el.innerHTML.replace(/^\\S+\\s/, '');
}}
// Paper-level extraction metadata (paper_style, extraction_comment,
// extraction_notes), shown in the detail panel.
function showPaperInfo() {{
  var panel = document.getElementById("detail-panel");
  if (_lastDetailNode === '__paperinfo__' && panel.className === "open") {{ resetView(); return; }}
  _lastDetailNode = '__paperinfo__';
  var I = PAPER_INFO, h = '<h3 style="margin:0 0 8px;font-size:16px;">Paper info</h3>';
  var rows = [['Model', I.model], ['Effort', I.effort], ['Prompt version', I.prompt_version],
              ['Extracted', I.extraction_date], ['Annotator', I.annotator],
              ['Non-formal rigor tags', I.rigor_nonformal_count]];
  h += '<div class="detail-section" style="font-size:12px;">';
  rows.forEach(function(r) {{ if (r[1] !== undefined) h += '<div><span style="color:#888;">' + r[0] + ':</span> ' + esc(String(r[1])) + '</div>'; }});
  h += '</div>';
  if (I.paper_style && I.paper_style.length) {{
    h += '<div class="detail-section"><h4>Paper style</h4>';
    I.paper_style.forEach(function(s) {{ h += '<span class="chip">' + esc(String(s).replace(/_/g, ' ')) + '</span>'; }});
    h += '</div>';
  }}
  if (I.extraction_comment) h += '<div class="detail-section"><h4>Extractor comment</h4><div style="font-size:13px;">' + esc(String(I.extraction_comment)) + '</div></div>';
  var notes = I.extraction_notes || [];
  h += '<div class="detail-section"><h4>Extraction notes (' + notes.length + ')</h4>';
  notes.forEach(function(x) {{ h += noteBlock(x); }});
  if (!notes.length) h += '<div style="color:#888;font-size:12px;">None recorded.</div>';
  h += '</div>';
  panel.innerHTML = h;
  panel.className = "open";
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([panel]).catch(function(){{}});
}}
function _toggleEdgeSet(btnId, gids) {{
  var btn = document.getElementById(btnId);
  if (!btn || btn.disabled) return;
  var nextShowing = !(btn.dataset.showing === "1");
  btn.dataset.showing = nextShowing ? "1" : "0";
  var el0 = document.querySelector("#svg-container svg");
  if (!el0) return;
  gids.forEach(function(gid) {{
    var el = el0.querySelector('[id="' + gid + '"]');
    if (el) el.style.display = nextShowing ? "" : "none";
  }});
}}
function toggleBackward() {{ _toggleEdgeSet("backward-btn", BACKWARD_EDGE_GIDS); }}
function toggleMention() {{ _toggleEdgeSet("mention-btn", MENTION_EDGE_GIDS); }}
// Nested results: hiding collapses them into the box they are stated in
// (their panel entry stays, under "Contains" / the step that states them).
function toggleNested() {{
  var btn = document.getElementById("nested-btn");
  if (btn.disabled) return;
  var nextShowing = !(btn.dataset.showing === "1");
  btn.dataset.showing = nextShowing ? "1" : "0";
  _setNodeVisibility(NESTED_NODE_IDS, nextShowing);
}}

// Hide ghost elements on load (wait for SVG to render)
window.addEventListener("load", function() {{
  var svgEl = document.querySelector("#svg-container svg");
  if (svgEl) {{
    // Hide all foundation ghost elements (mathlib AND book-derived).
    // The [id^="ghost"] selector covers both "ghost_*" and "ghostbook_*".
    var all = svgEl.querySelectorAll('[id^="ghost"]');
    all.forEach(function(el) {{ el.style.display = "none"; }});
  }}
  // Port #2: Cited Results (External) hidden by default — matches HEAD.
  _setNodeVisibility(EXT_NODE_IDS, false);
}});

var currentZoom = 1.0;
var svgEl = document.querySelector("#svg-container svg");
function toggleImplied() {{ _toggleEdgeSet("implied-btn", IMPLIED_EDGE_GIDS); }}

function toggleBackbone() {{
  var btn = document.getElementById("backbone-btn");
  if (btn.disabled) return;
  // data-showing="1" means "everything is showing", i.e. backbone mode OFF.
  var nextShowing = !(btn.dataset.showing === "1");
  btn.dataset.showing = nextShowing ? "1" : "0";
  _setNodeVisibility(NONBACKBONE_NODE_IDS, nextShowing);
}}

// Semantic zoom. 12pt body text is 16 CSS px at zoom 1 (matplotlib writes px
// and pt at the 96/72 ratio), so below ~0.5 it is too small to read and only
// costs legibility of the structure around it. Hiding it there is what lets a
// 116-inch figure be understood at a glance and read up close, instead of
// forcing a choice between the two.
// Done with a class on the <svg> (see the lod-far CSS rule), not per-element
// style.display, so it never overrides a node that a toggle has hidden.
var LOD_BODY_MIN = 0.5;
var _lodBodyShown = true;

function applyLOD() {{
  if (!svgEl) return;
  var want = currentZoom >= LOD_BODY_MIN;
  if (want === _lodBodyShown) return;        // only touch the DOM on a change
  _lodBodyShown = want;
  svgEl.classList.toggle("lod-far", !want);
  var b = document.getElementById("lod-note");
  if (b) b.textContent = want ? "" : "detail hidden — zoom in to read boxes";
}}

function applyZoom() {{
  if (svgEl) svgEl.style.transform = "scale(" + currentZoom + ")";
  applyLOD();
}}
function zoomIn() {{ currentZoom = Math.min(currentZoom * 1.3, 5.0); applyZoom(); }}
function zoomOut() {{ currentZoom = Math.max(currentZoom / 1.3, 0.02); applyZoom(); }}
// The box, in untransformed layout px, around what is VISIBLE: the hidden
// foundation ghosts (and any toggled-off group) still occupy the drawing, so
// fitting or scrolling to the whole SVG opened large papers on a blank band.
function visibleBox() {{
  var el = svgEl || document.querySelector("#svg-container svg");
  if (!el) return null;
  var s = el.getBoundingClientRect(), z = currentZoom || 1;
  var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  el.querySelectorAll('[id^="node_"]').forEach(function(n) {{
    var r = n.getBoundingClientRect();
    if (!r.width && !r.height) return;          // display:none, or inside a hidden group
    x0 = Math.min(x0, (r.left - s.left) / z); y0 = Math.min(y0, (r.top - s.top) / z);
    x1 = Math.max(x1, (r.right - s.left) / z); y1 = Math.max(y1, (r.bottom - s.top) / z);
  }});
  return x1 > x0 ? {{x: x0, y: y0, w: x1 - x0, h: y1 - y0}} : null;
}}
function scrollToBox(v, pad) {{
  var box = document.getElementById("svg-container");
  if (!box || !v) return;
  box.scrollLeft = Math.max(0, v.x * currentZoom - pad);
  box.scrollTop = Math.max(0, v.y * currentZoom - pad);
}}
function zoomFit() {{
  // Fit what is visible (not the whole drawing, see visibleBox) to the window.
  var box = document.getElementById("svg-container");
  var v = visibleBox();
  if (!box || !v) return;
  var pad = 24;
  currentZoom = Math.max(0.02, Math.min((box.clientWidth - 2 * pad) / v.w,
                                        (box.clientHeight - 2 * pad) / v.h));
  applyZoom();
  scrollToBox(v, pad);
}}

// Fit on load. The zoom floor for the buttons is 0.2, but fitting a large
// graph legitimately needs far less, so applyZoom is driven directly here.
// A graph whose fit would hide the box text opens at a readable zoom on the
// top-left of what is visible instead; "Fit" still gives the overview.
function openView() {{
  zoomFit();
  if (currentZoom < LOD_BODY_MIN) {{
    var v = visibleBox();
    currentZoom = 0.6;
    applyZoom();
    scrollToBox(v, 24);
  }}
}}
window.addEventListener("load", function() {{
  svgEl = svgEl || document.querySelector("#svg-container svg");
  openView();
}});
window.addEventListener("resize", function() {{ openView(); }});

// Mouse wheel zoom on the SVG container
document.getElementById("svg-container").addEventListener("wheel", function(e) {{
  e.preventDefault();
  if (e.deltaY < 0) {{ currentZoom = Math.min(currentZoom * 1.1, 5.0); }}
  else {{ currentZoom = Math.max(currentZoom / 1.1, 0.02); }}
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


def render_paper(data, png_path=None, html_path=None, resolution="standard", show_foundation=False,
                 foundation_path=None):
    """Draw a normalised graph as a PNG and/or the interactive HTML page.
    Returns (nodes, edges, clickable nodes) as far as drawn."""
    import tempfile
    nodes, edges, meta = data.get("nodes", []), data.get("edges", []), data.get("metadata", {})
    n = [0, 0, 0]
    if png_path:
        n[:2] = draw_dag(nodes, edges, str(png_path), metadata=meta, resolution=resolution,
                         show_foundation=show_foundation, foundation_path=foundation_path)[:2]
    if html_path:
        Path(html_path).parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as td:
            # write_png=False: the page embeds the SVG (rasterising cost GBs on big papers);
            # no in-figure title, the page shows it as <h1>
            draw_dag(nodes, edges, f"{td}/g_nolegend.png", metadata=meta, resolution=resolution, show_legend=False,
                     show_foundation=True, foundation_path=foundation_path, write_png=False, show_title=False)
            n[2] = generate_interactive_html(data, f"{td}/g_nolegend.svg", str(html_path))
    return n


def main():
    global LOW_CONF_THRESHOLD
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
    parser.add_argument("--min-confidence", type=float, default=LOW_CONF_THRESHOLD,
                        help=f"Edges below this confidence are faded (default {LOW_CONF_THRESHOLD}).")
    parser.add_argument("--hide-low-confidence", action="store_true",
                        help="Drop edges below --min-confidence entirely instead of fading them.")
    args = parser.parse_args()

    LOW_CONF_THRESHOLD = args.min_confidence
    if args.hide_low_confidence:
        # signal draw_dag to filter rather than fade
        globals()["HIDE_LOW_CONF"] = True

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
        data = _normalize_schema(data, source_path=input_path)

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        if not nodes:
            print(f"  WARNING: No 'nodes' found in {input_path.name}, skipping.")
            continue

        metadata = data.get("metadata", {})

        html_path = output_path.with_suffix(".html") if do_html else None   # next to -o, else next to the input
        n = render_paper(data, output_path if do_png else None, html_path, resolution=args.resolution,
                         show_foundation=args.show_foundation, foundation_path=args.foundation_path)
        print(*([f"  -> {output_path} ({n[0]} nodes, {n[1]} edges)"] if do_png else [])
              + ([f"  -> {html_path} ({n[2]} clickable nodes)"] if do_html else []), sep="\n")

    if len(files) > 1:
        print(f"\nDone: {len(files)} graphs generated.")


if __name__ == "__main__":
    main()
