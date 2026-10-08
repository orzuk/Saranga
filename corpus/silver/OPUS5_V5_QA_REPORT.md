# Opus-5 / v5 extraction — QA report

Sanity checks on the first `claude-opus-5` + prompt-v5 extractions, run overnight
2026-07-30. Reproduce any number below with the scripts named in each section.

**Scope:** 20 papers / 1,956 nodes / 1,789 edges.
- **5 "smoke" papers** (`paperNNN`) re-extracted from the existing 60-paper v4.1
  test set, so opus-5/v5 can be diffed against opus-4.8/v4.1 on identical inputs.
- **15 pool papers** (arXiv ids) from the new stratified 1000-paper sample
  (50 × 20 `CORPUS_CATEGORIES`).

> **Run did not reach the 100-paper target.** A sustained service-wide
> `529 Overloaded` condition killed ~25 agents, most before they did any work
> (they died within seconds of starting, at every concurrency level tried,
> including 5). This is transient infrastructure, unrelated to the prompt or
> schema. All 100 papers' LaTeX is already staged locally, so finishing is a
> pure re-run: `python scripts/extraction_status.py` prints the exact TODO list.

---

## 1. Headline: the extractions are faithful

`scripts/audit_verbatim.py` — checks every `statement` against the source .tex.

| | |
|---|---|
| nodes with a statement | 1,956 |
| traceable to source | **1,954** (exact 1,473 / after mechanical cleanup 474 / head-match 7) |
| **fabrication candidates** | **0** |
| **verbatim fidelity** | **99.90 %** |

The 2 flagged nodes are *not* fabrications: in `paper462` the model joined a
`{\bf The upper bound}` heading to the prose after it, skipping an intervening
display equation. Every character is genuine source text — it is a
**non-contiguous span**, a minor prompt-compliance nit. Both bodies match the
source 100 % on their own.

This includes `paper222` (*Attention Is All You Need*), the highest
memory-recall risk in the set: **90/90 statements exact**. The
no-prior-knowledge discipline holds.

## 2. Structural integrity: clean

`scripts/qa_extractions.py` — **0 ERROR-level problems across all 20 papers**:

- no cycles (every graph is a DAG)
- no dangling edge endpoints, no self-loops
- no duplicate node ids
- no non-canonical node or edge types
- no Level-2 (`proof_step`/`algorithm_step`) parent violations
- no bad `origin` values

## 3. Edge directions: fixed, and now conform

A real bug was found and fixed mid-run. `src/edge_types.py` declared the *actor*
as `source` for `solves`/`illustrates`/`tests`, contradicting the module's own
stated convention. The convention is now uniform —

> **arrow `A → B` means B relies on A** (`source` = relied upon, `target` = depends on it)

— which required editing `edge_types.py` (`problem→algorithm`, `concept→example`,
`concept→exercise`) and rewriting the prompt's edge section with an explicit
source/target table plus worked JSON examples, replacing an ambiguous
"B [type] A" phrasing that had caused **40 inverted `proves` edges**. Those were
normalised with `scripts/normalize_edge_directions.py`.

Post-fix: **0 non-conforming edges.**

## 4. Corpus shape

Mean **98 nodes / 85 edges** per paper (range 19–260).

| node type | n | share | | edge type | n | share |
|---|---|---|---|---|---|---|
| proof_step | 621 | 31.7 % | | `uses` | 1,482 | 82.8 % |
| definition | 285 | 14.6 % | | `proves` | 186 | 10.4 % |
| proof | 185 | 9.5 % | | `illustrates` | 75 | 4.2 % |
| remark | 166 | 8.5 % | | `generalizes` | 25 | 1.4 % |
| equation | 96 | 4.9 % | | `solves` | 11 | 0.6 % |
| proposition | 93 | 4.8 % | | `resolves` | 6 | 0.3 % |
| theorem | 86 | 4.4 % | | `specializes` | 4 | 0.2 % |
| lemma | 85 | 4.3 % | | | | |
| algorithm_step | 82 | 4.2 % | | | | |
| claim / example / assumption / corollary / algorithm / open_problem / problem / conjecture | 257 | 13.1 % | | | | |

New v5 fields populate well: `origin` on **100 %** (1,653 paper / 303 external),
`statement_short` on **81 %**, and `genus`+`differentia` on **243/285 = 85 %** of
definitions (skips are pure notation, as the prompt instructs).

## 5. Problems worth fixing (all WARN-level)

