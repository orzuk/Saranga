#!/bin/bash -l
#
# Stage 5 (GPU array): cross-encoder rerank of the fused shortlist.
#
# Budget: 15,143 problems x TOP_PER_PROBLEM=20 is ~300k pairs. At ~250 pairs/s
# on an L40s that is ~20 minutes on one GPU, ~5 across a 4-way array. This is the
# only per-pair stage in the pipeline, and it sees ~1e-5 of the 24 billion
# possible pairs — which is exactly why a cross-encoder is affordable here and
# would not be at the candidate-generation stage.
#
#   export SHORTLIST=discovery_suite/open_problems/runs/open_fused.csv
#   export STORE=.../textstore_100k
#   export OUT=discovery_suite/open_problems/runs/open_reranked.csv
#   sbatch --array=0-3 discovery_suite/open_problems/rerank_cluster.sh
#
# Each task writes OUT.partNNN.csv; concatenate afterwards (header from the first):
#   awk 'FNR==1 && NR!=1 {next} {print}' runs/open_reranked.part*.csv > runs/open_reranked.csv
#
#SBATCH --job-name=open_rerank
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=04:00:00
#SBATCH --mem=48G
#SBATCH --cpus-per-task=4

set -euo pipefail

SHORTLIST="${SHORTLIST:?set SHORTLIST to the fused/dense candidate CSV}"
STORE="${STORE:?set STORE to the text store (full node text for the pairs)}"
OUT="${OUT:-discovery_suite/open_problems/runs/open_reranked.csv}"
MODEL="${MODEL:-bge-reranker}"
VIEW="${VIEW:-ctx-concat}"
CANON="${CANON:-raw}"
TOP_PER_PROBLEM="${TOP_PER_PROBLEM:-20}"
BATCH="${BATCH:-}"

# Locate the repo root. NOT via $0: sbatch COPIES the batch script into a spool
# directory, so inside a SLURM job $0 is /var/spool/slurmd/.../slurm_script and
# "$(dirname "$0")/../.." lands in /var/spool. Prefer the directory sbatch was
# invoked from; fall back to $0 only when run directly with bash.
REPO="${REPO:-${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}}"
if [ ! -d "$REPO/discovery_suite" ]; then
    echo "ERROR: no discovery_suite/ under '$REPO'." >&2
    echo "       Submit from the repo root, or pass REPO=/path/to/Authomathics." >&2
    exit 2
fi
cd "$REPO"
export PYTHONPATH="$PWD/discovery_suite:${PYTHONPATH:-}"

echo "[rerank] model=$MODEL view=$VIEW shortlist=$SHORTLIST"
echo "[rerank] task ${SLURM_ARRAY_TASK_ID:-0}/${SLURM_ARRAY_TASK_COUNT:-1}"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

python3 -m embed.models --check --models "$MODEL"

python3 discovery_suite/open_problems/o5_rerank.py \
    --in "$SHORTLIST" --store "$STORE" --out "$OUT" \
    --model "$MODEL" --view "$VIEW" --canon "$CANON" \
    --top-per-problem "$TOP_PER_PROBLEM" \
    --shards "${SLURM_ARRAY_TASK_COUNT:-1}" \
    ${BATCH:+--batch-size "$BATCH"} \
    --status-dir "$(dirname "$OUT")/status"

echo "[rerank] task ${SLURM_ARRAY_TASK_ID:-0} done"
echo "[next] concatenate parts, then triage + the UNCHANGED Opus judge:"
echo "  python3 discovery_suite/open_problems/triage_open.py --in $OUT --out runs/triage_reranked.csv"
echo "  python3 discovery_suite/open_problems/batch_o4.py --triage runs/triage_reranked.csv --tex-root ... --model opus"
