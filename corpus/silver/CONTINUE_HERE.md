# Silver extraction — session handoff

**Updated 2026-08-04 (session 2).** The 200-paper target is **REACHED**.
This file now describes what remains *after* extraction.

---

## State

| | |
|---|---|
| papers in `corpus/silver/opus-5__v5.1/` | **200 / 200** |
| nodes / edges | 25,162 / 39,839 |
| mean nodes per paper | 125.8 |
| acyclic | 200/200 |
| papers with 0 orphans | 180/200 |
| partial or unparseable files | 0 |
| prompt | v5.1, sha256 prefix `100e6cf6fdbb3aea`, unchanged for all 200 |

Done this session: batch 6 leftovers (13) + batches 7-10 (80) = 93 papers.
`corpus_report.py`, `audit_verbatim.py`, `build_macro_glossary.py` (now 200/200
macro files) and `fetch_true_categories.py` have all been re-run.

## What is LEFT

1. **Assign the train/test split** — still deliberately deferred; the pool CSV
   has no split column, so it can be drawn at any time.
2. **Decide the E144 convention** before any re-extraction.

(Macro merge is DONE — all 200 papers carry `metadata.macros`, 10,085 macros.)

## Macros are now part of the paper JSON

Each paper's `metadata.macros` holds `{name: {expansion, kind, arity}}`, joined
in from `corpus/silver/macros/`. Macros are **recorded, never expanded** (E143),
so every `statement` is still a verbatim span of the *unexpanded* source.

`n_macros`/`by_kind` are deliberately not copied into the paper — both are
derivable from the dict, and a second copy would be a second thing to drift.

For future extractions this is one command; the merge is idempotent and asserts
the node/edge counts are unchanged before it swaps the file in:

```bash
python3 scripts/build_macro_glossary.py --merge      # build glossaries + merge
python3 scripts/merge_macros.py                      # merge only
python3 scripts/merge_macros.py --dry-run            # report, write nothing
```

Papers whose glossary is built before their extraction exists are skipped
silently, so the `--merge` build is safe to run at any point in a run.

**Gold is covered too** — all 46 files across the 6 gold dirs (15 distinct
papers). Gold tex now lives in `corpus/gold/tex/` (the 10 tier1 papers had none
and were fetched), glossaries in `corpus/gold/macros/`:

```bash
python3 scripts/fetch_tex_for_targets.py --out-dir corpus/gold/tex --ids <...>
python3 scripts/build_macro_glossary.py --tex-dir corpus/gold/tex \
        --out-dir corpus/gold/macros
python3 scripts/merge_macros.py --extract-dir corpus/gold/<dir> \
        --macro-dir corpus/gold/macros [--legacy-metadata]
```

Gold is **not** schema-uniform: the four tier1 dirs are `{metadata, nodes,
edges}` like silver, but `human__gold` and `human__diagram` are
`{paper_id, objects, relations}` with no metadata block. Those need
`--legacy-metadata`, which creates `metadata: {paper_id, macros}` and leaves the
existing top-level keys alone; without the flag they are skipped, not crashed
on. `objects`/`relations` counts are asserted unchanged, same as nodes/edges.

## Two findings that change what you should trust

- **E145 — one paper had the WRONG source file.** `pick_main_tex` took the first
  `.tex` containing `\documentclass` in arbitrary tar order; `1505.06386v1`
  shipped a 3 KB standalone figure file that beat the real 64 KB body, giving
  1 node / 0 edges. Fixed in `scripts/fetch_tex_for_targets.py` (candidates are
  now scored on documentclass / begin-document / title / size), paper re-fetched
  and re-extracted (74 nodes / 87 edges). The whole pool was swept — only case.

- **E144 — the verbatim audit's headline is generous.** It reports 99.97%
  traced, but 107 nodes match only on their *head*, so mid-span differences are
  invisible to it. A stricter whole-span check finds **84 nodes in 19 papers**
  that are not one contiguous source substring. These are **excisions, not
  fabrications**: agents removed TeX-suppressed blocks (`\iffalse`, `comment`,
  `\ignore{}`, `\exclude{}`, `\suppress{}`) from inside spans, and agents split
  both ways on whether to do so. Fix the convention in v6, and fix the audit to
  report head-only matches as their own bucket.

---

## THE ONE HARD CONSTRAINT

Every paper must be extracted with the **same frozen prompt**. Verify before
every launch:

```bash
sha256sum scripts/opus_extract_prompt_v5_1_rendered.md | cut -c1-16
# MUST print: 100e6cf6fdbb3aea
```

