#!/bin/bash -l
#
# SLURM ARRAY job: post-hoc distilled-rule subset selection, one task per
# --search-algo. Each task is an INDEPENDENT search over the same precomputed
# replay store, so the array is a pure throughput win -- the arms never need to
# talk to each other, and each writes its own --out-tag'd output files.
#
# CPU-ONLY, and deliberately so. The inner loop is frozenset intersection and
# dict lookup (an exact replica of silver_distillation_merged.metrics()); there
# is no dense numeric kernel, so a GPU buys nothing here. Do not request one.
#
# Each task is SINGLE-THREADED python. cpus-per-task=2 is headroom, not
# parallelism -- the arms scale by running side by side, not by adding cores.
# (A --workers flag that forks the per-step candidate sweep would cut each arm
# ~10x; it does not exist yet. Ask before assuming this finishes in an hour.)
#
# WHAT MUST BE ON THE CLUSTER (~65MB; no .tex, no parser, no API):
#   src/LLMVersion/merged_eval_v51_train60_v2/subset_search/precompute/*.json
#   src/LLMVersion/merged_eval_v51_train60_v2/silver_gold/*.csv
#   src/LLMVersion/merged_eval_v51_train60_v2/trajectory/scores.jsonl  (optional,
#       only for --validate-only)
#   corpus/silver/split_opus5.csv
#   scripts/rule_subset_search.py + scripts/rule_subset_algos.py  (git pull)
#
# Push the untracked data from the Mac:
#   R=/sci/labs/orzuk/orzuk/.../Saranga     # repo root on the cluster
#   rsync -av --relative \
#     src/LLMVersion/merged_eval_v51_train60_v2/subset_search/precompute \
#     src/LLMVersion/merged_eval_v51_train60_v2/silver_gold \
#     src/LLMVersion/merged_eval_v51_train60_v2/trajectory/scores.jsonl \
#     corpus/silver/split_opus5.csv \
#     cluster:$R/
#
# Submit ALL SEVEN arms:
#   mkdir -p logs
#   sbatch --array=0-6 scripts/subset_search_cluster.sh
#
# Submit ONE arm (indices below), e.g. lazy as a 10-minute smoke test FIRST:
#   sbatch --array=0 scripts/subset_search_cluster.sh
#
#   0 lazy   1 greedy   2 distorted   3 localsearch   4 poss   5 porss   6 dinkelbach
#   7 poss_empty   8 localsearch_empty   9 porss_empty
#     (the three seeded arms, rebuilt from nothing -- independent of greedy)
#
# Outputs are tagged cluster_<algo>, NOT <algo>. Tag "greedy" would name its
# curve greedy_curve.csv -- the committed Sep-01 file make_sep01_pdf.py reads --
# so that arm would refuse to start, and forcing it would silently repoint the
# report at a different run. Override with TAG_PREFIX=... for a second sweep.
#
# Re-running an arm refuses to clobber its previous output. To replace it:
#   OVERWRITE=1 sbatch --array=6 scripts/subset_search_cluster.sh
#
#SBATCH --job-name=subset_search
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --partition=glacier
#SBATCH --time=24:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2

# Fail loudly rather than echoing a false "done" after a killed python.
set -euo pipefail

EVAL_DIR="${EVAL_DIR:-src/LLMVersion/merged_eval_v51_train60_v2}"
SPLIT="${SPLIT:-train}"
OBJECTIVE="${OBJECTIVE:-m3}"
CV="${CV:-5}"
OVERWRITE="${OVERWRITE:-0}"

ARMS=(lazy greedy distorted localsearch poss porss dinkelbach poss_empty
      localsearch_empty porss_empty)

IDX="${SLURM_ARRAY_TASK_ID:-${ARM_INDEX:-0}}"
ALGO="${ARMS[$IDX]}"
TAG="$ALGO"          # arm label; ALGO may be rewritten below (poss_empty)

# Per-arm flags, as a case rather than a `declare -A` map: bash 3.2 (still the
# system bash on macOS, where this gets dry-run) has no associative arrays and
# fails SILENTLY here -- every arm would inherit the last entry's flags, which
# set -e does not catch. A case statement is correct on every bash.
#
# poss gets more iterations than porss because a porss crossover diffs far from
# its parent and forces a near-full 60-paper rescore (~0.43s), where a poss
# bit-flip touches ~5.8 papers (~0.085s) -- equal iteration counts would NOT be
# equal compute.
case "$ALGO" in
  poss)   FLAGS="--poss-iters ${POSS_ITERS:-20000}" ;;
  # arm 7: POSS as the paper actually states it -- the front starts EMPTY, not
  # warm-started from greedy. Arms 3/4/5/6 all seed from greedy and returned
  # its selection unchanged on every fold, so they never tested anything
  # independent of it. This is the one arm that can disagree with greedy.
  poss_empty) ALGO=poss
              FLAGS="--poss-iters ${POSS_ITERS:-40000} --poss-seed empty" ;;
  # arms 8/9: the same two, also built from nothing. With arm 7 and distorted
  # (which always starts empty) this makes all four modern methods tested
  # head-to-head against greedy on their own terms, not as polishers of it.
  localsearch_empty) ALGO=localsearch
              FLAGS="--ls-seed empty --ls-rounds ${LS_ROUNDS:-400}" ;;
  porss_empty) ALGO=porss
              FLAGS="--poss-iters ${PORSS_ITERS:-40000} --poss-seed empty" ;;
  porss)  FLAGS="--poss-iters ${PORSS_ITERS:-5000}" ;;
  # the default inner solver (distorted) always runs its full k=188 iterations
  # with no early stop, making it the single most expensive arm; the
  # patience-bounded greedy inner is roughly half the cost.
  dinkelbach) FLAGS="--dink-rounds ${DINK_ROUNDS:-4} --dink-inner ${DINK_INNER:-greedy}" ;;
  *)      FLAGS="" ;;
esac

[ "$OVERWRITE" = "1" ] && FLAGS="$FLAGS --overwrite"

echo "[subset_search] task=$IDX algo=$ALGO eval_dir=$EVAL_DIR split=$SPLIT"
echo "[subset_search] objective=$OBJECTIVE cv=$CV flags=${FLAGS:-none}"
echo "[subset_search] host=$(hostname) cpus=${SLURM_CPUS_PER_TASK:-?} started=$(date -Is)"

# Word-splitting $FLAGS is intended here (bash, not zsh): the flags must reach
# argparse as separate argv entries.
# shellcheck disable=SC2086
python3 -u scripts/rule_subset_search.py search \
    --eval-dir "$EVAL_DIR" \
    --split "$SPLIT" \
    --objective "$OBJECTIVE" \
    --cv "$CV" \
    --search-algo "$ALGO" \
    --out-tag "${TAG_PREFIX:-cluster}_$TAG" \
    $FLAGS

echo "[subset_search] $ALGO done at $(date -Is)"
echo "[next] compare arms:"
echo "  python3 -c \"import json,glob;"
echo "    [print(f'{json.load(open(f))[\\\"algo\\\"]:12s}'"
echo "      f' m3={json.load(open(f))[\\\"scores\\\"][\\\"selected\\\"][\\\"m3\\\"][\\\"f1\\\"]}'"
echo "      f' k={len(json.load(open(f))[\\\"selected_units\\\"])}')"
echo "     for f in sorted(glob.glob('$EVAL_DIR/subset_search/selection_*.json'))]\""
