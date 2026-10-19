#!/usr/bin/env python3
"""Write paper_nodiag.tex next to each gold paper.tex: the source with the authors' dependency
diagram (the gold) removed, so an extraction cannot read the answer from the figure.

    python3 scripts/gold_candidates/strip_diagram.py [ids...]   (default: the evaluation subset)

Every gold diagram (graph_tikz.json) is found as the drawing sharing the most \\ref keys with its
boxes, else by its caption, and so is any other drawing citing one of the gold's results;
meta.json's caption and LaTeX head are a fallback. Its figure is
replaced by a placeholder figure that keeps the \\label, so "see Figure 2" still resolves, and
says the diagram is omitted; the drawing and the caption (which cites the results it links) go.
A drawing outside a figure environment is cut to its own \\end{tikzpicture|tikzcd|picture|xy}
or, for an inline \\xymatrix, its closing brace.
Prints how many papers had a diagram removed; a paper with none found is listed.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPERS = REPO / "corpus/gold_candidates/papers"
_BEGIN_FIG = re.compile(r"\\begin\s*\{(figure\*?|wrapfigure|center)\}")
_DRAW = ("tikzpicture", "tikzcd", "picture", "xy", "xymatrix")


def loose(s, n=None):
    """A whitespace-insensitive pattern for the first n non-space characters of s."""
    chars = "".join(s.split())[:n] if n else "".join(s.split())
    return r"\s*".join(re.escape(c) for c in chars)


def enclosing_figure(tex, pos):
    """(start, end, labels) of the figure environment containing pos, or None."""
    best = None
    for m in _BEGIN_FIG.finditer(tex, 0, pos):
        env = re.escape(m.group(1))
        e = re.compile(r"\\end\s*\{" + env + r"\}").search(tex, m.end())
        if e and e.end() > pos:
            best = (m.start(), e.end())
    if not best:
        return None
    labels = re.findall(r"\\label\s*\{([^{}]*)\}", tex[best[0]:best[1]])
    return best[0], best[1], labels


def drawing_at(tex, pos):
    """(start, end) of the drawing environment, or inline \\xymatrix{...}, starting at or after pos."""
    m = re.compile(r"\\begin\s*\{(" + "|".join(_DRAW) + r")\}|\\xymatrix\b").search(tex, pos)
    if not m:
        return None
    if not m.group(1):                                 # \xymatrix{...}: to the matching brace
        depth, i = 0, tex.find("{", m.end())
        while 0 <= i < len(tex):
            c = tex[i]
            if c == "\\":
                i += 2
                continue
            depth += (c == "{") - (c == "}")
            if depth == 0:
                return m.start(), i + 1
            i += 1
        return None
    e = re.compile(r"\\end\s*\{" + re.escape(m.group(1)) + r"\}").search(tex, m.end())
    return (m.start(), e.end()) if e else None


_REF = re.compile(r"ref\*?\s*\{([^{}]*)\}")


def drawings(tex):
    """(start, end, \\ref keys) of every drawing in tex: a drawing environment or an inline \\xymatrix."""
    out, pos = [], 0
    while (dr := drawing_at(tex, pos)):
        out.append((dr[0], dr[1], set(_REF.findall(tex[dr[0]:dr[1]]))))
        pos = dr[1]
    return out


def spans_for(pid, tex):
    """The spans to cut: each diagram in graph_tikz.json (all of the paper's gold diagrams) is the drawing
    sharing the most \\ref keys with its boxes, else the drawing in the figure with its caption, plus any
    drawing citing one of the gold's \\ref keys (a diagram drawn in several pieces); meta.json's
    caption and LaTeX are a fallback. A figure holding no drawing (an image) is never cut."""
    d = PAPERS / pid
    meta = json.loads((d / "meta.json").read_text())
    graphs = json.loads((d / "graph_tikz.json").read_text()) if (d / "graph_tikz.json").is_file() else []
    draws = drawings(tex)
    picked = set()
    for g in graphs:
        keys = {r["label"] for n in g.get("nodes", []) for r in n.get("refs", [])}
        hit = max(draws, key=lambda x: len(keys & x[2]), default=None)
        if hit and keys & hit[2]:
            picked.add(hit[:2])
            continue
        cap = (g.get("caption") or "").strip()
        for m in re.finditer(loose(cap, 60), tex) if cap else ():
            f = enclosing_figure(tex, m.start())
            picked |= {x[:2] for x in draws if f and f[0] <= x[0] < f[1]}
    gold = {r["label"] for g in graphs for n in g.get("nodes", []) for r in n.get("refs", [])}
    picked |= {x[:2] for x in draws if gold & x[2]}   # a diagram drawn in several pieces, or a commented-out draft
    if not picked:                                     # meta.json: the caption, else the head of the recorded LaTeX
        anchors = []
        cap = (meta.get("caption") or "").strip()
        if cap:
            anchors += [m.start() for m in re.finditer(loose(cap, 60), tex)]
        snip = meta.get("figure_latex") or ""
        for n in (80, 40, 25):
            if anchors or not snip.strip():
                break
            anchors += [m.start() for m in re.finditer(loose(snip, n), tex)]
        for a in anchors:
            f = enclosing_figure(tex, a)
            inside = [x[:2] for x in draws if f and f[0] <= x[0] < f[1]]
            dr = inside[:1] or [x[:2] for x in draws if x[0] >= a][:1]
            picked |= set(dr)
    out = []
    for a, b in picked:
        f = enclosing_figure(tex, a)
        out.append(f if f else (a, b, None))
    return out


def strip(pid):
    d = PAPERS / pid
    tex = (d / "paper.tex").read_text(errors="replace")
    spans = sorted(set((a, b, None if l is None else tuple(l)) for a, b, l in spans_for(pid, tex)))
    out, pos, n = [], 0, 0
    for a, b, labels in spans:
        if a < pos:
            continue
        if labels is None:                             # an inline drawing, maybe inside math
            out.append(tex[pos:a] + "\\mbox{[omitted: a diagram of this paper's results, not reproduced here]}")
        else:
            keep = "".join(f"\\label{{{x}}}" for x in labels)
            out.append(tex[pos:a] + "\\begin{figure}[omitted: a diagram of this paper's results, not "
                       "reproduced here]" + keep + "\\end{figure}")
        pos, n = b, n + 1
    out.append(tex[pos:])
    (d / "paper_nodiag.tex").write_text("".join(out))
    return n


def main():
    ids = sys.argv[1:] or [l.split()[0] for l in open(PAPERS.parent / "eval_subset.txt")
                           if l.strip() and not l.startswith("#")]
    missing = [pid for pid in ids if strip(pid) == 0]
    print(f"{len(ids) - len(missing)}/{len(ids)} papers: diagram removed; not found in: {missing}")


if __name__ == "__main__":
    main()
