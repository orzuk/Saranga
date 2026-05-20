#!/bin/bash
# run_foundation_audit.sh — sample 50 v2 papers and measure foundation-graph
# coverage (the Method E gating audit).
#
# Submit as: sbatch scripts/run_foundation_audit.sh
# Or run directly inside an interactive srun allocation: bash scripts/run_foundation_audit.sh
#
# Output:
#   $HOME/method_e_jobs/found_audit.<jobid>.log     (stdout, the verbose run trace + summary)
#   $HOME/foundation_audit_v2_with_books.csv        (per-node audit rows)
#
# What it does:
#   - Walks tier3 corpus pointed at by env var V2 (default = v2 path below).
#   - Reservoir-samples 50 papers (memory-safe; no full-corpus materialization).
#   - Re-links each sample against the foundation index named by
#     config.FOUNDATION_INDEX_PATH (currently clean_foundation_with_books.json,
#     ~137 books / 51,415 entries).
#   - Prints walk progress every 5s, per-5-paper linking progress, and final
#     coverage summary.
#
# Gate (from open_problem_analysis.md §10):
#   grounded_to coverage on theorem-like nodes < 30% → fall back to operator +
#   token features for Method E's signature.foundation_ids.

#SBATCH --job-name=found_audit
#SBATCH --partition=glacier
#SBATCH --time=01:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=2
#SBATCH --output=/sci/home/orzuk/method_e_jobs/found_audit.%j.log
#SBATCH --error=/sci/home/orzuk/method_e_jobs/found_audit.%j.log

set -euo pipefail

mkdir -p "$HOME/method_e_jobs"

# Activate project env
source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
cd /sci/labs/orzuk/orzuk/github/Saranga

# Make sure we're on latest code
git pull --ff-only origin main || echo "[run_foundation_audit] git pull skipped/failed; continuing with local code"

# Tier3 corpus location (override by exporting V2 before sbatch)
V2="${V2:-/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v2}"
OUT="${AUDIT_OUT:-$HOME/foundation_audit_v2_with_books.csv}"
SAMPLE="${SAMPLE:-50}"

echo "[run_foundation_audit] corpus = $V2"
echo "[run_foundation_audit] output = $OUT"
echo "[run_foundation_audit] sample = $SAMPLE"
echo "[run_foundation_audit] starting at $(date)"

TIER3_DIR="$V2" python -m src.discovery.common.foundation_audit \
  --sample "$SAMPLE" \
  --fresh-link \
  --out "$OUT"

echo "[run_foundation_audit] done at $(date)"
echo "[run_foundation_audit] CSV: $OUT"
