#!/usr/bin/env python3
"""Regression + behaviour tests for the similarity stack.

Run directly (no pytest needed):

    python3 tests/test_similarity.py

The first block is the important one. Unifying six duplicated similarity
implementations into `src/node_similarity.py` was only safe because each
historical behaviour is reproduced exactly by a named Profile — these tests
pin that down, so a future "cleanup" of a profile shows up as a failure rather
than as silently moved P/R/F1 numbers in someone's paper.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in ("src", "src/LLMVersion", "scripts"):
    sys.path.insert(0, str(REPO / p))

import node_similarity as NS          # noqa: E402
import edge_similarity as ES          # noqa: E402
import graph_similarity as GS         # noqa: E402

FAILED = []


def check(name, got, want, tol=1e-12):
    ok = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
    print("  %-58s %s" % (name, "ok" if ok else "FAIL (got %r want %r)"
                          % (got, want)))
    if not ok:
        FAILED.append(name)


# ── Profiles reproduce the implementations they replaced ─────────────────────
def test_profiles_match_legacy():
    print("\nprofiles reproduce the legacy implementations")
    import graph_alignment as A
    import evaluate_extraction as E
    import distillation_analysis as D

    a = {"type": "theorem", "name": "T",
         "statement": r"Let $\alpha\in\mathbb{R}$. Then $f(\alpha)\le 2\alpha$.",
         "assumptions": ["$\\alpha>0$"], "conclusions": ["bounded"]}
    b = {"type": "lemma", "name": "L",
         "statement": r"Let $\alpha\in\mathbb{R}$. Then $f(\alpha)$ is bounded.",
         "assumptions": [], "conclusions": ["bounded"]}

    check("ALIGNMENT == graph_alignment._raw_jaccard",
          NS.text_sim(NS.node_text(a), NS.node_text(b),
                      profile=NS.Profile.ALIGNMENT),
          A._raw_jaccard(A.tokenize(A.node_text(a)), A.tokenize(A.node_text(b))))
    check("ALIGNMENT+GRADED == graph_alignment.jaccard_sim",
          NS.node_sim(a, b, profile=NS.Profile.ALIGNMENT,
                      type_policy=NS.TypePolicy.GRADED),
          A.jaccard_sim(a, b))
    check("EXTRACTION == evaluate_extraction.jaccard",
          NS.text_sim(NS.node_text(a, include_name=False),
                      NS.node_text(b, include_name=False),
                      profile=NS.Profile.EXTRACTION),
          E.jaccard(E.node_text(a), E.node_text(b)))
    check("DISTILLATION == distillation_analysis.jaccard_similarity",
          NS.text_sim(a["statement"], b["statement"],
                      profile=NS.Profile.DISTILLATION),
          D.jaccard_similarity(a["statement"], b["statement"]))
    check("type_compat table is graph_alignment's, unchanged",
          NS.TYPE_COMPAT == A.TYPE_COMPAT, True)


# ── Documented behavioural differences between profiles ──────────────────────
def test_profile_differences_are_intentional():
    print("\nprofile differences are the documented ones")
    t = r"$\alpha\in X$"
    check("ALIGNMENT keeps control sequences whole",
          "\\alpha" in NS.tokenize(t, NS.Profile.ALIGNMENT), True)
    check("EXTRACTION strips backslashes (legacy quirk)",
          "alpha" in NS.tokenize(t, NS.Profile.EXTRACTION), True)
    check("DISTILLATION emits brace/dollar tokens",
          "$" in NS.tokenize(t, NS.Profile.DISTILLATION), True)
    check("empty vs empty is 1.0 only under EXTRACTION",
          NS.text_sim("", "", profile=NS.Profile.EXTRACTION), 1.0)
    check("empty vs empty is 0.0 under CANONICAL",
          NS.text_sim("", "", profile=NS.Profile.CANONICAL), 0.0)


# ── Type policy ──────────────────────────────────────────────────────────────
def test_type_policy():
    print("\ntype policy")
    a = {"type": "theorem", "statement": "x y z"}
    b = {"type": "proposition", "statement": "x y z"}
    check("BLIND ignores type entirely",
          NS.node_sim(a, b, type_policy=NS.TypePolicy.BLIND), 1.0)
    check("GRADED damps theorem/proposition to 0.9",
          NS.node_sim(a, b, type_policy=NS.TypePolicy.GRADED), 0.9)
    check("STRICT zeroes it (the legacy double-penalty)",
          NS.node_sim(a, b, type_policy=NS.TypePolicy.STRICT), 0.0)


# ── Granularity: steps must not be penalised ─────────────────────────────────
def test_granularity():
    print("\ngranularity: stepless vs stepped extraction")
    stepless = {"nodes": [{"id": "P1", "type": "proof",
                           "statement": "First bound the sum. Then apply CS. "
                                        "Finally conclude."}], "edges": []}
    stepped = {"nodes": [
        {"id": "P1", "type": "proof", "statement": ""},
        {"id": "S1", "type": "proof_step", "parent_id": "P1", "step_order": 1,
         "statement": "First bound the sum."},
        {"id": "S2", "type": "proof_step", "parent_id": "P1", "step_order": 2,
         "statement": "Then apply CS."},
        {"id": "S3", "type": "proof_step", "parent_id": "P1", "step_order": 3,
         "statement": "Finally conclude."}], "edges": []}
    r = GS.compare_graphs(stepless, stepped, granularity="level1")
    check("collapsed: full credit", r["nodes"]["f1"], 1.0)
    check("collapsed: no phantom extra nodes", r["structure"]["only_b"], 0)
    check("step support reported, not penalised",
          r["steps"]["comparable"], False)
    r2 = GS.compare_graphs(stepless, stepped, granularity="as_is")
    check("as_is: granularity does cost you", r2["nodes"]["f1"] < 1.0, True)


# ── Split / merge: AB vs (A, B) ──────────────────────────────────────────────
def test_split_merge():
    print("\nsplit/merge: one theorem in two parts vs two theorems")
    merged = {"nodes": [{"id": "T1", "type": "theorem",
                         "statement": "Let f be continuous. Then f attains a "
                                      "maximum, and f is bounded."}],
              "edges": []}
    split = {"nodes": [
        {"id": "T1", "type": "theorem",
         "statement": "Let f be continuous. Then f attains a maximum."},
        {"id": "T2", "type": "theorem",
         "statement": "Let f be continuous. Then f is bounded."}],
        "edges": [{"source": "T1", "target": "T2", "type": "uses",
                   "confidence": 0.9}]}
    r = GS.compare_graphs(merged, split)
    check("scored as one matched group, not FP+FN", r["nodes"]["f1"], 1.0)
    check("recorded as a split", r["structure"]["split"], 1)
    check("no spurious unmatched nodes",
          r["structure"]["only_a"] + r["structure"]["only_b"], 0)
    check("intra-group edge dropped, not counted against",
          r["edges"]["n_b"], 0)


# ── Edge similarity ──────────────────────────────────────────────────────────
def test_edges():
    print("\nedge similarity")
    e1 = {"source": "A", "target": "B", "type": "uses"}
    same = {"source": "A", "target": "B", "type": "uses"}
    flipped = {"source": "B", "target": "A", "type": "uses"}
    subtype = {"source": "A", "target": "B", "type": "generalizes"}
    other = {"source": "A", "target": "B", "type": "proves"}
    unrelated = {"source": "C", "target": "D", "type": "uses"}
    check("identical edge", ES.edge_sim(e1, same), 1.0)
    check("reversed gets partial credit", ES.edge_sim(e1, flipped), 0.5)
    check("generalizes is a subtype of uses", ES.edge_sim(e1, subtype), 0.8)
    check("uses vs proves: dependency vs structural (canonical 0.2)",
          ES.edge_sim(e1, other), 0.2)
    check("proves vs resolves: related structural types",
          ES.edge_type_compat("proves", "resolves"), 0.6)
    check("opt-in table can refine generalizes/specializes",
          ES.edge_type_compat("generalizes", "specializes",
                              pair_table=ES.EDGE_TYPE_COMPAT_PROPOSED), 0.3)
    check("...which the group rule alone scores 0.8",
          ES.edge_type_compat("generalizes", "specializes"), 0.8)
    check("disjoint endpoints score 0", ES.edge_sim(e1, unrelated), 0.0)


if __name__ == "__main__":
    test_profiles_match_legacy()
    test_profile_differences_are_intentional()
    test_type_policy()
    test_granularity()
    test_split_merge()
    test_edges()
    print("\n%s" % ("ALL TESTS PASSED" if not FAILED
                    else "FAILURES: %s" % FAILED))
    sys.exit(1 if FAILED else 0)
