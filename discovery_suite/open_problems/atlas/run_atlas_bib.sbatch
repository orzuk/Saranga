#!/bin/bash
#SBATCH --job-name=atlas_bib
#SBATCH --time=6:00:00
#SBATCH --mem=48G
#SBATCH --cpus-per-task=1
#SBATCH --output=atlas_bib_%j.log
source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
python3 atlas_bib.py "$@"
