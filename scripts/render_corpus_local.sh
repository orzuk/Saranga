#!/bin/bash
# Render HTMLs locally for every JSON in <BASE_DIR>/<category>/json/ that
# doesn't yet have a corresponding <category>/html/<paper>.html.
#
# Designed for use on the local machine after copying parsed_100k category
# subdirs from the cluster: each <category>/json/<paper>.json gets a
# matching <category>/html/<paper>.html via visualize_annotation.py.
#
# Skips JSONs whose HTML already exists, so you can rerun after dropping
# more JSONs into a category and only the new ones get rendered.
#
# Usage:
#     bash scripts/render_corpus_local.sh [BASE_DIR] [VIZ_SCRIPT]
#
# Defaults:
#     BASE_DIR    = /mnt/g/My Drive/Research/Automath/parsed_100k
#     VIZ_SCRIPT  = /mnt/c/Code/Github/Authomathics/src/visualize_annotation.py
#
# Layout produced:
#     <BASE_DIR>/<category>/json/<paper>.json   (source, untouched)
#     <BASE_DIR>/<category>/html/<paper>.html   (rendered output)
set -euo pipefail

BASE_DIR="${1:-/mnt/g/My Drive/Research/Automath/parsed_100k}"
VIZ_SCRIPT="${2:-/mnt/c/Code/Github/Authomathics/src/visualize_annotation.py}"

if [ ! -d "$BASE_DIR" ]; then
    echo "ERROR: BASE_DIR not found: $BASE_DIR"
    exit 1
fi
if [ ! -f "$VIZ_SCRIPT" ]; then
    echo "ERROR: VIZ_SCRIPT not found: $VIZ_SCRIPT"
    exit 1
fi

n_total=0; n_rendered=0; n_skipped=0; n_failed=0
RENDER_LOG=$(mktemp /tmp/render_corpus.XXXXXX.log)

# Walk every <category>/json/ directory under BASE_DIR (one level deep).
for cat_dir in "$BASE_DIR"/*/; do
    cat=$(basename "$cat_dir")
    json_dir="$cat_dir/json"
    html_dir="$cat_dir/html"
    [ -d "$json_dir" ] || continue
    mkdir -p "$html_dir"

    cat_total=0; cat_rendered=0; cat_skipped=0; cat_failed=0
    echo "=== $cat ==="

    shopt -s nullglob
    for j in "$json_dir"/*.json; do
        cat_total=$((cat_total + 1))
        n_total=$((n_total + 1))
        name=$(basename "$j" .json)
        html_target="$html_dir/$name.html"

        if [ -f "$html_target" ]; then
            cat_skipped=$((cat_skipped + 1))
            n_skipped=$((n_skipped + 1))
            continue
        fi

        # visualize_annotation.py writes <input>.html alongside <input>.json,
        # so we run it on the json/ file then move the result into html/.
        if python3 "$VIZ_SCRIPT" "$j" --html-only > "$RENDER_LOG" 2>&1; then
            src_html="$json_dir/$name.html"
            if [ -f "$src_html" ]; then
                mv "$src_html" "$html_target"
                cat_rendered=$((cat_rendered + 1))
                n_rendered=$((n_rendered + 1))
                if [ $((cat_rendered % 5)) -eq 0 ]; then
                    echo "  $cat: rendered $cat_rendered / $cat_total (this run: skipped $cat_skipped, failed $cat_failed)"
                fi
            else
                cat_failed=$((cat_failed + 1))
                n_failed=$((n_failed + 1))
                echo "  FAIL $name (renderer succeeded but no HTML produced)"
            fi
        else
            cat_failed=$((cat_failed + 1))
            n_failed=$((n_failed + 1))
            tail -3 "$RENDER_LOG" | sed "s|^|    |"
            echo "  FAIL $name (renderer error; see $RENDER_LOG)"
        fi
    done
    shopt -u nullglob
    echo "  $cat done: $cat_rendered rendered, $cat_skipped already had HTML, $cat_failed failed"
done

echo ""
echo "=== Summary ==="
echo "  total JSONs scanned:  $n_total"
echo "  HTML already existed: $n_skipped"
echo "  newly rendered:       $n_rendered"
echo "  failed:               $n_failed"
echo "  log: $RENDER_LOG"
