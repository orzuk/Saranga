#!/usr/bin/env python3
"""Export a paper graph as TikZ, Mermaid or DOT.

For figures in the paper. Today a diagram in a write-up has to be redrawn by
hand from the rendered SVG, which means it drifts from the data the moment
either changes; this emits the figure FROM the JSON so it cannot.

Deliberately standalone: it does not import visualize_annotation, so it neither
drags in matplotlib nor depends on that module's per-paper global state, and it
can run while a render is in progress.

The reductions match the viewer's toggles, so a figure can be cut down the same
way the interactive version is:

    --backbone     definitions + theorem-like only     (keeps ~37% of nodes)
    --no-implied   drop transitively implied edges     (drops ~25% of edges)
    --collapse     fold proofs into the theorem they prove

Usage:
    python3 scripts/export_graph.py paper.json --format tikz --backbone
    python3 scripts/export_graph.py paper.json --format mermaid --no-implied
    python3 scripts/export_graph.py paper.json --format dot -o g.dot
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from latex_macros import normalize_for_mathtext          # noqa: E402

THEOREM_LIKE = {"theorem", "lemma", "proposition", "corollary", "claim",
                "conjecture"}
BACKBONE = THEOREM_LIKE | {"definition"}
LEVEL2 = {"proof_step", "algorithm_step"}
# Same grouping the viewer colours by; see visualize_annotation.EDGE_COLORS.
DEPENDENCY = ("uses", "generalizes", "specializes")

SHORT = {"theorem": "Thm", "lemma": "Lem", "proposition": "Prop",
         "corollary": "Cor", "claim": "Clm", "conjecture": "Conj",
         "definition": "Def", "proof": "Pf", "algorithm": "Alg",
         "equation": "Eq", "remark": "Rem", "example": "Ex",
         "assumption": "Asm", "problem": "Prob", "open_problem": "Open"}


def load(path, collapse=True, backbone=False, drop_level2=True):
    d = json.load(open(path, encoding="utf-8"))
    nodes = list(d.get("nodes") or [])
    edges = list(d.get("edges") or [])
    if drop_level2:
        gone = {n["id"] for n in nodes if n.get("type") in LEVEL2}
        nodes = [n for n in nodes if n["id"] not in gone]
        edges = [e for e in edges
                 if e.get("source") not in gone and e.get("target") not in gone]
    if collapse:
        # Fold each proof into what it proves: its dependencies become the
        # theorem's. Matches the viewer, where a proof is a badge not a box.
        proof_of = {}
        for n in nodes:
            pv = n.get("proves")
            if isinstance(pv, (list, tuple)):
                pv = pv[0] if pv else None
            if n.get("type") == "proof" and pv:
                proof_of[n["id"]] = pv
        nodes = [n for n in nodes if n["id"] not in proof_of]
        remapped = []
        for e in edges:
            a = proof_of.get(e.get("source"), e.get("source"))
            b = proof_of.get(e.get("target"), e.get("target"))
            if a != b:
                remapped.append(dict(e, source=a, target=b))
        edges = remapped
    if backbone:
        keep = {n["id"] for n in nodes if n.get("type") in BACKBONE}
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges
                 if e.get("source") in keep and e.get("target") in keep]
    ids = {n["id"] for n in nodes}
    seen = set()
    uniq = []
    for e in edges:
        k = (e.get("source"), e.get("target"), e.get("type"))
        if e.get("source") in ids and e.get("target") in ids and k not in seen:
            seen.add(k)
            uniq.append(e)
    return d.get("metadata") or {}, nodes, uniq


def drop_implied(nodes, edges):
    """Remove edges reachable by a longer path OF THE SAME COMPOSED TYPE.

    Same rule as the viewer: a path is `generalizes` only if every edge on it
    is; anything else composes to `uses`; and the non-transitive types
    (proves/illustrates/solves/resolves/tests) are never implied.
    """
    try:
        import networkx as nx
    except ImportError:
        return edges
    ids = {n["id"] for n in nodes}

    def build(pred):
        g = nx.DiGraph()
        g.add_nodes_from(ids)
        for e in edges:
            if pred(str(e.get("type") or "uses")) and e["source"] != e["target"]:
                g.add_edge(e["source"], e["target"])
        return g

    graphs = {"uses": build(lambda t: t in DEPENDENCY),
              "generalizes": build(lambda t: t == "generalizes"),
              "specializes": build(lambda t: t == "specializes")}
    out = []
    for e in edges:
        t = str(e.get("type") or "uses")
        g = graphs.get(t)
        if g is None or not g.has_edge(e["source"], e["target"]):
            out.append(e)
            continue
        g.remove_edge(e["source"], e["target"])
        implied = nx.has_path(g, e["source"], e["target"])
        g.add_edge(e["source"], e["target"])
        if not implied:
            out.append(e)
    return out


def layers(nodes, edges):
    """Longest-path layering: a node sits one level below its deepest support."""
    ids = [n["id"] for n in nodes]
    preds = {i: [] for i in ids}
    for e in edges:
        preds.setdefault(e["target"], []).append(e["source"])
    depth = {}

    def d(i, seen=()):
        if i in depth:
            return depth[i]
        if i in seen:                      # cycle: stop rather than recurse
            return 0
        v = 0
        for p in preds.get(i, ()):
            if p in preds:
                v = max(v, d(p, seen + (i,)) + 1)
        depth[i] = v
        return v

    for i in ids:
        d(i)
    return depth


def _san(nid):
    return re.sub(r"[^A-Za-z0-9]", "_", str(nid))


_MATH = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$", re.S)


def _label(n, macros=None, keep_math=True):
    r"""Short label. Paper macros are RESOLVED — an unexpanded `\xo` compiles
    fine here but not in the document the figure is pasted into."""
    t = SHORT.get(n.get("type"), (n.get("type") or "?")[:4])
    nm = (n.get("name") or "").strip()
    if nm:
        nm = normalize_for_mathtext(nm, macros or {})
        if not keep_math:                     # mermaid has no LaTeX
            nm = _MATH.sub(lambda m: m.group(1), nm)
            nm = re.sub(r"\\[A-Za-z]+", "", nm)
        nm = re.sub(r"\s+", " ", nm).strip()
        if len(nm) > 40:                      # cut on a word, not mid-token
            cut = nm[:40].rsplit(" ", 1)[0]
            nm = (cut or nm[:40]) + "\u2026"
    return ("%s: %s" % (t, nm)) if nm else t


def to_mermaid(meta, nodes, edges):
    mac = (meta or {}).get("macros") or {}
    out = ["flowchart BT"]          # prerequisites at the bottom, results on top
    for n in nodes:
        lbl = _label(n, mac, keep_math=False).replace('"', "'")
        shape = "([%s])" if n.get("type") == "definition" else "[%s]"
        out.append('  %s%s' % (_san(n["id"]), shape % ('"%s"' % lbl)))
    for e in edges:
        arrow = "-.->" if str(e.get("type")) == "generalizes" else "-->"
        lbl = str(e.get("type") or "uses")
        out.append("  %s %s|%s| %s"
                   % (_san(e["source"]), arrow, lbl, _san(e["target"])))
    return "\n".join(out)


def to_dot(meta, nodes, edges):
    mac = (meta or {}).get("macros") or {}
    out = ['digraph G {', '  rankdir=BT;', '  node [shape=box, fontsize=10];']
    for n in nodes:
        shape = "ellipse" if n.get("type") == "definition" else "box"
        out.append('  "%s" [label="%s", shape=%s];'
                   % (_san(n["id"]), _label(n, mac, keep_math=False).replace('"', "'"), shape))
    for e in edges:
        style = "dashed" if str(e.get("type")) == "generalizes" else "solid"
        out.append('  "%s" -> "%s" [style=%s];'
                   % (_san(e["source"]), _san(e["target"]), style))
    out.append("}")
    return "\n".join(out)


def _tex_escape(lbl):
    """Escape only OUTSIDE `$...$`; inside, the LaTeX must stay live."""
    out, i = [], 0
    for m in _MATH.finditer(lbl):
        out.append(lbl[i:m.start()].replace("_", r"\_").replace("&", r"\&")
                   .replace("#", r"\#").replace("%", r"\%"))
        out.append(m.group(0))
        i = m.end()
    out.append(lbl[i:].replace("_", r"\_").replace("&", r"\&")
               .replace("#", r"\#").replace("%", r"\%"))
    return "".join(out)


def to_tikz(meta, nodes, edges):
    """Layered TikZ. Positions are computed here, not authored — the same
    principle the viewer uses, so the figure cannot drift from the graph."""
    mac = (meta or {}).get("macros") or {}
    depth = layers(nodes, edges)
    rows = {}
    for n in nodes:
        rows.setdefault(depth.get(n["id"], 0), []).append(n)
    out = [r"% Generated by scripts/export_graph.py — do not hand-edit.",
           r"% Regenerate after any change to the paper graph.",
           r"\begin{tikzpicture}[",
           r"  every node/.style={font=\scriptsize},",
           r"  thm/.style={draw, rounded corners, fill=blue!5, "
           r"text width=32mm, align=center, inner sep=2pt},",
           r"  def/.style={draw, ellipse, fill=green!5, "
           r"text width=28mm, align=center, inner sep=1pt},",
           r"  uses/.style={->, >=latex, gray!70},",
           r"  gen/.style={->, >=latex, dashed, teal},",
           r"]"]
    for lvl in sorted(rows):
        for k, n in enumerate(sorted(rows[lvl], key=lambda x: x["id"])):
            sty = "def" if n.get("type") == "definition" else "thm"
            out.append(r"  \node[%s] (%s) at (%.1f,%.1f) {%s};"
                       % (sty, _san(n["id"]), k * 3.8, lvl * 2.2,
                          _tex_escape(_label(n, mac))))
    for e in edges:
        sty = "gen" if str(e.get("type")) == "generalizes" else "uses"
        out.append(r"  \draw[%s] (%s) -- (%s);"
                   % (sty, _san(e["source"]), _san(e["target"])))
    out.append(r"\end{tikzpicture}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paper")
    ap.add_argument("--format", choices=("tikz", "mermaid", "dot"),
                    default="mermaid")
    ap.add_argument("--backbone", action="store_true",
                    help="definitions + theorem-like only")
    ap.add_argument("--no-implied", action="store_true",
                    help="drop transitively implied edges")
    ap.add_argument("--keep-proofs", action="store_true",
                    help="do NOT fold proofs into what they prove")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    meta, nodes, edges = load(a.paper, collapse=not a.keep_proofs,
                              backbone=a.backbone)
    if a.no_implied:
        edges = drop_implied(nodes, edges)
    text = {"tikz": to_tikz, "mermaid": to_mermaid,
            "dot": to_dot}[a.format](meta, nodes, edges)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print("wrote %s (%d nodes, %d edges)" % (a.out, len(nodes), len(edges)),
              file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
