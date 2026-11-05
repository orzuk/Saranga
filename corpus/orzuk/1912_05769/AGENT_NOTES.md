# 1912.05769 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors; warnings kept (symbols reused with another meaning: P_value, F-hat^n_X; a sentence split at a colon;
(x_i, y_i) as a generic data point). 174 nodes (37 definitions, 29 equations, 17 claims, 10 algorithms, 9 remarks, 5
proofs, 4 propositions, 2 theorems, 1 each lemma, corollary, problem, example, conjecture, assumption; 4 proof steps, 52
algorithm steps), 198 edges (186 uses, 5 proves, 4 resolves, 2 illustrates, 1 generalizes); 6 external nodes (Harrison
2012, Vardi 1985, Kou-McCullagh sampler, three cited equations); 9 backward edges. The \ref{alg:...} edges did not resolve
(each algorithm's \label sits after the algorithmic body), added by hand. Main results: Claim 1 and Lemma 3.1 leading to
Corollary 1 (null law of P_W-permuted data), type-1 error control of the WP test, Proposition 1 (pooled empirical CDF
consistent under exchangeability and truncation), consistency of the inverse-weighted marginals when w > 0, Algorithms
1-3, the marginal-estimation algorithm and the LTRC adaptation; the Discussion's consistency conjecture is a node.
paper_style: modeling, computational.

## Possible errors in the paper, for the author

1. The Algorithm 3 (bootstrap) P-value uses 1{T_0 >= T_i}; Algorithm 1 uses T_i >= T_0. One looks reversed.
2. The Supp. 8.5 algorithm loops "While max_j d(...) < eps"; this should be > eps.
3. Eq. (12) writes F-hat^n_XY(x, inf); it should be (t, inf).
4. Sec. 4.2.1 writes f_X(x) = E{w(x, Y-tilde)} f-tilde(x)/...; this should be the observed f^(w)_X, and f-tilde should be f-tilde_X.
5. In Eq. (29), prod_{l != j} F_i(dx_{il}) should be F_l.
6. In Algorithm 4 the P_IS update uses W(sigma(i), pi_b(i)); it should be pi_b(sigma(i)). The prose says "select pi(i) maximizing", but the algorithm samples in proportion to W.
7. Step numbers are off: "stage 6" of Algorithm 1 is line 5; "step 9" of Algorithm 4 (the sampling line) is line 8; the uniform grid is written "0 = alpha_1 < alpha_0 < ..."; Kou-McCullagh defines C_i = sum_j W(i,j) but then uses C_j.
8. Definition 1 is titled "(quasi-dependence)" but defines quasi-independence. Remark 2 writes w = 1(x,y).
9. The LD marginals disagree in three places: main text exp(5) and Weibull(3, 8.5); caption X ~ Weibull(8.5, 3), Y ~ exp(0.2); Supp. text X ~ exp(0.2). CNorm's Y is U[0,16] in the main text but U[0,1] in the Supp.
10. The text says bootstrap has the highest power for CLmix, but Table 1 bolds WP (0.412 vs 0.338). "Our method has the highest power for all rho" fails at CNorm(-0.3), where minP2 is bolded.
11. \ref{fig:example} does not resolve (the label is "example"). The Supp. says the p-value "cannot be lower than 1/B"; it should be 1/(B+1).
