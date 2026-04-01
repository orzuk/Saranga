#!/bin/bash
#SBATCH --job-name=vllm-52017
#SBATCH --output=vllm-server-%j.log
#SBATCH --error=vllm-server-%j.log
#SBATCH --partition=gpu          # adjust to your cluster's GPU partition name
#SBATCH --gres=gpu:1             # one GPU is enough for 7-8B models
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --time=24:00:00          # keep server running for 24 hours (adjust as needed)

##############################################################################
# vLLM server for Big Data Project 52017
#
# INSTRUCTOR SETUP (one-time):
#   1. Edit MODEL and MODEL_DIR below
#   2. Submit: sbatch start_vllm_server.sh
#   3. Check the log for the URL, give it to students
#   4. Students set: export LLM_API_URL=http://<node>:8000
#
# To serve a different model, change MODEL and resubmit.
# To serve all 3 models simultaneously, submit 3 jobs with different ports.
##############################################################################

# === CONFIGURATION — edit these ===

# Where to store downloaded models (shared, fast storage — NOT Google Drive!)
# All students need read access to this directory.
export HF_HOME=/cs/labs/oMDG/shared/huggingface_cache
# Alternative locations (uncomment one):
# export HF_HOME=/scratch/$USER/huggingface_cache
# export HF_HOME=/cs/labs/your_lab/shared/huggingface_cache

# Which model to serve (one per job — change and resubmit for each model)
MODEL="meta-llama/Llama-3.1-8B-Instruct"
# MODEL="Qwen/Qwen2.5-7B-Instruct"
# MODEL="Qwen/Qwen3-8B"

PORT=8000
# Use different ports if running multiple models simultaneously:
# Llama: 8000, Qwen2.5: 8001, Qwen3: 8002

# === END CONFIGURATION ===

mkdir -p "$HF_HOME"

# Print connection info for students
echo "============================================"
echo "vLLM server starting on $(hostname):${PORT}"
echo "Model: ${MODEL}"
echo "============================================"
echo ""
echo "Students: run this command to connect:"
echo "  export LLM_API_URL=http://$(hostname):${PORT}"
echo ""
echo "Test with:"
echo "  python scripts/call_llm.py \"What is SVD?\""
echo "============================================"

# Activate environment
# First-time setup (run manually once):
#   python -m venv ~/vllm_env
#   source ~/vllm_env/bin/activate
#   pip install vllm
source ~/vllm_env/bin/activate

# Start the server (blocks until killed or time limit)
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --port "$PORT" \
    --host 0.0.0.0 \
    --max-model-len 16384 \
    --dtype auto \
    --trust-remote-code \
    --download-dir "$HF_HOME"
