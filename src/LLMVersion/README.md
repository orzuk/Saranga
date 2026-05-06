# LLMVersion: Extraction Engine for SARANGA

This directory is the extraction engine: LaTeX → unified JSON. It produces
knowledge graphs via pattern-based (manual) extraction and/or LLM-based
extraction (Anthropic Claude, OpenAI GPT, HuggingFace).

> **User-facing entry point:** `src/run_pipeline.py` (one directory up) is
> the recommended CLI. It internally invokes the extractor in this directory.
> The scripts here — `parse_batch.py`, `evaluation_pipeline.sh`,
> `prompt_optimizer.py`, `distillation_analysis.py` — are building blocks
> that can also be invoked directly for specialized workflows.

## Pipeline Usage

The extraction engine produces mathematical structures (definitions, theorems, lemmas, etc.) from LaTeX papers, then evaluates results against a gold standard.

1) Extracts structures to JSONs for each model and manual mode.
2) Merges all extracted objects into a CSV file (e.g. `definitions.csv`).
3) Merges extracted CSV with gold standard CSV → `MergedGoldAndDef.csv`.
4) Evaluates using Jaccard similarity (configurable threshold, default 0.7), calculating precision, recall, and F1 per provider and paper.

### Supported Structure Types

- `definition` (default), `theorem`, `lemma`, `proposition`, `corollary`, `claim`, `conjecture`, `problem` — core math structures
- `proof`, `algorithm`, `table` — supporting structures
- `equation` (orphan) — display equations not inside any named environment (manual regex only)

### Extraction & Evaluation

```bash
bash extraction.sh definition
# options: theorem lemma proof proposition corollary claim conjecture problem definition
```

Or manually with `evaluation_pipeline.sh`:
```bash
bash evaluation_pipeline.sh \
  --paper-id "1210.4634,1405.2464,2208.03112,1204.0109v1,1512.09272v2,2309.05826,2312.16785,2401.00367,2505.12804v1,2603.09769v1" \
  --structure-type definition \
  --gold-csv Gold_Standard_Definitions.csv \
  --out-dir definition_eval \
  --providers "anthropic,openai,manual"
```

Visualization:
```bash
python viz_eval_comparison.py --eval-dir definition_eval
```

## Parser

Use the `--extraction-mode` argument to choose the extraction strategy:
- `manual` — Pattern-based extraction (default, no API key needed)
- `llm` — LLM API extraction only
- `both` — Combines both methods for best coverage

### Command Line Arguments

```
--start, --end          Date range for arXiv papers (YYYY-MM-DD)
--category, -c          arXiv category (e.g., math.PR, math.DG)
--regex-id              Filter papers by ID pattern
--top-k                 Limit number of papers (default: 20)
--out-dir               Output directory
--extraction-mode       manual (default), llm, or both
--llm-provider          anthropic, openai, or huggingface
--llm-model             Model name (default: claude-sonnet-4-20250514)
--structure-types       Comma-separated types to extract
--prompt-file           Custom prompt template (use {latex_chunk} placeholder)
```

### Usage Examples

```bash
# Extract definitions via LLM
export ANTHROPIC_API_KEY="your-key"
python3 src/run_pipeline.py \
    --operations parse \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider anthropic

# Extract multiple structure types
python3 src/run_pipeline.py \
    --operations parse \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --extraction-mode llm \
    --llm-provider openai \
    --llm-model gpt-4o \
    --structure-types "definition,theorem,lemma"
```

## Prompt Templates

The `prompts/` directory contains per-type prompt templates. Resolution order:
1. `--prompt-file` (user-provided custom prompt)
2. `prompts/{structure_type}_prompt.txt`
3. Built-in default from `STRUCTURE_TYPE_CONFIG`

## Prompt Optimization

Iterative prompt optimization loop: extract → evaluate → error analysis → meta-LLM rewrite.

```bash
bash optimize.sh definition
# options: theorem lemma proof proposition corollary claim conjecture problem definition
```

Manual usage:
```bash
python prompt_optimizer.py \
  --structure-type definition \
  --train-papers 1210.4634 2401.00367 1204.0109v1 1405.2464 1512.09272v2 2208.03112 2309.05826 \
  --val-papers 2603.09769v1 2312.16785 2505.12804v1 \
  --gold-csv Gold_Standard_Definitions.csv \
  --initial-prompt prompts/definition_prompt.txt \
  --provider anthropic \
  --iterations 3 \
  --out-dir definition_optimization
```

## Distillation Analysis (NtRED)

The `distillation_analysis.py` script implements the NtRED distillation loop — identifying what manual regex misses but LLMs catch, mining LaTeX patterns, and generating new deterministic rules.

```bash
bash distill.sh definition
```

### Step by step

#### 1. `dark-knowledge` — Identify what regex misses but LLMs catch
```bash
python distillation_analysis.py dark-knowledge \
    --eval-dir definition_eval \
    --gold-csv Gold_Standard_Definitions.csv \
    --structure-type definition
```

#### 2. `analyze` — LLM-powered pattern mining
```bash
python distillation_analysis.py analyze \
    --input definition_eval/dark_knowledge.csv \
    --structure-type definition
```

#### 3. `aggregate` — Consolidate into `distilled_rules.py`
```bash
python distillation_analysis.py aggregate \
    --input definition_eval/analyze_patterns.csv \
    --structure-type definition \
    --eval-dir definition_eval
```

#### 4. `validate` — Re-run parser and verify improvement
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
