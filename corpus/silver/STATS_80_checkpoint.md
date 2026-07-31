# Saranga silver corpus — 80-paper checkpoint statistics

Generated before launching batch 5. Corpus: `corpus/silver/opus-5__v5.1/`

## Provenance (uniformity)

| field | value |
|---|---|
| papers | **80** |
| model | `claude-opus-5[1m]` (100%) |
| prompt | `v5.1`, frozen, sha256 prefix `100e6cf6fdbb3aea` (100%) |
| spec file | `scripts/opus_extract_prompt_v5_1_rendered.md` |
| sampling | 50/category x 20 `CORPUS_CATEGORIES`; 4 per category extracted |
| source | `corpus/silver/tex_pool/` (arXiv e-print, `\input` spliced) |

## Headline

| metric | value |
|---|---|
| nodes | **10,053** |
| edges | **17,445** (1.74 per node) |
| mean nodes/paper | 125.7 |
| **verbatim fidelity** | **99.95%** (5 flags / 10,053 nodes, all non-contiguous-span class) |
| ERROR-level QA problems | **1** (`proves`->`remark`, schema gap not extraction fault) |
| genuine orphans | **7 (0.07%)** |
| node confidence | mean 0.891, **100% coverage** |
| edge confidence | mean 0.897, **100% coverage** |
| definitions w/ genus | 1358/1660 (82%) |
| definitions w/ differentia | 1279/1660 (77%) |
| `statement_short` | 7719/10053 (77%) |
| **`rigor` populated** | **600/10053 (6.0%)** <- known gap (v6 E21) |
| origin | paper 8487 (84.4%) / external 1566 (15.6%) |

## Node types

| type | n | share |
|---|---|---|
| proof_step | 2735 | 27.2% |
| definition | 1660 | 16.5% |
| proof | 914 | 9.1% |
| remark | 859 | 8.5% |
| proposition | 543 | 5.4% |
| claim | 536 | 5.3% |
| theorem | 524 | 5.2% |
| equation | 474 | 4.7% |
| lemma | 373 | 3.7% |
| algorithm_step | 362 | 3.6% |
| example | 285 | 2.8% |
| assumption | 190 | 1.9% |
| corollary | 183 | 1.8% |
| algorithm | 160 | 1.6% |
| open_problem | 119 | 1.2% |
| problem | 112 | 1.1% |
| conjecture | 24 | 0.2% |

## Edge types

| type | n | share |
|---|---|---|
| `uses` | 15914 | 91.2% |
| `proves` | 923 | 5.3% |
| `illustrates` | 364 | 2.1% |
| `specializes` | 80 | 0.5% |
| `generalizes` | 77 | 0.4% |
| `solves` | 50 | 0.3% |
| `resolves` | 37 | 0.2% |

## Per category (4 papers each)

| category | nodes | edges | edges/node | mean node conf | defs w/ genus |
|---|---|---|---|---|---|
| cs_CC | 686 | 1213 | 1.77 | 0.912 | 103/117 |
| cs_DS | 500 | 884 | 1.77 | 0.849 | 41/48 |
| cs_IT | 641 | 1058 | 1.65 | 0.875 | 91/135 |
| cs_LG | 424 | 722 | 1.70 | 0.859 | 35/41 |
| math_AG | 445 | 755 | 1.70 | 0.893 | 40/55 |
| math_AP | 502 | 888 | 1.77 | 0.902 | 51/82 |
| math_AT | 713 | 1143 | 1.60 | 0.964 | 97/104 |
| math_CA | 416 | 771 | 1.85 | 0.907 | 71/92 |
| math_CO | 351 | 630 | 1.79 | 0.875 | 91/93 |
| math_DG | 556 | 1124 | 2.02 | 0.883 | 119/132 |
| math_FA | 422 | 795 | 1.88 | 0.919 | 66/77 |
| math_GR | 383 | 740 | 1.93 | 0.892 | 86/88 |
| math_LO | 811 | 1278 | 1.58 | 0.916 | 94/98 |
| math_NA | 300 | 577 | 1.92 | 0.858 | 51/70 |
| math_NT | 599 | 887 | 1.48 | 0.892 | 58/79 |
| math_OC | 349 | 633 | 1.81 | 0.850 | 44/61 |
| math_PR | 511 | 990 | 1.94 | 0.899 | 48/64 |
| math_RT | 433 | 702 | 1.62 | 0.906 | 81/92 |
| math_ph | 390 | 720 | 1.85 | 0.798 | 38/57 |
| stat_TH | 621 | 935 | 1.51 | 0.886 | 53/75 |

## Caveats (do not misread these numbers)

1. **`confidence` is NOT comparable across papers.** The step-segmentation rubric is
   undefined (v6 E54: per-paper mean `proof_step` confidence ranges 0.65-1.00), and
   there is no band for announced display equations (E45). Valid *within* a paper only.
2. **`rigor` is 6% populated** — a documented universal field the prompt omitted (E21).
3. **`category` is the sampling bucket**, which may differ from the paper's true arXiv
   primary category for cross-listed papers (E32). Fix via arXiv API before per-subfield claims.
4. **Nested statements**: ~1.8% of characters appear in two nodes (proof contains equation/
   definition/nested proof). Accepted; de-duplicate at evaluation time (B1).
5. **Edge counts not strictly comparable**: step->parent edges are emitted by some papers
   and not others (E8). Normalise post-hoc via `parent_id` before edge-density comparisons.

Full issue register: `scripts/opus_extract_prompt_v6_TODO.md`
