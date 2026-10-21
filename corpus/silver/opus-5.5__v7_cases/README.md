# opus-5.5__v7_cases — v7 extractions of the paper's worked examples

Extracted 2026-10-22 with exactly the frozen v7 prompt and code (prompt sha256 `86dcfbecdc4d78a5`), one Claude
Opus 5.5 agent per paper, as the silver corpus:

- `candes_tao_2005.json`: Candès & Tao, *Decoding by Linear Programming* (math/0502327), from its arXiv LaTeX
  (`portal/data/tier2_tex/paper002.tex`). 151 nodes, 170 edges; finalize 0 errors, 1 warning. Fig. 1 of the paper.
- `donoho_2006.json`: Donoho, *Compressed Sensing* (IEEE TIT 2006, not on arXiv), from a PDF-to-LaTeX conversion
  (the course repository's `paper21.tex`: no theorem environments, labels or `\ref`, so every node is a prose node
  and every edge is the agent's). 263 nodes, 241 edges; finalize 0 errors, 1 warning.

The sources are kept locally in `corpus/case_studies/<id>/paper.tex` and not committed (the Donoho text is the
publisher's). Viewer pages: `python3 src/graph_view/build.py <json> -o <dir> --suffix _new --standalone`; the
paper's figures are the results view focused on the main results (`#level=results&focus=main`).
