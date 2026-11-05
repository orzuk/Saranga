# Case study: the Polynomial Freiman-Ruzsa paper (Gowers, Green, Manners, Tao, arXiv 2311.05762)

*On a conjecture of Marton*. This page covers the SARANGA graphs of the paper, what they show about its proof, and how they compare with the Lean blueprint (`teorth/pfr`). It was prepared on 2026-11-03 for the proof-interpretability talk at the Caltech Mathathon.

## Files

| File | What |
|---|---|
| `corpus/silver/opus-5.5__v7_cases/pfr_2023.json` (+ `_new.html`) | LLM graph: frozen v7 prompt (sha `86dcfbecdc4d78a5`), extracted by a Claude Opus 5.5 agent, finalize 0 errors / 0 warnings |
| `pfr_2023_rules.json` (+ `_new.html`) | Rules graph: alg3 (v7 sentence tagger + all-pairs edge model, acyclic) |
| `pfr_2023_lean.json` (+ `_new.html`) | **One graph of paper and blueprint** (`scripts/merge_lean.py`, 2026-11-05): the LLM graph with the 84 core blueprint statements placed inside the paper result that states them, folklore and cited ones apart; see below |
| `grounding_llm.json`, `grounding_rules.json` | `grounded_to` edges into the books_v7b + ProofWiki concept layer |
| `blueprint_scores_llm.json`, `blueprint_scores_rules.json` | papers-vs-blueprint scorer (`scripts/gold_candidates/score_bp_papers.one`) |
| `blueprint_manual_alignment.json` | Hand alignment of the blueprint's PFR core to the LLM graph |
| `analysis.json` | All numbers below |
| `results_view.json` | Compact results view for a slide (32 results, 51 dependencies + 1 `resolves`) |
| `scripts/` | Build script of the LLM extraction, the analysis scripts and the scorer wrapper |
| `paper.tex` | The source, not committed |

Edge convention: an edge A → B means that B depends on A. In the *results view*:
- every proof is folded into the result it proves, and every equation or step into its container;
- `mention` and `resolves` edges are dropped;
- the nodes kept are theorems, lemmas, propositions, corollaries and claims.

## The two graphs

| | LLM (v7) | Rules (alg3) |
|---|---|---|
| Nodes | **250**: 85 proof_step, 63 equation, 23 claim, 18 proof, 17 definition, 16 theorem, 7 lemma, 5 corollary, 5 remark, 4 example, 3 conjecture, 2 proposition, 1 assumption, 1 open_problem | **229**: 153 equation, 19 definition, 17 claim, 12 proof, 8 theorem, 7 lemma, 5 corollary, 3 remark, 2 conjecture, 2 proposition, 1 example |
| Edges | **511**: 485 uses, 18 proves, 4 illustrates, 2 resolves, 1 specializes, 1 generalizes. 200 from `\ref`, 210 by defined term, 24 named in words, 68 inferred, 8 by syntax; 29 marked as mentions | **145**: 133 uses, 11 proves, 1 illustrates (82 from the parser, 63 from the learned edge model) |
| Results view | 56 results, 63 dependencies; 28 results under Theorem 1.2 | 41 results, 23 dependencies; only Conjecture 1.1 under Theorem 1.2 |
| External (cited) nodes | 54 | n/a |

## The proof as the LLM graph shows it

**Main results.**
- **Theorem 1.2**: Marton's conjecture holds with C = 12.
- **Theorem 1.8**: the entropic PFR, `d[X⁰₁;U_H] + d[X⁰₂;U_H] ≤ 11 d[X⁰₁;X⁰₂]`. This is the form the paper actually proves.

Theorem 1.2 has only one proof: Appendix B, which derives it from Theorem 1.8 using Jensen (A.1), the large-atom bound (A.2), `|H[X]−H[Y]| ≤ 2d` (A.12) and the Ruzsa covering lemma (cited).

Consequences:
- Theorem 1.3, the weak PFR over Z, via a citation of [GMT].
- Corollaries 1.4 to 1.6 (approximate homomorphisms, linearity testing, the U³ inverse theorem).
- Mudgal's Corollary 1.7, through Theorem 1.3.

**The spine.** The longest chain of results in the results view has 9 results (depth 8):

> Submodularity of entropy (A.6/A.7) → **Fibring lemma** (Prop 4.1, from [GMT]) → Corollary 4.2 (four-variable fibring identity) → **First estimate** (3.13) `I₁ ≤ 2ηk` → four-fold sum entropy bound (5.9) → **Second estimate** (3.14) → **Proposition 2.1** (τ can be decreased) → **Theorem 1.8** → **Theorem 1.2**

