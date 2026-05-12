#!/bin/bash -l
#
# Parse 20 arXiv categories in parallel via SLURM array jobs.
# Supports TWO modes:
#   (A) FETCH mode (default): fetch papers from arxiv by category/date/top-k.
#   (B) LOCAL mode: if TEX_SRC_BASE is set, use pre-downloaded .tex files
#       from that directory instead of fetching. In this mode TOP_K,
#       START_DATE, END_DATE are ignored (all pre-downloaded papers parsed).
#
# Extends scripts/parse_multi_category.sh (10-category version) to 20
# categories. Default fetch mode: 20 × 5000 = 100K total for the main run.
# Local mode: process Author's pre-downloaded ~1200-paper calibration corpus.
#
# Usage:
#
#   # [FETCH] Full 20 × 5000 paper run, 2010-2019 corpus:
#   sbatch --export=ALL,PAPERS_PER_CAT=5000,START_DATE=2010-01-01,END_DATE=2019-12-31,BASE_OUT_DIR=/<cluster>/<user>/projects/Authomathics/arxiv/parsed_100k_2010s \
#          scripts/parse_multi_category_20.sh
#
#   # [LOCAL] 1200-paper calibration run on 10 pre-downloaded categories (slots 0-9):
#   # Pre-req: symlink exists at /sci/.../projects/Authomathics/arxiv/full_papers_advanced
#   sbatch --array=0-9 \
#          --export=ALL,TEX_SRC_BASE=/<cluster>/<user>/projects/Authomathics/arxiv/full_papers_advanced,BASE_OUT_DIR=/<cluster>/<user>/projects/Authomathics/arxiv/parsed_calibration_1200 \
#          scripts/parse_multi_category_20.sh
#
#   # [FETCH] Small smoke test: 100 papers per category:
#   sbatch --export=ALL,PAPERS_PER_CAT=100 scripts/parse_multi_category_20.sh
#
#   # [FETCH] Custom with visualization:
#   sbatch --export=ALL,PAPERS_PER_CAT=2000,START_DATE=2023-01-01,OPERATIONS='parse,validate,anomalies,stats,visualize',HTML=1 \
#          scripts/parse_multi_category_20.sh
#
#   # Quick local (no SLURM), 10 papers per category:
#   PAPERS_PER_CAT=10 bash scripts/parse_multi_category_20.sh
#
# Categories (20 total) — divided into the student's pure-math 10 (already
# downloaded in the advanced-download batch) plus 10 complementary categories
# that add analysis, CS theory, and stats/engineering coverage.
#
#   Student's pure-math 10 (slots 0-9, already downloaded):
#     math.CO   — Combinatorics (baseline, already tested)
#     math.AG   — Algebraic Geometry (Stacks Project overlap, very formal)
#     math.NT   — Number Theory (classic results, strong Mathlib overlap)
#     math.PR   — Probability (PI's own field)
#     math.AP   — Analysis of PDEs (estimates, Sobolev)
#     math.RT   — Representation Theory (deep algebraic content)
#     math.GR   — Group Theory (strong Mathlib coverage)
#     math.AT   — Algebraic Topology (homology, homotopy, complements math.AG)
#     math.LO   — Logic (depth calibration, consistency-strength)
#     math.DG   — Differential Geometry (Perelman/Ricci-flow style)
#
#   Complementary 10 (slots 10-19, for the 20-category expansion):
#
#   Analysis (3):
#     math.FA   — Functional Analysis (bridges pure-math and stat.ML via RKHS)
#     math.CA   — Classical / Harmonic Analysis (Kakeya, decoupling)
#     math-ph   — Mathematical Physics (quantum, stat mech, integrable systems)
#
#   Theoretical CS / ML (4):
#     cs.DS     — Data Structures & Algorithms
#     cs.CC     — Computational Complexity (deep proofs)
#     cs.LG     — Machine Learning (CS side; subsumes most stat.ML via cross-list)
#     cs.IT     — Information Theory (Shannon, coding, compressed sensing)
#
#   Stats / Optim / Numerical (3):
#     stat.TH   — Statistics Theory (concentration, minimax rates)
#     math.OC   — Optimization & Control (algorithms + theorems)
#     math.NA   — Numerical Analysis (convergence rates, error bounds, iterative
#                 methods, PDE solvers) — swapped in from eess.SP because
#                 eess.SP did not exist on arxiv pre-2017, incompatible with
#                 the 2010-2019 date range used for the 100K corpus.
#
# Date sampling strategy (same as 10-cat version):
#   Default: ALL dates. The top_k pre-filter sorts by ID descending (newest first).
#   Override with --export=ALL,START_DATE=2020-01-01 to restrict to recent papers.
#
#SBATCH --job-name=authomath_multi20
#SBATCH --output=logs/authomath_multi20_%A_%a.out
#SBATCH --error=logs/authomath_multi20_%A_%a.err
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --array=0-19

