# silver_v6__edges_stack__2026-10

Learned edges, applied after parsing (opt-in), in three steps:

1. **Filter of the parser's own edges** (as in `silver_v6__edges_filter__2026-10`): drops edges
   the silver does not have, mostly "equation in its proof"; a dropped "equation in" edge is
   kept as the equation's `parent_id`, so the viewer still shows the equation in its container.
2. **Definition → user `uses` edges**, first stage: one logistic regression per candidate pair.
3. **Second stage** (new): each pair is rescored from the first-stage probabilities of related
   pairs: the definition's other users, the node's other sources, the node's neighbours, the
   proof/result partner, two-hop paths D → Y → X, and the gap to the node's best other source.

Found by an autoresearch run (alg3/doc/program.md, edge track, October 2026) and trained by
`alg3/edges.py` on the alg3 graphs of the 120 train papers of the v6 silver (parser at
44e49912); thresholds (`drop_below` 0.15, `threshold` 0.25) on out-of-fold predictions for
the train papers (5 folds by paper). The 40 val papers were used to compare versions.

    python3 src/LLMVersion/parse_batch.py ... --edge-model extractors/edges/silver_v6__edges_stack__2026-10

Edge metric (`src/LLMVersion/edge_metrics.py`, pooled, silver collapsed to Level 1), alg3
graphs, mean over three fold seeds (0, 1, 2):

| | train OOF F1 | val F1 |
|---|---|---|
| `silver_v6__defterm_edges__2026-10` (definition edges only) | 0.365 | 0.381 |
| `silver_v6__edges_filter__2026-10` (+ filter) | 0.420 | 0.430 |
| this model (+ second stage) | **0.435** | **0.433** |

Test not scored yet (one final run). `model.json` holds the logistic regressions as vocabulary
+ weights (no scikit-learn needed to apply); `recipe.json` the training record, both threshold
curves and the seed check.
