#!/bin/bash -l
#
# SLURM job: score the finished rule subsets on the 140 HELD-OUT papers.
#
# The subset search ranks candidates by 5-fold CV *inside the 60 distillation
# papers*. That cannot settle anything against keeping every rule, because
# those 60 papers are the ones the rules were written from -- a rule that fits
# one of them narrowly is in the pool because that paper was in the
# distillation set, so the full set is credited with fit that will not
# transfer. This job puts every arm on the 140 test papers instead, which
# entered no stage of distillation OR selection, and which is the same footing
# as the 0.7563 figure in the Appendix-F deck.
#
# Two steps, one job:
#   1. precompute over the test split  (the only expensive part: one baseline
#      parse per paper plus one isolated run per rule pattern). ~260 s/paper
#      serial on the train split, so ~10 h / workers.
#   2. score every selection_*.json against it -- pure set algebra, seconds,
#      and free for every additional subset once step 1 exists.
#
# Submit:
#   mkdir -p logs
#   sbatch scripts/heldout_frontier_cluster.sh
#
# Step 1 is skipped per-paper if its JSON already exists, so a re-submit after
# a timeout resumes rather than restarting. Pass FORCE=1 to redo them.
#
# NOTE: precompute needs <eval-dir>/groups/*/distilled_rules.py. Without
# them it used to run to completion recording zero units per paper, and
# every arm then scored identically to the base parser; it now refuses.
#
#SBATCH --job-name=heldout_frontier
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=glacier
#SBATCH --time=08:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=16

set -euo pipefail

EVAL_DIR="${EVAL_DIR:-src/LLMVersion/merged_eval_v51_train60_v2}"
TEX_DIR="${TEX_DIR:-corpus/silver/tex_staged}"
SPLIT="${SPLIT:-test}"
WORKERS="${WORKERS:-${SLURM_CPUS_PER_TASK:-8}}"
# FORCE=1 re-does papers whose JSON already exists -- needed once, to
# replace the empty records a run without groups/ left behind.
FORCE="${FORCE:-0}"

echo "[frontier] eval_dir=$EVAL_DIR tex_dir=$TEX_DIR split=$SPLIT workers=$WORKERS"
echo "[frontier] host=$(hostname) started=$(date -Is)"

echo "[frontier] step 1/2: precompute over the $SPLIT split"
python3 -u scripts/rule_subset_search.py precompute \
    --eval-dir "$EVAL_DIR" \
    --tex-dir "$TEX_DIR" \
    --split "$SPLIT" \
    --workers "$WORKERS" \
    ${FORCE:+$([ "$FORCE" = "1" ] && echo --force)}

echo "[frontier] step 2/2: score every selection on the $SPLIT papers"
python3 -u scripts/rule_subset_search.py score \
    --eval-dir "$EVAL_DIR" \
    --split "$SPLIT" \
    --selections "$EVAL_DIR/subset_search/selection_*.json"

echo "[frontier] done at $(date -Is)"
echo "[frontier] results -> $EVAL_DIR/subset_search/heldout_scores_$SPLIT.csv"
