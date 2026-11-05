# 2209.00346 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 183 nodes (76 equations, 56 steps, 14 definitions, 12 remarks, 7 theorems, 6 proofs,
3 claims, 2 lemmas, 2 algorithms, 2 algorithm steps, 1 open problem, 1 conjecture, 1 example), 191 edges (181 uses,
6 proves, 3 generalizes, 1 illustrates); 16 external nodes; one orphan (a chain on m of n variables has n!/m! linear
extensions). Main results: Theorem 2 (the correlation inequality), Theorem 3 (asymptotic independence of two maxima
events), Theorem 4 (LLN and CLTs for partial sums). Cited: XYZ inequality (Shepp; Fishburn), O'Neill's formula and
asymptotics for p_n, the Bai et al. variance result, #P-completeness of counting linear extensions
(Brightwell-Winkler), the failed generalizations (Shepp/Graham, Brightwell). Eq. (3) of the introduction is Theorem 2 in
other notation (also_stated_at); "Problem 1" is typed open_problem; the Bai/O'Neill argument for Theorem 3(2) is an
alternative proof.

## Things that looked wrong or unclear, for the author

1. Proof of Thm 2, possible gap: it proves the inequality pointwise given x_[2] and says "the theorem will follow by
   integration"; integrating fg <= hl gives int fg <= int hl, not (int f)(int g) <= (int h)(int l), which the unconditional ratio needs.
2. Proof of Lemma 1: line 3 drops a factor 1/n, since P(W_1 = 1 | W = i) = i/n; the next "= n E(W^2)/E(W)" has a spurious n; the correct value is E(W^2)/E(W) >= EW.
3. Upper bound (eq. 51): the inclusion-exclusion sum should run to u = n-1, not n-2; the next step uses sum = p_{k,n-1} - 1.
4. Proof of Thm 4(1) says "n rho_{k,n} -> inf"; it should be n p_n -> inf, Lemma 2's hypothesis (n rho actually -> 0).
5. Remark 1: H_i = {(a_i, b_j)} should be (a_i, b_i).
6. Problem 1 says "n i.i.d." for U_1..U_l.
7. Conjecture 1: the sums run j = 1..m, but the second indices lie in {2k+1..n}.
8. "All three conditions are necessary": a counterexample is given only for the equal-size condition. The agent brute-forced that counterexample; the numbers are right (861/2100 vs 336/840).
9. The printed command said to verify counterexample (27) uses the sets of Remark 3 with n = 9, not the sets in (27).
10. Notation slips: p_{k,n} and e_{k,m_n} alongside p_n; Z_1 used before it is defined; Z_i^{k,n} in Thm 4(1); Thm 3's proof writes {X_ij > x_mj}, the reverse orientation (harmless by symmetry); "\ldots.l" and "\mathbb[0,1]^k"; \label{eq:three_boxes_volumes} sits on an unnumbered align row.
11. Thm 4(3) states m_n << n log^k n, but the proof gives the stronger m_n < c' n log^{k-1} n.
