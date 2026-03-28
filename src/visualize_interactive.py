#!/usr/bin/env python3
"""Generate an interactive HTML visualization of a knowledge graph.

Usage:
    python visualize_interactive.py annotation.json [output.html]

Produces a standalone HTML file with:
  - Layered DAG layout (dagre) with compound theorem boxes
  - Click theorem → expand proof steps + related equations
  - Click definition → highlight all theorems that use it
  - Hover → full statement tooltip
  - Toggle buttons: show equations, show proof steps, reset
  - Orphan/miscellaneous equations in a collapsible side panel
  - Zoom and pan support
"""
import json
import sys
from pathlib import Path
from html import escape


NODE_COLORS = {
    "definition":  {"bg": "#D5F5E3", "border": "#27AE60", "header": "#27AE60"},
    "theorem":     {"bg": "#FADBD8", "border": "#C0392B", "header": "#C0392B"},
    "lemma":       {"bg": "#FDEBD0", "border": "#E67E22", "header": "#E67E22"},
    "corollary":   {"bg": "#E8DAEF", "border": "#8E44AD", "header": "#8E44AD"},
    "proposition": {"bg": "#FADBD8", "border": "#C0392B", "header": "#C0392B"},
    "algorithm":   {"bg": "#FFF9C4", "border": "#D4AC0D", "header": "#D4AC0D"},
    "proof":       {"bg": "#D5D8DC", "border": "#566573", "header": "#566573"},
    "equation":    {"bg": "#D4E6F1", "border": "#5DADE2", "header": "#5DADE2"},
    "proof_step":  {"bg": "#E8E8E8", "border": "#839192", "header": "#839192"},
    "claim":       {"bg": "#F6DDCC", "border": "#BA4A00", "header": "#BA4A00"},
}
DEFAULT_COLOR = {"bg": "#EAECEE", "border": "#566573", "header": "#566573"}


def classify_nodes(nodes, edges):
    """Classify nodes into base (always shown), proof steps, equations, and orphans."""
    node_by_id = {n["id"]: n for n in nodes}

    # Find which nodes are targets/sources of edges
    has_edge = set()
    for e in edges:
        has_edge.add(e["source"])
        has_edge.add(e["target"])

    base_types = {"definition", "theorem", "lemma", "corollary", "proposition",
                  "algorithm", "proof", "claim"}

    base_nodes = []
    proof_steps = []
    equations = []
    orphan_equations = []

    for n in nodes:
        ntype = n.get("type", "")
        nid = n["id"]
        if ntype == "proof_step":
            proof_steps.append(n)
        elif ntype == "equation":
            if nid in has_edge:
                equations.append(n)
            else:
                orphan_equations.append(n)
        elif ntype in base_types:
            base_nodes.append(n)
        else:
            base_nodes.append(n)

    return base_nodes, proof_steps, equations, orphan_equations


