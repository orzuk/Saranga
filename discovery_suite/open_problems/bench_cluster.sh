#!/bin/bash -l
#
# Tier-A benchmark on a GPU node: which (model x view x canonicalization) arm
# actually finds resolutions?  This is step 1 of the plan and it belongs HERE,
# not on a laptop — MiniLM is the only model in the roster that runs on CPU, and
# it is the one whose 256-token window made the context arms untestable.
#
# Self-contained: it plants its own ground truth in memory and encodes on the
# fly, so it needs NO text store and NO vector store. Run it before committing
# GPU time to a full corpus pass.
#
#   mkdir -p logs                     # sbatch cannot create its own log dir
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   export OUT=$PWD/discovery_suite/open_problems/runs/bench_cluster.csv
#   sbatch discovery_suite/open_problems/bench_cluster.sh
#
# With LLM=haiku the L2+ obfuscation becomes real paraphrase instead of synonym
# swapping — without it the lexical baseline scores near-perfectly at every
# level and the comparison is meaningless. Needs ANTHROPIC_API_KEY; responses
# are sqlite-cached so a re-run is free.
#
#SBATCH --job-name=open_bench
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=06:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8

set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed corpus dir (parent of the category dirs)}"
PAPERS="${PAPERS:-2000}"
TWINS="${TWINS:-200}"
MODELS="${MODELS:-minilm,distilbert,specter2,bge-m3,qwen3-0.6b}"
VIEWS="${VIEWS:-node,ctx-concat,ctx-late,concepts-only}"
CANONS="${CANONS:-raw,canon}"
LEVELS="${LEVELS:-L0,L1,L2,L3}"
LLM="${LLM:-}"
TOPK="${TOPK:-50}"
OUT="${OUT:-discovery_suite/open_problems/runs/bench_cluster.csv}"
JUDGED="${JUDGED:-discovery_suite/open_problems/runs/o4_verdicts_all.csv}"

cd "$(dirname "$0")/../.."
export PYTHONPATH="$PWD/discovery_suite:${PYTHONPATH:-}"
mkdir -p "$(dirname "$OUT")"

# Keep model weights on the lab filesystem, not in a per-user home quota, and
# shared across jobs so only the first run pays the download.
export HF_HOME="${HF_HOME:-/sci/labs/orzuk/orzuk/hf_cache}"
mkdir -p "$HF_HOME"

echo "[bench] root=$ROOT papers=$PAPERS twins=$TWINS"
echo "[bench] models=$MODELS"
echo "[bench] views=$VIEWS canons=$CANONS levels=$LEVELS llm=${LLM:-<rule-based>}"
echo "[bench] HF_HOME=$HF_HOME"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

# Fail fast, and record the per-model throughput this GPU actually achieves —
# that rate is what every later time estimate is built on.
echo "[bench] --- model availability + measured throughput ---"
python3 -m embed.models --check --models "$MODELS" --probe-n 512

echo "[bench] --- benchmark ---"
python3 discovery_suite/open_problems/bench_retrieval.py \
    --root "$ROOT" --papers "$PAPERS" --twins "$TWINS" \
    --models "$MODELS" --views "$VIEWS" --canons "$CANONS" \
    --levels "$LEVELS" --top-k "$TOPK" \
    ${LLM:+--llm "$LLM"} \
    ${JUDGED:+--judged "$JUDGED"} \
    --out "$OUT"

echo "[bench] done -> $OUT  (and ${OUT%.csv}.md)"
echo "[next] take the top 1-2 arms into the full corpus run:"
echo "  MODELS=<winner> ARMS=<view:canon> bash discovery_suite/open_problems/embed_cluster.sh"
