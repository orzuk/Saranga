# AI-assisted mathematics: candidate papers

Two lists, different confidence. Neither has been read; `assistance_level` in
`candidates.csv` is coded from secondary sources (OpenAI's own report and press),
not from the papers.

## `candidates.csv` — 15 papers, high confidence that AI was involved

Sourced from OpenAI's *Early science acceleration experiments with GPT-5*
(13 case studies over 4 parts; Part IV is the 4 genuinely NEW results) plus
targeted search. Every arXiv id resolved against the arXiv API — titles,
primary categories and dates are confirmed, the assistance coding is not.

Assistance levels (from `AI_generated_math_Results.md`):

    L0  tool use only (numerics, symbolic manipulation)
    L1  suggested a technique or reference
    L2  proved a lemma or key step
    L3  proved the main result; humans wrote it up
    L4  autonomous / formally verified

Current split: L0 2, L1 2, L2 3, L3 4, L4 4. **For "AI proved the result, humans
may have rewritten it", the target is L3+L4 — currently 8 papers.**

## `arxiv_pool.csv` — 117 broader candidates, unverified

Every arXiv paper in `math.*` (excluding `math.HO`, which is expository), 2025-26,
whose **title, abstract or comments** mention GPT-5 / ChatGPT / AlphaProof /
AlphaEvolve / Aristotle / "AI-assisted" / "large language model". Harvested from
350 raw hits.

**Mentioning an AI is not the same as AI having proved something.** This pool
still contains capability studies ("Can ChatGPT implement finite element
models…"), papers improving *on* an AI result rather than *with* one
("improvement over AlphaEvolve"), and incidental mentions. Each needs reading.

## The gap this does NOT cover

arXiv's API searches title/abstract/comments — **not full text**. A paper that
credits the model only in its acknowledgements is invisible here, and that is the
normal place to put it. The size of that hidden population is unknown and may
exceed the visible one.

Closing it needs a full-text harvester: download the `.tex` (our pipeline already
does this), grep the acknowledgements for model names and assistance phrases.
That is the one remaining way to turn this from a case-study list into a
population.
