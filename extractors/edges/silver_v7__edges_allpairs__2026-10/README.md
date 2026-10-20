# silver_v7__edges_allpairs__2026-10

Learned edges of **every kind** (`alg3/edges_all.py`), replacing the definition-only edge models
(`silver_v*__edges_stack__2026-10`). One logistic regression scores every candidate pair (s, t); the
graph's edges become exactly the candidates scoring ≥ 0.22 (the parser's own edges included: those
below are dropped; a dropped "equation in its container" edge is kept as the equation's `parent_id`).

Candidates mirror how the v7 silver makes its edges (`corpus/silver/opus-5.5__v7/prompt_opus_v7.md`,
"Edge coverage"; every silver edge records its `basis`):

- **term** (61% of silver edges): a definition and a node that uses its definiendum or the symbol it
  introduces. The definiendum is scored by its own model over a wider candidate set (relation
  left sides, arguments stripped, unmarked subjects "A *Willmore surface* is …", "the notion of X",
  custom term macros), with document clues (used later in the paper? before the definition?);
  trained on our parsed definitions aligned to silver definitions (top-1 0.66 on val, was 0.62).
  Pair clues: how and how strongly it is used, later or earlier (true document order, from the
  .tex), the use's rank among the definition's users, target type, the definition's origin
  (environment / tagger prose / parser inline pattern).
- **ref** (26%): `\label` in s (innermost owner) and `\ref`/`\eqref`/`\cref{a,b}` in t, both directions.
- **parser** edges, **near** nodes (3 before, 1 after), proof ↔ preceding result, rare shared tokens.

Trained by `alg3/edges_all.py train` on the parses of the 210 train papers of
`corpus/silver/split_v7_346.csv` with `extractors/rules/silver_v7__sentence_tagger__2026-10`
(parser 2ef5e47f), 5-fold out-of-fold threshold; three fold seeds agree (OOF F1 0.504–0.505,
val 0.472–0.473; a second stacking stage and gradient boosting added nothing and are not used).

**Needs the .tex at parse time** for document order: `alg3/edges.py add_edges(graph, model, tex=...)`
(`parse_batch.py --edge-model`, `portal/yours.py` and `alg3/analyze.py` pass it). Without it, the
graph's list order is used, which is not document order (tagger nodes come first).

    python3 src/LLMVersion/parse_batch.py ... --edge-model extractors/edges/silver_v7__edges_allpairs__2026-10

## Results

| | train OOF | val (68) | test silver (40) / gold (28) / all (68) | author diagrams, test (28) |
|---|---|---|---|---|
| v6 tagger + `silver_v6__edges_stack__2026-10` | – | 0.444 | 0.410 / 0.475 / 0.442 | 0.548 |
| v7 tagger + `silver_v7__edges_stack__2026-10` | 0.482 | 0.459 | 0.410 / 0.472 / 0.440 | 0.553 |
| **v7 tagger + this model** | **0.504** | **0.473** | **0.425 / 0.489 / 0.457** | **0.573** |

Level-1 edge F1 against v7 (`src/LLMVersion/edge_metrics.py`), pooled. Paired over the 68 test papers:
+0.017 [+0.007, +0.024] vs the v7 edges_stack, +0.015 [+0.006, +0.023] vs the v6 pair; author
diagrams +0.020. Full tables: `alg3/experiments/v7_346/RESULTS_test_allpairs.md`.

What limits it (val error analysis): the v6 and v7 silver agree on edges at F1 0.74, so the labels
are consistent; the remaining loss is mostly node-side — a quarter of the false term edges start at
a "definition" that is not a silver definition (tagger), and 18% of the silver `\ref` edges point
into prose proofs/claims the parse does not produce as nodes.
