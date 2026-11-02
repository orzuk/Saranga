"""A textbook's source as one LaTeX file per chapter, plus the book's label table, for the
v7-books extractor (scripts/opus_extract_prompt_v7_books.md).

    python -m structured_math.books.prepare_book SRC OUT [--main FILE]

SRC is a PreTeXt book (the .ptx/.xml file whose root holds <book>, found when --main is not
given) or a LaTeX book (--main main.tex). OUT gets chNN.tex (the book's preamble, the chapter,
\\setcounter so the chapter prints its own number) and labels.json, which maps every \\label of
the book to {chapter, number, kind, type, display, name}; a chapter's \\ref to another chapter
is resolved from it when the book is assembled.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementInclude as EI
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from latex_facts import extract_facts, read_tex          # noqa: E402
from structured_math.books.pretext_to_latex import PREAMBLE, conv, conv_title   # noqa: E402

_CHAPTER = re.compile(r"\\chapter\*?\s*(?:\[[^\]]*\])?\s*\{")
_END = re.compile(r"\\(?:appendix|backmatter|end\{document\}|printbibliography|bibliography\{)")
_STY = re.compile(r"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]*)\}")


def find_pretext_main(src: Path) -> Path:
    """The file whose root holds <book>; of several, the one with most includes (not a sample,
    exercises-only or solutions edition)."""
    found = []
    for f in sorted(src.rglob("*")):
        if (f.suffix in (".ptx", ".xml") and "publi" not in f.parts[-2] and f.stat().st_size < 5e6
                and not re.search(r"sample|exercise|solution|workbook", f.name)):
            head = f.read_text(encoding="utf-8", errors="replace")
            if re.search(r"<book[\s>]", head[:20000]):
                found.append((head.count("include"), f))
    if not found:
        raise SystemExit(f"{src}: no PreTeXt file with <book>")
    return max(found, key=lambda x: x[0])[1]


def pretext_book(main: Path) -> tuple[str, list[tuple[str, str]]]:
    """(preamble, [(title, LaTeX body)] per chapter) of a PreTeXt book."""
    root = ET.parse(main).getroot()
    def loader(href, parse, encoding=None):            # a missing include (unpublished exercises) is empty
        try:
            return EI.default_loader(href, parse, encoding)
        except FileNotFoundError:
            print("missing include:", href, file=sys.stderr)
            return ET.Element("missing") if parse == "xml" else ""
    EI.include(root, loader=loader, base_url=str(main.resolve()), max_depth=10)
    chapters = [e for e in root.iter() if e.tag.split("}")[-1] == "chapter"]
    out = []
    for c in chapters:
        t = c.find("title")
        out.append((conv_title(t), re.sub(r"\n{3,}", "\n\n", conv(c))))
    return PREAMBLE, out


def _inline_sty(pre: str, base: Path, seen: set) -> str:
    """The book's own .sty files inlined, so its \\newtheorem and macros reach latex_facts."""
    def one(m):
        out = [m.group(0)]
        for name in m.group(1).split(","):
            f = base / f"{name.strip()}.sty"
            if f.is_file() and f not in seen:
                seen.add(f)
                out.append(_inline_sty(read_tex(str(f), base), base, seen))
        return "\n".join(out)
    return _STY.sub(one, pre)


def latex_book(main: Path) -> tuple[str, list[tuple[str, str]]]:
    tex = read_tex(str(main))
    i = tex.find("\\begin{document}")
    pre, body = _inline_sty(tex[:i], main.parent, set()), tex[i + len("\\begin{document}"):]
    starts = [m.start() for m in _CHAPTER.finditer(body)]
    end = _END.search(body, starts[-1]) if starts else None
    bounds = starts + [end.start() if end else len(body)]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        m = _CHAPTER.match(body, a)
        depth, j = 1, m.end()
        while depth and j < len(body):
            depth += {"{": 1, "}": -1}.get(body[j], 0)
            j += 1
        out.append((body[m.end():j - 1].strip(), body[a:b]))
    return pre, out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--main", help="the main .tex (LaTeX book) or .ptx (PreTeXt book)")
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    main_f = Path(a.main) if a.main else find_pretext_main(src)
    pre, chapters = (latex_book if main_f.suffix == ".tex" else pretext_book)(main_f)
    out.mkdir(parents=True, exist_ok=True)
    labels, toc = {}, []
    for k, (title, body) in enumerate(chapters, 1):
        f = out / f"ch{k:02d}.tex"
        f.write_text(f"{pre}\n\\begin{{document}}\n\\setcounter{{chapter}}{{{k - 1}}}\n{body}\n\\end{{document}}\n",
                     encoding="utf-8")
        facts = extract_facts(read_tex(str(f)))
        by_label = {lab: x for x in facts["facts"] for lab in x["labels"]}
        for lab, v in facts["labels"].items():
            x = by_label.get(lab, {})
            labels[lab] = {"chapter": k, "number": v["number"], "kind": v["kind"], "type": x.get("type"),
                           "display": x.get("display"), "name": x.get("optarg")}
        toc.append({"chapter": k, "file": f.name, "title": title, "facts": len(facts["facts"]),
                    "chars": len(body)})
        print(f"ch{k:02d} {len(facts['facts']):4d} facts {len(body) // 1000:5d}K chars  {title[:60]}")
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=0))
    (out / "chapters.json").write_text(json.dumps({"main": str(main_f), "chapters": toc}, indent=1))
    print(f"{len(chapters)} chapters, {len(labels)} labels -> {out}")


if __name__ == "__main__":
    main()
