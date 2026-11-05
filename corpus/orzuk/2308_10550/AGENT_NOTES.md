# 2308.10550 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors; two warnings kept ("trading strategy" in RP15 means the continuous-time notion; the appendix c_k
claim ends on a display). 263 nodes (114 steps, 51 equations, 33 definitions, 16 proofs, 16 remarks, 14 claims,
7 assumptions, 6 lemmas, 4 theorems, 2 problems), 353 edges (331 uses, 16 proves, 3 resolves, 2 specializes); 3
external nodes (the Bachelier model, Toeplitz matrices, Hitsuda's 1968 representation theorem). Main results: Theorem
2.2 (explicit discrete-time optimizer, Toeplitz/banded A, and its value), Theorem 4.1 (scaling limit in the Bachelier
model), Theorem 4.3 (the continuous-time problem equals that limit). Display (9.2) retyped from equation to claim
("the upper bound", proved in Sec. 5.2). The agent checked Lemmas 3.2/3.3, identity (6.6) and the identities in (comp)
numerically: they hold.

## Possible errors in the paper, for the author

1. (6.5) is missing a minus sign: it reads -exp(+1/2 int ...), but should be -exp(-1/2 int ...). Only the corrected form, with (6.6), gives (9.2); the numbers confirm it.
2. Remark 4.4 conflicts with (eq:alpha_def): it says alpha_H -> 1 as H -> 0, but the formula gives alpha_H -> 1 - sigma-hat/sigma, as the Figure 3 caption says.
3. Remark 4.4's Merton line gives theta/(2 sigma^2), while (vol) gives theta/sigma^2.
4. Factor in (vol): the integral has prefactor 1/(2 sigma^2), but the proof of Theorem 4.1 derives 1/sigma^2, consistent with (1.5).
5. Small typos: the proof of Lemma 3.3 ends "= n sigma^2" where n sigma-hat^2/sigma^2 is meant; "(D - 2n - D - 1) v_1" for D(2n - D - 1) v_1; Lemma 3.2 Step II has "i_i" for i_1; the proof of Theorem 4.1 writes U_n(H, mu, ...) for U_n(H, theta, ...); the lower-bound display in the proof of Theorem 4.3 has V^pi where V^{pi_*} is meant; the Figure 1 asymptotic kappa_0 ~ (1/H)(1 - sigma-hat^2/sigma^2) does not match (eq:alpha_def), which gives (1/H)(sigma/sigma-hat - 1).
6. Gap in the proof of (9.2): the kernel l^eps is cut off at length (H - eps) ^ (1 - s) but keeps the denominator 1 + a-hat(H ^ (1 - s)), so it seems not to satisfy the variance constraint defining Gamma_eps for eps > 0, and the eps -> 0 limit is only sketched.
