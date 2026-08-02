#!/bin/bash -l
#
# Stage 3 (GPU): dense problem->theorem retrieval, map-reduce over doc shards.
#
# Two modes:
#   MODE=all     one job does everything. Correct choice at 100k: the whole
#                scoring pass is 15,143 x 1,589,327 x 1024 = 2.4e13 FLOPs,
#                i.e. under a minute of L40s tensor-core time. The lexical
#                inverted-index rank took ~57 CPU-minutes for the same work.
#   MODE=map     array over doc shards, then a reduce. Needed once the corpus is
#                large enough that one task cannot stream all shards in the wall
#                clock (the 3M run).
#
#   export VECS=.../vectors MODEL=qwen3-0.6b VIEW=node CANON=raw
#   export OUT=discovery_suite/open_problems/runs/open_dense_qwen_node_raw.csv
#   sbatch discovery_suite/open_problems/dense_cluster.sh                 # MODE=all
#   MODE=map sbatch --array=0-15 discovery_suite/open_problems/dense_cluster.sh
#   MODE=reduce sbatch discovery_suite/open_problems/dense_cluster.sh
#
#SBATCH --job-name=open_dense
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=04:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=4

set -euo pipefail

VECS="${VECS:?set VECS to the vector-store root built by encode_cluster.sh}"
MODEL="${MODEL:-qwen3-0.6b}"
VIEW="${VIEW:-node}"
CANON="${CANON:-raw}"
TOPK="${TOPK:-50}"
ALPHA="${ALPHA:-0.7}"
MODE="${MODE:-all}"
PARTIALS="${PARTIALS:-$VECS/partials_${MODEL}_${VIEW}_${CANON}}"
OUT="${OUT:-discovery_suite/open_problems/runs/open_dense_${MODEL}_${VIEW}_${CANON}.csv}"

cd "$(dirname "$0")/../.."
export PYTHONPATH="$PWD/discovery_suite:${PYTHONPATH:-}"

echo "[dense] mode=$MODE model=$MODEL view=$VIEW canon=$CANON top_k=$TOPK"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

COMMON=(--vectors "$VECS" --model "$MODEL" --view "$VIEW" --canon "$CANON"
        --top-k "$TOPK" --alpha "$ALPHA" --status-dir "$VECS/status")

case "$MODE" in
  all)
    python3 discovery_suite/open_problems/o1b_dense_sweep.py all \
        "${COMMON[@]}" --out "$OUT"
    ;;
  map)
    # --shard-id defaults to $SLURM_ARRAY_TASK_ID; stride makes task k take
    # shards k, k+N, k+2N, … so the array tiles the shard range exactly.
    python3 discovery_suite/open_problems/o1b_dense_sweep.py map \
        "${COMMON[@]}" --partials "$PARTIALS" \
        --shard-stride "${SLURM_ARRAY_TASK_COUNT:-1}"
    ;;
  reduce)
    python3 discovery_suite/open_problems/o1b_dense_sweep.py reduce \
        "${COMMON[@]}" --partials "$PARTIALS" --out "$OUT"
    ;;
  *)
    echo "MODE must be all | map | reduce" >&2; exit 2 ;;
esac

echo "[dense] done"
echo "[next] fuse with the lexical sweep, then triage:"
echo "  python3 discovery_suite/open_problems/o1c_fuse.py \\"
echo "      --lexical discovery_suite/open_problems/runs/open_sweep_100k_raw.csv \\"
echo "      --dense $OUT --out discovery_suite/open_problems/runs/open_fused.csv"
