# opus-5.5__v7_bpsource — v7 extractions of the blueprints' source papers

For the blueprints that formalise a paper or book (29), the source itself, extracted 2026-10-20 with exactly the
prompt and code of the v7 silver (one Claude Opus 5.5 agent per paper; the agents read no blueprint file), from
`corpus/gold_blueprints/<id>/paper/source/<main>.tex`:

- 17 arXiv LaTeX sources. fpvandoorn__carleson's arXiv source carries the blueprint's `\uses`/`\lean`/`\leanok`/
  `\proves` (= the gold), so it is extracted from `paper/source_nouses/` (those 697 macros removed; local copy).
- 12 PDFs (trimmed to the formalised pages) converted to LaTeX by Mathpix: `paper/source/main.tex`. Plain `article`
  LaTeX with no theorem environments, `\label` or `\ref` (results are paragraphs "Theorem 2.1. ...", proofs
  "Proof: ... \square"), so every node is a prose node and every edge is found from names; diagrams are images and
  are lost. The only edit: full-width punctuation in userAZ__compositional-protocol-proof made ASCII.
  e-values and GGPTransversalityBounds have no source.

To be scored against the blueprint's dependency graph after aligning the paper's nodes to the blueprint's (not yet
done; the Mathpix papers have no labels, so alignment is by number and text).

**Statistics (29 papers):** 9,567 nodes and 14,563 edges.
