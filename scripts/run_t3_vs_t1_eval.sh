#!/bin/bash
# Evaluate T3 (rule-based regex) against T1 (manual gold) using the SAME
# pipeline as run_t3_vs_t2_eval.sh: T3 extraction first, then
# src/evaluate_extraction.py (Jaccard threshold TAU, default 0.5) with --exclude-origin external.
#
# Sanity-check intent: should reproduce the headline T3-vs-T1 mean F1 ~0.83.
# If it does, the pipeline is fine and the low T3-vs-T2 number reflects
# style mismatch. If T3-vs-T1 also collapses, the pipeline itself is broken.
#
# For each T1 paper we (a) locate its LaTeX source under TEX_BASE_DIR,
# (b) run rule-based T3 extraction via run_pipeline.py, (c) run the
# evaluator vs T1 gold.
#
# Usage:
#     bash scripts/run_t3_vs_t1_eval.sh [TEX_BASE_DIR] [WORK_DIR] [SAMPLE_N]
#
# Defaults:
#     TEX_BASE_DIR = /sci/labs/orzuk/orzuk/projects/Authomathics/alignment_benchmark/papers
#     WORK_DIR     = /tmp/t3_vs_t1_eval
#     SAMPLE_N     = 0  (evaluate all T1 papers; pass an int N>0 to randomly sample N)
set -euo pipefail

TEX_BASE_DIR="${1:-/sci/labs/orzuk/orzuk/projects/Authomathics/alignment_benchmark/papers}"
WORK_DIR="${2:-/tmp/t3_vs_t1_eval}"
SAMPLE_N="${3:-0}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

T1_DIR="portal/data/tier1"
T3_OUT="$WORK_DIR/t3_extractions"
EVAL_OUT="$WORK_DIR/eval_results"
mkdir -p "$T3_OUT" "$EVAL_OUT"

EVAL="src/evaluate_extraction.py"
TAU=${TAU:-0.5}          # node-match Jaccard threshold: TAU=0.7 ./this_script.sh
PIPELINE="src/run_pipeline.py"

echo "=== [1/3] Listing T1 papers ==="
T1_LIST="$WORK_DIR/t1_list.txt"
ls "$T1_DIR"/paper*.json 2>/dev/null | xargs -n1 basename | sed 's/\.json$//' > "$T1_LIST"
n_t1=$(wc -l < "$T1_LIST")
echo "  -> $n_t1 T1 papers in $T1_DIR"

if [ "$SAMPLE_N" -gt 0 ] && [ "$SAMPLE_N" -lt "$n_t1" ]; then
    shuf -n "$SAMPLE_N" "$T1_LIST" > "$T1_LIST.sample"
    mv "$T1_LIST.sample" "$T1_LIST"
    echo "  -> sampled $SAMPLE_N papers"
fi

echo ""
echo "=== [2/3] Locating LaTeX source + running T3 extraction ==="
n_extracted=0; n_skipped=0
while read -r pid; do
    out_dir="$T3_OUT/$pid"
    if [ -f "$out_dir/parse_summary.json" ]; then
        n_extracted=$((n_extracted + 1))
        continue
    fi

    # Locate LaTeX. Try paperN/source/, then paperNNN/source/, etc.
    tex_dir=""
    for d in "$TEX_BASE_DIR/$pid/source" \
             "$TEX_BASE_DIR/$(echo "$pid" | sed 's/^paper0*/paper/')/source"; do
        if [ -d "$d" ]; then
            tex_dir="$d"; break
        fi
    done
    if [ -z "$tex_dir" ]; then
        echo "  skip $pid (no LaTeX source under $TEX_BASE_DIR)"
        n_skipped=$((n_skipped + 1))
        continue
    fi

    mkdir -p "$out_dir"
    python3 "$PIPELINE" \
        --operations parse,validate \
        --extract-mode regex \
        --tex-dir "$tex_dir" \
        --out-dir "$out_dir" \
        > "$out_dir/run.log" 2>&1 || {
            echo "  FAIL extract $pid (see $out_dir/run.log)"
            n_skipped=$((n_skipped + 1))
            continue
        }
    n_extracted=$((n_extracted + 1))
done < "$T1_LIST"
echo "  -> T3 extracted $n_extracted, skipped $n_skipped"

echo ""
echo "=== [3/3] Running evaluator T3 vs T1 ==="
n_evaluated=0; n_failed=0
while read -r pid; do
    t1_path="$T1_DIR/$pid.json"
    # T3 output filename varies; try common names.
    t3_json=""
    for f in "$T3_OUT/$pid"/*.json; do
        case "$f" in
            *parse_summary.json|*run.log) continue ;;
            *)
                if [ -f "$f" ]; then t3_json="$f"; break; fi
                ;;
        esac
    done
    if [ -z "$t3_json" ]; then
        # Fall back: look for the per-paper graph JSON directly
        t3_json=$(ls "$T3_OUT/$pid"/*.json 2>/dev/null | grep -v parse_summary | head -1 || true)
    fi
    if [ -z "$t3_json" ] || [ ! -f "$t3_json" ]; then
        echo "  skip $pid (no T3 JSON)"
        n_failed=$((n_failed + 1))
        continue
    fi

    out_csv="$EVAL_OUT/${pid}_results.csv"
    python3 "$EVAL" \
        --extracted "$t3_json" \
        --gold "$t1_path" \
        --csv "$out_csv" \
        --exclude-origin external \
        --node-sim-threshold "$TAU" \
        > "$EVAL_OUT/${pid}.log" 2>&1 || {
            echo "  FAIL eval $pid (see ${pid}.log)"
            n_failed=$((n_failed + 1))
            continue
        }
    n_evaluated=$((n_evaluated + 1))
done < "$T1_LIST"
echo "  -> evaluated $n_evaluated, failed $n_failed"

echo ""
echo "=== Aggregate ==="
EVAL_OUT="$EVAL_OUT" python3 - <<'PY'
import csv, glob, os
out = os.environ['EVAL_OUT']
rows = []
for f in sorted(glob.glob(out + '/*_results.csv')):
    pid = os.path.basename(f).replace('_results.csv', '')
    metrics = {}
    for r in csv.DictReader(open(f)):
        cat = (r.get('category') or '').strip()
        typ = (r.get('type') or '').strip()
        if cat == 'nodes' and typ == 'OVERALL':
            for k in ('precision', 'recall', 'f1'):
                try: metrics[f'node_{k}'] = float(r.get(k, '') or '0')
                except ValueError: pass
        elif cat == 'edges' and typ == 'OVERALL':
            for k in ('precision', 'recall', 'f1'):
                try: metrics[f'edge_{k}'] = float(r.get(k, '') or '0')
                except ValueError: pass
    rows.append((pid, metrics))

if not rows:
    print('No results.')
else:
    print(f'evaluated: {len(rows)} papers')
    for k in ('node_precision', 'node_recall', 'node_f1',
             'edge_precision', 'edge_recall', 'edge_f1'):
        vals = [m[k] for _, m in rows if k in m]
        if not vals: continue
        vals.sort()
        mean = sum(vals) / len(vals)
        med = vals[len(vals) // 2]
        print(f'  {k:18s}  mean={mean:.3f}  median={med:.3f}  n={len(vals)}')
PY
