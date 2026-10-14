# LLMVersion: Extraction Engine for Authomathics

This directory is the extraction engine: LaTeX → unified JSON. It produces
knowledge graphs via pattern-based (manual) extraction and/or LLM-based
extraction (Anthropic Claude, OpenAI GPT, HuggingFace).

> **User-facing entry point:** `src/run_pipeline.py` (one directory up) is
> the recommended CLI for all operations (parse, validate, visualize, link,
> evaluate, …). It internally invokes the extractor in this directory.
> The scripts here — `parse_batch.py`, `evaluation_pipeline.sh`,
> `prompt_optimizer.py`, `distillation_analysis.py` — are building blocks
> that `run_pipeline.py` composes. Invoking them directly still works for
> specialized workflows (prompt optimization, distillation analysis,
> evaluation-pipeline orchestration) but new code should prefer
> `src/run_pipeline.py` as the unified interface.

## Pipeline Usage
The extraction engine produces mathematical structures (definitions, theorems, lemmas, etc.) from LaTeX papers using HuggingFace, Anthropic, OpenAI, and manual methods, then evaluates results against a gold standard.

1) Extracts structures to JSONs for each model and manual mode.
2) Merges all extracted objects from all methods into a CSV file (e.g. `definitions.csv`).
3) Gold standard needs to be defined the same way as in `Gold_Standard.csv` — then it merges the extracted CSV with the gold standard CSV to form `MergedGoldAndDef.csv`.
4) The evaluation process compares extracted objects from each provider (HuggingFace, Anthropic, OpenAI, Manual) against gold standard using Jaccard similarity with a configurable threshold (default 0.7), calculating precision, recall, and F1 scores for each method. It outputs two CSV files: a detailed match report showing similarity scores for each individual object (`detailed_matches.csv`), and a summary report with overall performance metrics (TP/FP/FN, precision, recall, F1) per provider and paper (`evaluation_results.csv`).

### Supported Structure Types
The pipeline is parameterized by structure type. Supported types:
- `definition` (default) — mathematical definitions
- `theorem`, `lemma`, `proposition`, `corollary`, `claim` — theorem-like structures
- `conjecture`, `problem` — conjectures and problems
- `proof` — proofs
- `algorithm` — algorithms
- `table` — tables
- `equation` (orphan) — display equations not contained within any named environment (theorem, definition, proof, etc.). These are extracted via manual regex only (no LLM needed) and identified by `parent_id=None`.

Pass `--structure-types` (comma-separated) to `src/run_pipeline.py --operations parse ...` or to `parse_batch.py` directly, or `--structure-type` (single) to other scripts.

### Extraction & Evaluation

Use `extraction.sh` to run extraction and evaluation for any structure type:
```bash
bash extraction.sh definition
# options: theorem lemma proof proposition corollary claim conjecture problem definition
```

Or run manually with `evaluation_pipeline.sh`:
```bash
bash evaluation_pipeline.sh \
  --paper-id "1210.4634,1405.2464,2208.03112,1204.0109v1,1512.09272v2,2309.05826,2312.16785,2401.00367,2505.12804v1,2603.09769v1" \
  --structure-type definition \
  --gold-csv Gold_Standard_Definitions.csv \
  --prompt-file definition_optimization/optimized_prompt_definition_anthropic.txt \
  --out-dir definition_eval \
  --providers "anthropic,openai,manual"
```

Visualization:
```bash
python viz_eval_comparison.py --eval-dir definition_eval
```
Produces `eval_comparison.png` in the eval directory.

**Available pipeline arguments:**
- `--paper-id`: Comma-separated ArXiv paper IDs
- `--out-dir`: Output directory (e.g. `definition_eval`)
- `--threshold`: Evaluation threshold (default: 0.7)
- `--gold-csv`: Gold standard CSV file (e.g. `Gold_Standard_Definitions.csv`)
- `--prompt-file`: Path to optimized prompt (e.g. from prompt optimization output)
- `--structure-type`: Which structure type to extract
- `--providers`: Comma-separated providers (e.g. `"anthropic,openai,manual"`)

## Parser Info
Use the `--extraction-mode` argument to choose the extraction strategy:
- `manual` — Pattern-based extraction (default, no API key needed)
- `llm` — LLM API extraction only
- `both` — Combines both methods for best coverage

### Command Line Arguments
Shared by both `src/run_pipeline.py` (recommended) and `parse_batch.py` (direct invocation):
```
--start, --end          Date range for arXiv papers (YYYY-MM-DD format)
--days                  Alternative to start/end; fetch papers from last N days
--category, -c          Filter by arXiv category (e.g., math.PR, math.DG)
--regex-id              Filter papers by ID pattern (e.g., "^2501\\.00685")
--top-k                 Limit number of papers to process (default: 20, use <=0 for no limit)
--out-dir               Output directory (defaults to FULL_PAPERS_DIR from config.py)
--verbose               Enable detailed logging
--extraction-mode       Extraction method: manual (default), llm, or both
--llm-provider          Choose provider: anthropic, openai, or huggingface
--llm-model             Model name (default: claude-sonnet-4-20250514)
--llm-chunk-chars       Max characters per LLM chunk (default: 30000)
--prompt-file           Path to custom prompt template file (use {latex_chunk} as placeholder)
--structure-types       Comma-separated structure types to extract via LLM (default: definition)
```

