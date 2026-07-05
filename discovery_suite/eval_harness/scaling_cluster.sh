#!/bin/bash -l
#
# SLURM job: discovery-suite scaling benchmark on the v4 100k parsed corpus.
# Light methods only (P1 shingling + O1 retrieval) — no API cost, CPU-only.
#
# Usage:
#   sbatch discovery_suite/eval_harness/scaling_cluster.sh
# Customize:
#   sbatch --export=ROOT=/path/to/v4/tier3,SIZES=2000,8000,32000,100000 \
#          discovery_suite/eval_harness/scaling_cluster.sh
#
#SBATCH --job-name=disc_scaling
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --time=04:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8

set -uo pipefail

ROOT="${ROOT:-$HOME/Datasets/Saranga_data/tier3}"     # v4 100k tier3 tree
SIZES="${SIZES:-2000,8000,16000,32000,64000,100000}"
OUT="${OUT:-discovery_suite/eval_harness/runs/scaling_v4_100k.json}"

echo "[scaling] root=$ROOT sizes=$SIZES"
python3 discovery_suite/eval_harness/scaling_benchmark.py \
    --root "$ROOT" --sizes "$SIZES" --out "$OUT"

echo "[scaling] done -> $OUT"
echo "[report] regenerate the meeting PDF with:"
echo "  python3 discovery_suite/report/make_meeting_pdf.py --scaling $OUT \\"
echo "      --out discovery_suite/report/saranga_discovery_brief.pdf"
