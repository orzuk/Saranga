#!/bin/bash
# run_fp_panel_cluster.sh — serve ONE open-weight judge and run it over the
# held-out M3 false positives, then shut the server down again.
#
# The server and the client live in the same job on purpose. Launching vLLM,
# reading the node name out of a log, exporting a base URL and remembering to
# scancel afterwards is four chances to leave a 4-GPU allocation idle for the
# rest of a 24h reservation. Here the judge run IS the job: when it finishes,
# the GPUs come back.
#
# Usage (one per judge; each needs the card to itself):
#   sbatch --gres=gpu:l40s:1 scripts/run_fp_panel_cluster.sh qwen3-32b-awq
#   sbatch --gres=gpu:l40s:2 scripts/run_fp_panel_cluster.sh mistral-small-24b
#   sbatch --gres=gpu:l40s:2 scripts/run_fp_panel_cluster.sh gemma-3-27b-it
#   sbatch --gres=gpu:l40s:4 scripts/run_fp_panel_cluster.sh llama-3.3-70b
#
# The --gres must match the model's row below; weights land in VRAM at roughly
# their on-disk size and still need room for the KV cache (see
# launch_qwen_judge_server.sh for the per-card arithmetic).

#SBATCH --job-name=fp_panel
#SBATCH --partition=salmon
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --time=12:00:00
#SBATCH --output=logs/fp_panel.%j.log
#SBATCH --error=logs/fp_panel.%j.log

set -euo pipefail

JUDGE="${1:?usage: $0 <qwen3-32b-awq|mistral-small-24b|gemma-3-27b-it|llama-3.3-70b>}"
REPO="${FP_PANEL_REPO:-/sci/labs/orzuk/yaron.otmazgin/Authomathics}"
EVAL_DIR="$REPO/src/LLMVersion/heldout_eval_selected146"
FPS="$EVAL_DIR/heldout_fp_m3.csv"
PORT="${FP_PANEL_PORT:-8${RANDOM:0:3}}"

# model key -> HF id, tensor-parallel size. TP must equal the --gres count.
case "$JUDGE" in
  qwen3-32b-awq)      MODEL=Qwen/Qwen3-32B-AWQ;                        TP=1 ;;
  mistral-small-24b)  MODEL=mistralai/Mistral-Small-24B-Instruct-2501; TP=2 ;;
  gemma-3-27b-it)     MODEL=google/gemma-3-27b-it;                     TP=2 ;;
  llama-3.3-70b)      MODEL=meta-llama/Llama-3.3-70B-Instruct;         TP=4 ;;
  *) echo "unknown judge: $JUDGE" >&2; exit 2 ;;
esac

source /sci/labs/orzuk/orzuk/venvs/qwen-vllm/bin/activate
# HF_HOME stays on the shared weights -- they only need reading, and every
# account should hit the same download rather than its own copy.
export HF_HOME="${HF_HOME:-/sci/labs/orzuk/orzuk/foundation_models/hf}"

# Everything below is WRITTEN during load: the model-info cache, the torch
# compile cache, triton and inductor artefacts. Hardcoding orzuk's paths meant
# any other account died mid-load with EACCES -- twice over, once in the
# registry cache and again deeper in torch_compile_cache, each a full model
# load wasted before it failed. Default them per user instead.
_FP_CACHE_HOME="${XDG_CACHE_HOME:-/sci/labs/orzuk/$USER/xdg-cache}"
export XDG_CACHE_HOME="$_FP_CACHE_HOME"
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$_FP_CACHE_HOME/vllm}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-$_FP_CACHE_HOME/triton}"
export TORCH_INDUCTOR_CACHE_DIR="${TORCH_INDUCTOR_CACHE_DIR:-$_FP_CACHE_HOME/torchinductor}"
export TMPDIR="${TMPDIR:-/sci/labs/orzuk/$USER/tmp}"
mkdir -p "$VLLM_CACHE_ROOT" "$TRITON_CACHE_DIR" "$TORCH_INDUCTOR_CACHE_DIR" "$TMPDIR"
export HF_HUB_ENABLE_HF_TRANSFER=1
umask 002

echo "[panel] judge=$JUDGE model=$MODEL tp=$TP node=$(hostname) port=$PORT"

python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" --served-model-name "$JUDGE" \
  --host 127.0.0.1 --port "$PORT" \
  --tensor-parallel-size "$TP" \
  --gpu-memory-utilization 0.90 --max-model-len 32768 \
  --dtype auto --trust-remote-code &
SERVER=$!
# Kill the server on ANY exit path, including a failed judge run: an sbatch
# job that ends with vLLM still resident holds the GPUs until the walltime.
trap 'kill $SERVER 2>/dev/null || true' EXIT

for i in $(seq 1 180); do
  if curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
    echo "[panel] server up after ${i}0s"; break
  fi
  kill -0 $SERVER 2>/dev/null || { echo "[panel] server died during load"; exit 1; }
  sleep 10
done
curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null || { echo "[panel] server never became ready"; exit 1; }

# The judge venv is not the repo venv; run the client with the repo's python so
# the parser imports resolve.
"${FP_PANEL_PY:-$REPO/src/LLMVersion/venv/bin/python}" \
  "$REPO/scripts/fp_panel_judge.py" \
  --fps "$FPS" --model "$JUDGE" \
  --base-url "http://127.0.0.1:$PORT/v1" \
  --match-mode m3 --batch-size 5 --concurrency 16 --repair-missing

echo "[panel] done: $EVAL_DIR/panel/fp_panel_$JUDGE.csv"