If it does not match, **stop** — do not extract. A mid-run prompt change makes
the corpus non-uniform, which has already forced one full re-extraction.
Do not "improve" the prompt mid-run, however tempting; log issues to
`scripts/opus_extract_prompt_v6_TODO.md` instead.

## What to run first

```bash
python3 scripts/extraction_status.py --batches 10 --todo-only
```

The **filesystem is the source of truth** — this reconciles the 1000-paper pool
against what has actually been written, so no bookkeeping needs to survive the
session boundary. A paper counts as done only if its JSON has BOTH nodes and
edges.

## Procedure per batch

1. **Fetch tex** (plain script, costs no agents; batch 6 is already done):
   ```bash
   python3 scripts/fetch_tex_for_targets.py --batch 7      # then 8, 9, 10
   ```
   Batch N = the Nth paper of each of the 20 categories.

2. **Verify the prompt hash** (above).

3. **Launch one agent per paper**, up to 20 concurrent. The launch prompt that
   works is in `scripts/LAUNCH_PROMPT_TEMPLATE.md` — use it verbatim, only
   substituting the arxiv id. Two clauses in it are load-bearing:
   - **builder-script write method.** Emitting the whole JSON as literal output
     tokens stalls mid-stream; it cost ~11 papers before the switch. The script
     must write to a temp file and `os.replace()` into place, so a stall during
     the agent's *report* does not lose the extraction (confirmed: `1211.4949v1`
     "failed" yet its file is complete and valid).
   - **private scratchpad subdirectory.** Agents pick generic names
     (`build.py`, `clean.py`, `cleaned.txt`) and one collision was observed at
     the shared root. A collision could make an agent read another paper's
     cleaned source and emit spans from the WRONG paper.

4. **After each batch**, re-run `extraction_status.py` — never trust remembered
   counts. Retry whatever is still missing. Check for partial files: a JSON with
   nodes but no edges must be deleted and redone.

## Known operational hazards

- **Per-session subagent cap.** The previous session hit 200 spawned agents and
  could spawn no more; the counter counts agents *spawned*, not concurrent, so
  finishing one frees nothing. Historically ~45% of agents went to retries, so
  93 papers may need ~135 agents. Raise the cap in `/config` if needed.
- **Long tail.** Median paper is 8-13 min, but `1705.02177v2` took 2.5 hours. A
  batch finishes only when its slowest member does.
- **Transient stalls** ("Response stalled mid-stream") are infrastructure, not
  the paper's fault. Re-launch identically; check for a partial file first.

## Do NOT do these

- Do not change the prompt, the schema, or `src/node_types.py` / `edge_types.py`.
- Do not EXPAND macros into statements (E143). Merging the glossary into
  `metadata.macros` is fine and is now automatic — that records the pairs
  without touching any span.
- Do not commit `corpus/silver/tex_pool/` (regenerable) or
  `corpus/silver/opus-5__v5/` (superseded run).

## After 200 papers  (1-4 DONE this session; only 5 remains)

1. `python3 scripts/corpus_report.py` — QA report
2. `python3 scripts/audit_verbatim.py --dir corpus/silver/opus-5__v5.1` —
   anti-hallucination audit (last run: 99.97% traced, 7 unmatched — but see
   E144: head-only matches hide 84 non-contiguous spans across 19 papers)
3. `python3 scripts/fetch_true_categories.py` — arXiv primary vs sampled category
4. ~~Merge macro glossaries into `metadata.macros`~~ — DONE
   (`build_macro_glossary.py --merge`, or `merge_macros.py`)
5. Assign the train/test split (deliberately deferred — the pool CSV has no
   split column so it can be drawn later)

## Context that is easy to lose

- `scripts/opus_extract_prompt_v6_TODO.md` holds ~143 catalogued issues. The
  highest-severity ones are **spec defects, not model failures**: E120
  (acyclicity forces silent deletion of real edges — 3 papers, 5 edges, 3
  distinct causes, and NOT detectable post-hoc), E130 (`rigor` declared
  universal but never requested → present on 5% of nodes), E113 (the prompt
  lists 7 edge types in one place and 8 in another, and disagrees with
  `edge_types.py`), E143 (macros must not be expanded — measured 341 colliding
  expansions and 473 colliding names).
- `category` in `extraction_targets_opus5.csv` is the **sampled** category, not
  the arXiv primary; 30/100 differ. Use the sampled axis for per-subfield tables
  (it is balanced 5x20) and treat primary as a robustness check
  (`ROADMAP.md` 7.5.1).
- `confidence` is **not comparable across papers** (no shared rubric anchor).
- Owner split: Yaron owns `src/LLMVersion/` and the cluster pipeline; Or owns
  the schema, orchestrator, and portal. Do not edit Yaron's files without
  flagging it.
