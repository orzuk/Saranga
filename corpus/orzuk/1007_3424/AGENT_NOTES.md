# 1007.3424 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 105 nodes (24 claims, 19 definitions, 17 algorithm steps, 16 equations, 7 algorithms,
7 remarks, 5 problems, 5 assumptions, 4 theorems, 1 example), 144 edges (138 uses, 3 resolves, 2 illustrates,
1 generalizes); 8 external nodes; 34 nodes carry rigor (mostly numerical). No proofs. Main results: the BCS algorithm
(AP1, spread over the introduction, the GPSR solver in 2.2 and the appendix preprocessing), and the findings as claims:
16S rRNA varies enough to reconstruct mixtures of tens of species; graceful degradation under realistic noise; the
five-species wet-lab mixture (3 of 5 found, one more at genus level, E. coli mistaken for S. enterica).
paper_style: modeling, computational. Cited: classical CS recovery under RIP, NP-hardness of l0, l1 relaxation,
robustness to noise, RIP/UUP, mutual coherence.

## Things in the paper that look wrong or unclear, for the author

1. RIP is spelled out as "Robust Isometry Property"; the standard name is Restricted Isometry Property.
2. S is N x k with S_ij the j-th nucleotide of species i, but A is called k x N with A_ij = 1 iff S_ij = 'A': the indices are transposed; it should be A_ji.
3. Eq. (B.2): j is both the free index and the summation index; parentheses are missing; as written d_ij sums to 1 over a read, so its mean is 1/(k-1), not the 1 the text says the normalisation ensures (a factor k-1 looks missing).
4. P means both the PSSM (2.1) and the peak-position table P(alpha). In Appendix B, a_ij is a peak height and c the Gaussian width, clashing with the PSSM entries a_j, c_j.
5. Section 3.1.3 says the power-law and uniform curves are the "blue and green lines" of Fig. 4B; per the caption the uniform 16S curve is black and green is the random-sequence database.
6. A stray "4" in "Figure \ref{fig:PowerlawReconstruction}4.A,B" and a doubled "with with".
7. The usable region is bins 125-700 in the text but 100-700 in the Fig. 7 caption.
8. "RMSE" is defined as the plain l2 norm, with no mean or root-mean factor.
9. The Fig. 4C caption describes precision as the "fraction of incorrect sequences identified", the opposite of the definition in the text.
10. Section 2.3 says sequences within 2 bp of another were removed; E. coli was removed for differing from S. enterica by 2 bases only in the region used, so the removal must have been done on that region, which the paper never says.
