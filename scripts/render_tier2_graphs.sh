#!/bin/bash
# Regenerate HTML + PNG knowledge-graph visualizations for every T2 silver
# paper in portal/data/tier2/. Skips papers whose existing
# portal/graphs/tier2/<id>.{html,png} are both newer than the source JSON.
#
# Outputs:
#   portal/graphs/tier2/<paper_id>.html  (interactive viewer, used by paper.html iframe)
#   portal/graphs/tier2/<paper_id>.png   (static PNG, same render as the paper figures)
#
# Usage:
#   bash scripts/render_tier2_graphs.sh           # incremental (skips up-to-date)
#   bash scripts/render_tier2_graphs.sh --force   # regenerate everything
#
# Run from the Authomathics repo root.
set -euo pipefail

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
    FORCE=1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

JSON_DIR="portal/data/tier2"
OUT_DIR="portal/graphs/tier2"
WORK_DIR="/tmp/t2_render"
VIZ_SCRIPT="src/visualize_annotation.py"

mkdir -p "$OUT_DIR" "$WORK_DIR"

n_total=0
n_skipped=0
n_rendered=0
n_failed=0
failed_ids=()

for json_path in "$JSON_DIR"/paper*.json; do
    n_total=$((n_total + 1))
    pid=$(basename "$json_path" .json)
    html_path="$OUT_DIR/$pid.html"
    png_path="$OUT_DIR/$pid.png"

    if [[ $FORCE -eq 0 && -f "$html_path" && -f "$png_path" ]]; then
        json_mtime=$(stat -c %Y "$json_path")
        html_mtime=$(stat -c %Y "$html_path")
        png_mtime=$(stat -c %Y "$png_path")
        if [[ $html_mtime -ge $json_mtime && $png_mtime -ge $json_mtime ]]; then
            n_skipped=$((n_skipped + 1))
            continue
        fi
    fi

    work_subdir="$WORK_DIR/$pid"
    rm -rf "$work_subdir"
    mkdir -p "$work_subdir"
    cp "$json_path" "$work_subdir/$pid.json"

    if (cd src && python3 visualize_annotation.py "$work_subdir/$pid.json" --html) \
        > "$work_subdir/run.log" 2>&1; then
        cp "$work_subdir/$pid.html" "$html_path"
        cp "$work_subdir/$pid.png" "$png_path"
        n_rendered=$((n_rendered + 1))
        if [[ $((n_rendered % 10)) -eq 0 ]]; then
            echo "  rendered $n_rendered (skipped $n_skipped, failed $n_failed) ..."
        fi
    else
        echo "  FAIL $pid (see $work_subdir/run.log)"
        n_failed=$((n_failed + 1))
        failed_ids+=("$pid")
    fi
done

echo ""
echo "=== Summary ==="
echo "  total:    $n_total"
echo "  skipped:  $n_skipped (already up-to-date)"
echo "  rendered: $n_rendered"
echo "  failed:   $n_failed"
if [[ $n_failed -gt 0 ]]; then
    echo "  failed ids: ${failed_ids[*]}"
fi
