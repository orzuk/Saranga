#!/bin/bash
#SBATCH --job-name=atlas
#SBATCH --time=4:00:00
#SBATCH --mem=96G
#SBATCH --cpus-per-task=1
#SBATCH --output=atlas_%j.log
source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
python3 atlas_pilot.py
