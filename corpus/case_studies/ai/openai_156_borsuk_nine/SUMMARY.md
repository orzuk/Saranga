# OpenAI release, family 156: a nine-dimensional counterexample to Borsuk's covering assertion

AI-written paper (OpenAI internal model, September 23 2026; Lean-formalized main result). The claim: the
rank-one orthogonal projectors onto lines in R^4, a compact subset of R^9 under the Frobenius metric,
have diameter sqrt(2) and cannot be covered by ten sets of smaller diameter, so Borsuk's conjecture
fails in dimension nine (Corollary 7.1: in every dimension >= 9). The previous record, cited in the
paper, is Grinsztajn's 63-dimensional counterexample (2026); Kahn-Kalai's 1993 disproof is the origin.

## Files

| File | What |
|---|---|
| `openai_156_borsuk_nine.json` (+ `_new.html`) | LLM graph: frozen v7 prompt, Claude Opus 5.5 agent, finalize 0 errors, 2 warnings kept (uses of a cited fact and of a nested claim outside their proofs, both real) |
| `openai_156_borsuk_nine_rules.json` (+ `_rules_new.html`) | Rules graph (alg3) |
| `scripts/build_156.py` | The extraction's build script (`--write`) |
| `prompt_v7.md` | The rendered prompt the agent followed |
| `paper.pdf`, `paper.tex`, `arxiv_src/` | The manuscript (not committed) |

## Counts

| | LLM (v7) | Rules (alg3) |
|---|---|---|
| Nodes | 198: 78 Level-1 + 120 proof steps; 18 equations, 16 definitions, 16 proofs, 11 lemmas, 6 theorems, 4 remarks, 4 claims, 1 conjecture, 1 proposition, 1 corollary | 108: 56 equations, 17 proofs, 16 definitions, 11 lemmas, 4 theorems, 1 remark |
| Edges | 309: 289 uses, 16 proves, 4 resolves; basis term 117, inferred 86, ref 81, syntax 16, named 9 | 137 |
| Level-1 by origin | 68 paper, 10 external | |
| Results view | 19 results, 34 dependencies, longest chain 11 | |

## What the graph shows

- **Main results.** Theorem 1.1 (TP1) and Corollary 7.1 (CP1). Borsuk's conjecture (CnjP1, cited) is
  `resolved` by both, and by the cited Kahn-Kalai and Grinsztajn results.
- **A long spine.** The chain to Theorem 1.1 has 11 results: Lemma 3.1 -> Lemma 3.2 (the odd extension)
  -> Proposition 4.1 (at least N_k labels) -> Theorem 4.3 (facets have k vertices, their sum is a cycle)
  -> the transport claim ClP3 -> Lemmas 6.1 to 6.4 (facet complements, two tetrahedra per triangle, short
  edge links, partner blocks) -> Theorem 6.5 (no admissible map RP^3 -> Delta^9) -> Theorem 1.1. This is a
  topological argument (odd maps between spheres, degrees, a simplicial complex of labels) wrapped
  around a linear-algebra construction; the graph separates the two.
- **Mostly self-contained.** Theorem 1.1 rests on 17 results, one external: Lemma 2.1 on projector
  geometry (Conway-Hardin-Sloane 1996, re-proved for the normalization). The Hatcher facts on odd maps
  (TP4) are stated in full inside the proof of Proposition 4.1 and reused in Theorem 4.3 without
  restatement; the extractor made them a node and flagged the reuse.
- **Hidden reuse.** The transport principle used by Lemma 6.3 is stated only inside the proof of Lemma
  6.2 ("First observe ..."); the extractor promoted it to a Level-1 claim (ClP4) so the dependency has an
  endpoint. Two "immediate" assertions carry weight and are marked `rigor: semi_formal`: restricting an
  admissible map to a subspace keeps it admissible (ClP1), and the support complex is a finite simplicial
  complex (ClP2).
- **Proof decomposition.** 16 proofs, 120 steps; Theorem 4.3's proof has four paragraph-headed parts
  with 3, 8, 6 and 7 sub-steps (the `\paragraph` headings are not reported by `latex_facts`, so the
  agent labelled them by hand).

## Rules vs LLM

nodes P 0.67 / R 0.37, edges P 0.87 / R 0.58; result-level dependencies 23 of 38 recovered. The best of
the three: this paper states its argument in numbered lemmas with `\ref`s, which the rules read.

## What the extracting agent flagged in the paper

No failing step. The weakest-documented points: the local-coordinate regularity argument around (4.6);
the claim that the fibre maps G_x form a continuous map on the sphere bundle "by the subspace-restriction
and continuity properties"; "the stated disjointness and lower size bound are immediate" in Lemma 6.4;
the overloaded symbol S (support set in Section 4, a tetrahedron in Section 6); the smoothing conventions
of the norm spheres carried by remarks (RP3, RP4) rather than a lemma.

## Three findings for the talk

1. **An 11-result spine the paper never draws.** The AI paper is organised by section, not by argument;
   the graph gives the argument: construction, odd extension, counting labels, the simplicial complex,
   the partner blocks, the final obstruction.
2. **The load-bearing facts the paper does not state as results.** A transport principle inside a proof,
   two "immediate" claims, Hatcher's odd-map facts stated mid-proof and reused later: the extractor
   surfaces each as a node and flags the reuse, which is what a referee would list.
3. **The rules recover most of this one.** 23 of 38 result dependencies, because the paper is written
   in numbered lemmas with references; the prose-stated principles are what they miss.
