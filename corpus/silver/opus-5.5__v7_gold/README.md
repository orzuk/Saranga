# opus-5.5__v7_gold — v7 extractions of the 146 gold-evaluation papers

The 146 papers of the author-diagram evaluation subset (`corpus/gold_candidates/eval_subset.txt`), extracted
2026-10-19 with exactly the prompt and code of the v7 silver (`prompt_opus_v7.md`, sha256 `86dcfbecdc4d78a5`,
one Claude Opus 5.5 agent per paper). The only difference from the silver is the input: each paper's source with
its dependency diagram removed (`paper_nodiag.tex`, made by `scripts/gold_candidates/strip_diagram.py`), because the
diagram is the gold. The same file is in `corpus/silver/tex_pool/<id>.tex` (and staged locally in
`corpus/silver/tex_staged/<id>/source/<id>.tex`, the layout `alg3/data.py --tex-dir` reads).

**Use as silver:** together with `opus-5.5__v7/` this is a pool of 346 papers, split in
`corpus/silver/split_v7_346.csv` (column `source`: silver or gold_author). The 200 silver papers keep their
120/40/40 split; these 146 are split 90/28/28. Train = 120 + 90 = 210, val = 40 + 28 = 68, test = 40 + 28 = 68.
A trained extractor may be scored against the author diagrams only on the 28 gold test papers (and on the
blueprints); the LLM itself is scored on all 146.

**Scores against the author diagrams** (`docs/v7_handoff/gold_eval_v7.py`, `gold_eval_v7.json`): node recall 0.973,
type precision 0.980; edge P 0.813, R 0.758, F1 0.784 [0.752, 0.812]; hierarchy-invariant F1 0.722.

**Statistics:** 47,004 nodes and 78,767 edges; median paper 285 nodes, 462 edges (about 1.7x a silver paper).
Agent time median 12.8 min, list-price cost median $4.3 per paper.

**Known issues:** 2009.05878 has 2 finishing-step errors (the parser reads `\cref{x}.(iii)` as an item label; it
was written with the assert bypassed). Proof-sketch `rigor` is inconsistent across papers, as in the silver.
