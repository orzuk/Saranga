#!/bin/bash
#
# Build the Python environment the semantic-retrieval pipeline needs.
#
# RUN THIS ON THE LOGIN NODE — it needs internet. Compute nodes usually have
# none, which is why a missing package only ever surfaces as a dead job.
#
#   cd /path/to/Authomathics
#   bash discovery_suite/setup_env.sh
#
# By default it installs into the venv you already have active — the problem is
# simply that torch was never installed, and a second environment is not needed
# to fix that. Set VENV_DIR to build a separate one instead, which is only worth
# doing if you want to keep a ~2.5GB CUDA torch build out of an environment
# whose dependency set you would rather not perturb.
#
# Options (env vars):
#   VENV_DIR     target venv  (default: the active $VIRTUAL_ENV, else ./venv_embed)
#   TORCH_INDEX  PyTorch wheel channel         (default CUDA 12.4)
#                cpu    https://download.pytorch.org/whl/cpu
#                cu124  https://download.pytorch.org/whl/cu124   <- default here
#                cu126  https://download.pytorch.org/whl/cu126
#                cu128  https://download.pytorch.org/whl/cu128
#                Driver 580.95 on this cluster supports all of them; older
#                channels such as cu121 no longer carry recent torch releases.
#   PYTHON       interpreter to build from     (default python3)

set -euo pipefail

VENV_DIR="${VENV_DIR:-${VIRTUAL_ENV:-$PWD/venv_embed}}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu124}"
PYTHON="${PYTHON:-python3}"

echo "[setup] interpreter : $($PYTHON -V 2>&1)  ($(command -v $PYTHON))"
echo "[setup] venv        : $VENV_DIR"
echo "[setup] torch wheels: $TORCH_INDEX"
echo

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON" -m venv "$VENV_DIR"
    echo "[setup] created $VENV_DIR"
else
    echo "[setup] using the existing venv (installing into it, not replacing it)"
fi
# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"

# Scratch and cache on LAB DISK. pip unpacks wheels in $TMPDIR, which defaults
# to /tmp — usually a RAM-backed tmpfs on a login node. Extracting the 664MB
# cuDNN wheel there gets the process SIGKILLed (exit 137, "Killed", no useful
# message). The home quota is only 5GB, so that is no good either. Same fix
# scripts/launch_qwen_judge_server.sh already applies for vLLM's caches.
export TMPDIR="${TMPDIR:-/sci/labs/orzuk/$USER/tmp_install}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/sci/labs/orzuk/$USER/pip-cache}"
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR"
echo "[setup] TMPDIR      : $TMPDIR"
echo "[setup] pip cache   : $PIP_CACHE_DIR"

pip install --quiet --upgrade pip wheel

# torch FIRST, from the CUDA channel. sentence-transformers depends on torch and
# would otherwise pull the default PyPI build, which on many clusters is the
# CPU-only one — the job then runs happily and ~50x too slowly.
echo "[setup] installing torch (this is the big one, several minutes) …"
pip install --index-url "$TORCH_INDEX" torch

# torch must already be satisfied at this point, or pip resolves
# `sentence-transformers` -> `torch>=1.11` against PyPI and downloads a SECOND,
# non-CUDA torch on top of the one just installed.
python3 -c "import torch" 2>/dev/null || { echo "ERROR: torch did not install; not continuing" >&2; exit 1; }

echo "[setup] installing the rest …"
pip install "transformers>=4.40" "sentence-transformers>=3.0" numpy pandas

echo
echo "[setup] verifying …"
python3 - <<'PY'
import importlib, sys
ok = True
for mod in ("numpy", "pandas", "transformers", "sentence_transformers", "torch"):
    try:
        m = importlib.import_module(mod)
        print(f"  {mod:<22} {getattr(m, '__version__', '?')}")
    except ImportError as exc:
        ok = False
        print(f"  {mod:<22} MISSING ({exc})")
import torch
print(f"  torch.cuda.is_available  {torch.cuda.is_available()}")
if not torch.cuda.is_available():
    print("\n  NOTE: no GPU on the login node — this is EXPECTED here. What matters\n"
          "  is whether it reports True inside a GPU job; the cluster scripts print\n"
          "  it in their [env] banner. If it is False there too, this venv has a\n"
          "  CPU-only torch: re-run with TORCH_INDEX set to a cu* channel.")
sys.exit(0 if ok else 1)
PY

echo
echo "[setup] done. Warm the model cache now (also needs internet):"
echo "  export HF_HOME=/sci/labs/orzuk/\$USER/hf_cache"
echo "  export PYTHONPATH=\$PWD/discovery_suite:\$PYTHONPATH"
echo "  python3 -m embed.models --check --models qwen3-0.6b --device cpu --probe-n 8"
echo
if [ "$VENV_DIR" = "${VIRTUAL_ENV:-}" ]; then
    echo "[setup] then submit — the scripts pick up the active venv automatically:"
    echo "  sbatch discovery_suite/open_problems/pilot_cluster.sh"
else
    echo "[setup] then submit, pointing at this venv:"
    echo "  VENV=$VENV_DIR sbatch discovery_suite/open_problems/pilot_cluster.sh"
fi
