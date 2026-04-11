# Authomathics

Tools for downloading, parsing, and structuring mathematical knowledge from arXiv papers and textbooks. Extracts typed knowledge graphs (definitions, theorems, lemmas, proofs, and their dependencies) from LaTeX sources, links them to a foundation graph of ~298K well-known results (NaturalProofs + LeanDojo/Herald + Mathlib4), and provides validation, visualization, and evaluation tools.

The data model and unified JSON schema are documented in [`src/annotation_schema.md`](src/annotation_schema.md).

---

## Quick start

```bash
git clone https://github.com/orzuk/Authomathics
cd Authomathics

# Smoke test: parse 5 math.CO papers through the unified pipeline (no LLM cost)
./scripts/parse_smoke_test.sh

# Cluster run: 500 math.CO papers via SLURM
sbatch scripts/parse_math_co_cluster.sh
```

### Prerequisites

- Python 3.8+
- Core: `pip install requests networkx matplotlib pyvis pandas h5py tables`
- LLM extraction (optional): `pip install anthropic openai huggingface_hub`
- Environment variables (only needed for LLM extraction):
  - `ANTHROPIC_API_KEY` — Anthropic Claude
  - `OPENAI_API_KEY` — OpenAI GPT
  - `HF_TOKEN` — HuggingFace

Path configuration is auto-detected per platform by `src/config.py` (Windows, WSL, HUJI cluster, or home).

---

## The unified pipeline (`src/run_pipeline.py`)

A single orchestrator that filters arXiv papers by metadata, then runs one or more pluggable operations. Operations can be chained.

