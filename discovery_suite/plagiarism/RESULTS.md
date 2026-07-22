# T-PLAG — Plagiarism / Undisclosed Reuse: Results (100K corpus)

End-to-end pipeline over the full 100K parsed corpus. Directional: "B reuses A",
A the older paper.

## Stages
1. **Sweep** — corpus-scale, disk-based MinHash/LSH over every *substantive* node
   in every paper (theorem/lemma/definition/proof/…; LaTeX + stopwords stripped,
   math normalized; non-prose boilerplate — TikZ, all-constant matrices/tables —
   and degenerate nodes dropped at fingerprint time). Finds near-identical node
   pairs across different papers → aggregated into candidate paper→paper reuse
   pairs, oriented older-as-source. Peak RAM is bounded regardless of corpus size
   (external four-pass design), so it runs on the full 100K in ~80 min and is
   ready for the 3M whole-arXiv corpus.
2. **Triage + promiscuity (IDF) filter** — shortlist to strong reuse (high max
   node-Jaccard, ≥2 shared nodes), then drop generic boilerplate nodes that match
   many papers (standard phrasings like "the proof is analogous to that of
   Theorem X").
3. **Same-author / self-reuse gate** — the official CC0 Cornell/arXiv metadata
   dump (id → authors, surname+initial matching) separates self-reuse (same
   author) from genuine cross-author reuse. The analogue of the open-problem
   citation gate.
4. **LLM judge (P4)** — pulls both statements' full text and classifies:
   VERBATIM / PARAPHRASE / CONCEPTUAL_REUSE / LEGITIMATE_CITATION / INDEPENDENT.
   Built; not yet run at scale (next step now that the shortlist is clean).

## Funnel (all 100K)
| stage | pairs |
|---|---|
| candidate cross-paper pairs (sweep) | 384,115 |
| strong (score_max ≥ 0.8, ≥2 shared nodes) | 15,003 |
| − same-author self-reuse (8,887; 59%) | 6,116 cross-author |
| − promiscuous / generic-phrase nodes | **737** |

Author coverage: 100% — every paper id in the corpus resolved in the metadata
dump (corpus spans Jan-2010 … Jan-2020; dump covers Apr-2007 … May-2025).

## Notable candidates (pre-judge)
- **`1109.0956 → 1304.6179` (math.NT)** — 223 near-identical statements across two
  *different-author* papers two years apart; whole-manuscript-level overlap. The
  first case to verify.
- `1109.0303 → 1106.1973` (math.CO) — a specific cubic-graph *m*-cut theorem.
- `1609.02250 → 1609.03006` (math.AT) — "the algebraic transfer φ_k is an
  epimorphism" — two same-month papers.
- `1706.03451 (cs.CC) → 1711.01943 (math.LO)` — a genuine cross-field pair.

## Status
No LLM-confirmed plagiarism yet — the judge is the next run — but the machinery
works end-to-end and produces real, checkable matches, and the self-reuse gate
validates by correctly stripping the majority (59%) as same-author.

## Next
- Run the P4 judge over the 737-pair shortlist; verify the NT standout.
- Optional paper-level promiscuity filter (one paper, `1110.2661`, with dozens of
  templated proofs still generates residual noise).
- Embedding-based (BERT-style) semantic stage + ANN index to catch paraphrased /
  differently-notated reuse the lexical match misses (same runtime challenge as
  the open-problem task).
- 3M whole-arXiv run.

## Artifacts
`discovery_suite/plagiarism/` — `sweep_plag.py` (sweep), `triage_plag.py` (triage
+ gates), `build_author_index.py` (author index), `p4_judge.py` (LLM judge),
`sweep_cluster.sh` (SLURM). Under `runs/`: `plag_sweep_100k.csv` (+ `_nodes.csv`
evidence), `plag_triage_top.csv` (the 737-pair shortlist), `author_index_100k.json`.
