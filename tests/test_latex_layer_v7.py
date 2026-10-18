"""The v7 fixes to the LaTeX layer, from the v6 agents' extraction notes.

Runs without pytest:  python3 tests/test_latex_layer_v7.py

- proof labels with inline math ("\\textbf{Estimate of $A$.}", "{\\bf $C_4$-freeness.}") and
  $(1)$-style part labels; an emphasised sentence is not a label;
- algorithm2e under [algo2e] (environment algorithm2e) and "\\begin {algorithm}" with a space;
- the else-branch of \\eIf has a span, so the enclosing loop spans both branches;
- a capitalised sentence after a display with no period counts as a new sentence (step rule 9).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import proof_structure as P  # noqa: E402
from algorithm_lines import find_blocks  # noqa: E402

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

if FAILS:
    print("\n".join(FAILS))
    sys.exit(1)
print("latex layer v7: ok")
