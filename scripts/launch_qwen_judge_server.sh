#!/bin/bash
# launch_qwen_judge_server.sh — spin up a vLLM OpenAI-compatible server
# for an open-weight Qwen model on a HUJI GPU node.
#
# Method E's LLM judge talks to this via OpenAI SDK with a custom base_url.
# Free compute (1 H100) replaces $2-3k of Sonnet API spend per Method E run.
#
# Usage:
#   sbatch scripts/launch_qwen_judge_server.sh
#
# After launch, find the node and port, then on the client side:
#   export LLM_LOCAL_BASE_URL=http://<node>:8000/v1
#   python -m src.discovery.method_e.run judge --judge-model qwen ...
#
# The first run downloads weights (~16-60 GB depending on quant + size) to
# the HF cache, then loads in memory. Subsequent runs reuse the cache.

#SBATCH --job-name=qwen_judge
# HUJI cluster: 'gpu' partition doesn't exist; use salmon (l40s, 48GB) as
# the default. Override via sbatch --partition=<other> if needed.
#   l4    -> catfish (24GB; tight for 32B AWQ-int4 but works)
#   l40s  -> salmon  (48GB; comfortable; current default)
#   a100  -> dogfish (80GB; overkill; often drained anyway)
#   h200  -> goldfish (way overkill)
#
# GPU COUNT: weights land in VRAM roughly at their on-disk size, so a card
# holds a model only if it also leaves room for the KV cache. On l40s (48GB):
#   qwen3-32b-awq       18GB  -> 1 GPU   (4-bit; the default here)
#   mistral-small-24b   44GB  -> 2 GPUs  (bf16; 44 clears 48 only on paper)
#   gemma-3-27b-it      51GB  -> 2 GPUs  (bf16)
#   llama-3.3-70b      132GB  -> 4 GPUs  (bf16)
# Pass BOTH the allocation and the split, and keep them equal:
#   TP=2 sbatch --gres=gpu:l40s:2 scripts/launch_qwen_judge_server.sh
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=/sci/labs/orzuk/orzuk/method_e_jobs/qwen_judge.%j.log
#SBATCH --error=/sci/labs/orzuk/orzuk/method_e_jobs/qwen_judge.%j.log

export PYTHONHASHSEED=0   # deterministic output (see src/config.py)

set -euo pipefail

mkdir -p /sci/labs/orzuk/orzuk/method_e_jobs

# Model — pick a size that fits the GPU you got. Defaults to Qwen3-32B AWQ.
# Real model IDs on HuggingFace (verified 2026-05-21):
#   Qwen/Qwen3-32B                           (~64 GB FP16; needs H100 80GB)
#   Qwen/Qwen3-32B-AWQ                       (~16-20 GB AWQ-int4; fits L40s/A100/H100)
#   Qwen/Qwen3-32B-FP8                       (~32 GB FP8; needs A100 40GB+)
#   Qwen/Qwen3-14B                           (~28 GB FP16; A100 40GB)
#   Qwen/Qwen2.5-32B-Instruct-AWQ            (older but solid; ~16 GB)
# (Older 'Qwen/Qwen3-32B-Instruct-AWQ-int4' name was wrong — that exact
#  ID does not exist on HF; the verified AWQ path is Qwen3-32B-AWQ.)
#
# `--served-model-name` lets the client refer to a friendly alias
# (e.g. 'qwen3-32b-awq-int4') without needing to match the real HF model ID.
MODEL="${QWEN_MODEL:-Qwen/Qwen3-32B-AWQ}"
# The client picks its provider by sniffing this name (llm_judge._provider_for),
# so it has to keep the vendor prefix -- 'gemma-3-27b' routes local, 'judge-2'
# raises. It is otherwise free-form and need not match the HF id.
SERVED_AS="${QWEN_SERVED_NAME:-qwen3-32b-awq-int4}"
# Number of GPUs to shard the weights over; must equal the --gres count.
TP="${TP:-1}"
PORT="${QWEN_PORT:-8000}"
HOST="0.0.0.0"

# Use the dedicated qwen-vllm venv (vllm + flashinfer + torch + nvidia
# libs together are too heavy for the shared authomathics-venv). Set up
# once via scripts in /sci/labs/orzuk/orzuk/method_e_jobs/install_vllm.sh.
source /sci/labs/orzuk/orzuk/venvs/qwen-vllm/bin/activate

# All caches and scratch on the lab disk. The 5GB /sci/home/orzuk quota
# is far too small for vLLM's combined caches (model weights + Triton
# compile cache + PyTorch inductor cache + vLLM modelinfo registry +
# tmp wheel extraction). Each of these needs its own env override —
# vLLM reads XDG_CACHE_HOME for the generic cache root but Triton and
# torch.inductor have their own variables. HF_HOME alone is not enough.
export HF_HOME="${HF_HOME:-/sci/labs/orzuk/orzuk/foundation_models/hf}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/sci/labs/orzuk/orzuk/xdg-cache}"
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-/sci/labs/orzuk/orzuk/xdg-cache/vllm}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-/sci/labs/orzuk/orzuk/xdg-cache/triton}"
export TORCH_INDUCTOR_CACHE_DIR="${TORCH_INDUCTOR_CACHE_DIR:-/sci/labs/orzuk/orzuk/xdg-cache/torchinductor}"
export TMPDIR="${TMPDIR:-/sci/labs/orzuk/orzuk/tmp_install}"
mkdir -p "$HF_HOME" "$XDG_CACHE_HOME" "$VLLM_CACHE_ROOT" "$TRITON_CACHE_DIR" "$TORCH_INDUCTOR_CACHE_DIR" "$TMPDIR"

# Optional: speed up downloads on first run
export HF_HUB_ENABLE_HF_TRANSFER=1

# Files written into the shared model tree must stay group-writable, or the
# next person to touch this cache is locked out of it.
umask 002

echo "[launch_qwen] node=$(hostname) port=$PORT"
echo "[launch_qwen] model=$MODEL  served_as=$SERVED_AS  tp=$TP"
echo "[launch_qwen] HF_HOME=$HF_HOME"
echo "[launch_qwen] starting vLLM server at $(date)"
echo "[launch_qwen]"
echo "[launch_qwen] On the client side, point at:"
echo "[launch_qwen]   export LLM_LOCAL_BASE_URL=http://$(hostname):$PORT/v1"
echo "[launch_qwen]"

# vLLM serves the OpenAI-compatible API. --served-model-name lets clients
# call the model by the friendly alias rather than the HF ID.
python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --served-model-name "$SERVED_AS" \
  --host "$HOST" \
  --port "$PORT" \
  --tensor-parallel-size "$TP" \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --dtype auto \
  --trust-remote-code

# NOTE: one-time install (done 2026-05-21):
#   sbatch /sci/labs/orzuk/orzuk/method_e_jobs/install_vllm.sh
# Creates /sci/labs/orzuk/orzuk/venvs/qwen-vllm with vllm + openai installed.
# All paths (PIP_CACHE_DIR, TMPDIR, HF_HOME, venv) live under /sci/labs/...
# to avoid the 5GB /sci/home/orzuk quota.
