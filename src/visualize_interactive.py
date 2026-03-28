#!/usr/bin/env python3
"""Generate an interactive HTML visualization of a knowledge graph.

Usage:
    python visualize_interactive.py annotation.json [output.html]

Produces a standalone HTML file with:
  - Layered DAG layout (dagre-d3)
  - Click node → side panel shows details, proof steps, equations
  - Hover → tooltip
  - Zoom and pan
  - Orphan equations in collapsible panel
"""
import json
import sys
from pathlib import Path
from html import escape


NODE_COLORS = {
    "definition":  {"bg": "#D5F5E3", "border": "#27AE60"},
    "theorem":     {"bg": "#FADBD8", "border": "#C0392B"},
    "lemma":       {"bg": "#FDEBD0", "border": "#E67E22"},
    "corollary":   {"bg": "#E8DAEF", "border": "#8E44AD"},
    "proposition": {"bg": "#FADBD8", "border": "#C0392B"},
    "algorithm":   {"bg": "#FFF9C4", "border": "#D4AC0D"},
    "proof":       {"bg": "#D5D8DC", "border": "#566573"},
    "equation":    {"bg": "#D4E6F1", "border": "#5DADE2"},
    "proof_step":  {"bg": "#E8E8E8", "border": "#839192"},
    "claim":       {"bg": "#F6DDCC", "border": "#BA4A00"},
}
DEFAULT_COLOR = {"bg": "#EAECEE", "border": "#566573"}


def _short(text, maxlen=60):
    if not text or len(text) <= maxlen:
        return text or ""
    return text[:maxlen-3] + "..."


def classify_and_merge(nodes, edges):
    """Merge proofs into parent theorems. Separate equations/proof_steps."""
    node_by_id = {n["id"]: n for n in nodes}
    base_types = {"definition", "theorem", "lemma", "corollary", "proposition",
                  "algorithm", "proof", "claim"}

    # Merge proofs
    proof_map = {}
    for n in nodes:
        if n.get("type") == "proof" and n.get("proves") and n["proves"] in node_by_id:
            proof_map[n["id"]] = n["proves"]
            parent = node_by_id[n["proves"]]
            if "proof_info" not in parent:
                parent["proof_info"] = []
            if n.get("proof_strategy"):
                parent["proof_info"].append(n["proof_strategy"])

    # Classify
    base_nodes, proof_steps, equations, orphan_eqs = [], [], [], []
    has_edge = set()
    for e in edges:
        has_edge.add(e["source"])
        has_edge.add(e["target"])

    for n in nodes:
        if n["id"] in proof_map:
            continue  # merged into parent
        if n["type"] == "proof_step":
            proof_steps.append(n)
        elif n["type"] == "equation":
            if n["id"] in has_edge:
                equations.append(n)
            else:
                orphan_eqs.append(n)
        else:
            base_nodes.append(n)

    # Redirect edges
    base_ids = {n["id"] for n in base_nodes}
    base_edges = []
    seen = set()
    for e in edges:
        s = proof_map.get(e["source"], e["source"])
        t = proof_map.get(e["target"], e["target"])
        if s == t or s not in base_ids or t not in base_ids:
            continue
        key = (s, t)
        if key not in seen:
            base_edges.append({"source": s, "target": t})
            seen.add(key)

    # Proof step chains per theorem
    step_chains = {}
    for ps in proof_steps:
        parent = ps.get("parent_proof", "")
        thm_id = proof_map.get(parent, parent)
        step_chains.setdefault(thm_id, []).append(ps)

    # Equations per parent
    eq_map = {}
    for eq in equations:
        for e in edges:
            if e["source"] == eq["id"] and e["target"] in base_ids:
                eq_map.setdefault(e["target"], []).append(eq)
            if e["target"] == eq["id"] and e["source"] in base_ids:
                eq_map.setdefault(e["source"], []).append(eq)

    return base_nodes, base_edges, step_chains, eq_map, orphan_eqs


