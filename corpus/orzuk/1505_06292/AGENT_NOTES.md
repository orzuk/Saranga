# 1505.06292 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 1 warning kept (r_i from DP21 in Lemmas 5-6, which declare their own Bernoulli r_i). 210 nodes
(59 equations, 33 steps, 31 definitions, 24 claims, 16 algorithm steps, 13 proofs, 11 theorems, 8 lemmas, 6 algorithms,
2 problems, 2 corollaries, 2 remarks, 1 example, 1 open problem, 1 assumption), 299 edges (283 uses, 13 proves,
2 resolves, 1 illustrates); 35 external nodes; one orphan (the cited Theta(nr log n) matrix-completion bound).
Main results: SVLS (AP2), Theorem 1 (exact GRC recovery with probability 1), Theorem 2 (RCMC recovery w.h.p. for
incoherent X), Theorem 3 (noisy GRC error bound). paper_style: theorem_proof, computational.
Notes: Lemma 3 (rotation invariance of Gaussian matrices) is standard but proved without attribution, kept as paper;
the set-up of the proof of Theorem 3 in running text before Lemma 8 was split into two definitions, one w.l.o.g.
assumption and two claims; SVLS_P gets no steps.

## Possible errors in the paper, for the author

1. Example 1: ||X_0||_* should be 2 sqrt(2) n / 3 (about 0.94 n), not n sqrt(2)/3. The conclusion still holds.
2. Rank estimator printed as round((r-hat^(C) + r-hat^(C))/2); the second term should be r-hat^(R).
3. Proof of Theorem 3: the final bounds for II and III drop the sqrt(r/k) factor that the derivation and the theorem need; a stray fragment "> 1 - e^{-c_3 k}." before the bound on III.
4. Proof of Lemma 6: gamma = -log(2)/K is negative.
5. Proof of Lemma 4: "gamma as in Theorem 4" should point to Lemma 6.
6. Talagrand's bound printed with "sigma + B r"; the r looks like a typo.
7. Smaller typos: a missing minus sign in 1 - e^{n t^2/2} (proof of Corollary 2); covariance N(0, sigma I) instead of sigma^2 in Lemma 3's proof; "p{-1}" in (22); the dimensions of Z^(R) and Z^(C) are swapped.
8. Sampling model: Section 4.1.2 says rows and columns are "sampled with replacement", but the model is Bernoulli inclusion, which is without replacement.
9. Discussion calls RCMC guarantees a future challenge although Theorem 2 proves the noiseless case (read as the noisy case).
10. Claim 1's proof cites "closest in Frobenius norm" while bounding the spectral norm; still valid by Eckart-Young.
11. Halko algorithm step 2: the formula does not type-check as printed; Q^(C)T is presumably meant.
