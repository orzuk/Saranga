# AI-generated papers as SARANGA case studies

Three manuscripts from the OpenAI math release (github.com/openai/math, clone at `/mnt/c/Code/Github/math`,
pulled 2026-10-29: 751 model-written manuscripts, ~300 with a Lean formalization of the main result).
In this collection the proof, the paper text and the Lean proof are all produced by an unreleased OpenAI
model (about three hours of reasoning compute per result on average, per the release README); the
author field is "OpenAI". They are the test of whether the graph makes AI-written mathematics readable.
Chosen (2026-11-05) for an elementary statement, a formalized main result and a short source; the scan of
all 751 is `discovery_suite/ai_math/openai_math_scan_2026-11-05.csv`, the wider candidate list
`discovery_suite/ai_math/talk_candidates_2026-11.csv`.

| Case | Family | Claim | Source | Lean |
|---|---|---|---|---|
| `openai_132_sensitivity_separation/` | 132 | Boolean functions with bs(f) >= s(f)^alpha for a fixed alpha > 2: the quadratic strengthening of the Sensitivity Conjecture is false | 32 KB, 5 files | yes |
| `openai_156_borsuk_nine/` | 156 | a compact subset of R^9 that ten sets of smaller diameter cannot cover: Borsuk fails in dimension nine | 51 KB, 9 files | yes |
| `openai_165_zarankiewicz_bipartite/` | 165 | cr(K_{m,n}) = floor(m/2) floor((m-1)/2) floor(n/2) floor((n-1)/2): Zarankiewicz's conjecture | 45 KB, 7 files | yes |

Each folder: `paper.pdf` and the original multi-file source under `arxiv_src/` (not committed), the
flattened `paper.tex` (not committed), the rendered frozen v7 prompt `prompt_v7.md`, the LLM graph
`<case>.json` (Claude Opus 5.5 agent, prompt `v7-86dcfbecdc4d78a5`, `extraction_finalize` 0 errors) with
its build script under `scripts/`, the rules graph `<case>_rules.json` (alg3: v7 sentence tagger +
all-pairs edge model), the viewer pages `<case>_new.html` and `<case>_rules_new.html` (built with
`build.py --standalone --tex paper.tex`; not committed), and a `SUMMARY.md`.

Pipeline (the same as for Huang and PFR): flatten the source, `parse_batch.py --tex-dir` for the rules
graph, one Opus agent per paper following `prompt_v7.md`, `graph_view/build.py` for the pages,
`graph_score.score(rules, llm)` for the agreement. No grounding layer yet (it needs the 100K
document-frequency background; see the Huang summary).

Caveat on the results themselves: the release is unrefereed and has had withdrawals (its `history.md`).
All three main results here carry a Lean proof in the release, so they are correct as far as the Lean
statement matches the paper; the extraction agents checked the algebra of the proofs and found no failing
step, and recorded the places that rest on unstated facts (each SUMMARY).
