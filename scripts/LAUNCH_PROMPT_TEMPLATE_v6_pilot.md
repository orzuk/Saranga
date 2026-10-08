# Agent launch prompt — v6 pilot (four model arms)

Use verbatim, substituting `{ARXIV_ID}`, `{ARM}`, `{MODEL}`, `{EFFORT}`. One agent
per (paper, arm). Verify the rendered spec's sha256 prefix is `e8634828e2122158`
before launching. Derived from `LAUNCH_PROMPT_TEMPLATE.md` (v5.1); every clause
kept from it exists for the reason recorded there.

---

```
Extract a unified-JSON knowledge graph from an arXiv paper, following a FROZEN specification exactly.

STEP 1 — Read the specification IN FULL and follow it literally:
  /mnt/c/Code/Github/Saranga/scripts/opus_extract_prompt_v6_pilot_rendered.md
Frozen, sha256 prefix e8634828e2122158. Do NOT deviate, do NOT add heuristics of your own, do NOT optimize for metrics it does not state. Uniformity across all papers matters more than any local improvement you think you could make.
In the spec: {TEX_SOURCE} = /mnt/c/Code/Github/Saranga/corpus/silver/tex_pool/{ARXIV_ID}.tex ; {OUTPUT_JSON} = /mnt/c/Code/Github/Saranga/corpus/silver/pilot_v6/{ARM}/{ARXIV_ID}.json ; {MODEL} = {MODEL} ; {EFFORT} = {EFFORT} ; {BID} = {ARXIV_ID}. Title, authors and year: take them from the source.

STEP 2 — LaTeX facts first (the spec's "Two layers" section):
  python3 /mnt/c/Code/Github/Saranga/src/latex_facts.py /mnt/c/Code/Github/Saranga/corpus/silver/tex_pool/{ARXIV_ID}.tex --out <your scratch dir>/facts.json
Read the cleaned `source` from facts.json; slice every verbatim field from it, never from the raw .tex. The facts cover environments only: finding the results, definitions, remarks and problems written in prose is your main job.

STEP 3 — WRITE METHOD. Work in a PRIVATE scratchpad subdirectory named for this paper AND arm ({ARM}_{ARXIV_ID}); other agents run concurrently in the same scratchpad root and generic names collide. Do NOT emit the whole JSON as literal output tokens — that stalls mid-stream on large graphs. Write a small Python builder script and run it:
  - it loads facts.json and uses facts["source"] as the cleaned text;
  - you supply a compact node table (id, type, name, section, confidence, origin, + a (start,end) offset pair into the cleaned source, or a fact id, for each verbatim field);
  - the script SLICES statement/assumptions/conclusions/genus/differentia out of the cleaned source rather than you retyping them;
  - json.dump to a temp file, verify, then os.replace() into place.
Top-level keys "metadata","nodes","edges"; metadata.model="{MODEL}", metadata.effort="{EFFORT}", metadata.prompt_version="v6-pilot", metadata.arxiv_id="{ARXIV_ID}".
Never leave a partial file at the target path.

STEP 4 — Before the final move, the builder must call the pipeline's finishing stage and assert on it (spec, Workflow step 8):
  import sys; sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
  from extraction_finalize import finalize
  report = finalize(graph, open(TEX_PATH, encoding="utf-8", errors="replace").read())
  assert not report["errors"], report["errors"]
It fills label and source_line_label, adds \ref-stated uses edges and syntax-stated proves edges, and validates. Fix every error and re-run until it passes. Also have the script assert that no span swallows a structural boundary (\section{, \begin{proof}) more than 200 chars in.

Return a CONCISE report: node/edge counts, breakdown by type, how many nodes came from environment facts vs prose, orphan count, mean node and edge confidence, statement_short coverage, the finalize report summary (labels filled, edges added, backward refs), and any spec ambiguity/gap/conflict you hit. Report problems honestly; do not silently invent rules.
```
