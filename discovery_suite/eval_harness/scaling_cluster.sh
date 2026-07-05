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
# Resource request mirrors the lab's proven scripts (parse_multi_category_20.sh):
# 32G / 4 cpus / 4h, no explicit partition. Asking for 64G/8cpu triggered
# SLURM (BadConstraints) — no node in the default partition offered it, and the
# benchmark is single-threaded Python anyway (extra cores unused).
#SBATCH --job-name=disc_scaling
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=glacier
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
# NOTE: the site auto-adds Features=cpuonly to CPU jobs; only the `glacier`
# partition advertises that feature (dogfish/catfish/etc. do not), so leaving
# the partition to the scheduler lands on a node that can't satisfy it →
# BadConstraints. Pin glacier explicitly.

set -uo pipefail

ROOT="${ROOT:-$HOME/Datasets/Saranga_data/tier3}"     # v4 100k tier3 tree
# Default stops at 32k: comfortably fits 32G RAM and already fixes the scaling
# slope. Push higher via --export=SIZES=... if the node has the memory.
SIZES="${SIZES:-2000,8000,16000,32000}"
OUT="${OUT:-discovery_suite/eval_harness/runs/scaling_v4_100k.json}"

echo "[scaling] root=$ROOT sizes=$SIZES"
python3 discovery_suite/eval_harness/scaling_benchmark.py \
    --root "$ROOT" --sizes "$SIZES" --out "$OUT"

echo "[scaling] done -> $OUT"
echo "[report] regenerate the meeting PDF with:"
echo "  python3 discovery_suite/report/make_meeting_pdf.py --scaling $OUT \\"
echo "      --out discovery_suite/report/saranga_discovery_brief.pdf"
