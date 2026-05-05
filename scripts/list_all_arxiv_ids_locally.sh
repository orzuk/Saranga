#!/bin/bash -l
#SBATCH --job-name=arxiv_list_ids
#SBATCH --output=arxiv_list_ids.log
#SBATCH --partition=glacier
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G

# Load your Python environment (so urllib is available, and config.py in PYTHONPATH)
module load python/3.10

# Full path to your CLI script
SCRIPT=/<cluster>/<user>/github/Authomathics/src/extract_arxiv_data.py

# Ensure it’s executable (optional if already done)
chmod +x "$SCRIPT"

# Run the list_ids subcommand and force a full re-download of every arXiv ID
python "$SCRIPT" list_ids \
    --update
