"""Dive into Deep Learning (d2l-en markdown source) as one LaTeX file per chapter, plus the book's
label table, in the format of prepare_book.py (chNN.tex, labels.json, chapters.json).

    python -m structured_math.books.d2l_to_latex SRC OUT

Only the mathematically substantive chapters are written (CHAPTERS); NN is the chapter's own
number in the book (index.md's numbered toc), and \\setcounter keeps its numbering. Inside a
chapter, a section that is mostly code (data loading, from-scratch / concise implementations)
is kept as its heading and \\label only, so the remaining sections keep their book numbers and
references to the skipped ones still resolve.

Conversion: chapter index.md "#" -> \\chapter, a section file's "#"/"##"/"###" -> \\section/
\\subsection/\\subsubsection; :label:`x` -> \\label{x}; :numref:`x` -> \\ref{x}; :eqref:`x` ->
\\eqref{x}; :cite:/:citet: -> \\cite; $$...$$ followed by :eqlabel:`x` -> equation with \\label
(numbered within the section, as in the book), other $$...$$ -> \\[...\\]; inline $...$ verbatim;
code cells and :begin_tab: ... :end_tab: blocks dropped; figures -> figure with caption and label;
markdown lists -> itemize/enumerate; the "Exercises" section -> one exercise environment per
top-level item (sub-items an enumerate inside it).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from latex_facts import extract_facts, read_tex          # noqa: E402

# chapter folder -> sections kept with their text (the others: heading + label only)
CHAPTERS = {
    "chapter_preliminaries": {"linear-algebra", "calculus", "probability"},
    "chapter_linear-regression": {"linear-regression", "generalization", "weight-decay"},
    "chapter_linear-classification": {"softmax-regression", "generalization-classification",
                                      "environment-and-distribution-shift"},
    "chapter_multilayer-perceptrons": {"mlp", "backprop", "numerical-stability-and-init",
                                       "generalization-deep", "dropout"},
    "chapter_attention-mechanisms-and-transformers": {
        "queries-keys-values", "attention-pooling", "attention-scoring-functions", "bahdanau-attention",
        "multihead-attention", "self-attention-and-positional-encoding", "transformer"},
    "chapter_optimization": None,                                     # None: every section
    "chapter_appendix-mathematics-for-deep-learning": None,
}

PREAMBLE = r"""\documentclass{book}
\usepackage{amsmath,amssymb,amsthm,graphicx,natbib}
\numberwithin{equation}{section}
\theoremstyle{definition}
\newtheorem{exercise}{Exercise}[section]
"""


def toc(md: str) -> list[str]:
    out = []
    for block in re.findall(r"```toc\n(.*?)```", md, re.S):
        out += [x.strip() for x in block.splitlines() if x.strip() and not x.strip().startswith(":")]
    return out


# ── inline text ────────────────────────────────────────────────────────────

_TEXT_ESC = {"%": r"\%", "&": r"\&", "#": r"\#", "_": r"\_", "^": r"\^{}", "~": r"\textasciitilde{}"}


def _esc(t: str) -> str:
    """Plain prose escaped for LaTeX (math and commands are handled before this)."""
    t = re.sub(r"(?<!\\)[%&#_^~]", lambda m: _TEXT_ESC[m.group(0)], t)
    return t.replace("<", r"\textless{}").replace(">", r"\textgreater{}")


def _code(t: str) -> str:
    t = t.replace("\\", r"\textbackslash{}").replace("{", r"\{").replace("}", r"\}")
    t = re.sub(r"[$%&#_^~]", lambda m: "\\" + m.group(0) + ("{}" if m.group(0) in "^~" else ""), t)
    return r"\texttt{" + t + "}"


def _refs(t: str) -> str:
    t = re.sub(r":numref:`([^`]*)`", lambda m: r"\ref{" + _key(m.group(1)) + "}", t)
    t = re.sub(r":eqref:`([^`]*)`", lambda m: r"\eqref{" + _key(m.group(1)) + "}", t)
    t = re.sub(r":citet?:`([^`]*)`", lambda m: r"\cite{" + m.group(1).strip() + "}", t)
    t = re.sub(r":label:`([^`]*)`", lambda m: r"\label{" + m.group(1).strip() + "}", t)
    return t


def _key(s: str) -> str:
    """`text <label>` (a numref with its own text) or `label`."""
    m = re.search(r"<([^>]+)>\s*$", s)
    return (m.group(1) if m else s).strip()


_PROTECT = re.compile(r"`[^`\n]+`|\$\$.*?\$\$|\\\(.*?\\\)|(?<![\\$])\$(?:\\.|[^$\\])+?\$"
                      r"|:(?:numref|eqref|cite|citet|label):`[^`]*`", re.S)


def inline(t: str) -> str:
    """One paragraph of markdown prose as LaTeX: math and references kept, the rest escaped."""
    t = t.replace("[**", "").replace("**]", "")              # d2l's highlighting of code-backed text
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\((?:https?://|\.\./|#)[^)]*\)", r"\1", t)
    out, pos = [], 0
    for m in _PROTECT.finditer(t):
        out.append(_prose(t[pos:m.start()]))
        x = m.group(0)
        if x.startswith("`"):
            out.append(_code(x[1:-1]))
        elif x.startswith(":"):
            out.append(_refs(x))
        elif x.startswith("$$"):
            out.append("\\[" + x[2:-2] + "\\]")
        else:
            out.append(x)
        pos = m.end()
    out.append(_prose(t[pos:]))
    return "".join(out)


def _prose(t: str) -> str:
    t = _esc(t)
    t = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"\\textbf{\1}", t, flags=re.S)
    t = re.sub(r"(?<![\w*\\])\*(?=\S)([^*]+?)(?<=\S)\*(?![\w*])", r"\\emph{\1}", t, flags=re.S)
    t = re.sub(r"(?<![\w\\])\\_(?=\S)([^_]+?)(?<=\S)\\_(?!\w)", r"\\emph{\1}", t)   # _emph_
    return t


# ── blocks ─────────────────────────────────────────────────────────────────

_ITEM = re.compile(r"^( *)(?:([*+-])|(\d+)[.)])\s+(.*)$")


def _list(lines: list[str]) -> str:
    """Markdown list lines (nested by indentation) as itemize/enumerate."""
    out, stack = [], []                     # stack of (indent, env)
    for ln in lines:
        m = _ITEM.match(ln)
        if not m:
            out.append(inline(ln.strip()))
            continue
        ind, env = len(m.group(1)), "itemize" if m.group(2) else "enumerate"
        while stack and ind < stack[-1][0]:
            out.append(f"\\end{{{stack.pop()[1]}}}")
        if not stack or ind > stack[-1][0]:
            stack.append((ind, env))
            out.append(f"\\begin{{{env}}}")
        out.append(r"\item " + inline(m.group(4)))
    while stack:
        out.append(f"\\end{{{stack.pop()[1]}}}")
    return "\n".join(out)


def _exercises(lines: list[str]) -> str:
    """The Exercises list: each top-level item an exercise, its sub-items an enumerate."""
    items, cur = [], None
    for ln in lines:
        m = _ITEM.match(ln)
        if m and not m.group(1):
            cur = [m.group(4)]
            items.append(cur)
        elif cur is not None:
            cur.append(ln)
        elif ln.strip():
            items.append([ln])
    out = []
    for it in items:
        head, rest = it[0], [x for x in it[1:] if x.strip()]
        sub = [x for x in rest if _ITEM.match(x)]
        body = inline(head)
        if rest and not sub:
            body += "\n" + inline(" ".join(x.strip() for x in rest))
        elif rest:
            ind = min(len(_ITEM.match(x).group(1)) for x in sub)
            body += "\n" + _list([x[ind:] if x[:ind].strip() == "" else x for x in rest])
        out.append(f"\\begin{{exercise}}\n{body}\n\\end{{exercise}}")
    return "\n\n".join(out)


def _table(lines: list[str]) -> str:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines
            if not re.match(r"^\s*\|?\s*:?-{2,}", ln)]
    n = max(len(r) for r in rows)
    body = " \\\\\n".join(" & ".join(inline(c) for c in r) for r in rows)
    return f"\\begin{{center}}\n\\begin{{tabular}}{{{'l' * n}}}\n{body}\n\\end{{tabular}}\n\\end{{center}}"


def convert(md: str, level: int) -> str:
    """One markdown file as LaTeX; level 0: its "#" is a \\chapter, 1: a \\section."""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    md = re.sub(r"\(\*\*|\*\*\)|\[\*\*|\*\*\]", "", md)     # d2l's marks for code-backed text
    md = re.sub(r"^```.*?^```[ \t]*$", "", md, flags=re.S | re.M)              # code cells, toc
    md = re.sub(r"^:begin_tab:`[^`]*`.*?^:end_tab:`?[ \t]*$", "", md, flags=re.S | re.M)
    md = re.sub(r"^\[Discussions\]\([^)]*\)\s*$", "", md, flags=re.M)
    lines = md.split("\n")
    out, i, in_ex = [], 0, False
    para: list[str] = []

    def flush():
        if para:
            out.append(inline("\n".join(para)))
            para.clear()
    heads = ["chapter", "section", "subsection", "subsubsection", "paragraph", "paragraph"]
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        lab = re.match(r":label:`([^`]*)`", nxt)
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", ln)
        if m:
            flush()
            cmd = heads[min(len(m.group(1)) - 1 + level, 5)]
            title = m.group(2).strip()
            in_ex = title.lower() in ("exercises", "exercise")
            out.append(f"\\{cmd}{{{inline(title)}}}" + (f"\\label{{{lab.group(1).strip()}}}" if lab else ""))
            i += 2 if lab else 1
            continue
        if s.startswith("$$"):                                    # display math
            flush()
            j, buf = i, s[2:]
            while "$$" not in buf and j + 1 < len(lines):
                j += 1
                buf += "\n" + lines[j]
            k = buf.find("$$")
            math, tail = buf[:k].strip(), buf[k + 2:].strip()
            j += 1
            while j < len(lines) and not lines[j].strip() and j + 1 < len(lines) \
                    and lines[j + 1].strip().startswith(":eqlabel:"):
                j += 1
            em = re.match(r":eqlabel:`([^`]*)`", lines[j].strip()) if j < len(lines) else None
            em = em or re.match(r":eqlabel:`([^`]*)`", tail)
            if em:
                out.append(f"\\begin{{equation}}\n{math}\n\\label{{{em.group(1).strip()}}}\n\\end{{equation}}")
                if j < len(lines) and lines[j].strip().startswith(":eqlabel:"):
                    j += 1
            else:
                out.append(f"\\[\n{math}\n\\]")
            i = j
            continue
        fm = re.match(r"^!\[(.*)\]\(([^)]*)\)\s*$", s)
        if fm:                                                    # a figure, then :label:/:width:
            flush()
            j, flab = i + 1, ""
            while j < len(lines) and re.match(r"\s*:(label|width):`", lines[j]):
                g = re.match(r"\s*:label:`([^`]*)`", lines[j])
                flab = f"\\label{{{g.group(1).strip()}}}" if g else flab
                j += 1
            out.append(f"\\begin{{figure}}\n\\centering\n\\caption{{{inline(fm.group(1))}}}{flab}\n\\end{{figure}}")
            i = j
            continue
        if _ITEM.match(ln):                                       # a list (until a blank line not
            flush()                                               # followed by more of it)
            j, block = i, []
            while j < len(lines):
                if lines[j].strip():
                    if not (_ITEM.match(lines[j]) or lines[j].startswith(" ") or block):
                        break
                    if not _ITEM.match(lines[j]) and not lines[j].startswith(" ") and block \
                            and not lines[j - 1].strip():
                        break
                    block.append(lines[j])
                elif j + 1 < len(lines) and (_ITEM.match(lines[j + 1]) or lines[j + 1].startswith("  ")):
                    pass
                else:
                    break
                j += 1
            out.append(_exercises(block) if in_ex else _list(block))
            i = j
            continue
        if s.startswith("|") and s.count("|") >= 2:
            flush()
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(_table(lines[i:j]))
            i = j
            continue
        if s.startswith(">"):
            s = s.lstrip("> ")
        if not s:
            flush()
            out.append("")
        elif re.match(r":label:`", s):
            flush()
            out.append(_refs(s))
        else:
            para.append(ln if not ln.startswith(">") else s)
        i += 1
    flush()
    tex = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", tex).strip() + "\n"


def _stub(md: str) -> str:
    """A code section: its heading and label only."""
    m = re.search(r"^#\s+(.*?)\s*\n(?::label:`([^`]*)`)?", md, re.M)
    title = inline(m.group(1)) if m else "?"
    lab = f"\\label{{{m.group(2)}}}" if m and m.group(2) else ""
    return f"\\section{{{title}}}{lab}\n(A section on code; its text is not included.)\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", help="the d2l-en checkout (with index.md)")
    ap.add_argument("out")
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    # the numbered toc is the second toc block of index.md
    blocks = re.findall(r"```toc\n(.*?)```", (src / "index.md").read_text(encoding="utf-8"), re.S)
    numbered = [x.strip().split("/")[0] for x in next(b for b in blocks if ":numbered:" in b).splitlines()
                if x.strip().startswith("chapter_")]
    out.mkdir(parents=True, exist_ok=True)
    labels, chapters = {}, []
    for folder, keep in CHAPTERS.items():
        k = numbered.index(folder) + 1
        index = (src / folder / "index.md").read_text(encoding="utf-8")
        parts, kept = [convert(index, 0)], []
        for sec in toc(index):
            md = (src / folder / f"{sec}.md").read_text(encoding="utf-8")
            if keep is None or sec in keep:
                parts.append(convert(md, 1))
                kept.append(sec)
            else:
                parts.append(_stub(md))
        body = "\n".join(parts)
        title = re.search(r"\\chapter\{([^}]*)\}", body).group(1)
        f = out / f"ch{k:02d}.tex"
        f.write_text(f"{PREAMBLE}\n\\begin{{document}}\n\\setcounter{{chapter}}{{{k - 1}}}\n{body}\n\\end{{document}}\n",
                     encoding="utf-8")
        facts = extract_facts(read_tex(str(f)))
        by_label = {lab: x for x in facts["facts"] for lab in x["labels"]}
        for lab, v in facts["labels"].items():
            x = by_label.get(lab, {})
            labels[lab] = {"chapter": k, "number": v["number"], "kind": v["kind"], "type": x.get("type"),
                           "display": x.get("display"), "name": x.get("optarg")}
        chapters.append({"chapter": k, "file": f.name, "title": title, "facts": len(facts["facts"]),
                         "chars": len(body), "source": folder, "sections_kept": kept,
                         "sections_stubbed": [s for s in toc(index) if s not in kept]})
        print(f"ch{k:02d} {len(facts['facts']):4d} facts {len(body) // 1000:5d}K chars  {title[:60]}")
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=0))
    (out / "chapters.json").write_text(json.dumps({"main": str(src / "index.md"), "chapters": chapters}, indent=1))
    print(f"{len(chapters)} chapters, {len(labels)} labels -> {out}")


if __name__ == "__main__":
    main()