def make_node_label_html(node):
    """Create HTML label for a node in the DAG."""
    ntype = node.get("type", "")
    colors = NODE_COLORS.get(ntype, DEFAULT_COLOR)
    nid = escape(node["id"])
    name = escape(node.get("name") or "")
    header = f"{nid}: {name}" if name else nid

    parts = [f'<div style="background:{colors["header"]};color:white;padding:4px 8px;'
             f'font-weight:bold;font-size:12px;border-radius:4px 4px 0 0;">{header}</div>']

    if ntype in ("theorem", "lemma", "corollary", "proposition"):
        # Assumptions
        assumptions = node.get("assumptions", [])
        if assumptions:
            parts.append('<div style="padding:3px 6px;font-size:10px;color:#555;font-weight:bold;">Assume:</div>')
            for a in assumptions[:4]:
                parts.append(f'<div style="padding:1px 6px 1px 12px;font-size:10px;font-style:italic;color:#333;">'
                             f'&bull; {escape(_short(a, 60))}</div>')
            if len(assumptions) > 4:
                parts.append(f'<div style="padding:1px 12px;font-size:9px;color:#888;">... +{len(assumptions)-4} more</div>')

        # Divider
        parts.append(f'<hr style="margin:2px 4px;border:none;border-top:1px solid {colors["border"]}40;">')

        # Conclusions
        conclusions = node.get("conclusions", [])
        if conclusions:
            parts.append('<div style="padding:3px 6px;font-size:10px;color:#555;font-weight:bold;">Conclude:</div>')
            for c in conclusions[:4]:
                parts.append(f'<div style="padding:1px 6px 1px 12px;font-size:10px;color:#333;">'
                             f'&bull; {escape(_short(c, 60))}</div>')

        # Proof strategy (if available from merged proof)
        proof_info = node.get("proof_info", [])
        if not proof_info and node.get("proof_strategy"):
            proof_info = [node["proof_strategy"]]
        if proof_info:
            parts.append(f'<hr style="margin:2px 4px;border:none;border-top:1px solid #ccc;">')
            for ps in proof_info:
                ps_text = ps if isinstance(ps, str) else str(ps)
                if ps_text:
                    parts.append(f'<div style="padding:2px 6px;font-size:9px;color:#666;font-style:italic;">'
                                 f'Proof: {escape(_short(ps_text, 50))}</div>')

    elif ntype == "algorithm" and (node.get("input") or node.get("output")):
        inputs = node.get("input", [])
        outputs = node.get("output", [])
        if inputs:
            parts.append('<div style="padding:3px 6px;font-size:10px;color:#555;font-weight:bold;">Input:</div>')
            for x in inputs:
                parts.append(f'<div style="padding:1px 12px;font-size:10px;">&bull; {escape(_short(x, 60))}</div>')
        if outputs:
            parts.append(f'<hr style="margin:2px 4px;border:none;border-top:1px solid {colors["border"]}40;">')
            parts.append('<div style="padding:3px 6px;font-size:10px;color:#555;font-weight:bold;">Output:</div>')
            for x in outputs:
                parts.append(f'<div style="padding:1px 12px;font-size:10px;">&bull; {escape(_short(x, 60))}</div>')
    else:
        stmt = node.get("statement", "")
        if stmt:
            parts.append(f'<div style="padding:4px 6px;font-size:10px;color:#333;">{escape(_short(stmt, 100))}</div>')

    return "".join(parts)


def _short(text, maxlen=80):
    if not text:
        return ""
    # Don't cut inside $...$
    if len(text) <= maxlen:
        return text
    cut = maxlen - 3
    if text[:cut].count("$") % 2 == 1:
        last = text.rfind("$", 0, cut)
        if last > 0:
            cut = last
    return text[:cut].rstrip() + "..."


def make_tooltip(node):
    """Full tooltip text for hover."""
    parts = [f"ID: {node['id']}"]
    parts.append(f"Type: {node.get('type', '?')}")
    if node.get("name"):
        parts.append(f"Name: {node['name']}")
    if node.get("section"):
        parts.append(f"Section: {node['section']}")
    if node.get("statement"):
        parts.append(f"Statement: {node['statement']}")
    if node.get("assumptions"):
        parts.append(f"Assumptions: {'; '.join(node['assumptions'])}")
    if node.get("conclusions"):
        parts.append(f"Conclusions: {'; '.join(node['conclusions'])}")
    if node.get("proof_strategy"):
        parts.append(f"Proof strategy: {node['proof_strategy']}")
    if node.get("proves"):
        parts.append(f"Proves: {node['proves']}")
    return "\\n".join(parts)


def merge_proofs_for_display(nodes, edges):
    """Collapse proof nodes into their parent theorem (for base view)."""
    node_by_id = {n["id"]: n for n in nodes}
    proof_map = {}
    for n in nodes:
        if n.get("type") == "proof" and n.get("proves"):
            target = n["proves"]
            if target in node_by_id:
                proof_map[n["id"]] = target

    display_nodes = []
    for n in nodes:
        if n["id"] in proof_map:
            parent_id = proof_map[n["id"]]
            parent = node_by_id[parent_id]
            if "proof_info" not in parent:
                parent["proof_info"] = []
            if n.get("proof_strategy"):
                parent["proof_info"].append(n["proof_strategy"])
            continue
        display_nodes.append(n)

    display_edges = []
    seen = set()
    for e in edges:
        s = proof_map.get(e["source"], e["source"])
        t = proof_map.get(e["target"], e["target"])
        if s == t:
            continue
        key = (s, t)
        if key not in seen:
            display_edges.append({"source": s, "target": t,
                                  "type": e.get("type", "uses"),
                                  "note": e.get("note", "")})
            seen.add(key)

    return display_nodes, display_edges, proof_map


