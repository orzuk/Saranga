"""Multi-line displays: one equation fact per equation (latex_facts._split_rows).

Runs without pytest:  python3 tests/test_align_rows.py

An align whose numbered rows have their own left-hand sides is several equations; a
chain ("x &= y \\\\ &= z") is one, whatever its numbering.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from latex_facts import extract_facts  # noqa: E402
from extraction_finalize import _key  # noqa: E402

FAILS = []


def eqs(body, pre=""):
    fx = extract_facts("\\documentclass{article}\n" + pre + "\\begin{document}\n" + body + "\n\\end{document}")
    src = fx["source"]
    out = [f for f in fx["facts"] if f["kind"] == "equation"]
    for f in out:
        if _key(f["statement"]) not in _key(src):
            FAILS.append(f"not verbatim: {f['statement']!r}")
        if not (f["outer_start"] <= f["start"] <= f["end"] <= f["outer_end"]):
            FAILS.append(f"bad span {f['id']}")
    ids = [f["id"] for f in fx["facts"]]
    if len(ids) != len(set(ids)):
        FAILS.append(f"duplicate fact ids {ids}")
    return out, fx


def check(ok, what):
    if not ok:
        FAILS.append(what)


def shape(fs):
    return [(f["number"], f["labels"]) for f in fs]


# separate equations
fs, fx = eqs("\\begin{align}\na &= b \\label{e1}\\\\\nc &= d \\label{e2}\n\\end{align}\nBy \\eqref{e2} done.")
check(shape(fs) == [("1", ["e1"]), ("2", ["e2"])], f"separate: {shape(fs)}")
check(fs[0]["statement"].strip().startswith("a &= b") and "c &= d" in fs[1]["statement"]
      and "c &= d" not in fs[0]["statement"], f"separate spans: {[f['statement'] for f in fs]}")
check(fx["labels"]["e2"]["id"] == fs[1]["id"] and fx["labels"]["e2"]["number"] == "2", "label e2 -> second fact")
check([r["target"] for r in fx["refs"] if r["key"] == "e2"] == [fs[1]["id"]], "ref to e2 resolves to second fact")
check(fs[0]["outer_start"] < fs[0]["start"] and fs[-1]["outer_end"] > fs[-1]["end"], "outer span on first/last")
check(len(fx["displays"]) == 1, "the display stays one display")

# a chain, numbered on every row: one fact with both labels
fs, fx = eqs("\\begin{align}\nx &= y \\label{c1}\\\\\n &\\le z \\label{c2}\\\\\n &= w\n\\end{align}")
check(len(fs) == 1 and fs[0]["labels"] == ["c1", "c2"], f"chain: {shape(fs)}")
check(fx["labels"]["c2"]["id"] == fs[0]["id"] and fx["labels"]["c2"]["number"] == "2", "chain label keeps its number")

# mixed: a chain, then a new equation
fs, _ = eqs("\\begin{align}\na &= b \\\\\n &= c \\label{m1}\\\\\nd &= e \\label{m2}\n\\end{align}")
check(shape(fs) == [("1", ["m1"]), ("3", ["m2"])] or shape(fs) == [("1", []), ("3", ["m2"])] or len(fs) == 2,
      f"mixed: {shape(fs)}")
check(len(fs) == 2 and "a &= b" in fs[0]["statement"] and "&= c" in fs[0]["statement"], "mixed: chain kept together")

# an unnumbered row with its own left-hand side joins the next numbered one
fs, _ = eqs("\\begin{align}\na &= b \\nonumber\\\\\nc &= d \\label{n1}\\\\\ne &= f \\label{n2}\n\\end{align}")
check(shape(fs) == [("1", ["n1"]), ("2", ["n2"])] and "a &= b" in fs[0]["statement"], f"nonumber row: {shape(fs)}")

# a label on a \notag row takes the next numbered row's number (amsmath)
fs, fx = eqs("\\begin{align}\na &= b \\notag \\label{t1}\\\\\n &= c\\\\\nd &= e \\label{t2}\n\\end{align}")
check(len(fs) == 2 and fx["labels"]["t1"]["id"] == fs[0]["id"], f"notag label: {shape(fs)}")

# not split: align*, one numbered row, equation with split/aligned, numcases
for body in ["\\begin{align*}\na &= b\\\\\nc &= d\n\\end{align*}",
             "\\begin{align}\na &= b \\nonumber\\\\\nc &= d \\label{s1}\n\\end{align}",
             "\\begin{equation}\\label{q}\\begin{split}a &= b\\\\ c &= d\\end{split}\\end{equation}",
             "\\begin{equation}\\label{q2}\\begin{aligned}a &= b\\\\ c &= d\\end{aligned}\\end{equation}"]:
    fs, _ = eqs(body)
    check(len(fs) <= 1, f"should not split: {body[:40]!r} -> {shape(fs)}")
fs, _ = eqs("\\begin{align}\na &= b\\\\\nc &= d\n\\end{align}")
check(len(fs) == 2, f"two numbered rows without labels are two equations: {shape(fs)}")

# split inside an align row: its \\ are not rows of the align
fs, _ = eqs("\\begin{align}\n\\begin{split} a &= b\\\\ &= c \\end{split} \\label{p1}\\\\\nd &= e \\label{p2}\n\\end{align}")
check(shape(fs) == [("1", ["p1"]), ("2", ["p2"])], f"split in an align row: {shape(fs)}")

# subequations, gather, eqnarray, \intertext, a cite and a ref inside a row
fs, _ = eqs("\\begin{subequations}\\label{sub}\\begin{align}\na &= b \\label{s_a}\\\\\nc &= d \\label{s_b}\n"
            "\\end{align}\\end{subequations}")
check(shape(fs) == [("1a", ["s_a"]), ("1b", ["s_b"])], f"subequations: {shape(fs)}")
fs, _ = eqs("\\begin{gather}\na = b \\label{g1}\\\\\nc = d \\label{g2}\n\\end{gather}")
check(len(fs) == 2, f"gather: {shape(fs)}")
fs, _ = eqs("\\begin{eqnarray}\na &=& b \\label{r1}\\\\\n &=& c \\label{r2}\\\\\nd &=& e \\label{r3}\n\\end{eqnarray}")
check([f["labels"] for f in fs] == [["r1", "r2"], ["r3"]], f"eqnarray: {shape(fs)}")
fs, _ = eqs("\\begin{align}\na &= b \\label{i1}\\\\\n\\intertext{and}\nc &= d \\label{i2}\n\\end{align}")
check(len(fs) == 2 and "intertext" not in fs[1]["statement"], f"intertext: {[f['statement'] for f in fs]}")
fs, fx = eqs("\\begin{align}\na &= b \\label{k1}\\\\\nc &= d \\cite{Foo} \\eqref{k1} \\label{k2}\n\\end{align}")
check(fs[1]["cites"] == ["Foo"] and fs[0]["cites"] == [] and fs[1]["refs"] == ["k1"], f"cites/refs per row: {fs}")
check([r["in"] for r in fx["refs"] if r["key"] == "k1"] == [fs[1]["id"]], "ref 'in' is the row's fact")

# inside a theorem: the equation facts keep the theorem as parent
fs, fx = eqs("\\begin{theorem}\\label{T}We have\n\\begin{align}\na &= b \\label{h1}\\\\\nc &= d \\label{h2}\n"
             "\\end{align}\n\\end{theorem}", pre="\\newtheorem{theorem}{Theorem}\n")
thm = next(f for f in fx["facts"] if f["kind"] == "theorem_env")
check(len(fs) == 2 and all(f["parent"] == thm["id"] for f in fs), "parent of row facts")
check(fx["labels"]["T"]["id"] == thm["id"], "theorem label untouched")

if FAILS:
    print("\n".join(map(str, FAILS)))
    sys.exit(1)
print("align rows: ok")
