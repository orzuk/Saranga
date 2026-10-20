#!/usr/bin/env python3
"""Regression checks for the parser's edge builder: which result a proof
proves, and which references are mentions rather than dependencies.

    python3 tests/test_edge_builder.py
"""
import contextlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src", "LLMVersion"))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from math_paper_parser import PaperParser            # noqa: E402
from validate_annotation import reasoning_cycles     # noqa: E402

TEX = r"""
\documentclass{article}
\newtheorem{proposition}{Proposition}
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}{Lemma}
\begin{document}
\section{Rules}
\begin{proposition}\label{p:one}
If $f$ is differentiable then \begin{equation}\label{eq:one} f^* = g. \end{equation}
\end{proposition}
\begin{proof}
A direct computation.
\end{proof}
\begin{proposition}\label{p:two}
If $f$ and $g$ are differentiable then $fg$ is differentiable.
\end{proposition}
\begin{proof}
Using \eqref{eq:one} and Proposition~\ref{p:one} the product rule follows.
\end{proof}
\begin{theorem}\label{t:main}
Every bounded sequence has a convergent subsequence, as eventually proved in Theorem~\ref{t:late}.
\end{theorem}
\begin{proof}
We argue as in the proof of Theorem~\ref{t:late}, and the assumptions of Theorem~\ref{t:late} hold.
\end{proof}
\begin{theorem}\label{t:late}
Compact sets are closed.
\end{theorem}
\begin{proof}
By Theorem~\ref{t:main} the claim follows.
\end{proof}
\begin{lemma}\label{l:aux}
Closed subsets of compact sets are compact.
\end{lemma}
\begin{theorem}\label{t:own}
Continuous images of compact sets are compact.
\end{theorem}
\begin{proof}
Theorem~\ref{t:own} follows from Lemma~\ref{l:aux}.
\end{proof}
\end{document}
"""


def parse():
    with tempfile.TemporaryDirectory() as tmp:
        empty = os.path.join(tmp, "rules")
        os.mkdir(empty)
        path = os.path.join(tmp, "paper.tex")
        with open(path, "w") as f:
            f.write(TEX)
        with contextlib.redirect_stdout(io.StringIO()):
            g = PaperParser(paper_id="t", extraction_mode="rules", rules_dir=empty).parse_file(path)
        return g.to_unified_dict(include_research_fields=True)


def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        sys.exit(1)


d = parse()
by_label = {n.get("label"): n["id"] for n in d["nodes"] if n.get("label")}
proves = {}
for e in d["edges"]:
    if e.get("type") == "proves":
        proves.setdefault(e["source"], e["target"])
for n in d["nodes"]:
    if n["type"] == "proof" and n.get("proves"):
        proves.setdefault(n["id"], n["proves"])
proved = sorted(proves.values())

# The proof right after Proposition 2 proves Proposition 2, although it cites
# an equation of Proposition 1 first.
check(proved.count(by_label["p:two"]) == 1, "the product-rule proof proves p:two, got %s" % proves)
check(proved.count(by_label["p:one"]) == 1, "p:one has exactly its own proof, got %s" % proves)

# "as in the proof of", "the assumptions of", "as eventually proved in" are
# mentions; "By Theorem" is a use.
late, main = by_label["t:late"], by_label["t:main"]
ment = [e for e in d["edges"] if e.get("mention")]
check(any(e["source"] == late for e in ment), "references to t:late are mentions")
check(not reasoning_cycles(d["nodes"], d["edges"]),
      "no cycle: t:late uses t:main, t:main only mentions t:late")

# A proof that names the result it proves ("Theorem \ref{t:own} follows from ...") still
# proves it: the reference is not a use (it used to close a 2-cycle with 'proves', and the
# cycle breaker dropped 'proves', which cut Lemma l:aux off from the theorem).
own, aux = by_label["t:own"], by_label["l:aux"]
check(proved.count(own) == 1, "the last proof proves t:own, got %s" % proves)
pf = next(p for p, r in proves.items() if r == own)
check(not any(e["source"] == own and e["target"] == pf for e in d["edges"]), "t:own is not used by its own proof")
check(any(e["source"] == aux and e["target"] == pf for e in d["edges"]), "l:aux is used by the proof of t:own")
print("all edge-builder checks pass")

# The learned definition -> user edges (alg3/edges.py) are opt-in: the parser's own edges
# above are what every parse gets by default. Their deterministic part: a definition's
# candidates, and which other text uses them (exact symbol, head symbol, whole words).
sys.path.insert(0, os.path.join(HERE, "..", "alg3"))
import edges as E                                    # noqa: E402
cs = {c["key"]: c for c in E.candidates(
    r"A partially ordered set or \emph{poset} is a set $P$ with an order. We call $T_p=(t_{vu})$ the transfer matrix.")}
check({"poset", "T_p", "transfer matrix"} <= set(cs), "definition candidates: %s" % sorted(cs))
user = r"Every finite poset $Q$ has a transfer matrix $T_q$."
mn, w = E.math_regions(user), E.wnorm(user)
check(E.uses(cs["poset"], user, mn, w) == "word", "a defined word is used as a word")
check(E.uses(cs["T_p"], user, mn, w) == "head", "T_q uses the head symbol of T_p")
check(E.uses(cs["P"], user, mn, w) is None, "a lone P is not in this text")
print("all learned-edge checks pass")
