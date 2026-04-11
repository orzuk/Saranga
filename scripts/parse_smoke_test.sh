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

# Pick a Python interpreter. Priority:
#   1. $PYTHON env var (explicit override)
#   2. $VIRTUAL_ENV/bin/python (set by `source venv/bin/activate`)
#   3. $CONDA_PREFIX/bin/python (set by conda activate)
#   4. python3 on PATH
#   5. python on PATH
#
# Recommended: activate your venv before running.
#   source /sci/labs/orzuk/$USER/venvs/your-venv/bin/activate
#   ./scripts/parse_smoke_test.sh
if [ -z "${PYTHON:-}" ]; then
    if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
        PYTHON="$VIRTUAL_ENV/bin/python"
    elif [ -n "${CONDA_PREFIX:-}" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
        PYTHON="$CONDA_PREFIX/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON="python"
    else
        echo "ERROR: no python interpreter found. Set PYTHON env var or install python."
        exit 1
    fi
fi

echo "===================================================="
echo "Authomathics smoke test"
echo "===================================================="
echo "  CATEGORY        = $CATEGORY"
echo "  TOP_K           = $TOP_K"
echo "  EXTRACTION_MODE = $EXTRACTION_MODE"
echo "  OUT_DIR         = $OUT_DIR"
echo "  REPO_ROOT       = $REPO_ROOT"
echo "  PYTHON          = $PYTHON"
echo "===================================================="
echo

cd "$REPO_ROOT/src"

"$PYTHON" run_pipeline.py \
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
