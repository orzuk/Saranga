# silver_v6__defterm_edges__2026-10

Learned **definition → user** `uses` edges, added on top of the parser's own edges. Trained by
`alg3/edges.py` on the v6 silver (`corpus/silver/opus-5.5__v6`, split `split_v6_6-2-2.csv`):
the definiendum model on the silver definitions of the 120 train papers, the pair model on the
alg3 (`tagger_v6`) rule graphs of the same papers; threshold 0.2 chosen on the 40 val papers.

Opt-in, off by default:

    python3 src/LLMVersion/parse_batch.py ... --edge-model extractors/edges/silver_v6__defterm_edges__2026-10
    python3 src/run_pipeline.py parse ... --edge-model extractors/edges/silver_v6__defterm_edges__2026-10
    python3 alg3/edges.py apply --graphs DIR --model extractors/edges/silver_v6__defterm_edges__2026-10 --out OUT

Edge metric (`src/LLMVersion/edge_metrics.py`, silver collapsed to Level 1, 40 test papers):

| graphs | P | R | F1 |
|---|---|---|---|
| alg3 (tagger_v6) | 0.383 | 0.199 | 0.262 |
| alg3 + these edges | 0.316 | 0.353 | **0.333** (+0.071, paired 95% CI +0.030 to +0.130) |
| units (rules_v6) + these edges | 0.322 | 0.341 | 0.331 (from 0.261) |

Definition → X edges found: 2.7% → 28%. `model.json` holds both logistic regressions as
vocabulary + weights (no scikit-learn needed to apply); `recipe.json` the training record.