def generate_html(data, output_path):
    """Generate the interactive HTML file."""
    all_nodes = data.get("nodes", [])
    all_edges = data.get("edges", [])
    metadata = data.get("metadata", {})

    # Classify nodes
    base_nodes_raw, proof_steps, equations, orphan_equations = classify_nodes(all_nodes, all_edges)

    # Merge proofs into theorems for base view
    base_nodes, base_edges, proof_map = merge_proofs_for_display(base_nodes_raw, all_edges)

    # Filter base edges to only reference base node IDs
    base_ids = {n["id"] for n in base_nodes}
    base_edges = [e for e in base_edges if e["source"] in base_ids and e["target"] in base_ids]

    # Build proof step chains per proof
    proof_step_chains = {}
    for ps in proof_steps:
        parent = ps.get("parent_proof", "")
        # Map parent proof to its theorem
        thm_id = proof_map.get(parent, parent)
        if thm_id not in proof_step_chains:
            proof_step_chains[thm_id] = []
        proof_step_chains[thm_id].append(ps)

    # Build equation associations
    eq_by_parent = {}
    for eq in equations:
        # Find which theorem/def this equation connects to via edges
        connected_to = set()
        for e in all_edges:
            if e["source"] == eq["id"] and e["target"] in base_ids:
                connected_to.add(e["target"])
            if e["target"] == eq["id"] and e["source"] in base_ids:
                connected_to.add(e["source"])
        for tid in connected_to:
            if tid not in eq_by_parent:
                eq_by_parent[tid] = []
            eq_by_parent[tid].append(eq)

    # Title
    ch = metadata.get("chapter", "")
    ch_title = metadata.get("chapter_title", "")
    title = f"Chapter {ch}: {ch_title}" if ch_title else "Knowledge Graph"

    # Build node data for JavaScript
    js_nodes = []
    for n in base_nodes:
        colors = NODE_COLORS.get(n.get("type", ""), DEFAULT_COLOR)
        label_html = make_node_label_html(n)
        tooltip = make_tooltip(n)
        has_steps = n["id"] in proof_step_chains
        has_eqs = n["id"] in eq_by_parent
        js_nodes.append({
            "id": n["id"],
            "label": label_html,
            "tooltip": tooltip,
            "type": n.get("type", ""),
            "bg": colors["bg"],
            "border": colors["border"],
            "hasSteps": has_steps,
            "hasEqs": has_eqs,
        })

    # Build proof step data
    js_proof_steps = {}
    for thm_id, steps in proof_step_chains.items():
        js_proof_steps[thm_id] = [{
            "id": s["id"],
            "statement": s.get("statement", ""),
            "parent_proof": s.get("parent_proof", ""),
        } for s in steps]

    # Build equation data
    js_equations = {}
    for parent_id, eqs in eq_by_parent.items():
        js_equations[parent_id] = [{
            "id": e["id"],
            "statement": e.get("statement", ""),
            "section": e.get("section", ""),
        } for e in eqs]

    # Orphan equations
    js_orphans = [{
        "id": e["id"],
        "statement": e.get("statement", ""),
        "section": e.get("section", ""),
    } for e in orphan_equations]

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(title)} — Knowledge Graph</title>
<style>
  body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 0; background: #fafafa; }}
  #header {{ background: #2c3e50; color: white; padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; }}
  #header h1 {{ margin: 0; font-size: 18px; }}
  #controls {{ display: flex; gap: 8px; }}
  #controls button {{ padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; background: #34495e; color: white; }}
  #controls button:hover {{ background: #4a6785; }}
  #controls button.active {{ background: #2980b9; }}
  #main {{ display: flex; height: calc(100vh - 48px); }}
  #graph-container {{ flex: 1; overflow: auto; position: relative; }}
  #graph-container svg {{ display: block; margin: 20px auto; }}
  .node rect {{ cursor: pointer; rx: 5; ry: 5; }}
  .node:hover rect {{ filter: brightness(0.95); }}
  .edgePath path {{ stroke: #7f8c8d; stroke-width: 1.5px; fill: none; }}
  .edgePath marker {{ fill: #7f8c8d; }}
  #detail-panel {{ width: 0; overflow-y: auto; background: white; border-left: 1px solid #ddd;
                   transition: width 0.3s; padding: 0; }}
  #detail-panel.open {{ width: 380px; padding: 16px; }}
  #detail-panel h3 {{ margin: 0 0 12px 0; color: #2c3e50; font-size: 15px; }}
  .detail-section {{ margin-bottom: 16px; }}
  .detail-section h4 {{ margin: 0 0 6px 0; color: #555; font-size: 12px; text-transform: uppercase; }}
  .step-chain {{ display: flex; flex-direction: column; gap: 4px; }}
  .step-item {{ background: #f0f0f0; border-left: 3px solid #839192; padding: 6px 10px; font-size: 11px; border-radius: 0 4px 4px 0; }}
  .step-arrow {{ text-align: center; color: #aaa; font-size: 14px; }}
  .eq-item {{ background: #d4e6f1; border-left: 3px solid #5dade2; padding: 6px 10px; font-size: 11px; border-radius: 0 4px 4px 0; margin-bottom: 4px; }}
  .orphan-item {{ background: #fef9e7; border-left: 3px solid #f39c12; padding: 6px 10px; font-size: 11px; border-radius: 0 4px 4px 0; margin-bottom: 4px; }}
  #orphan-panel {{ position: fixed; bottom: 16px; right: 16px; background: white; border: 1px solid #ddd;
                   border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); max-width: 350px; max-height: 400px;
                   overflow-y: auto; display: none; padding: 12px; z-index: 100; }}
  #orphan-toggle {{ position: fixed; bottom: 16px; right: 16px; background: #f39c12; color: white;
                    border: none; border-radius: 20px; padding: 8px 16px; cursor: pointer; font-size: 12px;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.2); z-index: 101; display: {'block' if js_orphans else 'none'}; }}
  .legend {{ display: flex; gap: 12px; flex-wrap: wrap; padding: 8px 24px; background: #f5f5f5; border-bottom: 1px solid #eee; }}
  .legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 11px; }}
  .legend-color {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid #999; }}
  .clickable-hint {{ font-size: 10px; color: #888; padding: 2px 6px; }}
</style>
</head>
<body>
<div id="header">
  <h1>{escape(title)} — Knowledge Graph</h1>
  <div id="controls">
    <button onclick="resetView()">Reset View</button>
    <button id="btn-steps" onclick="toggleAllSteps()">Show All Proof Steps</button>
  </div>
</div>
<div class="legend">
  <div class="legend-item"><div class="legend-color" style="background:#D5F5E3;border-color:#27AE60;"></div>Definition</div>
  <div class="legend-item"><div class="legend-color" style="background:#FADBD8;border-color:#C0392B;"></div>Theorem</div>
  <div class="legend-item"><div class="legend-color" style="background:#FDEBD0;border-color:#E67E22;"></div>Lemma</div>
  <div class="legend-item"><div class="legend-color" style="background:#E8DAEF;border-color:#8E44AD;"></div>Corollary</div>
  <div class="legend-item"><div class="legend-color" style="background:#FFF9C4;border-color:#D4AC0D;"></div>Algorithm</div>
  <div class="legend-item"><div class="legend-color" style="background:#D4E6F1;border-color:#5DADE2;"></div>Equation</div>
  <div class="legend-item" style="margin-left:20px;font-style:italic;color:#888;">Click a node for details. Hover for full statement.</div>
</div>
<div id="main">
  <div id="graph-container"></div>
  <div id="detail-panel"></div>
</div>
<button id="orphan-toggle" onclick="toggleOrphans()">{len(js_orphans)} orphan equation{'s' if len(js_orphans) != 1 else ''}</button>
<div id="orphan-panel">
  <h3>Unconnected Equations</h3>
  <div id="orphan-list"></div>
</div>

<script src="https://d3js.org/d3.v5.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dagre-d3@0.6.4/dist/dagre-d3.min.js"></script>
<script>
const NODES = {json.dumps(js_nodes)};
const EDGES = {json.dumps([dict(source=e["source"], target=e["target"], type=e.get("type","")) for e in base_edges])};
const PROOF_STEPS = {json.dumps(js_proof_steps)};
const EQUATIONS = {json.dumps(js_equations)};
const ORPHANS = {json.dumps(js_orphans)};

// Build graph
const g = new dagreD3.graphlib.Graph().setGraph({{
  rankdir: "TB",
  ranksep: 60,
  nodesep: 30,
  marginx: 20,
  marginy: 20,
}});

NODES.forEach(n => {{
  g.setNode(n.id, {{
    labelType: "html",
    label: n.label,
    style: `fill: ${{n.bg}}; stroke: ${{n.border}}; stroke-width: 2px;`,
    padding: 0,
    id: n.id,
  }});
}});

EDGES.forEach(e => {{
  g.setEdge(e.source, e.target, {{
    style: "stroke: #7f8c8d; stroke-width: 1.5px;",
    arrowheadStyle: "fill: #7f8c8d",
    curve: d3.curveBasis,
  }});
}});

// Render
const svg = d3.select("#graph-container").append("svg");
const svgGroup = svg.append("g");
const render = new dagreD3.render();
render(svgGroup, g);

// Size SVG
const graphWidth = g.graph().width + 40;
const graphHeight = g.graph().height + 40;
svg.attr("width", Math.max(graphWidth, 800));
svg.attr("height", Math.max(graphHeight, 600));

// Zoom
const zoom = d3.zoom().on("zoom", () => {{
  svgGroup.attr("transform", d3.event.transform);
}});
svg.call(zoom);

// Tooltips — dagre-d3 stores the DOM element on g.node(id).elem after render
NODES.forEach(n => {{
  const nd = g.node(n.id);
  if (nd && nd.elem) {{
    d3.select(nd.elem)
      .attr("data-node-id", n.id)
      .insert("title", ":first-child")
      .text(n.tooltip.replace(/\\\\n/g, "\\n"));
  }}
}});

// Click handler — use data-node-id set during tooltip phase
svg.selectAll("g.node").on("click", function() {{
  const nodeId = d3.select(this).attr("data-node-id");
  if (nodeId) showDetail(nodeId);
}});

function showDetail(nodeId) {{
  const panel = document.getElementById("detail-panel");
  const node = NODES.find(n => n.id === nodeId);
  if (!node) return;

  let html = `<h3>${{node.id}}: ${{node.type}}</h3>`;

  // Proof steps
  const steps = PROOF_STEPS[nodeId];
  if (steps && steps.length > 0) {{
    html += `<div class="detail-section"><h4>Proof Steps (${{steps.length}})</h4><div class="step-chain">`;
    steps.forEach((s, i) => {{
      html += `<div class="step-item"><strong>${{s.id}}</strong>: ${{escapeHtml(s.statement)}}</div>`;
      if (i < steps.length - 1) html += `<div class="step-arrow">&#8595;</div>`;
    }});
    html += `</div></div>`;
  }}

  // Equations
  const eqs = EQUATIONS[nodeId];
  if (eqs && eqs.length > 0) {{
    html += `<div class="detail-section"><h4>Related Equations (${{eqs.length}})</h4>`;
    eqs.forEach(e => {{
      html += `<div class="eq-item"><strong>${{e.id}}</strong> (Sec ${{e.section}}): ${{escapeHtml(e.statement)}}</div>`;
    }});
    html += `</div>`;
  }}

  if (!steps && !eqs) {{
    html += `<div style="color:#888;font-size:12px;margin-top:8px;">No proof steps or equations linked to this node.</div>`;
  }}

  panel.innerHTML = html;
  panel.classList.add("open");
}}

function resetView() {{
  document.getElementById("detail-panel").classList.remove("open");
  document.getElementById("detail-panel").innerHTML = "";
  svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
}}

function toggleAllSteps() {{
  const btn = document.getElementById("btn-steps");
  // For now just show the detail panel with all steps
  const panel = document.getElementById("detail-panel");
  let html = "<h3>All Proof Steps</h3>";
  for (const [thmId, steps] of Object.entries(PROOF_STEPS)) {{
    html += `<div class="detail-section"><h4>${{thmId}} (${{steps.length}} steps)</h4><div class="step-chain">`;
    steps.forEach((s, i) => {{
      html += `<div class="step-item"><strong>${{s.id}}</strong>: ${{escapeHtml(s.statement)}}</div>`;
      if (i < steps.length - 1) html += `<div class="step-arrow">&#8595;</div>`;
    }});
    html += `</div></div>`;
  }});
  panel.innerHTML = html;
  panel.classList.add("open");
}}

function toggleOrphans() {{
  const panel = document.getElementById("orphan-panel");
  if (panel.style.display === "block") {{
    panel.style.display = "none";
  }} else {{
    let html = "";
    ORPHANS.forEach(e => {{
      html += `<div class="orphan-item"><strong>${{e.id}}</strong> (Sec ${{e.section}}): ${{escapeHtml(e.statement)}}</div>`;
    }});
    document.getElementById("orphan-list").innerHTML = html;
    panel.style.display = "block";
  }}
}}

function escapeHtml(text) {{
  if (!text) return "";
  return text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return len(base_nodes), len(base_edges), len(proof_steps), len(equations), len(orphan_equations)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="Input JSON annotation file")
    parser.add_argument("output", nargs="?", default=None, help="Output HTML file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".html")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    n_base, n_edges, n_steps, n_eqs, n_orphans = generate_html(data, output_path)
    print(f"Interactive HTML saved to {output_path}")
    print(f"  Base nodes: {n_base}, Edges: {n_edges}")
    print(f"  Proof steps: {n_steps}, Equations: {n_eqs}, Orphan equations: {n_orphans}")


if __name__ == "__main__":
    main()
