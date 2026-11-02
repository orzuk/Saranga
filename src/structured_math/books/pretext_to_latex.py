"""A PreTeXt chapter (XML; Judson, Beezer, Levin) as a LaTeX document the v7 extractor can
read: sections, theorem-like environments with \\label from xml:id, proofs, math, \\ref
for xref. Sage cells, index entries and hints are dropped; exercises are kept.

    python -m structured_math.books.pretext_to_latex src/cosets.xml -o cosets.tex
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementInclude as EI
import xml.etree.ElementTree as ET
from pathlib import Path

XI = "{http://www.w3.org/XML/1998/namespace}id"
ENVS = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture", "definition", "example",
        "remark", "exercise", "algorithm", "axiom", "fact", "observation", "note", "question", "problem",
        "principle", "assemblage"}                  # assemblage: a boxed key statement
SECTIONS = {"chapter": "chapter", "section": "section", "subsection": "subsection",
            "subsubsection": "subsubsection", "exercises": "section*", "paragraphs": "paragraph"}
DROP = {"sage", "idx", "index", "hint", "answer", "solution", "notation", "pg-code", "setup", "pg-macros", "image", "video",
        "interactive", "input", "output", "commentary", "fn", "feedback", "shortsummary"}
# blocks PreTeXt books use for student work, as the environment the extractor knows
ALIAS = {"activity": "exercise", "exploration": "exercise", "project": "exercise", "investigation": "problem"}
INLINE = {"em": "\\emph{%s}", "term": "\\textbf{%s}", "alert": "\\textbf{%s}", "q": "``%s''",
          "c": "\\texttt{%s}", "i": "\\textit{%s}", "b": "\\textbf{%s}"}
CHARS = {"mdash": "---", "ndash": "--", "nbsp": "~", "ellipsis": "\\ldots{}", "lq": "``", "rq": "''",
         "times": "$\\times$", "copyleft": "", "TeX": "\\TeX{}", "LaTeX": "\\LaTeX{}"}


DOLLAR_MATH = False      # the source writes inline math as $...$ in the text (Beezer's older dialect)
TARGETS: dict[str, ET.Element] = {}     # xml:id -> element, for the name an xref prints (index_targets)
_FIGS = {"figure", "table", "listing", "sidebyside"}
_NAMES = {"men": "Equation", "mrow": "Equation", "mdn": "Equation", "md": "Equation", "sageadvice": "Sage",
          "exercises": "Exercises", "li": "Item", "task": "Part", "biblio": "", "p": "", "ol": "List"}


def index_targets(root: ET.Element) -> None:
    """PreTeXt prints an xref as the target's type and number ("Theorem 3.2"); remember the targets."""
    TARGETS.clear()
    TARGETS.update({e.get(XI): e for e in root.iter() if e.get(XI)})


def _text(s: str | None) -> str:
    esc = lambda x: re.sub(r"([#%&_])", r"\\\1", x)      # noqa: E731
    if not DOLLAR_MATH:
        return esc(s or "")
    return "".join(x if i % 2 else esc(x) for i, x in enumerate(re.split(r"(\$[^$]*\$)", s or "")))


def _xref(e: ET.Element) -> str:
    refs = [r.strip() for r in (e.get("ref") or "").split(",") if r.strip()]
    t = TARGETS.get(refs[0]) if refs else None
    tag = e.get("kind") or (t.tag.split("}")[-1] if t is not None else "")
    if e.get("text") == "title" and t is not None and t.find("title") is not None:
        return conv_title(t.find("title")) + "".join(f"~(\\ref{{{r}}})" for r in refs)
    if tag in _FIGS and t is not None:          # figures carry no number here: print the caption
        cap = t.find("caption") if t.find("caption") is not None else t.find("title")
        c = conv_title(cap) if cap is not None else ""
        return f"{tag.capitalize()}" + (f" (``{c}'')" if c else "")
    word = (e.text or "").strip() or ("" if e.get("text") in ("global", "local") or not tag
                                      else _NAMES.get(tag, tag.capitalize()))
    return (word + "~" if word else "") + ", ".join(f"\\ref{{{r}}}" for r in refs)


