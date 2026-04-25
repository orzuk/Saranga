#!/bin/bash -l
#
# Tier B — Silver-gold driver. Holistic multi-LLM extraction over ~270
# alignment_benchmark papers, then validate / anomaly / link / visualize /
# consensus.
#
# Thin wrapper around src/run_pipeline.py. All tier-specific defaults
# (paths, operations, holistic-multi mode, models config) are set here;
# user-tweakable args (--limit, --paper-ids, --no-extraction) are passed
# through via "$@".
#
# Required env vars (per the model in your config):
#   ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY, OPENROUTER_API_KEY...
#
# Usage:
#   scripts/run_silver_gold.sh                              # all papers, default config
#   BASE_DIR=/path/to/bench scripts/run_silver_gold.sh
#   scripts/run_silver_gold.sh --limit 5
#   scripts/run_silver_gold.sh --paper-ids paper1,paper2
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BASE_DIR=${BASE_DIR:-$REPO_ROOT/alignment_benchmark}
REGISTRY=${REGISTRY:-$BASE_DIR/paper_registry.csv}
MODELS_CONFIG=${MODELS_CONFIG:-$REPO_ROOT/scripts/silver_gold/example_config.yaml}
PROMPT_FILE=${PROMPT_FILE:-$REPO_ROOT/scripts/paper_extraction_prompt.txt}
OUT_DIR=${OUT_DIR:-$BASE_DIR}
OPERATIONS=${OPERATIONS:-parse,validate,anomalies,link,visualize,consensus}
PYTHON=${PYTHON:-python3}

CMD=(
    "$PYTHON" "$REPO_ROOT/src/run_pipeline.py"
    --operations "$OPERATIONS"
    --extract-mode holistic-multi
    --models-config "$MODELS_CONFIG"
    --base-dir "$BASE_DIR"
    --registry "$REGISTRY"
    --prompt-file "$PROMPT_FILE"
    --out-dir "$OUT_DIR"
)

echo "[run_silver_gold] ${CMD[*]} $*"
"${CMD[@]}" "$@"
