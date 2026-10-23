#!/bin/bash
#SBATCH --job-name=kourovka
#SBATCH --time=3:00:00
#SBATCH --mem=8G
#SBATCH --output=kourovka_%j.log
source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate
python3 kourovka_scan.py
