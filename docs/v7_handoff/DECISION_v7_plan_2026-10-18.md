# v7 run plan: A, B or C? (notes to decide, 2026-10-18)

Status: **open**. The "Decided: Plan B" in `README.md` (this folder, written the morning of 2026-10-18) is
reopened by Or. This file holds the options, costs and arguments.

## Budget

- Weekly plan ≈ $1,750 (README estimate). It resets **Monday 2026-10-19 afternoon**; whatever is not used
  by then is lost.
- Or wants to spend ~70–75% today / Monday morning ≈ **$1,250–1,300**.
- Building code in Claude Code comes out of the same plan (included below as "build").

## Cost per job (share of a weekly plan, from README)

| job | estimate | week |
|---|---:|---:|
| 200 silver (v7 maybe +10–20%) | ~$580 | 33–40% |
| 146 diagram papers (LaTeX 2.2× silver, median 148 KB) | ~$750–900 | 45–50% |
| 104 blueprints (least certain) | ~$300–450 | 20–25% |
| ~20 blueprint source papers (long) | ~$150–250 | 10–15% |
| mini-pilot, 5 papers | ~$30 | ~2% |
| building v7 with Claude Code (estimate) | — | 5–10% |

The 146 = good, class "results, reliable", ≥ 0.05 arrows per KB; list in
`corpus/gold_candidates/eval_subset.txt` (tracked since d1a0cda).

## The options

### Plan A: keep v6; run the 146 with the old code
- Code: rebuild branch `v6-frozen` = `ea74b60` (end of the v6 run) + the cycle fix of `e7f0fc3`.
  (The branch existed only on the other laptop; `ea74b60` is in the repo.)
- **This week: ~50%. Total: ~50%.**
- Pros: no new code, lowest risk; consistent with the existing 200 v6 silver (same code); directly validates
  the silver that the paper and Yaron's alg3 use today.
- Cons: Or's fixes are never run (v7 wanted anyway); ~20–25% of this week's budget unused.

### Plan B (README): build v7 tonight, freeze, run 200 silver, then as many of the 146 as fit
- **Today ~75%**: build 5–10% + mini-pilot 2% + 200 silver 33–40% + ~25% → ~60–80 of the 146.
- **Next week ~60%**: rest of the 146 (~25%) + blueprints (20–25%) + source papers (10–15%).
- **Total ≈ 135%** (cheapest overall; every job runs once).
- Pros: one consistent v7 for everything; no double runs.
- Cons:
  - v7 scope is not confirmed and would be built and frozen in a few hours *because the budget expires* —
    v6 needed 13 reruns from mid-run fixes.
  - Schema decisions 3 (`equivalent` edge) and 4 (`motivates` / non-dependency links) were meant to be decided
    *with a gold pilot*; B freezes before any gold evidence → a v8 is likely.
  - Tonight's silver-vs-gold numbers would be partial (only part of the 146).

### Plan C (Claude's recommendation): Plan A on gold now, Plan B next week
- **Today ~70%**: rebuild `v6-frozen` + 3-paper gold smoke (~1%, ~1 h); the 146 under v6 (45–50%);
  meanwhile build v7 interactively, without rush (5–10%); ~10% buffer (the diagram estimate is the uncertain one).
- **Next week ~100–120%**: v7 on everything (200 + 146 + blueprints + sources); may spill into a third week,
  mainly the blueprints.
- **Total ≈ 170–190%**, but the first ~70% is budget that would otherwise expire.
- Pros:
  - uses expiring budget on a job that needs no new code;
  - first silver-vs-gold numbers, for the silver that actually exists (paper + alg3);
  - v6 errors on real gold become the error analysis that scopes v7 and settles decisions 3 and 4 with evidence;
  - the paper gets a v6 → v7 improvement measured on independent gold (an ablation);
- Cons: the 146 are extracted twice (~50% extra over two weeks); next week fully booked; the paper reports two
  versions (v7 main, v6 as comparison).

### Variant B′ (if v7 must be final in the paper within ~10 days)
Plan B but narrow and gold-first: v7 = only the `finalize()` code additions + prompt rules from README (no
schema changes); mini-pilot; run the **146 first** (the paper's missing number arrives first, and a v7 problem
shows up before the 200), then the 200 with what is left; blueprints next week. Costs as B.

## What actually matters (Or, 2026-10-18)
1. **Cost against the weekly plan**, and the run must start tonight so this week's allowance is not wasted.
2. **Re-analysis**: every re-extraction means redoing the analysis (silver stats, distillation, paper
   numbers), and the new results may be worse or unexpected.
Not a factor: Yaron's retraining (alg3 retrains in 5–10 min, no API cost).

How the plans fare on these two:
| | tonight's spend | re-analysis |
|---|---|---|
| A | ~50% (no build, starts within ~1 h) | none of the existing work; only new gold scores |
| B | ~75% (starts after the v7 build, late tonight) | everything (200 + 146 + later blueprints), on a v7 never seen on gold |
| C | ~70% (A now + v7 build) | none now; next week only if v7 proves better on gold |

Under factor 2, C has one more advantage: **v7 becomes optional.** With v6 scored on gold, a small v7
pilot on gold papers next week shows whether v7 is better; if it is not clearly better, the 200 are not
re-extracted and nothing is re-analysed.

## Why C (Claude's view)
The only reason to spend today is that the budget expires. That is a bad reason to freeze extractor code in a
hurry, and a good reason to run a job that needs no new code. If the deadline forces v7 into the paper soon,
take B′.

## Questions to settle before choosing
1. Paper deadline: must the final silver be v7 for submission, and when?
2. Is a v6-vs-v7 comparison on gold worth having in the paper (favours C)?
3. Yaron: is he OK retraining alg3 on v7 silver, and when (affects B and C)?
4. v7 scope: confirm the README list; include decisions 3/4 now or after gold evidence?
5. Reviews: no `review.json` exists on this machine — are reviews on the other laptop still unpushed?

## Related
- `README.md` (this folder): v7 scope, run procedure, dry-run results.
- `G:/My Drive/Research/Automath/HANDOFF_2026-10-17.md`, `saranga_paper_status_todo.md` (items 2.2–2.4).