`src/run_pipeline.py` also takes `--operations parse,validate,visualize,link,eval` to chain post-processing steps after extraction in a single invocation.

### Usage Examples

> **Recommended**: use `src/run_pipeline.py` with `--operations parse ...`.
> The examples below show the `parse_batch.py` form for reference and
> for users who want to invoke the extractor directly (e.g. from within
> `evaluation_pipeline.sh`, `prompt_optimizer.py`, or standalone debugging).

#### Extract definitions (default, via unified pipeline)
```bash
export ANTHROPIC_API_KEY="your-key"
python3 src/run_pipeline.py \
    --operations parse \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider anthropic \
    --llm-model claude-sonnet-4-20250514
```

#### Extract theorems via LLM
```bash
export ANTHROPIC_API_KEY="your-key"
python3 src/run_pipeline.py \
    --operations parse \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider anthropic \
    --structure-types theorem
```

#### Extract multiple structure types at once
```bash
python3 src/run_pipeline.py \
    --operations parse \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider openai \
    --llm-model gpt-4o \
    --structure-types "definition,theorem,lemma"
```

#### OpenAI
```bash
export OPENAI_API_KEY="your-key"
python3 src/run_pipeline.py \
    --operations parse \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider openai \
    --llm-model gpt-4o
```

#### HuggingFace
```bash
export HF_TOKEN="your-token"
python3 src/run_pipeline.py \
    --operations parse \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider huggingface \
    --llm-model "Qwen/Qwen2.5-7B-Instruct"
```

#### Custom Prompt Example
```bash
python3 src/run_pipeline.py \
    --operations parse \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider anthropic \
    --prompt-file my_custom_prompt.txt
```

#### Direct invocation of parse_batch.py (legacy)
The underlying extractor can still be invoked directly for specialized
workflows (e.g., inside `evaluation_pipeline.sh` or the prompt optimizer).
All flags above also work with `parse_batch.py` (just drop the
`--operations parse` and use `python3 parse_batch.py`) — but new
code should prefer the unified `src/run_pipeline.py` interface.

Example `my_custom_prompt.txt`:
```
Extract all mathematical definitions from this LaTeX text.
Return a JSON array with objects containing: name, raw_latex, clean_text, label.

LaTeX text:
{latex_chunk}

Respond ONLY with valid JSON.
```

## Prompt Templates

The `prompts/` directory contains per-type prompt templates. The prompt resolution order is:

1. `--prompt-file` (user-provided custom prompt) — overrides everything
2. `prompts/{structure_type}_prompt.txt` — per-type template file
3. Built-in default generated from `STRUCTURE_TYPE_CONFIG`

All 11 structure types have dedicated templates in `prompts/` (e.g. `definition_prompt.txt`, `theorem_prompt.txt`, `lemma_prompt.txt`, etc.). Theorem-like types use `assumptions` and `conclusions` fields.

To add a new type, create `prompts/{type}_prompt.txt` with `{latex_chunk}` placeholder. Otherwise, the built-in default prompt is generated automatically from the type's configuration.

## Post-processing

### JSON to CSV
```bash
# Extract definitions (default)
python3 definitions_from_json_to_csv.py --paper-id 2208.03112

# Extract theorems
python3 definitions_from_json_to_csv.py --paper-id 2208.03112 --structure-type theorem
```

## Prompt Optimization
The pipeline includes an iterative prompt optimization loop (`prompt_optimizer.py`). It extracts structures with the current prompt, evaluates against the gold standard, analyzes errors (FP/FN/near-misses), and feeds them to a meta-LLM to produce an improved prompt. This repeats for N iterations, keeping the best prompt by F1.

### Quick usage (recommended)

Use `optimize.sh` to run optimization for any structure type:
```bash
bash optimize.sh definition
# options: theorem lemma proof proposition corollary claim conjecture problem definition
```

### Manual usage

```bash
export ANTHROPIC_API_KEY="your-key"
python prompt_optimizer.py \
  --structure-type definition \
  --train-papers 1210.4634 2401.00367 1204.0109v1 1405.2464 1512.09272v2 2208.03112 2309.05826 \
  --val-papers 2603.09769v1 2312.16785 2505.12804v1 \
  --gold-csv Gold_Standard_Definitions.csv \
  --initial-prompt prompts/definition_prompt.txt \
  --provider anthropic \
  --model claude-opus-4-6 \
  --meta-model claude-opus-4-6 \
  --iterations 3 \
  --out-dir definition_optimization
```

