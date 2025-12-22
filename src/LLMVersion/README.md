Adjusted run_parse_papers.py and math_paper_parser.py for LLM option.

To test the API integration on a specific paper (e.g 2501.00685) run command:
```bash
export ANTHROPIC_API_KEY="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"
python3 run_parse_papers.py \
    --regex-id "^2501\.00685" \
    --out-dir . \
    --definition-mode llm
```

The API functionality, as a proof of concept, parses only definitions, while the rest of the objects (theorems, lemmas, proofs, etc.) are still being parsed manually.

Added the `--definition-mode` argument to choose whether definitions should be parsed by LLM, manually, or both:
- `--definition-mode manual` - Pattern-based extraction (default, no API key needed)
- `--definition-mode llm` - Anthropic Claude API extraction only
- `--definition-mode both` - Combines both methods for best coverage

**Cost note:** Parsing a single paper (2501.00685) cost approximately $0.70 using the LLM API. This is quite expensive, so we need to think of a more efficient method for batch parsing (e.g., reducing chunk sizes, using cheaper models, or hybrid approaches).

Install requirements if anthropic library is missing on your environment
