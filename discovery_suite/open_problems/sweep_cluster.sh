#!/bin/bash -l
#
# SLURM job: T-OPEN corpus sweep over the v4 100k parsed corpus.
# CPU-only, no API cost. Emits a ranked triage CSV of real open-problem ->
# theorem resolution candidates (cross-category) for O4 LLM-judge review.
#
# Usage (PREFERRED — plain sbatch propagates exported env):
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   sbatch discovery_suite/open_problems/sweep_cluster.sh
#
# Resource profile mirrors the lab's proven scripts (32G/4cpu/4h, glacier).
#SBATCH --job-name=open_sweep
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=glacier
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4

ROOT="${ROOT:?set ROOT to the parsed_100k_v4 dir (parent of the 20 category dirs)}"
OUT="${OUT:-discovery_suite/open_problems/runs/open_sweep_100k.csv}"
MIN_SCORE="${MIN_SCORE:-0.10}"
TOPK="${TOPK:-20}"

echo "[open_sweep] root=$ROOT out=$OUT min_score=$MIN_SCORE top_k=$TOPK"
# --text-source raw: tokenize clean_latex_to_text(raw_latex) so retrieval sees the
# real math (constants/operators/identifiers), not the [MATH]-masked clean_text.
# This is the sweep_open.py default too; stated explicitly here for clarity.
python3 discovery_suite/open_problems/sweep_open.py \
    --root "$ROOT" --out "$OUT" --top-k "$TOPK" --min-score "$MIN_SCORE" \
    --text-source raw

echo "[open_sweep] done -> $OUT"
echo "[next] review top rows, then adjudicate with:"
echo "  python3 discovery_suite/open_problems/o4_judge.py --problem <pk> --theorem <tk> --model opus"
