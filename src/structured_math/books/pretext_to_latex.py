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
        "remark", "exercise", "algorithm", "axiom", "fact", "observation", "note", "question", "problem"}
SECTIONS = {"chapter": "chapter", "section": "section", "subsection": "subsection",
            "subsubsection": "subsubsection", "exercises": "section*", "paragraphs": "paragraph"}
DROP = {"sage", "idx", "index", "hint", "answer", "solution", "notation", "image", "figure", "video",
        "interactive", "input", "output", "commentary", "fn"}
INLINE = {"em": "\\emph{%s}", "term": "\\textbf{%s}", "alert": "\\textbf{%s}", "q": "``%s''",
          "c": "\\texttt{%s}", "i": "\\textit{%s}", "b": "\\textbf{%s}"}
CHARS = {"mdash": "---", "ndash": "--", "nbsp": "~", "ellipsis": "\\ldots{}", "lq": "``", "rq": "''",
         "times": "$\\times$", "copyleft": "", "TeX": "\\TeX{}", "LaTeX": "\\LaTeX{}"}


def _text(s: str | None) -> str:
    return re.sub(r"([#%&_])", r"\\\1", s or "")


def conv(e: ET.Element) -> str:
    tag = e.tag.split("}")[-1]
    if tag in DROP:
        return _text(e.tail)
    inner = lambda: _text(e.text) + "".join(conv(c) for c in e)    # noqa: E731
    out: str
    if tag == "m":
        out = "$" + (e.text or "") + "$"
    elif tag == "me":
        out = "\\[" + (e.text or "") + "\\]"
    elif tag == "men":
        out = "\\begin{equation}" + (e.text or "") + (f"\\label{{{e.get(XI)}}}" if e.get(XI) else "") + "\\end{equation}"
    elif tag in ("md", "mdn"):
        rows = [(r.text or "") + (f"\\label{{{r.get(XI)}}}" if r.get(XI) else "") for r in e if r.tag.endswith("mrow")]
        out = "\\begin{align*}" + "\\\\\n".join(rows) + "\\end{align*}"
    elif tag == "xref":
        ref = e.get("ref") or ""
        out = (e.text or "") + "~" + ", ".join(f"\\ref{{{r.strip()}}}" for r in ref.split(",") if r.strip())
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
        body = "".join(conv(c) for c in e if c.tag not in ("proof", "title"))
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
    body = re.sub(r"\n{3,}", "\n\n", conv(root))
    Path(a.out).write_text(PREAMBLE + "\\begin{document}\n" + body + "\n\\end{document}\n", encoding="utf-8")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
