# Huang 2019 (arXiv:1907.00847): the Sensitivity Conjecture as a SARANGA graph

Case study for the Caltech Mathathon talk on proof interpretability. Hao Huang, *Induced subgraphs of
hypercubes and a proof of the Sensitivity Conjecture* (Annals of Math. 2019): 6 pages, 18.5K characters
of prepared LaTeX, 11 environments (4 theorems, 3 lemmas, 1 conjecture, 3 proofs).

## Files

| File | What |
|---|---|
| `../../silver/opus-5.5__v7_cases/huang_2019.json` | LLM graph: frozen v7 prompt (sha `86dcfbecdc4d78a5`), Claude Opus 5.5 as the extracting agent; `extraction_finalize` 0 errors, 1 warning (RP1 starts after `\textcolor{black}{`, a markup false alarm) |
| `rules/1907.00847_rules.json` | Rules graph (alg3): `parse_batch.py --rules-dir extractors/rules/silver_v7__sentence_tagger__2026-10 --edge-model extractors/edges/silver_v7__edges_allpairs__2026-10` (acyclic: `edges_all.apply` skips a learned edge that would close a cycle) |
| `grounding_llm.json`, `grounding_rules.json` | `grounded_to` edges from `structured_math.books.ground_papers` into `foundation/books_v7b/concepts.json` |
| `huang_2019_new.html`, `huang_2019_rules.html` | Viewer pages (`src/graph_view/build.py --standalone`; both pass `check_pages.py`) |
| `analysis.json` | All numbers below |
| `results_view.json` | Compact one-slide view: 13 nodes, 16 edges, takeaways |
| `paper.tex`, `arxiv_src/` | Source from `extract_arxiv_funcs.fetch_arxiv_source` (single .tex, kept with its archive) |

Grounding note: `ground_papers` calls a term generic when more than 10% of the root's papers use it and
weights confidence by idf, so one paper alone grounds nothing. The temp root therefore held the 100K v7
bundles (`tier3_bundles/v7`, 99,988 papers, symlinked) plus the two Huang graphs under `math_CO/`, which
reproduces the df background of the 100K grounding layer (342 generic terms, as in that run).

## Counts

| | LLM (v7) | Rules (alg3) |
|---|---|---|
| Nodes | 58 (43 Level-1 + 15 proof steps) | 44 (incl. 12 equations, no steps) |
| Edges | 98: 86 uses, 7 proves, 2 generalizes, 1 specializes, 1 resolves, 1 illustrates | 45: 41 uses, 4 proves (8 parser, 37 learned) |
| Level-1 by origin | 19 paper, 24 external | 40 paper, 4 external |
| Edge basis (LLM) | 54 term, 20 inferred, 11 named, 10 ref, 3 syntax | |
| Grounding | 41 edges, 29 nodes, 15 concepts | 30 edges, 21 nodes, 15 concepts |

## 1. The whole proof as a graph

Longest dependency path in the LLM graph (uses/proves, mentions excluded):

`DP11 signed matrix A_n -> PP4 -> LP2 (Lemma 2.2: A_n^2 = nI, spectrum ±√n) -> PP6 -> TP3 (Theorem 1.1:
Δ(H) ≥ √n) -> PP1 -> TP8 (Theorem 1.4: s(f) ≥ √deg f) -> PP2 -> TP10 (Theorem 1.5: bs(f) ≤ s(f)^4) -> OpenP3
(close the quadratic-quartic gap)`.

At the level of results (proofs collapsed):

```
LP1 Cauchy interlacing [ext] ─┐
LP2 A_n spectrum ±√n ─────────┼─> TP3 Δ(H) ≥ √n ─┐
LP3 Δ(H) ≥ λ1(signed A) ──────┘                  ├─> TP8 s(f) ≥ √deg f ─┐
TP7 Gotsman–Linial [ext] ────────────────────────┘                      ├─> TP10 bs(f) ≤ s(f)^4
TP9 Nisan–Szegedy / Tal bs ≤ deg² [ext] ────────────────────────────────┘   ^ resolves
                                                                 CnjP1 Sensitivity Conjecture [ext]
```

