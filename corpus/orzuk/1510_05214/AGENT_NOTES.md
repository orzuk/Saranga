# 1510.05214 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 94 nodes (29 definitions, 19 algorithm steps, 15 claims, 13 equations, 8 algorithms,
4 remarks, 3 theorems, 2 problems, 1 open problem), 112 edges (108 uses, 2 resolves, 2 generalizes); 42 external
nodes; one orphan (Dynamic Time Warping, mentioned but unused). Main results: Group-Sparse K-means (Algorithm 1, 5
steps) and multivariate group-sparse clustering; supporting: the group-sparse K-means problem (eq. 7), the claim that it
generalizes sparse K-means, the scale-based and scattering group partitions. paper_style: modeling, computational.
Cited: sparse K-means (Witten-Tibshirani), wavelet decomposition, DWT and wavelet shrinkage (Donoho), group norm (Bach et
al.), scattering transform (Mallat), ARI, the Giacofci and Antoniadis baselines.

## Possible errors or unclear points, for the author

1. Phoneme counts: 800+757+1163+695+1022 = 4437, not the 4507 stated (the ESL dataset has "sh" = 872 and a total of 4509).
2. Scale groups g_j = {w_{2^j}, ..., w_{2^{j+1}-1}} with j = 0..log2(T): the last group goes past index T; the range should probably end at log2(T) - 1.
3. DWT index range k = 0..2^j should be 2^j - 1; "vector of coefficients c_0, Psi_{j,k}" should read v_{j,k}.
4. Multivariate groups {t, t+T, ..., t+GT} have G+1 elements; the last should be t + (G-1)T.
5. Notation slips: "v_(g) the elements of w" (v vs w); "Let |g| the number..." missing "be"; "updating the clusters C_j" uses j where the rest uses k; "|x * Psi^(1)|" should have f; "for each S^(L)_{j_1..j_l}" should be S^(l).
6. SPARCScatter, the best method in Table 1, is never defined in the text. The text attributes "only 2 non-zero weights" to the group-sparse Wheat run, while Table 2's ||w||_0 = 2 seems to describe SPARCScatter itself.
7. Typos: "led to the about the same results... ARI=0.87)" (extra "the", stray parenthesis); "lead" for "led" (twice); ", ," in the ARI definition; "it's group extension"; "Phenome" and "weighs" in captions; the appendix subsections are numbered 6.x.