**Proposition 2.1, the central step, has no proof environment.** It is proved by contradiction, and the argument is spread over four sections:
- Section 3 sets the standing hypothesis (3.11)/(3.12): `(X₁,X₂)` minimises τ.
- Section 5 proves the first estimate, and Section 6 the second.
- Section 7, the endgame, finishes with "The proof of Proposition 2.1 (and hence of all our results) is complete."

In the LLM graph, nine results feed Proposition 2.1 directly:
- the first and second estimates, the four-fold sum bound, the hypothesis (3.12);
- Lemmas 5.1, 5.2, 7.1 and 7.2;
- the entropic Balog-Szemerédi-Gowers lemma A.2.

Theorem 1.8 then follows from Proposition 2.1, Lemma 2.2 (the 100% case) and the Ruzsa triangle inequality, by compactness: take a minimiser of τ.

**Which steps carry the weight.** Two measures: how many results in Theorem 1.2's chain rest on a result (transitively), and how many results use it directly.

| Result | Results resting on it | Used directly by |
|---|---|---|
| Non-negativity of conditional mutual information (A.8) | 16 | — |
| Submodularity (A.6) | 15 | — |
| Alternative formula for conditional distance (A.15) | 15 | — |
| **Lemma 5.1** (conditioning raises Ruzsa distance by at most ½ the mutual informations) | 14 | Lemma 5.2, Lemma 7.2, Proposition 2.1 |
| Kaimanovich-Vershik-Madiman inequality (Lemma A.1 = (5.4)) | 13 | — |
| **Lemma 5.2** (distance to a sum or a fibre) | 12 | 4 results: both estimates, Lemma 7.1, Proposition 2.1 |
| Hypothesis (3.12) | 12 | 4 results |
| **Fibring lemma** (Prop 4.1) | 11 | — |

The paper's own most-cited labels are:
- (2.2), the τ-decrement goal: 15 `\ref`s;
- Theorem 1.8: 14;
- Proposition 2.1: 12;
- Theorem 1.2: 9;
- the hypothesis (3.12): 9;
- the four candidate pairs (3.1) to (3.4): 7 or 8 each;
- entropic BSG (A.2): 7.

**The one characteristic-2 step is not a lemma.** It is the identity `U + V + W = 0` (7.4). The paper calls it "the key observation" and "the only critical use of this fact in the argument", and the discrete-Gaussian example (Example ExP4) shows why the endgame must use it. In both the paper and the LLM graph it is one equation inside a step of the Section 7 proof. The blueprint makes it a lemma of its own, `key-ident`.

## Grounding in the foundation concepts

Concepts: books_v7b concepts with ProofWiki. Each graph was grounded together with the 4,993 math_CO v7 papers, so that the document-frequency filter works; the 100K run used all 20 categories.

| | grounded_to edges | Paper nodes | Concepts |
|---|---|---|---|
| LLM graph | 71 | 43 | 22 |
| Rules graph | 44 | 32 | 15 |

LLM concepts, by number of paper nodes grounded to them:
- Random variable: 28
- Abelian group: 8
- Uniform distribution: 5
- Independent random variables: 5
- Mutual information: 4
- Pairwise independence: 3
- Conditional independence: 2
- Conditional entropy, Density function, Marginal distribution, Affine subspace, Affine transformation, Gaussian distribution, Linearly independent, Finite subset, Additive group: 1 each

