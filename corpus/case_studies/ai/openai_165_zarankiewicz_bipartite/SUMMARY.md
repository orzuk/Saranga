# OpenAI release, family 165: the crossing number of complete bipartite graphs

AI-written paper (OpenAI internal model, September 23 2026; Lean-formalized main result). The claim:
cr(K_{m,n}) = d_m d_n with d_r = floor(r/2) floor((r-1)/2) for all m, n, i.e. Zarankiewicz's conjecture
(Turan's brickyard problem), with the classical drawings optimal among all plane drawings with continuous
edge arcs. The companion manuscript in the same family claims the Harary-Hill formula for K_n.

## Files

| File | What |
|---|---|
| `openai_165_zarankiewicz_bipartite.json` (+ `_new.html`) | LLM graph: frozen v7 prompt, Claude Opus 5.5 agent, finalize 0 errors, 1 warning kept (the rigor-on-sketch rule conflict) |
| `openai_165_zarankiewicz_bipartite_rules.json` (+ `_rules_new.html`) | Rules graph (alg3) |
| `scripts/build_165.py` | The extraction's build script |
| `prompt_v7.md` | The rendered prompt the agent followed |
| `paper.pdf`, `paper.tex`, `arxiv_src/` | The manuscript (not committed) |

## Counts

| | LLM (v7) | Rules (alg3) |
|---|---|---|
| Nodes | 177: 63 Level-1 + 114 proof steps; 24 equations, 16 definitions, 9 proofs, 6 lemmas, 4 theorems, 2 assumptions, 1 remark, 1 corollary | 90: 60 equations, 12 definitions, 7 proofs, 6 lemmas, 2 claims, 1 theorem |
| Edges | 194: 182 uses, 9 proves, 3 specializes; basis inferred 67, ref 63, term 54, syntax 6, named 4; 7 backward | 43 |
| Level-1 by origin | 54 paper, 9 external | |
| Results view | 11 results, 10 dependencies, longest chain 4 | |

## What the graph shows

- **Main results.** Theorem 1.1 (TP1); the extractor also marked Lemma 2.1 (the subspace intersection
  bound) and Lemma 4.2 (the rank detector Phi) as main, since the paper presents them as its tools.
  Theorem 1.1 `specializes` the three cited partial results it contains: Kleitman 1970 (one class of at
  most 6 vertices), Woodall 1993 (K_{7,7}, K_{7,9} by computation) and Balogh et al. 2023 (the 0.9118
  bound). There is no conjecture node and no `resolves` edge: the paper names Zarankiewicz's conjecture
  and Turan's problem but never states them apart from Theorem 1.1.
- **Short spine, heavy proofs.** Four results on the chain, Lemma 4.1 -> Lemma 4.2 -> Theorem 1.1, and
  Theorem 1.1 rests on 7 results, none external. The work is inside the proofs: 9 proofs, 114 steps,
  the proof of Theorem 1.1 is the whole of Section 5 with no proof environment (closed by `\qed`), 4
  top-level steps with nested sub-steps.
- **Standing assumptions as nodes.** The fixed normalized drawing D (AssumP1, set in running text at the
  start of Section 3) and n = 2s+1 (AssumP2, Section 4) are what Lemmas 3.1, 3.2 and 4.1 depend on; the
  graph has them as `assumption` nodes with edges, where the paper has a sentence.
- **Used before proved.** The normalization lemma A.1 is used in Sections 3 and 5 and proved in the
  appendix; the `\ref`s are backward edges (7 of the 194 edges point against paper order).

## Rules vs LLM

nodes P 0.64 / R 0.32, edges P 0.56 / R 0.17; result-level dependencies 5 of 13. The weakest of the three:
the main proof has no environment and the dependencies are stated in prose and in displays.

## What the extracting agent flagged in the paper

No algebraic step fails (the four-cycle expansion in Lemma 3.2, the corollary's arithmetic, the support
of H' on Q_s, the even-case identity n d_{n-1} = (n-2) d_n, the multiplicity argument in Lemma 2.1 were
checked). The crux is Lemma 3.1, the cycle pairing: a hand-built left/right shift of the second cycle
through crossing, bend and vertex disks, with an averaging that makes a shared spoke contribute zero;
it is described in prose only and is the least verifiable part. The method also appears to prove a
stronger claim than it states: the lower bound counts only pairs of independent edges with nonzero
signed intersection plus the rotation at each vertex, so in effect an algebraic/rotation-type crossing
count already reaches Zarankiewicz's bound. That is where a reviewer should test it against the known
gaps between odd, algebraic and ordinary crossing numbers.

## Three findings for the talk

1. **The graph finds where to look.** Eleven results, one chain of four, and the extractor's own note
   points at Lemma 3.1 as the only prose-only topological step and at the signed-count issue. A referee
   starts there.
2. **Standing assumptions become visible.** Two sentences of running text are what three lemmas depend
   on; as nodes they appear in every Rests-on view.
3. **Rules cannot read it.** Prose proof of the main theorem, dependencies in displays: 5 of 13 result
   dependencies. This is the extractor-side cost of AI writing style, not only the reader's.
