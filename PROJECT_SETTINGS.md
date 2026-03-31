# Authomathics - Project Settings & Configuration

## Overview

Authomathics is a Python system for downloading and parsing arXiv papers,
extracting mathematical objects (theorems, definitions, proofs, equations,
algorithms, tables), building knowledge graphs of their relationships, and
optionally grounding concepts to external registries (Wikidata, ProofWiki).

---

## Python Version

- Python 3.6+

## Dependencies

### Core (rule-based pipeline)

| Package      | Purpose                                |
|--------------|----------------------------------------|
| requests     | HTTP client (arXiv API, Wikidata)      |
| h5py         | HDF5 metadata index                   |
| pandas       | Tabular data processing                |
| networkx     | Graph data structures                  |
| matplotlib   | Static graph visualization             |
| pyvis        | Interactive HTML graph visualization   |
| tables       | PyTables backend for HDF5              |

### LLM pipeline (src/LLMVersion)

| Package      | Purpose                                |
|--------------|----------------------------------------|
| anthropic    | Anthropic Claude API client            |
| openai       | OpenAI GPT API client                  |
| huggingface_hub | HuggingFace model API (optional)   |

### Standard library (no install needed)

`os`, `sys`, `re`, `json`, `pathlib`, `argparse`, `tarfile`, `tempfile`,
`datetime`, `dataclasses`, `typing`, `csv`, `xml.etree.ElementTree`,
`collections`, `textwrap`, `urllib`

---

## Environment Variables

```bash
# Required for LLM-based definition extraction and autoformalization
ANTHROPIC_API_KEY=sk-ant-...

# Optional: for OpenAI provider in LLMVersion
OPENAI_API_KEY=sk-proj-...

# Optional: for HuggingFace provider in LLMVersion
HF_TOKEN=hf_...
```

---

## Platform-Specific Path Configuration (src/config.py)

Paths are auto-detected in this priority order:

| Priority | Platform   | DATA_DIR                                         | CODE_DIR                                        |
|----------|------------|--------------------------------------------------|-------------------------------------------------|
| 1        | Cluster    | `/sci/labs/orzuk/orzuk/projects/Authomathics`    | `/sci/labs/orzuk/orzuk/github/Authomathics`     |
| 2        | WSL        | `/mnt/c/Datasets/Authomathics_data`              | `/mnt/c/Code/Github/Authomathics`               |
| 3        | Windows    | `C:/Datasets/Authomathics_data`                  | `C:/Code/Github/Authomathics`                   |
| 4        | Fallback   | `~/Datasets/Authomathics_data`                   | `~/Code/Authomathics`                           |

### Derived Paths (relative to DATA_DIR)

| Variable              | Path                                              | Content                        |
|-----------------------|---------------------------------------------------|--------------------------------|
| `ARXIV_DIR`           | `DATA_DIR/arxiv`                                  | All arXiv data                 |
| `PROOFWIKI_DIR`       | `DATA_DIR/proofwiki`                              | ProofWiki corpus               |
| `WIKIDATA_DIR`        | `DATA_DIR/wikidata`                               | Wikidata concept registry      |
| `FULL_PAPERS_DIR`     | `ARXIV_DIR/full_papers`                           | Cached LaTeX source archives   |
| `ARXIV_META_DATA`     | `ARXIV_DIR/arxiv-metadata-oai-snapshot.json`      | Full NDJSON metadata dump      |
| `ARXIV_META_DATA_HDF5`| `ARXIV_DIR/arxiv-metadata-oai-snapshot-compact.h5`| Fast HDF5 index                |
| `ARXIV_IDS_FILE`      | `ARXIV_DIR/arxiv_ids_all_min_max.json`            | Cached ID listing              |
| `PROOFWIKI_CORPUS`    | `PROOFWIKI_DIR/proofwiki_corpus.json`             | Scraped ProofWiki content      |
| `WIKIDATA_REGISTRY`   | `WIKIDATA_DIR/concept_registry.json`              | Concept registry for grounding |

---

## API Endpoints

| Service       | URL                                     | Usage                          |
|---------------|----------------------------------------|--------------------------------|
| arXiv API     | `http://export.arxiv.org/api/query`     | Metadata queries (fallback)    |
| arXiv PDF     | `https://arxiv.org/pdf/{id}.pdf`        | PDF download                   |
| arXiv source  | `https://arxiv.org/e-print/{id}`        | LaTeX tarball download         |
| arXiv HTML    | `https://arxiv.org/abs/{id}`            | Abstract page                  |
| Wikidata      | `https://www.wikidata.org/w/api.php`    | Entity search                  |
| Wikidata SPARQL| `https://query.wikidata.org/sparql`    | SPARQL queries                 |
| ProofWiki     | `https://proofwiki.org/w/api.php`       | Content scraping               |