### Visualization

```bash
python viz_opt_comparison.py --opt-dir definition_optimization
```
Produces `optimization_viz.png` in the optimization directory.

### Optimizer arguments
- `--train-papers`: ArXiv paper IDs for training (optimize on these)
- `--val-papers`: ArXiv paper IDs for validation (held-out evaluation)
- `--provider`: LLM provider for extraction (`anthropic`, `openai`, `huggingface`)
- `--model`: Model name for extraction (default: `claude-opus-4-6`)
- `--gold-csv`: Gold standard CSV path (e.g. `Gold_Standard_Definitions.csv`)
- `--initial-prompt`: Initial prompt template file (e.g. `prompts/definition_prompt.txt`)
- `--iterations`: Number of optimization iterations (default: 3)
- `--threshold`: Jaccard similarity threshold for matching (default: 0.7)
- `--meta-provider`: LLM provider for meta-optimization (default: `anthropic`)
- `--meta-model`: Model for meta-optimization (default: `claude-opus-4-6`)
- `--out-dir`: Output directory (e.g. `definition_optimization`)
- `--structure-type`: Structure type to optimize extraction for

### Outputs
- `optimized_prompt_{structure_type}_{provider}.txt` — best prompt from the training loop
- `optimization_history.json` — per-iteration metrics and prompts
- `optimization_viz.png` — visualization of the optimization process

## Distillation Analysis (NtRED)

The `distillation_analysis.py` script implements the NtRED distillation loop — identifying what manual regex misses but LLMs catch, mining LaTeX patterns, and validating new rules.

### Quick usage (recommended)

Use `distill.sh` to run the full distillation pipeline for any structure type:
```bash
bash distill.sh definition
# options: theorem lemma proof proposition corollary claim conjecture problem definition
```

### Manual usage (step by step)

#### 1. `dark-knowledge` — Identify dark knowledge
```bash
python distillation_analysis.py dark-knowledge \
    --eval-dir definition_eval \
    --gold-csv Gold_Standard_Definitions.csv \
    --structure-type definition
```

#### 2. `analyze` — LLM-powered pattern mining from missed structures
```bash
python distillation_analysis.py analyze \
    --input definition_eval/dark_knowledge.csv \
    --structure-type definition \
    --output definition_eval/analyze_patterns.csv
```

#### 3. `aggregate` — Consolidate suggestions into `distilled_rules.py`
Produces a `distilled_rules.py` file with an `extract_distilled_{type}()` function, auto-imported by `math_paper_parser.py` at parse time.
```bash
python distillation_analysis.py aggregate \
    --input definition_eval/analyze_patterns.csv \
    --structure-type definition \
    --eval-dir definition_eval
```

#### 4. `validate` — Re-run parser with distilled rules and verify improvement
```bash
python distillation_analysis.py validate \
    --paper-ids "1210.4634,1405.2464,2208.03112,1204.0109v1,1512.09272v2,2309.05826,2312.16785,2401.00367,2505.12804v1,2603.09769v1" \
    --structure-type definition \
    --expected definition_eval/dark_knowledge.csv
```

Visualization (before/after distillation):
```bash
python viz_distillation_comparison.py --eval-dir definition_eval
```
Produces `distillation_comparison.png` in the eval directory.

### Typical workflow
1. Run evaluations for all providers → produces `detailed_matches.csv`
2. `dark-knowledge` → identifies what manual misses but LLMs catch → `dark_knowledge.csv`
3. `analyze` → LLM generates concrete code suggestions for each missed item → `analyze_patterns.csv`
4. `aggregate` → meta-LLM consolidates suggestions into `distilled_rules.py` (auto-imported by parser)
5. `validate` → re-runs parser with distilled rules, confirms improvement → `dark_knowledge_validation.csv`
6. Repeat until F1 plateaus

### Common arguments
- `--threshold`: Jaccard similarity threshold (default: 0.7)
- `--output`: Override default output CSV path

## Downloading arXiv Papers

Papers can be downloaded using `extract_arxiv_data.py`. There are two storage modes:

### Standard mode (legacy)
Downloads the main `.tex` file only. `\input{}`/`\include{}` references remain unresolved.
```
full_papers/{year}/{month}/{day}/tex/{versioned_id}.tex
```
```bash
python3 extract_arxiv_data.py --start 1996-01-01 --end 1999-12-31 --formats latex
```

### Advanced mode (recommended)
Resolves all `\input{}`/`\include{}` references into a single unified `.tex` file. The original archive is preserved alongside it.
```
full_papers_advanced/{year}/{month}/{day}/{versioned_id}/
    {versioned_id}.tex      ← unified/flattened
    {versioned_id}.tar.gz   ← original archive
```
```bash
python3 extract_arxiv_data.py --start 1996-01-01 --end 1999-12-31 --advanced
```