set -uo pipefail

# ============================================================================
# Configuration
# ============================================================================

# The 20 categories — order matches SLURM_ARRAY_TASK_ID 0-19
# Slots 0-9 match the "student set" of 10 pure-math categories already
# downloaded (Author's advanced-download batch). Slots 10-19 are the
# complement to reach 20 (analysis, CS theory, stats/engineering).
CATEGORIES=(
    # --- Slots 0-9: student's pure-math 10 (already downloaded) -----------
    math.CO    # 0   Combinatorics
    math.AG    # 1   Algebraic Geometry
    math.NT    # 2   Number Theory
    math.PR    # 3   Probability
    math.AP    # 4   Analysis of PDEs
    math.RT    # 5   Representation Theory
    math.GR    # 6   Group Theory
    math.AT    # 7   Algebraic Topology
    math.LO    # 8   Logic (math)
    math.DG    # 9   Differential Geometry
    # --- Slots 10-19: complementary 10 (analysis + CS + stats/eng) --------
    math.FA    # 10  Functional Analysis
    math.CA    # 11  Classical / Harmonic Analysis
    math-ph    # 12  Mathematical Physics
    cs.DS      # 13  Data Structures & Algorithms
    cs.CC      # 14  Computational Complexity
    cs.LG      # 15  Machine Learning (CS; subsumes stat.ML via cross-list)
    cs.IT      # 16  Information Theory
    stat.TH    # 17  Statistics Theory
    math.OC    # 18  Optimization & Control
    math.NA    # 19  Numerical Analysis (convergence rates, error bounds)
)

PAPERS_PER_CAT=${PAPERS_PER_CAT:-5000}
START_DATE=${START_DATE:-}
END_DATE=${END_DATE:-}
EXTRACTION_MODE=${EXTRACTION_MODE:-rules}
OPERATIONS=${OPERATIONS:-parse,validate,link,anomalies,stats}
HTML=${HTML:-0}
HTML_ONLY=${HTML_ONLY:-0}

# Optional: pre-downloaded local source (calibration / re-parse mode).
# If set, --tex-dir is passed to run_pipeline.py and fetch is skipped.
# Expected layout: $TEX_SRC_BASE/$CATEGORY/... (e.g. full_papers_advanced/math.CO/).
# If not set: default FETCH mode (fetch from arxiv by category + date range + top-k).
TEX_SRC_BASE=${TEX_SRC_BASE:-}

# Base output directory. Each category gets a subdirectory.
# Override via BASE_OUT_DIR env var (different default per mode).
if [ -n "$TEX_SRC_BASE" ]; then
    BASE_OUT_DIR=${BASE_OUT_DIR:-/<cluster>/<user>/projects/Authomathics/arxiv/parsed_local_tex}
else
    BASE_OUT_DIR=${BASE_OUT_DIR:-/<cluster>/<user>/projects/Authomathics/arxiv/parsed_multi_category_20}
fi

