# corpus/orzuk — the arXiv papers of Or Zuk as a small SARANGA corpus

All arXiv papers with Or Zuk as an author (query to the arXiv API on 2026-11-05: `au:Zuk_O` and
`au:"Or Zuk"`, keeping the entries whose author list has "Or Zuk" literally; one entry, cs/0507060, lists
"O. Zuk" with the same co-authors and topic as cs/0510005 and is kept but flagged). Each paper's LaTeX
source was fetched from `arxiv.org/e-print/<id>`, flattened to one file, run through the alg3 rules
extractor (silver_v7 sentence tagger + all-pairs edge model), and rendered as a standalone graph page.
The frozen v7 LLM extraction prompt is rendered per paper for a later extraction run.

19 of 23 papers have LaTeX source; the rest were submitted as PDF only and have no extraction.

## Papers

| arXiv id | date | primary | title | source | paper.tex | thm-like envs | rules nodes / edges (thm-like) |
|---|---|---|---|---|---|---|---|
| [cs/0507060](https://arxiv.org/abs/cs/0507060) | 2005-07-23 | cs.IT | The Entropy of a Binary Hidden Markov Process (listed as "O. Zuk" — attribution to check) | tar.gz, 125 KB, 6 files | 39 KB | 0 | 96 / 44 (8) |
| [cs/0510005](https://arxiv.org/abs/cs/0510005) | 2005-10-03 | cs.IT | Taylor series expansions for the entropy rate of Hidden Markov Processes | tar.gz, 26 KB, 4 files | 50 KB | 7 | 106 / 113 (9) |
| [cs/0510016](https://arxiv.org/abs/cs/0510016) | 2005-10-06 | cs.IT | From finite-system entropy to entropy rate for a Hidden Markov Process | gzipped-tex, 14 KB, 1 file | 40 KB | 4 | 56 / 54 (4) |
| [q-bio/0511022](https://arxiv.org/abs/q-bio/0511022) | 2005-11-15 | q-bio.MN | The promoters of human cell cycle genes integrate signals from two tumor suppressive pathways during cellular transformation | **no source (PDF only)** | — | — | — |
| [0811.1289](https://arxiv.org/abs/0811.1289) | 2008-11-08 | q-bio.MN | Wide-Scale Analysis of Human Functional Transcription Factor Binding Reveals a Strong Bias towards the Transcription Start Site | **no source (PDF only)** | — | — | — |
| [0909.0400](https://arxiv.org/abs/0909.0400) | 2009-09-02 | q-bio.GN | Rare-Allele Detection Using Compressed Se(que)nsing | tar.gz, 763 KB, 28 files | 76 KB | 0 | 44 / 47 (3) |
| [0909.3704](https://arxiv.org/abs/0909.3704) | 2009-09-21 | stat.ME | FDR control with adaptive procedures and FDR monotonicity | tar.gz, 731 KB, 9 files | 83 KB | 3 | 58 / 65 (10) |
| [1007.3424](https://arxiv.org/abs/1007.3424) | 2010-07-20 | q-bio.GN | Bacterial Community Reconstruction Using A Single Sequencing Reaction | tar.gz, 748 KB, 15 files | 75 KB | 0 | 29 / 25 (0) |
| [1206.5280](https://arxiv.org/abs/1206.5280) | 2012-06-20 | cs.AI | Ranking Under Uncertainty | **no source (PDF only)** | — | — | — |
| [1206.6862](https://arxiv.org/abs/1206.6862) | 2012-06-27 | cs.LG | On the Number of Samples Needed to Learn the Correct Structure of a Bayesian Network | **no source (PDF only)** | — | — | — |
| [1309.6919](https://arxiv.org/abs/1309.6919) | 2013-09-26 | cs.CE | Accurate Profiling of Microbial Communities from Massively Parallel Sequencing using Convex Optimization | tar.gz, 200 KB, 7 files | 53 KB | 4 | 52 / 100 (5) |
| [1505.06292](https://arxiv.org/abs/1505.06292) | 2015-05-23 | cs.LG | Low-Rank Matrix Recovery from Row-and-Column Affine Measurements | tar.gz, 463 KB, 31 files | 79 KB | 1 | 130 / 143 (18) |
| [1510.05214](https://arxiv.org/abs/1510.05214) | 2015-10-18 | cs.LG | Clustering Noisy Signals with Structured Sparsity Using Time-Frequency Representation | tar.gz, 696 KB, 17 files | 44 KB | 0 | 43 / 44 (1) |
| [1707.00314](https://arxiv.org/abs/1707.00314) | 2017-07-02 | math.ST | On The Asymptotic Efficiency of Selection Procedures for Independent Gaussian Populations | tar.gz, 435 KB, 8 files | 84 KB | 14 | 172 / 117 (34) |
| [1912.05769](https://arxiv.org/abs/1912.05769) | 2019-12-12 | stat.ME | Testing Independence under Biased Sampling | tar.gz, 1780 KB, 42 files | 137 KB | 8 | 100 / 145 (11) |
| [2112.15534](https://arxiv.org/abs/2112.15534) | 2021-12-31 | math.PR | A phase transition for the probability of being a maximum among random vectors with general iid coordinates | tar.gz, 297 KB, 8 files | 41 KB | 4 | 102 / 70 (10) |
| [2209.00346](https://arxiv.org/abs/2209.00346) | 2022-09-01 | math.PR | A correlation inequality for random points in a hypercube with some implications | tar.gz, 21 KB, 5 files | 52 KB | 7 | 115 / 72 (13) |
| [2305.18136](https://arxiv.org/abs/2305.18136) | 2023-05-29 | q-fin.MF | Exponential Utility Maximization in a Discrete Time Gaussian Framework | tar.gz, 2508 KB, 6 files | 31 KB | 2 | 54 / 44 (3) |
| [2308.10550](https://arxiv.org/abs/2308.10550) | 2023-08-21 | q-fin.MF | Explicit Computations for Delayed Semistatic Hedging | tar.gz, 2697 KB, 11 files | 73 KB | 9 | 155 / 173 (17) |
| [2601.18662](https://arxiv.org/abs/2601.18662) | 2026-01-26 | math.OC | A Unique Inverse Decomposition of Positive Definite Matrices under Linear Constraints | tar.gz, 165 KB, 9 files | 100 KB | 9 | 189 / 217 (17) |
| [2603.10215](https://arxiv.org/abs/2603.10215) | 2026-03-10 | q-bio.PE | SDSR: A Spectral Divide-and-Conquer Approach for Species Tree Reconstruction | tar.gz, 2108 KB, 20 files | 129 KB | 20 | 189 / 285 (26) |
| [2605.08777](https://arxiv.org/abs/2605.08777) | 2026-05-09 | stat.ML | Measuring and Decomposing Mode Separation via the Canonical Diffusion | tar.gz, 16202 KB, 27 files | 198 KB | 14 | 136 / 85 (15) |
| [2605.09439](https://arxiv.org/abs/2605.09439) | 2026-05-10 | cs.LG | Inverse Design for Conditional Distribution Matching | tar.gz, 18203 KB, 67 files | 209 KB | 4 | 113 / 76 (4) |

Authors per paper are in `papers.csv` (arxiv_id, date, primary, title, authors, has_tex).

"thm-like envs" counts `\begin{theorem|lemma|proposition|corollary|claim|conjecture}` (and `\newtheorem`
aliases of those) in the flattened source, outside comments; "rules nodes" is the full node count of the
rules graph (every type, proof steps included), with the theorem-like nodes in parentheses.

## Layout

```
corpus/orzuk/
  README.md, index.html, papers.csv
  <id>/                      arXiv id with '.' and '/' replaced by '_' (cs/0507060 -> cs_0507060)
    arxiv_src/               the e-print as fetched (<id>.tar.gz or <id>.tex) and its extracted tree
    paper.tex                the main .tex with every \input/\include inlined (marked %% [inlined ...])
    <id>_rules.json          alg3 rules extraction (unified JSON)
    <id>_rules_new.html      standalone graph page of the rules extraction
    prompt_v7.md             rendered frozen v7 extraction prompt (version v7-86dcfbecdc4d78a5-f0f2ca3)
    <id>.json, <id>_new.html the LLM extraction and its page: not built yet (index.html links to them)
```

## How it was built

```bash
# 1. rules extraction, one run per paper from a one-file folder (tex-dir mode processes one file per run)
mkdir -p $SCRATCH/orzuk_rules/<id> && cp corpus/orzuk/<id>/paper.tex $SCRATCH/orzuk_rules/<id>/<id>.tex
PYTHONPATH=src python3 src/LLMVersion/parse_batch.py --tex-dir $SCRATCH/orzuk_rules/<id> \
  --out-dir $SCRATCH/orzuk_rules/out --extraction-mode rules \
  --rules-dir extractors/rules/silver_v7__sentence_tagger__2026-10 \
  --edge-model extractors/edges/silver_v7__edges_allpairs__2026-10 --top-k 0
cp $SCRATCH/orzuk_rules/out/json/<id>_rules.json corpus/orzuk/<id>/
# 2. the page
python3 src/graph_view/build.py corpus/orzuk/<id>/<id>_rules.json -o corpus/orzuk/<id> \
  --suffix _new --standalone --tex corpus/orzuk/<id>/paper.tex
python3 src/graph_view/check_pages.py corpus/orzuk/*/*_rules_new.html --hash "selftest=1"
# 3. the LLM extraction (to do): run corpus/orzuk/<id>/prompt_v7.md with an extraction agent; it writes
#    corpus/orzuk/<id>/<id>.json, then build the page as in 2 without --suffix
```

The prompt was rendered as in `scripts/render_v6_prompt.py` (`--prompt v7`), with TEX_SOURCE pointing at the
original main .tex inside `arxiv_src/` (the prompt's tooling inlines `\input` itself).

## LLM graphs (frozen v7 prompt, Claude Opus 5.5 agent, 2026-11-05)

All 19 extractions finished with 0 finalize errors. Each folder holds `<id>.json`, its page `<id>_new.html`, the build script `scripts/build.py`, and `AGENT_NOTES.md`: the extracting agent's notes and its list of possible errors in the paper, for the author to judge.

| id | title | nodes (Level-1) | edges | external | rules nodes/edges | flagged points |
|---|---|---|---|---|---|---|
| 0909_0400 | Rare-Allele Detection Using Compressed Se(que)nsing | 107 (97) | 209 | 15 | 44/47 | 0 |
| 0909_3704 | FDR control with adaptive procedures and FDR monotonicity | 118 (109) | 239 | 35 | 58/65 | 9 |
| 1007_3424 | Bacterial Community Reconstruction Using A Single Sequencing | 105 (88) | 144 | 8 | 29/25 | 10 |
| 1309_6919 | Accurate Profiling of Microbial Communities from Massively P | 89 (66) | 148 | 7 | 52/100 | 10 |
| 1505_06292 | Low-Rank Matrix Recovery from Row-and-Column Affine Measurem | 210 (161) | 299 | 32 | 130/143 | 11 |
| 1510_05214 | Clustering Noisy Signals with Structured Sparsity Using Time | 94 (75) | 112 | 34 | 43/44 | 7 |
| 1707_00314 | On The Asymptotic Efficiency of Selection Procedures for Ind | 279 (188) | 360 | 31 | 172/117 | 9 |
| 1912_05769 | Testing Independence under Biased Sampling | 175 (119) | 198 | 3 | 100/145 | 11 |
| 2112_15534 | A phase transition for the probability of being a maximum am | 141 (115) | 198 | 11 | 102/70 | 5 |
| 2209_00346 | A correlation inequality for random points in a hypercube wi | 183 (125) | 191 | 16 | 115/72 | 11 |
| 2305_18136 | Exponential Utility Maximization in a Discrete Time Gaussian | 88 (55) | 183 | 2 | 54/44 | 7 |
| 2308_10550 | Explicit Computations for Delayed Semistatic Hedging | 263 (149) | 353 | 3 | 155/173 | 6 |
| 2601_18662 | A Unique Inverse Decomposition of Positive Definite Matrices | 283 (168) | 447 | 6 | 189/217 | 8 |
| 2603_10215 | SDSR: A Spectral Divide-and-Conquer Approach for Species Tre | 320 (185) | 404 | 31 | 189/285 | 9 |
| 2605_08777 | Measuring and Decomposing Mode Separation via the Canonical  | 229 (128) | 323 | 16 | 136/85 | 10 |
| 2605_09439 | Inverse Design for Conditional Distribution Matching | 160 (91) | 269 | 16 | 113/76 | 9 |
| cs_0507060 | The Entropy of a Binary Hidden Markov Process | 113 (100) | 165 | 36 | 96/44 | 6 |
| cs_0510005 | Taylor series expansions for the entropy rate of Hidden Mark | 126 (87) | 194 | 16 | 106/113 | 9 |
| cs_0510016 | From finite-system entropy to entropy rate for a Hidden Mark | 69 (49) | 128 | 10 | 56/54 | 9 |

Totals: 3152 nodes, 4564 edges over 19 papers; 156 flagged points.
