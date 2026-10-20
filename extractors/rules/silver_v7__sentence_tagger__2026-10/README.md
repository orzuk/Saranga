# silver_v7__sentence_tagger__2026-10

The alg3 sentence tagger (same recipe as `silver_v6__sentence_tagger__2026-10`, version v2b),
retrained on the **v7** silver: the 210 train papers of `corpus/silver/split_v7_346.csv`
(120 silver, `corpus/silver/opus-5.5__v7`, + 90 gold-author, `corpus/silver/opus-5.5__v7_gold`,
whose sources have the dependency diagram stripped). This is the "T-A" model of the experiment in
`alg3/experiments/v7_346/` (README and full results there). No teacher call.

What it is and how it works: see the v6 README; only the training data differs. 79,337 clues
(v6: ~47,000). `RULES.md` lists the strongest clues for and against each type.

**Use** it like any extractor, optionally with its edge model:

    python3 src/run_pipeline.py ... --rules-dir extractors/rules/silver_v7__sentence_tagger__2026-10
    python3 src/LLMVersion/parse_batch.py ... --edge-model extractors/edges/silver_v7__edges_stack__2026-10

## Training

`alg3/train.py --class-weight sqrt --stack --objective e2e` (C = 0.3, thresholds tuned on the
end-to-end out-of-fold objective), on the cache of `alg3/experiments/v7_346/run.sh`.
Train OOF F (e2e) 0.746, validation (68 papers, simulated e2e) 0.752. `recipe.json` has the
parameters and paper lists.

## Held-out results (68 test papers of split_v7_346, against v7, m1g pooled)

| | 40 silver | 28 gold-author | all 68 |
|---|---|---|---|
| base parser | 0.617 | 0.695 | 0.654 |
| units (`silver_v6__sentence_rules_haiku__2026-10`) | 0.697 | 0.751 | 0.723 |
| `silver_v6__sentence_tagger__2026-10` | 0.721 | 0.781 | 0.749 |
| **this model** | **0.730** | **0.786** | **0.756** [0.732, 0.776] |

Paired over the 68 papers: vs the v6 tagger +0.007 [+0.001, +0.015]; vs units +0.033.
