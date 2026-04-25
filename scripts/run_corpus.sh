#!/bin/bash -l
#
# Tier A — Corpus driver. Per-type regex extraction over the ~50K-paper
# arXiv math corpus. Cheap, scalable; no LLM cost.
#
# This is a thin wrapper around src/run_pipeline.py — all dispatcher
# logic lives there. This wrapper only encodes Tier A defaults
# (extract-mode = regex; operations = parse,validate,anomalies,stats,link).
#
# Usage:
#   scripts/run_corpus.sh                                   # 500 math.CO papers
#   CATEGORY=math.PR TOP_K=2000 scripts/run_corpus.sh       # custom slice
#   scripts/run_corpus.sh --regex-id '^2501\.'              # passthrough flags
#
# Override any default with an env var or pass-through CLI arg ("$@").
set -uo pipefail

CATEGORY=${CATEGORY:-math.CO}
TOP_K=${TOP_K:-500}
START_DATE=${START_DATE:-2024-01-01}
END_DATE=${END_DATE:-}
OUT_DIR=${OUT_DIR:-./corpus_out}
OPERATIONS=${OPERATIONS:-parse,validate,anomalies,stats,link}
EXTRACTION_MODE=${EXTRACTION_MODE:-manual}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON=${PYTHON:-python3}

CMD=(
    "$PYTHON" "$REPO_ROOT/src/run_pipeline.py"
    --operations "$OPERATIONS"
    --extract-mode regex
    --extraction-mode "$EXTRACTION_MODE"
    --category "$CATEGORY"
    --top-k "$TOP_K"
    --start "$START_DATE"
    --out-dir "$OUT_DIR"
)
if [ -n "$END_DATE" ]; then
    CMD+=(--end "$END_DATE")
fi

echo "[run_corpus] ${CMD[*]} $*"
"${CMD[@]}" "$@"
