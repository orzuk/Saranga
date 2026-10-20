# opus-5.5__v7_bpsource — v7 extractions of the blueprints' source papers

For the blueprints formalising an arXiv paper whose LaTeX is available (17 of 19), the paper itself
(`corpus/gold_blueprints/<id>/paper/source/<main>.tex`), extracted 2026-10-20 with exactly the prompt and code of the
v7 silver (one Claude Opus 5.5 agent per paper; the agents read no blueprint file). Scored against the blueprint's
dependency graph after aligning the paper's nodes to the blueprint's (not yet done). The papers converted from PDF
(Mathpix) are to be added.

fpvandoorn__carleson: its arXiv source carries the blueprint's `\uses`/`\lean`/`\leanok`/`\proves`, so it is
extracted from `paper/source_nouses/` (those macros removed); pending.

**Statistics (16 papers):** 4,604 nodes and 7,095 edges.
