# 2603.10215 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 1 warning kept (DP25, the MSC coalescence conditions: one enumerated list introduces two symbols).
320 nodes (108 steps, 47 equations, 46 definitions, 27 algorithm steps, 24 claims, 23 proofs, 15 lemmas, 8 theorems,
7 remarks, 6 algorithms, 5 assumptions, 2 examples, 1 problem, 1 proposition), 404 edges (379 uses, 23 proves,
2 illustrates); 36 external nodes; 14 backward edges. Main results: the SDSR algorithm, Theorem 3 (asymptotic
consistency of the partition step), Theorem 4 (finite-gene guarantee), Proposition 1 (full-pipeline guarantee; no proof
in the paper, semi_formal). Cited: Aizenbud et al. 2021 Thm 4.2, matrix Bernstein (Tropp), Davis-Kahan, Chang 1996,
inconsistency of CA-ML under the MSC, consistency of summary methods. Properties 1 and 2 typed as assumptions
(hypotheses of Theorem 3); Remark 2 retyped as a claim with a nested proof; Lemma 8 has no proof environment, its two
prose parts (H.2, H.3) are separate proof nodes.

## Possible problems in the paper, for the author

1. Lemma 4's proof shows only that clans give rank-1 blocks; the rank-1 condition is an "iff" and the converse is not shown.
2. Lemma 2's proof, quartet part, assumes E[S^g] is the similarity matrix of a tree; Lemma 1 provides that only once the quartet condition is known, so the argument looks circular. The non-clan case of the same proof already gives a positive quartet determinant.
3. Eq. (33) in Lemma 10's proof says "ultrametric iff the similarity across the root is constant"; the "if" direction fails as written (the two sides may sit at different distances from the root).
4. Inconsistent normalisation: Appendix C uses S^g = S exp(-2 Delta) and mixes distances D with times tau (also in Property 2 and the Fig. 5 caption); Sec. 5.1 gives e^{4 tr(Q) tau}.
5. "Q is negative semi-definite by the first two properties": Q is not symmetric; real non-positive eigenvalues need reversibility, property (iv).
6. Lemma 1's proof says the 2x2 determinant is positive "by the definition of the rank-1 matrix"; it is the quartet condition that gives this. The factorisation W(i,j) = w(i,h_A) w(h_A,j) also needs i and j on different sides of h_A.
7. Lemma 8 concludes only "two clans", but Lemma 6 and Theorem 4 claim the specific root clans C_L, C_R.
8. Theorem 3's proof uses the eigenvalues of the sample L-bar in Davis-Kahan; the population eigengap should be used.
9. Typos: in Lemma 5's proof w(A,h_B) should be w(B,h_B), w(h_A2,h_A2) should be w(h_A2,h_A), c_A w(A_2,h_B) should use h_A; "To prove the corollary, is suffices" (proof of Theorem 4); "Step 1a" in Appendix E does not exist; stray ^m in the sum defining v-bar^(2); Lemma 3 allows alpha < 0.5 while Eq. (5) allows beta' <= 0.5, and beta < 0.5 vs <= 0.5 elsewhere; alphabet size l in Sec. 2 but d in Sec. 5.1; the species tree is unrooted in Sec. 2 but rooted in Definition 1; "the the" in Sec. 5.1; missing braces in {T^g}_{g=1}^K in Theorem 4.
