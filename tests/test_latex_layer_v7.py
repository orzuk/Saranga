"""The v7 fixes to the LaTeX layer, from the v6 agents' extraction notes.

Runs without pytest:  python3 tests/test_latex_layer_v7.py

- proof labels with inline math ("\\textbf{Estimate of $A$.}", "{\\bf $C_4$-freeness.}") and
  $(1)$-style part labels; an emphasised sentence is not a label;
- algorithm2e under [algo2e] (environment algorithm2e) and "\\begin {algorithm}" with a space;
- the else-branch of \\eIf has a span, so the enclosing loop spans both branches;
- a capitalised sentence after a display with no period counts as a new sentence (step rule 9);
- code review 2026-10-19: chapter numbering, a \\label in a nested aligned, \\eqno labels, the step
  checker (immediate sentences, ';', "non-trivial", claim/case openers, Proof/Remark headings),
  enumerate pseudocode under algorithm2e, \\SetNlSty arguments, the brace reader at \\\\}.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import proof_structure as P  # noqa: E402
from algorithm_lines import find_blocks  # noqa: E402
from latex_facts import extract_facts  # noqa: E402
from latex_macros import _read_group  # noqa: E402

FAILS = []


def check(ok, what):
    if not ok:
        FAILS.append(what)


body = ("First we split.\n\n\\textbf{Estimate of $A$.} This is small.\n\n"
        "{\\bf $\\mathbf{C_4}$-freeness.} No four-cycle.\n\n{\\em Let $D$ be a curve.} Then more.")
texts = [l["text"] for l in P.detect(body)["labels"]]
check(any("Estimate of $A$" in t for t in texts), f"textbf heading with math: {texts}")
check(any("freeness" in t for t in texts), f"bf switch heading with math: {texts}")
check(not any("Let $D$" in t for t in texts), f"emphasised sentence taken as a label: {texts}")
texts = [l["text"] for l in P.detect("$(1)$ It is easy to see.\n\n$(2)$ Similar to $(1)$.")["labels"]]
check(texts == ["$(1)$", "$(2)$"], f"$(1)$ labels: {texts}")

pre = "\\usepackage[algo2e,linesnumbered]{algorithm2e}\n"
blocks = find_blocks(pre + "\\begin{algorithm2e}\n$x \\gets 0$\\;\n\\Return{$x$}\\;\n\\end{algorithm2e}")
check(len(blocks) == 1 and len(blocks[0].lines) == 2, f"algorithm2e env: {[len(b.lines) for b in blocks]}")
blocks = find_blocks("\\usepackage{algorithm2e}\n\\begin {algorithm}\n$x \\gets 0$\\;\n\\end {algorithm}")
check(len(blocks) == 1, "\\begin {algorithm} with a space")
src = ("\\usepackage{algorithm2e}\n\\begin{algorithm}\n\\For{$i$}{\n\\eIf{$c$}{$a$\\;}{$b$\\;\n$d$\\;}\n}\n"
       "\\end{algorithm}")
lines = find_blocks(src)[0].lines
kinds = [ln.kind for ln in lines]
check(kinds == ["for", "if", "state", "else", "state", "state"], f"eIf lines: {kinds}")
els = lines[kinds.index("else")]
check(els.start is not None and lines[0].end >= lines[-1].end, "else has a span and the loop spans the else-branch")
check(lines[4].parent == kinds.index("else"), "else-branch lines are children of the else")

check(P._sentences("We have \\[ a=b \\] Hence $x$ holds. Therefore $y$.") == 3, "sentence after a display")
check(P._sentences("We have \\[ a=b \\] where $a$ is real. Hence $y$.") == 2, "where-clause after a display")
check(P._sentences("Since $x$ We get it.") == 1, "inline math does not end a sentence")

fx = extract_facts(r"""\documentclass{book}\newtheorem{theorem}{Theorem}[section]\begin{document}
\chapter{A}\section{X}\chapter{B}\section{Y}\begin{theorem}\label{t}T\end{theorem}
\begin{equation}a\label{e}\end{equation}\appendix\chapter{C}\section{Z}\end{document}""")
check([s["number"] for s in fx["sections"]] == ["1", "1.1", "2", "2.1", "A", "A.1"], f"chapters: {fx['sections']}")
check(fx["labels"]["t"]["number"] == "2.1.1" and fx["labels"]["e"]["number"] == "2.1", "numbers within chapters")
fx = extract_facts("\\documentclass{article}\\begin{document}\\begin{align}\\begin{aligned}a&=b\\label{x}"
                   "\\end{aligned}\\\\[2pt] c&=d\\label{y}\\end{align}\\end{document}")
check([(f["labels"], f["statement"]) for f in fx["facts"]] == [(["x"], "\\begin{aligned}a&=b\\end{aligned}"),
                                                             (["y"], "c&=d")], f"nested label, row start: {fx['facts']}")
fx = extract_facts(r"\documentclass{article}\begin{document}\section{A} $$a=b\label{q}\eqno(3)$$ By \ref{q}.\end{document}")
check(fx["labels"]["q"]["number"] == "3" and fx["refs"][0]["target"] == fx["labels"]["q"]["id"], "eqno label")
body = "Let $G$ be a graph on $n$ vertices. Clearly $G$ has an edge. Then we count; then we bound it."
errs, _ = P.check_steps(body, {"labels": []}, [{"id": "s1", "statement": "Let $G$ be a graph on $n$ vertices. Clearly $G$ has an edge."},
                                               {"id": "s2", "statement": "Then we count;"},
                                               {"id": "s3", "statement": "then we bound it."}])
check(errs == ["s3: step starts mid-sentence (after ';')"], f"step checker: {errs}")
check(not P._IMMEDIATE.search("a non-trivial subgroup") and P._CLAIM.search("We now show that x")
      and P._CASE_OPENER.match("In the other case"), "immediate words, claim and case openers")
check([l["text"] for l in P.detect("A.\n\n{\\bf Proof.} x. {\\bf Remark 2.} y.\n\n\\textbf{Step 1.} z.")["labels"]]
      == ["\\textbf{Step 1."], "Proof/Remark headings are not step labels")
blocks = find_blocks("\\usepackage{algorithm2e}\n\\begin{algorithm}\\begin{enumerate}\\item A.\\item B.\\end{enumerate}"
                     "\\end{algorithm}")
check([l.number for b in blocks for l in b.lines] == [1, 2], "enumerate pseudocode under algorithm2e")
blocks = find_blocks("\\usepackage[linesnumbered]{algorithm2e}\n\\begin{algorithm}\\SetNlSty{textbf}{}{:}\n"
                     "$x \\gets 0$\\;\n\\end{algorithm}")
check([l.content for b in blocks for l in b.lines] == ["$x \\gets 0$"], "SetNlSty arguments skipped")
check(_read_group(r"{a\\}b}", 0) == ("a\\\\", 5), "brace reader at \\\\}")

if FAILS:
    print("\n".join(FAILS))
    sys.exit(1)
print("latex layer v7: ok")
