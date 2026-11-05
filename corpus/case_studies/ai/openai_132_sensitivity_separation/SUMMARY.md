# OpenAI release, family 132: a superquadratic separation between sensitivity and block sensitivity

AI-written paper (OpenAI internal model, September 25 2026; Lean-formalized main result). The claim: for
every C > 0 there is a total Boolean function with bs(f) > C s(f)^2, and by composition a fixed exponent
alpha > 2 with bs(f) >= s(f)^alpha. Huang 2019 gives bs(f) <= s(f)^4, so the true exponent now lies in
[alpha, 4] instead of [2, 4]; Huang's quartic bound is untouched. The construction adapts Meiburg's
August 2026 spectral-sensitivity construction (arXiv 2608.00851), whose key idea Meiburg credits to
GPT-5.6-Sol. So the lineage is AI idea, human write-up, then this fully AI-written paper.

## Files

| File | What |
|---|---|
| `openai_132_sensitivity_separation.json` (+ `_new.html`) | LLM graph: frozen v7 prompt, Claude Opus 5.5 agent, finalize 0 errors, 2 warnings kept (the rigor-on-sketch rule conflict) |
| `openai_132_sensitivity_separation_rules.json` (+ `_rules_new.html`) | Rules graph (alg3) |
| `scripts/build_132.py` | The extraction's build script (reproducible) |
| `cross_paper_huang.json` | Hand alignment to the Huang 2019 graph: the `resolves` edge and the seven cited nodes both graphs carry |
| `prompt_v7.md` | The rendered prompt the agent followed |
| `paper.pdf`, `paper.tex`, `arxiv_src/` | The manuscript (not committed) |

## Counts

| | LLM (v7) | Rules (alg3) |
|---|---|---|
| Nodes | 146: 69 Level-1 + 77 proof steps; 23 definitions, 12 proofs, 10 equations, 6 theorems, 6 claims, 5 lemmas, 2 conjectures, 2 remarks, 1 proposition, 1 corollary, 1 example | 78: 44 equations, 14 definitions, 8 proofs, 5 theorems, 5 lemmas, 1 proposition |
| Edges | 261: 245 uses, 12 proves, 2 resolves, 1 specializes, 1 illustrates; basis term 144, inferred 65, ref 35, named 9, syntax 8 | 66 |
| Level-1 by origin | 53 paper, 16 external | |
| Results view | 14 results, 18 dependencies, longest chain 6 | |

## What the graph shows

- **Main results.** Theorem 1.1 (TP5, the unbounded ratio) and Corollary 4.3 (CP1, the fixed exponent).
  TP5 `resolves` the quadratic conjecture of Nisan and Szegedy (CnjP2, cited); the Sensitivity Conjecture
  itself (CnjP1) is recorded as resolved by Huang's theorem (TP3, cited).
- **Self-contained.** Theorem 1.1 rests on 11 results, none of them external. The only cited result in the
  chain is the composition lemma (LP5, Tal / standard) that Corollary 4.3 uses. The paper imports
  definitions and history, not arguments: 16 external Level-1 nodes, of which 8 are results or
  conjectures (Rubinstein, Virza and Ambainis-Sun, Huang with Tal, Wellens, Ambainis-Prusis, the
  composition lemma, the two conjectures) and none is used in a proof except LP5.
- **The definition load is the readability story.** One step below Theorem 1.1 the "Rests on" view holds
  24 boxes: 3 lemmas, 1 claim and 20 definitions (construction parameters L, k, r, t; level parameters;
  blocks; centres; initial, nested and recursive predicates; clauses; target and gate conditions;
  sensitivity profiles S and J). Under Huang's Theorem 1.4 the same view holds 12 boxes, 10 of them
  standard definitions. A reader of the AI paper must hold twenty paper-specific symbols to read the
  theorem's proof; the graph makes that visible and lets each be opened in place.
- **The spine.** ClP3 (distinct children) -> ClP4 (one bit changes at most one condition) -> Proposition 3.1
  (the four coupled recurrences for S and J) -> Lemma 4.1 (quantitative profiles, 12 steps) -> Theorem 1.1
  (11 steps) -> Corollary 4.3. The six prose claims of Section 2 (nesting, valid indices, distinct
  children, one-bit-one-condition, recursive nesting, N_l = k r N_{l-1}) carry the construction and are
  stated as sentences, not as lemmas.
- **Proof decomposition.** 12 proofs, 77 steps; the two big ones are Lemma 4.1 (12 steps, three labelled
  parts with 5, 8 and 5 sub-steps) and Theorem 1.1 (11 steps).

## Rules vs LLM

`graph_score.score(rules, llm)`: nodes P 0.64 / R 0.34, edges P 0.83 / R 0.23; result-level dependencies
6 of 22 recovered. The rules find the environments and the numbered displays and little else: the prose
claims of Section 2 and the prose definitions of the construction are the LLM graph's and are what the
proofs rest on.

## Cross-paper link to Huang 2019

`cross_paper_huang.json`: Huang's Open Problem 3 ("close the quadratic-quartic gap") -> Theorem 1.1 here,
type `resolves` (partial: the exponent is above 2). Seven nodes are the same statement in both graphs:
Huang's Theorem 1.5 is the AI paper's cited TP3; the Sensitivity Conjecture, Rubinstein, Ambainis-Sun
(with Nisan-Szegedy/Tal behind Huang's theorem), and the definitions of sensitivity and block
sensitivity. This is the discovery use of the representation on one example: an AI paper whose place in
the human literature the graphs locate without reading either.

## What the extracting agent flagged in the paper

No failing step. Wording: in the proof of Corollary 4.3 "A > 1" is presented as following from B/A^2 > 1
(it follows from A = 22 M^10). A loose bound in Proposition 3.1 (3 J'_1 where 2 J'_1 suffices). Facts
used without being stated: the 1-Lipschitz property of D rests on the prose claim ClP1; "M >= 81" in Lemma
4.1 is derived silently from M >= 9^{d+1}; the OR-balancing step in Theorem 1.1 cites Ambainis-Sun but is
argued directly. Corollary 4.3 uses "the function constructed in the proof of Theorem 1.1": a dependency
on a proof, recorded as PP10 -> PP12.

## Three findings for the talk

1. **The graph reads an AI paper the same way it reads Huang.** Same extractor, same checks, zero errors;
   the main theorem, its spine of six results and its proof decomposition come out as for a human paper.
2. **What makes it hard to read is the definition load, and the graph shows it.** 20 paper-specific
   definitions under the main theorem, against 10 standard ones under Huang's; the argument itself is
   short (six results on the spine), the vocabulary is not.
3. **The graphs place the AI result in the literature.** Huang's open problem resolves to this theorem,
   and the two graphs share seven cited statements; the AI paper rests on no external result at all.
