## Pipeline Usage
The pipeline extracts mathematical structures (definitions, theorems, lemmas, etc.) from LaTeX papers using HuggingFace, Anthropic, OpenAI and manual methods, then evaluates results against a gold standard.

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

Pass `--structure-types` (comma-separated) to `run_parse_papers.py`, or `--structure-type` (single) to other scripts.

### Pipeline Examples

Run the pipeline with default settings (extracts definitions):
```bash
./evaluation_pipeline.sh
```

Extract theorems instead of definitions:
```bash
./evaluation_pipeline.sh --paper-id 2208.03112 --structure-type theorem
```

Customize parameters using named arguments:
```bash
./evaluation_pipeline.sh --paper-id 2208.03112 --threshold 0.8 --prompt-file custom_prompt.txt
```

**Available pipeline arguments:**
- `--paper-id`: ArXiv paper ID (default: 2208.03112)
- `--out-dir`: Output directory (default: .)
- `--threshold`: Evaluation threshold (default: 0.7)
- `--gold-csv`: Gold standard CSV file (default: Gold_Standard.csv)
- `--definitions-csv`: Definitions CSV file (default: definitions.csv)
- `--merged-csv`: Merged output CSV file (default: MergedGoldAndDef.csv)
- `--prompt-file`: Path to custom prompt template file for LLM extraction (optional). Use `{latex_chunk}` as placeholder for the LaTeX text.
- `--structure-type`: Which structure type to extract (default: `definition`)

**First time setup:**
```bash
chmod +x evaluation_pipeline.sh
```

## Parser Info
Use the `--extraction-mode` argument to choose the extraction strategy:
- `manual` — Pattern-based extraction (default, no API key needed)
- `llm` — LLM API extraction only
- `both` — Combines both methods for best coverage

### Command Line Arguments (`run_parse_papers.py`)
```
--start, --end          Date range for arXiv papers (YYYY-MM-DD format)
--days                  Alternative to start/end; fetch papers from last N days
--category, -c          Filter by arXiv category (e.g., math.PR, math.DG)
--regex-id              Filter papers by ID pattern (e.g., "^2501\\.00685")
--top-k                 Limit number of papers to process (default: 20, use <=0 for no limit)
--out-dir               Output directory (defaults to FULL_PAPERS_DIR from config.py)
--draw-graphs           Generate network visualization PNGs
--verbose               Enable detailed logging
--extraction-mode       Extraction method: manual (default), llm, or both
--llm-provider          Choose provider: anthropic, openai, or huggingface
--llm-model             Model name (default: claude-sonnet-4-20250514)
--llm-chunk-chars       Max characters per LLM chunk (default: 30000)
--prompt-file           Path to custom prompt template file (use {latex_chunk} as placeholder)
--structure-types       Comma-separated structure types to extract via LLM (default: definition)
```

### Usage Examples

#### Extract definitions (default)
```bash
export ANTHROPIC_API_KEY="your-key"
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider anthropic \
    --llm-model claude-sonnet-4-20250514
```

#### Extract theorems via LLM
```bash
export ANTHROPIC_API_KEY="your-key"
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider anthropic \
    --structure-types theorem
```

#### Extract multiple structure types at once
```bash
python3 run_parse_papers.py \
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
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider openai \
    --llm-model gpt-4o
```

#### HuggingFace
```bash
export HF_TOKEN="your-token"
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider huggingface \
    --llm-model "Qwen/Qwen2.5-7B-Instruct"
```

#### Custom Prompt Example
```bash
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider anthropic \
    --prompt-file my_custom_prompt.txt
```

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

Included templates:
- `prompts/definition_prompt.txt` — definition extraction
- `prompts/theorem_prompt.txt` — theorem extraction (includes `assumptions` and `statement` fields)

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
The pipeline includes an optional iterative prompt optimization loop (`prompt_optimizer.py`). It extracts structures with the current prompt, evaluates against the gold standard, analyzes errors (FP/FN/near-misses), and feeds them to a meta-LLM to produce an improved prompt. This repeats for N iterations, keeping the best prompt by F1.

### Single-paper mode (backward compatible)

Optimize on a single paper:
```bash
python3 prompt_optimizer.py \
    --paper-id 2208.03112 \
    --provider anthropic \
    --model claude-sonnet-4-20250514 \
    --iterations 3 \
    --initial-prompt custom_prompt.txt
```

Optimize for theorems instead of definitions:
```bash
python3 prompt_optimizer.py \
    --paper-id 2208.03112 \
    --provider anthropic \
    --model claude-sonnet-4-20250514 \
    --iterations 3 \
    --structure-type theorem
```

### Train/validation split

To reduce overfitting to a single paper's style, use `--train-papers` to optimize across multiple papers and `--val-papers` to evaluate the best prompt on held-out papers. Metrics are micro-averaged: TP/FP/FN are summed globally across all papers, then P/R/F1 are computed from the totals. Validation papers are never used for error analysis or meta-prompt construction.

