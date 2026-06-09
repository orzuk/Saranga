#!/usr/bin/env python3
"""Paper distillation filmstrip
=================================
For one paper, render its graph at every distillation snapshot produced by
``silver_distillation_merged.py``:

  step_00_initial    -> no distilled rules (pure base parser)
  step_01_paper001   -> cumulative rules after paper001's distillation
  step_02_paper002   -> ... after paper002 (rules learned on OTHER papers too)
  ...

Each snapshot is installed (its self-contained importer symlinked into the
type dirs), the chosen paper is re-parsed with ``extraction_mode='rules'``, the
resulting graph is written as JSON, and an HTML is rendered with the same
renderer used for the portal graphs. The output is a flip-through set of HTMLs
showing how distillation reshapes this one paper's graph step by step.

Usage:
    python scripts/paper_filmstrip.py \
        --paper paper001 \
        --tex-dir /Users/yaronot/Datasets/Authomathics_data/alignment/papers \
        --eval-dir src/LLMVersion/merged_eval_silver_001_011 \
        --out-dir src/LLMVersion/merged_eval_silver_001_011/filmstrip_paper001
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import silver_distillation_sequential as seq
import silver_distillation_merged as merged
from silver_distillation_sequential import _find_main_tex


def parse_paper_graph(pid: str, tex_dir: Path, types, snap_dir: Path | None) -> dict:
    """Parse `pid` with `snap_dir`'s distilled rules installed; return graph dict.

    snap_dir=None parses with whatever is committed (no snapshot installed).
    A step_00 snapshot has empty groups, so installing it == no distilled rules.
    """
    from math_paper_parser import PaperParser

    backups = {}
    if snap_dir is not None:
        for t in types:
            _, b = seq._install_silver_rules(snap_dir, t)
            backups[t] = b
    try:
        main_tex = _find_main_tex(tex_dir / pid / "source")
        if main_tex is None:
            raise FileNotFoundError(f"no .tex for {pid} under {tex_dir/pid/'source'}")
        parser = PaperParser(paper_id=pid, extraction_mode='rules',
                             structure_types=list(types))
        graph = parser.parse_file(str(main_tex))
        # to_unified_dict() emits the renderer schema ({nodes, edges}); the
        # pipeline (parse_batch) uses it too. to_dict() is internal-only.
        if hasattr(graph, "to_unified_dict"):
            return graph.to_unified_dict()
        return graph.to_dict()
    finally:
        if snap_dir is not None:
            for t in types:
                seq._uninstall_silver_rules(t, backups.get(t))


def _render_html(json_path: Path) -> tuple[bool, str]:
    """Render json_path -> json_path.with_suffix('.html').

    Mirrors render_html_robust._render_one but drops the `show_extras` kwarg,
    which the committed visualize_annotation.draw_dag does not accept (the
    repo's render_html_robust targets the not-yet-committed viz port).
    """
    import os
    import visualize_annotation as viz
    html_path = json_path.with_suffix(".html")
    try:
        data = json.load(open(json_path, encoding="utf-8"))
        data = viz._normalize_schema(data, source_path=json_path)
        nodes = data.get("nodes", [])
        if not nodes:
            return False, "no nodes"
        metadata = data.get("metadata", {})
        svg_path = str(json_path.with_suffix(".png")).replace(".png", "_nolegend.svg")
        viz.draw_dag(nodes, data.get("edges", []),
                     svg_path.replace(".svg", ".png"),
                     metadata=metadata, resolution="standard",
                     show_legend=False, show_foundation=True, foundation_path=None)
        n = viz.generate_interactive_html(data, svg_path, str(html_path))
        for tmp in (svg_path, svg_path.replace(".svg", ".png")):
            if os.path.exists(tmp):
                os.remove(tmp)
        return True, f"{n} nodes"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _node_count(data: dict) -> int:
    for key in ("nodes", "objects"):
        v = data.get(key)
        if isinstance(v, dict):
            return len(v)
        if isinstance(v, list):
            return len(v)
    return 0


def main():
    p = argparse.ArgumentParser(description="Per-step graph filmstrip for one paper")
    p.add_argument("--paper", default="paper001")
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--out-dir", default=None,
                   help="Default: <eval-dir>/filmstrip_<paper>")
    p.add_argument("--no-render", action="store_true",
                   help="Only dump JSONs, skip HTML rendering")
    args = p.parse_args()

    tex_dir = Path(args.tex_dir).resolve()
    eval_dir = Path(args.eval_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else \
        eval_dir / f"filmstrip_{args.paper}"
    out_dir.mkdir(parents=True, exist_ok=True)

    types = list(merged.FNAME_MAP.keys())
    snaps = sorted((eval_dir / "snapshots").glob("step_*"))
    if not snaps:
        print(f"ERROR: no snapshots under {eval_dir/'snapshots'} "
              f"(run the distillation with snapshotting first)")
        sys.exit(1)

    print(f"Filmstrip for {args.paper}: {len(snaps)} step(s) -> {out_dir}")
    jsons = []
    for snap in snaps:
        data = parse_paper_graph(args.paper, tex_dir, types, snap)
        out_json = out_dir / f"{snap.name}.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        jsons.append(out_json)
        print(f"  {snap.name:<28} nodes={_node_count(data):>3}  -> {out_json.name}")

    if args.no_render:
        print("\n(--no-render) JSONs written; skipping HTML.")
        return

    # Render each JSON -> HTML (same draw_dag/interactive-HTML as the portal).
    print("\nRendering HTML ...")
    for j in jsons:
        ok, msg = _render_html(j)
        print(f"  {'ok ' if ok else 'ERR'} {j.with_suffix('.html').name}  {msg}")

    print(f"\nDone. Open the HTMLs in {out_dir} in step order.")


if __name__ == "__main__":
    main()
