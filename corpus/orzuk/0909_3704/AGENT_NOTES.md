# 0909.3704 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 1 warning kept ("conservative" in ExP1/ClP24 describes a procedure, a different sense from the
defined estimator term). 118 nodes (32 claims, 30 definitions, 26 equations, 7 algorithm steps, 6 remarks, 5 theorems,
5 proofs, 2 algorithms, 2 steps, 1 open problem, 1 corollary, 1 example), 239 edges (232 uses, 5 proves, 1 resolves,
1 illustrates); 38 external nodes. Main results: Thm 2.3 (FDR <= m0 q E[1/m0-hat^(not 1)] for a monotonic estimator),
Thm 4.1 (FDR monotonicity), Claim 3.2 (IBHlog controls the FDR), "both procedures control the FDR".

Extraction notes: the proofs of Thm 2.3, Claim 3.2 and Thm 4.1 are only in the supplement; PP4 is the one-sentence
proof outline for Claim 3.2. ClP9 both asserts E[m0-hat'] <= m and defines "stochastically smaller". U, V, T, S are
defined only in Table 1 (no definition nodes). Simulation and real-data findings are numerical claims.

## Possible errors in the paper, for the author

1. Claim 3.1(a) says E[m0-hat'] >= m; it should be >= m0.
2. The proof of 3.1(a) writes E[m0-tilde'] = sum E[log(1-p_j)] without the minus sign.
3. Def 2.2 defines the step-down rule with alpha_i where gamma_i seems intended.
4. The supplement list calls the IBHlog proof "Claim 3.1"; it is Claim 3.2.
5. Thm 2.3 needs a monotonic estimator, but monotonicity is only asserted for the uncorrected m0-hat' and m0-tilde'. For the
   IBHsum estimator C(m) min[m, max(s(m), m0-hat')], Definition 2.1(ii) depends on C(m) and s(m) and is never checked;
   IBHsum control also rests on numerically computed C and s.
6. Thm 4.1 uses "threshold FDR procedures" and "for any q" without defining them. The Corollary says "monotonically decreasing" where the theorem says "nonincreasing".
7. FNR is described as T/m1; Genovese-Wasserman define it relative to non-rejections.
8. Table 2 prints "(0.0340"; it should be "(0.034)".
9. Sec. 6.2 speaks of the "standard deviations of V/R+" on real data, where V is unknown.
