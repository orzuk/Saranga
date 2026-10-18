"""The v7 additions to the finishing step (src/extraction_finalize.py).

Runs without pytest:  python3 tests/test_finalize_v7.py

On a small paper: display/number from the environment, cites, edge basis (ref, syntax),
a proof step with a claim's span merged into the claim, a restated copy's \\label
resolving to the one node, a result stated inside a proof and used outside it, and a
prose proof that fills a section with subsections.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from extraction_finalize import finalize  # noqa: E402

TEX = r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}[theorem]{Lemma}
\begin{document}
\section{Introduction}
Our main result is the following.
\begin{theorem}\label{t:intro}
Every finite group of odd order is solvable.
\end{theorem}
\section{Results}
\begin{lemma}\label{l:a}
Every group of prime order is cyclic, see \cite{Lag, Cau}.
\end{lemma}
\begin{theorem}\label{t:main}
Every finite group of odd order is solvable.
\end{theorem}
\begin{proof}
By Lemma \ref{l:a} we may assume the order is composite. We claim that the group has a normal subgroup. Indeed, take a Sylow subgroup and count. This proves the claim. The rest follows by induction.
\end{proof}
Theorem \ref{t:intro} has many consequences. Every abelian group is solvable.
\section{Proof of the second result}
We prove it in two steps.
\subsection{The setup}
Let $G$ be abelian. Its derived subgroup is trivial.
\subsection{The end}
Hence $G$ is solvable.
\section{Later}
The claim in the proof of Theorem \ref{t:main} is used again here.
\end{document}
"""


def build():
    claim = "We claim that the group has a normal subgroup."
    claim_span = claim + " Indeed, take a Sylow subgroup and count. This proves the claim."
    proof = ("By Lemma \\ref{l:a} we may assume the order is composite. " + claim_span
             + " The rest follows by induction.")
    nodes = [
        {"id": "LP1", "type": "lemma", "name": "L", "statement": "Every group of prime order is cyclic, see \\cite{Lag, Cau}."},
        {"id": "TP1", "type": "theorem", "name": "T", "statement": "Every finite group of odd order is solvable.",
         "also_stated_at": ["Every finite group of odd order is solvable."], "main": True},
        {"id": "PP1", "type": "proof", "name": "P", "statement": proof},
        {"id": "ClP1", "type": "claim", "name": "C", "statement": claim_span},
        {"id": "PSP1", "type": "proof_step", "name": "s1", "parent_id": "PP1", "step_order": 1,
         "statement": "By Lemma \\ref{l:a} we may assume the order is composite."},
        {"id": "PSP2", "type": "proof_step", "name": "s2", "parent_id": "PP1", "step_order": 2, "statement": claim_span},
        {"id": "PSP3", "type": "proof_step", "name": "s2a", "parent_id": "PSP2", "step_order": 1,
         "statement": claim},
        {"id": "PSP4", "type": "proof_step", "name": "s2b", "parent_id": "PSP2", "step_order": 2,
         "statement": "Indeed, take a Sylow subgroup and count. This proves the claim."},
        {"id": "PSP5", "type": "proof_step", "name": "s3", "parent_id": "PP1", "step_order": 3,
         "statement": "The rest follows by induction."},
        {"id": "RP1", "type": "remark", "name": "R", "statement": "Theorem \\ref{t:intro} has many consequences."},
        {"id": "ClP2", "type": "claim", "name": "C2", "statement": "Every abelian group is solvable."},
        {"id": "PP2", "type": "proof", "name": "P2", "confidence": 0.7,
         "statement": "We prove it in two steps. \\subsection{The setup} Let $G$ be abelian. Its derived subgroup is trivial. "
                      "\\subsection{The end} Hence $G$ is solvable."},
        {"id": "RP2", "type": "remark", "name": "R2",
         "statement": "The claim in the proof of Theorem \\ref{t:main} is used again here."},
    ]
    for n in nodes:
        n.setdefault("section", "x")
        n.setdefault("origin", "paper")
        n.setdefault("confidence", 1.0)
    edges = [{"source": "PP2", "target": "ClP2", "type": "proves", "confidence": 0.7, "basis": "named"},
             {"source": "PSP3", "target": "PSP4", "type": "uses", "confidence": 0.8, "basis": "inferred"},
             {"source": "ClP1", "target": "RP2", "type": "uses", "confidence": 0.8, "basis": "named"}]
    return {"metadata": {"paper_style": ["theorem_proof"], "rigor_nonformal_count": 0}, "nodes": nodes, "edges": edges}


def main():
    g = build()
    r = finalize(g, TEX)
    n = {x["id"]: x for x in g["nodes"]}
    e = {(x["source"], x["target"], x["type"]): x for x in g["edges"]}
    fails = []

    def check(ok, what):
        if not ok:
            fails.append(what)
    check(n["TP1"].get("display") == "Theorem" and n["TP1"].get("number") == "3", f"display/number: {n['TP1']}")
    check(n["LP1"].get("cites") == ["Lag", "Cau"], f"cites: {n['LP1'].get('cites')}")
    check(e.get(("LP1", "PP1", "uses"), {}).get("basis") == "ref", "\\ref edge basis")
    check(e.get(("PP1", "TP1", "proves"), {}).get("basis") == "syntax", "proof environment basis")
    check("PSP2" not in n and r["steps_merged"] == [("PSP2", "ClP1")], f"merge: {r['steps_merged']}")
    check(n["PSP3"]["parent_id"] == "ClP1" and n["PSP5"]["step_order"] == 2, "children and step_order after merge")
    check(("TP1", "RP1", "uses") in e, "the restated copy's \\label resolves to TP1")
    check(any("ClP1 is stated inside proof PP1" in w for w in r["warnings"]), "encapsulation warning")
    check(not any("PP2" in x and "section heading" in x for x in r["errors"]), "a proof may span its subsections")
    check(not any("basis" in x or "main" in x for x in r["errors"]), "no basis/main errors")
    if fails:
        print("\n".join(fails))
        print("errors:", r["errors"])
        sys.exit(1)
    print("finalize v7: ok")


if __name__ == "__main__":
    main()
