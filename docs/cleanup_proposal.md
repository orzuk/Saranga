# Phase 4 Cleanup Proposal

> Generated: 2026-04-26 (Or, in main thread — sub-agent was sandboxed
> without Bash/Grep). **READ-ONLY proposal — no deletions performed.**
> Owner-of-decision: Or Zuk. Reviewer for `unsure` / LLMVersion items: Yaron.

## Summary

- 99 files scanned (40 in `src/`, 59 in `scripts/`)
- **keep**: 67   **merge**: 4   **delete-candidate**: 11   **unsure**: 17
- Estimated lines removable across confident-delete items: ~600 lines
- Scope: file-level identification only. **Within-file dead-code analysis
  was not performed** (deferred to a manual pass).

## Approach

For each `.py`/`.sh` file in `src/` and `scripts/`:
1. Pulled last-modified date and last-author from `git log -1`.
2. Counted incoming references via `grep -rn` across .py/.sh/.md.
3. Special handling for files explicitly preserved in
   `docs/pipeline_architecture.md` Section 11.
4. Yaron-touched-in-last-30-days files default to `unsure`.

## Confident-delete candidates (no refs, dormant, clearly one-off)

These are unused, have **zero incoming references** anywhere in the
repo (besides possibly the README's directory listing), and last
edits suggest they were one-off investigation scripts.

| File | Last edit | Refs | Reason |
|---|---|---|---|
| `scripts/debug_herald_counts.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/debug_herald_link.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/debug_herald_names.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/find_herald_examples.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/find_herald_examples_applied.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/find_herald_examples_concrete.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/find_herald_examples_favorites.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/save_herald_local.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/run_herald_convert.sh` | 2026-04-12 | 0 | Herald investigation one-off |
| `scripts/show_sample_records.sh` | 2026-04-12 | 0 | Herald inspection one-off |
| `scripts/zip_script.sh` | 2025-11-20 | 1 | One self-ref; old archiver utility |

**All 11 are Or-authored** (per `git log`), so no Yaron sign-off needed.
Confident: **delete**. Net: ~250 lines removed.

## Probable-delete (no refs, but newer or larger)

These have zero incoming references but are larger and/or more recent.
Worth a 2-minute eyeball before deleting.

| File | Last edit | Lines | Reason |
|---|---|---|---|
| `src/LLM_API_parsing.py` | 2025-12-03 | ~50 | Stub from earlier era, never imported anywhere |
| `src/arxiv_word_count.py` | 2026-01-04 | ~80 | One-off word-frequency tool, never imported |
| `scripts/run_multidim_benchmark.py` | 2026-04-14 | ~284 | No incoming refs; possibly dead exploration |
| `scripts/show_foundation_stats.py` | 2026-04-12 | unknown | No incoming refs |
| `scripts/inspect_naturalproofs.py` | 2026-04-12 | unknown | No incoming refs |
| `scripts/audit_foundation_index.py` | 2026-04-12 | unknown | No incoming refs (one-off audit) |

Recommendation: open each, confirm it's not in your active workflow,
then delete. ~half-day's worth of stale exploration scripts.

## merge (will be retired in a follow-up, NOT now)

| File | Status | Plan |
|---|---|---|
| `scripts/silver_gold/run_full_pipeline.py` | superseded | Replaced by `scripts/run_silver_gold.sh` (Phase 3); kept until silver-gold experiment migrates. **Do not delete this cycle.** |
| `src/foundation_linker.py` | duplicate-likely | Self-imports only; only README mentions it. `src/link_to_foundation.py` is the actively-used variant (17 refs across run_pipeline, run_extraction, design docs). Probable retire after verifying. |
| `scripts/parse_multi_category.sh` | predecessor | The 10-category version, superseded by `parse_multi_category_20.sh`. Self-references only. Probable retire after verifying Yaron isn't using it. |
| `src/evaluate_extraction.py` | future-merge | Will be subsumed by the new `eval` op in `src/run_pipeline.py` once the in-process `match_same_paper` lift lands (per `docs/graph_compare_design.md` Phase 2). Keep for now; ~6 weeks out. |

## unsure (Yaron-touched in last 30 days OR LLMVersion area)

These need Yaron's sign-off, not Or's alone:

| File | Last touch | Author | Status |
|---|---|---|---|
| `src/LLMVersion/*` (15 files) | last 30 days | Yaron + Or (mixed) | Yaron's primary area; unsure for all |
| `src/visualize_alignment.py` | 2026-04-20 | Yaron | Yaron's recent work for alignment viz |

**Action**: include in next email to Yaron — ask whether any of his
LLMVersion files are now obsolete after the Y2 + multi-category +
distillation work he's been doing.

## Phase-3-preserved files (don't touch yet)

Per `docs/pipeline_architecture.md` Section 11, the following are
**explicitly kept working** even though they overlap with Phase 3:

- `scripts/silver_gold/run_full_pipeline.py` — see `merge` table above
- `scripts/silver_gold/run_extraction.py` — Phase 3 backend for holistic-multi
- `scripts/silver_gold/consensus_intersect.py` — `consensus` op backend
- `scripts/silver_gold/wrap_math.py` — auto-wrap-math pre-pass
- `scripts/parse_smoke_test.sh` — referenced by Phase 3 docs as the
  smoke test
- The five `scripts/run_*.sh` Phase 3 wrappers (`run_corpus.sh`,
  `run_silver_gold.sh`, `run_gold_eval.sh`, `run_high_res.sh`,
  `run_alignment.sh`)

## keep — actively used core

Big-picture inventory of definitely-keep files (not exhaustively listed;
just so the list-counts add up). Includes:

- `src/run_pipeline.py` (Phase 3 master)
- `src/visualize_annotation.py` (just-stabilized after the math-render
  rabbit hole)
- `src/validate_annotation.py`, `src/anomaly_detection.py`,
  `src/link_to_foundation.py`, `src/graph_alignment.py` (cross-paper
  alignment library)
- `src/evaluate_annotation.py` — DAG/schema validation helpers
- `src/extract_arxiv_funcs.py`, `src/extract_arxiv_data.py` (arXiv API
  layer)
- `src/concept_registry_wikidata.py` (Wikidata grounding)
- `src/proofwiki_scraper.py`, `src/scrape_all_proofwiki.py`
- `src/foundation_linker.py` — see `merge` (probably retire, but verify)
- `src/extract_all_chapters.py` (BHK textbook extractor)
- `src/Autoformalizer/autoformalization.py`
- `src/structured_math/__init__.py`
- `src/edge_types.py`, `src/node_types.py`, `src/config.py`,
  `src/parsing_analysis.py`, `src/paper_plot_utils.py`,
  `src/annotation_utils.py`, `src/corpus_stats.py`
- `scripts/parse_smoke_test.sh`, `scripts/parse_math_co_cluster.sh`,
  `scripts/parse_multi_category_20.sh`, `scripts/parse_gold_papers.sh`
- `scripts/download_*.sh`, `scripts/fetch_arxiv_papers_metadata.sh`,
  `scripts/list_all_arxiv_ids_locally.sh`,
  `scripts/run_proofwiki_scrape.sh`
- `scripts/canonicalize/*` (8 files) — actively imported by
  `embedding_sigma.py` and others (5 incoming refs)
- `scripts/cross_paper_analysis.py`, `scripts/run_alignment_benchmark.py`
- `scripts/embedding_sigma.py`, `scripts/viz_alignment_heatmaps.py` (2 refs)
- `scripts/clean_foundation.py`, `scripts/annotate_granularity.py`

## Recommended action plan

If you want to act on this proposal:

### Round 1 (safe, high-confidence — ~2 min):

```bash
cd /mnt/c/Code/Github/Authomathics
git rm scripts/debug_herald_counts.sh scripts/debug_herald_link.sh \
       scripts/debug_herald_names.sh scripts/find_herald_examples.sh \
       scripts/find_herald_examples_applied.sh \
       scripts/find_herald_examples_concrete.sh \
       scripts/find_herald_examples_favorites.sh \
       scripts/save_herald_local.sh scripts/run_herald_convert.sh \
       scripts/show_sample_records.sh scripts/zip_script.sh
git commit -m "Phase 4 cleanup round 1: remove 11 unused herald/zip one-offs"
```

### Round 2 (probable, eyeball each first — ~15 min):

Open each in turn; if it's not in your workflow, delete:
- `src/LLM_API_parsing.py`
- `src/arxiv_word_count.py`
- `scripts/run_multidim_benchmark.py`
- `scripts/show_foundation_stats.py`
- `scripts/inspect_naturalproofs.py`
- `scripts/audit_foundation_index.py`

### Round 3 (post-NeurIPS):

- Verify and retire `src/foundation_linker.py` (replaced by
  `link_to_foundation.py`)
- Verify and retire `scripts/parse_multi_category.sh` (replaced by
  `parse_multi_category_20.sh`)
- After silver-gold experiment migrates to `scripts/run_silver_gold.sh`,
  retire `scripts/silver_gold/run_full_pipeline.py`
- After `eval` op matures, retire `src/evaluate_extraction.py`

### Round 4 (after Yaron review):

- Send Yaron the LLMVersion + visualize_alignment list — ask if any
  of his recent files are now obsolete

## Open questions for Or

1. **`scripts/run_multidim_benchmark.py`** (284 lines, no refs, recent):
   is this experimental and you'll come back to it, or genuinely
   superseded by `scripts/run_alignment_benchmark.py` + the embedding
   sigma work? Default: defer / mark unsure if you're not sure.

2. **`src/foundation_linker.py`** vs `src/link_to_foundation.py`:
   the README documents both as if they're parallel APIs. Are they?
   If so, why two? If `foundation_linker.py` is the OOP version that's
   never called, it's a clean delete.

3. **`scripts/zip_script.sh`** has 1 self-ref but no external use. Was
   this an old release-archiving tool? Probably safe to delete but
   confirm.

4. **`src/visualize_alignment.py`**: Yaron's last commit; only used by
   alignment-benchmark workflow. Worth a one-line message to him before
   touching.

## Risks (from Phase 3 handoff)

- The new `--extract-mode` flag in `src/run_pipeline.py` and the legacy
  `--extraction-mode` flag are intentionally distinct names but one
  letter apart. Reviewers / new contributors may confuse them. Consider
  a clearer rename in a future cycle.
- `op_consensus` / `op_eval` are defined after `if __name__ == "__main__":
  main()` originally but moved to EOF; if anyone refactors run_pipeline
  back to a non-EOF main guard, dispatch will silently fail again.

---

Total scope: 11 confident deletions, 6 probable deletions, ~17 unsure,
~4 future-merge candidates. Net potential reduction: ~600 LOC and 17
files (out of 99) before any Yaron review.
