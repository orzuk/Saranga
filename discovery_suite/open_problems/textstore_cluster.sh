#!/bin/bash -l
#
# Stage 1 (CPU array): corpus JSONs -> sharded text store.
#
# Canonicalization runs at ~240 nodes/s/core, so this is the CPU-heavy stage and
# it is deliberately separated from the GPU stage: doing it inline in the encode
# job would leave an L40s idle ~90% of the time.
#
# Run the plan step FIRST (seconds, and it stops 64 array tasks from each
# os.walk-ing a 100k-file Lustre tree — the shared-metadata hammering that killed
# the download jobs):
#
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   export STORE=$PWD/discovery_suite/open_problems/runs/textstore_100k
#   python3 -m embed.textstore plan --root $ROOT --out $STORE      # from discovery_suite/
#   sbatch --array=0-63 discovery_suite/open_problems/textstore_cluster.sh
#
#SBATCH --job-name=open_textstore
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --partition=glacier
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=8

set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed corpus dir (parent of the category dirs)}"
STORE="${STORE:?set STORE to the text-store output dir}"
SHARDS="${SHARDS:-64}"
CANON_SCOPE="${CANON_SCOPE:-local}"
CTX_CANON_SCOPE="${CTX_CANON_SCOPE:-paper}"
CTX_DEPTH="${CTX_DEPTH:-1}"
MAX_NEIGHBOURS="${MAX_NEIGHBOURS:-4}"

cd "$(dirname "$0")/../.."          # repo root
export PYTHONPATH="$PWD/discovery_suite:${PYTHONPATH:-}"

echo "[textstore] root=$ROOT store=$STORE shard=${SLURM_ARRAY_TASK_ID:-0}/$SHARDS"
echo "[textstore] canon: node=$CANON_SCOPE ctx=$CTX_CANON_SCOPE depth=$CTX_DEPTH"

# --shard-id defaults to $SLURM_ARRAY_TASK_ID inside the tool; passing --shards
# is what makes the slice files[k::N] deterministic across tasks.
python3 -m embed.textstore build \
    --root "$ROOT" --out "$STORE" \
    --shards "$SHARDS" \
    --canon-scope "$CANON_SCOPE" \
    --ctx-canon-scope "$CTX_CANON_SCOPE" \
    --ctx-depth "$CTX_DEPTH" \
    --max-neighbours "$MAX_NEIGHBOURS" \
    --status-dir "$STORE/status"

echo "[textstore] shard ${SLURM_ARRAY_TASK_ID:-0} done"
echo "[watch] python3 discovery_suite/open_problems/watch_open.py $STORE/status"
