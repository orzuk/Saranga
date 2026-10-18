# silver_v6__edges_filter__2026-10

Learned edges, applied after parsing (opt-in), in two steps:

1. **Filter of the parser's own edges.** A logistic regression over clues of each parser edge
   (its kind, whether the equation is labelled, referenced elsewhere or defining, its place in
   its container, explicit `\ref`s, distance) drops the edges the silver does not have, mostly
   "equation in its proof" edges. A dropped "equation in" edge is kept as the equation's
   `parent_id`, so the viewer still shows the equation in its container's panel.
2. **Definition → user `uses` edges**, as in `silver_v6__defterm_edges__2026-10`, now with
   defining displays (`X := ...`) as sources, unaligned pairs as negatives in training, and
   clues on how a definition ranks among the sources a node uses.

Trained by `alg3/edges.py` on the v6 silver (`corpus/silver/opus-5.5__v6`, split
`split_v6_6-2-2.csv`): both models on the alg3 graphs of the 120 train papers (parser at
d290d28e); thresholds (`drop_below` 0.15, `threshold` 0.25) chosen on out-of-fold predictions
for the train papers (5 folds by paper). The 40 val papers were used to compare versions.

    python3 src/LLMVersion/parse_batch.py ... --edge-model extractors/edges/silver_v6__edges_filter__2026-10
    python3 alg3/edges.py apply --graphs DIR --model extractors/edges/silver_v6__edges_filter__2026-10 --out OUT

Edge metric (`src/LLMVersion/edge_metrics.py`, pooled, silver collapsed to Level 1), alg3 graphs:

| | train OOF F1 | val P | val R | val F1 |
|---|---|---|---|---|
| parser edges only | 0.246 | 0.469 | 0.209 | 0.290 |
| + `silver_v6__defterm_edges__2026-10` (previous model) | 0.365 | 0.409 | 0.358 | 0.381 |
| + this model | **0.421** | 0.632 | 0.326 | **0.431** |

Test not scored yet (one final run with `compare_distillers.py`). Recall per edge kind is
unchanged by the filter (e.g. proves 0.735, result -> proof 0.59 on val); the gain is precision.
`model.json` holds the three logistic regressions as vocabulary + weights (no scikit-learn
needed to apply); `recipe.json` the training record and both threshold curves.
