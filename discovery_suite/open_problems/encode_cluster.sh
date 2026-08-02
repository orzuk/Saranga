#!/bin/bash -l
#
# Stage 2 (GPU array): text-store shards -> fp16 normalized vectors.
#
# Cost check before you launch: this is O(N) in nodes, ONCE. At ~800 nodes/s on
# an L40s, the 100k corpus (~1.6M retrievable nodes) is ~33 GPU-minutes per
# (model, view, canon) arm. The whole champion configuration — raw + canonical
# node views plus one ctx-concat pass — is under 2 GPU-hours. ctx-late needs NO
# pass of its own; it is assembled from the node vectors at search time.
#
#   export STORE=.../textstore_100k
#   export VECS=.../vectors
#   export MODEL=qwen3-0.6b VIEW=node CANON=raw
#   sbatch --array=0-15 discovery_suite/open_problems/encode_cluster.sh
#
# The array need not cover every shard: --shard-stride makes task k take shards
# k, k+stride, k+2*stride, … so 16 tasks cleanly cover 64 shards.
#
# Partitions (per scripts/launch_qwen_judge_server.sh):
#   catfish  l4    24GB   fine for minilm/distilbert/specter2
#   salmon   l40s  48GB   default; comfortable for bge-m3 and qwen3-0.6b
#   dogfish  a100  80GB   needed for qwen3-4b
#SBATCH --job-name=open_encode
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=08:00:00
#SBATCH --mem=48G
#SBATCH --cpus-per-task=4

set -euo pipefail

STORE="${STORE:?set STORE to the text-store dir built by textstore_cluster.sh}"
VECS="${VECS:?set VECS to the vector-store output root}"
MODEL="${MODEL:-qwen3-0.6b}"
VIEW="${VIEW:-node}"
CANON="${CANON:-raw}"
SHARDS="${SHARDS:-64}"
STRIDE="${STRIDE:-}"
BATCH="${BATCH:-}"
MAX_TOKENS="${MAX_TOKENS:-}"

cd "$(dirname "$0")/../.."
export PYTHONPATH="$PWD/discovery_suite:${PYTHONPATH:-}"

# One array task per stride slot; default stride = array width so the tasks tile
# the shard range exactly.
if [ -z "$STRIDE" ]; then
    STRIDE="${SLURM_ARRAY_TASK_COUNT:-1}"
fi

echo "[encode] model=$MODEL view=$VIEW canon=$CANON store=$STORE"
echo "[encode] task ${SLURM_ARRAY_TASK_ID:-0}, stride $STRIDE over $SHARDS shards"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

# Fail fast: a missing HF model should cost 30 seconds here, not four hours in.
python3 -m embed.models --check --models "$MODEL"

python3 -m embed.encode \
    --store "$STORE" --out "$VECS" \
    --model "$MODEL" --view "$VIEW" --canon "$CANON" \
    --shard-stride "$STRIDE" \
    ${BATCH:+--batch-size "$BATCH"} \
    ${MAX_TOKENS:+--max-tokens "$MAX_TOKENS"} \
    --status-dir "$VECS/status"

echo "[encode] task ${SLURM_ARRAY_TASK_ID:-0} done"
echo "[watch] python3 discovery_suite/open_problems/watch_open.py $VECS/status"
