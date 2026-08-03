#!/bin/bash -l
#
# Stage 2 (GPU array): text-store shards -> fp16 normalized vectors.
#
# Cost check before you launch: this is O(N) in nodes, ONCE. At ~800 nodes/s on
# an L40s, the 100k corpus (~1.6M retrievable nodes) is ~33 GPU-minutes per
# (model, view, canon) arm. The whole champion configuration — raw + canonical
# node views plus one ctx-concat pass — is under 2 GPU-hours. ctx-late needs NO
# pass of its own; it is assembled from the node vectors at search time.
#
#   export STORE=.../textstore_100k
#   export VECS=.../vectors
#   export MODEL=qwen3-0.6b VIEW=node CANON=raw
#   sbatch --array=0-15 discovery_suite/open_problems/encode_cluster.sh
#
# The array need not cover every shard: --shard-stride makes task k take shards
# k, k+stride, k+2*stride, … so 16 tasks cleanly cover 64 shards.
#
# Partitions (per scripts/launch_qwen_judge_server.sh):
#   catfish  l4    24GB   fine for minilm/distilbert/specter2
#   salmon   l40s  48GB   default; comfortable for bge-m3 and qwen3-0.6b
#   dogfish  a100  80GB   needed for qwen3-4b
#SBATCH --job-name=open_encode
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=08:00:00
#SBATCH --mem=48G
#SBATCH --cpus-per-task=4

set -euo pipefail

STORE="${STORE:?set STORE to the text-store dir built by textstore_cluster.sh}"
VECS="${VECS:?set VECS to the vector-store output root}"
MODEL="${MODEL:-qwen3-0.6b}"
VIEW="${VIEW:-node}"
CANON="${CANON:-raw}"
SHARDS="${SHARDS:-64}"
STRIDE="${STRIDE:-}"
BATCH="${BATCH:-}"
MAX_TOKENS="${MAX_TOKENS:-}"

# Locate the repo root. NOT via $0: sbatch COPIES the batch script into a spool
# directory, so inside a SLURM job $0 is /var/spool/slurmd/.../slurm_script and
# "$(dirname "$0")/../.." lands in /var/spool. Prefer the directory sbatch was
# invoked from; fall back to $0 only when run directly with bash.
REPO="${REPO:-${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}}"
if [ ! -d "$REPO/discovery_suite" ]; then
    echo "ERROR: no discovery_suite/ under '$REPO'." >&2
    echo "       Submit from the repo root, or pass REPO=/path/to/Authomathics." >&2
    exit 2
fi
cd "$REPO"
export PYTHONPATH="$PWD/discovery_suite:${PYTHONPATH:-}"

# Re-activate the virtualenv. `#!/bin/bash -l` starts a LOGIN shell, which
# re-sources /etc/profile and RESETS PATH -- silently dropping the venv that was
# active when you ran sbatch, so `python3` becomes the system one and torch is
# missing. VIRTUAL_ENV survives in the exported environment, so use that.
VENV="${VENV:-${VIRTUAL_ENV:-}}"
if [ -n "$VENV" ] && [ -f "$VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    . "$VENV/bin/activate"
    echo "[env] venv: $VENV"
fi
echo "[env] python: $(command -v python3)"
# Hard-fail on a missing torch, and REPORT whether the GPU is actually visible.
# A silent CPU fallback is worse than a crash here: the job still "succeeds",
# just ~50x slower, and every timing number it produces is meaningless.
if ! python3 - <<'PYCHK'
import sys
try:
    import torch
except ImportError as exc:
    print(f"ERROR: torch not importable: {exc}", file=sys.stderr)
    sys.exit(3)
cuda = torch.cuda.is_available()
name = torch.cuda.get_device_name(0) if cuda else "-"
print(f"[env] torch {torch.__version__}  cuda_available={cuda}  device={name}")
if not cuda:
    print("WARNING: no GPU visible to torch — this job will run on CPU and any "
          "timing it reports will not reflect the real pipeline.", file=sys.stderr)
PYCHK
then
    echo "       Activate the venv before sbatch, or pass VENV=/path/to/venv." >&2
    exit 3
fi

# One array task per stride slot; default stride = array width so the tasks tile
# the shard range exactly.
if [ -z "$STRIDE" ]; then
    STRIDE="${SLURM_ARRAY_TASK_COUNT:-1}"
fi

echo "[encode] model=$MODEL view=$VIEW canon=$CANON store=$STORE"
echo "[encode] task ${SLURM_ARRAY_TASK_ID:-0}, stride $STRIDE over $SHARDS shards"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

# Fail fast: a missing HF model should cost 30 seconds here, not four hours in.
python3 -m embed.models --check --models "$MODEL"

python3 -m embed.encode \
    --store "$STORE" --out "$VECS" \
    --model "$MODEL" --view "$VIEW" --canon "$CANON" \
    --shard-stride "$STRIDE" \
    ${BATCH:+--batch-size "$BATCH"} \
    ${MAX_TOKENS:+--max-tokens "$MAX_TOKENS"} \
    --status-dir "$VECS/status"

echo "[encode] task ${SLURM_ARRAY_TASK_ID:-0} done"
echo "[watch] python3 discovery_suite/open_problems/watch_open.py $VECS/status"
