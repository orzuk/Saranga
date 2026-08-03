#!/bin/bash -l
#
# Tier-A benchmark on a GPU node: which (model x view x canonicalization) arm
# actually finds resolutions?  This is step 1 of the plan and it belongs HERE,
# not on a laptop — MiniLM is the only model in the roster that runs on CPU, and
# it is the one whose 256-token window made the context arms untestable.
#
# Self-contained: it plants its own ground truth in memory and encodes on the
# fly, so it needs NO text store and NO vector store. Run it before committing
# GPU time to a full corpus pass.
#
#   mkdir -p logs                     # sbatch cannot create its own log dir
#   export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
#   export OUT=$PWD/discovery_suite/open_problems/runs/bench_cluster.csv
#   sbatch discovery_suite/open_problems/bench_cluster.sh
#
# With LLM=haiku the L2+ obfuscation becomes real paraphrase instead of synonym
# swapping — without it the lexical baseline scores near-perfectly at every
# level and the comparison is meaningless. Needs ANTHROPIC_API_KEY; responses
# are sqlite-cached so a re-run is free.
#
#SBATCH --job-name=open_bench
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#SBATCH --partition=salmon
#SBATCH --gres=gpu:l40s:1
#SBATCH --time=06:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8

set -euo pipefail

ROOT="${ROOT:?set ROOT to the parsed corpus dir (parent of the category dirs)}"
PAPERS="${PAPERS:-2000}"
TWINS="${TWINS:-200}"
MODELS="${MODELS:-minilm,distilbert,specter2,bge-m3,qwen3-0.6b}"
VIEWS="${VIEWS:-node,ctx-concat,ctx-late,concepts-only}"
CANONS="${CANONS:-raw,canon}"
LEVELS="${LEVELS:-L0,L1,L2,L3}"
LLM="${LLM:-}"
TOPK="${TOPK:-50}"
OUT="${OUT:-discovery_suite/open_problems/runs/bench_cluster.csv}"
JUDGED="${JUDGED:-discovery_suite/open_problems/runs/o4_verdicts_all.csv}"

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
mkdir -p "$(dirname "$OUT")"

# Model weights on lab storage, not a home quota, and under OUR OWN user dir --
# a shared path under another user is usually not writable, and with `set -e` a
# failed mkdir would kill the job before anything ran. Override HF_HOME to point
# at a genuinely shared cache once one exists.
export HF_HOME="${HF_HOME:-/sci/labs/orzuk/$USER/hf_cache}"
if ! mkdir -p "$HF_HOME" 2>/dev/null; then
    echo "[warn] cannot write $HF_HOME - falling back to the default HF cache" >&2
    unset HF_HOME
fi

echo "[bench] root=$ROOT papers=$PAPERS twins=$TWINS"
echo "[bench] models=$MODELS"
echo "[bench] views=$VIEWS canons=$CANONS levels=$LEVELS llm=${LLM:-<rule-based>}"
echo "[bench] HF_HOME=$HF_HOME"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

# Fail fast, and record the per-model throughput this GPU actually achieves —
# that rate is what every later time estimate is built on.
echo "[bench] --- model availability + measured throughput ---"
python3 -m embed.models --check --models "$MODELS" --probe-n 512

echo "[bench] --- benchmark ---"
python3 discovery_suite/open_problems/bench_retrieval.py \
    --root "$ROOT" --papers "$PAPERS" --twins "$TWINS" \
    --models "$MODELS" --views "$VIEWS" --canons "$CANONS" \
    --levels "$LEVELS" --top-k "$TOPK" \
    ${LLM:+--llm "$LLM"} \
    ${JUDGED:+--judged "$JUDGED"} \
    --out "$OUT"

echo "[bench] done -> $OUT  (and ${OUT%.csv}.md)"
echo "[next] take the top 1-2 arms into the full corpus run:"
echo "  MODELS=<winner> ARMS=<view:canon> bash discovery_suite/open_problems/embed_cluster.sh"
