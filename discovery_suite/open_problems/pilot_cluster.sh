#!/bin/bash -l
#
# TIMED PILOT — run the whole pipeline on a small slice and print how long each
# stage took, so the full-corpus estimates stop being arithmetic and become
# measurements. Answers "what do we get, and how long will the real thing take?"
# in one job.
#
#   mkdir -p logs
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   export RUN=$PWD/discovery_suite/open_problems/runs/pilot
#   sbatch discovery_suite/open_problems/pilot_cluster.sh
#
# PAPERS=2000 by default: big enough for the per-node rates to be stable, small
# enough to finish inside an hour. Every stage prints its own elapsed time and
# the script ends with a table extrapolating each to the full 100k corpus.
#
#SBATCH --job-name=open_pilot
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=04:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8

set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed corpus dir}"
RUN="${RUN:-$PWD/discovery_suite/open_problems/runs/pilot}"
PAPERS="${PAPERS:-2000}"
MODEL="${MODEL:-qwen3-0.6b}"
VIEW="${VIEW:-node}"
CANON="${CANON:-raw}"
SHARDS="${SHARDS:-8}"
TOPK="${TOPK:-50}"
FULL_CORPUS="${FULL_CORPUS:-100000}"

cd "$(dirname "$0")/../.."
export PYTHONPATH="$PWD/discovery_suite:${PYTHONPATH:-}"
export HF_HOME="${HF_HOME:-/sci/labs/orzuk/orzuk/hf_cache}"
mkdir -p "$RUN" "$HF_HOME"

STORE="$RUN/textstore"
VECS="$RUN/vectors"
TIMING="$RUN/timing.txt"
: > "$TIMING"

# awk, not bc: bc is not guaranteed to be installed on a compute node and a
# missing binary here would kill the run after the expensive stage had finished.
stamp() {  # stamp <label> <seconds>
    awk -v l="$1" -v s="$2" -v p="$PAPERS" -v f="$FULL_CORPUS" \
        'BEGIN { printf "%-22s %8d s   (x%.1f -> %7.1f min for %d papers)\n",
                 l, s, f/p, s*f/p/60, f }' | tee -a "$TIMING"
}

echo "[pilot] root=$ROOT papers=$PAPERS model=$MODEL view=$VIEW canon=$CANON"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

echo; echo "=== 0. model availability + measured throughput ==="
python3 -m embed.models --check --models "$MODEL" --probe-n 512

echo; echo "=== 1. text store (CPU, parallel) ==="
t0=$SECONDS
python3 -m embed.textstore plan --root "$ROOT" --out "$STORE" --limit "$PAPERS"
python3 -m embed.textstore build --root "$ROOT" --out "$STORE" \
    --shards "$SHARDS" --status-dir "$STORE/status"
stamp "textstore" "$((SECONDS - t0))"

echo; echo "=== 2. encode (GPU) ==="
t0=$SECONDS
python3 -m embed.encode --store "$STORE" --out "$VECS" \
    --model "$MODEL" --view "$VIEW" --canon "$CANON" --status-dir "$VECS/status"
stamp "encode ($MODEL)" "$((SECONDS - t0))"

echo; echo "=== 3. dense retrieval (GPU) ==="
t0=$SECONDS
python3 discovery_suite/open_problems/o1b_dense_sweep.py all \
    --vectors "$VECS" --model "$MODEL" --view "$VIEW" --canon "$CANON" \
    --top-k "$TOPK" --out "$RUN/dense.csv"
stamp "dense retrieval" "$((SECONDS - t0))"

echo; echo "=== 4. triage (unchanged downstream tool) ==="
python3 discovery_suite/open_problems/triage_open.py \
    --in "$RUN/dense.csv" --out "$RUN/triage.csv" \
    --min-score 0.5 --per-problem 3 || true

echo; echo "=========================================================="
echo "TIMING SUMMARY  (pilot on $PAPERS papers, extrapolated to $FULL_CORPUS)"
echo "=========================================================="
cat "$TIMING"
echo
echo "NOTE: the textstore row scales with CPUS_PER_TASK and the encode row with"
echo "how many GPU array tasks you use — both stages are shard-parallel, so the"
echo "extrapolation above is the ONE-TASK cost. Divide by your array width."
echo
echo "outputs:  $RUN/dense.csv   $RUN/triage.csv   $TIMING"
