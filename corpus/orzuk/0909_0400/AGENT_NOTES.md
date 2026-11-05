# 0909.0400 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 107 nodes (34 definitions, 19 claims, 14 equations, 10 algorithm steps, 8 problems,
6 assumptions, 5 theorems, 4 algorithms, 3 remarks, 3 open problems, 1 example), 209 edges (201 uses, 6 illustrates,
2 resolves); 15 external nodes; 19 nodes carry rigor (numerical findings). paper_style: computational, modeling.
Only the 14 numbered equations come from environments; 93 nodes are prose. Main results: the reconstruction algorithm
(AP2: GPSR l1 solve, round the top-s entries to {0,1,2}, keep the s with smallest residual), the barcoded-pools
design (AP3), and the simulation findings as claims (up to 20000 individuals with k=500 lanes; efficiency score >= 10,
up to 70; f = 1% and 2%; barcodes give a large increase in N_max).

Extraction notes: no theorem environments; results are read off figures. The optimization problems are equation nodes
nested inside prose problem nodes. The abstract's headline (4 carriers out of 4000+ with ~10 lanes and 10 barcodes) is
never stated in the body, so it has no node.

## Things in the paper that look wrong or unclear, for the author

- Appendix A: the read-error convolution z*e_r = z + e_r - 2 z e_r is applied to the count vector z, when it only makes
  sense for frequencies z/r; M' is reused for the augmented matrix although it already means M+D; z' is never defined;
  with the 1/2 prefactor the -1 column contributes -x_{N+1}/2, not -x_{N+1}; the extra variable x_{N+1} is neither
  sparse nor integer but the l1 objective penalizes it anyway.
- Eq. (12) is written with an unsquared l2 residual; GPSR minimizes 1/2 ||.||_2^2 + tau ||x||_1.
- tau scaling: the text says it scales with ||M^T y||_inf, the setting uses M-hat^T y, while the sensing matrix is M-hat/2.
- Gamma assumption r ~ Gamma(R/L, 1) uses R and L before they are defined.
- Footnote "simple linear transformation x -> (2x-1)/sqrt(k)": the map is affine, and its effect on the CS problem (a rank-one shift) is not discussed.
- Intractability of l0 is cited to candes2005error; the usual reference is Natarajan 1995.
- Typos: "s is the is the number" (Sec. 2.1); "posses"; Sec. 3.4 "but without using barcodes, could not recover" has no subject; "Assert`ion" in a \newtheorem (not printed).
