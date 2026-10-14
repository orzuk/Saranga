# LLMVersion: the extraction engine

LaTeX -> unified JSON (nodes and edges). The rule-based extractor is the parser plus a
distilled rule set; the LLM extractor sends chunks to a model API.

| File | What it is |
|---|---|
| `math_paper_parser.py` | `PaperParser`: environments, proofs, prose results, edges; applies the rules |
| `math_classes.py` | the in-memory graph (`PaperGraph`, node classes) and its export to unified JSON |
| `parse_batch.py` | runs the parser over many papers (called by `src/run_pipeline.py --operations parse`) |
| `unit_rules.py`, `rule_guard.py`, `latex_clean.py` | the distilled sentence rules' runtime and guards |
| `distillation_analysis.py`, `node_metrics.py`, `match_modes.py` | matching and scoring used by the distillation drivers in `scripts/` |
| `*_eval/distilled_rules.py` | 14 symlinks to the production rule set (`extractors/rules/silver_v6__sentence_rules_haiku__2026-10`) |
| `download_arxiv_advanced.py`, `extract_arxiv_funcs.py`, `config.py` | arXiv download by date range; shims to the `src/` copies |
| `full_papers/` | LaTeX of the T1 gold papers (read by `scripts/parse_gold_papers.sh`) |
| `rule_complexity.py` | static and timing measures of a rule set |

> **User-facing entry point:** `src/run_pipeline.py` (one directory up). The v1 per-type
> prompt-optimisation tooling that used to live here (`prompt_optimizer.py`,
> `evaluation_pipeline.sh`, per-type gold CSVs) is on the `archive/pre-v6` branch.

## Parser Info
Use the `--extraction-mode` argument to choose the extraction strategy:
- `rules` — rule-based extraction: the LaTeX parser plus the distilled sentence rules (default, no API key)
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
--extraction-mode       Extraction method: rules (default), llm, or both
--rules-dir             Rule set to apply (default: the v6 sentence rules, through the *_eval/ symlinks)
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
> for users who want to invoke the extractor directly (e.g. for debugging).

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
workflows.
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

The repository's `prompts/` directory contains per-type prompt templates. The prompt resolution order is:

1. `--prompt-file` (user-provided custom prompt) — overrides everything
2. `prompts/{structure_type}_prompt.txt` — per-type template file
3. Built-in default generated from `STRUCTURE_TYPE_CONFIG`

All 11 structure types have dedicated templates in `prompts/` (e.g. `definition_prompt.txt`, `theorem_prompt.txt`, `lemma_prompt.txt`, etc.). Theorem-like types use `assumptions` and `conclusions` fields.

To add a new type, create `prompts/{type}_prompt.txt` with `{latex_chunk}` placeholder. Otherwise, the built-in default prompt is generated automatically from the type's configuration.

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
