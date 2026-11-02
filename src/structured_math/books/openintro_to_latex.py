"""OpenIntro Statistics (LaTeX source) as one standard-LaTeX file per chapter, plus the book's
label table, in the format of prepare_book.py (chNN.tex, labels.json, chapters.json).

    python -m structured_math.books.openintro_to_latex SRC OUT

The book's chapters are \\includechapter{N}{folder} calls (folder/TeX/folder.tex, then
folder/TeX/review_exercises.tex), titled by \\chaptertitle inside a chapterpage box, and its
results are custom boxes. Each is rewritten as an environment declared with \\newtheorem, so
latex_facts sees it as a fact:

    nexample{question}...      -> example        (shares the equation counter, as in the book)
    nexercise (Guided Practice) -> gpractice     ("Guided Practice Exercise", same counter)
    \\eoce{\\qt{title\\label{x}} text}{}  -> eoce   ("Exercise", numbered within the chapter)
    onebox{title}              -> definition / theorem / procedure / condition / remark
                                  (unnumbered; chosen from the title and body, see _onebox_env)
    tipBox, termBox, caution   -> remark

Guided Practice solutions (\\footnotemark + \\footnotetext) are dropped; end-of-chapter
solutions live in the appendix, which is not read. Figures keep their caption and label.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from latex_facts import extract_facts, read_tex          # noqa: E402

PREAMBLE = r"""\documentclass{book}
\usepackage{amsmath,amssymb,amsthm,graphicx}
\numberwithin{equation}{chapter}
\newcommand{\R}{\textbf{\textsf{R}}}
\newcommand{\degree}{\ensuremath{^\circ}}
\newcommand{\us}{\_}
\theoremstyle{definition}
\newtheorem{example}[equation]{Example}
\newtheorem{gpractice}[equation]{Guided Practice Exercise}
\newtheorem{eoce}{Exercise}[chapter]
\newtheorem*{definition}{Definition}
\newtheorem*{theorem}{Theorem}
\newtheorem*{procedure}{Procedure}
\newtheorem*{condition}{Condition}
\newtheorem*{remark}{Remark}
"""


# ── balanced-argument helpers ─────────────────────────────────────────────

def _arg(s: str, i: int, o: str = "{", c: str = "}") -> tuple[str | None, int]:
    """The group opening at s[i] (after spaces), and the index after it; (None, i) if none."""
    j = i
    while j < len(s) and s[j] in " \t\n":
        j += 1
    if j >= len(s) or s[j] != o:
        return None, i
    depth, k = 0, j
    while k < len(s):
        ch = s[k]
        if ch == "\\":
            k += 2
            continue
        if ch == o:
            depth += 1
        elif ch == c:
            depth -= 1
            if depth == 0:
                return s[j + 1:k], k + 1
        k += 1
    return None, i


def sub_cmd(s: str, name: str, nargs: int, fn, opt: bool = True) -> str:
    """Replace every \\name[opt]{a1}..{an} by fn(opt, [a1..an]) (balanced braces)."""
    pat = re.compile(r"\\" + name + r"(?![A-Za-z@])\*?")
    out, pos = [], 0
    for m in pat.finditer(s):
        if m.start() < pos:
            continue
        j, o = m.end(), None
        if opt:
            o, j = _arg(s, j, "[", "]")
        args = []
        for _ in range(nargs):
            a, j2 = _arg(s, j)
            if a is None:
                break
            args.append(a)
            j = j2
        if len(args) < nargs:
            continue
        out.append(s[pos:m.start()])
        out.append(fn(o, args))
        pos = j
    out.append(s[pos:])
    return "".join(out)


def sub_env(s: str, name: str, fn, nargs: int = 0) -> str:
    """Replace every \\begin{name}{a1}..body..\\end{name} (not nested) by fn(args, body)."""
    pat = re.compile(r"\\begin\{" + re.escape(name) + r"\}")
    end = "\\end{" + name + "}"
    out, pos = [], 0
    while True:
        m = pat.search(s, pos)
        if not m:
            break
        j, args = m.end(), []
        for _ in range(nargs):
            a, j = _arg(s, j)
            args.append(a or "")
        e = s.find(end, j)
        if e < 0:
            break
        out.append(s[pos:m.start()])
        out.append(fn(args, s[j:e]))
        pos = e + len(end)
    out.append(s[pos:])
    return "".join(out)


# ── the boxes ──────────────────────────────────────────────────────────────

_THEOREM_T = re.compile(r"theorem|\blaw\b|\brule\b|formula|\bfacts\b", re.I)
_CONDITION_T = re.compile(r"^conditions?\b|conditions (?:to check|for)|how to verify", re.I)
_PROCEDURE_T = re.compile(r"^(?:hypothesis test|confidence interval|constructing|computing|finding|"
                          r"identifying|diagnostics|model selection|\d+\\?% confidence|inference for)", re.I)
_DEFINING = re.compile(r"\\term|\bis called\b|\bare called\b|\bdefined\b|\bnotation\b", re.I)


def _onebox_env(title: str, body: str) -> str:
    plain = re.sub(r"\\[A-Za-z]+|[{}$]", "", title).strip()
    if _CONDITION_T.search(plain) or re.search(r"conditions to check", plain, re.I):
        return "condition"
    if _THEOREM_T.search(plain):
        return "theorem"
    if _PROCEDURE_T.search(plain):
        return "procedure"
    if _DEFINING.search(body) or _DEFINING.search(title) or len(plain.split()) <= 4:
        return "definition"
    return "remark"


def _box(env: str, title: str, body: str) -> str:
    t = f"[{title.strip()}]" if title and title.strip() else ""
    return f"\\begin{{{env}}}{t}\n{body.strip()}\n\\end{{{env}}}"


def _titled(body: str, cmd: str) -> tuple[str, str]:
    """(title, rest) of a box body that starts with \\cmd[...]{title}."""
    m = re.match(r"\s*\\" + cmd + r"\b", body)
    if not m:
        return "", body
    _, j = _arg(body, m.end(), "[", "]")
    t, j = _arg(body, j)
    return (t or ""), body[j:]


def _eoce(o, args) -> str:
    text = args[0]
    title, label = "", ""
    m = re.search(r"\\qt\b", text)
    if m and not text[:m.start()].strip():
        _, j = _arg(text, m.end(), "[", "]")
        t, j = _arg(text, j)
        if t is not None:
            lm = re.search(r"\\label\{[^}]*\}", t)
            label = lm.group(0) if lm else ""
            title = re.sub(r"\\label\{[^}]*\}", "", t).strip()
            text = text[j:]
    t = f"[{title}]" if title else ""
    return f"\\begin{{eoce}}{t}{label}\n{text.strip()}\n\\end{{eoce}}\n"


# ── one chapter ────────────────────────────────────────────────────────────

_DROP_1 = ["index", "footnotetext", "footfullcite", "CalculatorVideos", "Comment", "Cut", "MarginVideo",
           "textB", "textC", "vspaceB", "hspaceB", "chaptersection", "ec", "videohref", "slideshref",
           "videomarginhref", "sectionvideohref", "sectionslideshref", "subref", "captionsetup"]
_KEEP_1 = {"D": "{}", "Add": "{}", "hiddenterm": "{}", "SimulationAndRandomization": "{}",
           "term": r"\textbf{{{}}}", "termni": r"\textbf{{{}}}", "termO": r"\textbf{{{}}}",
           "highlightO": r"\textbf{{{}}}", "highlightT": r"\emph{{{}}}", "highlight": r"\textbf{{{}}}",
           "resp": r"\texttt{{{}}}", "var": r"\texttt{{{}}}", "data": r"\texttt{{{}}}",
           "datalink": r"\texttt{{{}}}", "calctext": r"\texttt{{{}}}", "calcbutton": r"\texttt{{{}}}",
           "calctextmath": r"\mathtt{{{}}}", "lmlevel": r":~\emph{{{}}}", "qt": r"\textbf{{{}.}}",
           "qtq": r"\textbf{{{}?}}", "urlwofont": r"\url{{{}}}"}
_FIRST_OF_2 = ["termsub", "indexthis", "MultipleRegression", "MultipleRegressionChapter", "ANOVASection",
               "GLMSection"]
_SECOND_OF_2 = ["APVersion", "oiRedirect"]


def convert_chapter(tex: str) -> tuple[str, str]:
    """(title, standard-LaTeX body) of one chapter's source (chapter file + review exercises)."""
    s = tex
    # the chapter heading: \chaptertitle[size]{title} and the labels inside the chapterpage box
    title = ""

    def chapterpage(args, body):
        nonlocal title
        t, _ = _titled(body, "chaptertitle")
        t = t or args[0]
        title = re.sub(r"\s+", " ", re.sub(r"\\titlebreak\s*(\{\})?", " ", t)).strip()
        labels = "".join(re.findall(r"\\label\{[^}]*\}", body))
        return f"\\chapter{{{title}}}{labels}\n"
    s = sub_env(s, "chapterpage", chapterpage, 1)
    s = re.sub(r"\\renewcommand\{\\chapterfolder\}\{[^}]*\}", "", s)
    s = sub_cmd(s, "chapterintro", 1, lambda o, a: a[0] + "\n")
    s = re.sub(r"\\reviewexercisesheader(\[[^\]]*\])?(\{\})?", r"\\section*{Chapter exercises}", s)
    s = re.sub(r"\\exercisesheader(\[[^\]]*\])?(\{\})?", r"\\subsection*{Exercises}", s)
    # Guided Practice solutions
    s = re.sub(r"\\footnotemark(\[[^\]]*\])?", "", s)
    # figures: keep caption and label, drop the image (and its long alt text)
    for name, n in (("Figure", 2), ("Figures", 3), ("Figuress", 3), ("FigureFullPath", 2)):
        s = sub_cmd(s, name, n, lambda o, a: "")
    s = sub_cmd(s, "includegraphics", 1, lambda o, a: "")
    s = sub_cmd(s, "subfigure", 1, lambda o, a: (f"({o})" if o else "") + " ")
    for name in _DROP_1:
        s = sub_cmd(s, name, 1, lambda o, a: "")
    for name, fmt in _KEEP_1.items():
        s = sub_cmd(s, name, 1, lambda o, a, fmt=fmt: fmt.format(a[0]), opt=False)
    for name in _FIRST_OF_2:
        s = sub_cmd(s, name, 2, lambda o, a: a[0], opt=False)
    for name in _SECOND_OF_2:
        s = sub_cmd(s, name, 2, lambda o, a: a[1], opt=False)
    s = sub_cmd(s, "indfunc", 2, lambda o, a: f"\\texttt{{{a[0]}}}_{{\\texttt{{{a[1]}}}}}", opt=False)
    s = re.sub(r"\\(?:titlebreak|newpage|clearpage|stdvspace|stdaddvspace|exspace|warningsymbol)"
               r"(?![A-Za-z])(\{\})?", " ", s)
    s = re.sub(r"\\eoce(?:NeedSolution|Replace|FF)(\[[^\]]*\])?", "", s)
    # the boxes
    for w in ("examplewrap", "exercisewrap", "exampleewrap", "gpewrapper"):
        s = re.sub(r"\\(?:begin|end)\{" + w + r"\}(\{[^}]*\})?", "", s)
    s = sub_env(s, "exercise", lambda a, b: _box("gpractice", "", b))      # older Guided Practice
    s = sub_env(s, "nexercise", lambda a, b: _box("gpractice", "", b))
    s = sub_env(s, "example", lambda a, b: _box("example", "", a[0].strip() + "\n\n" + b), 1)
    s = sub_env(s, "nexample", lambda a, b: _box("example", "", a[0].strip() + "\n\n" + b), 1)
    s = sub_env(s, "onebox", lambda a, b: _box(_onebox_env(a[0], b), a[0], b), 1)
    s = sub_env(s, "tipBox", lambda a, b: _box("remark", *_titled(a[0] + b, "tipBoxTitle")), 1)
    s = sub_env(s, "termBox", lambda a, b: _box("remark", *_titled(a[0] + b, "tBoxTitle")), 1)
    s = sub_env(s, "caution", lambda a, b: _box("remark", "Caution: " + a[0], a[1] + b), 2)
    s = sub_cmd(s, "eoce", 2, _eoce)
    for env, std, opt in (("parts", "enumerate", ""), ("subparts", "enumerate", ""),
                          ("romanparts", "enumerate", ""), ("cond", "enumerate", ""), ("hyp", "itemize", "")):
        s = s.replace(f"\\begin{{{env}}}", f"\\begin{{{std}}}{opt}").replace(f"\\end{{{env}}}", f"\\end{{{std}}}")
    s = re.sub(r"\\begin\{(?:multicols)\}\{\d+\}|\\end\{multicols\}", "", s)
    s = re.sub(r"\\begin\{adjustwidth\}\{[^}]*\}\{[^}]*\}|\\end\{adjustwidth\}", "", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return title, s.strip() + "\n"


def chapters_of(src: Path) -> list[tuple[int, str]]:
    main = (src / "main.tex").read_text(encoding="utf-8", errors="replace")
    main = re.sub(r"(?<!\\)%.*", "", main)
    return [(int(n), d) for n, d in re.findall(r"\\includechapter\{(\d+)\}\{([^}]+)\}", main)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", help="the book's folder (with main.tex)")
    ap.add_argument("out")
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    labels, toc, converted = {}, [], []
    for k, folder in chapters_of(src):
        tex = read_tex(str(src / folder / "TeX" / f"{folder}.tex"), src)
        rev = src / folder / "TeX" / "review_exercises.tex"
        if rev.is_file():
            tex += "\n" + read_tex(str(rev), src)
        converted.append((k, folder, *convert_chapter(tex)))
    # the chapters' data macros (\newcommand{\fashN}{1822}) are defined in the body; one that a
    # later chapter reuses is copied into that chapter's preamble
    defs = {}
    for _, _, _, body in converted:
        for m in re.finditer(r"\\newcommand\{?\\([A-Za-z]+)\}?", body):
            o, j = _arg(body, m.end(), "[", "]")
            a, j = _arg(body, j)
            if a is not None:
                defs.setdefault(m.group(1), body[m.start():j])
    for k, folder, title, body in converted:
        own = set(re.findall(r"\\newcommand\{?\\([A-Za-z]+)", body))
        used = set(re.findall(r"\\([A-Za-z]+)", body))
        extra = "".join(defs[n] + "\n" for n in sorted((used & defs.keys()) - own))
        f = out / f"ch{k:02d}.tex"
        f.write_text(f"{PREAMBLE}{extra}\n\\begin{{document}}\n\\setcounter{{chapter}}{{{k - 1}}}\n{body}\n\\end{{document}}\n",
                     encoding="utf-8")
        facts = extract_facts(read_tex(str(f)))
        by_label = {lab: x for x in facts["facts"] for lab in x["labels"]}
        for lab, v in facts["labels"].items():
            x = by_label.get(lab, {})
            labels[lab] = {"chapter": k, "number": v["number"], "kind": v["kind"], "type": x.get("type"),
                           "display": x.get("display"), "name": x.get("optarg")}
        toc.append({"chapter": k, "file": f.name, "title": title, "facts": len(facts["facts"]),
                    "chars": len(body), "source": folder})
        print(f"ch{k:02d} {len(facts['facts']):4d} facts {len(body) // 1000:5d}K chars  {title[:60]}")
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=0))
    (out / "chapters.json").write_text(json.dumps({"main": str(src / "main.tex"), "chapters": toc}, indent=1))
    print(f"{len(toc)} chapters, {len(labels)} labels -> {out}")


if __name__ == "__main__":
    main()
