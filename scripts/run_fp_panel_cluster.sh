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

EXTRA_LOAD=""

# model key -> HF id, tensor-parallel size. TP must equal the --gres count.
case "$JUDGE" in
  qwen3-32b-awq)      MODEL=Qwen/Qwen3-32B-AWQ;                        TP=1 ;;
  # Mistral ships params.json alongside the HF shards, and vLLM reads that as
  # "this is a Mistral-format checkpoint", then goes looking for
  # consolidated.safetensors. The cache has the ten HF shards, complete, but
  # not that file -- so it silently started a 28GB download, filled the lab
  # quota and died at model load every time. Force the loader onto the shards
  # that are already there.
  # Mistral needs two overrides that none of the other judges do, both caused
  # by files it ships alongside the standard HF ones:
  #   params.json  -> vLLM reads it as a Mistral-format checkpoint and hunts
  #                   for consolidated.safetensors, which the cache does not
  #                   have, so it began a 28GB download that filled the shared
  #                   quota and killed the job at load with no error.
  #   tekken.json  -> vLLM switches to Mistral's own tokenizer, whose
  #                   validate_request_params rejects any chat template, so
  #                   every /v1/chat/completions request came back 400.
  # The HF shards and tokenizer.json are both present and complete; point the
  # loader and the tokenizer at those instead.
  mistral-small-24b)  MODEL=mistralai/Mistral-Small-24B-Instruct-2501; TP=2
                      EXTRA_LOAD="--load-format safetensors --tokenizer-mode slow" ;;
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
echo "[panel] extra_load=${EXTRA_LOAD:-none}"

# A partial blob means a previous run started fetching a file the cache does
# not have. Left in place it is both dead weight against the lab quota and a
# download that will simply restart.
_INC=$(find "$HF_HOME/hub" -name '*.incomplete' -size +1G 2>/dev/null | head -5)
if [ -n "$_INC" ]; then
  echo "[panel] WARNING: partial downloads >1G still in the HF cache:"
  echo "$_INC" | sed 's/^/    /'
  echo "[panel] delete them before rerunning, or they will be fetched again"
fi

# torch in this venv is built against CUDA 13.0 and the cluster's newest
# module is 12.9, so there is no nvcc that matches. vLLM only needs one to
# JIT-compile kernels, and --enforce-eager skips both torch.compile and
# CUDA-graph capture, so it never looks. Generation is somewhat slower, which
# does not matter for ~1,900 short verdicts. An account with a usable toolkit
# can set FP_PANEL_EAGER=0 to get the compiled path back.
# flashinfer JIT-compiles its sampling kernels on first use (top_k_mask_logits),
# and that path needs nvcc no matter what --enforce-eager does -- it is not
# torch.compile. Fall back to vLLM's native PyTorch sampler, which is already
# what the judge's near-greedy decoding wants and compiles nothing.
export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"

EAGER_FLAG=""
[ "${FP_PANEL_EAGER:-1}" = "1" ] && EAGER_FLAG="--enforce-eager"
echo "[panel] eager=${FP_PANEL_EAGER:-1} flashinfer_sampler=$VLLM_USE_FLASHINFER_SAMPLER"
echo "[panel] torch cuda=$(python -c 'import torch;print(torch.version.cuda)') (cluster modules top out at 12.9, hence no JIT)"

# shellcheck disable=SC2086
python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" --served-model-name "$JUDGE" \
  --host 127.0.0.1 --port "$PORT" \
  --tensor-parallel-size "$TP" \
  --gpu-memory-utilization 0.90 --max-model-len 32768 \
  --dtype auto --trust-remote-code $EAGER_FLAG $EXTRA_LOAD &
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
