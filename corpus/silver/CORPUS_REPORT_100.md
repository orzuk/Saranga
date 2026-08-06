# opus-5 / v5.1 silver corpus — final QA report

Extraction dir: `corpus/silver/opus-5__v5.1`  
Prompt: **v5.1**, sha256 prefix `100e6cf6fdbb3aea` (frozen for all papers)

## Headline

| metric | value |
|---|---|
| papers | **200** |
| nodes | **25162** (mean 125.8/paper) |
| edges | **39839** (mean 199.2/paper) |
| edge/node ratio | mean 1.61, median 1.60 |
| mean node confidence | 0.880 |
| mean edge confidence | 0.894 |
| statement_short coverage | 78.2% |
| papers with 0 orphans | 180/200 |
| acyclic | 200/200 |

## Node types

| type | n | %% |
|---|---|---|
| `proof_step` | 7332 | 29.1% |
| `definition` | 3976 | 15.8% |
| `proof` | 2383 | 9.5% |
| `remark` | 1890 | 7.5% |
| `proposition` | 1360 | 5.4% |
| `theorem` | 1258 | 5.0% |
| `equation` | 1226 | 4.9% |
| `algorithm_step` | 1106 | 4.4% |
| `claim` | 1093 | 4.3% |
| `lemma` | 1060 | 4.2% |
| `example` | 645 | 2.6% |
| `assumption` | 429 | 1.7% |
| `corollary` | 410 | 1.6% |
| `algorithm` | 352 | 1.4% |
| `open_problem` | 293 | 1.2% |
| `problem` | 273 | 1.1% |
| `conjecture` | 73 | 0.3% |
| `exercise` | 3 | 0.0% |

## Edge types

| type | n | %% | canonical in `edge_types.py`? |
|---|---|---|---|
| `uses` | 36058 | 90.5% | yes |
| `proves` | 2401 | 6.0% | yes |
| `illustrates` | 782 | 2.0% | yes |
| `generalizes` | 202 | 0.5% | yes |
| `specializes` | 154 | 0.4% | yes |
| `solves` | 141 | 0.4% | yes |
| `resolves` | 93 | 0.2% | **NO — see E113** |
| `tests` | 8 | 0.0% | yes |

## Field coverage

| field | nodes | %% |
|---|---|---|
| `id` | 25162 | 100% |
| `type` | 25162 | 100% |
| `name` | 25162 | 100% |
| `statement` | 25162 | 100% |
| `section` | 25162 | 100% |
| `origin` | 25162 | 100% |
| `confidence` | 25162 | 100% |
| `tags` | 20305 | 81% |
| `statement_short` | 19586 | 78% |
| `parent_id` | 8461 | 34% |
| `step_order` | 8438 | 34% |
| `subclass` | 8438 | 34% |
| `conclusions` | 5146 | 20% |
| `assumptions` | 4910 | 20% |
| `definiendum` | 3789 | 15% |
| `origin_citation` | 3576 | 14% |
| `proof_strategy` | 2383 | 9% |
| `genus` | 2286 | 9% |
| `differentia` | 2161 | 9% |
| `proves` | 1236 | 5% |
| `rigor` | 726 | 3% |
| `input` | 279 | 1% |
| `output` | 269 | 1% |

## Per-category (axis = `sampled_from`; see ROADMAP 7.5.1)

| category | papers | nodes | edges | mean node conf | orphans |
|---|---|---|---|---|---|
| ? | 100 | 12345 | 18238 | 0.878 | 19 |
| cs_CC | 5 | 770 | 1326 | 0.904 | 2 |
| cs_DS | 5 | 595 | 1055 | 0.849 | 4 |
| cs_IT | 5 | 725 | 1209 | 0.865 | 0 |
| cs_LG | 5 | 475 | 813 | 0.825 | 0 |
| math_AG | 5 | 650 | 1033 | 0.899 | 1 |
| math_AP | 5 | 573 | 1008 | 0.899 | 1 |
| math_AT | 5 | 1255 | 1836 | 0.959 | 1 |
| math_CA | 5 | 546 | 987 | 0.906 | 0 |
| math_CO | 5 | 492 | 835 | 0.848 | 0 |
| math_DG | 5 | 627 | 1239 | 0.888 | 0 |
| math_FA | 5 | 561 | 933 | 0.922 | 1 |
| math_GR | 5 | 449 | 886 | 0.906 | 0 |
| math_LO | 5 | 963 | 1539 | 0.887 | 0 |
| math_NA | 5 | 392 | 750 | 0.854 | 0 |
| math_NT | 5 | 701 | 1036 | 0.890 | 0 |
| math_OC | 5 | 417 | 770 | 0.849 | 0 |
| math_PR | 5 | 669 | 1224 | 0.881 | 0 |
| math_RT | 5 | 644 | 1021 | 0.893 | 2 |
| math_ph | 5 | 484 | 883 | 0.827 | 0 |
| stat_TH | 5 | 829 | 1218 | 0.893 | 0 |

## Integrity problems

None. Every paper: valid JSON, all edge endpoints resolve, acyclic,
`model=claude-opus-5[1m]`, `prompt_version=v5.1`.

## Known limits — NOT measurable from this data

- **E120 (dropped forward-reference edges).** Nodes keep no source `\label`
  and `name` is descriptive, so `\ref{}` cannot be resolved to a node.
  Edges an agent deleted to preserve acyclicity leave no trace. Confirmed
  in 1 paper / 2 edges only because that agent reported it; true rate unknown.
- **`rigor` (E130).** Declared universal in `node_types.py`, requested nowhere
  in the prompt; present on ~5% of nodes in 6 papers. Excluded from all
  cross-paper statistics above.
- **`confidence` is within-paper only.** No shared rubric anchor across papers
  (E54); per-paper means range widely. Do not compare across papers.
- **Step->parent edges are inconsistent (E8).** Some papers emit them, some
  rely on `parent_id` alone, which shifts edge/node ratio by up to ~0.5.
