#!/bin/bash

# Defaults
PAPER_ID="2208.03112"
OUT_DIR="."
THRESHOLD="0.7"
GOLD_CSV="Gold_Standard.csv"
DEFINITIONS_CSV="definitions.csv"
MERGED_CSV="MergedGoldAndDef.csv"
PROMPT_FILE=""
STRUCTURE_TYPE="definition"

# Prompt optimization defaults
OPTIMIZE_PROMPT=false
OPT_ITERATIONS=3
OPT_PROVIDER="anthropic"
OPT_MODEL="claude-sonnet-4-20250514"
OPT_META_PROVIDER="anthropic"
OPT_META_MODEL="claude-sonnet-4-20250514"

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
        --optimize-prompt) OPTIMIZE_PROMPT=true; shift ;;
        --opt-iterations) OPT_ITERATIONS="$2"; shift 2 ;;
        --opt-provider) OPT_PROVIDER="$2"; shift 2 ;;
        --opt-model) OPT_MODEL="$2"; shift 2 ;;
        --opt-meta-provider) OPT_META_PROVIDER="$2"; shift 2 ;;
        --opt-meta-model) OPT_META_MODEL="$2"; shift 2 ;;
        --structure-type) STRUCTURE_TYPE="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# Split comma-separated paper IDs into array
IFS=',' read -ra PAPER_IDS <<< "$PAPER_ID"
echo "=== Papers: ${PAPER_IDS[*]} ==="

# Prompt optimization (runs before main extraction)
if [ "$OPTIMIZE_PROMPT" = true ]; then
    echo "=== Running prompt optimization ==="
    python3 prompt_optimizer.py \
        --paper-id "${PAPER_ID}" \
        --provider "${OPT_PROVIDER}" \
        --model "${OPT_MODEL}" \
        --gold-csv "${GOLD_CSV}" \
        --initial-prompt "${PROMPT_FILE:-custom_prompt.txt}" \
        --iterations "${OPT_ITERATIONS}" \
        --threshold "${THRESHOLD}" \
        --meta-provider "${OPT_META_PROVIDER}" \
        --meta-model "${OPT_META_MODEL}" \
        --out-dir "${OUT_DIR}"

    PROMPT_FILE="optimized_prompt_${OPT_PROVIDER}.txt"
    echo "=== Using optimized prompt: ${PROMPT_FILE} ==="
fi

# --- Extraction: loop over each paper × each provider ---
for pid in "${PAPER_IDS[@]}"; do
    REGEX_ID="^${pid}"
    echo ""
    echo "============================================"
    echo "=== Extracting paper: ${pid} ==="
    echo "============================================"

    # HuggingFace
    export HF_TOKEN
    python3 run_parse_papers.py \
        --regex-id "${REGEX_ID}" \
        --out-dir "${OUT_DIR}" \
        --definition-mode llm \
        --llm-provider huggingface \
        --llm-model "Qwen/Qwen2.5-7B-Instruct" \
        --prompt-file "${PROMPT_FILE}" \
        --structure-types "${STRUCTURE_TYPE}"

    # Anthropic
    export ANTHROPIC_API_KEY
    python3 run_parse_papers.py \
        --regex-id "${REGEX_ID}" \
        --out-dir "${OUT_DIR}" \
        --definition-mode llm \
        --llm-provider anthropic \
        --llm-model claude-sonnet-4-20250514 \
        --prompt-file "${PROMPT_FILE}" \
        --structure-types "${STRUCTURE_TYPE}"

    # OpenAI
    export OPENAI_API_KEY
    python3 run_parse_papers.py \
        --regex-id "${REGEX_ID}" \
        --out-dir "${OUT_DIR}" \
        --definition-mode llm \
        --llm-provider openai \
        --llm-model gpt-4o \
        --prompt-file "${PROMPT_FILE}" \
        --structure-types "${STRUCTURE_TYPE}"

    # Manual
    python3 run_parse_papers.py \
        --regex-id "${REGEX_ID}" \
        --out-dir "${OUT_DIR}" \
        --definition-mode manual \
        --structure-types "${STRUCTURE_TYPE}"
done

# --- Post-processing: all papers together ---
# Build --paper-id flags for definitions_from_json_to_csv.py (supports multiple)
PAPER_ID_FLAGS=""
for pid in "${PAPER_IDS[@]}"; do
    PAPER_ID_FLAGS="${PAPER_ID_FLAGS} --paper-id ${pid}"
done

python3 definitions_from_json_to_csv.py ${PAPER_ID_FLAGS} --structure-type "${STRUCTURE_TYPE}" --out-dir "${OUT_DIR}" --output-csv "${OUT_DIR}/${DEFINITIONS_CSV}"
python3 add_gold_standard.py --input-csv "${OUT_DIR}/${DEFINITIONS_CSV}" --gold-csv "${GOLD_CSV}" --output-csv "${OUT_DIR}/${MERGED_CSV}"
python3 evaluate_definitions.py --input-csv "${OUT_DIR}/${MERGED_CSV}" --threshold "${THRESHOLD}" --output-csv "${OUT_DIR}/evaluation_results.csv" --detailed-csv "${OUT_DIR}/detailed_matches.csv"