- Proof of Theorem 1.1 (PP6), 6 steps: take A_n (PSP10); A_n is a signing of Q^n's adjacency matrix
  (PSP11); Lemma 2.3 on the restriction A_H gives Δ(H) ≥ λ1(A_H) (PSP12); spectrum of A_n from Lemma 2.2
  (PSP13); **Cauchy interlacing** gives λ1(A_H) ≥ λ_{2^{n-1}}(A_n) = √n (PSP14); combine (PSP15). Two
  branches (PSP10-12 via Lemma 2.3, PSP13-14 via Lemma 2.2 + interlacing) meet in PSP15.
- Lemma 2.2's proof (PP4, induction, 5 steps) and Lemma 2.3's (PP5, largest coordinate of the top
  eigenvector, 4 steps) are the only new arguments. Theorems 1.4 and 1.5 are each proved by one
  sentence in the introduction (PP1, PP2: prose proofs, no environment).
- The tightness clause of Theorem 1.1 (ClP1) has no proof in the paper: it rests on the Chung–Füredi–
  Graham–Seymour construction (TP2). The closing remark (RP2) adds the strengthening
  λ1(H) ≥ λ1(A_H) ≥ √n (ClP3, the only `rigor: semi_formal` node: the first inequality is asserted
  without argument) and its tightness via the star K_{1,n} (ClP4, proved by PP7).

## 2. Proved in the paper vs imported

- The paper's own: Lemma 2.2 (LP2) with its matrix A_n (DP11), Lemma 2.3 (LP3), and the three main
  results TP3, TP8, TP10 (`main`). 19 of 43 Level-1 nodes are `paper`, 24 `external`.
- Theorem 1.1 rests on **1** external result, Cauchy's Interlace Theorem (LP1), plus 3 standard
  definitions (Q^n, Δ/λ1, principal submatrix). Its "proof" in the paper is a pointer (PP3, `origin:
  external`): "a direct consequence of the Courant-Fischer-Weyl min-max principle … also in [Fisk]".
- Theorem 1.4 adds **Gotsman–Linial** (TP7, which brings Γ(H), Q^n−H and deg f: DP7-DP9).
- Theorem 1.5 adds **Nisan–Szegedy / Tal** bs(f) ≤ deg(f)² (TP9). So the Sensitivity Theorem rests on
  exactly 3 imported results and 10 imported definitions. Seven more external results (CFGS bound TP1,
  CFGS construction TP2, Kenyon–Kutin TP5, Rubinstein TP6, Ambainis–Sun TP11, the polynomial-equivalence
  survey result TP4, bs ≥ s ClP2) are background the proof never uses.
- Theorem 1.4 also confirms a Gotsman–Linial conjecture that the paper names but never states (no node).

## 3. Which textbook / ProofWiki concepts it rests on

The LLM graph grounds 29 of 58 nodes into 15 concepts: Induced subgraph (9), Switching (Boolean) function
(9), Even vertex (3), Adjacency matrix, Symmetric matrix, Square matrix, Undirected graph, Vertex set,
Perfect square, Odd vertex, Isolated vertex (2 each), SubMatrix, Perfect matching, Absolute value,
Direct proof (1 each). Per node: LP1 Cauchy interlacing -> Symmetric matrix only; LP3 -> Undirected
graph, Symmetric matrix; LP2 and DP11 -> Square matrix; PP6 -> Adjacency matrix, Perfect matching,
Induced subgraph; DP10 principal submatrix -> SubMatrix.

