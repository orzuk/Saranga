## Pipeline Usage
The pipeline extracts definitions from papers using HuggingFace, Anthropic, OpenAI and manual and then evaluate their results according to the golden standard.
1) Extracts definitions/lemmas/theorem etc.. to jsons for each model and manual mode.
2) merge all definitions from all methods into a csv file named definitions.csv
3) gold standars need to be defined the same way as in Gold_Standard.csv - then it merges the definitions csv with the gold standard csv to form MergedGoldAndDef.csv
4) the evaluation process compares extracted definitions from each provider (HuggingFace, Anthropic, OpenAI, Manual) against gold standard definitions using Jaccard similarity with a configurable threshold (default 0.7), calculating precision, recall, and F1 scores for each method. It outputs two CSV files: a detailed match report showing similarity scores for each individual definition (detailed_matches.csv), and a summary report with overall performance metrics (TP/FP/FN, precision, recall, F1) per provider and paper (evaluation_results.csv).
Examples of usage:
Run the pipeline with default settings:
```bash
./evaluation_pipeline.sh
```
Customize parameters using named arguments:
```bash
./evaluation_pipeline.sh --paper-id 2208.03112 --threshold 0.8 --prompt-file custom_prompt.txt
```
**Available arguments to adjust in the pipeline bash:**
- `--paper-id`: ArXiv paper ID (default: 2208.03112)
- `--out-dir`: Output directory (default: .)
- `--threshold`: Evaluation threshold (default: 0.7)
- `--gold-csv`: Gold standard CSV file (default: Gold_Standard.csv)
- `--definitions-csv`: Definitions CSV file (default: definitions.csv)
- `--merged-csv`: Merged output CSV file (default: MergedGoldAndDef.csv)
- `--prompt-file`: Path to custom prompt template file for LLM extraction (optional). Use `{latex_chunk}` as placeholder for the LaTeX text.

**First time setup:**
```bash
chmod +x evaluation_pipeline.sh
```
## Parser Info:
Use the `--definition-mode` argument to choose your parsing strategy:
- `manual` - Pattern-based extraction (default, no API key needed)
- `llm` - LLM API extraction only
- `both` - Combines both methods for best coverage
Command Line Arguments
```bash
--start, --end: Date range for arXiv papers (YYYY-MM-DD format)
--days: Alternative to start/end; fetch papers from last N days
--category, -c: Filter by arXiv category (e.g., math.PR, math.DG)
--regex-id: Filter papers by ID pattern (e.g., "^2501\\.00685")
--top-k: Limit number of papers to process (default: 20, use ≤0 for no limit)
--out-dir: Output directory (defaults to FULL_PAPERS_DIR from config.py)
--draw-graphs: Generate network visualization PNGs
--verbose: Enable detailed logging
--definition-mode: Extraction method:
manual: Pattern-based extraction only (default)
llm: LLM-based extraction only
both: Combine both methods
--llm-provider: Choose provider: anthropic, openai, or huggingface
--llm-model: Model name (default: claude-sonnet-4-20250514)
--llm-chunk-chars: Max characters per LLM chunk (default: 30000)
--prompt-file: Path to custom prompt template file (use {latex_chunk} as placeholder)
```
Usage Examples
### Anthropic Claude
```bash
export ANTHROPIC_API_KEY="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"
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --definition-mode llm \
    --llm-provider anthropic \
    --llm-model claude-sonnet-4-20250514
```
### OpenAI
```bash
export OPENAI_API_KEY="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"
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --definition-mode llm \
    --llm-provider openai \
    --llm-model gpt-4o
```
### HuggingFace
```bash
export HF_TOKEN="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"
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --definition-mode llm \
    --llm-provider huggingface \
    --llm-model "Qwen/Qwen2.5-7B-Instruct"
```

### Custom Prompt Example
```bash
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --definition-mode llm \
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

## Cost Considerations
Parsing 1707.07938v2:
anthropic sonnet 4.0 - 20cents
openai 4o mini - 10cents
huggingface - 4cents
