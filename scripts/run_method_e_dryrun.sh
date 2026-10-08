#!/bin/bash
# Method E dry-run on the full cluster corpus.
#
# Runs all phases except the LLM judge (Phase 2c) — uses --dry-run so the
# judge step substitutes stub NO verdicts, and --no-citations to skip the
# S2 fetch. Produces:
#   problems.jsonl  theorems.jsonl  dedup_clusters.jsonl
#   candidates.jsonl  judged_candidates.jsonl  (stubs)
#
# After the job completes, get the hand-review CSV with:
#   python3 -m discovery.method_e.export_triage \
#       --judged $RUN_DIR/judged_candidates.jsonl \
#       --out    $RUN_DIR/triage_all.csv \
#       --include YES,MAYBE,NO
#
# Tweak runtime via environment variables:
#   sbatch --export=TOP_K=3,SCORE_THRESHOLD=0.40 scripts/run_method_e_dryrun.sh
#
#SBATCH --job-name=me_dryrun
#SBATCH --time=4:00:00
#SBATCH --mem=48G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/me_dryrun_%j.out
#SBATCH --error=logs/me_dryrun_%j.err

export PYTHONHASHSEED=0   # deterministic output (see src/config.py)

set -euo pipefail

# ── Env ────────────────────────────────────────────────────────────────────
source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate

# ── Repo + working dir ────────────────────────────────────────────────────
CODE_DIR="${CODE_DIR:-/sci/labs/orzuk/orzuk/github/Saranga}"
cd "$CODE_DIR"
mkdir -p logs

# ── Tunables (overridable via --export=KEY=VAL,...) ──────────────────────
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)_v1}"
DATA_BASE="${DATA_BASE:-/sci/labs/orzuk/orzuk/projects/Authomathics}"
RUN_DIR="${RUN_DIR:-${DATA_BASE}/discovery/method_e/runs/${RUN_ID}}"
TOP_K="${TOP_K:-5}"
SCORE_THRESHOLD="${SCORE_THRESHOLD:-0.30}"
CATEGORIES_FLAG="${CATEGORIES_FLAG:-}"      # empty = all 20 categories
EXTRA_FLAGS="${EXTRA_FLAGS:-}"

mkdir -p "$RUN_DIR"

# ── Run ───────────────────────────────────────────────────────────────────
echo "=== Method E dry-run start  $(date)  on $(hostname) ==="
echo "    CODE_DIR=$CODE_DIR"
echo "    RUN_DIR=$RUN_DIR"
echo "    TOP_K=$TOP_K  SCORE_THRESHOLD=$SCORE_THRESHOLD"
echo "    CATEGORIES_FLAG='${CATEGORIES_FLAG}'  EXTRA_FLAGS='${EXTRA_FLAGS}'"
echo ""

cd "${CODE_DIR}/src"
python3 -m discovery.method_e.run all \
    --dry-run --no-citations \
    --run-dir "$RUN_DIR" \
    --top-k "$TOP_K" --score-threshold "$SCORE_THRESHOLD" \
    ${CATEGORIES_FLAG} ${EXTRA_FLAGS}

echo ""
echo "=== Method E dry-run done  $(date) ==="
echo "Outputs in $RUN_DIR :"
ls -lh "$RUN_DIR"
echo ""
echo "Next: re-export triage CSV including NO verdicts for hand review:"
echo "  python3 -m discovery.method_e.export_triage \\"
echo "      --judged $RUN_DIR/judged_candidates.jsonl \\"
echo "      --out    $RUN_DIR/triage_all.csv \\"
echo "      --include YES,MAYBE,NO"
