# SARANGA

Structured extraction and knowledge-graph construction from mathematical arXiv papers at scale. Extracts typed knowledge graphs (definitions, theorems, lemmas, proofs, and their dependencies) from LaTeX sources using pattern-based (regex) and LLM-based extraction, then evaluates and distills LLM extraction intelligence into deterministic rules via the NtRED pipeline.

---

## Quick start

```bash
git clone <REPO_URL_REDACTED_FOR_REVIEW>
cd SARANGA

pip install -r src/LLMVersion/requirements.txt

# Optional: set API keys for LLM extraction
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
export HF_TOKEN="your-token"
```

### Parse a paper (manual mode, no API cost)

```bash
python src/run_pipeline.py \
    --operations parse \
    --regex-id '^2501\.00685' \
    --extraction-mode manual \
    --out-dir ./out_example
```

### Parse with LLM extraction

```bash
python src/run_pipeline.py \
    --operations parse \
    --regex-id '^2501\.00685' \
    --extraction-mode llm \
    --llm-provider anthropic \
    --llm-model claude-sonnet-4-20250514 \
    --structure-types "definition,theorem,lemma" \
    --out-dir ./out_example
```

---

## Project structure

```
SARANGA/
├── README.md                          # This file
├── src/
│   ├── run_pipeline.py                # Unified pipeline orchestrator
│   ├── config.py                      # Platform-auto-detected paths
│   ├── node_types.py                  # Canonical node type definitions
│   ├── edge_types.py                  # Canonical edge type definitions
│   ├── schema_for_prompts.py          # Schema utilities for prompt generation
│   │
│   └── LLMVersion/                    # ★ Core extraction engine (NtRED)
│       ├── math_paper_parser.py       # Heuristic + LLM parser (16 structure types)
│       ├── math_classes.py            # Data model (PaperGraph, TheoremLike, etc.)
│       ├── parse_batch.py             # Batch extraction orchestrator
│       ├── distillation_analysis.py   # NtRED distillation loop
│       ├── prompt_optimizer.py        # Iterative prompt optimization
│       ├── evaluate_definitions.py    # Jaccard-based P/R/F1 evaluation
│       ├── add_gold_standard.py       # Gold standard merging
│       ├── definitions_from_json_to_csv.py  # JSON→CSV conversion
│       ├── extract_arxiv_funcs.py     # arXiv download helpers
│       ├── prompts/                   # Per-type LLM prompt templates
│       ├── Gold_Standard_*.csv        # Per-type gold annotations (10 papers)
│       ├── *_eval/                    # Per-type evaluation results + distilled rules
│       ├── evaluation_pipeline.sh     # Multi-provider evaluation harness
│       ├── distill.sh                 # Full distillation pipeline
│       ├── extraction.sh              # Extraction + evaluation
│       ├── optimize.sh                # Prompt optimization
│       └── viz_*.py                   # Visualization scripts
│
└── tables/                            # Generated paper tables
```

---

## Core pipeline

### Unified orchestrator (`src/run_pipeline.py`)

| Operation | What it does |
|---|---|
| `parse` | Run extraction engine (manual regex / LLM / both) → unified JSON |
| `validate` | DAG acyclicity + schema check |
| `visualize` | Render PNG + interactive HTML knowledge graphs |
| `evaluate` | Precision / recall / F1 vs gold standard |

### Supported structure types

16 types organized as:
- **Theorem-like** (8): theorem, lemma, proposition, corollary, claim, conjecture, problem, open_problem
- **Simple environments** (5): definition, assumption, example, exercise, remark
- **Others**: proof, algorithm, table
- **Orphan equations**: display math outside named environments (manual regex only)

### Extraction modes

| Mode | Description |
|---|---|
| `manual` | Pattern-based regex extraction (default, no API cost) |
| `llm` | LLM API extraction only |
| `both` | Combines both methods for best coverage |

### LLM providers

| Provider | Model |
|---|---|
| Anthropic | claude-sonnet-4-20250514 |
| OpenAI | gpt-4o |
| HuggingFace | Qwen/Qwen2.5-7B-Instruct |

---

## NtRED: Neural-to-Rule Ensemble Distillation

The novel contribution of this work. NtRED distills LLM extraction intelligence into deterministic regex rules — crossing the representational boundary from neural to non-neural student.

### Pipeline

1. **Extract**: 3 LLM providers + manual baseline extract math structures from LaTeX
2. **Evaluate**: Jaccard similarity → P/R/F1 per provider against gold standard
3. **Dark knowledge**: identify structures that LLMs catch but regex misses
4. **Analyze**: LLM-powered pattern mining on missed structures
5. **Aggregate**: meta-LLM consolidates suggestions into `distilled_rules.py`
6. **Validate**: re-run parser with new rules, verify improvement
7. **Iterate**: repeat until F1 plateaus

### Usage

```bash
# Full distillation pipeline for one structure type
bash src/LLMVersion/distill.sh definition

# Or step by step — see src/LLMVersion/README.md for details
```

---

## Evaluation

Evaluation compares extracted structures against gold standard using Jaccard similarity.

```bash
# Run evaluation for all providers
bash src/LLMVersion/extraction.sh definition

# Visualize results
python src/LLMVersion/viz_eval_comparison.py --eval-dir src/LLMVersion/definition_eval
```

Results for 9 structure types across 10 gold-standard papers are in `src/LLMVersion/*_eval/evaluation_results.csv`.

---

## See also

- [`src/LLMVersion/README.md`](src/LLMVersion/README.md) — detailed extraction engine docs (prompts, optimization, distillation)
