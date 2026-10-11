# silver_v6__sentence_rules_haiku__2026-10

**134 sentence rules** distilled from the v6 silver corpus (`opus-5.5__v6`) by
the sentence-rule algorithm (`scripts/distill_units.py`). Teacher:
`claude-haiku-5-5`; 1,644 LLM calls; $1.93; about 1.4 h. This is run 1 of the
three 120-paper runs (`g_units_haiku_f1` in `scripts/compare_configs/v6.json`).
It replaces the v5.1 rule sets (`silver_v5.1__*`) as the default.

## What a rule is

A rule is one regular expression over a single prose sentence, plus a node type
and a span (`unit_rules.json`: `uid`, `name`, `type`, `regex`, `flags`, `span`,
`precision`). The base parser still finds the structures stated in LaTeX
environments. The rules add the structures stated in running prose.
`src/LLMVersion/unit_rules.py` applies them, both during training and in the
parser. `distilled_rules.py` is only an importer that loads them into the parser.

| type | rules | type | rules |
|---|---|---|---|
| definition | 53 | assumption | 4 |
| claim | 29 | open_problem | 3 |
| theorem | 17 | example | 3 |
| proof | 14 | conjecture | 2 |
| remark | 7 | lemma, algorithm | 1 each |

## How it was trained

- **Split:** `corpus/silver/split_v6_6-2-2.csv`, 120/40/40 papers (6/2/2 per category).
  - The teacher saw only the 120 training papers.
  - The 40 validation papers were used to accept rules and to stop the run.
  - The 40 test papers entered no stage.
- **Metric:** training used graded M1 (`m1g`, one-to-one matching with type-compatibility credit).
- **Acceptance:** a rule was accepted if it raised overall training F1 jointly with the rules already accepted, and did not lower validation F1.
- **Full record:** the parameters, paper lists, per-stage token costs and the file sha256 are in `recipe.json`.

## Held-out results (40 test papers, graded M1)

These numbers were recomputed after the `rule_guard` lookahead fix.

| | P | R | F1 [95% CI] | Δ vs base [paired CI] | M3 F1 | prose F1 |
|---|---|---|---|---|---|---|
| base parser | 0.944 | 0.482 | 0.638 [0.544, 0.697] | | 0.753 | 0.137 |
| **this rule set** | 0.805 | 0.622 | **0.702** [0.636, 0.738] | **+0.064** [+0.038, +0.102] | 0.825 | 0.426 |
| v5.1 released rules | 0.721 | 0.578 | 0.642 [0.574, 0.683] | +0.004 [−0.017, +0.037] | 0.801 | 0.309 |

- **Repeat runs:** two more runs on 120 papers score 0.701 and 0.703.
- **Against the v5.1 rules:** +0.060 graded M1 and +0.024 M3 [+0.006, +0.051].
- **Parse cost:** about 0.5 s per paper (base parser alone: 0.12 s).
- **Full comparison:** `runs/compare/v6_6-2-2/results/`.

## Running it

```bash
python3 src/run_pipeline.py --operations parse --extraction-mode rules \
    --rules-dir extractors/rules/silver_v6__sentence_rules_haiku__2026-10 \
    --tex-dir <abs path to staged .tex> --out-dir <out>
```

On the cluster, set `RULES_DIR=extractors/rules/silver_v6__sentence_rules_haiku__2026-10`
for `scripts/parse_multi_category_20.sh`.

- **Check the log first:** before trusting the output, confirm it reports "134 sentence rule(s)".
- **Dependency:** the rules need the `regex` package. Each sentence is matched with a 0.5 s timeout, and a rule that times out on a sentence is skipped for that sentence only.
