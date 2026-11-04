# opus-5.5__v7_cases — v7 extractions of the paper's worked examples

Extracted 2026-10-22 with exactly the frozen v7 prompt and code (prompt sha256 `86dcfbecdc4d78a5`), one Claude
Opus 5.5 agent per paper, as the silver corpus:

- `candes_tao_2005.json`: Candès & Tao, *Decoding by Linear Programming* (math/0502327), from its arXiv LaTeX
  (`portal/data/tier2_tex/paper002.tex`). 151 nodes, 170 edges; finalize 0 errors, 1 warning. Fig. 1 of the paper.
- `donoho_2006.json`: Donoho, *Compressed Sensing* (IEEE TIT 2006, not on arXiv), from a PDF-to-LaTeX conversion
  (the course repository's `paper21.tex`: no theorem environments, labels or `\ref`, so every node is a prose node
  and every edge is the agent's). 263 nodes, 241 edges; finalize 0 errors, 1 warning.
- `viazovska_2016.json`: Viazovska, *The sphere packing problem in dimension 8* (1603.04246), from its arXiv
  LaTeX (`corpus/gold_blueprints/thefundamentaltheor3m__Sphere-Packing-Lean/paper/source`), extracted
  2026-11-03 with the same prompt (code 78180fe). 263 nodes, 494 edges; finalize 0 errors, 1 warning. Talk case
  study (rules graph, grounding, blueprint comparison) in `corpus/case_studies/viazovska_2016/SUMMARY.md`.
- `huang_2019.json`: Huang, *Induced subgraphs of hypercubes and a proof of the Sensitivity Conjecture* (1907.00847),
  from its arXiv LaTeX, extracted 2026-11-03 with the same prompt. 58 nodes, 98 edges; finalize 0 errors, 1 warning.
  Talk case study in `corpus/case_studies/huang_2019/SUMMARY.md`.
- `pfr_2023.json`: Gowers, Green, Manners, Tao, *On a conjecture of Marton* (2311.05762), from its arXiv LaTeX,
  extracted 2026-11-03 with the same prompt. 250 nodes, 511 edges; finalize 0 errors, 0 warnings. Talk case study in
  `corpus/case_studies/pfr_2023/SUMMARY.md`.

The sources are kept locally in `corpus/case_studies/<id>/paper.tex` and not committed (the Donoho text is the
publisher's). Viewer pages: `python3 src/graph_view/build.py <json> -o <dir> --suffix _new --standalone`; the
paper's figures are the results view focused on the main results (`#level=results&focus=main`).
