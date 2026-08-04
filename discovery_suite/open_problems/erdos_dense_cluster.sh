#!/bin/bash -l
#
# SLURM job: Erdős coverage by MEANING instead of shared words.
#
# The lexical arm (erdos_array.sh + erdos_merge.py) is the baseline: on the 100k
# corpus it produced one smooth score distribution with no gap, a handful of
# generic nodes matched to dozens of unrelated problems, and exactly one
# verifiable hit (Erdős–Gallai, #184). Its own documented failure mode is that
# Erdős statements are prose and corpus nodes are LaTeX-derived.
#
# This runs the same 1,063 problems through the embedding engine instead. Local
# check on a 6-document pool: the true positives moved from 0.63/0.50 (words) to
# 0.79/0.78 (meaning) while the nearest rival fell to 0.37/0.25 — i.e. a gap
# appeared where token-Jaccard had none. Whether that survives 10^5 candidates
# is what this job answers.
#
# Usage:
#   export STORE=/sci/labs/orzuk/$USER/saranga/textstore_100k
#   export VECS=/sci/labs/orzuk/$USER/saranga/vectors_100k
#   sbatch discovery_suite/open_problems/erdos_dense_cluster.sh
#
# Prerequisite: STORE must already hold the corpus rows (embed/textstore.py) and
# this script injects the Erdős rows as one extra shard, re-encodes ONLY the new
# shard, then searches. Existing corpus vectors are reused — encode skips shards
# that are already done, so this costs one shard of GPU time, not a re-encode.
#
#SBATCH --job-name=erdos_dense
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=02:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=4

set -euo pipefail

STORE="${STORE:?set STORE to the text-store root built by textstore_cluster.sh}"
VECS="${VECS:?set VECS to the vector-store root built by encode_cluster.sh}"
MODEL="${MODEL:-minilm}"
VIEW="${VIEW:-node}"        # Erdős rows have no context, so node is the only view
CANON="${CANON:-raw}"
TOPK="${TOPK:-20}"
ERDOS_CSV="${ERDOS_CSV:-discovery_suite/open_problems/erdos_problems.csv}"
OUT="${OUT:-discovery_suite/open_problems/runs/erdos_dense_100k.csv}"

# Never fall back to $HOME: the ~5GB quota fills and HuggingFace dies mid-run.
export HF_HOME="${HF_HOME:-/sci/labs/orzuk/$USER/hf_cache}"
if ! mkdir -p "$HF_HOME" 2>/dev/null; then
    echo "ERROR: cannot create HF_HOME=$HF_HOME — refusing to fall back to \$HOME" >&2
    exit 4
fi
echo "[env] HF_HOME: $HF_HOME"

echo "[erdos_dense] store=$STORE vecs=$VECS model=$MODEL view=$VIEW canon=$CANON"

# 1. Inject the Erdős problems as one extra text-store shard (role="erdos").
python3 discovery_suite/open_problems/erdos_textstore.py \
    --store "$STORE" --erdos-csv "$ERDOS_CSV"

# 2. Encode. Shards already done are skipped, so in practice this encodes only
#    the Erdős shard. "erdos" is in encode.py's default roles and in
#    QUERY_LIKE_ROLES, so it gets the query-side instruction wrapper.
python3 -m embed.encode --store "$STORE" --out "$VECS" \
    --model "$MODEL" --view "$VIEW" --canon "$CANON"

# 3. Search. The doc side is the corpus's own QUESTION nodes (role "query"),
#    because coverage asks "is this problem stated in our corpus" — not "is it
#    resolved". Use --doc-roles doc for the resolution question instead.
#    --no-temporal: an Erdős problem predates every arXiv paper, and the rows
#    carry year=0, so the year gate would suppress everything.
python3 discovery_suite/open_problems/o1b_dense_sweep.py all \
    --vectors "$VECS" --model "$MODEL" --view "$VIEW" --canon "$CANON" \
    --query-roles erdos --doc-roles query \
    --no-temporal --top-k "$TOPK" --out "$OUT"

echo "[erdos_dense] done -> $OUT"
echo "[next] compare against the lexical arm:"
echo "  python3 discovery_suite/open_problems/erdos_compare.py \\"
echo "      --lexical discovery_suite/open_problems/runs/erdos_coverage_100k.csv \\"
echo "      --dense   $OUT"
