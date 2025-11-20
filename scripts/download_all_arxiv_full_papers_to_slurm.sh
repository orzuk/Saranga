#!/usr/bin/env bash
#
# Usage: `./download_all_arxiv_full_papers_to_slurm.sh`
SCRIPT_DIR="/sci/labs/orzuk/orzuk/github/ArXivAnalysis/scripts"
JOB_SCRIPT="${SCRIPT_DIR}/download_one_month_arxiv_papers.sh"

START_YEAR=1991
END_YEAR=2025

for YEAR in $(seq $START_YEAR $END_YEAR); do
  for MONTH in $(seq -w 1 12); do
    JOBNAME="arxiv_${YEAR}_${MONTH}"
    echo "Submitting job ${JOBNAME}"
    sbatch \
      --job-name=${JOBNAME} \
      --export=YEAR=${YEAR},MONTH=${MONTH} \
      $JOB_SCRIPT
  done
done
