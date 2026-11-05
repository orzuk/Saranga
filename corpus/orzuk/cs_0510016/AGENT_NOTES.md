# cs/0510016 — extraction agent's notes (Claude Opus 5.5, frozen v7 prompt, 2026-11-05)

finalize: 0 errors, 0 warnings. 69 nodes (20 steps, 18 equations, 12 definitions, 5 claims, 4 theorems, 4 proofs, 3 lemmas,
1 assumption, 1 open problem, 1 remark), 128 edges (124 uses, 4 proves). 10 external nodes. Main result: Theorem 1 (TP3),
C_N^{(k)} = C^{(k)} for N >= ceil((k+3)/2), through the blocking (LP1), zero-padding (LP2) and no-hole (LP3) lemmas.

Extraction notes: each lemma's proof sits inside its lemma environment with the \label after \end{proof}, so the \ref edges
start at the proofs; named edges were added from the lemmas. The proof of Theorem 1 is linked only by "We are now ready to
prove our main theorem". The ZKD1 conjecture the paper generalizes is never stated (no node).

## Possible errors in the paper, for the author

1. Lemma 1 index: states F_N([e]_1^N) = F_{N-j+1}([e]_{j+1}^N); the proof sums over [Z]_j^N and Lemma 3 applies it to [e]_j^N, so j+1 should be j.
2. Eq. (11): C_N^{(k)} = sum_{omega(k)=k} F_N^k is missing the multinomial factor 1/(k_1! ... k_N!). The term-by-term argument of the main proof is unaffected.
3. Conditional entropy is written with P(U=u) where P(V=v) is meant.
4. SNR wording: "the signal to noise ratio (SNR) is small", but the next sentence works in the high-SNR (small-noise) regime.
5. t_{X_i r} in Lemmas 2-3: the index i is not bound there; the derivative at Z_j = X_j suggests t_{r Z_j}.
6. Proof of Theorem 1, step 1: "It easily follows" hides work: the case with no k_i > 1 (minimum over an empty set) is not handled, and Lemma 2 only adds zeros, so using it here needs the removed leading entries to be zero, a further use of Lemma 3 not written out.
7. Lemma 2, case k_1 = 1, is shown only for r = 1.
8. The last step of Theorem 1 rests on the footnote's unproven assumption of analyticity uniform in N (recorded in extraction_comment).
9. Two claims in the Conclusion are asserted without proof: weaker settling for relative entropy at N >= k, and the same settling in the almost-memoryless regime.