def _tabular(e: ET.Element) -> str:
    rows = [r for r in e if r.tag == "row"]
    n = max((sum(int(c.get("colspan", 1)) for c in r if c.tag == "cell") for r in rows), default=1)
    body = " \\\\\n".join(" & ".join(conv_title(c) for c in r if c.tag == "cell") for r in rows)
    return f"\n\\begin{{tabular}}{{{'l' * n}}}\n{body}\n\\end{{tabular}}\n"


def _kids(e: ET.Element, f=None, skip=()) -> str:
    """The children through f (default conv), with consecutive tasks (an exercise's parts) as one enumerate."""
    out, tasks = [], []
    for c in e:
        if c.tag in skip:
            continue
        if c.tag == "task":
            tasks.append("\\item " + (_text(c.text) + "".join(conv(x) for x in c)).strip() + "\n")
            continue
        if tasks:
            out.append("\n\\begin{enumerate}\n" + "".join(tasks) + "\\end{enumerate}\n")
            tasks = []
        out.append((f or conv)(c))
    if tasks:
        out.append("\n\\begin{enumerate}\n" + "".join(tasks) + "\\end{enumerate}\n")
    return "".join(out)


def conv(e: ET.Element) -> str:
    tag = e.tag.split("}")[-1]
    tag = ALIAS.get(tag, tag)
    if tag in DROP:
        return _text(e.tail)
    inner = lambda: _text(e.text) + _kids(e)    # noqa: E731
    out: str
    if tag == "webwork" and re.search(r"DBsubject\(|DOCUMENT\(\)", e.text or ""):   # a PG program included as text
        return _kids(e) + _text(e.tail)
    if tag == "var":                                          # a WeBWorK answer blank; name is the answer
        out = "\\underline{\\hspace{2em}}"
    elif tag == "choices":                                      # multiple choice, without which is correct
        out = "\n\\begin{enumerate}\n" + "".join("\\item " + conv_title(c) + "\n" for c in e if c.tag == "choice") + "\\end{enumerate}\n"
    elif tag in ("figure", "table", "listing"):                  # the caption (and a table's cells), no image
        cap = e.find("caption") if e.find("caption") is not None else e.find("title")
        rest = "".join(conv(c) for c in e if c.tag not in ("caption", "title"))
        out = f"\n\\begin{{{'table' if tag == 'table' else 'figure'}}}\n" + rest.strip() + (
            f"\n\\caption{{{conv_title(cap)}}}" if cap is not None else "") + f"\n\\end{{{'table' if tag == 'table' else 'figure'}}}\n"
    elif tag == "propertylist":                                 # Beezer's named properties inside a theorem
        out = "\n\\begin{enumerate}\n" + "".join(
            "\\item " + (f"\\textbf{{{conv_title(c.find('title'))}.}} " if c.find("title") is not None else "")
            + (f"\\label{{{c.get(XI)}}} " if c.get(XI) else "")
            + "".join(conv(x) for x in c if x.tag != "title").strip() + "\n"
            for c in e if c.tag == "property") + "\\end{enumerate}\n"
    elif tag == "tabular":
        out = _tabular(e)
    elif tag == "caption":
        return _text(e.tail)                                    # placed by the parent
    elif tag == "br":
        out = "\n"
    elif tag == "m":
        out = "$" + (e.text or "") + "$"
    elif tag == "me" and e.get(XI):                             # a labelled display is numbered so its \ref resolves
        out = "\\begin{equation}" + "".join(e.itertext()) + f"\\label{{{e.get(XI)}}}" + "\\end{equation}"
    elif tag == "me":
        out = "\\[" + (e.text or "") + "\\]"
    elif tag == "men":
        out = "\\begin{equation}" + (e.text or "") + (f"\\label{{{e.get(XI)}}}" if e.get(XI) else "") + "\\end{equation}"
    elif tag in ("md", "mdn"):
        rows = ["".join(r.itertext()) + (f"\\label{{{r.get(XI)}}}" if r.get(XI) else "") for r in e if r.tag.endswith("mrow")]
        if not rows:                                            # a one-line display written without <mrow>
            rows = ["".join(e.itertext())]
        if e.get(XI):                                           # the display's own label, on its last row
            rows[-1] += f"\\label{{{e.get(XI)}}}"
        out = "\\begin{align*}" + "\\\\\n".join(rows) + "\\end{align*}"
    elif tag == "xref":
        out = _xref(e)
    elif tag in INLINE:
        out = INLINE[tag] % inner()
    elif tag in CHARS:
        out = CHARS[tag]
    elif tag == "title":
        return _text(e.tail)                                    # placed by the parent
    elif tag in SECTIONS:
        t = e.find("{*}title") if e.find("{*}title") is not None else e.find("title")
        title = conv_title(t)
        lab = f"\\label{{{e.get(XI)}}}" if e.get(XI) else ""
        out = f"\n\\{SECTIONS[tag]}{{{title}}}{lab}\n" + inner()
    elif tag in ENVS:
        t = e.find("title")
        opt = f"[{conv_title(t)}]" if t is not None else ""
        lab = f"\\label{{{e.get(XI)}}}" if e.get(XI) else ""
        # an example's worked solution is part of the example (an exercise's solution is dropped)
        sol = lambda c: (_text(c.text) + "".join(conv(x) for x in c) + _text(c.tail)) if c.tag == "solution" and tag == "example" else conv(c)  # noqa: E731
        body = _text(e.text) + _kids(e, sol, ("proof", "title"))
        if tag == "exercise" and not body.strip():               # a server problem with no text in the source
            return _text(e.tail)
        proofs = "".join(conv(c) for c in e if c.tag == "proof")
        out = f"\n\\begin{{{tag}}}{opt}{lab}\n{body.strip()}\n\\end{{{tag}}}\n{proofs}"
    elif tag == "proof":
        out = "\n\\begin{proof}\n" + inner().strip() + "\n\\end{proof}\n"
    elif tag == "p":
        out = "\n" + inner().strip() + "\n"
    elif tag in ("ol", "ul"):
        env = "enumerate" if tag == "ol" else "itemize"
        out = f"\n\\begin{{{env}}}\n" + "".join(conv(c) for c in e if c.tag == "li") + f"\\end{{{env}}}\n"
    elif tag == "li":
        out = "\\item " + inner().strip() + "\n"
    else:                                                       # statement, introduction, task, ...
        out = inner()
    return out + _text(e.tail)


def conv_title(t) -> str:
    if t is None:
        return ""
    return (_text(t.text) + "".join(conv(c) for c in t)).strip()


PREAMBLE = r"""\documentclass{book}
\usepackage{amsmath,amssymb,amsthm}
""" + "".join(f"\\newtheorem{{{e}}}{{{e.capitalize()}}}[chapter]\n" for e in sorted(ENVS - {"definition", "example", "remark", "exercise"})) + \
    "\\theoremstyle{definition}\n" + "".join(f"\\newtheorem{{{e}}}{{{e.capitalize()}}}[chapter]\n" for e in ("definition", "example", "remark", "exercise"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("xml")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    root = ET.parse(a.xml).getroot()
    EI.include(root, base_url=str(Path(a.xml).resolve()), max_depth=10)     # chapters split over files
    index_targets(root)
    body = re.sub(r"\n{3,}", "\n\n", conv(root))
    Path(a.out).write_text(PREAMBLE + "\\begin{document}\n" + body + "\n\\end{document}\n", encoding="utf-8")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
