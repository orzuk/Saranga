#!/bin/bash -l
#
# SLURM job: Erdős-problem coverage over the v4 100k parsed corpus.
# CPU-only, no API cost. For each of the 1217 catalogued Erdős problems, finds
# the best-matching open_problem/conjecture node in our corpus and (for covered
# ones) cross-references the T-OPEN sweep for a candidate resolving theorem.
#
# Usage (PREFERRED — plain sbatch propagates exported env):
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   sbatch discovery_suite/open_problems/erdos_cluster.sh
#
# The CSV ships IN THE REPO (discovery_suite/open_problems/erdos_problems.csv,
# 1217 problems) — nothing to scp up. Override with ERDOS_CSV only if importing
# a newer export, and run erdos_reconcile.py against it first.
#
# Resource profile mirrors sweep_cluster.sh (32G/4cpu, glacier). The default
# open_problem+conjecture pass is minutes; --match-theorems is the expensive
# mode (millions of theorem nodes) — hence the 4h wall.
#SBATCH --job-name=erdos_cov
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=glacier
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4

set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed_100k_v4 dir (parent of the 20 category dirs)}"
ERDOS_CSV="${ERDOS_CSV:-discovery_suite/open_problems/erdos_problems.csv}"
OUT="${OUT:-discovery_suite/open_problems/runs/erdos_coverage_100k.csv}"
# NOTE 0.25 is the script default, tuned on a tiny local corpus and NOT
# trustworthy here: the score is a max over all corpus nodes, so the noise floor
# rises with corpus size. This first run is a CALIBRATION run — set the
# threshold low, read the printed score histogram in the .out log, then re-run
# with a cut above p99.
THRESHOLD="${THRESHOLD:-0.15}"
MATCH_THEOREMS="${MATCH_THEOREMS:-0}"   # set to 1 for the wider, noisier pass

EXTRA=()
[[ "$MATCH_THEOREMS" == "1" ]] && EXTRA+=(--match-theorems)

echo "[erdos_cov] root=$ROOT csv=$ERDOS_CSV out=$OUT threshold=$THRESHOLD match_theorems=$MATCH_THEOREMS"

# No --accept-bare on the cluster: tier3 files carry _rules.json suffixes and
# arXiv ids, so the canonical loader (shared.corpus.stream_papers) picks them up.
python3 discovery_suite/open_problems/erdos_coverage.py \
    --erdos-csv "$ERDOS_CSV" \
    --corpus-dir "$ROOT" \
    --threshold "$THRESHOLD" \
    --show 40 \
    --out "$OUT" \
    ${EXTRA[@]+"${EXTRA[@]}"}   # guarded expansion: bash 3.2 + set -u trips on an empty array

echo "[erdos_cov] done -> $OUT"
echo "[next] 1. read the score histogram above and pick a real threshold"
echo "       2. re-run with THRESHOLD=<p99+> to get the headline coverage number"
echo "       3. spot-check top rows:"
echo "          python3 discovery_suite/open_problems/o4_judge.py --problem <match_key> --theorem <resolving_theorem> --model opus"
