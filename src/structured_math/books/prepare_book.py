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
import copy
import json
import re
import sys
import xml.etree.ElementInclude as EI
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from latex_facts import extract_facts, read_tex          # noqa: E402
from structured_math.books.pretext_to_latex import PREAMBLE, conv, conv_title, index_targets   # noqa: E402

_UNIT = r"\\%s\*?\s*(?:\[[^\]]*\])?\s*\{"            # a chapter, or a section of a book in sections
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
    pre = PREAMBLE
    if any(e.tag == "acroref" for e in root.iter()):
        pre += _beezer_dialect(root, main.parent)
    _group_intros(root)
    _webwork_statics(root, main)
    index_targets(root)
    chapters = [e for e in root.iter() if e.tag.split("}")[-1] == "chapter"]
    out = []
    for c in chapters:
        t = c.find("title")
        out.append((conv_title(t), re.sub(r"\n{3,}", "\n\n", conv(c))))
    return pre, out


def _group_intros(root: ET.Element) -> None:
    """An exercise group's instructions ("For C10-C19, find all solutions ...") copied into each
    of its exercises, which are otherwise bare systems or matrices."""
    for g in root.iter("exercisegroup"):
        intro = [c for c in g if c.tag in ("introduction", "p")]
        for c in intro:
            g.remove(c)
        for ex in (c for c in g if c.tag == "exercise"):
            at = 1 if len(ex) and ex[0].tag == "title" else 0
            for i, c in enumerate(intro):
                c = copy.deepcopy(c)
                c.tail = None
                ex.insert(at + i, c)


def _webwork_statics(root: ET.Element, main: Path) -> None:
    """A WeBWorK exercise that names a server problem (<webwork source="....pg"/>) gets the
    problem's text from the static version PreTeXt generated (generated-assets/.../webwork-representations.xml)."""
    reps = next((f for d in list(main.parents)[:3]
                 for f in sorted(d.glob("generated-assets/*/webwork/webwork-representations.xml"))), None)
    if reps is None:
        return
    static = {st.get("source"): st for st in ET.parse(reps).getroot().iter("static") if st.get("source")}
    for w in root.iter("webwork"):
        st = static.get(w.get("source"))
        if st is not None and not len(w):
            w.extend(copy.deepcopy(list(st)))


def _archetype_parts(root: ET.Element, src: Path) -> None:
    """<archetypepart acro="A" part="augmented"/> replaced by that part of Archetype A
    (archetypes.xml, not included in the book's chapters)."""
    f = src / "archetypes.xml"
    if not f.is_file():
        return
    arch = {a.get("acro"): a for a in ET.parse(f).getroot().iter("archetype")}
    for parent in list(root.iter()):
        for c in parent:
            if c.tag != "archetypepart":
                continue
            part = arch.get(c.get("acro"))
            part = part.find(c.get("part")) if part is not None else None
            tail = c.tail
            c.clear()
            c.tag, c.tail = "span", tail
            if part is not None:
                c.text = part.text
                c.extend(copy.deepcopy(list(part)))


def _beezer_dialect(root: ET.Element, src: Path) -> str:
    """Rewrite Beezer's older dialect (acro ids, acroref, $ math, alignmath, define, archetypes)
    as PreTeXt in place; returns its LaTeX macros for the preamble. Ids are the acronym with the
    kind ("theorem-RREF"), because sections, definitions and theorems reuse acronyms."""
    import structured_math.books.pretext_to_latex as P
    P.DOLLAR_MATH = True
    _archetype_parts(root, src)
    kind = {"sageadvice": "sage"}
    macros = "".join(x.text or "" for m in root.iter("macros") for x in m.iter("latex"))
    for parent in list(root.iter()):
        for e in list(parent):
            if e.tag == "macros":
                parent.remove(e)
    rel = {"implyforward": "($\\Rightarrow$) ", "implyreverse": "($\\Leftarrow$) ", "ie": "i.e.", "eg": "e.g."}
    parent = {c: e for e in root.iter() for c in e}
    parent_tag = {c: e.tag for c, e in parent.items()}
    for e in root.iter():
        if e.get("acro") and not e.get(P.XI) and e.tag not in ("acroref", "exercise"):
            e.set(P.XI, kind.get(e.tag, e.tag) + "-" + e.get("acro"))
        if e.tag == "acroref" and e.get("type") == "archetype":     # the archetypes are not in the book
            e.tag, e.text, e.attrib = "span", "Archetype " + e.get("acro", ""), {}
        elif e.tag == "acroref":
            t = {"solution": "exercise"}.get(e.get("type"), e.get("type"))
            e.tag, e.attrib = "xref", {"ref": f"{t}-{e.get('acro', '')}", "kind": {"sage": "sageadvice"}.get(t, t)}
        elif e.tag == "miscref":
            e.tag, e.text, e.attrib = "span", e.get("text", ""), {}
        elif e.tag == "problem" and parent_tag.get(e) == "exercise":
            e.tag = "span"                       # the exercise is the environment, not its problem
        elif e.tag in ("alignmath", "equation"):
            body = (e.text or "") + "".join((f"\\ref{{{c.get('type')}-{c.get('acro')}}}" if c.tag == "acroref"
                                             else "".join(c.itertext()) if c.tag == "span" else "")
                                            + (c.tail or "") for c in e)
            for c in list(e):
                e.remove(c)
            e.text = "\\begin{aligned}" + body + "\\end{aligned}" if e.tag == "alignmath" else body
            e.tag = "men" if e.get(P.XI) else "me"
        elif e.tag == "define":
            e.tag = "term"
        elif e.tag in rel:
            e.text, e.tag = rel[e.tag], "span"
        elif e.tag == "exercise" and e.get("number") and not e.get(P.XI):
            sec = e
            while sec is not None and sec.tag != "section":
                sec = parent.get(sec)
            pre = (sec.get("acro") + ".") if sec is not None and sec.get("acro") else ""
            e.set(P.XI, "exercise-" + pre + e.get("type", "") + e.get("number"))    # the book cites SSLE.M40
    return "\n" + macros + "\n"


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


def latex_book(main: Path, level: str = "chapter") -> tuple[str, list[tuple[str, str]]]:
    tex = read_tex(str(main))
    i = tex.find("\\begin{document}")
    pre, body = _inline_sty(tex[:i], main.parent, set()), tex[i + len("\\begin{document}"):]
    unit = re.compile(_UNIT % level)
    starts = [m.start() for m in unit.finditer(body)]
    end = _END.search(body, starts[-1]) if starts else None
    bounds = starts + [end.start() if end else len(body)]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        m = unit.match(body, a)
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
    ap.add_argument("--level", default="chapter", help="LaTeX unit to split at: chapter, or section")
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    main_f = Path(a.main) if a.main else find_pretext_main(src)
    pre, chapters = latex_book(main_f, a.level) if main_f.suffix == ".tex" else pretext_book(main_f)
    out.mkdir(parents=True, exist_ok=True)
    labels, toc = {}, []
    for k, (title, body) in enumerate(chapters, 1):
        f = out / f"ch{k:02d}.tex"
        f.write_text(f"{pre}\n\\begin{{document}}\n\\setcounter{{{a.level}}}{{{k - 1}}}\n{body}\n\\end{{document}}\n",
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
