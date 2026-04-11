#!/bin/bash -l
#
# Quick smoke test for the unified pipeline.
# Parses 5 math.CO papers in manual mode via src/run_pipeline.py, no SLURM,
# no LLM API cost. Use this to verify the pipeline works end-to-end before
# submitting the full cluster job.
#
# Usage:
#   ./scripts/parse_smoke_test.sh               # 5 papers, manual mode
#   TOP_K=20 ./scripts/parse_smoke_test.sh      # 20 papers
#   CATEGORY=math.PR ./scripts/parse_smoke_test.sh   # different category
#   OUT_DIR=./my_test ./scripts/parse_smoke_test.sh  # custom output dir
#
# On the cluster, you can also submit this via sbatch with env vars:
#   sbatch --export=TOP_K=5 scripts/parse_math_co_cluster.sh
#

set -euo pipefail

CATEGORY=${CATEGORY:-math.CO}
TOP_K=${TOP_K:-5}
OUT_DIR=${OUT_DIR:-./smoke_test_out}
EXTRACTION_MODE=${EXTRACTION_MODE:-manual}

# Resolve repo root from this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "===================================================="
echo "Authomathics smoke test"
echo "===================================================="
echo "  CATEGORY        = $CATEGORY"
echo "  TOP_K           = $TOP_K"
echo "  EXTRACTION_MODE = $EXTRACTION_MODE"
echo "  OUT_DIR         = $OUT_DIR"
echo "  REPO_ROOT       = $REPO_ROOT"
echo "===================================================="
echo

cd "$REPO_ROOT/src"

python3 run_pipeline.py \
    --operations parse \
    --category "$CATEGORY" \
    --top-k "$TOP_K" \
    --extraction-mode "$EXTRACTION_MODE" \
    --out-dir "$OUT_DIR" \
    --verbose

RC=$?

echo
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Smoke test finished with exit code $RC"

if [ -d "$OUT_DIR" ]; then
    N_JSON=$(find "$OUT_DIR" -name "*.json" 2>/dev/null | wc -l)
    echo "  JSON files produced: $N_JSON"
    if [ "$N_JSON" -gt 0 ]; then
        echo "  First few outputs:"
        find "$OUT_DIR" -name "*.json" 2>/dev/null | head -5
    fi
fi

exit $RC
