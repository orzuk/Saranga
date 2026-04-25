#!/bin/bash -l
#
# Tier D — High-resolution extraction. Holistic LLM with proof-step
# decomposition over ~20 papers. Used for fine-grained per-step proof
# evaluation.
#
# Thin wrapper around src/run_pipeline.py with extract-mode set to
# holistic-proof-steps. Otherwise this looks like Tier B but:
#   - smaller paper set (--limit 20 default)
#   - proof-step output schema variant
#   - optionally followed by eval against hand-gold (if proof-step gold exists)
#
# Usage:
#   scripts/run_high_res.sh
#   scripts/run_high_res.sh --paper-ids paper1,paper5
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BASE_DIR=${BASE_DIR:-$REPO_ROOT/alignment_benchmark}
REGISTRY=${REGISTRY:-$BASE_DIR/paper_registry.csv}
MODELS_CONFIG=${MODELS_CONFIG:-$REPO_ROOT/scripts/silver_gold/example_config.yaml}
PROMPT_FILE=${PROMPT_FILE:-$REPO_ROOT/scripts/paper_extraction_prompt.txt}
OUT_DIR=${OUT_DIR:-$BASE_DIR}
LIMIT=${LIMIT:-20}
OPERATIONS=${OPERATIONS:-parse,validate,anomalies,link,visualize}
PYTHON=${PYTHON:-python3}

CMD=(
    "$PYTHON" "$REPO_ROOT/src/run_pipeline.py"
    --operations "$OPERATIONS"
    --extract-mode holistic-proof-steps
    --models-config "$MODELS_CONFIG"
    --base-dir "$BASE_DIR"
    --registry "$REGISTRY"
    --prompt-file "$PROMPT_FILE"
    --out-dir "$OUT_DIR"
    --limit "$LIMIT"
)

echo "[run_high_res] ${CMD[*]} $*"
"${CMD[@]}" "$@"