**Does interlacing ground? No.** The 16K-concept books_v7b layer has no concept for Cauchy interlacing,
Courant–Fischer(-Weyl) min-max, hypercube graph (only "N-Cube (Euclidean Space)"), principal submatrix,
or (block) sensitivity. **Eigenvalue and eigenvector do not ground either**, although the concepts exist
(C4716 Eigenvalue, C4726 Eigenvector): a one-word term needs three of the concept's distinctive words in
the node, and no node has them. "Maximum degree Δ(G)" exists (C3978, Levin) but its term is the symbol,
so DP2 grounds to Adjacency matrix and Undirected graph instead. "Degree", "graph", "matrix", "vector"
and "lower/upper bound" are generic (df > 10%). The foundation layer sees the combinatorial vocabulary
but none of the spectral machinery that carries the proof. The imported step (interlacing) is exactly
the one it cannot see.

## 4. LLM vs rules

`graph_score.score(rules, llm)` (text matching, LLM as reference): nodes P 0.674 / R 0.511; result-level
dependencies P 0.553 / R 0.296. Recall is 0.37 (20/54) on definition edges but **0.059 (1/17)** on
result-to-result edges. The one it keeps is Lemma 2.2 -> Theorem 1.1. Missing:

- **Cauchy interlacing -> Theorem 1.1**: the proof cites it by name ("By Cauchy's Interlace Theorem") with
  no `\ref`, and the rules graph has no edge out of L1 at all.
- **Lemma 2.3 -> Theorem 1.1**: the parser keeps the `\ref` edge L3 -> R3 but flags it `mention`
  ("satisfy the conditions in Lemma 2.3"), so it drops out of the dependency graph and the key lemma
  looks unused.
- **The reduction chain**: TP3 -> TP8 -> TP10, Gotsman–Linial -> TP8 and Nisan–Szegedy/Tal -> TP10. The
  rules make the one-sentence prose proof of Theorem 1.4 a remark (DIST_REMARK1, with edges from T1 and
  T2 but none to T3). They find no proof of Theorem 1.5 and no `resolves` edge from the conjecture, so
  the Sensitivity Theorem is an island (only D1 -> T4).
- Origin: rules mark Cauchy's Interlace Theorem (L1) as `paper`. Only 4 rules nodes are `external`
  (CFGS bound, Kenyon–Kutin, Gotsman–Linial, Nisan–Szegedy/Tal), against 24 in the LLM graph.
- Nodes the rules miss: the tightness claims (ClP1, ClP3, ClP4, PP7), the two prose proofs (PP1, PP2),
  block sensitivity bs(f) (DP6), Rubinstein, Ambainis–Sun, the AND-of-ORs example and open problem 3.
  The rules add 12 equation nodes that v7 leaves inside their statements (unlabelled displays are not
  v7 nodes), and they split open problem 1 into its definitions (α(G), f(G), g(n,k)).
- Grounding is nearly identical (the same 15 concept names), since both sides share the environments'
  statement text.

## Three findings for the talk

1. **The new mathematics is two lemmas; the rest is imported.** The results graph has a single spine,
   A_n -> Lemma 2.2 -> Thm 1.1 -> Thm 1.4 -> Thm 1.5. The Sensitivity Theorem rests on exactly 3
   external results (Cauchy interlacing, Gotsman–Linial, Nisan–Szegedy/Tal), and 24 of 43
   statement nodes are external.
2. **The textbook layer cannot see the decisive imported step.** Interlacing, Courant–Fischer, the
   hypercube graph, principal submatrices and even "eigenvalue" have no grounding. The proof grounds
   only to symmetric/square/adjacency matrix, induced subgraph and boolean function.
3. **Rules recover the parts but not the argument.** They keep 1 of 17 result dependencies (only Lemma 2.2 ->
   Thm 1.1). Interlacing is cited by name without `\ref`, Lemma 2.3 is downgraded to a mention, and the
   one-sentence prose proofs that reduce the conjecture to Theorem 1.1 are missed. That is exactly the
   connective tissue that makes this proof famous.
