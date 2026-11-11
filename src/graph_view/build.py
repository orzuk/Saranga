#!/usr/bin/env python3
"""Build the v2 paper-graph viewer: one <id>_new.html per silver JSON.

Usage:
    python3 src/graph_view/build.py <silver json|dir|glob ...> [-o outdir]
                                    [--standalone] [--libs local|cdn]

The page carries the paper's graph as JSON and lays it out in the browser
(Cytoscape.js + ELK layered), so views can be coarse (Overview), filtered
(Results, toggles) or focused (path to the main results, neighbourhood).
See docs/visualization_v2_plan.md. The classic viewer (visualize_annotation.py)
is untouched: its data preparation and side panel are reused from here.

Pages are written as <id>_new.html next to the classic <id>.html and never
overwrite any other file. The JS/CSS libraries sit once in <outdir>/lib/.
"""
import argparse
import copy
import contextlib
import io
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import visualize_annotation as va                                # noqa: E402

# Pinned library releases, fetched once into lib/ (see lib/README.md). The viewer
# drives elkjs itself (no cytoscape-elk adapter): the adapter discards ELK's edge
# routes and swallows layout errors, and the overview needs its own summary edges.
LIBS = [
    ("cytoscape.min.js", "cytoscape 3.34.3",
     "https://cdn.jsdelivr.net/npm/cytoscape@3.34.3/dist/cytoscape.min.js"),
    ("elk.bundled.js", "elkjs 0.9.3",
     "https://cdn.jsdelivr.net/npm/elkjs@0.9.3/lib/elk.bundled.js"),
]
# Standalone pages inline this self-contained MathJax (SVG output, every TeX extension), so the
# formulas render without a network; the other modes load MathJax from the CDN, as the classic pages do.
MATHJAX_LIB = ("tex-svg-full.js", "MathJax 3.2.2 (tex-svg-full)",
               "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg-full.js")
from node_types import PROVABLE as THEOREM_LIKE, ID_SHORT  # noqa: E402
RESULT_TYPES = {"definition", "theorem", "lemma", "proposition", "corollary",
                "claim", "conjecture", "algorithm"}
# Weight of a node type in the importance proxy and the main-result ranking.
TYPE_WEIGHT = {"theorem": 1.0, "proposition": 0.75, "corollary": 0.6,
               "lemma": 0.45, "algorithm": 0.5, "conjecture": 0.5,
               "open_problem": 0.4, "problem": 0.4, "definition": 0.3,
               "claim": 0.2}
MAIN_TYPES = ("theorem", "proposition", "corollary")
SHORT_CHARS = 150            # box text, in characters


# ── Text for the boxes ────────────────────────────────────────────────────
_SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "varrho": "ϱ", "sigma": "σ", "tau": "τ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ",
    "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω", "infty": "∞",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆", "supset": "⊃",
    "supseteq": "⊇", "cup": "∪", "cap": "∩", "times": "×", "cdot": "·",
    "to": "→", "rightarrow": "→", "mapsto": "↦", "Rightarrow": "⇒",
    "Leftrightarrow": "⇔", "iff": "⇔", "implies": "⇒", "forall": "∀",
    "exists": "∃", "partial": "∂", "nabla": "∇", "sum": "Σ", "prod": "Π",
    "int": "∫", "pm": "±", "approx": "≈", "sim": "∼", "equiv": "≡",
    "ldots": "…", "cdots": "⋯", "dots": "…", "emptyset": "∅", "setminus": "∖",
    "circ": "∘", "otimes": "⊗", "oplus": "⊕", "langle": "⟨", "rangle": "⟩",
    "ell": "ℓ", "wedge": "∧", "vee": "∨", "neg": "¬", "mid": "|", "|": "‖",
    "lbrace": "{", "rbrace": "}", "{": "{", "}": "}", "quad": " ", "qquad": " ",
    ",": " ", ";": " ", "!": "", " ": " ", "_": "_", "%": "%", "&": "&",
    "#": "#",
}
_FUNCS = {"log", "ln", "exp", "sin", "cos", "tan", "max", "min", "sup", "inf",
          "lim", "det", "dim", "ker", "deg", "gcd", "Pr", "arg", "liminf",
          "limsup", "Var", "Cov", "Tr", "tr", "rank", "diag", "span", "supp"}
_BB = {"R": "ℝ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "C": "ℂ", "P": "ℙ", "E": "𝔼",
       "F": "𝔽"}


_SUP = dict(zip("0123456789+-=()abcdefghijklmnoprstuvwxyzABDEGHIJKLMNOPRTUVWαβγδεθιφχ*′'",
                "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂᵅᵝᵞᵟᵋᶿᶥᵠᵡ*′′"))
_SUB = dict(zip("0123456789+-=()aehijklmnoprstuvxβγρφχ",
                "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓᵦᵧᵨᵩᵪ"))
_SCRIPT = re.compile(r"([_^])(?:\{([^{}]*)\}|([^\s{}\\]))")


def _scripts(s):
    """`x^{2}` -> x², `W_{m,n}` -> Wₘ,ₙ: Unicode super/subscripts where every
    character has one (commas and spaces pass through); otherwise `^(..)`."""
    def rep(m):
        table = _SUP if m.group(1) == "^" else _SUB
        body = m.group(2) if m.group(2) is not None else m.group(3)
        if body and all(c in table or c in ", " for c in body):
            return "".join(table.get(c, c) for c in body)
        mark = "\x01" if m.group(1) == "^" else "\x02"     # kept out of the next pass
        return mark + (body if len(body) == 1 else "(" + body + ")")
    for _ in range(3):                      # x^{a_{i}}: inner first, then outer
        s = _SCRIPT.sub(rep, s)
    return s.replace("\x01", "^").replace("\x02", "_")