| Operation | What it does | Input → Output |
|---|---|---|
| `download` | Fetch LaTeX source / PDF / metadata from arXiv | arXiv ID → local cache |
| `parse` | Run the extraction engine (delegates to `src/LLMVersion/parse_batch.py` via subprocess — this isolates LLMVersion's module cache from the orchestrator process) | `.tex` → unified JSON |
| `validate` | DAG acyclicity + schema check | JSON → validation report CSV |
| `visualize` | Render PNG + interactive HTML knowledge graphs | JSON → PNG + HTML |
| `link` | Augment JSON with foundation-graph links (Wikidata / NaturalProofs / Mathlib) | JSON → JSON with links |
| `evaluate` | Precision / recall / F1 vs a gold standard | JSON + gold → report |
| `cross_paper` | (placeholder — Phase 3 cross-paper relationship detection) | — |

### Examples

Parse 500 math.CO papers with pattern-based (manual) extraction, no API cost:

```bash
python src/run_pipeline.py \
    --operations parse \
    --category math.CO \
    --start 2024-01-01 \
    --end 2026-04-01 \
    --top-k 500 \
    --extraction-mode manual \
    --out-dir ./out_math_co_500
```

Parse + validate + visualize a single paper with both manual and LLM extraction:

```bash
python src/run_pipeline.py \
    --operations parse,validate,visualize \
    --regex-id '^2501\.00685' \
    --extraction-mode both \
    --llm-provider anthropic \
    --llm-model claude-sonnet-4-20250514 \
    --html \
    --out-dir ./out_one_paper
```

Visualize existing JSONs (no re-extraction needed):

```bash
python src/run_pipeline.py \
    --operations visualize \
    --out-dir ./out_math_co_500 \
    --html
```

### Filter flags (shared by all operations)

| Flag | Meaning |
|---|---|
| `--category math.CO` | arXiv category |
| `--start 2024-01-01` | Earliest submission date |
| `--end 2026-04-01` | Latest submission date |
| `--days 30` | Last N days (alternative to start/end) |
| `--regex-id '^2501\.00685'` | Regex filter on base IDs |
| `--top-k 500` | Process at most N papers after filtering |

### Parse operation flags (forwarded to LLMVersion extractor)

| Flag | Default | Meaning |
|---|---|---|
| `--extraction-mode` | `manual` | `manual` / `llm` / `both` |
| `--llm-provider` | `anthropic` | `anthropic` / `openai` / `huggingface` |
| `--llm-model` | `claude-sonnet-4-20250514` | Model name |
| `--structure-types` | (all 11) | Comma-separated: `definition,theorem,lemma,proposition,corollary,claim,conjecture,problem,proof,algorithm,equation` |
| `--prompt-file` | None | Path to custom prompt template |

---

## Cluster workflow (HUJI SLURM)

Two ready-to-run shell scripts:

- [`scripts/parse_smoke_test.sh`](scripts/parse_smoke_test.sh) — quick 5-paper test, no SLURM, runs `run_pipeline.py` directly. Verifies the pipeline works end-to-end before committing to a cluster job.
- [`scripts/parse_math_co_cluster.sh`](scripts/parse_math_co_cluster.sh) — SLURM wrapper for large cluster runs (default: 500 papers, math.CO, manual mode, 8h timeout, 32 GB RAM).

Both scripts are configurable via environment variables:

```bash
# Override via env vars:
TOP_K=1000 CATEGORY=math.PR ./scripts/parse_smoke_test.sh

# Or for sbatch:
sbatch --export=TOP_K=1000,CATEGORY=math.PR scripts/parse_math_co_cluster.sh
```

---

## Core tools (`src/`)

### The unified orchestrator

| Tool | Purpose |
|---|---|
| [`src/run_pipeline.py`](src/run_pipeline.py) | **Top-level entry point.** Filter + operations dispatcher |

### Consumer tools (invoked by `run_pipeline.py`, also usable standalone)

| Tool | Purpose |
|---|---|
| `src/validate_annotation.py` | DAG acyclicity + schema validation on unified JSON |
| `src/visualize_annotation.py` | PNG and interactive HTML rendering (dagre-d3) |
| `src/link_to_foundation.py` | Link paper nodes to the 298K foundation graph |
| `src/foundation_linker.py` | OOP foundation linker (NaturalProofs + Mathlib) |
| `src/evaluate_annotation.py` | DAG/schema evaluation utilities |
| `src/evaluate_extraction.py` | Precision/recall/F1 vs gold standard (Jaccard-based) |
| `src/parsing_analysis.py` | Post-parse statistics |
| `src/paper_plot_utils.py` | Low-level graph plotting helpers |
| `src/annotation_utils.py` | JSON format conversion helpers (research ↔ student) |
| `src/extract_arxiv_data.py` | CLI wrapper for arXiv metadata/source/PDF fetch |
| `src/extract_arxiv_funcs.py` | arXiv fetch library (HDF5 index, fetch_arxiv_batch) |
| `src/concept_registry_wikidata.py` | Wikidata concept-registry CLI |
| `src/proofwiki_scraper.py` / `scrape_all_proofwiki.py` | ProofWiki corpus builder |
| `src/extract_all_chapters.py` | Batch extract all BHK textbook chapters |

### Shared data model

`src/LLMVersion/math_classes.py` is the **single source of truth** for the Python data model (`PaperGraph`, `TheoremLike`, `Definition`, `Proof`, `Equation`, `Algorithm`, `Concept`, `Relation`, …). The consumer tools above resolve it via a small `sys.path` fix-up that points at `src/LLMVersion/`.

The unified JSON schema on disk (`{metadata, nodes, edges}`) is the interface between the extraction engine and all downstream tools. See [`src/annotation_schema.md`](src/annotation_schema.md) for the full spec.

### Extraction engine (`src/LLMVersion/`)

The LLMVersion subdirectory is the active extraction engine:

- `src/LLMVersion/parse_batch.py` — core extractor; LaTeX → unified JSON
- `src/LLMVersion/math_paper_parser.py` — heuristic + LLM-based parser, 11 structure types
- `src/LLMVersion/math_classes.py` — data model (shared with src/ tools)
- `src/LLMVersion/prompts/` — per-node-type LLM prompts
- `src/LLMVersion/prompt_optimizer.py` — iterative prompt optimization against gold standards
- `src/LLMVersion/distillation_analysis.py` — "dark knowledge" distillation: things LLMs catch that regex misses
- `src/LLMVersion/Gold_Standard_*.csv` — per-node-type gold annotations across 10 arXiv papers
- `src/LLMVersion/*_eval/` — per-node-type evaluation results and detailed matches

See [`src/LLMVersion/README.md`](src/LLMVersion/README.md) for the full extraction engine docs (prompt optimization, distillation, per-type evaluation).

### Autoformalizer (`src/Autoformalizer/`)

LaTeX → Lean 4 theorem translation via the Claude API. See [`src/Autoformalizer/README.md`](src/Autoformalizer/README.md).

### Foundation graph builders (`src/structured_math/`)

Converters that populate the 298K-node foundation graph from existing databases:

- `src/structured_math/naturalproofs/convert_to_midlevel.py` — ProofWiki + Stacks Project + Trench textbook → unified JSON
- `src/structured_math/mathlib/convert_to_midlevel.py` — LeanDojo Benchmark 4 + Herald (NL translations) → unified JSON
- `src/structured_math/books/mathpix_to_thm_env.py` — Mathpix OCR post-processing + chapter splitting for PDF textbooks

---

## Standalone usage (individual tools)

### Validate annotations

```bash
python src/validate_annotation.py annotation.json                   # single file
python src/validate_annotation.py papers/gold/                      # whole directory
python src/validate_annotation.py 'papers/gold/paper*.json'         # glob pattern
```

### Visualize annotations

```bash
python src/visualize_annotation.py papers/gold/                     # PNG only
python src/visualize_annotation.py --html papers/gold/              # PNG + interactive HTML
python src/visualize_annotation.py --html-only papers/gold/         # HTML only (faster)
```

### Link to foundation knowledge

```bash
python src/link_to_foundation.py --paper-json paper1_gold.json --output paper1_linked.json
```

### Evaluate extraction quality

```bash
python src/evaluate_extraction.py --extracted output.json --gold gold.json
python src/evaluate_extraction.py --extracted output.json --gold gold.json --node-sim-threshold 0.7
python src/evaluate_extraction.py --extracted output.json --gold gold.json --flipped-edge-credit 0.5
```

**Flags:**
- `--node-sim-threshold` (default: 0.5) — minimum Jaccard similarity between node texts to count as a match
- `--flipped-edge-credit` (default: 0.5) — partial credit for edges with correct endpoints but reversed direction

### Class 52017 evaluation pipeline

```bash
cd class_52017/instructor_only

python run_evaluation.py --extractor ../cluster_package/scripts/annotate_chapter.py --doc-type both --split both
python run_evaluation.py --help

python run_all_evaluations.py \
  --extractors baseline:../cluster_package/scripts/annotate_chapter.py \
               solution:annotate_chapter_solution.py

python run_all_evaluations.py \
  --students-dir ../StudentsSolutions \
  --doc-type papers --split test
```

Student directory layout:
```
StudentsSolutions/
  john_doe_02345134/annotate_chapter_student.py
  jane_smith_98765432/annotate_chapter_student.py
```

Output: per-extractor CSVs + combined `all_results.csv` + printed leaderboard.

---

## Textbook (PDF → LaTeX)

The BHK textbook (*Foundations of Data Science*, Blum-Hopcroft-Kannan 2020) was converted from PDF to structured LaTeX using [Mathpix](https://mathpix.com/) OCR, then post-processed and split into per-chapter files:

```bash
# 1. Convert PDF to raw LaTeX via Mathpix (external service, ~$0.01/page)
#    Upload book PDF at https://mathpix.com/ → download .tex output

# 2. Post-process: add theorem environments + split into chapters
python src/structured_math/books/mathpix_to_thm_env.py \
    --split-chapters raw_mathpix_output.tex \
    -o BHK_chapters/
```

Output: per-chapter files `chapterN.tex` (with preamble), `chapterN_body.tex` (body only), `chapterN_bib.tex` (bibliographic notes).

---

## Project structure

```
Authomathics/
├── README.md                          # This file
├── PROJECT_ORGANIZATION.txt           # Detailed architecture notes
├── PROJECT_SETTINGS.md                # Configuration reference
├── .gitignore                         # Includes output/, logs/, __pycache__/
│
├── src/                               # Python source (Or Zuk)
│   ├── run_pipeline.py                # ★ Unified pipeline orchestrator
│   ├── config.py                      # Platform-auto-detected paths + endpoints
│   ├── annotation_schema.md           # Unified JSON schema spec
│   │
│   ├── extract_arxiv_data.py          # CLI for arXiv fetch
│   ├── extract_arxiv_funcs.py         # arXiv fetch library
│   │
│   ├── validate_annotation.py         # DAG + schema validator
│   ├── visualize_annotation.py        # PNG + HTML renderer
│   ├── link_to_foundation.py          # Foundation linker CLI
│   ├── foundation_linker.py           # OOP foundation linker
│   ├── evaluate_annotation.py         # Annotation evaluation helpers
│   ├── evaluate_extraction.py         # Gold-standard P/R/F1
│   ├── annotation_utils.py            # Format conversion helpers
│   ├── parsing_analysis.py            # Post-parse statistics
│   ├── paper_plot_utils.py            # Graph plotting helpers
│   │
│   ├── concept_registry_wikidata.py   # Wikidata concept registry CLI
│   ├── proofwiki_scraper.py           # ProofWiki scraper
│   ├── scrape_all_proofwiki.py        # Batch ProofWiki scrape
│   ├── extract_all_chapters.py        # BHK chapter batch extractor
│   │
│   ├── LLMVersion/                    # ★ Active extraction engine (Yaron Otmazgin)
│   │   ├── parse_batch.py        # Core extractor
│   │   ├── math_paper_parser.py       # Heuristic + LLM parser
│   │   ├── math_classes.py            # ★ Single source of truth for the data model
│   │   ├── prompt_optimizer.py        # Iterative prompt tuning
│   │   ├── distillation_analysis.py   # Dark knowledge distillation
│   │   ├── prompts/                   # Per-node-type LLM prompts
│   │   ├── Gold_Standard_*.csv        # Per-node-type gold annotations
│   │   └── *_eval/                    # Per-node-type evaluation outputs
│   │
│   ├── Autoformalizer/                # LaTeX → Lean 4 (Claude API)
│   │
│   └── structured_math/               # Foundation graph builders
│       ├── naturalproofs/             # ProofWiki + Stacks + Trench converter
│       ├── mathlib/                   # LeanDojo + Herald converter
│       └── books/                     # Mathpix PDF → LaTeX post-processing
│
├── scripts/                           # SLURM + shell scripts
│   ├── parse_smoke_test.sh            # ★ Quick 5-paper smoke test (no SLURM)
│   ├── parse_math_co_cluster.sh       # ★ SLURM wrapper for cluster runs
│   ├── download_one_month_arxiv_papers.sh
│   ├── download_all_arxiv_full_papers_to_slurm.sh
│   ├── fetch_arxiv_papers_metadata.sh
│   ├── list_all_arxiv_ids_locally.sh
│   ├── run_proofwiki_scrape.sh
│   └── ...                            # herald/debug helpers
│
├── class_52017/                       # Teaching infrastructure
│   ├── instructor_only/
│   │   ├── run_evaluation.py          # Single-extractor eval pipeline
│   │   ├── run_all_evaluations.py     # Batch eval + leaderboard
│   │   └── annotate_chapter_solution.py
│   └── gold_standards/                # BHK chapters 2-12 as unified JSON
│
└── gold/                              # Gold-standard arXiv papers (10)
    ├── *.json                         # Annotations
    └── tex/ / pdf/ / figures/         # Source material
```

---

## Data flow

```
arXiv API ──► fetch_arxiv_batch ──► local tex cache
                                         │
                                         ▼
                          LLMVersion/parse_batch.py
                           (manual regex / LLM / both)
                                         │
                                         ▼
                         Unified JSON  {metadata, nodes, edges}
                                         │
                 ┌──────────────┬────────┼────────┬──────────────┐
                 ▼              ▼        ▼        ▼              ▼
            validate       visualize   link   evaluate      cross_paper
                                                               (future)
```

The **unified JSON on disk** is the interface between the extraction engine and all downstream tools. Every operation in `run_pipeline.py` either produces or consumes this format.

---

## See also

- [`src/annotation_schema.md`](src/annotation_schema.md) — unified JSON schema spec
- [`src/LLMVersion/README.md`](src/LLMVersion/README.md) — extraction engine detailed docs (prompts, optimization, distillation)
- [`src/Autoformalizer/README.md`](src/Autoformalizer/README.md) — LaTeX → Lean 4 pipeline
- [`PROJECT_ORGANIZATION.txt`](PROJECT_ORGANIZATION.txt) — full architecture notes
- [`PROJECT_SETTINGS.md`](PROJECT_SETTINGS.md) — configuration reference (paths, env vars, CLI flags)
