Adjusted run_parse_papers.py and math_paper_parser.py for LLM option.
To test the API integration on a specific paper (e.g 2501.00685) run command:

python3 run_parse_papers.py \
--regex-id "^2501\.00685" \
--out-dir . \
--definition-mode llm


to the the functionality, as a proof of concept the LLM option parses only definitions, while rest of objects are still being parsed manually.

added the definition argument to be able to choose wether we want the definitions to be parsed by llm, manual or both (--definition manual or --definition both).
