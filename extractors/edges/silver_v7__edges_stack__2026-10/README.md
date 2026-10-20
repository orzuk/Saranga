# silver_v7__edges_stack__2026-10

The learned edge model of `silver_v6__edges_stack__2026-10` (parser-edge filter, definition →
user `uses` edges, second stage over related pairs; see its README), retrained on the **v7**
silver: graphs of the 210 train + 68 val papers of `corpus/silver/split_v7_346.csv` parsed with
`extractors/rules/silver_v7__sentence_tagger__2026-10` by the parser at 2ef5e47f (with the
proof-reference cycle fix, 3ce77a9a). Thresholds on out-of-fold train predictions:
`drop_below` 0.15, `threshold` 0.25. Train OOF F1 0.482, val F1 0.459. `recipe.json` has the curves.

    python3 src/LLMVersion/parse_batch.py ... --edge-model extractors/edges/silver_v7__edges_stack__2026-10

## Held-out results (68 test papers, parser 2ef5e47f)

| tagger + edge model | edge F1 vs v7 (Level 1), 40 silver / 28 gold / all | author diagrams (28 gold) |
|---|---|---|
| base parser (no edge model) | 0.257 / 0.315 / 0.286 | 0.534 |
| v6 tagger + `silver_v6__edges_stack__2026-10` | 0.410 / 0.475 / 0.442 | 0.548 |
| **v7 tagger + this model** | **0.410 / 0.472 / 0.440** | **0.553** |

On par with the v6 edge model (−0.002 [−0.008, +0.006] on all 68): retraining the edges on v7
gains nothing. The parser fix lifts every arm on the author diagrams by ~0.08 (e.g. 0.466 → 0.548
for the v6 pair). Full tables: `alg3/experiments/v7_346/RESULTS_test_parserfix.md`.
