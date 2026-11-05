# 1309.6919 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 1 warning kept ("identifiable" vs "partially identifiable", different senses). 89 nodes (28
definitions, 15 equations, 15 steps, 8 algorithm steps, 6 remarks, 4 propositions, 4 proofs, 3 claims, 2 assumptions,
2 problems, 1 algorithm, 1 open problem), 148 edges (142 uses, 4 proves, 2 resolves); 7 external nodes, one backward
edge. Main results: Prop. 1 (rank criterion for identifiability, rank(A_(1)) = N), Prop. 2 (a critical read length L_c
exists), Prop. 3 (null-space criterion for partial identifiability), Prop. 4 (finite-sample error bounds in l2 and
Mahalanobis distance), the divide-and-conquer algorithm (Box 1). paper_style: modeling, theorem_proof.

Extraction notes: Box 1 is a framed block, extracted as a prose algorithm; equations (14) and (15) carry the same
duplicate \label; the two-step sampling model was typed as a definition; proves edges come from the "Proof of
Proposition" subsection headings; simulation parameters not extracted.

## Possible errors in the paper, for the author

1. Box 1 step (d) says "non-identifiable ... (i.e. species i is orthogonal to the null space)"; by Prop. 3 orthogonality means identifiable, so the condition is inverted.
2. Eq. (8) writes A_(1) x^(1) = A_(1) x^(2) = 0; this should not be 0, since the last entry is 1.
3. Proof of Prop. 2, L=1 part: x^(2) = x^(1) + x is missing epsilon; "P_x(x^(1))" is sloppy; "subsequence" should be "substring"; in the monotonicity part y and y' are mixed up, and the same A is used for L and L'.
4. Proof of Prop. 4 writes x and x* where x-hat is meant throughout.
5. D_{l2} is defined with sum_{i=1}^M; it should be N (M is the number of unique reads).
6. Appendix A.1 says "the next n_i - L nucleotides"; it should be L - n_i, and n_i and n_j are mixed. The proof of Prop. 1 ends with "MCR(L,S,A)".
7. Prop. 4 covers the simplex-constrained l2 estimator; Algorithm 1 solves x >= 0 and then normalizes, so the bound does not directly apply to its output.
8. The simulation text says "poisson sampling model", but the model is i.i.d./multinomial.
9. Fig. 3's caption uses N = 10,000 species while the text says 455,055.
10. "Divide-and-Conqour" typo in the A.5 heading.
