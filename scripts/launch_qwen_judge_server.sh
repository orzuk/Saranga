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
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=/sci/labs/orzuk/orzuk/method_e_jobs/qwen_judge.%j.log
#SBATCH --error=/sci/labs/orzuk/orzuk/method_e_jobs/qwen_judge.%j.log

set -euo pipefail

mkdir -p /sci/labs/orzuk/orzuk/method_e_jobs

# Model — pick a size that fits the GPU you got. Defaults to Qwen3-32B int4.
# Options:
#   Qwen/Qwen3-32B-Instruct                  (~64 GB FP16; needs 1× H100 80GB or 2× 40GB)
#   Qwen/Qwen3-32B-Instruct-AWQ-int4         (~16 GB; fits 1× H100 / A100 / RTX A6000)
#   Qwen/Qwen3-14B-Instruct                  (~28 GB FP16; 1× A100 40GB)
#   Qwen/Qwen2.5-72B-Instruct-AWQ-int4       (~40 GB; needs H100 80GB)
MODEL="${QWEN_MODEL:-Qwen/Qwen3-32B-Instruct-AWQ-int4}"
PORT="${QWEN_PORT:-8000}"
HOST="0.0.0.0"

# Use the dedicated qwen-vllm venv (vllm + flashinfer + torch + nvidia
# libs together are too heavy for the shared authomathics-venv). Set up
# once via scripts in /sci/labs/orzuk/orzuk/method_e_jobs/install_vllm.sh.
source /sci/labs/orzuk/orzuk/venvs/qwen-vllm/bin/activate

# HuggingFace cache — keep weights on the lab disk, NOT the 5GB home quota.
# (HF model downloads are 16-65GB and will OOM the home dir if left default.)
export HF_HOME="${HF_HOME:-/sci/labs/orzuk/orzuk/hf-cache}"
mkdir -p "$HF_HOME"
# Also redirect TMPDIR to lab disk for pip/vllm wheel extraction.
export TMPDIR="${TMPDIR:-/sci/labs/orzuk/orzuk/tmp_install}"
mkdir -p "$TMPDIR"

# Optional: speed up downloads on first run
export HF_HUB_ENABLE_HF_TRANSFER=1

echo "[launch_qwen] node=$(hostname) port=$PORT"
echo "[launch_qwen] model=$MODEL"
echo "[launch_qwen] HF_HOME=$HF_HOME"
echo "[launch_qwen] starting vLLM server at $(date)"
echo "[launch_qwen]"
echo "[launch_qwen] On the client side, point at:"
echo "[launch_qwen]   export LLM_LOCAL_BASE_URL=http://$(hostname):$PORT/v1"
echo "[launch_qwen]"

# vLLM serves the OpenAI-compatible API. Tuned for a single H100/A100 80GB.
python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --dtype auto \
  --trust-remote-code

# NOTE: one-time install (done 2026-05-21):
#   sbatch /sci/labs/orzuk/orzuk/method_e_jobs/install_vllm.sh
# Creates /sci/labs/orzuk/orzuk/venvs/qwen-vllm with vllm + openai installed.
# All paths (PIP_CACHE_DIR, TMPDIR, HF_HOME, venv) live under /sci/labs/...
# to avoid the 5GB /sci/home/orzuk quota.
