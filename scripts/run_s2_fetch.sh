#!/bin/bash
# run_s2_fetch.sh — populate the Semantic Scholar citation-graph cache
# for the IDs Method E will query.
#
# The fetch is idempotent and resumable. SQLite cache keyed by paper_id;
# subsequent runs only fetch missing IDs. Free API.
#
# Submit: sbatch scripts/run_s2_fetch.sh
#
# Required env var:
#   S2_API_KEY   — Semantic Scholar API key (request at api.semanticscholar.org).
#                  Without it, the fetcher falls back to ~2s/paper anonymous
#                  rate-limit; with it, ~0.15s/paper. For 96k papers that's
#                  the difference between ~12-15h and ~4-5h.
#
# Optional env vars:
#   IDS_FROM     — comma-separated jsonl paths whose paper_id columns get
#                  queued for fetch. Default: smoke run's problems+theorems.
#   S2_CACHE     — sqlite path (default ~/method_e_cache/s2_cache.sqlite)
#
# To run BEFORE method_e_smoke (so the citation-novelty filter is hot),
# either pre-seed IDS_FROM from an earlier Method E index run, or run
# this AFTER index phases land problems.jsonl + theorems.jsonl.

#SBATCH --job-name=s2_fetch
#SBATCH --partition=glacier
#SBATCH --time=16:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --output=/sci/home/orzuk/method_e_jobs/s2_fetch.%j.log
#SBATCH --error=/sci/home/orzuk/method_e_jobs/s2_fetch.%j.log

export PYTHONHASHSEED=0   # deterministic output (see src/config.py)

set -euo pipefail

mkdir -p "$HOME/method_e_jobs" "$HOME/method_e_cache"

source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
cd /sci/labs/orzuk/orzuk/github/Saranga

S2_CACHE="${S2_CACHE:-$HOME/method_e_cache/s2_cache.sqlite}"
DEFAULT_RUN_DIR="${RUN_DIR:-$HOME/method_e_runs/v2_smoke_$(date +%Y%m%d)}"
IDS_FROM="${IDS_FROM:-$DEFAULT_RUN_DIR/problems.jsonl,$DEFAULT_RUN_DIR/theorems.jsonl}"

echo "[run_s2_fetch] cache = $S2_CACHE"
echo "[run_s2_fetch] ids-from = $IDS_FROM"
echo "[run_s2_fetch] api-key = ${S2_API_KEY:+SET (anon mode if blank)}"
echo "[run_s2_fetch] starting at $(date) on $(hostname)"

if [ -z "${S2_API_KEY:-}" ]; then
  echo "[run_s2_fetch] WARNING: S2_API_KEY not set; running in anonymous mode"
  echo "[run_s2_fetch]          (rate-limited ~2s/paper; total time will be"
  echo "[run_s2_fetch]           ~12-15h instead of ~4-5h)"
fi

python -m src.discovery.common.citation_graph fetch \
  --cache "$S2_CACHE" \
  --ids-from "$IDS_FROM" \
  ${S2_API_KEY:+--api-key "$S2_API_KEY"}

echo "[run_s2_fetch] done at $(date)"

# Print cache stats so we know the population state
python -m src.discovery.common.citation_graph stats --cache "$S2_CACHE" || true
