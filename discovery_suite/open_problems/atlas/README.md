# Atlas of open problems and their resolutions (pilot on the 100K v7 corpus, 2026-10-23)

Problems stated in arXiv papers, where they were posed, which later papers settle them, and how long they stayed
open; checked against the Kourovka Notebook and against lists of problems claimed solved by AI.

Outputs live on the cluster in `/sci/labs/orzuk/orzuk/projects/Authomathics/theoremgraph/saranga_gold/`
(`atlas_pilot.json`, `atlas_bib.json`, and `atlas_out/` with the judged links, the calibration set, the
AI-claim matches and `atlas_report.json`).

## Pipeline

| Step | Script | What |
|---|---|---|
| 1 | `atlas_pilot.py` (cluster, `run_atlas.sbatch`) | Over Yaron's `parsed_100k_v7` (99,988 papers): *restated* links (a conjecture / open_problem / problem node citing its source), *claim* links (a theorem-like node saying it settles a cited problem), *edge* links (`resolves` edges); cites resolved through TheoremGraph's citation table |
| 2 | `atlas_bib.py` (cluster, `run_atlas_bib.sbatch`) | Keeps open problems only (`problem` nodes whose text says they are open); resolves cite keys from the paper's own bibliography (`\bibitem`, `.bbl`, `.bib` in the source tarball) to arXiv by id or by title + first-author surname (arXiv metadata snapshot); records the bibliography year |
| 3 | `JUDGE_INSTRUCTIONS.md` | LLM pass (Claude subagents, 14 chunks of ~2,000) over the 27,805 restated + claim links: keep, status, role of the cited paper, canonical name, poser |
| 4 | `parse_kourovka.py`, `kourovka_scan.py` | The Kourovka Notebook (arXiv:1401.0300, 21st ed.): 1,758 problems, 693 with an answer (archive of solved problems) |
| 5 | `join_external.py` | Candidate matches (TF-IDF) to VibeMathed (1,284 AI-solved / claimed), OpenAI's `openai/math` release (372 families), whataifound; judged by an LLM |
| 6 | `atlas_analyze.py` | Time to resolution; stale open problems; AI-claim labels |

## Results (100K corpus)

- Links: 152,805 problem-like nodes; after the open filter 17,732 restated and 10,073 claim links. `resolves`
  edges (11,505) are dropped: in a 50-link check none was an open problem (they link a task to an algorithm).
- Citation resolution to arXiv: 6.6% through TheoremGraph, 27% (restated) / 25% (claims) with the papers' own
  bibliographies; 73% of links have a dated source. 9 of 9 checked arXiv matches were right.
- LLM pass: 13,903 of 27,805 kept. Against a blind re-judging of 420 (30 per chunk): agreement 0.86, precision
  0.93, recall 0.82; no chunk drifted (22–29 of 30); status agreement 0.90, cited-paper role 0.88.
- Time to resolution (claims that settle a problem and cite where it was posed, n = 192): median 13 years
  (IQR 4–26; answered 8, proved 16, disproved 22). Kourovka archive: median 7 (IQR 3–13, n = 608).
- Stale: 4,363 named problem groups restated as open with their source; 1,239 open 20+ years at their last
  mention and not settled by a claim in the corpus; 60 of them claimed by AI (VibeMathed / OpenAI), e.g.
  Goldfeld, Falconer distance, Hadwiger, Auslander–Reiten, Curtis, Albertson–Berman; the Erdős unit distance
  problem marked resolved.
- AI lists: 210 distinct AI-claimed problems appear in the atlas (149 VibeMathed, 61 OpenAI), 232 of the 304
  matching links stated as open in our (2010–2020) papers.

## Caveats

- The 100K is ~4% of arXiv and 20 categories, mostly papers to ~2020: a resolution is usually outside the
  corpus, so "stale" here means "open at its last mention in the sample". The real atlas needs the full-arXiv run.
- The 100K was extracted by the rules extractor (`DIST_*` ids); its `problem` type is mostly not open problems.
- Problems are grouped by a normalized name; the same problem under two names counts twice.
- AI claims are labelled, never taken as resolutions: most VibeMathed entries are unreviewed candidates and
  OpenAI's release has withdrawals (2026-10-07). Kourovka's 21st edition marks AI solutions (♯) as unsolved.
