Adjusted `run_parse_papers.py` and `math_paper_parser.py` to support multiple LLM providers for parsing.



Use the `--definition-mode` argument to choose your parsing strategy:

- `manual` - Pattern-based extraction (default, no API key needed)
- `llm` - LLM API extraction only
- `both` - Combines both methods for best coverage

## Command Line Arguments

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
--llm-chunk-chars: Max characters per LLM chunk (default: 8000)
```

## Usage Examples

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

## Cost Considerations

Parsing 1707.07938v2:

anthropic sonnet 4.0 - 20cents
openai 4o mini - 10cents
huggingface - 4cents

