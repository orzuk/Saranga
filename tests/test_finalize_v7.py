"""The v7 additions to the finishing step (src/extraction_finalize.py).

Runs without pytest:  python3 tests/test_finalize_v7.py

On a small paper: display/number from the environment, cites, edge basis (ref, syntax),
a proof step with a claim's span merged into the claim, a restated copy's \\label
resolving to the one node, a result stated inside a proof and used outside it, and a
prose proof that fills a section with subsections. Then equivalent theorems: the
loop "König gives Hall, Hall gives König" is circular unless the second proof of
König is marked `alternative`; `alternative` and `equivalent_conditions` errors; a
gold equivalence arrow is scored in either direction.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from extraction_finalize import finalize, validate  # noqa: E402
from validate_annotation import reasoning_cycles  # noqa: E402
import graph_score as GS  # noqa: E402

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


def equivalence():
    fails = []
    src = ("Theorem K. Max matching equals min cover. Proof. A real proof. Theorem H. Hall's condition "
           "holds iff there is a matching. Proof. Apply Theorem K. Remark. Conversely Theorem H gives Theorem K.")
    nodes = [{"id": "K", "type": "theorem", "statement": "Max matching equals min cover."},
             {"id": "P1", "type": "proof", "statement": "A real proof."},
             {"id": "H", "type": "theorem", "statement": "Hall's condition holds iff there is a matching.",
              "equivalent_conditions": ["Hall's condition holds", "there is a matching"]},
             {"id": "P2", "type": "proof", "statement": "Apply Theorem K."},
             {"id": "P3", "type": "proof", "statement": "Conversely Theorem H gives Theorem K."}]
    edges = [{"source": "P1", "target": "K", "type": "proves", "confidence": 1.0, "basis": "syntax"},
             {"source": "K", "target": "P2", "type": "uses", "confidence": 0.9, "basis": "named"},
             {"source": "P2", "target": "H", "type": "proves", "confidence": 1.0, "basis": "syntax"},
             {"source": "H", "target": "P3", "type": "uses", "confidence": 0.9, "basis": "named"},
             {"source": "P3", "target": "K", "type": "proves", "confidence": 0.9, "basis": "named"}]
    if not reasoning_cycles(nodes, edges):
        fails.append("the unmarked loop through a second proof is a cycle")
    edges[-1]["alternative"] = True
    if reasoning_cycles(nodes, edges):
        fails.append(f"alternative proof still a cycle: {reasoning_cycles(nodes, edges)}")

    def errors(nodes, edges):
        r = {"errors": [], "warnings": []}
        validate({"metadata": {"paper_style": ["theorem_proof"], "rigor_nonformal_count": 0},
                  "nodes": nodes, "edges": edges}, src, r)
        return r["errors"]
    if any("alternative" in x or "equivalent_conditions" in x for x in errors(nodes, edges)):
        fails.append(f"valid graph rejected: {errors(nodes, edges)}")
    bad = [dict(e) for e in edges]
    bad[0]["alternative"] = True                              # K's only other proof is alternative too
    bad[1]["alternative"] = True                              # on a uses edge
    errs = errors(nodes, bad)
    if not any("on a proves edge" in x for x in errs) or not any("has no other proof" in x for x in errs):
        fails.append(f"alternative errors: {errs}")
    one = [dict(n) for n in nodes]
    one[2]["equivalent_conditions"] = ["Hall's condition holds"]
    if not any("equivalent_conditions" in x for x in errors(one, edges)):
        fails.append("a one-element equivalent_conditions is accepted")

    gold = {"nodes": [{"id": "G1", "type": "theorem", "statement": "Max matching equals min cover."},
                      {"id": "G2", "type": "theorem", "statement": "Hall's condition holds iff there is a matching."}],
            "edges": [{"source": "G1", "target": "G2", "type": "uses", "confidence": 1.0, "equivalence": True}]}
    pred = {"nodes": gold["nodes"], "edges": [{"source": "G2", "target": "G1", "type": "uses", "confidence": 1.0}]}
    sc = GS.score(pred, gold)
    if sc["edge_g_credit"] != 1 or sc["edge_p_credit"] != 1:
        fails.append(f"reversed arrow on a gold equivalence: {sc}")
    gold["edges"][0].pop("equivalence")
    if GS.score(pred, gold)["edge_g_credit"] != 0:
        fails.append("reversed arrow scored on an ordinary gold edge")
    if fails:
        print("\n".join(fails))
        sys.exit(1)
    print("equivalence: ok")


if __name__ == "__main__":
    main()
    equivalence()
