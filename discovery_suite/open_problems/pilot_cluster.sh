#!/bin/bash -l
#
# TIMED PILOT — run the whole pipeline on a small slice and print how long each
# stage took, so the full-corpus estimates stop being arithmetic and become
# measurements. Answers "what do we get, and how long will the real thing take?"
# in one job.
#
#   mkdir -p logs
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   export RUN=$PWD/discovery_suite/open_problems/runs/pilot
#   sbatch discovery_suite/open_problems/pilot_cluster.sh
#
# PAPERS=2000 by default: big enough for the per-node rates to be stable, small
# enough to finish inside an hour. Every stage prints its own elapsed time and
# the script ends with a table extrapolating each to the full 100k corpus.
#
#SBATCH --job-name=open_pilot
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=04:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8

set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed corpus dir}"
RUN="${RUN:-$PWD/discovery_suite/open_problems/runs/pilot}"
PAPERS="${PAPERS:-2000}"
MODEL="${MODEL:-qwen3-0.6b}"
VIEW="${VIEW:-node}"
CANON="${CANON:-raw}"
SHARDS="${SHARDS:-8}"
TOPK="${TOPK:-50}"
FULL_CORPUS="${FULL_CORPUS:-100000}"

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
mkdir -p "$RUN"

STORE="$RUN/textstore"
VECS="$RUN/vectors"
TIMING="$RUN/timing.txt"
: > "$TIMING"

# awk, not bc: bc is not guaranteed to be installed on a compute node and a
# missing binary here would kill the run after the expensive stage had finished.
stamp() {  # stamp <label> <seconds>
    awk -v l="$1" -v s="$2" -v p="$PAPERS" -v f="$FULL_CORPUS" \
        'BEGIN { printf "%-22s %8d s   (x%.1f -> %7.1f min for %d papers)\n",
                 l, s, f/p, s*f/p/60, f }' | tee -a "$TIMING"
}

# Every stage is resumable by design: finished shards carry a .done marker and
# are skipped. That is right for a production re-run and WRONG for a timing run —
# the stages would report seconds and the extrapolation would be meaningless.
if [ -d "$STORE" ] || [ -d "$VECS" ]; then
    echo "[pilot] WARNING: $RUN already has a text store / vector store."
    echo "         Finished shards will be SKIPPED, so the timings below will be"
    echo "         far too low. Use a fresh RUN=... for numbers you can trust,"
    echo "         or delete $STORE and $VECS first."
fi

echo "[pilot] root=$ROOT papers=$PAPERS model=$MODEL view=$VIEW canon=$CANON"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

echo; echo "=== 0. model availability + measured throughput ==="
python3 -m embed.models --check --models "$MODEL" --probe-n 512

echo; echo "=== 1. text store (CPU, parallel) ==="
t0=$SECONDS
python3 -m embed.textstore plan --root "$ROOT" --out "$STORE" --limit "$PAPERS"
python3 -m embed.textstore build --root "$ROOT" --out "$STORE" \
    --shards "$SHARDS" --status-dir "$STORE/status"
stamp "textstore" "$((SECONDS - t0))"

echo; echo "=== 2. encode (GPU) ==="
t0=$SECONDS
python3 -m embed.encode --store "$STORE" --out "$VECS" \
    --model "$MODEL" --view "$VIEW" --canon "$CANON" --status-dir "$VECS/status"
stamp "encode ($MODEL)" "$((SECONDS - t0))"

echo; echo "=== 3. dense retrieval (GPU) ==="
t0=$SECONDS
python3 discovery_suite/open_problems/o1b_dense_sweep.py all \
    --vectors "$VECS" --model "$MODEL" --view "$VIEW" --canon "$CANON" \
    --top-k "$TOPK" --out "$RUN/dense.csv"
stamp "dense retrieval" "$((SECONDS - t0))"

echo; echo "=== 4. triage (unchanged downstream tool) ==="
python3 discovery_suite/open_problems/triage_open.py \
    --in "$RUN/dense.csv" --out "$RUN/triage.csv" \
    --min-score 0.5 --per-problem 3 || true

echo; echo "=========================================================="
echo "TIMING SUMMARY  (pilot on $PAPERS papers, extrapolated to $FULL_CORPUS)"
echo "=========================================================="
cat "$TIMING"
echo
echo "NOTE: the textstore row scales with CPUS_PER_TASK and the encode row with"
echo "how many GPU array tasks you use — both stages are shard-parallel, so the"
echo "extrapolation above is the ONE-TASK cost. Divide by your array width."
echo
echo "outputs:  $RUN/dense.csv   $RUN/triage.csv   $TIMING"
