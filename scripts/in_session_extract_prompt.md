# In-session extraction prompt (v4.1, agentic)

Paste the block below into a Claude Code session, filling in `<PAPER_NUM>`
and the two paths. It reproduces the paper005 run: v4.1 rules executed with
the operational discipline that kept the output verbatim and hallucination-free.

Prerequisite — WHERE THE SOURCE LIVES: the tier2 `.tex` sources are NOT in
the code repo. They live in the external dataset dir:

    /Users/yaronot/Datasets/Authomathics_data/alignment/papers/paper<NNN>/source/paper<NNN>.tex

Always look there FIRST (one paper per `paper<NNN>/source/` subdir). Do not
conclude "no local source" just because nothing matches under the repo working
directory — the repo only holds the rendered graphs (`portal/graphs/tier2/`),
not the `.tex`. Only if the file is genuinely absent from the dataset dir,
fetch the arXiv source tarball (`https://arxiv.org/e-print/<arxiv_id>`),
extract the main `.tex`, and save it to that same canonical path before
extracting.

---

Extract paper<PAPER_NUM> to a v4.1 knowledge-graph JSON, in-session, exactly
the way we did paper005. Do NOT one-shot this and do NOT use any prior
knowledge you have of the paper — only text that literally appears in the .tex.

INPUTS
- Extraction rules (schema, types, verbatim rule, step triggers, edge
  directions, self-check): scripts/opus_extract_prompt_v4.md, rendered with
  src/schema_for_prompts.py: render_prompt (it fills {{SCHEMA_BLOCK}}). Use
  /tmp/tier2_v4_rendered_prompt.md if already rendered.
- TEX SOURCE:
  /Users/yaronot/Datasets/Authomathics_data/alignment/papers/paper<NNN>/source/paper<NNN>.tex
  (read it IN FULL with the Read tool)
- Metadata (BID/TITLE/AUTHORS/YEAR): from the paper's existing tier2 JSON if
  one exists, else from the .tex preamble (\title, \author).

EXECUTION DISCIPLINE (this is what made paper005 faithful — follow it)
1. Read the ENTIRE .tex first (multiple Read calls with offsets if large).
   Never extract from memory; for well-known papers this is the #1 risk.
2. For every node, COPY the source span into `statement` verbatim — LaTeX
   preserved, only mechanical cleanup (whitespace, % comments, \label,
   \index). Keep unexpanded macros (\defeq, \dotprod, \RR, ...) exactly as
   written; do not expand them. Flag heavy macro use as an anomaly.
3. Build the JSON with a Python builder script using raw strings (r"...") and
   json.dump — do NOT hand-escape LaTeX. This guarantees backslashes / `\\`
   line-breaks round-trip exactly.
4. Apply v4.1 structural rules: type-promotion (content > environment),
   mandatory Level-2 step extraction when triggers fire, origin:"external"
   for cited prior results, compact IDs per the convention.
5. Self-verify before finishing: (a) JSON round-trips, (b) the within-paper
   graph is a DAG (run a cycle check), (c) every `statement` traces to a
   source span. Fix violations.
6. Write paper<NNN>.json, then optionally render with
   `cd src && python3 visualize_annotation.py <path>.json --html`.

OUTPUT
- The JSON file, plus the v4.1 report: node count by type, step counts per
  proof/algorithm parent, edge count by type, 3 sample node names, anomalies,
  and the confirmation line "All `statement` fields are verbatim copies of
  source spans; no paraphrasing applied."
