# Big Data Project 52017 (2025-26) — Held-out Test Set Manifest

INSTRUCTOR ONLY. None of these gold standards may appear in the public repo
`github.com/orzuk/BigDataProject_52017`. Only the held-out chapter `.tex`
(ch11, ch12) and the train materials are public.

Last finalized: 2026-06-02.

## Final leaderboard test set (7 documents)

The combined-F1 leaderboard (project Part 2) is scored on these 7 held-out documents.

### Book chapters (2)

| Doc | Gold file | Nodes | Edges |
|---|---|---|---|
| ch11 (Wavelets) | `gold_standards/gold_standard_chapter11.json` | 26 | 33 |
| ch12 (Appendix) | `gold_standards/gold_standard_chapter12.json` | 69 | 67 |

The chapter `.tex` are public (`chapters/tex/chapter11.tex`, `chapter12.tex`); the
gold JSONs above are private.

### arXiv papers (5)

`instructor_only/papers_test_gold/`, `.tex` in `gold_standards/papers/test/`.

| arXiv id | Gold file | Nodes | Edges |
|---|---|---|---|
| 1405.2464v2 | `1405.2464v2_gold.json` | 25 | 49 |
| 1512.09272v2 | `1512.09272v2_gold.json` | 21 | 32 |
| 2309.05826v1 | `2309.05826v1_gold.json` | 13 | 19 |
| 2505.12804v1 | `2505.12804v1_gold.json` | 25 | 33 |
| 2603.09769v1 | `2603.09769v1_gold.json` | 29 | 41 |

These are the 5 arXiv papers from the instructor T1 set NOT used for training.
The 5 training papers (public) are 1204.0109v1, 1210.4634, 2208.03112v1,
2312.16785, 2401.00367.

## Schema (all golds must conform)

Six node types only: definition, theorem, lemma, corollary, proof, algorithm.
This matches the project brief and the student train golds. Evaluation
(`evaluate_extraction.py`) counts every gold node, so any extra node type in a
gold (e.g. equation, proof_step, claim) becomes an unfair false-negative against
students. Keep test golds at this "standard" granularity.

## Finalization edits applied 2026-06-02

1. **ch11/ch12 normalized to the 6-type schema.** The Opus extractions were the
   "full" granularity (ch11: 62 nodes incl. 12 equation + 24 proof_step; ch12:
   139 nodes incl. 35 equation + 35 proof_step). Equation and proof_step nodes
   were removed and edges transitively bridged through them, giving ch11=26 and
   ch12=69 nodes (matching the project's documented standard-extraction counts).
   The full versions are preserved as `gold_standards/chapter11_extracted_full.json`
   and `chapter12_extracted_full.json`. The evaluator reads the normalized
   `gold_standard_chapter{11,12}.json` (preferred) / `chapter{11,12}_extracted.json`
   (fallback) — both now hold the normalized version.
   Impact: a solution extractor's ch11 output went from combined-F1 0.102
   (full gold) to 0.203 (normalized gold) — the unfair penalty is removed.

2. **2309.05826v1_gold.json fixed.** Was invalid: a 2-cycle
   (`def_merging_conflict` <-> `claim_inner_snn_better`) and two off-schema types.
   Mapped `equation`->`definition` (FixMatch objective/loss/filter are
   definitional) and `claim`->`theorem` (asserted results with
   assumptions/conclusions); removed the backwards edge
   `def_merging_conflict -> claim_inner_snn_better` (the claim justifies the
   heuristic, not the reverse). Original kept as `2309.05826v1_gold_orig.json`.

   NOTE for instructor review: 2309.05826v1 (KD-FixMatch, applied ML) is the
   least "formal" test paper — mostly definitions + one algorithm + empirical
   claims, few theorems/lemmas/proofs. Still a valid test of generalization to a
   different document style, but consider swapping for a more theorem-dense paper
   if a re-annotated alternate is available.

## How the leaderboard reads these

`instructor_only/run_evaluation.py` -> `find_gold()` prefers
`gold_standard_chapter{N}.json`, else `chapter{N}_extracted.json`. Paper golds
via `papers_test_gold/`. See `run_leaderboard.py` for the batch run.
