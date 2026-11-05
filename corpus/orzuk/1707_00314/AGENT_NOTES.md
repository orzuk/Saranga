# 1707.00314 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors; two warnings kept (DP14 "introducing symbols in separate sentences", a false positive from an "e.g.";
the Grigelionis proposition stated inside the proof of Theorem 4.1 is also used in the proof of Theorem 4.2, a real use).
279 nodes (88 equations, 82 steps, 23 definitions, 17 claims, 16 theorems, 16 proofs, 10 remarks, 9 algorithm steps,
4 lemmas, 3 problems, 3 algorithms, 3 open problems, 2 assumptions, 2 corollaries, 1 conjecture), 360 edges (339 uses,
16 proves, 4 resolves, 1 specializes: Theorem 3.1 to Robbins-Siegmund); 40 external nodes. Main results: Theorems 2.1
and 2.2 (limits of linear combinations of partial maxima), Theorem 3.1 (generalized Robbins-Siegmund), Theorems 4.1 and
4.2 (asymptotics of h^(1) and h^(2)), Theorem 4.4 (nu ~ 2 ln k), Theorem 4.5, two prose claims (the factor
2^{2/(N0-1)}; first-order equivalence at the optimal nu). The proofs are written as \proof...\endproof, which the parser
does not recognise, so they are prose proofs; the pseudocode parser nested Stage Two of Algorithm 1 under a Stage One
line, corrected in the build script.

## Possible errors in the paper, for the author

1. Ghosh density, (4.17)/(4.19): the exponent 1 + nu/2 gives a tail t^{-(nu+2)}, but (4.21) says t^{-(nu+1)}; using the
   exponent (nu+1)/2 after Euler (nu + 1/2 before it) reproduces the constant in (4.21) exactly.
2. Remark 4: lim_{nu -> inf} h_k^(2) should be sqrt(2) Phi^{-1}(p^{1/k}), not Phi^{-1}(p^{1/k})/sqrt(2); this also fits Theorem 4.3.
3. Proof of Theorem 4.3: h_k^{+-} uses b_k - g/a_k and b_k - z_p where the signs should be +; "h_k(tau)^+" should read h_k^{+-}(tau); q_p is used where the Gumbel quantile g_p is meant.
4. Proof of Theorem 4.5: part 2 announces two cases but only treats case (i).
5. Proof of Theorem 2.2: the proof scales by a_{delta_k^{t*}} but L** is defined with a_k; the second line of the align is missing "lim"; {Y_t; t in T_1} where T_2 is meant, and L* where L** is meant.
6. Proof of Theorem 3.1: in (3.5), max over i <= k - s_k + 1 should be k - s_k; (3.17) swaps Delta and sigma; b_k carries -ln(4 pi) where the standard constant has +.
7. Theorem 4.4 proof: the bounds on 2 ln(Gamma(nu/2)/Gamma((nu+1)/2)) and on nu (Psi((nu+1)/2) - Psi(nu/2)) fail for nu <= 2, so H_k(1) < 0 is not justified at nu = 1; (4.44) takes ln of the negative number sqrt(pi) ln p; the theorem claims the result for both j but proves only j = 1.
8. Wrong cross-references: Corollary 2's proof cites Lemma 3 (about h^(1), not h^(2)); Remark 4 cites (4.26) where Theorems 4.1-4.2 are meant; Rinott's "Step 3/Step 2" does not match Algorithm 1's numbering.
9. Smaller typos: N(theta_j, sigma_j^2) should be N(theta_i, sigma_i^2); the Frechet c.d.f. "e^{-x}^{-nu}" should be e^{-x^{-nu}}; Theorem 4.5 writes nu-tilde^{(i*)} where the index should be j; its source has stray Hebrew vowel marks inside \tilde{N}.