# Repo and scripts.
# Under SLURM, the script is COPIED to /var/spool/slurmd/job*/slurm_script,
# so $BASH_SOURCE[0] no longer points at the repo — it points at that temp
# copy. Fall back to $SLURM_SUBMIT_DIR (the dir from which sbatch was
# invoked) when running under SLURM. Users submitting from the repo root
# therefore get the correct REPO_ROOT automatically.
REPO_ROOT="${REPO_ROOT:-}"
if [ -z "$REPO_ROOT" ]; then
    if [ -n "${SLURM_JOB_ID:-}" ] && [ -n "${SLURM_SUBMIT_DIR:-}" ] \
            && [ -f "$SLURM_SUBMIT_DIR/src/run_pipeline.py" ]; then
        REPO_ROOT="$SLURM_SUBMIT_DIR"
    else
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
    fi
fi
if [ ! -f "$REPO_ROOT/src/run_pipeline.py" ]; then
    echo "ERROR: run_pipeline.py not found under REPO_ROOT=$REPO_ROOT"
    echo "       (You may need to set REPO_ROOT=... in the sbatch --export list,"
    echo "        or sbatch from the repo root directory.)"
    exit 1
fi

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
    CAT_SAFE="${CATEGORY//./_}"        # math.CO -> math_CO
    CAT_SAFE="${CAT_SAFE//-/_}"        # math-ph -> math_ph
    OUT_DIR="${BASE_OUT_DIR}/${CAT_SAFE}"

    # Resolve tex-dir for this category when in LOCAL mode
    TEX_DIR=""
    if [ -n "$TEX_SRC_BASE" ]; then
        # Try $CATEGORY (math.CO) first, then $CAT_SAFE (math_CO)
        if [ -d "$TEX_SRC_BASE/$CATEGORY" ]; then
            TEX_DIR="$TEX_SRC_BASE/$CATEGORY"
        elif [ -d "$TEX_SRC_BASE/$CAT_SAFE" ]; then
            TEX_DIR="$TEX_SRC_BASE/$CAT_SAFE"
        else
            echo "WARNING: local tex dir not found for $CATEGORY at either"
            echo "  $TEX_SRC_BASE/$CATEGORY   or  $TEX_SRC_BASE/$CAT_SAFE"
            echo "  Falling back to TEX_SRC_BASE itself; run_pipeline.py will"
            echo "  search the whole tree for matching arxiv IDs."
            TEX_DIR="$TEX_SRC_BASE"
        fi
    fi

    echo "===================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Category: $CATEGORY"
    if [ -n "$TEX_SRC_BASE" ]; then
        echo "  MODE            = LOCAL (pre-downloaded tex)"
        echo "  TEX_DIR         = $TEX_DIR"
    else
        echo "  MODE            = FETCH (arxiv API)"
        echo "  PAPERS_PER_CAT  = $PAPERS_PER_CAT"
        echo "  START_DATE      = ${START_DATE:-<all>}"
        echo "  END_DATE        = ${END_DATE:-<all>}"
    fi
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
        --extraction-mode "$EXTRACTION_MODE"
        --out-dir "$OUT_DIR"
        --verbose
    )
    if [ -n "$TEX_SRC_BASE" ]; then
        # LOCAL mode: point at pre-downloaded tex; no fetch-related args
        CMD+=(--tex-dir "$TEX_DIR")
    else
        # FETCH mode: top-k + optional date range
        CMD+=(--top-k "$PAPERS_PER_CAT")
        if [ -n "$START_DATE" ]; then
            CMD+=(--start "$START_DATE")
        fi
        if [ -n "$END_DATE" ]; then
            CMD+=(--end "$END_DATE")
        fi
    fi
    if [ "$HTML_ONLY" = "1" ]; then
        CMD+=(--html-only)
    elif [ "$HTML" = "1" ]; then
        CMD+=(--html)
    fi
    if [ -n "${SAFEGUARD:-}" ]; then
        CMD+=(--safeguard "$SAFEGUARD")
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
