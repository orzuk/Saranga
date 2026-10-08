#!/bin/bash
# Method E Phase 2a — S2 citation fetch.
#
# Populates the run dir's s2_citations.sqlite with the Semantic Scholar
# citation graph for every paper that appears in problems.jsonl or
# theorems.jsonl. This is the prerequisite for retrieve_pairs.py's
# `headline_only_no_citation` and `drop_same_author` filters to actually
# drop pairs (otherwise both cites and same_author stay None and the
# filters become no-ops).
#
# Requires an S2 API key — without it, S2 rate-limits aggressively
# (2s/request unauthenticated → 3-5 days for ~100K papers; with a key,
# 0.15s/request → ~3 hours).
#
# Usage:
#   export S2_API_KEY=<your-key>
#   sbatch --export=RUN_DIR=/path/to/run,S2_API_KEY=$S2_API_KEY \
#          scripts/run_method_e_cite.sh
#
#SBATCH --job-name=me_cite
#SBATCH --time=24:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=2
#SBATCH --output=/sci/home/orzuk/method_e_jobs/me_cite.%j.log
#SBATCH --error=/sci/home/orzuk/method_e_jobs/me_cite.%j.log

export PYTHONHASHSEED=0   # deterministic output (see src/config.py)

set -euo pipefail

mkdir -p "$HOME/method_e_jobs"

source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
cd /sci/labs/orzuk/orzuk/github/Saranga

if [ -z "${RUN_DIR:-}" ]; then
  echo "ERROR: RUN_DIR not set. Pass --export=RUN_DIR=..."
  exit 2
fi
if [ -z "${S2_API_KEY:-}" ]; then
  echo "ERROR: S2_API_KEY not set. Pass --export=S2_API_KEY=\$S2_API_KEY"
  exit 2
fi

echo "[me_cite] === Method E Phase 2a S2 citation fetch ==="
echo "[me_cite] RUN_DIR  = $RUN_DIR"
echo "[me_cite] starting at $(date) on $(hostname)"

cd src
# S2 throttles authenticated keys harder than their docs suggest —
# the prior attempt at 0.15s delay hit rate-limit retries constantly,
# averaging ~0.7 req/sec. Use 0.5s = 2 req/sec sustained (under most
# academic-tier limits) for ~11h to fetch ~80K papers.
S2_DELAY="${S2_DELAY:-0.5}"
# --force bypasses phase_cite's "skip if sqlite exists" early return.
# Otherwise resuming after a killed earlier job (with partial sqlite)
# is a no-op. The inner fetch_batch still has skip_existing=True so
# already-fetched papers won't be re-queried — only the missing ones.
python3 -u -m discovery.method_e.run cite \
  --run-dir "$RUN_DIR" \
  --s2-api-key "$S2_API_KEY" \
  --s2-delay "$S2_DELAY" \
  --force

echo "[me_cite] done at $(date)"
ls -lh "$RUN_DIR/s2_citations.sqlite"
