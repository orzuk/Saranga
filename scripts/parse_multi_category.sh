#!/bin/bash -l
#
# Parse multiple arXiv categories in parallel via SLURM array jobs.
#
# Usage:
#   # Default: 10 categories × 5000 papers each = 50K total
#   sbatch scripts/parse_multi_category.sh
#
#   # Smaller test run: 100 papers per category
#   sbatch --export=ALL,PAPERS_PER_CAT=100 scripts/parse_multi_category.sh
#
#   # Custom: 2000 papers, only recent (2023+), with visualization
#   sbatch --export=ALL,PAPERS_PER_CAT=2000,START_DATE=2023-01-01,OPERATIONS='parse,validate,anomalies,stats,visualize',HTML=1 \
#          scripts/parse_multi_category.sh
#
#   # Quick local test (no SLURM, sequential, 10 papers per category):
#   PAPERS_PER_CAT=10 bash scripts/parse_multi_category.sh
#
# Categories (10 total, covering pure math, theoretical CS, and stat/ML):
#
#   Pure mathematics:
#     math.CO  — Combinatorics (baseline, already tested)
#     math.PR  — Probability (PI's own field)
#     math.AG  — Algebraic Geometry (Stacks Project overlap, very formal)
#     math.NT  — Number Theory (classic results, strong Mathlib overlap)
#     math.LO  — Logic (depth-agenda calibration, consistency-strength)
#     math.GR  — Group Theory (strong Mathlib coverage)
#
#   Theoretical CS:
#     cs.DS   — Data Structures & Algorithms (FormulaOne connection)
#     cs.CC   — Computational Complexity (deep proofs, SETH-related)
#
#   Statistics / applied:
#     stat.ML  — Statistical Machine Learning (PI's background)
#     math.OC  — Optimization & Control (algorithms + theorems)
#
# Date sampling strategy:
#   Default: ALL dates (no filter). This gives a representative mix of
#   old and new papers. The top_k pre-filter sorts by ID descending
#   (newest first), so with PAPERS_PER_CAT=5000 you get the ~5000 most
#   recent papers in each category.
#
#   To restrict to recent papers only, set START_DATE:
#     --export=ALL,START_DATE=2020-01-01
#
#   To sample older papers, set both START_DATE and END_DATE:
#     --export=ALL,START_DATE=2010-01-01,END_DATE=2015-12-31
#
#SBATCH --job-name=authomath_multi
#SBATCH --output=logs/authomath_multi_%A_%a.out
#SBATCH --error=logs/authomath_multi_%A_%a.err
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --array=0-9

set -uo pipefail

# ============================================================================
# Configuration
# ============================================================================

# The 10 categories — order matches SLURM_ARRAY_TASK_ID 0-9
CATEGORIES=(
    math.CO    # 0
    math.PR    # 1
    math.AG    # 2
    math.NT    # 3
    math.LO    # 4
    math.GR    # 5
    cs.DS      # 6
    cs.CC      # 7
    stat.ML    # 8
    math.OC    # 9
)

PAPERS_PER_CAT=${PAPERS_PER_CAT:-5000}
START_DATE=${START_DATE:-}
END_DATE=${END_DATE:-}
EXTRACTION_MODE=${EXTRACTION_MODE:-manual}
OPERATIONS=${OPERATIONS:-parse,validate,anomalies,stats}
HTML=${HTML:-0}

# Base output directory. Each category gets a subdirectory.
BASE_OUT_DIR=${BASE_OUT_DIR:-/<cluster>/<user>/projects/Authomathics/arxiv/parsed_multi_category}

