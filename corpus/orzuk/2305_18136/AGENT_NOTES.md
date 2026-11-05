# 2305.18136 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 88 nodes (27 steps, 14 definitions, 13 claims, 12 equations, 6 algorithm steps,
5 remarks, 4 proofs, 2 assumptions, 1 problem, 1 theorem, 1 corollary, 1 example, 1 algorithm), 183 edges (175 uses,
4 proves, 2 resolves, 1 specializes, 1 illustrates); only the fBm definition and its covariance are external (the other
cited results are only applied). Main result: Theorem 1.1, the unique decomposition Lambda = Q-hat^{-1} + Gamma-hat,
the optimal strategy (2.4) and the value (2.5); also Corollary 1.3 (D=0 and D=1), the Step II verification claim and
Algorithm 1. The proof of Theorem 1.1 has 22 steps (Steps I-III, plus 7 inside the nested claim). paper_style:
theorem_proof, computational. The agent checked the closed forms of Example 1.5 (Cases I and II) and Corollary 1.3
against Theorem 1.1: they agree.

## Possible errors in the paper, for the author

1. Remark 1.2: the value in the trivial cases is written exp(-1/2 mu Lambda mu'); by (2.5) it should be -exp(-1/2 mu Lambda mu'): the minus sign is missing.
2. Section 3, Laplace expansion: the minor index is written [2:2+D]^{1+j -> 2+D}; it should be [2:1+D]^{1+j -> 2+D}, otherwise index 2+D appears twice. Algorithm line 4 uses the correct form.
3. Section 3, start: "R_ij = Lambda_ij for i,j < D+1" disagrees with the later condition |i-j| <= D; the argument needs the band condition.
4. Legendre-Fenchel inequality stated "for all x, y in R", but log y needs y > 0.
5. Step I: "Since Sigma is symmetric..." is meant as Lambda being symmetric (harmless).
6. Section 3, fBm discussion: "the value increases with D towards the maximum 0" contradicts the earlier "decrease in the value as D in increasing"; probably means increasing in H. "D in increasing" is a typo for "is".
7. Discretized fBm covariance indexes increments as B_{(i+1)dt} - B_{i dt}, while S_i - S_{i-1} = B_{i dt} - B_{(i-1)dt}: an index shift, harmless by stationarity.
