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

# Strict mode: catch undefined variables and pipefailures, but NOT set -e
# (set -e is fragile around the python-detection block below).
set -uo pipefail

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
OUT_DIR=${OUT_DIR:-/<cluster>/<user>/projects/Authomathics/arxiv/parsed_${CATEGORY//./_}_${EXTRACTION_MODE}_${TOP_K}}

# Code
REPO_ROOT=${REPO_ROOT:-/<cluster>/<user>/github/Authomathics}

# Python interpreter. Priority:
#   1. $PYTHON env var (via sbatch --export=PYTHON=/path/to/python)
#   2. $VIRTUAL_ENV/bin/python (if venv is activated in the submitting shell)
#   3. $CONDA_PREFIX/bin/python (if conda env is active in submitting shell)
#   4. python3 / python on PATH
#
# Recommended workflow on the cluster:
#   source /<cluster>/$USER/venvs/your-venv/bin/activate
#   sbatch scripts/parse_math_co_cluster.sh
# SLURM inherits VIRTUAL_ENV from the submitting shell, so the venv stays
# active inside the job.
if [ -z "${PYTHON:-}" ]; then
    PYTHON=""

    # Try $VIRTUAL_ENV/bin
    if [ -n "${VIRTUAL_ENV:-}" ]; then
        for _cand in "$VIRTUAL_ENV/bin/python" "$VIRTUAL_ENV/bin/python3"; do
            if [ -x "$_cand" ]; then
                PYTHON="$_cand"
                break
            fi
        done
        if [ -z "$PYTHON" ]; then
            for _cand in "$VIRTUAL_ENV"/bin/python3.*; do
                if [ -x "$_cand" ]; then
                    PYTHON="$_cand"
                    break
                fi
            done
        fi
    fi

    # Fall back to $CONDA_PREFIX/bin
    if [ -z "$PYTHON" ] && [ -n "${CONDA_PREFIX:-}" ]; then
        for _cand in "$CONDA_PREFIX/bin/python" "$CONDA_PREFIX/bin/python3"; do
            if [ -x "$_cand" ]; then
                PYTHON="$_cand"
                break
            fi
        done
    fi

    # Fall back to PATH
    if [ -z "$PYTHON" ]; then
        if command -v python3 >/dev/null 2>&1; then
            PYTHON="python3"
        elif command -v python >/dev/null 2>&1; then
            PYTHON="python"
        fi
    fi

    if [ -z "$PYTHON" ]; then
        echo "ERROR: no python interpreter found. Set PYTHON env var or install python."
        exit 1
    fi
fi

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