def plain_text(s):
    """A light TeX-to-Unicode rendering for box text (the panel uses MathJax)."""
    s = va._as_text(s)
    s = re.sub(r"\\label\{[^}]*\}|\\(?:begin|end)\{[^}]*\}", " ", s)
    s = re.sub(r"\\texorpdfstring\s*\{((?:[^{}]|\{[^{}]*\})*)\}\s*\{(?:[^{}]|\{[^{}]*\})*\}", r"\1", s)
    s = re.sub(r"\\mathbb\{?([A-Z])\}?", lambda m: _BB.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", s)
    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", s)
    s = re.sub(r"\\(?:text|mathrm|mathbf|mathcal|mathsf|mathit|operatorname|emph|textbf|textit|bm|boldsymbol|mathfrak|mathscr)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)\b", "", s)
    s = re.sub(r"\\([A-Za-z]+|.)", lambda m: _SYMBOLS.get(
        m.group(1), m.group(1) if m.group(1) in _FUNCS else ""), s)
    # sub/superscripts only inside math: label-derived names such as thm_main keep their "_"
    parts = re.split(r"(?<!\\)\$", s)
    s = "".join(_scripts(p) if i % 2 else p for i, p in enumerate(parts))
    s = s.replace("~", " ")
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


_BARE_SCRIPT = re.compile(r"(?<![A-Za-z\\$])([A-Za-z])([_^])(\{[^{}]*\}|\([^()]*\)|[A-Za-z0-9])")


def box_tex(s, n=SHORT_CHARS):
    """Box text that keeps its math, for MathJax in the box (None if there is no math).

    Cut at about n visible characters, never inside $...$; references and labels are
    dropped. A bare script outside math (a name such as `S_N`) is put inside $...$."""
    s = va.latex_macros.display_tex(va._as_text(s))        # anchors, side notes, drawings, text commands
    s = re.sub(r"\\label\{[^}]*\}|\\(?:notag|nonumber)\b", " ", s)

    def inline(m):                                       # display math -> one inline formula
        body = re.sub(r"\\\\(\[[^\]]*\])?|&", " ", m.group(1) or m.group(2) or m.group(3) or "")
        return " $" + re.sub(r"\s+", " ", body).strip() + "$ "
    s = re.sub(r"\\begin\{(?:equation|align|gather|multline|eqnarray|displaymath)\*?\}(.*?)"
               r"\\end\{(?:equation|align|gather|multline|eqnarray|displaymath)\*?\}|\$\$(.*?)\$\$|\\\[(.*?)\\\]",
               inline, s, flags=re.S)
    # text environments go; those that live inside a formula (cases, matrices, aligned) stay for MathJax
    s = re.sub(r"\\(?:begin|end)\{(?!(?:cases|[pbBvV]?matrix|smallmatrix|array|aligned|gathered|split|subarray)\*?\})[^}]*\}", " ", s)
    s = re.sub(r"\\(?:eq|c|C|auto)?ref\{[^}]*\}", "(ref)", s)
    s = re.sub(r"\\cite[pt]?\*?(?:\[[^\]]*\])?\{[^}]*\}", "[cite]", s)
    s = re.sub(r"\\\(|\\\)", "$", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s.count("$") % 2:
        s = s.replace("$", "")
    parts = re.split(r"(?<!\\)\$", s)
    for i in range(0, len(parts), 2):                    # outside math: plain text, bare scripts as math
        bare = []
        t = _BARE_SCRIPT.sub(lambda m: bare.append(m.group(0)) or "\x03%d\x03" % (len(bare) - 1), parts[i])
        if "\\" in t or "{" in t:                       # keep the spaces around the math
            t = (" " if t[:1].isspace() else "") + plain_text(t) + (" " if t[-1:].isspace() else "")
        parts[i] = re.sub("\x03(\\d+)\x03", lambda m: "$" + bare[int(m.group(1))] + "$", t)
    s = "$".join(parts)
    if "$" not in s:
        return None
    out, vis, inside = [], 0, False
    for tok in re.split(r"((?<!\\)\$)", s):
        if tok == "$":
            inside = not inside
            out.append(tok)
            continue
        if not inside and vis + len(tok) > n:
            cut = tok[:max(0, n - vis)].rsplit(" ", 1)[0]
            out.append(cut.rstrip(" ,;:") + "…")
            return "".join(out)
        vis += len(tok) if not inside else max(1, len(tok) // 3)
        out.append(tok)
        if vis > n and not inside:
            return "".join(out) + "…"
    return "".join(out)


def shorten(s, n=SHORT_CHARS):
    """Cut at a word boundary, with an ellipsis."""
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return (cut if len(cut) > n // 2 else s[:n]).rstrip(" ,;:") + "…"


# ── Sections ──────────────────────────────────────────────────────────────
_SEC_RE = re.compile(r"\s*((?:\d+|[A-Z])(?:\.\d+)*)\.?(?:\s+|$)(.*)")


def section_keys(sec):
    """(top key, sub key, title) for a section string like '3.1 Setup'."""
    sec = va._as_text(sec).strip()
    m = _SEC_RE.match(sec)
    if not m:
        return (sec or "(no section)"), "", sec
    parts = m.group(1).split(".")
    return parts[0], ".".join(parts[:2]) if len(parts) > 1 else "", sec


def build_sections(base_nodes):
    """Top-level sections (and their subsections) in paper order."""
    tops, subs, first = {}, {}, {}
    for i, n in enumerate(base_nodes):
        top, sub, title = section_keys(n.get("section"))
        first.setdefault(top, i)
        t = tops.setdefault(top, {"id": "sec:" + top, "key": top, "title": "",
                                  "subs": [], "nodes": []})
        num = _SEC_RE.match(title)
        if num and num.group(1) == top and not t["title"]:
            t["title"] = title
        elif not num and not t["title"]:
            t["title"] = title or "(no section)"
        if sub:
            if sub not in subs:
                subs[sub] = {"id": "sec:" + sub, "key": sub, "title": title,
                             "parent": t["id"], "nodes": []}
                t["subs"].append(subs[sub]["id"])
            subs[sub]["nodes"].append(n["id"])
        t["nodes"].append(n["id"])
    out = []
    for top in sorted(tops, key=lambda k: first[k]):
        t = tops[top]
        if not t["title"]:
            t["title"] = ("Section " if top.isdigit() else "Appendix ") + top
        out.append(t)
    for s in list(tops.values()) + list(subs.values()):
        s["title"] = shorten(plain_text(s["title"]), 70)
    return out, list(subs.values())


# ── Importance and main results ───────────────────────────────────────────
def numbered_ids(nodes, metadata):
    """Nodes the paper numbers (a \\label with a number, or a label field)."""
    out = {n["id"] for n in nodes if n.get("label")}
    labels = (metadata or {}).get("labels") or {}
    if isinstance(labels, dict):
        for v in labels.values():
            if isinstance(v, dict) and v.get("node") and v.get("number"):
                out.add(v["node"])
    return out


def importance_and_main(base_nodes, layout_edges, numbered):
    """Importance 1-5 per node and the main-result candidates.

    `importance` from the JSON wins when present. Otherwise the proxy is how
    much of the paper builds on the node (its descendants), plus a weight for
    the node type and for being numbered. Main results: theorem-like paper
    results that nothing else uses (examples and remarks aside), ranked by
    type, by how much they build on, and by number. Used only by corollaries,
    examples or remarks still counts as unused; a theorem-like result whose
    name says "main" is always a candidate.
    """
    ids = [n["id"] for n in base_nodes]
    by_id = {n["id"]: n for n in base_nodes}
    kids, pars = defaultdict(set), defaultdict(set)
    for e in layout_edges:
        kids[e["source"]].add(e["target"])
        pars[e["target"]].add(e["source"])

    def reach(start, nbrs):
        seen, stack = set(), [start]
        while stack:
            for m in nbrs[stack.pop()]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        seen.discard(start)
        return seen

    desc = {i: reach(i, kids) for i in ids}
    raw = {}
    for i in ids:
        n = by_id[i]
        r = math.log2(1 + len(desc[i])) + 1.5 * TYPE_WEIGHT.get(n.get("type"), 0.1)
        r += 0.75 if i in numbered else 0.0
        if n.get("origin") == "external":
            r *= 0.8
        raw[i] = r

    explicit = {i for i in ids if by_id[i].get("main") is True
                or "main_result" in [str(t) for t in va._as_list(by_id[i].get("tags"))]
                or (by_id[i].get("type") in THEOREM_LIKE and by_id[i].get("origin") != "external"
                    and re.search(r"\bmain\b", va._as_text(by_id[i].get("name")), re.I))}
    # What may use a main result without making it a step to something else:
    # its own corollaries, and examples and remarks.
    aux = {"example", "remark", "corollary"}
    cands = []
    for i in ids:
        n = by_id[i]
        if n.get("type") not in THEOREM_LIKE or n.get("origin") == "external" or n.get("inside"):
            continue
        if any(by_id[k].get("type") not in aux for k in kids[i] if k in by_id):
            continue
        anc = len(reach(i, pars))
        score = (2.0 * TYPE_WEIGHT.get(n.get("type"), 0.1) + math.log2(1 + anc)
                 + (0.75 if i in numbered else 0.0))
        cands.append((score, i))
    if any(by_id[i].get("type") in MAIN_TYPES for _, i in cands):
        cands = [c for c in cands if by_id[c[1]].get("type") in MAIN_TYPES]
    cands.sort(key=lambda c: (-c[0], va._natural_key(c[1])))
    main = [i for s, i in cands[:5] if s >= 0.6 * cands[0][0]] if cands else []
    main = sorted(set(main) | explicit, key=ids.index)

    top = max(raw.values()) if raw else 1.0
    imp = {}
    for i in ids:
        given = by_id[i].get("importance")
        if isinstance(given, (int, float)) and not isinstance(given, bool):
            imp[i] = max(1.0, min(5.0, float(given)))
        else:
            imp[i] = round(1 + 4 * raw[i] / top, 1) if top > 0 else 1.0
        if i in main:
            imp[i] = 5.0
    return imp, main, {i: len(desc[i]) for i in ids}


# ── Classic side panel, reused as-is ──────────────────────────────────────
_PANEL_FUNCS = ("showDetail", "resetView", "toggleOrphans", "showGhostDetail",
                "toggleEqPanel", "esc", "escAttr", "eqTex", "rigorBadge", "confBadge",
                "nodeLink", "noteBlock", "toggleStepKids", "showPaperInfo", "defGloss", "toggleGhostDefs", "listItem")


def _js_function(src, name):
    """Source of `function name(...) {...}` in src.

    Braces are matched past string literals, regex literals and // comments.
    """
    m = re.search(r"^function %s\s*\(" % re.escape(name), src, re.M)
    if not m:
        return ""
    i = src.index("{", m.end())
    depth, q, prev = 0, None, ""
    while i < len(src):
        c = src[i]
        if q:
            if c == "\\":
                i += 1
            elif c == q:
                q, prev = None, c
        elif c in "'\"":
            q = c
        elif c == "/" and src[i + 1] == "/":
            i = src.index("\n", i)
            continue
        elif c == "/" and prev in "(,=:[!&|?{};":
            q = "/"                       # a regex literal, ends at the next unescaped /
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():i + 1]
        if not c.isspace() and not q:
            prev = c
        i += 1
    return ""


def classic_panel(data, stem):
    """The classic page's panel data, panel JS, CSS and MathJax head.

    generate_interactive_html is run on an empty figure into a scratch file:
    that yields exactly the classic DETAILS (statement render source, proofs,
    steps, equations, foundation links), PAPER_INFO and the edge sets
    (backward, mention, implied, low confidence) without redoing any of it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "empty.svg"
        svg.write_text('<svg width="1pt" height="1pt"></svg>', encoding="utf-8")
        page = Path(tmp) / (stem + ".html")
        with contextlib.redirect_stdout(io.StringIO()):
            va.generate_interactive_html(data, str(svg), str(page))
        html = page.read_text(encoding="utf-8")
    jsvars = {}
    for m in re.finditer(r"^var ([A-Z][A-Z0-9_]*) = (.*);$", html, re.M):
        try:
            jsvars[m.group(1)] = json.loads(m.group(2))
        except ValueError:
            pass
    script = html[html.index("var DETAILS"):]
    bodies = {f: _js_function(script, f) for f in _PANEL_FUNCS}
    missing = [f for f, b in bodies.items() if not b]
    if missing:
        raise RuntimeError("classic panel functions not found: %s" % ", ".join(missing))
    funcs = "\n".join(bodies.values())
    funcs = funcs.replace("function showDetail(", "function classicShowDetail(", 1)
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    head = re.search(r"(<script>MathJax = .*?</script>\s*<script src=[^>]*></script>)", html, re.S)
    return jsvars, funcs, css, head.group(1) if head else ""


# ── One paper ─────────────────────────────────────────────────────────────
def _gid(s, t):
    return "edge_%s__to__%s" % (str(s).replace(" ", "_"), str(t).replace(" ", "_"))


def _book_registry():
    """The foundation books registry rows (id, title, prepared source folder)."""
    try:
        reg = json.loads((Path(__file__).resolve().parents[1] / "structured_math" / "books" /
                          "foundation_books.json").read_text(encoding="utf-8"))
        rows = reg.get("books") if isinstance(reg, dict) else reg
        return [b for b in rows or [] if isinstance(b, dict) and b.get("id")]
    except Exception:
        return []


def _books_root():
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from config import FOUNDATION_DIR
        return Path(FOUNDATION_DIR) / "books_v7b"
    except Exception:
        return None


_BOOK_NODES, _BOOK_MACROS = {}, {}


def _book_node(book, nid):
    """A node of an assembled foundation book (full statement, genus, differentia)."""
    if book not in _BOOK_NODES:
        _BOOK_NODES[book] = {}
        root = _books_root()
        f = root / "assembled" / f"{book}.json" if root else None
        if f and f.exists():
            _BOOK_NODES[book] = {n["id"]: n for n in json.loads(f.read_text(encoding="utf-8")).get("nodes", [])}
    return _BOOK_NODES[book].get(nid)


def _book_macros(book, nid):
    """The macros a book chapter defines (its prepared LaTeX preamble), read like a paper's."""
    if book == "proofwiki":
        return va.latex_macros.PROOFWIKI_MACROS
    ch = nid.split(":")[0] if ":" in nid else ""
    key = (book, ch)
    if key not in _BOOK_MACROS:
        root = _books_root()
        row = next((b for b in _book_registry() if b["id"] == book), {})
        pd, src_dir = row.get("prepared"), row.get("src")
        macros = {}
        # the book's own source macros (a PreTeXt macros.ptx / macros.xml), then the first chapter's
        # preamble (a LaTeX book's \newcommands), then this chapter's: later definitions win
        files = []
        if src_dir:
            sd = Path(__file__).resolve().parents[2] / "textbooks" / "source" / src_dir
            files += sorted(sd.glob("**/macros.ptx")) + sorted(sd.glob("**/macros.xml")) if sd.exists() else []
        if root and pd:
            files += [root / "prepared" / pd / c for c in ("ch01.tex", f"{ch}.tex") if c != "ch01.tex" or ch != "ch01"]
        for f in files:
            if f.exists():
                # the whole file: a prepared chapter may define its macros after \begin{document}
                macros.update(va.latex_macros.read_definitions(f.read_text(encoding="utf-8", errors="replace")))
        _BOOK_MACROS[key] = va.latex_macros.renderable(macros)
    return _BOOK_MACROS[key]


def _list_field(v):
    """genus / differentia as the assembled books store them (a list, a string, or a list printed as a string)."""
    if isinstance(v, list):
        return [str(x) for x in v if x]
    v = str(v or "").strip()
    if v.startswith("[") and v.endswith("]"):
        try:
            import ast
            return [str(x) for x in ast.literal_eval(v) if x]
        except Exception:
            pass
    return [v] if v else []


def _ods_code(text):
    """Open Data Structures writes code tokens as #i#, #n#\\times#n#: inside math they become
    \\mathtt, outside math a run of them is typeset as math."""
    if "#" not in text:
        return text
    text = re.sub(r"#([^#$]{1,40})#", r"\\mathtt{\1}", text)
    run = r"\\mathtt\{[^}]*\}(?:(?:\\times|\\cdot|\^|_|[0-9+\-*/=])+\\mathtt\{[^}]*\})*"
    return va.latex_macros._outside_math(text, lambda u: re.sub(run, lambda m: "$" + m.group(0) + "$", u))


_CONTEXT_PHRASES = re.compile(r"\b(in the following|in this (section|chapter|book|exercise)|exercises?|we (will|shall|now)|"
                              r"recall|as (we )?(saw|defined)|presented as|can be represented)\b", re.I)


def def_rank(d, concept_name, terms):
    """How good a book's definition is as the one to show first: self-contained, readable, and
    about the concept itself. Higher is better. Favours a statement whose subject is the bare
    term ("A submatrix of A is ..." over "the submatrix A(i|j) is ..."), a recovered genus,
    a moderate length; penalises leftover markup, context-dependent phrasing, and a very long
    or very short text."""
    words = re.sub(r"\$[^$]*\$", " MATH ", d["statement"] or "")      # a formula in the subject breaks the pattern
    words = re.sub(r"\s+", " ", words).strip()
    names = [t for t in {concept_name, d.get("name") or ""} | set(terms or []) if t]
    score, defined = 0.0, False
    low = words.lower()
    for t in names:
        tt = re.escape(t.strip().lower())
        # "A submatrix of A is ...", "The absolute value or modulus of z is ..."
        if re.search(r"\b(?:an?|the)\s+" + tt + r"s?\b\s+(?:(?:or|and)\s+\w+\s+)?(?:of\b[^.,;]{0,40})?\b(?:is|are|means)\b", low):
            score += 3; defined = True; break
        if re.search(r"\b" + tt + r"s?\b", low):
            score = max(score, 1)
            # a definition by formula or naming: "we define |x|, called the absolute value of x, by ..."
            if re.search(r"\b(?:define[ds]?|denoted?|called|is said to be|:=)\b", low):
                score += 2; defined = True; break
    words = words.replace(" MATH ", " ")
    if d.get("genus"):
        score += 1
    n = len(d["statement"] or "")
    if n > 600: score -= 2
    elif n > 350: score -= 1
    elif n < 30: score -= 1
    if re.search(r"#|\\marginnote|\\amp|\\key\b|\\protect|\\(?:begin|end)\{(?:itemize|enumerate|tabular)", d["statement"] or ""):
        score -= 2
    if _CONTEXT_PHRASES.search(words):            # tied to its surroundings ("In the following exercises, ...")
        score -= 2
    if d["statement"].count("$") > 24:              # a wall of formulas
        score -= 1
    return score, defined


def concept_defs(concept, titles, terms=None):
    """The textbook definitions a concept is made of, one per book, rendered as the panel
    renders a paper statement: the book's macros expanded, text commands to words, math kept
    for MathJax (ProofWiki: its markup removed and its macros expanded). A member whose page
    only transcludes sub-definitions (no text) is left out."""
    defs, seen = [], set()
    for m in concept.get("members", []):
        book, nid = m.get("book") or "", m.get("node") or ""
        if book in seen:
            continue
        n = _book_node(book, nid) or {}
        text = n.get("raw_latex") or n.get("statement") or m.get("statement") or ""
        if book == "proofwiki":
            text = va.latex_macros.wiki_tex(text)
        text = _ods_code(text)
        text = va.latex_macros.display_tex(va.latex_macros.normalize_for_mathtext(text, _book_macros(book, nid)))
        text = re.sub(r"\s+", " ", text or "").strip()
        if not re.search(r"[A-Za-z]{3}", re.sub(r"\$[^$]*\$", "", text)):
            continue
        seen.add(book)
        genus = _list_field(n.get("genus"))
        defs.append({"book": titles.get(book, book), "where": nid, "name": m.get("name") or n.get("name") or "",
                     "statement": text, "genus": genus[0] if genus else "",
                     "differentia": _list_field(n.get("differentia"))})
    # best first: the panel shows the first and keeps the rest behind "show all"
    for d in defs:
        d["rank"], defined = def_rank(d, concept.get("name") or "", terms)
        if not defined:                   # the sentence uses the term rather than defining it
            d["weak"] = True
    return sorted(defs, key=lambda d: (-d["rank"], len(d["statement"])))     # ties: the shorter one


def book_titles():
    """Book id -> short title, from the foundation books registry (ProofWiki added)."""
    out = {"proofwiki": "ProofWiki"}
    try:
        reg = json.loads((Path(__file__).resolve().parents[1] / "structured_math" / "books" /
                          "foundation_books.json").read_text(encoding="utf-8"))
        rows = reg.get("books") if isinstance(reg, dict) else reg
        for b in rows or []:
            if isinstance(b, dict) and b.get("id"):
                out[b["id"]] = b.get("title") or b["id"]
    except Exception:
        pass
    return out


def grounding_in_json(data):
    """The paper's book grounding when it is written in the JSON (bundle_t3 --grounding copies the
    layer's edges in: node -> concept id, with term, basis, confidence and concept_name), as the row
    the layer would give; None when the JSON holds no such edge."""
    edges = [e for e in data.get("edges", []) or []
             if e.get("type") == "grounded_to" and "basis" in e]
    if not edges:
        return None
    return {"paper_id": (data.get("metadata") or {}).get("paper_id", ""), "edges": edges}


def grounding_ghosts(grounding, nodes, base_ids, concepts_path=None):
    """Foundation boxes from a grounding layer (ground_papers output), one per concept.

    `grounding` is the paper's row of the layer: {"paper_id", "edges": [{source,
    target (concept id), term, basis, confidence, concept_name?}]}. The concept
    records (name, kind, and the textbook definitions that make up the concept,
    each with its book) are read from concepts.json (books_v7b). A source that
    is not a base node (a proof, a step, an equation) is lifted to the result it
    belongs to, as the classic panel does for name-linker matches.
    Returns (ghost_list, ghost_refs, ghost_defs): the viewer's list, the panel's
    name->refs, and the panel's name->{id, kind, terms, defs:[{book, where, statement}]}.
    """
    by = {n["id"]: n for n in nodes}
    names, recs = {}, {}
    need = {e["target"] for e in grounding.get("edges", [])}
    if need:
        cp = Path(concepts_path) if concepts_path else None
        if cp is None:
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from config import FOUNDATION_DIR
                cp = Path(FOUNDATION_DIR) / "books_v7b" / "concepts.json"
            except Exception:
                cp = None
        if cp and cp.exists():
            for c in json.loads(cp.read_text(encoding="utf-8")).get("concepts", []):
                if c["id"] in need:
                    names[c["id"]] = c.get("name") or c["id"]
                    recs[c["id"]] = c

    def lift(i):
        seen = set()
        while i in by and i not in base_ids and i not in seen:
            seen.add(i)
            n = by[i]
            pv = n.get("proves")
            if isinstance(pv, (list, tuple)):
                pv = pv[0] if pv else None
            i = n.get("parent_id") or n.get("parent_proof") or pv
        return i if i in base_ids else None

    refs, terms, cid = defaultdict(set), defaultdict(set), {}
    for e in grounding.get("edges", []):
        t = lift(e["source"])
        if not t:
            continue
        nm = e.get("concept_name") or names.get(e["target"]) or e["target"]
        refs[nm].add(t)
        cid.setdefault(nm, e["target"])
        if e.get("term"):
            terms[nm].add(e["term"])
    order = sorted(refs, key=lambda k: (-len(refs[k]), k))
    ghost_list = [{"name": k, "refs": sorted(refs[k]), "book": 1,
                   "terms": sorted(terms[k])} for k in order]
    titles = book_titles()
    ghost_defs = {}
    for k in order:
        c = recs.get(cid.get(k)) or {}
        ghost_defs[k] = {"id": cid.get(k, ""), "kind": c.get("kind") or "", "terms": sorted(terms[k]),
                         "books": [titles.get(b, b) for b in c.get("books", [])], "defs": concept_defs(c, titles, terms[k])}
    return ghost_list, {k: sorted(refs[k]) for k in order}, ghost_defs


def paper_model(data, stem, grounding=None, concepts_path=None):
    """The JSON object a v2 page embeds, plus the classic panel pieces.

    With `grounding` (the paper's row of a ground_papers layer), the Foundations
    boxes (the Foundations toggle, off by default as on every page) are its
    concepts instead of the classic name-linker matches.
    """
    nodes = data.get("nodes", []) or []
    edges = data.get("edges", []) or []
    if grounding is None:
        grounding = grounding_in_json(data)
    va.NAME_LINKER = grounding is None       # the old name linker only where no book grounding exists
    jsvars, funcs, css, mathjax = classic_panel(copy.deepcopy(data), stem)
    metadata = data.get("metadata", {}) or {}
    base_nodes, base_edges, step_chains, _eq, _orph = va._classify_and_merge(
        copy.deepcopy(nodes), edges)
    base_ids = {n["id"] for n in base_nodes}

    back = set(jsvars.get("BACKWARD_EDGE_GIDS", []))
    mention = set(jsvars.get("MENTION_EDGE_GIDS", []))
    implied = set(jsvars.get("IMPLIED_EDGE_GIDS", []))
    out_edges, layout_edges = [], []
    for e in base_edges:
        g = _gid(e["source"], e["target"])
        try:
            conf = float(e.get("confidence", 1.0) or 1.0)
        except (TypeError, ValueError):
            conf = 1.0
        x = {"s": e["source"], "t": e["target"], "type": str(e.get("type") or "uses"),
             "conf": conf}
        for k, on in (("back", g in back), ("mention", e.get("mention") or g in mention), ("both", e.get("equivalence")),
                      ("implied", g in implied), ("low", conf < va.LOW_CONF_THRESHOLD),
                      ("lean", e.get("lean")), ("mismatch", e.get("mismatch"))):
            if on:
                x[k] = 1
        out_edges.append(x)
        if not (x.get("back") or x.get("mention")):
            layout_edges.append(e)

    numbered = numbered_ids(nodes, metadata)
    imp, main, ndesc = importance_and_main(base_nodes, layout_edges, numbered)
    sections, subsections = build_sections(base_nodes)
    top_of = {i: s["id"] for s in sections for i in s["nodes"]}
    sub_of = {i: s["id"] for s in subsections for i in s["nodes"]}

    # Proof steps, for opening a result's proof in place (one level at a time).
    proof_map = {n["id"]: (n["proves"][0] if isinstance(n.get("proves"), list) else n.get("proves"))
                 for n in nodes if n.get("type") == "proof" and n.get("proves")}
    steps, step_ids = {}, set()
    for host, chain in step_chains.items():
        if host not in base_ids:
            continue
        lst = []
        for s in chain:
            name = va._as_text(s.get("name"))
            body = s.get("statement_short") or s.get("statement_clean") or s.get("statement")
            lst.append({"id": s["id"], "name": shorten(plain_text(name), 60),
                        "short": shorten(plain_text(body), 110),
                        "parent": s.get("parent_step") or "",
                        "type": s.get("type") or "proof_step"})
            step_ids.add(s["id"])
        steps[host] = lst
    step_edges, seen = [], set()

    def _end(x):
        if x in step_ids or x in base_ids:
            return x
        return proof_map.get(x) if proof_map.get(x) in base_ids else None
    for e in edges:
        s, t = _end(e.get("source")), _end(e.get("target"))
        if not s or not t or s == t or (s not in step_ids and t not in step_ids):
            continue
        if (s, t) in seen:
            continue
        seen.add((s, t))
        x = {"s": s, "t": t, "type": str(e.get("type") or "uses")}
        if e.get("backward"):
            x["back"] = 1
        if e.get("mention"):
            x["mention"] = 1
        step_edges.append(x)

    out_nodes = []
    for n in base_nodes:
        i = n["id"]
        body = n.get("statement_short") or n.get("statement_clean") or n.get("statement")
        out_nodes.append({
            "id": i, "type": n.get("type", ""),
            "name": plain_text(n.get("name") or ""),
            "short": shorten(plain_text(body)),
            "top": top_of.get(i, ""), "sub": sub_of.get(i, ""),
            "inside": n.get("inside", ""), "origin": n.get("origin", "paper"),
            "conf": n.get("confidence"), "imp": imp[i], "desc": ndesc[i],
            "num": str(n.get("number") or ""),            # the paper's own number (Theorem 1.1), shown in the box head
            "res": 1 if (n.get("type") in RESULT_TYPES and not n.get("inside")) else 0,
            "nsteps": len(steps.get(i, [])),
        })
        if isinstance(n.get("pos"), list) and len(n["pos"]) >= 2:   # the box's place in the authors' drawing
            out_nodes[-1]["pos"] = n["pos"]
        if isinstance(n.get("lean"), dict):                          # a Lean blueprint statement (merge_lean.py)
            out_nodes[-1]["lean"] = n["lean"].get("status") or "node"
        tex = box_tex(va._statement_render_source(n) or body)     # raw_latex when it has TeX: statement may be de-TeX'd
        tex_name = box_tex(n.get("name") or "", 80)
        if tex or tex_name:
            out_nodes[-1]["tex"] = tex or shorten(plain_text(body))
            out_nodes[-1]["tex_name"] = tex_name or plain_text(n.get("name") or "")

    ghosts = jsvars.get("GHOSTS", {}) or {}
    book = set(jsvars.get("GHOST_BOOK_INDICES", []))
    ghost_list = [{"name": g, "refs": [r for r in refs if r in base_ids],
                   "book": 1 if gi in book else 0}
                  for gi, (g, refs) in enumerate(sorted(ghosts.items()))]
    grounded = False
    if grounding is not None:
        ghost_list, ghost_refs, ghost_defs = grounding_ghosts(grounding, nodes, base_ids, concepts_path)
        jsvars["GHOSTS"] = ghost_refs
        jsvars["GHOST_DEFS"] = ghost_defs
        grounded = True

    md = metadata
    title = md.get("title") or stem
    aid = str(md.get("arxiv_id") or "").strip()
    if not aid and re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", stem):
        aid = stem
    n_top = len(out_nodes)
    model = {
        "id": stem, "title": title, "arxiv": aid,
        "n_top": n_top, "level": "full",         # every page opens at Full; Overview stays one click away
        "colors": va.NODE_COLORS, "default_color": va.DEFAULT_COLOR,
        "edge_colors": va.EDGE_COLORS, "default_edge_color": va.DEFAULT_EDGE_COLOR,
        "low_conf": va.LOW_CONF_THRESHOLD,
        "sections": sections, "subsections": subsections,
        "nodes": out_nodes, "edges": out_edges, "steps": steps,
        "step_edges": step_edges, "main": main, "ghosts": ghost_list, "grounded": grounded,
        "n_notes": len((jsvars.get("PAPER_INFO") or {}).get("extraction_notes") or []),
    }
    # The panel data without its duplicates (viewer.js restores them):
    # step_info aliases steps, and statement_clean / statement_render often
    # repeat the statement. About a third of the page on the largest papers.
    details = jsvars.get("DETAILS") or {}
    for d in details.values():
        d.pop("step_info", None)
        nm = box_tex(d.get("name") or "", 200)           # a bare `S_N` in a name: typeset it
        if nm and "$" not in (d.get("name") or ""):
            d["name"] = nm
        for k in ("statement_clean", "statement_render"):
            if d.get(k) == d.get("statement"):
                d.pop(k, None)
    panel_vars = {k: jsvars.get(k) for k in ("DETAILS", "ORPHANS", "GHOSTS",
                                             "PAPER_INFO", "FOLDED_HOST")} | {"ID_SHORT": ID_SHORT}
    if grounded:
        panel_vars["GHOST_DEFS"] = jsvars.get("GHOST_DEFS") or {}
    return model, panel_vars, funcs, css, mathjax


# ── Page ──────────────────────────────────────────────────────────────────
def _script_json(obj):
    """JSON safe inside a <script> element."""
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")


def lib_tags(libs_mode, lib_dir):
    """<script> tags for the libraries: relative lib/ paths, CDN, or inlined."""
    out = []
    for fname, _ver, url in LIBS:
        if libs_mode == "standalone":
            src = (lib_dir / fname).read_text(encoding="utf-8").replace("</script", "<\\/script")
            out.append("<script>%s</script>" % src)
        elif libs_mode == "cdn":
            out.append('<script src="%s"></script>' % url)
        else:
            out.append('<script src="lib/%s"></script>' % fname)
    return "\n".join(out)


def render_page(model, panel_vars, funcs, css, mathjax, libs_mode, lib_dir):
    """The page: template + libraries + the paper's JSON + viewer."""
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    aid = model["arxiv"]
    links = ""
    if aid:
        u = "https://arxiv.org/%s/" + escape(aid)
        links = ('<span class="aid">%s</span><a href="%s" target="_blank" rel="noopener">abstract</a>'
                 '<a href="%s" target="_blank" rel="noopener">PDF</a>'
                 % (escape(aid), u % "abs", u % "pdf"))
    panel_js = "".join("var %s = %s;\n" % (k, _script_json(v)) for k, v in panel_vars.items())
    if libs_mode == "standalone":                                   # MathJax inline: formulas without a network
        mjp = Path(lib_dir) / MATHJAX_LIB[0]
        if not mjp.exists():
            mjp = ensure_lib(Path.home() / ".cache" / "saranga_graph_view" / "lib") / MATHJAX_LIB[0]
        mj = mjp.read_text(encoding="utf-8").replace("</script", "<\\/script")
        mathjax = re.sub(r'<script src="[^"]*mathjax[^"]*"></script>', lambda m: "<script>" + mj + "</script>", mathjax)
    rep = {
        "{{TITLE}}": escape(model["title"]),
        "{{MATHJAX}}": mathjax,
        "{{CLASSIC_CSS}}": css,
        "{{VIEWER_CSS}}": (HERE / "viewer.css").read_text(encoding="utf-8"),
        "{{SRCLINKS}}": links,
        "{{LIBS}}": lib_tags(libs_mode, lib_dir),
        "{{GRAPH_JSON}}": _script_json(model),
        "{{PANEL_JS}}": panel_js + funcs,
        "{{VIEWER_JS}}": (HERE / "viewer.js").read_text(encoding="utf-8"),
    }
    # One pass, so text inserted for one placeholder is never rescanned.
    return re.sub(r"\{\{[A-Z_]+\}\}", lambda m: rep.get(m.group(0), m.group(0)), tpl)


def ensure_lib(lib_dir, src_dir=None):
    """Make sure lib_dir holds the pinned libraries (copied, or downloaded once)."""
    lib_dir.mkdir(parents=True, exist_ok=True)
    for fname, ver, url in LIBS + [MATHJAX_LIB]:
        dst = lib_dir / fname
        if dst.exists():
            continue
        if src_dir and (Path(src_dir) / fname).exists():
            shutil.copyfile(Path(src_dir) / fname, dst)
            continue
        import urllib.request
        print("  downloading %s (%s)" % (fname, ver))
        with urllib.request.urlopen(url, timeout=60) as r:
            dst.write_bytes(r.read())
    readme = lib_dir / "README.md"
    if not readme.exists():
        rows = "\n".join("| `%s` | %s | %s |" % (f, v, u) for f, v, u in LIBS)
        readme.write_text(
            "# Libraries for the v2 graph pages (`*_new.html`)\n\n"
            "Pinned releases, downloaded once by `src/graph_view/build.py`; every page in\n"
            "this folder loads them by relative path (`lib/...`).\n\n"
            "| file | version | source |\n|---|---|---|\n%s\n\n"
            "The viewer calls elkjs directly (to keep ELK's edge routes and catch layout\n"
            "errors) and builds the overview's collapsed groups and summary edges itself.\n"
            "MathJax 3 is loaded from jsdelivr, as in the classic pages.\n" % rows,
            encoding="utf-8")
    return lib_dir


def lib_dir_for(out_dir, mode, src_dir=None):
    """Where the libraries come from: <out>/lib (local), a cache (standalone)."""
    if mode == "local":
        return ensure_lib(out_dir / "lib", src_dir)
    if mode == "standalone":
        if (out_dir / "lib" / LIBS[0][0]).exists():
            return out_dir / "lib"
        return ensure_lib(Path(src_dir) if src_dir else
                          Path.home() / ".cache" / "saranga_graph_view" / "lib")
    return None                                           # cdn: nothing local


def target_path(out_dir, stem, suffix="_new"):
    """<stem><suffix>.html, refusing any existing file that is not a v2 page."""
    p = out_dir / (stem + suffix + ".html")
    if p.exists():
        head = p.read_text(encoding="utf-8", errors="replace")[:4000]
        if 'name="generator" content="saranga-graph-view-v2"' not in head:
            raise SystemExit("refusing to overwrite %s: not a v2 page" % p)
    return p


def with_tex_macros(data, tex_path):
    """The paper's \\newcommands (read from its source) resolved in every node text, as the
    classic page does when the JSON carries metadata.macros; the metadata gets them too, so
    the panel's own pass sees the same table."""
    if not tex_path.exists():
        print("  tex source not found: %s" % tex_path)
        return data
    macros = va.latex_macros.renderable(va.latex_macros.read_definitions(
        tex_path.read_text(encoding="utf-8", errors="replace")))
    md = data.setdefault("metadata", {})
    if not md.get("macros"):
        md["macros"] = macros
        data["nodes"] = va._resolve_nodes(data["nodes"], macros)
    return data


def load_grounding(spec, stem, data):
    """The paper's grounding row for --grounding (see main); None if not found."""
    path = Path(spec.replace("{stem}", stem))
    if not path.exists():
        print("  grounding file not found: %s" % path)
        return None
    if path.suffix == ".jsonl":
        ids = {stem, str((data.get("metadata") or {}).get("arxiv_id") or "")}
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("paper_id") in ids:
                    return row
        print("  no grounding row for %s in %s" % (stem, path))
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="+", help="silver JSON file(s), directories or globs")
    ap.add_argument("-o", "--outdir", default=None,
                    help="output folder (default: <input dir>/graphs)")
    ap.add_argument("--suffix", default="_new",
                    help="page name suffix: <id><suffix>.html (e.g. _rules for rule-based graphs)")
    ap.add_argument("--tex", default=None,
                    help="the paper's LaTeX source ({stem} allowed): its \\newcommands are expanded in boxes "
                         "and panel when the JSON carries no macros")
    ap.add_argument("--standalone", action="store_true",
                    help="inline the libraries: one self-contained file per paper")
    ap.add_argument("--libs", choices=["local", "cdn"],
                    default="cdn" if os.environ.get("SARANGA_LIBS_CDN") else "local",
                    help="load libraries from lib/ (default) or from the CDN (default if "
                         "SARANGA_LIBS_CDN is set, as on the public Space: no lib copy)")
    ap.add_argument("--lib-source", default=None,
                    help="folder holding already-downloaded library files")
    ap.add_argument("--grounding", default=None,
                    help="grounding of the paper(s) in the foundation concept layer: a JSON row of "
                         "ground_papers ({paper_id, edges}), a .jsonl layer file (the row whose paper_id "
                         "is the input's stem or arxiv id), or a path with {stem}; the Foundations boxes "
                         "(the Foundations toggle) then show its concepts")
    ap.add_argument("--concepts", default=None,
                    help="concepts.json naming the grounding's concept ids "
                         "(default: <FOUNDATION_DIR>/books_v7b/concepts.json)")
    args = ap.parse_args()

    files = va.resolve_paths(args.inputs)
    if not files:
        sys.exit("no JSON files found")
    n_ok, t0 = 0, time.time()
    for k, path in enumerate(files):
        out_dir = Path(args.outdir) if args.outdir else path.parent / "graphs"
        out_dir.mkdir(parents=True, exist_ok=True)
        mode = "standalone" if args.standalone else args.libs
        lib_dir = lib_dir_for(out_dir, mode, args.lib_source)
        stem = path.stem
        dst = target_path(out_dir, stem, args.suffix)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            with contextlib.redirect_stdout(io.StringIO()):
                data = va._normalize_schema(data, source_path=path)
            if args.tex:
                data = with_tex_macros(data, Path(args.tex.replace("{stem}", stem)))
            if not data.get("nodes"):
                print("[%d/%d] %s: no nodes, skipped" % (k + 1, len(files), stem))
                continue
            grounding = load_grounding(args.grounding, stem, data) if args.grounding else None
            model, pv, funcs, css, mj = paper_model(data, stem, grounding, args.concepts)
            html = render_page(model, pv, funcs, css, mj, mode, lib_dir)
        except Exception as e:                                   # keep the batch going
            print("[%d/%d] %s: FAILED %s: %s" % (k + 1, len(files), stem, type(e).__name__, e))
            continue
        dst.write_text(html, encoding="utf-8")
        n_ok += 1
        print("[%d/%d] %s -> %s (%d nodes, %d edges, %s, %.0f KB)"
              % (k + 1, len(files), stem, dst.name, len(model["nodes"]),
                 len(model["edges"]), model["level"], len(html) / 1024))
    print("done: %d/%d pages in %.0f s" % (n_ok, len(files), time.time() - t0))


if __name__ == "__main__":
    main()
