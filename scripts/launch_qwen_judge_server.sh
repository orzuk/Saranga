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
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=/sci/home/orzuk/method_e_jobs/qwen_judge.%j.log
#SBATCH --error=/sci/home/orzuk/method_e_jobs/qwen_judge.%j.log

set -euo pipefail

mkdir -p "$HOME/method_e_jobs"

# Model — pick a size that fits the GPU you got. Defaults to Qwen3-32B int4.
# Options:
#   Qwen/Qwen3-32B-Instruct                  (~64 GB FP16; needs 1× H100 80GB or 2× 40GB)
#   Qwen/Qwen3-32B-Instruct-AWQ-int4         (~16 GB; fits 1× H100 / A100 / RTX A6000)
#   Qwen/Qwen3-14B-Instruct                  (~28 GB FP16; 1× A100 40GB)
#   Qwen/Qwen2.5-72B-Instruct-AWQ-int4       (~40 GB; needs H100 80GB)
MODEL="${QWEN_MODEL:-Qwen/Qwen3-32B-Instruct-AWQ-int4}"
PORT="${QWEN_PORT:-8000}"
HOST="0.0.0.0"

# Use the project venv (must have vllm + openai installed; see install
# note below) or a separate qwen-serving venv if vllm conflicts.
source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate

# HuggingFace cache — keep weights on a fast scratch path if available.
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
mkdir -p "$HF_HOME"

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

# NOTE: one-time install if vllm isn't in the venv yet:
#   pip install --upgrade vllm openai
# vLLM bundles its own CUDA build; conflicts with system PyTorch are
# possible. If so, use a dedicated venv:
#   python -m venv /sci/labs/orzuk/orzuk/venvs/qwen-vllm
#   source /sci/labs/orzuk/orzuk/venvs/qwen-vllm/bin/activate
#   pip install vllm openai
