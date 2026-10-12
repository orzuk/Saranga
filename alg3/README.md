# alg3: the sentence tagger (third distillation algorithm)

A distillation algorithm next to the merged algorithm (`--alg merged`) and the
units algorithm (`--alg units`) of `scripts/silver_distillation_merged.py`. The
teacher's only contribution is the supervision (the v6 silver); how the
evidence in a sentence is weighed is learned from it by a regularised linear
model over deterministic clues. Training makes no API call. Method, notation
and results: `doc/alg3_method.pdf` (source `doc/alg3_method.tex`).

The released extractor is `extractors/rules/silver_v6__sentence_tagger__2026-10`
(test m1g F1 0.729 against 0.702 for the units rule set; see its README).

## Files

| file | what it does |
|---|---|
| `data.py` | builds the training data with the units algorithm's own loader (`scripts/distill_units.py`): prose sentences, silver prose nodes, the base parser's counts; train and val papers only (test is refused) |
| `features.py` | the clues of a sentence (shared by training and the parser) |
| `train.py` | anchor model, optional second pass (`--stack`), span model, thresholds tuned on out-of-fold predictions; writes an extractor directory |
| `runtime.py` | the parse-time code, copied into every extractor directory (pure Python) |
| `invent.py` | optional: Claude Haiku proposes extra regex clues from the out-of-fold mistakes on the training papers (`--clues` in train.py); round 1 (`clues_r1.json`, $0.01) gave no gain and is not used by the release |
| `analyze.py` | per-type errors of an extractor on the validation papers |
| `explain.py` | `RULES.md`: the strongest clues for and against each type |
| `v6_alg3.json` | `scripts/compare_distillers.py` config: base vs units vs this extractor |

## Run

    # 1. data (base-parses the 160 train+val papers, about a minute with 6 workers)
    python3 alg3/data.py --splits train,val --tex-dir corpus/silver/tex_staged
    # 2. train (about 5-10 minutes; the released v2b settings)
    python3 alg3/train.py --class-weight sqrt --stack --out alg3/runs/<name>
    # 3. compare on the test papers, same harness and metrics as the other algorithms
    python3 scripts/compare_distillers.py run --config alg3/v6_alg3.json --no-trajectory

The common driver runs it too, next to the other two algorithms:

    python3 scripts/silver_distillation_merged.py --alg tagger \
        --pilot-papers train --splits corpus/silver/split_v6_6-2-2.csv \
        --tex-dir corpus/silver/tex_staged --eval-dir <out> \
        [--tagger-args "--class-weight sqrt --stack"]

and so does `scripts/compare_distillers.py`, with an arm like
`{"alg": "tagger", "args": {"tagger-args": "--class-weight sqrt --stack"}}`
(`train_per_category` works as for the other algorithms; no `model` needed).
To compare an already trained model, add an arm
`{"alg": "fixed", "rules_dir": "alg3/runs/<name>"}` to the config. Choose between versions on the out-of-fold score and the
validation papers (both printed by train.py), not on the test papers.

`cache/` and `runs/` are local (git-ignored).
