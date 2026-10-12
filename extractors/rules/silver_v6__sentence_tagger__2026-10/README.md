# silver_v6__sentence_tagger__2026-10

The third distillation algorithm (alg3, "sentence tagger"), trained on the v6
silver (`corpus/silver/opus-5.5__v6`) with no teacher call. Code and method:
`alg3/` (method write-up: `alg3/doc/alg3_method.pdf`).

**What it is.** For every prose sentence of a paper (the same sentences as the
units algorithm, `src/prose_units.py`), a weighted sum of ~47,000 deterministic
clues (words, word pairs, openings, markup, position, section, neighbours,
adjacent environments, cue phrases) gives a probability per node type; a second
pass adds the neighbours' first-pass probabilities; a sentence starts a node of
its most probable type when that probability clears the type's threshold, and a
small span model says how many sentences the node covers. Unlike the regex rule
sets, no single clue creates a node: every regex is evidence. `RULES.md` lists
the strongest clues for and against each type.

**Use** it like any extractor:

    python3 src/run_pipeline.py ... --rules-dir extractors/rules/silver_v6__sentence_tagger__2026-10
    RULES_DIR=$PWD/extractors/rules/silver_v6__sentence_tagger__2026-10 sbatch ... scripts/parse_multi_category_20.sh

Files: `distilled_rules.py` (the parser's entry point, same interface as the
other rule sets), `alg3_runtime.py` and `alg3_features.py` (pure Python, no
numpy or scikit-learn at parse time), `sentence_model.json` (weights,
thresholds, span model, training metadata).

## Training

Version v2b: multinomial logistic regression, square-root class weights,
C = 0.3, second pass on out-of-fold neighbour probabilities, thresholds tuned on
5-fold out-of-fold predictions for the overall F of base parser + tagger
(graded M1). Trained on the 120 train papers of `corpus/silver/split_v6_6-2-2.csv`;
chosen among seven versions on the out-of-fold score (0.694) and the 40
validation papers (0.726) before testing. `recipe.json` has the parameters and
paper lists. Retrain with

    python3 alg3/data.py --splits train,val --tex-dir corpus/silver/tex_staged
    python3 alg3/train.py --class-weight sqrt --stack --out <dir>

which reproduces this model within run-to-run noise (validation 0.725 vs 0.726;
bit-identical weights need the same BLAS thread count, e.g. OMP_NUM_THREADS=1).

## Held-out results (40 test papers, pooled, `scripts/compare_distillers.py`)

| | m1g P | m1g R | m1g F1 | m1 F1 | m3 F1 | prose m1g F1 | teacher cost |
|---|---|---|---|---|---|---|---|
| base parser | 0.944 | 0.482 | 0.638 | 0.630 | 0.753 | 0.137 | – |
| units (`silver_v6__sentence_rules_haiku__2026-10`) | 0.805 | 0.622 | 0.702 | 0.686 | 0.825 | 0.426 | $1.93 |
| merged (Yaron's, fixed, Haiku, 40 papers) | 0.740 | 0.601 | 0.663 | 0.636 | 0.831 | 0.376 | $2.87 |
| **this rule set** | 0.819 | 0.656 | **0.729** | **0.709** | **0.858** | **0.491** | **$0** |

Paired over the test papers (2,000 bootstrap resamples, 95% intervals), against
the units rule set: m1g +0.027 [+0.015, +0.043], m1 +0.023 [+0.012, +0.038],
m3 +0.033 [+0.021, +0.053]. All seven versions trained were ahead of the units
rule set on test (0.721–0.729); differences between versions are within
run-to-run noise.

Parse time per paper, base parser included (20 validation papers, one process):
median 0.54 s, mean 0.67 s (units rule set: 0.76 s / 0.96 s).
