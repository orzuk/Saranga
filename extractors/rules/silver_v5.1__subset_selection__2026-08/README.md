# silver_v5.1__subset_selection__2026-08

**146 of 300 selectable units**, chosen by greedy forward search with a backward
pass over the rules in `silver_v5.1__per_rule_fdr__2026-08`, with k fixed by
5-fold cross-validation on the 60-paper training split. Objective: pooled M3 F1.

This is the extractor the Appendix F held-out result refers to, and the one that
produced the 200 parsed graphs.

## Held-out result

140 papers that entered no stage of distillation or selection, one real parse
each, pooled M3 (containment, threshold 0.7, cover 0.7):

| | precision | recall | F1 |
|---|---|---|---|
| base parser | — | — | 0.6865 |
| all rules (pre-subset) | — | — | 0.7538 |
| **this extractor** | 0.8228 | 0.6997 | **0.7563** |

Dropping half the pool costs nothing out of sample. The claim is *not* that
fewer rules are better.

## Reading `n_patterns` — it is not the rule count

`recipe.json` reports **393 compiled patterns**, which is larger than the 388 of
the parent. That is not a bigger rule set:

- 5 of them are the sentinel definition `_SUBSET_NEVER = re.compile(r'(?!x)x')`,
  one per group file;
- **85 rules are rebound to that sentinel** and can never match.

Non-selected rules were made inert rather than deleted because some units are
**guards** — patterns whose job is to exclude. Deleting every non-selected
pattern broke the parser: theorem-like output went up and proof output dropped
to zero. A rule is only disabled here if it was non-selected *and* had actually
fired during precompute, or was quarantined.

So: 146 selected units, 85 producing rules switched off, 43 of the 300 units
never eligible because they blew the per-rule time budget.

## Caveats worth a sentence

- **Selection scored subsets by composition, not by parsing.** Candidate subsets
  were scored by unioning per-rule precomputed extractions, which cannot model
  rule interaction and runs roughly 0.3 points optimistic against a real parse.
  The held-out table above is real parses; the search curve behind it is not.
- **The margin over the full set is 0.0025.** Treat "the subset beats the full
  pool" as "does not lose to it".
- `selection.json` is copied in beside the rules: it carries `selected_units`,
  `dropped_units`, `quarantined_units`, and per-unit `papers_fired` / timings.

## Running it

```bash
python3 src/run_pipeline.py --operations parse --extraction-mode rules \
    --rules-dir extractors/rules/silver_v5.1__subset_selection__2026-08 \
    --tex-dir <abs path to staged .tex> \
    --out-dir corpus/silver/rules__silver_v5.1__subset_selection__2026-08
```

The 200 v5.1 papers have already been parsed with this extractor — see
`corpus/silver/rules__silver_v5.1__subset_selection__2026-08/`.
