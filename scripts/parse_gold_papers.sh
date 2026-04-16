#!/bin/bash
#
# Parse, validate, visualize, and analyze Yaron's 10 gold-standard papers.
#
# These papers have manually annotated gold standards in
# src/LLMVersion/Gold_Standard_*.csv, so the extraction output can be
# directly compared to the gold. The tex files are already downloaded in
# src/LLMVersion/full_papers/.
#
# Usage:
#   ./scripts/parse_gold_papers.sh                    # all operations
#   OPERATIONS=validate,anomalies,stats \
#       ./scripts/parse_gold_papers.sh                # skip re-parsing
#   EXTRACTION_MODE=both ./scripts/parse_gold_papers.sh  # manual + LLM
#
# Output: gold_paper_output/ with JSONs, PNGs, HTMLs, and reports.

set -uo pipefail

# --- Configuration ---

OPERATIONS=${OPERATIONS:-parse,validate,anomalies,stats,visualize}
EXTRACTION_MODE=${EXTRACTION_MODE:-manual}
HTML=${HTML:-1}
OUT_DIR=${OUT_DIR:-./gold_paper_output}
TEX_DIR=${TEX_DIR:-}

# Normalize OUT_DIR to absolute
if [[ "$OUT_DIR" != /* ]]; then
    if command -v realpath >/dev/null 2>&1; then
        OUT_DIR="$(realpath -m "$OUT_DIR")"
    else
        OUT_DIR="$PWD/${OUT_DIR#./}"
    fi
fi

# The 10 gold-standard paper IDs
PAPER_IDS=(
    1204.0109v1
    1210.4634
    1405.2464v2
    1512.09272v2
    2208.03112v1
    2309.05826v1
    2312.16785
    2401.00367
    2505.12804v1
    2603.09769v1
)

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Auto-detect TEX_DIR if not set by the user
if [ -z "$TEX_DIR" ]; then
    _default_tex="$REPO_ROOT/src/LLMVersion/full_papers"
    if [ -d "$_default_tex" ]; then
        TEX_DIR="$_default_tex"
    fi
fi

# Python detection (same logic as other scripts)
if [ -z "${PYTHON:-}" ]; then
    PYTHON=""
    if [ -n "${VIRTUAL_ENV:-}" ]; then
        for _cand in "$VIRTUAL_ENV/bin/python" "$VIRTUAL_ENV/bin/python3"; do
            [ -x "$_cand" ] && PYTHON="$_cand" && break
        done
        if [ -z "$PYTHON" ]; then
            for _cand in "$VIRTUAL_ENV"/bin/python3.*; do
                [ -x "$_cand" ] && PYTHON="$_cand" && break
            done
        fi
    fi
    if [ -z "$PYTHON" ] && [ -n "${CONDA_PREFIX:-}" ]; then
        for _cand in "$CONDA_PREFIX/bin/python" "$CONDA_PREFIX/bin/python3"; do
            [ -x "$_cand" ] && PYTHON="$_cand" && break
        done
    fi
    [ -z "$PYTHON" ] && command -v python3 >/dev/null 2>&1 && PYTHON="python3"
    [ -z "$PYTHON" ] && command -v python >/dev/null 2>&1 && PYTHON="python"
    if [ -z "$PYTHON" ]; then echo "ERROR: no python found"; exit 1; fi
fi

echo "===================================================="
echo "Gold-standard papers pipeline"
echo "===================================================="
echo "  OPERATIONS      = $OPERATIONS"
echo "  EXTRACTION_MODE = $EXTRACTION_MODE"
echo "  HTML            = $HTML"
echo "  OUT_DIR         = $OUT_DIR"
echo "  PYTHON          = $PYTHON"
echo "  Papers (${#PAPER_IDS[@]}):"
for pid in "${PAPER_IDS[@]}"; do echo "    $pid"; done
echo "===================================================="
echo

cd "$REPO_ROOT/src"

# --- Step 1: Parse each paper by regex-id ---
# We loop because --regex-id accepts one pattern at a time, and parse_batch.py
# uses it to find the local tex file via _find_local_tex().
if [[ "$OPERATIONS" == *"parse"* ]]; then
    echo "[gold] ========== Parsing ${#PAPER_IDS[@]} papers =========="
    for i in "${!PAPER_IDS[@]}"; do
        pid="${PAPER_IDS[$i]}"
        n=$((i + 1))
        echo "[gold] parse: $pid [$n/${#PAPER_IDS[@]}]"
        _TEX_FLAG=()
        if [ -n "$TEX_DIR" ]; then
            _TEX_FLAG=(--tex-dir "$TEX_DIR")
        fi
        "$PYTHON" run_pipeline.py \
            --operations parse \
            --regex-id "^${pid}" \
            --extraction-mode "$EXTRACTION_MODE" \
            --out-dir "$OUT_DIR" \
            "${_TEX_FLAG[@]}" 2>&1 | grep -E "^\[OK\]|^\[WARN\]|^\[INFO\] _(extract|build|link)" || true
    done
    echo "[gold] parse done."
    echo
fi

# --- Step 2: Run remaining operations on all papers at once ---
# Strip "parse" from OPERATIONS for the batch run
REMAINING_OPS=$(echo "$OPERATIONS" | sed 's/parse,\?//; s/,$//')

if [ -n "$REMAINING_OPS" ]; then
    echo "[gold] ========== Running $REMAINING_OPS on all papers =========="

    CMD=("$PYTHON" run_pipeline.py --operations "$REMAINING_OPS" --out-dir "$OUT_DIR" --verbose)
    if [ "$HTML" = "1" ]; then
        CMD+=(--html)
    fi

    "${CMD[@]}"
    echo
fi

# --- Summary ---
echo "===================================================="
echo "[gold] Done."
N_JSON=$(find "$OUT_DIR" -name "*_manual.json" -o -name "*_anthropic.json" -o -name "*_openai.json" 2>/dev/null | wc -l)
echo "  Papers extracted: $N_JSON"

for report in anomalies_report.csv anomalies_detail.json corpus_stats.csv validate_report.csv; do
    if [ -f "$OUT_DIR/$report" ]; then
        echo "  $report: $OUT_DIR/$report"
    fi
done

if [ -f "$OUT_DIR/anomalies_report.csv" ]; then
    N_PASS=$(grep -c "pass" "$OUT_DIR/anomalies_report.csv" 2>/dev/null || echo 0)
    N_FLAG=$(grep -vc "pass\|paper_id" "$OUT_DIR/anomalies_report.csv" 2>/dev/null || echo 0)
    echo "  Anomalies: $N_FLAG flagged, $N_PASS clean"
fi
echo "===================================================="
