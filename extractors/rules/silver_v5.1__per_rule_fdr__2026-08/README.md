# silver_v5.1__per_rule_fdr__2026-08

The full distilled rule set from the v5.1 run: **388 patterns** across 5 group
files, distilled from 40 papers drawn worst-first out of a 60-paper training
split of the 200-paper v5.1 silver corpus. Teacher: `claude-sonnet-4-6`,
457 LLM calls, $95.15.

This is the **pre-subset** extractor — every rule the loop kept, before subset
selection removed any. `silver_v5.1__subset_selection__2026-08` is derived from
exactly these files.

## Which state this is

The run's **final** rule state (`merged_eval_v51_train60_v2/groups/`), i.e.
after the last aggregate call. That is 4 patterns further along than the last
per-paper snapshot, `snapshots/step_40_1302.1114v2`, which has 384. If you are
diffing against a snapshot, this is the one that matches nothing exactly — use
the sha256 in `recipe.json`.

## Caveats worth a sentence

- **40 distilled, not 60.** The training split is 60 papers and `train.papers`
  lists all 60, but the loop ran 40 iterations. The remaining 20 were never
  distilled from; subset selection used all 60. Held-out numbers are unaffected
  — the 140 held-out papers entered no stage — but "trained on 60" overstates
  what the loop saw.
- **Slow rules are still in.** Subset selection quarantined 43 units on a
  per-rule wall-clock budget; none of that has happened here. Parsing with this
  extractor is substantially slower than with the subset, and a pathological
  regex on an unseen paper can stall a parse. `rule_guard` will neutralise such
  a rule **by rewriting this file**, so keep the archived copy.
- **Pruning was m1.** `alpha=0.5`, `match_mode=m1` — the FDR gate ran against
  the strict metric, while subset selection later optimised m3.

## Running it

```bash
python3 src/run_pipeline.py --operations parse --extraction-mode rules \
    --rules-dir extractors/rules/silver_v5.1__per_rule_fdr__2026-08 \
    --tex-dir <abs path to staged .tex> \
    --out-dir corpus/silver/rules__silver_v5.1__per_rule_fdr__2026-08
```

Check the loaded-rules line before trusting output; it should report 388.
