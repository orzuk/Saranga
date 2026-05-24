#!/bin/bash
# Rerun Method E Phase 2b (retrieve) only, on an existing run directory.
#
# Used to regenerate candidates.jsonl + candidates_ranked.csv after
# changes to retrieve_pairs.py (filter fixes, raw_latex emission, etc.).
# Skips Phases 1L/1R/1.5 because indices are unchanged and slow to
# rebuild (~1h+ on full corpus).
#
# Phase 2b needs ~30-60GB RAM at v2 corpus scale (1.24M theorems) to
# hold the loaded rows + the inverted index. After the split-index
# refactor (see scripts/split_theorems_index.py) RAM drops to ~750MB.
#
# Usage:
#   sbatch --export=RUN_DIR=/path/to/run scripts/run_method_e_retrieve_only.sh
#
#SBATCH --job-name=me_retrieve
#SBATCH --time=4:00:00
#SBATCH --mem=80G
#SBATCH --cpus-per-task=4
#SBATCH --output=/sci/home/orzuk/method_e_jobs/me_retrieve.%j.log
#SBATCH --error=/sci/home/orzuk/method_e_jobs/me_retrieve.%j.log

set -euo pipefail

mkdir -p "$HOME/method_e_jobs"

source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
cd /sci/labs/orzuk/orzuk/github/Saranga

if [ -z "${RUN_DIR:-}" ]; then
  echo "ERROR: RUN_DIR not set. Pass --export=RUN_DIR=..."
  exit 2
fi

echo "[me_retrieve] === Method E Phase 2b retrieve ==="
echo "[me_retrieve] RUN_DIR  = $RUN_DIR"
echo "[me_retrieve] starting at $(date) on $(hostname)"

cd src
python3 -u -m discovery.method_e.run retrieve \
  --run-dir "$RUN_DIR" \
  --no-cutoff

echo "[me_retrieve] done at $(date)"
ls -lh "$RUN_DIR"
