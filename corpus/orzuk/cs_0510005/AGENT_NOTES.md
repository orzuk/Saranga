# cs/0510005 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 126 nodes (36 steps, 29 equations, 18 definitions, 10 remarks, 9 theorems of which 8
external, 7 claims, 7 proofs, 3 lemmas, 3 algorithm steps, 2 propositions, 1 assumption, 1 algorithm), 194 edges
(186 uses, 7 proves, 1 generalizes; 7 mentions, 2 backward). 16 external nodes; one orphan, the Nair-Ordentlich-Weissman
rare-transitions result cited only as contrast. Main results: Theorem 1 (High-SNR coefficients settle, C_N^(k) = C^(k)
for N >= ceil((k+3)/2), assuming analyticity), Theorem 2 (the same in the Almost-Memoryless regime, analyticity proved),
Propositions 1 and 2 (first-order expansions, general alphabet), the symmetric-binary A-M series to O(delta^14).

Choices: each lemma/proposition environment contains its own proof (proves edges added by hand); edges from Theorem 1
that only use the symbol C_N are mentions (otherwise a false cycle); Theorem 2 is semi_formal (part 2 "analogous, details
omitted"); two numerical claims from the figures; one claim asserted without proof. Han-Marcus Thm 1.1 is only applied
and the ZKD1 conjecture only mentioned, so neither is a node.

## Possible errors in the paper, for the author

1. Lemma 1 has F_{N-j+1}([e]_{j+1}^N), but the proof and Lemma 3 use [e]_j^N: the index range should start at j.
2. The proofs of Lemmas 2 and 3 write sum_r t_{X_i r} P(Z^{(j->r)}); since X is summed out the factor should be t_{r Z_j}.
3. Proof of Theorem 1: l(k) takes the min over k_i > 1, but the support argument needs the first nonzero entry; "It easily
   follows" hides the counting; passing to the limit needs the uniform-bound assumption that appears only in the footnote.
4. Proposition 1 assumes analyticity "near delta = 0"; it should be epsilon = 0. Theorem 2 writes H-bar(M,T,epsilon) where delta is meant.
5. xi is called "the vector of N ones"; it should have s entries.
6. "Computing C_2 enables us to extract H-bar^{(k)}": C_2 gives only k <= 1.
7. In the expansion of F .* log F, the factor [I + log(...)] should be the all-ones matrix, not I (the final result is consistent with all-ones).
8. Section 4 writes the point "(epsilon, 1/2)" in (p, epsilon) coordinates; it should be (1/2, epsilon). Small transposes, e.g. pi R where pi^t R is meant.
9. T means the noise perturbation in the High-SNR regime and the Markov perturbation in the A-M regime.
