# opus-5.5__v7 — the current silver corpus

200 papers, ten from each of the 20 categories, the same 200 papers as `opus-5.5__v6`. One Claude Opus 5.5
agent per paper, prompt `prompt_opus_v7.md` (sha256 `86dcfbecdc4d78a5`, tag `v7-frozen`, code `4f9e8ef` plus
check-only fixes made during the run). Extracted 2026-10-19. This replaces v6 as the silver for training
and analysis; `opus-5.5__v6` stays, unchanged, because the paper's distillation results are scored on it.

**Split:** use `corpus/silver/split_v6_6-2-2.csv` unchanged: the same 120 train / 40 val / 40 test papers as v6
(column `split`; every v7 paper is in it).

**Statistics** (`docs/v7_handoff/silver_stats.py`, results in `docs/v7_handoff/silver_stats_v7.json`):
39,402 nodes (26,415 Level-1, 12,987 steps), 60,697 edges; median paper 164 nodes, 237 edges. Agent time
median 8.1 min per paper, about $2.3 per paper at list prices.

**Known issues** (fix in code, then re-run `finalize()` on the paper):
- 1309.7607v2: 3 finishing-step errors under the final code (its case labels do not start steps); it passed
  when written.
- The prompt asks for `rigor: semi_formal` on proof sketches, which the rigor rule forbids on proofs;
  agents differ (some kept it, with a warning; some dropped it).

**Retraining alg3 on v7** (`alg3/` defaults to v6, so pass the v7 directory):

    python3 alg3/data.py --splits train,val --tex-dir corpus/silver/tex_staged --silver corpus/silver/opus-5.5__v7
    python3 alg3/train.py --class-weight sqrt --stack --out <dir>

`alg3/train.py --objective e2e` and `alg3/analyze.py` still read `SILVER` (v6) as a module constant. A
retrain with the default objective on v7 (run here, 2026-10-19) scored M1g F1 0.720 on the 40 test papers
against v7, the same as the released v6-trained tagger (0.721); see `scripts/compare_configs/silver_v7_vs_rules.json`.
