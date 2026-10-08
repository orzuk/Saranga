#!/bin/bash -l
#SBATCH --job-name=arxiv_month
#SBATCH --output=logs/%x_ID_%j.out
#SBATCH --error=logs/%x_ID_%j.err
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2

export PYTHONHASHSEED=0   # deterministic output (see src/config.py)


cd ../src || exit 1

YEAR=${YEAR:-$(date +%Y)}
MONTH=${MONTH:-$(date +%m)}
echo "Starting download for ${YEAR}-${MONTH}"

FORMATS="pdf html latex"

PYTHON=/<cluster>/<user>/software/miniforge3/envs/pymol-env/bin/python

current="${YEAR}-${MONTH}-01"
while [[ "${current:0:7}" == "${YEAR}-${MONTH}" ]]; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Processing-slurm $current …"

  # ←– Python invocation must end here with a backslash
  $PYTHON extract_arxiv_data.py \
    --start  "$current" \
    --end    "$current" \
    --formats $FORMATS \
    --verbose

  # ←– This is now a separate shell command
  current=$(date -I -d "$current + 1 day")
done

echo "Finished ${YEAR}-${MONTH}"
