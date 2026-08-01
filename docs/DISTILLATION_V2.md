# Distillation v2 — design for review

**Status:** registry implemented + tested (`scripts/distill_registry.py`).
Incremental aggregate and the driver loop are specified below but **not yet
wired** — review this first.

---

## Why change anything

Three defects measured on the v1 run (`merged_eval_silver_001_011_v3`, 17 papers).
All three come from one root cause: **the generated `.py` file is treated as the
source of truth for what rules exist.**

| # | Defect | Evidence |
|---|---|---|
| 1 | **Rule identity is not stable.** `aggregate` regenerates the whole file from scratch each paper. | 0 of 10 definition rules survived by *name* step_05→step_06. Bodies also rewritten: 0 exact matches step_05→step_17, but `EMPH_SEMI_PATTERN` ≈ `R12_EMPH_SEMI` at >0.95 similarity. |
| 2 | **Pruning is transient.** `prune_rules` comments out code; the next `aggregate` regenerates from a suggestion list that has no record of the prune. | Cumulative pruned count *falls* across steps: 13 → 12 → 9 → 4 → 3. Only possible if prunes are undone. |
| 3 | **Cost is quadratic; context runs out.** The whole `cumulative_analyze.csv` is re-sent every paper. | `aggregate_input_tokens` 19K → 184K over 17 papers (+~11K/paper). A 200K model dies around paper 18–19 — probably why v1 stopped at 17. |

Consequences worth naming: a rule's lifetime is untrackable; "new rules per
paper" (the paper's sub-linearity metric) measures file regeneration rather than
accumulation; and the pipeline cannot reach 100 papers at all.

---

## Core idea

> **The registry is the source of truth. The `.py` file is a projection of the
> active subset.**

- Every pattern gets a monotonic `uid`, never reused.
- Rules are **never deleted** — only `status` flips `active` ⇄ `retired`.
- Per-rule `(tp, fp)` cached **per paper**, so FDR at any α is a lookup.
- Gating is a flag, so it is **reversible** and an α-sweep needs no file snapshots.
- **Recycling:** a retired rule that would catch a new paper's miss is revived
  for free, instead of being re-invented by the LLM under a new name.

---

## Algorithm

```
STATE
  REG      : uid -> {name, group, pattern_src, born, status, stats{paper:(tp,fp)}, history}
  RULES.py : projection of REG.active  (each pattern preceded by "# @uid:N")

MAIN(train_papers, alpha)
  REG = load_or_create()
  for P in train_papers:                       # order matters only for cost curves
      ┌─ 1. EXTRACT ─────────────────────────────────────────────────────────
      │  extracted = parse(P, base_rules + REG.active)
      │  DK        = gold(P) \ extracted        # dark knowledge = the misses
      │
      ├─ 2. RECYCLE  (free, no LLM)  ◀── NEW ───────────────────────────────
      │  for R in REG.retired:
      │      if R.regex matches >=1 item in DK:
      │          REG.revive(R, reason="recycled@P")
      │  DK = DK \ items now covered by revived rules
      │
      ├─ 3. GENERATE  (LLM, only if DK still non-empty) ────────────────────
      │  if DK:
      │      suggestions = analyze(DK, tex(P))              # LLM call 1
      │      new_src     = aggregate_incremental(           # LLM call 2  ◀── CHANGED
      │                        current_rules = RULES.py,    #   send CURRENT RULES
      │                        new_only      = suggestions) #   + NEW suggestions only
      │      for (name, pattern) in patterns(new_src):
      │          uid = uid_marker(name) or REG.match_by_body(pattern)
      │          REG.mint_or_update(uid, name, pattern, born=P)
      │
      ├─ 4. SCORE  (free) ─────────────────────────────────────────────────
      │  for R in REG.all:                      # all, not just active
      │      (tp, fp) = attribute(R, papers_seen)   # by rule_name / @uid
      │      REG.record(R.uid, ..., tp, fp)
      │
      ├─ 5. GATE  (free, reversible)  ◀── CHANGED ─────────────────────────
      │  for R in REG.all:
      │      R.status = ACTIVE if R.fdr(papers_seen) <= alpha else RETIRED
      │      # unobserved rules stay active — no evidence against them
      │
      └─ 6. EMIT + LOG
         write RULES.py from REG.active, each pattern tagged "# @uid:N"
         REG.save()                              # small JSON, not a file copy
```

### α-sweep (unchanged in spirit, much cheaper now)

Because step 4 caches per-paper `(tp, fp)` for **every** rule — including retired
ones — re-gating at a different α is a dict scan:

```
for alpha in grid:
    REG.apply_gate(alpha, papers=train_fold)     # pure CPU, reversible
    emit RULES.py
    score on val_fold
pick alpha* = argmax CV-F1
```

No snapshots, no restore, no risk of compounding prunes. `eval_distill_heldout.py`
keeps working; its snapshot machinery simply becomes unnecessary.

---

## What changes vs v1

| | v1 | v2 |
|---|---|---|
| rule identity | variable name, regenerated each paper | monotonic `uid`, stable |
| pruning | comment out source lines | `status` flag in registry |
| prune durability | wiped by next `aggregate` | persists; explicitly reversible |
| discarded rules | lost; re-invented later under new names | kept, **recycled for free** |
| aggregate prompt | all suggestions ever (19K→184K tokens) | current rules + *new* suggestions (bounded) |
| cost | quadratic; wall at ~paper 18 | ~linear |
| per-step snapshots | full dir copy (~14 MB / 147 files) | one JSON registry |
| "new rules per paper" | file size delta — conflates rewording | count of newly minted `uid`s |

---

## Open questions for Or

1. **Recycle threshold.** Currently a retired rule is revived if it matches ≥1
   dark-knowledge item at Jaccard ≥ 0.7. Too eager? A revived rule can be
   re-retired at step 5 the same round, so the cost of being wrong is low — but
   it will churn `status` in the history.

2. **Should recycling bypass the α gate?** Right now no: a revived rule is
   re-scored and re-gated immediately, so a genuinely bad rule bounces straight
   back out. That is principled but means recycling only helps when new evidence
   actually lowers the rule's FDR.

3. **Should `aggregate` see retired rules?** Sending "here are patterns that were
   tried and retired, don't re-propose them" would cut duplicate generation, at
   the cost of prompt size. Not currently done.

4. **Ordering.** Sub-linearity claims depend on paper order. Worth running two
   permutations to show the curve isn't an artifact of one ordering.

5. **Migration.** v1 artifacts have no UIDs. Options: (a) start the registry
   fresh and re-run, (b) back-fill UIDs into the v3 final rule set by body match
   and continue from there. (b) preserves the $14.57 already spent.

6. **Does the incremental aggregate degrade rule quality?** v1 showed the LLM
   *all* suggestions each round, which may have helped it generalize across
   papers. v2 shows current rules + new suggestions. This is the one change that
   could plausibly hurt F1 — worth an A/B on a few papers before committing.

---

## Files

| path | role | status |
|---|---|---|
| `scripts/distill_registry.py` | registry, stats, gating, recycling | **built + tested** |
| `scripts/eval_distill_heldout.py` | k-fold CV α-tuning wrapper | built (v1-compatible) |
| `scripts/distill_v2.py` | driver loop (steps 1–6) | **not yet written** |
| aggregate prompt change | emit `# @uid:N`; send current rules not all suggestions | **not yet written** |

The aggregate prompt lives in `src/LLMVersion/distillation_analysis.py`
(`aggregate_rules_merged`) — **Yaron's file**. v2 adds a parallel function rather
than editing his in place, so both paths stay runnable and comparable.
