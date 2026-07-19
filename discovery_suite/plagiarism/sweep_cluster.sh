#!/bin/bash -l
#
# SLURM job: T-PLAG P1 corpus sweep over the v4 100k parsed corpus.
# CPU-only, no API cost. EXTERNAL (disk-based) MinHash-LSH: peak RAM is bounded
# by one band-partition + the output, NOT the corpus, so it scales past the
# in-memory version that OOM-killed at ~25k/100k papers. Emits (a) a node-pair
# reuse-evidence CSV and (b) an aggregated paper-pair triage CSV for human /
# P4-LLM review.
#
# Usage (PREFERRED — plain sbatch propagates exported env):
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   sbatch discovery_suite/plagiarism/sweep_cluster.sh
#
# Pass 3 (bucket+verify) is the bottleneck and is parallelised across the
# allocated cores automatically (it reads SLURM_CPUS_PER_TASK). At 100k / 4 cores
# it was ~62 min serial; more cores scale it down near-linearly.
#
# Bigger corpora (e.g. 3M papers): this must stay ONE job (chunking by year would
# hide cross-year reuse). Override the SBATCH resources at submit time and raise
# PARTITIONS so a single shard still fits in RAM at pass 3 AND
# rank_workers*shard < mem, e.g.:
#   sbatch --cpus-per-task=16 --time=24:00:00 --mem=64G \
#     --export=ALL,ROOT=$ROOT,PARTITIONS=512 discovery_suite/plagiarism/sweep_cluster.sh
# Also make sure WORK_DIR has room for the signatures (~num_perm*8 bytes/node,
# ~8GB at 100k, ~240GB at 3M) + band rows; point it at fast scratch if needed.
#
# Resource profile mirrors the lab's proven scripts (32G/4cpu/4h, glacier).
#SBATCH --job-name=plag_sweep
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=glacier
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4

# Fail loudly: without this the script would echo a false "done" even if python
# was OOM-killed (the trap that hid the first failure).
set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed_100k_v4 dir (parent of the 20 category dirs)}"
OUT="${OUT:-discovery_suite/plagiarism/runs/plag_sweep_100k.csv}"
WORK_DIR="${WORK_DIR:-discovery_suite/plagiarism/runs/plag_sweep_100k_work}"
MIN_JACCARD="${MIN_JACCARD:-0.20}"
PARTITIONS="${PARTITIONS:-64}"
WORKERS="${WORKERS:-16}"
# RANK_WORKERS unset -> pass 3 auto-uses SLURM_CPUS_PER_TASK. Override to cap it.
RANK_WORKERS="${RANK_WORKERS:-}"

echo "[plag_sweep] root=$ROOT out=$OUT work_dir=$WORK_DIR min_jaccard=$MIN_JACCARD partitions=$PARTITIONS workers=$WORKERS rank_workers=${RANK_WORKERS:-auto}"
python3 discovery_suite/plagiarism/sweep_plag.py \
    --root "$ROOT" --out "$OUT" --work-dir "$WORK_DIR" \
    --min-jaccard "$MIN_JACCARD" --partitions "$PARTITIONS" --workers "$WORKERS" \
    ${RANK_WORKERS:+--rank-workers "$RANK_WORKERS"}

echo "[plag_sweep] done -> $OUT (+ *_nodes.csv evidence)"
echo "[next] filter cross_category / high score_max rows, then adjudicate the"
echo "       strongest node pairs with the P4 LLM judge (common/llm_judge.py)."
