#!/bin/bash -l
#
# SLURM job: run Authomathics unified pipeline on cluster.
#
# Default configuration: parse operation (tex -> JSON) on 500 math.CO papers
# with manual extraction mode. No API cost. Uses locally-downloaded .tex files
# from ARXIV_DIR if available; falls back to arXiv API if not.
#
# Usage:
#   sbatch scripts/parse_math_co_cluster.sh
#
# Customize via environment variables at submission time:
#   sbatch --export=CATEGORY=math.PR,TOP_K=1000 scripts/parse_math_co_cluster.sh
#
#SBATCH --job-name=authomath_parse
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --time=08:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4

set -euo pipefail

# ----------------------------------------------------------------------------
# Configurable parameters (override via sbatch --export)
# ----------------------------------------------------------------------------

CATEGORY=${CATEGORY:-math.CO}
START_DATE=${START_DATE:-2024-01-01}
END_DATE=${END_DATE:-2026-04-01}
TOP_K=${TOP_K:-500}
EXTRACTION_MODE=${EXTRACTION_MODE:-manual}
OPERATIONS=${OPERATIONS:-parse}

STRUCTURE_TYPES=${STRUCTURE_TYPES:-"definition,theorem,lemma,proposition,corollary,claim,conjecture,problem,proof,algorithm,equation"}

# Where the outputs land
OUT_DIR=${OUT_DIR:-/sci/labs/orzuk/orzuk/projects/Authomathics/arxiv/parsed_${CATEGORY//./_}_${EXTRACTION_MODE}_${TOP_K}}

# Code
REPO_ROOT=${REPO_ROOT:-/sci/labs/orzuk/orzuk/github/Authomathics}

# Python interpreter. Priority:
#   1. $PYTHON env var (via sbatch --export=PYTHON=/path/to/python)
#   2. python3 on PATH (SLURM job inherits the submitting shell's
#      environment, so activate your venv BEFORE sbatch)
#
# Recommended workflow on the cluster:
#   source /sci/labs/orzuk/$USER/venvs/authomathics-venv/bin/activate
#   sbatch scripts/parse_math_co_cluster.sh
# Or override explicitly:
#   sbatch --export=PYTHON=/sci/labs/orzuk/$USER/venvs/authomathics-venv/bin/python \
#          scripts/parse_math_co_cluster.sh
PYTHON=${PYTHON:-python3}

# ----------------------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------------------

mkdir -p logs
mkdir -p "$OUT_DIR"

echo "===================================================="
echo "Authomathics pipeline job"
echo "===================================================="
echo "Date:            $(date '+%Y-%m-%d %H:%M:%S')"
echo "Host:            $(hostname)"
echo "User:            $(whoami)"
echo "Job ID:          ${SLURM_JOB_ID:-(no SLURM)}"
echo "Job name:        ${SLURM_JOB_NAME:-(no SLURM)}"
echo
echo "Parameters:"
echo "  OPERATIONS      = $OPERATIONS"
echo "  CATEGORY        = $CATEGORY"
echo "  START_DATE      = $START_DATE"
echo "  END_DATE        = $END_DATE"
echo "  TOP_K           = $TOP_K"
echo "  EXTRACTION_MODE = $EXTRACTION_MODE"
echo "  STRUCTURE_TYPES = $STRUCTURE_TYPES"
echo "  OUT_DIR         = $OUT_DIR"
echo "  REPO_ROOT       = $REPO_ROOT"
echo "  PYTHON          = $PYTHON"
echo "===================================================="
echo

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: python interpreter not found at $PYTHON"
    exit 1
fi

if [ ! -d "$REPO_ROOT" ]; then
    echo "ERROR: REPO_ROOT not found at $REPO_ROOT"
    exit 1
fi

if [ ! -f "$REPO_ROOT/src/run_pipeline.py" ]; then
    echo "ERROR: run_pipeline.py not found at $REPO_ROOT/src/run_pipeline.py"
    echo "Pull latest from GitHub on the cluster: cd $REPO_ROOT && git pull"
    exit 1
fi

cd "$REPO_ROOT/src"

# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Launching run_pipeline.py"

"$PYTHON" run_pipeline.py \
    --operations "$OPERATIONS" \
    --category "$CATEGORY" \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --top-k "$TOP_K" \
    --extraction-mode "$EXTRACTION_MODE" \
    --structure-types "$STRUCTURE_TYPES" \
    --out-dir "$OUT_DIR" \
    --verbose

RC=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] run_pipeline.py exited with code $RC"

# ----------------------------------------------------------------------------
# Quick summary
# ----------------------------------------------------------------------------

if [ -d "$OUT_DIR" ]; then
    N_JSON=$(find "$OUT_DIR" -name "*.json" 2>/dev/null | wc -l)
    echo
    echo "Output summary:"
    echo "  JSON files produced in $OUT_DIR: $N_JSON"
    if [ -f "$OUT_DIR/status_log.csv" ]; then
        echo "  Status log:"
        head -n 5 "$OUT_DIR/status_log.csv" || true
    fi
fi

exit $RC
