# alg3 on the v7 pool of 346 papers (2026-10-20)

alg3 (sentence tagger v2b recipe + learned edge model) retrained on v7 labels, on three training sets
of `corpus/silver/split_v7_346.csv`, and scored on its test papers once.

| training set | papers (train / val) |
|---|---|
| T-S | 120 / 40 silver |
| T-G | 90 / 28 gold-author (diagram-stripped sources) |
| T-A | 210 / 68 (all) |

Recipe: `train.py --class-weight sqrt --stack --objective e2e`, then `edges.py train` on the model's own
parses. Test sets: E-S = 40 silver, E-G = 28 gold-author, E-A = all 68 (all against v7), and E-D = the 28
gold-author test papers against the AUTHORS' diagrams (graph_score preset `author`).

## Reproduce

    python3 alg3/experiments/v7_346/stage.py      # symlinks + split_{A,S,G}.csv -> alg3/cache/v7_346/
    alg3/experiments/v7_346/run.sh                # parses, 3 taggers, 3 edge models -> alg3/runs/v7_346/ (~2.5 h, CPU)
    python3 scripts/compare_distillers.py run --config alg3/experiments/v7_346/v7_346_alg3.json --stages eval,report
    python3 alg3/experiments/v7_346/score.py --split test      # RESULTS_test.md (and --split val)
    python3 alg3/experiments/v7_346/analyze_v7.py T-A+edges S  # val error breakdown (S | G); --diagrams <graphs>

## Results (TEST, pooled, 95% paper-bootstrap CI) — full tables in RESULTS_test.md

| arm | nodes m1g E-A | edges L1 F1 E-A | E-D edge F1 |
|---|---|---|---|
| base parser | 0.654 | 0.285 | 0.456 |
| units (v6) + edges_stack | 0.723 | 0.430 | 0.468 |
| alg3 v6 release + edges_stack | 0.749 | 0.441 | 0.466 |
| alg3 T-S + edges | 0.749 | 0.444 | 0.462 |
| alg3 T-G + edges | 0.752 | 0.438 | 0.469 |
| **alg3 T-A + edges** | **0.756** [0.732, 0.776] | **0.443** | **0.470** |
| v7 LLM | | | 0.787 |

- Nodes: T-A − v6 release +0.007 [+0.001, +0.015]; T-A − T-S +0.007 [+0.001, +0.014]; T-A − units +0.033
  on every subset. The released v6 tagger scores 0.721 on E-S, as in `scripts/compare_configs/silver_v7_vs_rules.json`.
- Edges: retraining on v7 adds nothing (T-A − v6 release +0.002 [−0.003, +0.008]).
- E-D: every rule-based arm is ≈ 0.46, the base parser included.

## Error analysis (VAL only; full reports in analysis/, made with analyze_v7.py)

- T-A's node gain is recall (silver val R 0.630 → 0.664, gold val 0.716 → 0.734).
- Weak types: claim F1 0.26 (silver) / 0.41 (gold), definition 0.67, assumption 0.45 / 0.63; environment
  types (lemma, proposition, corollary) ≈ 1.0. Misses outnumber spurious nodes ~2.5×; definitions and claims
  are ~70% of the misses.
- Edges vs v7: P 0.61, R 0.36. ~4.5k (silver val) / 5.9k (gold val) silver edges are missed with BOTH
  endpoints found, mostly definition → X / definition → proof; 2–3k more lack an endpoint.
- Author diagrams (28 gold val papers): 98% of boxes matched; 267 of 437 arrows missed between matched
  results (3 reversed, 8 unmatched endpoints); P 0.79, R 0.36 (LLM R 0.73). The gap to the LLM is
  result → result dependencies, which neither the tagger nor the edge model produces.

Not released: the T-* models stay in alg3/runs/v7_346/ (gitignored); the website keeps the v6 release.

## After Or's parser fix (3ce77a9a, proof's \ref to its own result; parser at 2ef5e47f)

All arms re-parsed (nodes identical in every paper; edges differ in ~10% of papers) and the T-A edge
model retrained (`VARIANTS=A run.sh`; T-S/T-G edges not re-run). Full tables: `RESULTS_test_parserfix.md`.

| arm | edges L1 F1 E-A | E-D edge F1 (before fix) |
|---|---|---|
| base parser | 0.286 | 0.534 (0.456) |
| units + edges_stack | 0.431 | 0.547 (0.468) |
| alg3 v6 release + edges_stack | 0.442 | 0.548 (0.466) |
| **alg3 T-A + edges (retrained)** | 0.440 | **0.553** (0.470) |

The fix lifts every arm on the author diagrams by ~0.08; retraining the edge model adds nothing
(T-A − v6 release −0.002 [−0.008, +0.006] on E-A). Released as
`extractors/rules/silver_v7__sentence_tagger__2026-10` + `extractors/edges/silver_v7__edges_stack__2026-10`.
