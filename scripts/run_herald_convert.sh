#!/bin/bash
#SBATCH --job-name=herald_convert
#SBATCH --output=/<cluster>/<user>/projects/Authomathics/mathlib/herald_convert_%j.log
#SBATCH --time=02:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --partition=glacier

source /<cluster>/<user>/authomathics-venv/bin/activate

DATA_DIR=/<cluster>/<user>/projects/Authomathics
cd /<cluster>/<user>/github/Authomathics

python src/structured_math/mathlib/convert_to_midlevel.py \
  --leandojo-dir $DATA_DIR/mathlib/raw/leandojo_benchmark_4 \
  --output-dir $DATA_DIR/mathlib/midlevel_with_herald \
  --herald \
  --herald-dir $DATA_DIR/mathlib/raw
