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

# Provider selection (comma-separated: anthropic,openai,huggingface,manual)
PROVIDERS="anthropic,openai,huggingface,manual"

# Prompt optimization defaults
OPTIMIZE_PROMPT=false
OPT_ITERATIONS=3
OPT_PROVIDER="anthropic"
OPT_MODEL="claude-sonnet-4-6"
OPT_META_PROVIDER="anthropic"
OPT_META_MODEL="claude-sonnet-4-6"

# API Keys
HF_TOKEN="${HF_TOKEN:?set HF_TOKEN in the environment}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY in the environment}"
OPENAI_API_KEY="${OPENAI_API_KEY:?set OPENAI_API_KEY in the environment}"

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
        --providers) PROVIDERS="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# Split comma-separated paper IDs into array
IFS=',' read -ra PAPER_IDS <<< "$PAPER_ID"
echo "=== Papers: ${PAPER_IDS[*]} ==="

# Split comma-separated providers into array
IFS=',' read -ra PROVIDER_LIST <<< "$PROVIDERS"
echo "=== Providers: ${PROVIDER_LIST[*]} ==="

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
# Now invokes the unified pipeline (src/run_pipeline.py) for the parse
# operation. The pipeline internally delegates to parse_batch.py.
# This shell script lives in src/LLMVersion/; RUN_PIPELINE resolves to
# src/run_pipeline.py (one directory up).
RUN_PIPELINE="$(cd "$(dirname "$0")/.." && pwd)/run_pipeline.py"

for pid in "${PAPER_IDS[@]}"; do
    REGEX_ID="^${pid}"
    echo ""
    echo "============================================"
    echo "=== Extracting paper: ${pid} ==="
    echo "============================================"

    for provider in "${PROVIDER_LIST[@]}"; do
        case "$provider" in
            huggingface)
                export HF_TOKEN
                python3 "${RUN_PIPELINE}" \
                    --operations parse \
                    --regex-id "${REGEX_ID}" \
                    --out-dir "${OUT_DIR}" \
                    --extraction-mode llm \
                    --llm-provider huggingface \
                    --llm-model "Qwen/Qwen2.5-7B-Instruct" \
                    --prompt-file "${PROMPT_FILE}" \
                    --structure-types "${STRUCTURE_TYPE}"
                ;;
            anthropic)
                export ANTHROPIC_API_KEY
                python3 "${RUN_PIPELINE}" \
                    --operations parse \
                    --regex-id "${REGEX_ID}" \
                    --out-dir "${OUT_DIR}" \
                    --extraction-mode llm \
                    --llm-provider anthropic \
                    --llm-model claude-opus-4-7 \
                    --prompt-file "${PROMPT_FILE}" \
                    --structure-types "${STRUCTURE_TYPE}"
                ;;
            openai)
                export OPENAI_API_KEY
                python3 "${RUN_PIPELINE}" \
                    --operations parse \
                    --regex-id "${REGEX_ID}" \
                    --out-dir "${OUT_DIR}" \
                    --extraction-mode llm \
                    --llm-provider openai \
                    --llm-model gpt-4o \
                    --prompt-file "${PROMPT_FILE}" \
                    --structure-types "${STRUCTURE_TYPE}"
                ;;
            manual)
                python3 "${RUN_PIPELINE}" \
                    --operations parse \
                    --regex-id "${REGEX_ID}" \
                    --out-dir "${OUT_DIR}" \
                    --extraction-mode rules \
                    --structure-types "${STRUCTURE_TYPE}"
                ;;
            *)
                echo "Unknown provider: $provider (valid: anthropic,openai,huggingface,manual)"
                ;;
        esac
    done
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
