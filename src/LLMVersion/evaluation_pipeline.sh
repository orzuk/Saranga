#!/bin/bash

# Defaults
PAPER_ID="2208.03112"
OUT_DIR="."
THRESHOLD="0.7"
GOLD_CSV="Gold_Standard.csv"
DEFINITIONS_CSV="definitions.csv"
MERGED_CSV="MergedGoldAndDef.csv"
PROMPT_FILE=""

# API Keys
HF_TOKEN="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"
ANTHROPIC_API_KEY="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"
OPENAI_API_KEY="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"

# Parse named arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --paper-id) PAPER_ID="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        --threshold) THRESHOLD="$2"; shift 2 ;;
        --gold-csv) GOLD_CSV="$2"; shift 2 ;;
        --definitions-csv) DEFINITIONS_CSV="$2"; shift 2 ;;
        --merged-csv) MERGED_CSV="$2"; shift 2 ;;
        --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

REGEX_ID="^${PAPER_ID}"

# HuggingFace
export HF_TOKEN
python3 run_parse_papers.py \
    --regex-id "${REGEX_ID}" \
    --out-dir "${OUT_DIR}" \
    --definition-mode llm \
    --llm-provider huggingface \
    --llm-model "Qwen/Qwen2.5-7B-Instruct" \
    --prompt-file "${PROMPT_FILE}"

# Anthropic
export ANTHROPIC_API_KEY
python3 run_parse_papers.py \
    --regex-id "${REGEX_ID}" \
    --out-dir "${OUT_DIR}" \
    --definition-mode llm \
    --llm-provider anthropic \
    --llm-model claude-sonnet-4-20250514 \
    --prompt-file "${PROMPT_FILE}"

# OpenAI
export OPENAI_API_KEY
python3 run_parse_papers.py \
    --regex-id "${REGEX_ID}" \
    --out-dir "${OUT_DIR}" \
    --definition-mode llm \
    --llm-provider openai \
    --llm-model gpt-4o \
    --prompt-file "${PROMPT_FILE}"

# Manual
python3 run_parse_papers.py \
    --regex-id "${REGEX_ID}" \
    --out-dir "${OUT_DIR}" \
    --definition-mode manual

# Post-processing
python3 definitions_from_json_to_csv.py --paper-id "${PAPER_ID}"
python3 add_gold_standard.py --input-csv "${DEFINITIONS_CSV}" --gold-csv "${GOLD_CSV}" --output-csv "${MERGED_CSV}"
python3 evaluate_definitions.py --input-csv "${MERGED_CSV}" --threshold "${THRESHOLD}"
