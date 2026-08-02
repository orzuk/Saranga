#!/bin/bash
#
# Submitter for the whole semantic T-OPEN pipeline. Not an sbatch job itself —
# it chains the stage jobs with SLURM dependencies so one command launches
# textstore -> encode -> dense retrieve, each starting only if the previous
# stage's array finished cleanly.
#
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   export RUN=$PWD/discovery_suite/open_problems/runs/dense_100k
#   export MODELS="qwen3-0.6b bge-m3"
#   export ARMS="node:raw node:canon ctx-concat:raw"
#   bash discovery_suite/open_problems/embed_cluster.sh
#
# The text store is built ONCE and shared by every (model, view, canon) arm —
# canonicalization and graph-context assembly do not depend on the embedder, and
# rebuilding them per arm would waste the majority of the CPU budget.
#
# Watch everything: python3 discovery_suite/open_problems/watch_open.py $RUN

set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed corpus dir}"
RUN="${RUN:?set RUN to a run directory (text store + vectors + outputs live here)}"
SHARDS="${SHARDS:-64}"
TEXT_TASKS="${TEXT_TASKS:-32}"      # concurrent CPU array tasks
ENC_TASKS="${ENC_TASKS:-8}"         # concurrent GPU array tasks per arm
MODELS="${MODELS:-qwen3-0.6b}"
ARMS="${ARMS:-node:raw node:canon ctx-concat:raw}"
TOPK="${TOPK:-50}"

cd "$(dirname "$0")/../.."
HERE=discovery_suite/open_problems
export STORE="$RUN/textstore"
export VECS="$RUN/vectors"
mkdir -p "$RUN" logs
export PYTHONPATH="$PWD/discovery_suite:${PYTHONPATH:-}"

# ── plan: enumerate the corpus once, on the login node (seconds) ─────────────
if [ ! -f "$STORE/files.txt" ]; then
    echo "[submit] planning file list …"
    python3 -m embed.textstore plan --root "$ROOT" --out "$STORE"
fi
N_FILES=$(wc -l < "$STORE/files.txt")
echo "[submit] $N_FILES corpus files, $SHARDS shards"

# ── stage 1: text store (CPU array) ─────────────────────────────────────────
TS_JOB=$(ROOT="$ROOT" STORE="$STORE" SHARDS="$SHARDS" \
    sbatch --parsable --array=0-$((SHARDS-1))%${TEXT_TASKS} "$HERE/textstore_cluster.sh")
echo "[submit] textstore array = $TS_JOB"

# ── stage 2+3: one encode array and one retrieval job per arm ───────────────
# Arms are independent, so they queue in parallel and each depends only on the
# shared text store.
DENSE_JOBS=()
for MODEL in $MODELS; do
  for ARM in $ARMS; do
    VIEW="${ARM%%:*}"; CANON="${ARM##*:}"
    ENC_JOB=$(STORE="$STORE" VECS="$VECS" MODEL="$MODEL" VIEW="$VIEW" CANON="$CANON" \
        SHARDS="$SHARDS" \
        sbatch --parsable --dependency=afterok:"$TS_JOB" \
               --array=0-$((ENC_TASKS-1)) "$HERE/encode_cluster.sh")
    OUT="$RUN/open_dense_${MODEL}_${VIEW}_${CANON}.csv"
    D_JOB=$(VECS="$VECS" MODEL="$MODEL" VIEW="$VIEW" CANON="$CANON" \
        TOPK="$TOPK" OUT="$OUT" MODE=all \
        sbatch --parsable --dependency=afterok:"$ENC_JOB" "$HERE/dense_cluster.sh")
    DENSE_JOBS+=("$D_JOB")
    echo "[submit] $MODEL/$VIEW/$CANON: encode=$ENC_JOB dense=$D_JOB -> $OUT"
  done
done

echo
echo "[submit] queued. watch with:"
echo "  squeue -u \$USER"
echo "  python3 $HERE/watch_open.py $RUN"
echo
echo "[submit] when the dense CSVs land, fuse with the lexical sweep:"
echo "  python3 $HERE/o1c_fuse.py --lexical $HERE/runs/open_sweep_100k_raw.csv \\"
echo "      --dense $RUN/open_dense_*.csv --out $RUN/open_fused.csv"
