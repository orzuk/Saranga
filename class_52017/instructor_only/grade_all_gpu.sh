#!/bin/bash
#SBATCH --job-name=grade_all
#SBATCH --partition=catfish        # L4 24GB, enough for 8B models
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=grade_all_%j.log
#
# Grade ALL student submissions on the cluster vLLM server (free, unlimited) and
# build the leaderboard. Launches one vLLM server, runs grade_all.py over every
# submission, then shuts the server down.
#
# IMPORTANT: feed it ALREADY-DECRYPTED submissions (plaintext). Decrypt locally so
# your age private key never has to live on the cluster:
#     AGE_KEY=instructor_key.txt ./decrypt_submissions.sh submissions submissions_dec
#     rsync -a submissions_dec/ test_set/ <cluster>:<workdir>/...
# then on the cluster:  sbatch grade_all_gpu.sh
# ---------------------------------------------------------------------------

set -euo pipefail

# ===== CONFIG: set these paths for your cluster layout =====
COURSE_REPO="/sci/labs/orzuk/orzuk/github/BigDataProject_52017"   # holds src/run_all.py
INSTRUCTOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # this folder (grade_all.py, make_leaderboard.py)
SUBMISSIONS="${SUBMISSIONS:-submissions_dec}"                      # DECRYPTED submissions (one folder per pair)
OUT="${OUT:-results}"                                              # per-pair scores go here
TEST_DIR="${TEST_DIR:-}"                                           # set to a test_set/ dir to also grade the test split
SPLIT="${SPLIT:-train}"                                            # train | test | both
MODEL="${MODEL:-Qwen/Qwen3-8B}"                                    # vLLM serves ONE model; must match grade_all --model
LEADERBOARD="${LEADERBOARD:-$COURSE_REPO/LEADERBOARD.md}"          # publish straight into the course repo by default
RANK_BY="${RANK_BY:-test}"                                         # rank by test combined-F1 (train shown until test exists)
BOARD_TITLE="${BOARD_TITLE:-Big Data Project 52017 — Part 2 Leaderboard}"
NOTE="${NOTE:-Every pair starts at the baseline score. Submit your own annotate_chapter.py and your row updates with your real numbers. Final ranking uses the held-out test set (chapters 11-12 + 5 unseen papers).}"
VLLM_PORT=8000
VLLM_PID=""
# ==========================================================

cleanup() {
    [ -n "$VLLM_PID" ] && { echo "[grade_all] stopping vLLM ($VLLM_PID)"; kill $VLLM_PID 2>/dev/null || true; wait $VLLM_PID 2>/dev/null || true; }
}
trap cleanup EXIT

# --- environment ---
# Must be an env with vllm installed. Override on the command line if needed:
#   SHARED_ENV=/path/to/env  sbatch grade_all_gpu.sh
SHARED_ENV="${SHARED_ENV:-/sci/labs/orzuk/orzuk/venvs/llm}"
SHARED_HF_CACHE="${SHARED_HF_CACHE:-/sci/labs/orzuk/orzuk/trained_models/hf_cache}"
if [ -f "$SHARED_ENV/bin/activate" ]; then
    source "$SHARED_ENV/bin/activate"                       # plain venv
elif command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"    # conda env (init for batch shells)
    conda activate "$SHARED_ENV"
fi
export LD_LIBRARY_PATH="$SHARED_ENV/lib:${LD_LIBRARY_PATH:-}"
export HF_HOME="$SHARED_HF_CACHE"
echo "[grade_all] python: $(which python)"
# Fail fast with a clear message instead of hanging 10 min on a server that never starts.
python -c "import vllm" 2>/dev/null || {
    echo "[grade_all] ERROR: 'vllm' not importable in env: $SHARED_ENV"
    echo "[grade_all]   Set SHARED_ENV=/path/to/env-with-vllm and resubmit, e.g.:"
    echo "[grade_all]   SHARED_ENV=... SPLIT=both TEST_DIR=../test_set SUBMISSIONS=submissions_dec sbatch grade_all_gpu.sh"
    exit 1
}

# --- launch vLLM ---
echo "[grade_all] starting vLLM for $MODEL ..."
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" --port $VLLM_PORT \
    --max-model-len 32768 --gpu-memory-utilization 0.9 --trust-remote-code \
    > vllm_server.log 2>&1 &
VLLM_PID=$!
for i in $(seq 1 60); do
    curl -s "http://localhost:$VLLM_PORT/v1/models" >/dev/null 2>&1 && { echo "[grade_all] vLLM ready (~${i}0s)"; break; }
    sleep 10
done
export LLM_API_URL="http://localhost:$VLLM_PORT"

# --- grade everyone + build leaderboard ---
CMD=(python3 "$INSTRUCTOR_DIR/grade_all.py"
     --submissions "$SUBMISSIONS" --out "$OUT"
     --runner "$COURSE_REPO/src/run_all.py"
     --split "$SPLIT" --model "$MODEL" --leaderboard "$LEADERBOARD"
     --jobs "${JOBS:-4}" --rank-by "$RANK_BY" --board-title "$BOARD_TITLE")
[ -n "$TEST_DIR" ] && CMD+=(--test-dir "$TEST_DIR")
[ -n "$NOTE" ] && CMD+=(--note "$NOTE")
[ "${DEDUPE:-1}" = "1" ] && CMD+=(--dedupe)   # group identical submissions; safe always-on
echo "[grade_all] ${CMD[*]}"
"${CMD[@]}"

echo "[grade_all] done. Leaderboard: $LEADERBOARD"
