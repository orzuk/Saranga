#!/bin/bash
# Evaluate T2 (Opus silver) against T1 (manual gold) using the SAME pipeline
# as the T3-vs-T1 script: src/evaluate_extraction.py with strict greedy
# Jaccard at threshold TAU (default 0.5) and --exclude-origin external.
#
# Sanity-check intent: if this reproduces the headline T2-vs-T1 mean F1 ~0.92
# we know the pipeline is fine and the low T3-vs-T2 number reflects style
# mismatch; if this also collapses to <0.1, the pipeline is the problem.
#
# Pairs each T1 paper to a T2 paper by arxiv_id from metadata.
#
# Usage:
#     bash scripts/run_t2_vs_t1_eval.sh [WORK_DIR]
#
# Defaults:
#     WORK_DIR = /tmp/t2_vs_t1_eval
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

T1_DIR="portal/data/tier1"
T2_DIR="portal/data/tier2"
WORK_DIR="${1:-/tmp/t2_vs_t1_eval}"
EVAL_OUT="$WORK_DIR/eval_results"
mkdir -p "$EVAL_OUT"

EVAL="src/evaluate_extraction.py"
TAU=${TAU:-0.5}          # node-match Jaccard threshold: TAU=0.7 ./this_script.sh
OVERLAP="$WORK_DIR/overlap.tsv"

echo "=== [1/2] Finding T1<->T2 overlap by arxiv_id ==="
python3 - "$T1_DIR" "$T2_DIR" > "$OVERLAP" <<'PY'
import json, os, glob, sys
t1_dir, t2_dir = sys.argv[1], sys.argv[2]
def aid_of(d):
    md = d.get('metadata') or {}
    return md.get('arxiv_id') or md.get('arxiv') or md.get('paper_id') or ''
t1 = {}
for f in sorted(glob.glob(os.path.join(t1_dir, 'paper*.json'))):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    aid = aid_of(d).strip()
    pid = os.path.basename(f).replace('.json', '')
    if aid:
        t1[aid] = pid
for f in sorted(glob.glob(os.path.join(t2_dir, 'paper*.json'))):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    aid = aid_of(d).strip()
    if aid in t1:
        pid_t2 = os.path.basename(f).replace('.json', '')
        print(f'{t1[aid]}\t{pid_t2}\t{aid}')
PY
n_overlap=$(wc -l < "$OVERLAP")
echo "  -> $n_overlap T1<->T2 paper pairs"
if [ "$n_overlap" -eq 0 ]; then
    echo "ERROR: No T1<->T2 overlap by arxiv_id."
    echo "  Inspect metadata fields:"
    head -1 "$T1_DIR"/paper001.json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('metadata'))" 2>/dev/null || true
    exit 2
fi

echo ""
echo "=== [2/2] Running evaluations ==="
n_evaluated=0; n_skipped=0
while IFS=$'\t' read -r pid_t1 pid_t2 aid; do
    t1_path="$T1_DIR/$pid_t1.json"
    t2_path="$T2_DIR/$pid_t2.json"
    out_csv="$EVAL_OUT/${pid_t1}_results.csv"
    python3 "$EVAL" \
        --extracted "$t2_path" \
        --gold "$t1_path" \
        --csv "$out_csv" \
        --exclude-origin external \
        --node-sim-threshold "$TAU" \
        > "$EVAL_OUT/${pid_t1}.log" 2>&1 || {
            echo "  FAIL $pid_t1 / $pid_t2 (see ${pid_t1}.log)"
            n_skipped=$((n_skipped + 1))
            continue
        }
    n_evaluated=$((n_evaluated + 1))
done < "$OVERLAP"
echo "  -> evaluated $n_evaluated, skipped $n_skipped"

echo ""
echo "=== Aggregate ==="
EVAL_OUT="$EVAL_OUT" python3 - <<'PY'
import csv, glob, os
from collections import defaultdict
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
