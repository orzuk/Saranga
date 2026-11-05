# 2112.15534 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 141 nodes (54 equations, 26 steps, 18 definitions, 13 claims, 11 remarks, 6 proofs,
4 theorems, 2 examples, 2 open problems, 1 each problem, corollary, proposition, conjecture, lemma), 198 edges (188
uses, 6 proves, 2 illustrates, 2 resolves); 11 external nodes; one orphan (a "study other distributions" remark).
Main results: Theorem 1 (the almost-sure phase transition at k_n ~ gamma^{-1} log n with gamma = -E log S(X)) and
Corollary 1 (the same transition for p_{k,n}); also Proposition 1 (continuous and Bernoulli as the extreme cases),
Lemma 1 (coupling with maxima of iid geometrics), the Bernoulli exact formulas and variance, and the conjecture for
weak maxima q_{k,n}. Cited: Bai et al. 2005, Barndorff-Nielsen & Sobel 1966, Hwang 2004 (whose open question TP1
partly resolves). The proof of Theorem 1 is all of Section 4 in prose, one proof node with the lemma block as a step.

## Possible errors in the paper, for the author

1. Threshold: the introduction ("slower than gamma log n") and Section 3.3 ("localization at gamma = 1/2 log 2") use gamma
   where Theorem 1 has gamma^{-1}. The Fig. 1c caption says log p -> 0 for c < gamma and -> -inf for c > gamma, the reverse of
   Theorem 1, whose threshold is gamma^{-1} ~ 2.885.
2. Section 2.4, two claims that fail in general: S[S^{-1}(y)] <= y is false for a left-continuous S (Bernoulli(p) with
   p < y < 1: S^{-1}(y) = 0 and S(0) = 1; the step P[X > S^{-1}] = S[S^{-1}] conflates P(X > s) with P(X >= s); the bound
   gamma <= 1 still holds). "gamma = 0 iff S = 1, i.e. X infinite" is wrong: a degenerate F has S(X) = 1 a.s., so gamma = 0;
   gamma in (0,1] needs a non-degenerate F.
3. The joint-probability formula before (26) lacks the multinomial cell probabilities ((1-p)^2)^a (p(1-p))^{b+c} p^{2d}, and writes k_n where k is meant.
4. Proof of Lemma 1 / continuation: the |gamma^{-1} - [log(1-alpha_l)]^{-1}| condition is missing a minus sign (should be
   gamma^{-1} + [log(1-alpha_l)]^{-1}); "G_1^{(alpha_l)}" should be G_2; the remark after Lemma 1 writes "1-alpha < e^{-gamma}"
   twice, the second should be ">"; "Therefore P(M_n > M_n^1 i.o.) = 0" skips the short argument from hitting times to maxima.
5. Typos: proof of Proposition 1 part 2, B_i^j and X_i^j should be B_i^k and X_i^k (B_ij also clashes with the counts in 3.2);
   Fig. 1a "p_{k,n}^{(0.5)} < p_{k,n}" lacks the (U); Fig. 1b says "exact combinatorial formula" but the text says the recurrence
   was used; Section 2.4 "and hence is well-defined" lacks its subject (gamma).
