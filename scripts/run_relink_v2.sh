#!/bin/bash
# run_relink_v2.sh — re-link the v2 tier3 corpus against the current
# foundation index (config.FOUNDATION_INDEX_PATH, currently
# clean_foundation_with_books.json / 137 books / 51,415 entries).
#
# Wraps `python -m src.run_pipeline --operations link`. The op rewrites
# grounded_to edges in-place across all v2 JSONs using a single shared
# Aho-Corasick automaton over the foundation index.
#
# Submit: sbatch scripts/run_relink_v2.sh
# Override corpus path: V2=/some/other/path sbatch scripts/run_relink_v2.sh

#SBATCH --job-name=relink_v2
#SBATCH --partition=glacier
#SBATCH --time=03:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --output=/sci/home/orzuk/method_e_jobs/relink_v2.%j.log
#SBATCH --error=/sci/home/orzuk/method_e_jobs/relink_v2.%j.log

export PYTHONHASHSEED=0   # deterministic output (see src/config.py)

set -euo pipefail

mkdir -p "$HOME/method_e_jobs"

source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
cd /sci/labs/orzuk/orzuk/github/Saranga

V2="${V2:-/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v2}"

echo "[run_relink_v2] corpus = $V2"
echo "[run_relink_v2] starting at $(date) on $(hostname)"

# op_link auto-discovers FOUNDATION_INDEX_PATH from config.py
python -m src.run_pipeline \
  --operations link \
  --out-dir "$V2"

echo "[run_relink_v2] done at $(date)"
