# cs/0507060 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors; two "ends mid-sentence" warnings kept (ClP12, ClP16 end at a display followed by \noindent or
\newpage; judged false positives). 113 nodes (41 equations, 17 definitions, 16 claims, 12 remarks, 10 steps, 4
assumptions, 3 theorems, 3 algorithm steps, 2 conjectures, 2 open problems, 1 proof, 1 example, 1 algorithm), 165 edges
(163 uses, 1 proves, 1 illustrates). The paper has no theorem environments: all but the equations is prose. 36 external
nodes. One orphan: the channel-capacity open problem, mentioned as motivation. Main results: the second-order expansion
of H with the new H^(2) (ClP3) and the Appendix coefficients H^(3)..H^(11) (ClP16, conjectural); conjectures: the
critical chain length N_c(k) = ceil((k+3)/2) and the rational form of H^(k) in lambda. paper_style: derivation, computational.

## Possible errors in the paper, for the author (the first two checked with sympy)

1. Eq. (40), the i.i.d. series, is wrong: the correct coefficient is -[(2p-1)^k/p^{k-1} + (1-2p)^k/(1-p)^{k-1}]/(k(k-1)).
   The paper has the opposite overall sign and p^k instead of p^{k-1}. For k=2 the true value is -(1-2p)^2/(2p(1-p)), the paper's formula gives a positive number.
2. The "free element" of [p(1-p)]^{2(k-1)} H^(k) has the wrong sign: the data gives -1/2, 1/6, -1/12 for k=2,3,4, which is (-1)^{k+1}/(k(k-1)), not (-1)^k/(k(k-1)).
3. The integers a_{j,k} in the H^(k)-form conjecture do not match the Appendix: with the prefactor 2^{4(k-1)}/(k(k-1)) the Appendix values give non-integer a_{j,k} (a factor -1/8 for k=3, 1/128 for k=4). Either the prefactor or the integrality claim is off.
4. Notation slips: lowercase n for N in eqs. (33) and (35); \sum_Y for \sum_R and "L=2" for k=2 in (37); eq. (33) uses 1_{S_i=S_{i+1}} but defines 1_{s,s'}; the Z in (33) is Q(R), not the Z of (16).
5. The settling threshold is stated two ways: the conjecture says N > N_c(k), the observations and the Summary say N >= N_c(k).
6. Unproved or loose steps: A_0 sum_R e^{H(R)} = 1 holds only up to O(tanh^N J) with periodic boundary conditions;
   analyticity of C_N and H at epsilon = 0 and swapping the limit with the Taylor coefficients are asserted, not proved;
   rho(p) = lim H^(k)/H^(k+1) needs an absolute value; the Cover-Thomas lower bound is used in Sec. 5 and Fig. 4 but never stated.
