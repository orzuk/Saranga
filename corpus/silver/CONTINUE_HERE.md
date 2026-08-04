# Silver extraction — session handoff

**Written 2026-08-04.** Read this first if you are continuing the opus-5 / v5.1
silver extraction in a new session. Everything needed is on disk; nothing depends
on the previous conversation.

---

## Goal

Reach **200 papers** in `corpus/silver/opus-5__v5.1/`. Currently at **107**.

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

## Where things stand

| | |
|---|---|
| done | 107 |
| batch 6 outstanding | 13 (tex ALREADY staged) |
| batches 7-10 | 80 (tex NOT yet fetched) |
| needed for 200 | 93 |

**Batch 6 leftovers** (3 failed mid-write, 10 never launched — a per-session
agent cap was hit):

```
1207.0773v2 1002.3951v4 1806.04821v1 1908.05998v1 1011.5266v2 1111.3171v5
1910.10789v1 1306.2128v2 1505.00362v2 1804.10737v1 1801.06721v2 1910.14559v3
1803.09015v4
```

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
- Do not merge the macro glossary into paper JSONs yet — that is a single pass
  over all 200 at the end (`corpus/silver/macros/` holds the staged per-paper
  files; see E143 in the v6 register for why macros must NOT be expanded).
- Do not commit `corpus/silver/tex_pool/` (regenerable) or
  `corpus/silver/opus-5__v5/` (superseded run).

## After 200 papers

1. `python3 scripts/corpus_report.py` — QA report
2. `python3 scripts/audit_verbatim.py --dir corpus/silver/opus-5__v5.1` —
   anti-hallucination audit (last run: 99.96% traced, 2 genuine alterations)
3. `python3 scripts/fetch_true_categories.py` — arXiv primary vs sampled category
4. Merge macro glossaries into `metadata.macros` in ONE pass
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
