#!/bin/bash
#SBATCH --job-name=proofwiki_scrape
#SBATCH --output=proofwiki_scrape_%j.log
#SBATCH --error=proofwiki_scrape_%j.err
#SBATCH --time=24:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=or.zuk@mail.huji.ac.il

# ProofWiki Comprehensive Scraper
# ===============================
# Scrapes all mathematical definitions and theorems from ProofWiki
#
# Usage:
#   sbatch run_proofwiki_scrape.sh           # Run all core topics
#   sbatch run_proofwiki_scrape.sh all       # Run ALL topics (~130)
#   sbatch run_proofwiki_scrape.sh core      # Run core topics (~20)
#
# The script is INCREMENTAL - it skips topics that already have output files.
# If interrupted, just resubmit and it will continue where it left off.
# Use --force flag in the python command to re-scrape existing topics.

set -e  # Exit on error

# Configuration
CODE_DIR="/sci/labs/orzuk/orzuk/github/Authomathics"
DATA_DIR="/sci/labs/orzuk/orzuk/projects/Authomathics"

# Parse mode argument (default: core)
MODE="${1:-core}"

echo "=============================================="
echo "ProofWiki Scraper - Started at $(date)"
echo "=============================================="
echo "Mode: $MODE"
echo "Code dir: $CODE_DIR"
echo "Data dir: $DATA_DIR"
echo ""

# Change to code directory
cd "$CODE_DIR"

# Ensure output directory exists
mkdir -p "$DATA_DIR/proofwiki/by_topic"

# Run the scraper
# --combined: also creates a single combined JSON file at the end
# Incremental by default: skips topics that already have output files
echo "Starting scraper..."
python src/scrape_all_proofwiki.py \
    --mode "$MODE" \
    --combined

echo ""
echo "=============================================="
echo "Completed at $(date)"
echo "=============================================="

# Show summary of output
echo ""
echo "Output files:"
ls -lh "$DATA_DIR/proofwiki/by_topic/" | head -20
echo ""
echo "Total files: $(ls -1 "$DATA_DIR/proofwiki/by_topic/" | wc -l)"
