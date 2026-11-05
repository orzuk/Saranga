# 2605.09439 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 160 nodes (42 steps, 36 definitions, 27 algorithm steps, 22 equations, 7 remarks,
6 assumptions, 5 algorithms, 3 claims, 3 propositions, 3 proofs, 2 problems, 2 theorems, 1 corollary, 1 open problem),
269 edges (258 uses of which 23 mentions, 4 specializes, 3 resolves, 3 proves, 1 generalizes); 18 external nodes; two
orphans (the four Stable Diffusion targets; the saliency definition). Main results: the inner estimator (Algorithm 2)
and the full MLGD-F algorithm (Algorithm 4); the two problems CDMS and CDMO; Proposition 1 (plug-in loss concentrates),
Proposition 2 (bias and variance of the gradient estimator), Proposition 3 (memory-fidelity trade-off), Corollary 1
(identifiability under low-rank targets). paper_style: computational, modeling. The \Return lines came back empty from
the tool and were copied by hand; the "Step 1-5" summary sentences opening Proposition 2's proof became setup steps.

## Possible problems in the paper, for the author

1. Proposition 1 assumes only Assumptions 1-2, but eps_s is defined through f_true from Assumption 4, so Assumption 4 is used without being stated.
2. Proposition 3 names eps_d and eps_{g,d} before they are defined in E.8; E.8 then defines eps_d with f_* and eps_{g,d} with f_ref, two names for the reference sampler.
3. Section 4 says Algorithm 4 gives the "explicit form" of the deterministic DDIM step, but Algorithm 4 uses a stochastic reverse-SDE step with noise. Algorithm 4 also reuses the index i for the outer loop and the Monte Carlo loop.
4. C.1 calls the square root of |U-statistic| + eps an "unbiased" estimator, which it is not; its median-heuristic formula uses x_i, y_j instead of y_i, y-tilde_j.
5. Remark 2 writes Q_beta^(t) = P_t E[e^{-beta L} | x_t] as an equality; it holds only up to a normalising constant.
6. E.8 says that if eps_g is unknown, Proposition 2 "becomes a bias bound in terms of eps_g alone"; the bound still contains both terms.
7. Assumption 1(iii) says "equivalently, k is C^2 with bounded mixed partials"; a Lipschitz d-phi needs more than that.
8. The text after the problems says Q "concentrates at the mode of the loss"; it should be the minimiser.
9. Smaller inconsistencies: K_* is 20 for SDXL-Base in E.5 but 30 in Section 5.4; "K_max = L" in E.1 versus K_max = 5 elsewhere; Eq. (2) parametrises the bandwidths differently from the sigma_l used in Assumption 1.
