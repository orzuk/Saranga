# SARANGA

**S**tructured **ar**Xiv **R**epresentation, **A**utomatic **N**etwork **G**eneration and **A**nalysis.

SARANGA turns mathematical papers into typed dependency graphs: the definitions, results, proofs and
assumptions a paper states, and which of them depends on which. It does so for the whole of arXiv, and
grounds the graphs in a foundation graph of concepts taken from open textbooks and ProofWiki.

| | |
|---|---|
| **Portal** (browse, or extract your own paper) | https://saranga.web.app |
| **Dataset** (bulk download) | https://huggingface.co/datasets/saranga-project/saranga |
| **Schema** | [`src/node_types.py`](src/node_types.py), [`src/edge_types.py`](src/edge_types.py), [`src/annotation_schema.md`](src/annotation_schema.md) |

## What is in it

- **A mid-level representation.** A typed DAG with 16 Level-1 node types (definition, theorem, lemma,
  proof, assumption, claim, …), optional Level-2 proof and algorithm steps, and 7 edge types
  (`uses`, `proves`, `generalizes`, …). Theorems are split into assumptions and conclusions.
- **Two extractors, two tiers.**
  - **T2, LLM extractor:** a Claude agent with a frozen prompt (v7) extracts a paper verbatim. It built
    the 200-paper *silver* corpus.
  - **T3, deterministic extractor:** the LaTeX *environment parser*, a learned *sentence tagger* for
    structures stated in prose, and a learned *edge model*. About 0.6 s of CPU per paper, no model
    calls. Learned from the LLM's output by **NERDS** (Neural Extraction Rule Distillation Scheme).
- **The whole of arXiv.** 2,648,739 papers (1991–2025) parsed with T3, 2,592,736 with a graph.
- **A foundation graph.** 30 open textbooks (389 chapters) and ProofWiki, merged into 17,023 concepts;
  49.5M grounding edges link paper nodes to them.
- **Two gold sets of author-stated dependencies.** 280 dependency diagrams drawn in arXiv papers
  (146 used for evaluation) and 104 Lean blueprints (91 scored).

## Quick start

Requirements: Python 3.10+, `pip install numpy scipy scikit-learn pandas networkx matplotlib`.
The LLM extractor additionally needs `anthropic` / `claude-agent-sdk` and an `ANTHROPIC_API_KEY`.

**Extract one paper with the released T3 extractor** (no API cost):

```bash
python3 src/LLMVersion/parse_batch.py \
    --regex-id "^2001.00001" --tex-dir <dir with the paper's .tex> --out-dir out/ \
    --extraction-mode rules \
    --rules-dir  extractors/rules/silver_v7__sentence_tagger__2026-10 \
    --edge-model extractors/edges/silver_v7__edges_allpairs__2026-10
```

The output is one unified JSON per paper (`*_rules.json`): `nodes`, `edges` and metadata. The edge model
adds edges in decreasing order of confidence and skips any that would close a cycle, so the graph is a DAG.

**View a graph** with the interactive viewer (writes an HTML page next to the JSON, or to `-o`):

```bash
python3 src/graph_view/build.py out/<paper>_rules.json --libs cdn
```

**Run the portal locally** (`http://localhost:8000`):

```bash
cd portal && python3 portal_server.py
```

## Repository layout

| Path | What it holds |
|---|---|
| `src/` | Shared library: the LaTeX layer (`latex_facts.py`, `latex_macros.py`), `extraction_finalize.py` (syntax-stated edges and validation), the schema, similarity and scoring (`graph_score.py`, `node_similarity.py`), `graph_io.py`, the viewer `graph_view/`, `run_pipeline.py` |
| `src/LLMVersion/` | The parser (`math_paper_parser.py`), `parse_batch.py`, node metrics (`node_metrics.py`, `match_modes.py`) |
| `alg3/` | NERDS: the sentence tagger (`data.py`, `features.py`, `train.py`, `runtime.py`) and the edge model (`edges.py`, `edges_all.py`); see [`alg3/README.md`](alg3/README.md) |
| `extractors/` | Released, versioned extractors, each with a `README.md` and a `recipe.json` (training papers, parameters, hashes); see [`extractors/README.md`](extractors/README.md) |
| `scripts/` | Experiment drivers: `compare_distillers.py` (the one place where extractors are scored and compared), the v7 extraction prompt (`opus_extract_prompt_v7.md`), gold-set tools (`gold_candidates/`), whole-arXiv download and grounding (`download_all_arxiv_full_papers_to_slurm.sh`, `ground_all_arxiv.sh`), portal index builders |
| `src/structured_math/books/` | The foundation graph: textbook extraction, concept merging (`concepts.py`) and the linker (`ground_papers.py`) |
| `corpus/` | The silver corpus (`silver/opus-5.5__v7`, with the train/validation/test split), the gold sets (`gold_candidates/` for author diagrams, `gold_blueprints/` for Lean blueprints), case studies |
| `portal/` | The web portal (`portal_server.py`, static pages, "Your paper" extraction with T3 or the LLM agent) |
| `textbooks/scripts/` | Downloading and preparing the open textbooks of the foundation graph |
| `prompts/` | The LLM prompts used by the code (per-type extraction, open-problem judging) |
| `deploy/` | The portal's Docker image (Cloud Run) |
| `discovery_suite/` | Cross-paper tasks: open problems and their resolutions, alignment, reuse |
| `tests/` | Regression tests (`python3 -m pytest tests`) |
| `docs/` | Design notes and changelogs |

## Reproducing the main steps

**Train the T3 extractor** on the silver corpus (CPU, minutes):

```bash
python3 alg3/data.py --tex-dir corpus/silver/tex_staged
python3 alg3/train.py --out alg3/runs/<name> --class-weight sqrt --stack --objective e2e
python3 alg3/edges_all.py train --graphs <parsed train graphs> --silver corpus/silver/opus-5.5__v7 \
    --split corpus/silver/split_v7_346.csv --tex corpus/silver/tex_staged --out alg3/runs/<edges>
```

**Score extractors** against the silver corpus, with the paper split and the headline metric
(graded one-to-one node matching, pooled F1):

```bash
python3 scripts/compare_distillers.py run --config scripts/compare_configs/<config>.json
```

**Score against the gold sets** (author diagrams and Lean blueprints):

```bash
python3 scripts/gold_candidates/score_gold.py --sets author,blueprint --extractors ta
```

**LLM extraction (T2).** The agent receives `scripts/opus_extract_prompt_v7.md`, runs the LaTeX layer,
writes and runs its own build script, and calls `extraction_finalize.finalize()` until the graph
validates. The portal's "Your paper" page runs the same extraction on your own API key
(`portal/yours_llm.py`).

**Whole arXiv.** T3 is applied on a SLURM cluster, one job per day of submissions; the graphs are
grounded with `scripts/ground_all_arxiv.sh` and bundled for the portal and the dataset with
`portal/bundle_t3.py`.

## Citation

The paper is under review. Please cite the dataset page until it appears.

## Contact

Or Zuk (or.zuk@mail.huji.ac.il), Yaron Otmazgin (yaron.otmazgin@mail.huji.ac.il).
Department of Statistics and Data Science, The Hebrew University of Jerusalem.
