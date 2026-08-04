#!/bin/bash -l
#
# SLURM ARRAY job: Erdős coverage, one task per corpus category dir.
#
# The single-node erdos_cluster.sh spends nearly all its wall time walking and
# parsing ~100k JSONs over NFS, single-threaded. Because the reported score is a
# max over corpus nodes, the corpus partitions cleanly: each task handles one
# category dir, and erdos_merge.py takes the argmax across tasks. The merged
# result is IDENTICAL to a whole-corpus run — this is a speedup, not an
# approximation.
#
# Submit (the array size must match the number of category dirs):
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   N=$(find "$ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l)
#   sbatch --array=0-$((N-1))%16 discovery_suite/open_problems/erdos_array.sh
#
# Then merge (seconds, no cluster needed):
#   python3 discovery_suite/open_problems/erdos_merge.py \
#       --shards 'discovery_suite/open_problems/runs/shards/erdos_shard_*.csv' \
#       --threshold 0.15 \
#       --out discovery_suite/open_problems/runs/erdos_coverage_100k.csv
#
#SBATCH --job-name=erdos_shard
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --partition=glacier
#SBATCH --time=02:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2

set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed_100k_v4 dir (parent of the category dirs)}"
SHARD_DIR="${SHARD_DIR:-discovery_suite/open_problems/runs/shards}"
MATCH_THEOREMS="${MATCH_THEOREMS:-0}"
ERDOS_CSV="${ERDOS_CSV:-discovery_suite/open_problems/erdos_problems.csv}"

# Deterministic task -> category mapping. `sort` makes the assignment stable
# across resubmissions, so a failed task can be rerun with --array=<id> alone.
mapfile -t CATS < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d | sort)
N=${#CATS[@]}
IDX="${SLURM_ARRAY_TASK_ID:?this script must run as an array job}"

if (( IDX >= N )); then
    echo "[erdos_shard] task $IDX >= $N category dirs — nothing to do."
    echo "[erdos_shard] resubmit with --array=0-$((N-1))"
    exit 0
fi

CAT="${CATS[$IDX]}"
OUT="$SHARD_DIR/erdos_shard_$(printf '%03d' "$IDX").csv"
mkdir -p "$SHARD_DIR"

EXTRA=()
[[ "$MATCH_THEOREMS" == "1" ]] && EXTRA+=(--match-theorems)

echo "[erdos_shard] task $IDX/$N  cat=$CAT  out=$OUT"

# --threshold 0 and --show 0: shards are raw per-problem best matches. All
# thresholding, cross-referencing and reporting happen once, in erdos_merge.py.
python3 discovery_suite/open_problems/erdos_coverage.py \
    --erdos-csv "$ERDOS_CSV" \
    --corpus-dir "$CAT" \
    --threshold 0 \
    --show 0 \
    --out "$OUT" \
    ${EXTRA[@]+"${EXTRA[@]}"}

echo "[erdos_shard] task $IDX done -> $OUT"
