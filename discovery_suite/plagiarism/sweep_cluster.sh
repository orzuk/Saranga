#!/bin/bash -l
#
# SLURM job: T-PLAG P1 corpus sweep over the v4 100k parsed corpus.
# CPU-only, no API cost. Emits (a) a node-pair reuse-evidence CSV and (b) an
# aggregated paper-pair triage CSV of cross-paper lexical-reuse candidates for
# human / P4-LLM review.
#
# Usage (PREFERRED — plain sbatch propagates exported env):
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   sbatch discovery_suite/plagiarism/sweep_cluster.sh
#
# Resource profile mirrors the lab's proven scripts (32G/4cpu/4h, glacier).
#SBATCH --job-name=plag_sweep
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=glacier
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4

ROOT="${ROOT:?set ROOT to the parsed_100k_v4 dir (parent of the 20 category dirs)}"
OUT="${OUT:-discovery_suite/plagiarism/runs/plag_sweep_100k.csv}"
MIN_JACCARD="${MIN_JACCARD:-0.20}"

echo "[plag_sweep] root=$ROOT out=$OUT min_jaccard=$MIN_JACCARD"
python3 discovery_suite/plagiarism/sweep_plag.py \
    --root "$ROOT" --out "$OUT" --min-jaccard "$MIN_JACCARD"

echo "[plag_sweep] done -> $OUT (+ *_nodes.csv evidence)"
echo "[next] filter cross_category / high score_max rows, then adjudicate the"
echo "       strongest node pairs with the P4 LLM judge (common/llm_judge.py)."
