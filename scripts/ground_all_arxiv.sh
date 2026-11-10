#!/bin/bash
# Ground the whole-arXiv T3 parse (parsed_all_v7/YYYY/MM/DD.tar.gz) in the textbook concept layer
# (foundation/books_v7b/concepts.json), on the HUJI cluster. CPU only, no model.
#
#   bash scripts/ground_all_arxiv.sh [NAME]            default NAME = all_v7
#
# One SLURM task per year scans its day archives (ground_papers --scan-only YEAR), then one job
# pools the scans (--finalize): the common-vocabulary cut (a term in more than 10% of the papers)
# is taken over the whole corpus, as it was for the 100K. Output: one <category>.jsonl per primary
# category under foundation/books_v7b/grounding/NAME/, plus summary.json; the format is that of
# grounding/v7 (the 100K). The paper JSONs are untouched: portal/bundle_t3.py --grounding copies
# the edges in when the portal bundles are built.
set -euo pipefail
NAME="${1:-all_v7}"
REPO=/sci/labs/orzuk/orzuk/github/Saranga
DATA=/sci/labs/orzuk/orzuk/projects/Saranga
ARXIV=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data
ROOT="${ROOT:-$ARXIV/parsed_all_v7}"
CATS="${CATS:-/sci/labs/orzuk/orzuk/projects/Authomathics/discovery/open_full/cats.tsv.gz}"   # id -> primary category
OUT=$DATA/foundation/books_v7b/grounding/$NAME
CONCEPTS=$DATA/foundation/books_v7b/concepts.json
PRE="source /sci/labs/orzuk/orzuk/venvs/authomathics-venv/bin/activate; cd $REPO/src"
LOGS=$DATA/logs
mkdir -p "$OUT" "$LOGS"
YEARS=($(ls "$ROOT" | grep -E '^[0-9]{4}$' | sort))
N=${#YEARS[@]}
echo "$N years: ${YEARS[0]} .. ${YEARS[$((N-1))]}  ->  $OUT"
sub() { sbatch --parsable --output="$LOGS/ground_${NAME}_%x_%A_%a.log" "$@"; }
j1=$(sub --job-name=ground_scan --array=0-$((N-1)) --cpus-per-task=8 --mem=32G --time=6:00:00 --wrap \
  "bash -c '$PRE; Y=\$(ls $ROOT | grep -E \"^[0-9]{4}\$\" | sort | sed -n \$((SLURM_ARRAY_TASK_ID+1))p); \
   python3 -m structured_math.books.ground_papers $ROOT --out $OUT --cats $CATS --concepts $CONCEPTS --years \$Y --scan-only \$Y --jobs 8'")
j2=$(sub --job-name=ground_final --dependency=afterok:$j1 --cpus-per-task=2 --mem=64G --time=4:00:00 --wrap \
  "bash -c '$PRE; python3 -m structured_math.books.ground_papers --out $OUT --concepts $CONCEPTS --finalize && rm -r $OUT/scan'")
echo "scan $j1 (array of $N) -> finalize $j2"
