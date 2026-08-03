#!/bin/bash -l
#
# Stage 3 (GPU): dense problem->theorem retrieval, map-reduce over doc shards.
#
# Two modes:
#   MODE=all     one job does everything. Correct choice at 100k: the whole
#                scoring pass is 15,143 x 1,589,327 x 1024 = 2.4e13 FLOPs,
#                i.e. under a minute of L40s tensor-core time. The lexical
#                inverted-index rank took ~57 CPU-minutes for the same work.
#   MODE=map     array over doc shards, then a reduce. Needed once the corpus is
#                large enough that one task cannot stream all shards in the wall
#                clock (the 3M run).
#
#   export VECS=.../vectors MODEL=qwen3-0.6b VIEW=node CANON=raw
#   export OUT=discovery_suite/open_problems/runs/open_dense_qwen_node_raw.csv
#   sbatch discovery_suite/open_problems/dense_cluster.sh                 # MODE=all
#   MODE=map sbatch --array=0-15 discovery_suite/open_problems/dense_cluster.sh
#   MODE=reduce sbatch discovery_suite/open_problems/dense_cluster.sh
#
#SBATCH --job-name=open_dense
#SBATCH --output=logs/%x_%A_%a.out
#SBATCH --error=logs/%x_%A_%a.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=04:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=4

set -euo pipefail

VECS="${VECS:?set VECS to the vector-store root built by encode_cluster.sh}"
MODEL="${MODEL:-qwen3-0.6b}"
VIEW="${VIEW:-node}"
CANON="${CANON:-raw}"
TOPK="${TOPK:-50}"
ALPHA="${ALPHA:-0.7}"
MODE="${MODE:-all}"
PARTIALS="${PARTIALS:-$VECS/partials_${MODEL}_${VIEW}_${CANON}}"
OUT="${OUT:-discovery_suite/open_problems/runs/open_dense_${MODEL}_${VIEW}_${CANON}.csv}"

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

# Model weights on lab storage. NOT a silent fallback to $HOME: the home quota is
# ~5GB and HuggingFace will fill it and then fail mid-array with ENOSPC, which is
# exactly what happened on the first 100k encode run.
export HF_HOME="${HF_HOME:-/sci/labs/orzuk/$USER/hf_cache}"
if ! mkdir -p "$HF_HOME" 2>/dev/null; then
    echo "ERROR: cannot create HF_HOME=$HF_HOME" >&2
    echo "       Refusing to fall back to \$HOME (quota ~5GB). Set HF_HOME to a" >&2
    echo "       writable lab path and resubmit." >&2
    exit 4
fi
echo "[env] HF_HOME: $HF_HOME"

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

echo "[dense] mode=$MODE model=$MODEL view=$VIEW canon=$CANON top_k=$TOPK"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

COMMON=(--vectors "$VECS" --model "$MODEL" --view "$VIEW" --canon "$CANON"
        --top-k "$TOPK" --alpha "$ALPHA" --status-dir "$VECS/status")

case "$MODE" in
  all)
    python3 discovery_suite/open_problems/o1b_dense_sweep.py all \
        "${COMMON[@]}" --out "$OUT"
    ;;
  map)
    # --shard-id defaults to $SLURM_ARRAY_TASK_ID; stride makes task k take
    # shards k, k+N, k+2N, … so the array tiles the shard range exactly.
    python3 discovery_suite/open_problems/o1b_dense_sweep.py map \
        "${COMMON[@]}" --partials "$PARTIALS" \
        --shard-stride "${SLURM_ARRAY_TASK_COUNT:-1}"
    ;;
  reduce)
    python3 discovery_suite/open_problems/o1b_dense_sweep.py reduce \
        "${COMMON[@]}" --partials "$PARTIALS" --out "$OUT"
    ;;
  *)
    echo "MODE must be all | map | reduce" >&2; exit 2 ;;
esac

echo "[dense] done"
echo "[next] fuse with the lexical sweep, then triage:"
echo "  python3 discovery_suite/open_problems/o1c_fuse.py \\"
echo "      --lexical discovery_suite/open_problems/runs/open_sweep_100k_raw.csv \\"
echo "      --dense $OUT --out discovery_suite/open_problems/runs/open_fused.csv"
