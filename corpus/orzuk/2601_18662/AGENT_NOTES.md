# 2601.18662 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 283 nodes (84 steps, 61 equations, 31 definitions, 31 algorithm steps, 20 remarks,
18 claims, 11 proofs, 7 examples, 5 algorithms, 3 lemmas, 3 propositions, 3 assumptions, 2 theorems, 2 problems,
1 corollary, 1 conjecture), 447 edges (422 uses, 11 proves, 10 illustrates, 3 resolves, 1 generalizes); 6 external
nodes (standard notions only). Main results: Theorem 2.1 (the decomposition and its converse), Prop 2.3 (stability),
the Newton-CG method and its global-convergence claim, Prop 4.1 (exponential utility), Algorithm 1 (backward
elimination), Theorem 5.2 (bilinear triangular decomposition), Prop 5.3 (variational U). Citations are only applied
(Slater/strong duality, self-concordance, inexact-Newton rates, Takahashi recursions, Sylvester's identity); the three
claims resting on them are semi_formal. The \Return lines came back empty from the pseudocode tool and were dropped.
The agent spot-checked the 2x2 example, the block-inverse and Schur computations, the perturbation constants and the
~330x ratio: correct.

## Possible issues in the paper, for the author

1. Appendix B says the residual uses "the corresponding dual gradient for Example II", but the dual example is Example III.
2. Proof of Prop 2.3, Step 3: "At t = 1 the first bound is (B_stab)" is off: (B_stab) is the fourth expression in the chain, not the first; the display also ends with "," before a new sentence.
3. Section 3's "arg min" is typed as plain math, not \arg\min.
4. Section 2.2 calls A "G-fixed", Section 3.5 "G-invariant".
5. Section 3.5 / Example IV: "G permutes r blocks" reads as permuting the blocks; per the figure it means permutations within blocks. The bound m_G <= r(r+1)/2 also relies on the zero-diagonal constraint of Example IV, which Section 3.5 does not state.
6. Proof of Theorem 5.2(ii): uniqueness when a solution exists needs pi_k != 0, shown only in part (iii); "if no zero pivot occurs the algorithm produces a solution" is asserted without being checked.
7. Example 5.4 cites only Theorem 5.2(ii) for the "iff"; it needs (ii) and (iii) together.
8. In Prop 5.3, B denotes the 2n x 2n matrix, clashing with B as the inverted component elsewhere; the decomposition is written with Q.
