# Agent launch prompt — opus-5 / v5.1 silver extraction

Use **verbatim**, substituting only `{ARXIV_ID}`. One agent per paper, max 20
concurrent. Verify `sha256sum scripts/opus_extract_prompt_v5_1_rendered.md`
prints `100e6cf6fdbb3aea` before launching any.

Every clause below is load-bearing — each was added after a specific observed
failure. Notes on why are at the bottom; do not trim them from the prompt.

---

```
Extract a unified-JSON knowledge graph from an arXiv paper, following a FROZEN specification exactly.

STEP 1 — Read the specification IN FULL and follow it literally:
  /mnt/c/Code/Github/Saranga/scripts/opus_extract_prompt_v5_1_rendered.md
Frozen, sha256 prefix 100e6cf6fdbb3aea. Do NOT deviate, do NOT add heuristics of your own, do NOT optimize for metrics it does not state. Uniformity across all papers matters more than any local improvement you think you could make.

STEP 2 — Source LaTeX:
  /mnt/c/Code/Github/Saranga/corpus/silver/tex_pool/{ARXIV_ID}.tex

STEP 3 — WRITE METHOD. Work in a PRIVATE scratchpad subdirectory named for this paper (other agents run concurrently in the same scratchpad root and generic names like build.py / clean.py / cleaned.txt collide). Do NOT emit the whole JSON as literal output tokens — that stalls mid-stream on large graphs. Instead write a small Python builder script and run it:
  - it reads the .tex and applies ONLY the spec's permitted mechanical cleanup (strip comments, drop \label/\index, collapse whitespace);
  - you supply a compact node table (id, type, name, section, confidence, origin, + a (start,end) offset pair or unique short anchor for each verbatim field);
  - the script SLICES statement/assumptions/conclusions/genus/differentia out of the cleaned source rather than you retyping them — this keeps your output small and guarantees verbatimness;
  - json.dump to a temp file, verify, then os.replace() into place.
Target: /mnt/c/Code/Github/Saranga/corpus/silver/opus-5__v5.1/{ARXIV_ID}.json
Top-level keys "metadata","nodes","edges"; metadata.model="claude-opus-5[1m]", metadata.prompt_version="v5.1", metadata.arxiv_id="{ARXIV_ID}".
Never leave a partial file at the target path — a file with nodes but no edges counts as a failed extraction.

STEP 4 — Have the script assert before the final move: valid JSON; every edge source/target resolves; edge set acyclic; every verbatim field is a substring of the cleaned source; no span swallows a structural boundary (\section{, \begin{proof}) more than 200 chars in, which catches an ambiguous anchor mis-slicing a span. Fix and re-run until all assertions pass.

Return a CONCISE report: node/edge counts, breakdown by type, orphan count, mean node and edge confidence, statement_short coverage, and any spec ambiguity/gap/conflict you hit. Report problems honestly; do not silently invent rules.
```

---

## Why each clause exists

| clause | failure it prevents |
|---|---|
| "frozen ... do NOT deviate ... uniformity matters more" | Agents given latitude optimized differently per batch — one wave produced 34.3% orphans vs ~0% for another, purely from prompt drift. Forced a full re-extraction. |
| **builder script, not literal JSON output** | ~11 agents died at "now I'll write the JSON", stalling mid-stream while emitting a large payload as output tokens. |
| **temp file + `os.replace()`** | Makes the write atomic, so a stall during the agent's *report* costs nothing. Confirmed: `1211.4949v1` reported as failed, yet its file is complete and valid (156 nodes / 268 edges). |
| **private scratchpad subdir** | One agent's `clean.py`/`cleaned.txt` collided with another's at the shared root. Worst case an agent reads a different paper's cleaned source and emits spans from the WRONG paper. |
| **"never leave a partial file"** | `extraction_status.py` counts a JSON with nodes but no edges as failed; without atomicity such files accumulate and look done. |
| **structural-boundary assertion** | One agent's ambiguous anchor produced a 19,000-char mis-sliced `proof_step`. A mis-slice is still a valid *substring*, so the verbatim audit cannot catch it — only this check can. |
| **"report problems honestly"** | The v6 issue register (~143 items) exists entirely because agents volunteer spec conflicts. E120 — the only defect that destroys data — is known ONLY because agents reported dropping edges. |

## Optional additions

- For a paper over ~250 KB, add: `NOTE: this is a LARGE paper (~N KB). Cover the whole paper; do not truncate.` But check first whether the bulk is commented-out — `1705.02177v2` was 267 KB of which 115 KB was commented-out working notes.
- On a retry after a stall, do **not** change the prompt. Check for a partial file first, then relaunch identically; stalls are infrastructure, not the paper.
