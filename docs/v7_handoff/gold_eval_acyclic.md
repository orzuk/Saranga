# Gold and test scores of the T3 extractor with the acyclicity step (2026-11-03)

T3 = alg3 T-A (`extractors/rules/silver_v7__sentence_tagger__2026-10`) + all-pairs edges
(`extractors/edges/silver_v7__edges_allpairs__2026-10`), now with the cycle check of d8e9a8d2
(`alg3/edges_all.py`: learned edges added by decreasing confidence, one that would close a cycle skipped).
Before = the gold run of c2e93e23 (`gold_eval_v7.json`, `gold_eval_bp_v7.json`). On every gold item the new
`ta.json` equals the old one passed through `edges_all.make_acyclic`, so the differences are the acyclicity
step alone (no parser drift): 389 learned edges dropped on the 146 diagram papers, edges dropped on 35 of the
91 blueprints.

## How it was produced

    # gold: ta.json deleted and regenerated with the current code (rules.json, tagger.json kept)
    python3 scripts/gold_candidates/score_gold.py --sets author,blueprint --extractors rules,tagger,ta
    python3 docs/v7_handoff/gold_eval_v7.py     --out docs/v7_handoff/gold_eval_v7_acyclic.json
    python3 docs/v7_handoff/gold_eval_bp_v7.py  --out docs/v7_handoff/gold_eval_bp_v7_acyclic.json
    python3 scripts/gold_candidates/compare_theoremgraph.py --out docs/v7_handoff/compare_theoremgraph_acyclic.json
    # test (68): T-A parsed with alg3/experiments/v7_346/parse_all.py, edges by alg3/edges_all.py apply
    #   -> alg3/runs/v7_346/graphs/T-A+allpairs_acyclic (current code) and T-A+allpairs (same, cycle check
    #   disabled: edges_all._reaches patched to False); score.py has the arm alg3_TA+allpairs_acyclic
    python3 alg3/experiments/v7_346/score.py --split test     (and --split val)

Intervals: 95% bootstrap over items (1000, seed 0), as in the existing results; paired for the differences.

## Results (edge F1)

| Set | before | after (acyclic) | paired after - before |
|---|---|---|---|
| Author diagrams, 146 | 0.644 [0.605, 0.682] (P 0.769 R 0.554) | 0.638 [0.599, 0.678] (P 0.776 R 0.542) | -0.006 [-0.014, +0.001] |
| hierarchy-invariant, 146 | 0.551 | 0.555 | |
| Author diagrams, 28 test | 0.587 [0.491, 0.683] (P 0.736 R 0.488) | 0.584 [0.491, 0.677] (P 0.739 R 0.483) | -0.003 [-0.014, +0.004] |
| Blueprints, 91 (declared + cited) | 0.494 [0.447, 0.534] (P 0.434 R 0.573) | 0.493 [0.446, 0.533] (P 0.433 R 0.572) | -0.001 [-0.002, +0.000] |
| blueprints, declared only | 0.458 [0.412, 0.503] | 0.457 [0.412, 0.503] | |
| blueprints, hierarchy-invariant | 0.567 [0.520, 0.613] | 0.565 [0.520, 0.611] | |
| blueprints, R on definitions / results | 0.552 / 0.595 | 0.552 / 0.592 | |
| TheoremGraph's 77 diagram papers | 0.614 [0.554, 0.669] (R 0.510) | 0.610 [0.547, 0.668] (R 0.499) | vs TheoremGraph +0.189 [0.130, 0.249] |
| Test 68, Level-1 edges vs silver | 0.456 [0.431, 0.482] | 0.455 [0.430, 0.480] | -0.001 [-0.003, -0.000] |
| test 40 silver / 28 diagram papers | 0.424 / 0.490 | 0.422 / 0.489 | |
| Val 68, Level-1 edges vs silver | 0.4758 | 0.4761 | +0.000 [-0.000, +0.001] |

Test "before" here is the same parse as "after" with the check disabled (0.4561 -> 0.4548); the commit
message of d8e9a8d2 reports 0.4568 -> 0.4555 on an older parse (RESULTS_test_oct22.md: 0.457 [0.432, 0.482]).
Node scores are unchanged (the step only drops edges). LLM and sentence-rule rows are unchanged.