---

## Runtime Options

### Global (config.py)

| Variable       | Default | Meaning                                              |
|---------------|---------|------------------------------------------------------|
| `LOCAL_FIRST` | `True`  | Try local data/metadata before querying arXiv remote  |

### PaperParser Constructor (math_paper_parser.py)

| Parameter               | Default         | Meaning                                           |
|------------------------|-----------------|---------------------------------------------------|
| `paper_id`             | `None`          | Identifier attached to all extracted objects       |
| `definition_mode`      | `"manual"`      | `"manual"`, `"llm"`, or `"both"`                  |
| `llm_model`            | `"gpt-4o-mini"` | LLM model name (when mode includes llm)           |
| `llm_chunk_chars`      | `8000`          | Chunk size for LLM definition extraction           |
| `extract_inline_let`   | `True`          | Extract inline "Let X be ..." definitions          |
| `concept_registry_path`| `None`          | Path to Wikidata registry JSON for grounding       |
| `enable_grounding`     | `False`         | Enable concept grounding to Wikidata               |
| `grounding_min_term_len`| `4`            | Minimum term length for concept matching           |

### Batch Runner CLI (run_parse_papers.py)

| Flag             | Type    | Default          | Meaning                            |
|------------------|---------|------------------|------------------------------------|
| `--start`        | str     | None             | Start date YYYY-MM-DD              |
| `--end`          | str     | None             | End date YYYY-MM-DD                |
| `--days`         | int     | None             | Last N days (alternative to dates) |
| `--category`     | str     | None             | arXiv category (e.g. `math.PR`)    |
| `--regex-id`     | str     | None             | Regex filter on paper IDs          |
| `--top-k`        | int     | 20               | Max papers to process              |
| `--out-dir`      | Path    | `FULL_PAPERS_DIR`| Output root                        |
| `--draw-graphs`  | flag    | False            | Generate PNG graph visualizations  |
| `--verbose`      | flag    | False            | Debug logging                      |

### LLM Version Additional CLI Flags

| Flag              | Type   | Default    | Meaning                            |
|-------------------|--------|------------|------------------------------------|
| `--definition-mode`| str   | `"manual"` | `manual`, `llm`, or `both`         |
| `--llm-provider`  | str    | `"anthropic"`| `anthropic`, `openai`, `huggingface`|
| `--llm-model`     | str    | varies     | Model name per provider             |
| `--prompt-file`   | Path   | None       | Custom prompt template              |

---

## Output Formats

### Parsed Paper JSON

Written to `{out_dir}/YYYY/MM/DD/json/{arxiv_id}.json`:

```
{
  "paper_id": "...",
  "objects": { "T1": {...}, "D1": {...}, "P1": {...}, "E1": {...}, ... },
  "relations": [ {"source_id": "...", "target_id": "...", "relation_type": "...", ...}, ... ]
}
```

### Graph PNG

Written to `{out_dir}/YYYY/MM/DD/png/{arxiv_id}.png` (when `--draw-graphs`).

### Status Log CSV

Written to `{out_dir}/status_log.csv`:

```
arxiv_id, status, message
2301.00543, OK,
2301.00544, FETCH_ERROR, "timeout"
```

---

## Supported arXiv Categories (examples)

`math.PR` (Probability), `math.DG` (Differential Geometry), `math.AG`
(Algebraic Geometry), `math.CO` (Combinatorics), `math.AP` (Analysis of PDEs),
`stat.ML` (Machine Learning), `cs.LG` (Learning), `math-ph` (Math Physics),
and all other valid arXiv categories.

---

## Gold Standard Evaluation (LLMVersion)

| File                    | Purpose                             |
|-------------------------|-------------------------------------|
| `Gold_Standard.csv`     | Manually annotated definitions      |
| `definitions.csv`       | Extracted definitions for eval      |
| `MergedGoldAndDef.csv`  | Merged gold + extracted             |
| `evaluation_results.csv`| Precision, Recall, F1 per paper     |
| `detailed_matches.csv`  | Per-definition match details        |

Evaluation threshold: Jaccard similarity >= 0.7 (configurable).