def generate_html(data, output_path):
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    metadata = data.get("metadata", {})

    base_nodes, base_edges, step_chains, eq_map, orphan_eqs = classify_and_merge(nodes, edges)

    ch = metadata.get("chapter", "")
    ch_title = metadata.get("chapter_title", "")
    title = f"Chapter {ch}: {ch_title}" if ch_title else "Knowledge Graph"

    # Build JS data — simple labels, detail in separate object
    js_nodes_list = []
    js_details = {}
    for n in base_nodes:
        colors = NODE_COLORS.get(n.get("type", ""), DEFAULT_COLOR)
        import re as _re
        name = n.get("name") or ""
        # Strip $...$ LaTeX from label — math renders in the detail panel via MathJax
        clean_name = _re.sub(r'\$[^$]*\$', lambda m: m.group(0).strip('$').replace('\\\\', '').replace('\\', ''), name)
        label = f"{n['id']}: {clean_name}" if clean_name else n["id"]
        if len(label) > 40:
            label = label[:37] + "..."

        js_nodes_list.append({
            "id": n["id"],
            "label": label,
            "type": n.get("type", ""),
            "bg": colors["bg"],
            "border": colors["border"],
        })

        js_details[n["id"]] = {
            "name": name,
            "type": n.get("type", ""),
            "section": n.get("section", ""),
            "statement": n.get("statement", ""),
            "assumptions": n.get("assumptions", []),
            "conclusions": n.get("conclusions", []),
            "proof_info": n.get("proof_info", []),
            "input": n.get("input", []),
            "output": n.get("output", []),
            "steps": [{"id": s["id"], "statement": s.get("statement","")} for s in step_chains.get(n["id"], [])],
            "equations": [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section","")} for e in eq_map.get(n["id"], [])],
        }

    js_orphans = [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section","")} for e in orphan_eqs]

    # Serialize data to JSON strings (properly escaped for embedding in HTML)
    nodes_json = json.dumps(js_nodes_list, ensure_ascii=True)
    edges_json = json.dumps([{"source": e["source"], "target": e["target"]} for e in base_edges], ensure_ascii=True)
    details_json = json.dumps(js_details, ensure_ascii=True)
    orphans_json = json.dumps(js_orphans, ensure_ascii=True)

    # Build HTML as plain string concatenation (NOT f-string) to avoid brace issues
    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; background: #fafafa; }}
#header {{ background: #2c3e50; color: white; padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; }}
#header h1 {{ margin: 0; font-size: 18px; }}
#controls button {{ padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; background: #34495e; color: white; margin-left: 8px; }}
#controls button:hover {{ background: #4a6785; }}
#main {{ display: flex; height: calc(100vh - 80px); }}
#graph-container {{ flex: 1; overflow: auto; }}
svg {{ display: block; }}
.node rect {{ cursor: pointer; rx: 5; ry: 5; }}
.node:hover rect {{ filter: brightness(0.90); }}
.edgePath path {{ stroke: #555; stroke-width: 2px; fill: none; }}
.edgePath marker path {{ fill: #555; stroke: none; }}
#detail-panel {{ width: 0; overflow-y: auto; background: white; border-left: 1px solid #ddd; transition: width 0.3s; }}
#detail-panel.open {{ width: 380px; padding: 16px; }}
.detail-section {{ margin-bottom: 12px; }}
.detail-section h4 {{ margin: 0 0 4px; color: #555; font-size: 11px; text-transform: uppercase; }}
.step-item {{ background: #f0f0f0; border-left: 3px solid #839192; padding: 5px 8px; font-size: 11px; margin-bottom: 3px; border-radius: 0 3px 3px 0; }}
.step-arrow {{ text-align: center; color: #aaa; font-size: 12px; }}
.eq-item {{ background: #d4e6f1; border-left: 3px solid #5dade2; padding: 5px 8px; font-size: 11px; margin-bottom: 3px; border-radius: 0 3px 3px 0; }}
.orphan-item {{ background: #fef9e7; border-left: 3px solid #f39c12; padding: 5px 8px; font-size: 11px; margin-bottom: 3px; }}
#orphan-panel {{ position: fixed; bottom: 16px; right: 16px; background: white; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); max-width: 350px; max-height: 400px; overflow-y: auto; display: none; padding: 12px; z-index: 100; }}
#orphan-toggle {{ position: fixed; bottom: 16px; right: 16px; background: #f39c12; color: white; border: none; border-radius: 20px; padding: 8px 16px; cursor: pointer; font-size: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.2); z-index: 101; display: {"block" if js_orphans else "none"}; }}
.legend {{ display: flex; gap: 12px; flex-wrap: wrap; padding: 6px 24px; background: #f5f5f5; border-bottom: 1px solid #eee; }}
.legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 11px; }}
.legend-color {{ width: 12px; height: 12px; border-radius: 2px; border: 1px solid #999; }}
</style>
</head>
<body>
<div id="header">
  <h1>{escape(title)}</h1>
  <div id="controls">
    <button onclick="resetView()">Reset View</button>
  </div>
</div>
<div class="legend">
  <div class="legend-item"><div class="legend-color" style="background:#D5F5E3;border-color:#27AE60;"></div>Definition</div>
  <div class="legend-item"><div class="legend-color" style="background:#FADBD8;border-color:#C0392B;"></div>Theorem</div>
  <div class="legend-item"><div class="legend-color" style="background:#FDEBD0;border-color:#E67E22;"></div>Lemma</div>
  <div class="legend-item"><div class="legend-color" style="background:#E8DAEF;border-color:#8E44AD;"></div>Corollary</div>
  <div class="legend-item"><div class="legend-color" style="background:#FFF9C4;border-color:#D4AC0D;"></div>Algorithm</div>
  <div class="legend-item" style="margin-left:auto;color:#888;font-style:italic;">Click a node for details</div>
</div>
<div id="main">
  <div id="graph-container"></div>
  <div id="detail-panel"></div>
</div>
<button id="orphan-toggle" onclick="toggleOrphans()">{len(js_orphans)} orphan eq{'s' if len(js_orphans) != 1 else ''}</button>
<div id="orphan-panel"><h3>Unconnected Equations</h3><div id="orphan-list"></div></div>
""")

    # JavaScript as a separate string to avoid f-string brace conflicts
    js_code = """
<script src="https://d3js.org/d3.v5.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dagre-d3@0.6.4/dist/dagre-d3.min.js"></script>
<script>MathJax = {tex: {inlineMath: [['$','$']]}, startup: {typeset: false}};</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<script>
var NODES = """ + nodes_json + """;
var EDGES = """ + edges_json + """;
var DETAILS = """ + details_json + """;
var ORPHANS = """ + orphans_json + """;

try {
  var g = new dagreD3.graphlib.Graph().setGraph({
    rankdir: "TB", ranksep: 50, nodesep: 25, marginx: 20, marginy: 20
  });

  NODES.forEach(function(n) {
    g.setNode(n.id, {
      label: n.label,
      style: "fill: " + n.bg + "; stroke: " + n.border + "; stroke-width: 2px;",
      paddingLeft: 10, paddingRight: 10, paddingTop: 6, paddingBottom: 6
    });
  });

  EDGES.forEach(function(e) {
    g.setEdge(e.source, e.target, {
      style: "stroke: #7f8c8d; stroke-width: 2px;",
      arrowheadStyle: "fill: #7f8c8d; stroke: #7f8c8d;"
    });
  });

  var svg = d3.select("#graph-container").append("svg")
    .attr("width", 1200)
    .attr("height", 800);
  var svgGroup = svg.append("g");

  var render = new dagreD3.render();
  render(svgGroup, g);

  // Resize SVG to fit graph
  var gw = g.graph().width + 80;
  var gh = g.graph().height + 80;
  svg.attr("width", Math.max(gw, 800));
  svg.attr("height", Math.max(gh, 600));

  // Center
  var xOffset = (Math.max(gw, 800) - g.graph().width) / 2;
  svgGroup.attr("transform", "translate(" + xOffset + ", 40)");

  // Zoom
  var zoom = d3.zoom().on("zoom", function() {
    svgGroup.attr("transform", d3.event.transform);
  });
  svg.call(zoom);

  // Set data attributes for click handling
  NODES.forEach(function(n) {
    var nd = g.node(n.id);
    if (nd && nd.elem) {
      d3.select(nd.elem).attr("data-node-id", n.id);
    }
  });

  // Click handler
  svg.selectAll("g.node").on("click", function() {
    var nodeId = d3.select(this).attr("data-node-id");
    if (nodeId) showDetail(nodeId);
  });

  console.log("SARANGA graph rendered: " + g.nodeCount() + " nodes, " + g.edgeCount() + " edges");

} catch(err) {
  console.error("SARANGA render error:", err);
  document.getElementById("graph-container").innerHTML =
    '<div style="color:red;padding:20px;"><h3>Render Error</h3><pre>' + err.message + '</pre></div>';
}

function showDetail(nodeId) {
  var panel = document.getElementById("detail-panel");
  var d = DETAILS[nodeId];
  if (!d) return;

  var h = '<h3 style="margin:0 0 8px;">' + esc(nodeId) + ': ' + esc(d.name || d.type) + '</h3>';
  h += '<div style="font-size:11px;color:#888;margin-bottom:8px;">' + d.type + (d.section ? ' (Sec ' + d.section + ')' : '') + '</div>';

  if (d.statement) {
    h += '<div class="detail-section"><h4>Statement</h4><div style="font-size:12px;">' + esc(d.statement) + '</div></div>';
  }
  if (d.assumptions && d.assumptions.length > 0) {
    h += '<div class="detail-section"><h4>Assumptions</h4>';
    d.assumptions.forEach(function(a) { h += '<div style="font-size:11px;padding:1px 0 1px 8px;">&bull; ' + esc(a) + '</div>'; });
    h += '</div>';
  }
  if (d.conclusions && d.conclusions.length > 0) {
    h += '<div class="detail-section"><h4>Conclusions</h4>';
    d.conclusions.forEach(function(c) { h += '<div style="font-size:11px;padding:1px 0 1px 8px;">&bull; ' + esc(c) + '</div>'; });
    h += '</div>';
  }
  if (d.proof_info && d.proof_info.length > 0) {
    h += '<div class="detail-section"><h4>Proof Strategy</h4>';
    d.proof_info.forEach(function(p) { h += '<div style="font-size:11px;font-style:italic;">' + esc(typeof p === 'string' ? p : JSON.stringify(p)) + '</div>'; });
    h += '</div>';
  }
  if (d.input && d.input.length > 0) {
    h += '<div class="detail-section"><h4>Input</h4>';
    d.input.forEach(function(x) { h += '<div style="font-size:11px;">&bull; ' + esc(x) + '</div>'; });
    h += '</div>';
  }
  if (d.output && d.output.length > 0) {
    h += '<div class="detail-section"><h4>Output</h4>';
    d.output.forEach(function(x) { h += '<div style="font-size:11px;">&bull; ' + esc(x) + '</div>'; });
    h += '</div>';
  }
  if (d.steps && d.steps.length > 0) {
    h += '<div class="detail-section"><h4>Proof Steps (' + d.steps.length + ')</h4>';
    d.steps.forEach(function(s, i) {
      h += '<div class="step-item"><strong>' + s.id + '</strong>: ' + esc(s.statement) + '</div>';
      if (i < d.steps.length - 1) h += '<div class="step-arrow">&#8595;</div>';
    });
    h += '</div>';
  }
  if (d.equations && d.equations.length > 0) {
    h += '<div class="detail-section"><h4>Equations (' + d.equations.length + ')</h4>';
    d.equations.forEach(function(e) {
      h += '<div class="eq-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>';
    });
    h += '</div>';
  }

  panel.innerHTML = h;
  panel.className = "open";
  if (window.MathJax && MathJax.typesetPromise) {
    MathJax.typesetPromise([panel]).catch(function(err) { console.log("MathJax error:", err); });
  }
}

function resetView() {
  document.getElementById("detail-panel").className = "";
  document.getElementById("detail-panel").innerHTML = "";
}

function toggleOrphans() {
  var panel = document.getElementById("orphan-panel");
  if (panel.style.display === "block") {
    panel.style.display = "none";
  } else {
    var h = "";
    ORPHANS.forEach(function(e) {
      h += '<div class="orphan-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>';
    });
    document.getElementById("orphan-list").innerHTML = h;
    panel.style.display = "block";
  }
}

function esc(text) {
  if (!text) return "";
  // Escape HTML but preserve $ and \\ for MathJax rendering
  return text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
</script>
</body>
</html>
"""

    html_parts.append(js_code)
    Path(output_path).write_text("".join(html_parts), encoding="utf-8")
    return len(base_nodes), len(base_edges), len(step_chains), len(eq_map), len(orphan_eqs)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input JSON")
    parser.add_argument("output", nargs="?", default=None, help="Output HTML")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".html")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    n_base, n_edges, n_steps, n_eqs, n_orphans = generate_html(data, output_path)
    print(f"Interactive HTML saved to {output_path}")
    print(f"  Base nodes: {n_base}, Edges: {n_edges}, Steps: {n_steps}, Eqs: {n_eqs}, Orphans: {n_orphans}")


if __name__ == "__main__":
    main()
