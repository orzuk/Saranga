#!/bin/bash
# Run the T3-vs-T2 evaluation on the 152 LaTeX-source T2 papers.
#
# Steps:
#   1. Filter portal/data/tier2/ to papers without a 'source_note'
#      metadata field (those have proper .tex source, not PDF fallback).
#   2. Locate each paper's .tex source under alignment_benchmark/papers/
#      (or another location specified by TEX_BASE_DIR).
#   3. Run T3 (rule-based) extraction on those papers via run_pipeline.py.
#   4. Run scripts/eval_t3_vs_t2.py to compare T3 outputs against the
#      pre-existing T2 silver JSONs in portal/data/tier2/.
#
# Run this from the Authomathics repo root (the directory containing
# 'scripts/' and 'src/'), with the project venv activated.
#
# Usage:
#     bash scripts/run_t3_vs_t2_eval.sh [TEX_BASE_DIR] [WORK_DIR]
#
# Defaults:
#     TEX_BASE_DIR = /sci/labs/orzuk/orzuk/projects/Authomathics/alignment_benchmark/papers
#     WORK_DIR     = /tmp/t3_vs_t2_eval
#
# Output:
#     $WORK_DIR/t2_tex_subset.txt           — list of 152 TeX-source paper IDs
#     $WORK_DIR/t3_extractions/<paper_id>/  — fresh T3 extraction JSONs
#     $WORK_DIR/eval_results/summary.csv    — per-paper F1 summary
#     $WORK_DIR/eval_results/paper*_results.csv — per-paper detailed metrics
# Last lines of stdout give mean / median node-F1 + edge-F1.
set -euo pipefail

TEX_BASE_DIR="${1:-/sci/labs/orzuk/orzuk/projects/Authomathics/alignment_benchmark/papers}"
WORK_DIR="${2:-/tmp/t3_vs_t2_eval}"

mkdir -p "$WORK_DIR"
T2_LIST="$WORK_DIR/t2_tex_subset.txt"
T3_OUT="$WORK_DIR/t3_extractions"
EVAL_OUT="$WORK_DIR/eval_results"

echo "=== [1/4] Filtering T2 to TeX-source subset ==="
python3 - <<PY > "$T2_LIST"
import json, glob, os
for f in sorted(glob.glob('portal/data/tier2/paper*.json')):
    d = json.load(open(f))
    md = d.get('metadata') or {}
    if 'source_note' in md:
        continue
    pid = os.path.basename(f).replace('.json', '')
    aid = md.get('arxiv_id') or md.get('arxiv') or ''
    title = (md.get('title') or '').replace('\t', ' ')[:60]
    print(f'{pid}\t{aid}\t{title}')
PY
n_subset=$(wc -l < "$T2_LIST")
echo "  -> $T2_LIST  ($n_subset papers)"

echo ""
echo "=== [2/4] Verifying TeX source dir layout ==="
echo "  TEX_BASE_DIR = $TEX_BASE_DIR"
if [ ! -d "$TEX_BASE_DIR" ]; then
    echo "ERROR: $TEX_BASE_DIR does not exist."
    echo "  Pass an alternate dir as the first argument:"
    echo "    bash scripts/run_t3_vs_t2_eval.sh <CORRECT_PATH>"
    exit 2
fi
sample_pid=$(head -n1 "$T2_LIST" | cut -f1)
sample_dir="$TEX_BASE_DIR/$sample_pid"
echo "  sample paper dir: $sample_dir"
if [ ! -d "$sample_dir" ]; then
    echo "WARN: $sample_dir not found. Listing TEX_BASE_DIR top-level:"
    ls "$TEX_BASE_DIR" | head -10
    echo ""
    echo "  Edit this script's --in-dir loop below if the layout differs."
fi

echo ""
echo "=== [3/4] Running T3 (rule-based) extraction on each TeX-source paper ==="
mkdir -p "$T3_OUT"
n_extracted=0
n_skipped=0
while IFS=$'\t' read -r pid aid title; do
    tex_dir="$TEX_BASE_DIR/$pid"
    if [ ! -d "$tex_dir" ]; then
        echo "  skip $pid (no tex dir at $tex_dir)"
        n_skipped=$((n_skipped + 1))
        continue
    fi
    out_dir="$T3_OUT/$pid"
    if [ -f "$out_dir/parse_summary.json" ]; then
        # already extracted in a previous run, skip
        n_extracted=$((n_extracted + 1))
        continue
    fi
    mkdir -p "$out_dir"
    python3 src/run_pipeline.py \
        --operations parse,validate \
        --extractor regex \
        --in-dir "$tex_dir" \
        --out-dir "$out_dir" \
        > "$out_dir/run.log" 2>&1 || {
            echo "  FAIL $pid (see $out_dir/run.log)"
            n_skipped=$((n_skipped + 1))
            continue
        }
    n_extracted=$((n_extracted + 1))
    if [ $((n_extracted % 25)) -eq 0 ]; then
        echo "  extracted $n_extracted so far..."
    fi
done < "$T2_LIST"
echo "  -> extracted $n_extracted, skipped $n_skipped"

echo ""
echo "=== [4/4] Running T3-vs-T2 eval ==="
python3 scripts/eval_t3_vs_t2.py \
    --t2-dir portal/data/tier2 \
    --t3-dir "$T3_OUT" \
    --out "$EVAL_OUT"

echo ""
echo "=== Done ==="
echo "  per-paper detail: $EVAL_OUT/paper*_results.csv"
echo "  aggregate summary: $EVAL_OUT/summary.csv"
echo ""
echo "Send the mean node_f1 / edge_f1 numbers from stdout above back to Or."
