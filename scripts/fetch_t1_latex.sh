#!/bin/bash
# Download arXiv .tex source for a list of papers and unpack into per-paper
# subdirectories suitable for run_pipeline.py --tex-dir consumption.
#
# Output layout:
#   $OUT_BASE/<arxiv_id>/source/*.tex
#
# Usage:
#   ./fetch_t1_latex.sh [OUT_BASE [arxiv_id ...]]
#
# With no extra args, defaults to the 10 T1 papers.
# With explicit IDs, fetches those instead — e.g.:
#   ./fetch_t1_latex.sh /mnt/c/Datasets/Saranga_data/tier3/math_CO/tex \
#       1001.4268v1 1001.2078v1 1001.3528v1
#
# After this runs, scripts/bootstrap_t1_cis.py picks up the LaTeX via
# --t3-tex-base $OUT_BASE.
set -euo pipefail

OUT_BASE="${1:-/tmp/t1_latex}"
shift || true
mkdir -p "$OUT_BASE"

if [ "$#" -gt 0 ]; then
    PAPER_IDS=("$@")
else
    PAPER_IDS=(
      "1204.0109"
      "1210.4634"
      "1405.2464"
      "1512.09272"
      "2208.03112"
      "2309.05826"
      "2312.16785"
      "2401.00367"
      "2505.12804"
      "2603.09769"
    )
fi

for AID in "${PAPER_IDS[@]}"; do
    PAPER_DIR="$OUT_BASE/$AID"
    SRC_DIR="$PAPER_DIR/source"
    if [ -d "$SRC_DIR" ] && ls "$SRC_DIR"/*.tex >/dev/null 2>&1; then
        echo "  [skip] $AID already has tex source"
        continue
    fi
    mkdir -p "$SRC_DIR"
    echo "  [fetch] $AID"
    URL="https://arxiv.org/e-print/${AID}"
    TARBALL="$PAPER_DIR/source.tar.gz"
    # arXiv e-print is usually .tar.gz
    if curl -sL --max-time 60 -o "$TARBALL" "$URL"; then
        # Detect format and extract
        if file "$TARBALL" | grep -q gzip; then
            tar -xzf "$TARBALL" -C "$SRC_DIR" 2>/dev/null || \
              gunzip -c "$TARBALL" > "$SRC_DIR/${AID}.tex"
        elif file "$TARBALL" | grep -q "TeX document"; then
            mv "$TARBALL" "$SRC_DIR/${AID}.tex"
        else
            # Try as tar
            tar -xf "$TARBALL" -C "$SRC_DIR" 2>/dev/null || \
              echo "    [warn] could not unpack $AID"
        fi
        rm -f "$TARBALL"
    else
        echo "    [fail] curl failed for $AID"
    fi
done

echo ""
echo "Done. Per-paper LaTeX under $OUT_BASE/<arxiv_id>/source/"
echo "Now run:"
echo "  python3 scripts/bootstrap_t1_cis.py --t3-tex-base $OUT_BASE"
