#!/bin/bash
# run_method_e_smoke.sh — Phase A smoke test for Method E on 5 categories
# with a real LLM judge (Qwen via local vLLM server).
#
# Differs from run_method_e_dryrun.sh in that:
#   - Uses --no-citations OFF (citation-novelty filter active) — requires
#     S2 cache to be populated first via run_s2_fetch.sh.
#   - Real LLM judge call (not --dry-run); model = qwen via local server.
#   - Restricted to 5 categories to keep wall-clock small (~1h).
#
# PREREQUISITES (must be done in order):
#   1. sbatch scripts/run_foundation_audit.sh    (confirm linker gate ≥30%)
#   2. sbatch scripts/run_relink_v2.sh           (re-link v2 against 137-book index)
#   3. sbatch scripts/launch_qwen_judge_server.sh — note the node it lands on
#      (look at the launch log for the hostname).
#   4. Method E index phases write problems.jsonl + theorems.jsonl;
#      ALTERNATIVELY just run this script which does phases 1L/1R first.
#   5. sbatch scripts/run_s2_fetch.sh (can run in parallel with this script).
#
# Then: export QWEN_HOST=<host>; sbatch scripts/run_method_e_smoke.sh
#
# Env vars:
#   QWEN_HOST    — hostname where the Qwen vLLM server is running (REQUIRED)
#   QWEN_PORT    — port (default 8000)
#   RUN_ID       — output dir suffix (default v2_smoke_YYYYMMDD_HHMMSS)
#   CATEGORIES   — comma-sep cats (default math_CO,math_NT,math_AG,cs_CC,stat_TH)
#   TOP_K        — top-K per problem (default 30)
#
# Output: $RUN_DIR/triage_cases.csv  (sorted, top hand-review candidates)

#SBATCH --job-name=me_smoke
#SBATCH --partition=glacier
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=/sci/home/orzuk/method_e_jobs/me_smoke.%j.log
#SBATCH --error=/sci/home/orzuk/method_e_jobs/me_smoke.%j.log

export PYTHONHASHSEED=0   # deterministic output (see src/config.py)

set -euo pipefail

mkdir -p "$HOME/method_e_jobs" "$HOME/method_e_runs" "$HOME/method_e_cache"

source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
cd /sci/labs/orzuk/orzuk/github/Saranga

# Required: where the Qwen vLLM server is listening
if [ -z "${QWEN_HOST:-}" ]; then
  echo "[me_smoke] ERROR: QWEN_HOST not set. Export it before sbatch:"
  echo "[me_smoke]   export QWEN_HOST=<node from launch_qwen_judge_server log>"
  echo "[me_smoke]   sbatch scripts/run_method_e_smoke.sh"
  exit 2
fi

QWEN_PORT="${QWEN_PORT:-8000}"
export LLM_LOCAL_BASE_URL="http://${QWEN_HOST}:${QWEN_PORT}/v1"
export LLM_LOCAL_API_KEY="dummy"

# Tunables
RUN_ID="${RUN_ID:-v2_smoke_$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="${RUN_DIR:-$HOME/method_e_runs/${RUN_ID}}"
CATEGORIES="${CATEGORIES:-math_CO,math_NT,math_AG,cs_CC,stat_TH}"
TOP_K="${TOP_K:-30}"
S2_CACHE="${S2_CACHE:-$HOME/method_e_cache/s2_cache.sqlite}"

mkdir -p "$RUN_DIR"

echo "[me_smoke] === Method E smoke test ==="
echo "[me_smoke] run_dir    = $RUN_DIR"
echo "[me_smoke] categories = $CATEGORIES"
echo "[me_smoke] top_k      = $TOP_K"
echo "[me_smoke] judge URL  = $LLM_LOCAL_BASE_URL"
echo "[me_smoke] s2 cache   = $S2_CACHE"
echo "[me_smoke] starting at $(date) on $(hostname)"
echo ""

# qwen judge model — must match what's loaded on the vLLM server.
# 'qwen' is aliased in config.SOURCES; provider sniff routes to 'local'.
python -m src.discovery.method_e.run all \
  --run-dir "$RUN_DIR" \
  --categories "$CATEGORIES" \
  --top-k "$TOP_K" \
  --model qwen \
  ${S2_API_KEY:+--s2-api-key "$S2_API_KEY"}

echo ""
echo "[me_smoke] === Done at $(date) ==="
ls -lh "$RUN_DIR"
echo ""
echo "Triage CSV (sorted): $RUN_DIR/triage_cases.csv"
echo "Hand-review top YES + non-citing candidates first."
