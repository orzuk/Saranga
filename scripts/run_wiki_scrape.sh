#!/bin/bash
# run_wiki_scrape.sh — SLURM launcher for src/wiki_scrape.py.
#
# Walks one site / pass (default: site=wikipedia, pass=A) and writes
# per-seed-page JSON files into NATURALPROOFS_DIR/raw/ on the cluster.
# Those files are picked up by scripts/clean_foundation.py on the next
# foundation-index rebuild.
#
# Submit:
#   sbatch scripts/run_wiki_scrape.sh                  # site=wikipedia pass=A
#   SITE=wikipedia PASS=A sbatch scripts/run_wiki_scrape.sh
#   SITE=wikipedia PASS=A ONLY=List_of_conjectures sbatch scripts/run_wiki_scrape.sh
#
# Override via env vars before sbatch:
#   SITE          which site config to run (default: wikipedia)
#   PASS          which pass to run within the site (default: A)
#   ONLY          space-separated seed pages to restrict to (default: all)
#   SLEEP         seconds between API calls (default: 1.0)
#   MAX_ARTICLES  cap per seed page, for smoke tests (default: unlimited)
#   FORCE         set to 1 to overwrite existing per-seed JSON files
#
# This script mirrors scripts/run_proofwiki_scrape.sh in shape so the
# cluster-side workflow stays consistent across sources.

#SBATCH --job-name=wiki_scrape
#SBATCH --partition=glacier
#SBATCH --time=08:00:00
#SBATCH --mem=2G
#SBATCH --cpus-per-task=1
#SBATCH --output=/sci/home/orzuk/wiki_scrape/wiki_scrape.%j.log
#SBATCH --error=/sci/home/orzuk/wiki_scrape/wiki_scrape.%j.log

export PYTHONHASHSEED=0   # deterministic output (see src/config.py)

set -euo pipefail

mkdir -p "$HOME/wiki_scrape"

# Defaults — overridable via env vars at sbatch time.
SITE="${SITE:-wikipedia}"
PASS="${PASS:-A}"
SLEEP="${SLEEP:-1.0}"
MAX_ARTICLES="${MAX_ARTICLES:-}"
ONLY="${ONLY:-}"
FORCE="${FORCE:-0}"

# Project venv on cluster.
source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate

# Move to the repo + pull latest. Same pattern as run_foundation_audit.sh.
cd /sci/labs/orzuk/orzuk/github/Saranga
git pull --ff-only origin main \
    || echo "[run_wiki_scrape] git pull skipped/failed; continuing with local code"

# Build the python args.
ARGS=(--site "$SITE" --pass "$PASS" --sleep "$SLEEP")
if [[ -n "$MAX_ARTICLES" ]]; then
    ARGS+=(--max-articles "$MAX_ARTICLES")
fi
if [[ -n "$ONLY" ]]; then
    # shellcheck disable=SC2086
    ARGS+=(--only $ONLY)
fi
if [[ "$FORCE" == "1" ]]; then
    ARGS+=(--force)
fi

echo "[run_wiki_scrape] starting at $(date)"
echo "[run_wiki_scrape] site=$SITE  pass=$PASS  sleep=$SLEEP  only=${ONLY:-<all>}"
echo "[run_wiki_scrape] cmd: python src/wiki_scrape.py ${ARGS[*]}"

python src/wiki_scrape.py "${ARGS[@]}"

echo "[run_wiki_scrape] done at $(date)"

# Summary of what landed.
echo ""
echo "[run_wiki_scrape] output files in NATURALPROOFS_DIR/raw/:"
python - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, "src")
from config import NATURALPROOFS_DIR
raw = NATURALPROOFS_DIR / "raw"
if raw.exists():
    for f in sorted(raw.glob("naturalproofs_*wikipedia*.json")):
        kb = f.stat().st_size // 1024
        print(f"  {f.name}  ({kb} KB)")
else:
    print(f"  (raw dir not found: {raw})")
PY