| issue | count | what it means |
|---|---|---|
| **orphan nodes** | **733 / 1,956 = 37.5 %** | **Biggest issue.** Nodes with no edge at all; mean degree is only 0.98 edges/node. Worst case 96/164 (59 %). A discovery graph this sparse under-links. |
| missing `section` | 37 | required by v5 |
| missing `origin` | 37 | required by v5 (the 100 % above counts nodes that have the key; these are the misses) |
| nested statements | 32 | same source text inside two nodes (e.g. a proof containing an equation) — double-counts content |
| proof without `proves` edge | 15 | proof not linked to what it proves |
| very long / very short statements | 3 | outliers worth eyeballing |

**Recommended prompt change (highest value): attack the orphan rate.** The v5
prompt tells the model to be conservative about edges ("2 well-justified edges
beat 10 speculative ones"), which — combined with dense node extraction — yields
graphs where over a third of nodes are isolated. Later waves already include an
explicit "minimise orphan nodes / link every proof / set origin+section on every
node" instruction; that should be folded into the prompt itself and re-measured.

## 6. Opus-5/v5 vs opus-4.8/v4.1 (`scripts/compare_extractions.py`)

Same 5 papers, both extraction configs:

| paper | v4.1 nodes → v5 | v4.1 edges → v5 | LaTeX theorem envs in source |
|---|---|---|---|
| paper431 (math note) | 15 → 19 | 14 → 19 | 5 |
| paper462 (JL sparsity) | 51 → 99 | 45 → 73 | 10 |
| paper217 (Highway Nets) | 8 → 47 | 8 → 52 | **0** |
| paper222 (Transformer) | 20 → 90 | 21 → 100 | **0** |

Two regimes, and the cause is legible:
- **Formal-environment papers grow modestly (~1.3–2×)**, almost entirely finer
  `proof_step` decomposition; the core skeleton is unchanged (paper431:
  definitions 5=5, theorems 3=3, proofs 2=2).
- **Papers with no theorem environments grow 4–6×.** v4.1 extracted essentially
  only what sat inside `\begin{...}` environments and produced **zero**
  claims/algorithms/examples, missing those papers' actual substance. v5
  correctly promotes asserted prose to `claim` nodes. Spot-checking confirmed the
  new nodes are real verbatim content with correct `origin` tagging, not noise.

**Context for how often this matters:** across the 100 staged papers, **11 %
have zero** theorem-like environments and **17 % have fewer than 5** (median 20).
So a regex extractor is structurally blind on roughly the 11–17 % tail — not on
the majority. (An earlier estimate of ~40 % was an artifact of the smoke sample,
which deliberately over-picked prose-heavy ML papers.)

**Implication for the rules-vs-silver evaluation:** pooled F1 against v5 silver
will read lower than the current in-sample 0.711→0.735, because the target now
includes node types regex cannot reach. Report **per-type F1** (the evaluator
already does) and decide deliberately whether prose `claim`/`remark` nodes belong
in the rule extractor's evaluation target.

## 7. Data-quality bug found and fixed: truncated multi-file papers

`scripts/fetch_tex_for_targets.py` originally kept only the main `.tex`, so
papers split across `\input{}`/`\include{}` files lost their real content.
`1008.2565v2` was **1,950 bytes of a 73,353-byte paper — 97 % missing**. The
fetcher now recursively splices `\input`/`\include` members from the arXiv tar
(skipping `.sty`/`.cls`/figure `.pdf_tex` includes). 6/100 staged papers were
affected; 3 had genuine content loss and were re-fetched. `1112.1643v2`, whose
first extraction used the truncated source, is queued for re-extraction.

## 8. Reliability observations for the full 1000-paper run

- **Concurrency cap is 20 subagents** (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`).
  Batches must be serialised or launches are rejected.
- **Partial writes are a real failure mode.** An agent killed mid-write left
  `1710.06030v2` with **114 nodes and 0 edges**. `extraction_status.py` now
  requires *both* nodes and edges before counting a paper done, and the prompt
  now demands a single complete write.
- **Expect retries.** Beyond the 529 storm, ~15 % of healthy long extractions
  ended in "stalled mid-stream" / "server error mid-response", always on large
  papers and always after the tex had been read. Retry is cheap and idempotent.
- **Model-string inconsistency:** agents self-report either `claude-opus-5` or
  `claude-opus-5[1m]` (14 vs 7). Cosmetic; worth normalising in metadata.

## 9. Reproduce / continue

```bash
python scripts/extraction_status.py                 # what is done / what is left
python scripts/fetch_tex_for_targets.py --batch N   # stage LaTeX (already done for 100)
python scripts/audit_verbatim.py                    # anti-hallucination gate (exit 1 on failure)
python scripts/qa_extractions.py                    # structural + anomaly sweep
python scripts/normalize_edge_directions.py --dry-run   # detect flipped edges
python scripts/compare_extractions.py               # v5 vs v4.1 diff
```