```bash
python3 prompt_optimizer.py \
    --train-papers 2208.03112 1210.4634 1405.2464 \
    --val-papers 1512.09272 2309.05826 \
    --provider anthropic \
    --model claude-sonnet-4-20250514 \
    --gold-csv Gold_Standard_Definitions.csv \
    --iterations 3
```

`--paper-id` and `--train-papers` are mutually exclusive — use one or the other. `--val-papers` requires `--train-papers`.

### Via the pipeline

Runs optimization before the main extraction:
```bash
./evaluation_pipeline.sh --optimize-prompt --opt-iterations 3 --opt-provider anthropic
```

Additional pipeline arguments for optimization:
- `--optimize-prompt`: Enable prompt optimization before extraction
- `--opt-iterations`: Number of optimization iterations (default: 3)
- `--opt-provider`: LLM provider for extraction during optimization (default: anthropic)
- `--opt-model`: Model for extraction during optimization (default: claude-sonnet-4-20250514)
- `--opt-meta-provider`: LLM provider for the meta-optimization call (default: anthropic)
- `--opt-meta-model`: Model for meta-optimization (default: claude-sonnet-4-20250514)

### Optimizer arguments
- `--paper-id`: Single ArXiv paper ID (no validation)
- `--train-papers`: ArXiv paper IDs for training (optimize on these)
- `--val-papers`: ArXiv paper IDs for validation (held-out evaluation)
- `--provider`: LLM provider for extraction (`anthropic`, `openai`, `huggingface`)
- `--model`: Model name for extraction
- `--gold-csv`: Gold standard CSV path (default: `Gold_Standard.csv`)
- `--initial-prompt`: Initial prompt template file (default: `custom_prompt.txt`)
- `--iterations`: Number of optimization iterations (default: 3)
- `--threshold`: Jaccard similarity threshold for matching (default: 0.7)
- `--meta-provider`: LLM provider for meta-optimization (default: `anthropic`)
- `--meta-model`: Model for meta-optimization (default: `claude-sonnet-4-20250514`)
- `--out-dir`: Output directory (default: `.`)
- `--work-dir`: Working directory for iteration data (default: auto temp dir)
- `--structure-type`: Structure type to optimize extraction for (default: `definition`)

### Outputs
- `optimized_prompt_{structure_type}_{provider}.txt` — best prompt from the training loop
- `optimization_history.json` — per-iteration `train_metrics` and prompts, plus `train_paper_ids`, `val_paper_ids`, and `validation_metrics` (when validation is used)

## Distillation Analysis (NtRED)

The `distillation_analysis.py` script implements the NtRED distillation loop — identifying what manual regex misses but LLMs catch, mining LaTeX patterns, and validating new rules.

### Subcommands

#### 1. `dark-knowledge` — Identify dark knowledge (gold-standard papers)
Finds gold items missed by manual but caught by at least one LLM (`gold=exists ∧ manual=FN ∧ any_LLM=TP`).
```bash
python distillation_analysis.py dark-knowledge \
    --eval-dir theorem_eval \
    --gold-csv Gold_Standard_Theorems.csv \
    --structure-type theorem
```

#### 2. `discovery` — Find new structures via LLM consensus (unlabeled papers)
Clusters LLM extractions that manual missed, filtered by ≥2 provider agreement.
```bash
python distillation_analysis.py discovery \
    --eval-dir theorem_eval \
    --structure-type theorem
```

#### 3. `analyze` — LLM-powered pattern mining from missed structures
Locates missed items in the TeX source, reads the current extraction method from `math_paper_parser.py`, and sends each item to an LLM (Anthropic API) along with the surrounding LaTeX context and extractor source code. The LLM returns concrete, copy-pasteable code changes (new regex patterns, environment names, or branches) to catch the missed structure. Falls back to rule-based classification if the LLM call fails.

```bash
python distillation_analysis.py analyze \
    --input theorem_eval/dark_knowledge.csv \
    --structure-type theorem \
    --model claude-sonnet-4-20250514   # optional, this is the default
```

Output CSV columns: `paper_id`, `gold_index`, `pattern_type` (rule-based secondary), `latex_context`, `llm_reasoning`, `llm_suggested_rule`.

#### 4. `validate` — Check if manual parser catches previously missed items
After manually adding new regex rules to `math_paper_parser.py`, re-run the parser and verify improvement.
```bash
python distillation_analysis.py validate \
    --paper-ids 1210.4634,1405.2464 \
    --structure-type theorem \
    --expected theorem_eval/dark_knowledge.csv
```

### Typical workflow
1. Run evaluations for all providers → produces `detailed_matches.csv`
2. `dark-knowledge` → identifies what manual misses but LLMs catch
3. `analyze` → LLM generates concrete code changes for each missed item
4. **Review and apply** LLM-suggested rules to `math_paper_parser.py`
5. `validate` → confirms the new rules catch previously-missed items
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

## Cost Considerations
Parsing 1707.07938v2:
anthropic sonnet 4.0 - 20cents
openai 4o mini - 10cents
huggingface - 4cents
