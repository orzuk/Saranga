#!/bin/bash -l
#
# Tier C — Hand-gold evaluation. Grade silver-gold (or any extracted)
# JSONs against the ~10 hand-annotated reference JSONs in gold/.
#
# Thin wrapper around src/run_pipeline.py. The "eval" operation runs a
# T1 grading pass: matches predicted nodes/edges to gold via the same
# greedy matcher used for consensus, then reports per-paper precision /
# recall / F1.
#
# Usage:
#   scripts/run_gold_eval.sh                                # default gold dir
#   GOLD_DIR=/abs/path/to/gold scripts/run_gold_eval.sh
#   scripts/run_gold_eval.sh --paper-ids 1710.08249v2,1801.07186v3
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GOLD_DIR=${GOLD_DIR:-$REPO_ROOT/gold}
PRED_DIR=${PRED_DIR:-$REPO_ROOT/gold_paper_output}
OUT_DIR=${OUT_DIR:-$PRED_DIR}
OPERATIONS=${OPERATIONS:-validate,eval}
PYTHON=${PYTHON:-python3}

CMD=(
    "$PYTHON" "$REPO_ROOT/src/run_pipeline.py"
    --operations "$OPERATIONS"
    --extract-mode regex
    --gold-dir "$GOLD_DIR"
    --out-dir "$OUT_DIR"
)

echo "[run_gold_eval] ${CMD[*]} $*"
"${CMD[@]}" "$@"
