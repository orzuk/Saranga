# 2605.08777 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors; two warnings kept (a symbol in another sense: Y = cQX in the Prop 1 proof, mu_k(A_0) in App.
D.1). 229 nodes (78 steps, 25 definitions, 23 algorithm steps, 22 remarks, 21 proofs, 17 equations, 13 claims,
8 theorems, 8 propositions, 3 corollaries, 3 algorithms, 2 lemmas, 2 open problems, 2 conjectures, 1 assumption,
1 example), 323 edges (298 uses of which 7 mentions, 23 proves, 2 illustrates); 16 external nodes (Tweedie's identity,
Marchenko-Pastur, Voiculescu's asymptotic freeness, R-transform additivity, the R-transform of MP, Eyring-Kramers, the
Smoluchowski limit, standard definitions). Main results: Theorem 1 (uniqueness of the canonical diffusion), Theorem 2
(null limit spectrum, a free convolution of two Marchenko-Pastur laws), Propositions 2-3 (SSA monotone in every
eigenvalue; k equal modes), Algorithm 1 (SSA and DA from a score oracle). Theorem 2's proof is split into four parts;
its tau = 0 and tau -> inf statements are nested claims with their own proofs. Tool notes: the source-preparation
tool turned "P&R\\R&Q" into "\mathbb{R}&Q" in a matrix in Lemma 2's proof; the \Return lines came back empty.
The agent re-derived Lemma 2's rotation, the cubic coefficients, the quartic's leading term, lambda_+(inf) with its
numbers, and the 0.479 atom: all match.

## Possible errors in the paper, for the author

1. Sec. 3 says SSA is invariant for A_0 = cI; App. D.1 says SSA scales as 1/c, which is right (changing A_0 rescales time).
2. The weight table in H.6 defines w_2 = lambda_1/tr, which is at most 1, yet lists values up to 4.87.
3. In C.7, mu_{k+2} ~ sigma_f^2/sigma_iso^2 ~ 0.5 is wrong: that ratio is 1, and the 0.5 OU rate is 1/2 sigma_f^2/sigma_iso^2. The varying-rate caption says "within 1%" for 2.00 vs 2.08; the text gives ratio 0.96.
4. The parallel ellipses are panel (f), but Sec. 7 says "(panel b)" and C.2 says "Figure 1c". C.2 also refers to "the bimodal example in Section 5", which is not there.
5. "S-hat lower-bounds the population value (Prop 2)": the bound follows from rho^2 >= 0, not from monotonicity in mu_k.
6. B.8 says it needs finite fourth moments; its scope paragraph says only second moments are needed (second suffices).
7. The proof of Prop 2 cites "Lemma 1(iii)", but Lemma 1 has no parts.
8. C.7 cites "L1/L2 components" of the score-oracle remark and a "peeled-bulk adjustment in Section 5"; neither exists.
9. The Tweedie identity is written with "=" where eps_theta only approximates. The primer says "upper-half-plane branch" while Theorem 2 says lower-half-plane root.
10. Minor: an extra ")" in C.4.1; the C.5 selection rule leaves out Sec. 5's dip-test condition.
