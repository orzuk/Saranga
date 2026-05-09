#!/usr/bin/env python3
"""Render <input>.html for every JSON in a directory or glob, skipping
papers that already have an .html sibling and catching errors per-paper
so one bad paper doesn't kill the whole run.

Imports visualize_annotation once so the foundation index loads only once.

Usage:
    python3 scripts/render_html_robust.py <dir-or-glob> [<dir-or-glob>...]

Examples:
    python3 scripts/render_html_robust.py /mnt/c/Datasets/Saranga_data/tier2/
    python3 scripts/render_html_robust.py '/mnt/c/Datasets/Saranga_data/tier3/math_CO/json/*.json'
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

# Load the visualizer module (foundation index loads once at module-level).
import visualize_annotation as viz  # noqa: E402


def _resolve(args):
    files = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            files.extend(sorted(p.glob("*.json")))
        elif "*" in arg or "?" in arg:
            import glob
            files.extend(sorted(Path(p) for p in glob.glob(arg)))
        else:
            files.append(p)
    # Filter out non-paper JSONs (anomalies, manifests, etc.)
    out = []
    for f in files:
        if not f.is_file() or f.suffix != ".json":
            continue
        if f.name in {"anomalies_detail.json", "manifest.json"}:
            continue
        out.append(f)
    return out


def _render_one(input_path: Path) -> tuple[bool, str]:
    """Render input_path -> input_path.with_suffix('.html'). Return (ok, msg)."""
    html_path = input_path.with_suffix(".html")
    if html_path.exists():
        return True, "skipped (already exists)"
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data = viz._normalize_schema(data, source_path=input_path)
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        if not nodes:
            return False, "no nodes"
        metadata = data.get("metadata", {})
        # Generate the SVG used by the HTML viewer (no PNG file)
        svg_only_path = str(input_path.with_suffix(".png")).replace(".png", "_nolegend.svg")
        viz.draw_dag(nodes, edges,
                     svg_only_path.replace(".svg", ".png"),
                     metadata=metadata,
                     resolution="standard",
                     show_legend=False,
                     show_foundation=True,
                     foundation_path=None,
                     show_extras=True)
        n = viz.generate_interactive_html(data, svg_only_path, str(html_path))
        # Clean up scratch files
        for tmp in [svg_only_path, svg_only_path.replace(".svg", ".png")]:
            if os.path.exists(tmp):
                os.remove(tmp)
        return True, f"{n} nodes"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    files = _resolve(sys.argv[1:])
    if not files:
        print("no JSON files found")
        sys.exit(1)

    print(f"rendering {len(files)} files")
    t0 = time.time()
    n_ok = n_skip = n_fail = 0
    failures = []
    for i, f in enumerate(files, 1):
        ok, msg = _render_one(f)
        if not ok:
            n_fail += 1
            failures.append((f.name, msg))
            status = "FAIL"
        elif "skipped" in msg:
            n_skip += 1
            status = "skip"
        else:
            n_ok += 1
            status = "ok  "
        elapsed = time.time() - t0
        eta = elapsed / i * (len(files) - i)
        print(f"[{i:3d}/{len(files)}] {status}  {f.name:30s}  {msg:40s}  "
              f"({elapsed:.0f}s elapsed, {eta:.0f}s eta)", flush=True)

    print(f"\nDone: {n_ok} rendered, {n_skip} skipped, {n_fail} failed")
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for name, msg in failures:
            print(f"  {name}: {msg}")


if __name__ == "__main__":
    main()
