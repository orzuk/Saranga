#!/bin/bash -l
#
# Tier E — Cross-paper alignment driver. Computes Hungarian + structural
# QAP alignment + permutation null Z-score for every (positive, negative)
# pair in the benchmark config.
#
# This is a thin wrapper around scripts/run_alignment_benchmark.py
# (which is already a thin Tier E driver — keep using it directly if
# you want full control). The wrapper exists for symmetry with the
# other four tiers and to encode the standard config / output paths.
#
# Usage:
#   scripts/run_alignment.sh
#   N_PERMS=1000 scripts/run_alignment.sh
#   scripts/run_alignment.sh --only Adam_vs_RMSProp
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CONFIG=${CONFIG:-$REPO_ROOT/alignment_benchmark/test_set/benchmark_config.json}
OUTPUT=${OUTPUT:-$REPO_ROOT/alignment_benchmark/results_jaccard.csv}
N_PERMS=${N_PERMS:-300}
ALPHA=${ALPHA:-0.5}
SIGMA_LABEL=${SIGMA_LABEL:-jaccard}
PYTHON=${PYTHON:-python3}

CMD=(
    "$PYTHON" "$REPO_ROOT/scripts/run_alignment_benchmark.py"
    --config "$CONFIG"
    --output "$OUTPUT"
    --n-perms "$N_PERMS"
    --alpha "$ALPHA"
    --sigma-label "$SIGMA_LABEL"
)
if [ -n "${SIGMA_IMPORT:-}" ]; then
    CMD+=(--sigma-import "$SIGMA_IMPORT")
fi

echo "[run_alignment] ${CMD[*]} $*"
"${CMD[@]}" "$@"