The foundation layer covers the probability and information-theory vocabulary. It does not cover the additive combinatorics the paper is about:
- **No concept is grounded** for entropy, subgroup, coset, the triangle inequality, the chain rule or Jensen. Those concepts *exist* in the layer (Entropy C4937, Subgroup, Coset, Chain rule, Triangle inequality, Jensen's inequality), but the ambiguity and homonym filters drop them: Entropy vs. Entropy (Physics), the triangle inequality vs. Metric space, and so on.
- **The layer has no concept at all** for Ruzsa distance, sumset or doubling, Freiman, Plünnecke or Kaimanovich-Vershik, or Balog-Szemerédi-Gowers.

A few groundings are spurious: "Repeat of a set of vectors", "Converse and contrapositive", "Mean".

## LLM vs rules

Comparing dependencies between labelled results:

| | Count |
|---|---|
| LLM graph | 26 |
| Rules graph | 10 |
| Shared | 9: Lemma 5.1 → Lemma 5.2 and → Lemma 7.2; Lemma 5.2 → Lemma 7.1; BSG → Lemma 7.2; Prop 4.1 → Cor 4.2; Lemma 2.2 → Thm 1.8; Prop 2.1 → Thm 1.8; Thm 1.8 → Thm 1.3; Conj 1.1 → Thm 1.2 |

**Only the LLM graph has these 17:**
- **The whole proof of Proposition 2.1.** The first and second estimates, Lemmas 5.1, 5.2, 7.1 and 7.2, and BSG all feed it. The rules pipeline finds proofs only by environment or adjacency, so a proof written in prose across Sections 3 and 5 to 7 is invisible to it: in the rules graph Proposition 2.1 rests on nothing.
- **Theorem 1.8 → Theorem 1.2.** This is the Appendix B proof, a whole-appendix prose proof. Without it the rules graph's main theorem is disconnected from the proof that establishes it.
- **The estimates as nodes, and Corollary 4.2 and Lemma 5.2 feeding them.** The rules graph has (3.13) and (3.14) only as equations.
- **Theorem 1.2 → Corollaries 1.4 to 1.6 and Theorem 1.3.**

**Only the LLM graph has these prose results.** There are 37 results with no LaTeX label:
- the standard facts of Appendix A as named results: submodularity, the chain rule, the Ruzsa triangle inequality (with its proof), sumset lower bounds, `|H[X]−H[Y]| ≤ 2d`;
- the cited history: Ruzsa's bound, Sanders' bound, Konyagin's bound, Green-Tao for downsets, Liao's C = 11, Bourgain-Chang, Even-Zohar's f(2,K), and Aaronson's refutation of the strong PFR conjecture;
- two prose conjectures (the strong PFR conjecture and the polynomial Bogolyubov conjecture) and one open problem (the strong PFR conjecture over Z);
- four worked examples from Section 3, and the heuristic plan claims (rigor `heuristic` or `semi_formal`).

**Only the rules graph has these:**
- 1 result dependency, Conj 1.1 → Thm 1.3, which is not a dependency;
- 90 more equations: it keeps unnumbered displays;
- the definition of mutual information, but typed as a theorem (DIST_THEOREM5).

## Comparison with the Lean blueprint

The blueprint (`teorth__pfr/graph.json`) has 408 nodes and 742 edges, with 219 statements. It goes beyond the paper: C = 9, torsion groups, odd characteristic and multidistance, and ρ-functionals. Its PFR theorem with C = 12 (`pfr`) rests on **84 statements** (by transitive dependency), and its longest chain is **17 statements**. The paper's longest chain is 9.

**Existing scorer** (`score_bp_papers.one`; statement alignment by quoted number, then by token overlap ≥ 0.5; graph_score presets):

| Paper graph | Aligned (by number) | Node P / R / F1 | Edge P / R / F1 (author) | Edge F1 (author_inv) |
|---|---|---|---|---|
| LLM | 62 / 219 (1) | 0.648 / 0.289 / **0.400** | 0.337 / 0.197 / **0.248** | 0.124 |
| Rules | 47 / 219 (0) | 0.514 / 0.200 / 0.288 | 0.341 / 0.096 / 0.150 | 0.130 |

The automatic alignment is noisy on this pair, because the blueprint renames and numbers its statements differently. Examples: blueprint `pfr` was aligned to the polynomial Bogolyubov conjecture, and `chain-rule` to a remark. So the scorer numbers understate agreement. A hand alignment of the 84-statement core to the LLM graph is in `blueprint_manual_alignment.json`:

| How the paper has it | Blueprint statements |
|---|---|
| A node of the LLM graph | **43** |
| Stated only inside a proof or another node | **22** |
| Cited and only applied | **6** |
| Never stated | **13** |

Of the 60 blueprint dependencies between distinct aligned nodes, the LLM graph has 47 directly and 49 as a path, which is 82%. The 11 it misses are mostly uses of the chain rule and of the definitions that the paper never names in a proof.

**What the formalisers made explicit that the paper leaves implicit:**

- **Intermediate inequalities inside proofs became lemmas (22).** Examples:
  - `first-fibre` (5.1), `first-cond` (5.2), `first-upper` (5.7)/(5.8), `first-dist-sum`;
  - `dist-sums` (6.5) and `second-estimate-aux` (6.6);
  - in the endgame: `uvw-s` (7.2), `total-dist` (7.3), `key-ident` (U+V+W=0, (7.4)) and `construct-good` (7.8);
  - the existence of a τ-minimiser (`tau-min`, the compactness sentence) and "τ depends only on the distributions" (`tau-copy`).

  The paper's Sections 5 to 7 are each a single argument. The blueprint splits them into 4 to 10 lemmas each.
- **Cited results had to be proved (6).** The paper gets the 100% case (Lemma 2.2) from [Tao 2010, Thm 1.11(i)] in one sentence. The blueprint proves it from scratch with a symmetry group: `sym-group-def`, `sym-group`, `zero-large`, `sym-zero` and `lem:100pc-self`. The Ruzsa covering lemma (`ruz-cov`) is also proved.
- **Folklore was never written down (13):**
  - the definition of Shannon entropy itself (`entropy-def`), and of independence and conditional independence;
  - `d ≥ 0`;
  - copies preserve entropy and distance;
  - negation, relabelling and commutativity of joint entropy;
  - subadditivity;
  - the existence of independent copies and of uniform distributions;
  - the concavity behind "by Jensen".
- **The contrapositive is made explicit.** The blueprint's τ-decrement (`de-prop`) is stated as "τ-minimisers have d = 0". The paper states the direct form (Prop 2.1) and proves the contrapositive in prose.

## One graph: the paper with its blueprint inside it

`pfr_2023_lean_new.html` (built from `pfr_2023_lean.json`, the output of `scripts/merge_lean.py`, with
`--tex paper.tex` so the paper's macros render). The viewer's "Lean blueprint" toggle adds the 84 core
blueprint statements (ancestors of `pfr`, proofs folded) as blue-edged boxes: the 65 the paper states (43 as
a result, 22 inside a proof) sit inside the frame of that result, so a frame's size shows how many lemmas
the formalisers cut one argument into (Proposition 2.1 and the first estimate hold 7 each, Theorem 1.8 four,
Theorem 1.2 three). The 13 folklore statements (orange band) and 6 re-proved cited results (purple band) stand
apart. A paper result with no Lean counterpart is greyed (the corollaries 1.4 to 1.7, the cited history, the
heuristic plan). Blueprint dependencies are thin blue edges; an edge is drawn orange when the other side has
no counterpart: 17 Lean dependencies run between paper results with no paper path between them, and 12 paper
dependencies join results whose Lean statements have no Lean path. Lean statements follow their host into
the Rests-on and Neighbourhood views, so one step from Proposition 2.1 shows its inputs with their Lean
versions inside. The earlier two-panel page `pfr_2023_vs_blueprint.html` is superseded by this one.

## Three findings for the talk

1. **A 9-step spine with the key step in no proof environment.** The path to Theorem 1.2 runs submodularity → fibring lemma → first estimate → four-fold sum bound → second estimate → Prop 2.1 → Theorem 1.8. Prop 2.1, the step all that work goes into, is proved by contradiction across four sections in prose. The LLM graph recovers 9 direct inputs to it. The rules graph recovers none, and its main theorem is not linked to its own proof (Appendix B). Making a proof's structure explicit needs reading the prose, not only the theorem environments.
2. **The load-bearing pieces are two small lemmas and one identity.** Lemma 5.1 and Lemma 5.2 (how Ruzsa distance moves under conditioning, sums and fibres) are each used by 3 or 4 results directly, with 12 to 14 results resting on each. Under them sit submodularity, the Kaimanovich-Vershik-Madiman inequality and the fibring lemma. The only place characteristic 2 enters, `U+V+W=0`, is one equation inside the endgame. The formalisers gave it its own lemma.
3. **The formalisers made about half the proof explicit that the paper does not state.** For the C = 12 theorem the blueprint needs 84 statements on a chain of 17, against 28 results on a chain of 9 in the paper. 22 of the 84 are inequalities buried in proofs, 6 are cited results the paper only applies (Tao's 100% inverse theorem, Ruzsa covering), and 13 are folklore never written down, starting with the definition of entropy. Where both sides state a statement, the paper's dependencies (as the LLM extracted them) agree with the blueprint's on 82% of edges.

## Caveats

- The rules extraction runs `parse_batch.py` through `run_pipeline.py`. Calling `parse_batch.py` directly needs `PYTHONPATH=src`, because the `provenance` import fails without it.
- The grounding background is math_CO only, not all 20 categories.
- The hand alignment is one reader's judgment. Its notes for each statement are in `blueprint_manual_alignment.json`.
