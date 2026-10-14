#!/bin/bash -l
#
# Quick smoke test for the unified pipeline.
# Parses 5 math.CO papers in rules mode via src/run_pipeline.py, no SLURM,
# no LLM API cost. Use this to verify the pipeline works end-to-end before
# submitting the full cluster job.
#
# Usage:
#   ./scripts/parse_smoke_test.sh               # 5 papers, rules mode
#   TOP_K=20 ./scripts/parse_smoke_test.sh      # 20 papers
#   CATEGORY=math.PR ./scripts/parse_smoke_test.sh   # different category
#   OUT_DIR=./my_test ./scripts/parse_smoke_test.sh  # custom output dir
#
# On the cluster, you can also submit this via sbatch with env vars:
#   sbatch scripts/parse_multi_category_20.sh   (the full 100K run)
#

# Strict mode: catch undefined variables and pipefailures, but NOT set -e
# (set -e is fragile around command substitution and the python-detection
# block below; explicit error handling is used instead).
set -uo pipefail

CATEGORY=${CATEGORY:-math.CO}
TOP_K=${TOP_K:-5}
OUT_DIR=${OUT_DIR:-./smoke_test_out}
EXTRACTION_MODE=${EXTRACTION_MODE:-rules}
OPERATIONS=${OPERATIONS:-parse}
START_DATE=${START_DATE:-}
END_DATE=${END_DATE:-}
HTML=${HTML:-0}

# Normalize OUT_DIR to an absolute, clean path right now, BEFORE we cd
# anywhere. Otherwise a relative OUT_DIR like "./smoke_test_out" would
# resolve relative to the repo's src/ directory after the `cd "$REPO_ROOT/src"`
# below, putting outputs one level deeper than the user expected.
if [[ "$OUT_DIR" != /* ]]; then
    if command -v realpath >/dev/null 2>&1; then
        # realpath -m allows non-existent target paths (we may be creating
        # the output dir fresh). Produces a clean absolute path.
        OUT_DIR="$(realpath -m "$OUT_DIR")"
    else
        # Fallback: strip any leading "./" and prepend $PWD
        OUT_DIR="$PWD/${OUT_DIR#./}"
    fi
fi

# Resolve repo root from this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Pick a Python interpreter. Priority:
#   1. $PYTHON env var (explicit override)
#   2. $VIRTUAL_ENV/bin/{python,python3,python3.X}
#   3. $CONDA_PREFIX/bin/{python,python3}
#   4. python3 / python on PATH
#
# Recommended: activate your venv before running.
#   source /<cluster>/$USER/venvs/your-venv/bin/activate
#   ./scripts/parse_smoke_test.sh
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
            # Try any python3.X in the venv bin (glob; expands to literal if no match)
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

echo "===================================================="
echo "Authomathics smoke test"
echo "===================================================="
echo "  OPERATIONS      = $OPERATIONS"
echo "  CATEGORY        = $CATEGORY"
echo "  TOP_K           = $TOP_K"
echo "  START_DATE      = ${START_DATE:-<none>}"
echo "  END_DATE        = ${END_DATE:-<none>}"
echo "  EXTRACTION_MODE = $EXTRACTION_MODE"
echo "  HTML            = $HTML"
echo "  OUT_DIR         = $OUT_DIR"
echo "  REPO_ROOT       = $REPO_ROOT"
echo "  PYTHON          = $PYTHON"
echo "===================================================="
echo

cd "$REPO_ROOT/src"

# Build the command line with only the flags that apply
CMD=(
    "$PYTHON" run_pipeline.py
    --operations "$OPERATIONS"
    --category "$CATEGORY"
    --top-k "$TOP_K"
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