# Repo and scripts
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Python detection (same logic as parse_smoke_test.sh)
if [ -z "${PYTHON:-}" ]; then
    PYTHON=""
    if [ -n "${VIRTUAL_ENV:-}" ]; then
        for _cand in "$VIRTUAL_ENV/bin/python" "$VIRTUAL_ENV/bin/python3"; do
            if [ -x "$_cand" ]; then PYTHON="$_cand"; break; fi
        done
        if [ -z "$PYTHON" ]; then
            for _cand in "$VIRTUAL_ENV"/bin/python3.*; do
                if [ -x "$_cand" ]; then PYTHON="$_cand"; break; fi
            done
        fi
    fi
    if [ -z "$PYTHON" ] && [ -n "${CONDA_PREFIX:-}" ]; then
        for _cand in "$CONDA_PREFIX/bin/python" "$CONDA_PREFIX/bin/python3"; do
            if [ -x "$_cand" ]; then PYTHON="$_cand"; break; fi
        done
    fi
    if [ -z "$PYTHON" ]; then
        if command -v python3 >/dev/null 2>&1; then
            PYTHON="python3"
        elif command -v python >/dev/null 2>&1; then
            PYTHON="python"
        fi
    fi
    if [ -z "$PYTHON" ]; then
        echo "ERROR: no python interpreter found."
        exit 1
    fi
fi

# ============================================================================
# Pick category for this array task (or loop all if not in SLURM)
# ============================================================================

if [ -n "${SLURM_ARRAY_TASK_ID:-}" ]; then
    # SLURM array mode: process one category per task
    TASK_ID=$SLURM_ARRAY_TASK_ID
    if [ "$TASK_ID" -ge "${#CATEGORIES[@]}" ]; then
        echo "ERROR: SLURM_ARRAY_TASK_ID=$TASK_ID but only ${#CATEGORIES[@]} categories defined."
        exit 1
    fi
    RUN_CATEGORIES=("${CATEGORIES[$TASK_ID]}")
else
    # Non-SLURM mode: process all categories sequentially
    RUN_CATEGORIES=("${CATEGORIES[@]}")
fi

mkdir -p logs

# ============================================================================
# Process each category
# ============================================================================

for CATEGORY in "${RUN_CATEGORIES[@]}"; do
    # Category-specific output directory
    CAT_SAFE="${CATEGORY//./_}"  # math.CO -> math_CO
    OUT_DIR="${BASE_OUT_DIR}/${CAT_SAFE}"

    echo "===================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Category: $CATEGORY"
    echo "  PAPERS_PER_CAT  = $PAPERS_PER_CAT"
    echo "  START_DATE      = ${START_DATE:-<all>}"
    echo "  END_DATE        = ${END_DATE:-<all>}"
    echo "  EXTRACTION_MODE = $EXTRACTION_MODE"
    echo "  OPERATIONS      = $OPERATIONS"
    echo "  OUT_DIR         = $OUT_DIR"
    echo "  PYTHON          = $PYTHON"
    echo "===================================================="

    cd "$REPO_ROOT/src"

    # Build command
    CMD=(
        "$PYTHON" run_pipeline.py
        --operations "$OPERATIONS"
        --category "$CATEGORY"
        --top-k "$PAPERS_PER_CAT"
        --extraction-mode "$EXTRACTION_MODE"
        --out-dir "$OUT_DIR"
        --verbose
    )
    if [ -n "$START_DATE" ]; then
        CMD+=(--start "$START_DATE")
    fi
    if [ -n "$END_DATE" ]; then
        CMD+=(--end "$END_DATE")
    fi
    if [ "$HTML" = "1" ]; then
        CMD+=(--html)
    fi

    "${CMD[@]}"
    RC=$?

    echo
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $CATEGORY finished with exit code $RC"

    if [ -d "$OUT_DIR" ]; then
        N_JSON=$(find "$OUT_DIR" -name "*.json" -not -name "anomalies_report*" -not -name "validate_report*" -not -name "corpus_stats*" 2>/dev/null | wc -l)
        echo "  Papers extracted: $N_JSON"
        if [ -f "$OUT_DIR/corpus_stats.csv" ]; then
            echo "  Stats: $OUT_DIR/corpus_stats.csv"
        fi
        if [ -f "$OUT_DIR/anomalies_report.csv" ]; then
            N_FLAGGED=$(grep -vc "pass\|paper_id" "$OUT_DIR/anomalies_report.csv" 2>/dev/null || echo "0")
            echo "  Anomalies flagged: $N_FLAGGED"
        fi
    fi
    echo
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] All categories done."
