#!/usr/bin/env python3
"""Visualize a student annotation JSON as a DAG knowledge graph.

Usage:
    python visualize_annotation.py annotation.json [output.png]

Produces a layered DAG visualization with:
  - Topological depth for vertical positioning (foundations at top, results at bottom)
  - Compound boxes for theorems/lemmas showing assumptions and conclusions
  - Proof strategy collapsed into the parent theorem's box
  - Color-coded by node type
"""
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams['mathtext.fontset'] = 'cm'  # Computer Modern for math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import networkx as nx


# ── Colors ──────────────────────────────────────────────────────────────────
NODE_COLORS = {
    "definition":  {"header": "#27AE60", "body": "#D5F5E3"},
    "theorem":     {"header": "#C0392B", "body": "#FADBD8"},
    "lemma":       {"header": "#E67E22", "body": "#FDEBD0"},
    "corollary":   {"header": "#8E44AD", "body": "#E8DAEF"},
    "algorithm":   {"header": "#D4AC0D", "body": "#FFF9C4"},
    "equation":    {"header": "#5DADE2", "body": "#D4E6F1"},
    "proposition": {"header": "#C0392B", "body": "#FADBD8"},
    "proof":       {"header": "#566573", "body": "#D5D8DC"},
    "proof_step":  {"header": "#839192", "body": "#E8E8E8"},
    "claim":       {"header": "#BA4A00", "body": "#F6DDCC"},
}
DEFAULT_COLOR = {"header": "#566573", "body": "#EAECEE"}
PROOF_COLOR = "#D5D8DC"


# ── Text helpers ────────────────────────────────────────────────────────────
# LaTeX commands not supported by matplotlib mathtext — replace with equivalents
_LATEX_FIXES = {
    r"\iff": r"\Leftrightarrow",
    r"\implies": r"\Rightarrow",
    r"\Pr": r"\mathrm{Pr}",
    r"\boldsymbol": r"\mathbf",
    r"\big|": "|", r"\Big|": "|", r"\bigg|": "|",
    r"\big(": "(", r"\Big(": "(", r"\big)": ")", r"\Big)": ")",
    r"\left|": "|", r"\right|": "|",
    r"\text": r"\mathrm",
    r"\operatorname": r"\mathrm",
    r"\binom": r"\mathrm{C}",
    r"\pmod": r"\mathrm{mod}",
    r"\mod": r"\mathrm{mod}",
    r"\lceil": r"\lfloor", r"\rceil": r"\rfloor",
    r"\lVert": r"\|", r"\rVert": r"\|",
    r"\triangleq": r"=",
    r"\coloneqq": r":=",
    r"\lfloor": r"\lfloor", r"\rfloor": r"\rfloor",  # these are fine
}

def _sanitize_math(text):
    """Replace unsupported LaTeX commands with matplotlib-compatible equivalents."""
    if not text:
        return text
    for old, new in _LATEX_FIXES.items():
        text = text.replace(old, new)
    return text


def _wrap(text, width=38):
    if not text:
        return []
    return textwrap.wrap(text, width=width)


def _shorten(text, maxlen=80):
    """Shorten text, never cutting inside a $...$ math expression.

    If cutting would land inside an equation, drop the equation entirely
    rather than showing a partial formula.
    """
    if not text:
        return ""
    text = _sanitize_math(text)
    if len(text) <= maxlen:
        return text
    cut = maxlen - 3
    # Count $ signs before cut point; if odd, we're inside math
    n_dollars = text[:cut].count("$")
    if n_dollars % 2 == 1:
        # Inside math — find the opening $ of this equation and cut before it
        # Walk backwards from cut to find the last unmatched $
        last_dollar = text.rfind("$", 0, cut)
        if last_dollar > 0:
            cut = last_dollar  # cut before the equation starts
        else:
            cut = maxlen - 3  # fallback
    return text[:cut].rstrip() + "..."


# ── DAG computation ─────────────────────────────────────────────────────────
def compute_dag_depth(nodes, edges):
    """Compute longest-path depth for each node. Roots = depth 0."""
    adj = defaultdict(list)
    in_deg = defaultdict(int)
    node_ids = {n["id"] for n in nodes}

    for e in edges:
        s, t = e["source"], e["target"]
        if s in node_ids and t in node_ids:
            adj[s].append(t)
            in_deg[t] += 0  # ensure exists
            in_deg[s] += 0

    # recount
    in_deg = defaultdict(int)
    for e in edges:
        s, t = e["source"], e["target"]
        if s in node_ids and t in node_ids:
            in_deg[t] += 1

    depth = {nid: 0 for nid in node_ids}
    queue = [nid for nid in node_ids if in_deg[nid] == 0]

    while queue:
        nid = queue.pop(0)
        for tgt in adj[nid]:
            depth[tgt] = max(depth[tgt], depth[nid] + 1)
            in_deg[tgt] -= 1
            if in_deg[tgt] == 0:
                queue.append(tgt)

    return depth


def _section_sort_key(node):
    """Sort by section number, then by ID."""
    sec = node.get("section", "99")
    try:
        parts = [float(x) for x in sec.split(".")]
    except ValueError:
        parts = [99]
    return (parts, node["id"])


# ── Merge proofs into parent theorems ───────────────────────────────────────
def merge_proofs(nodes, edges):
    """Collapse proof nodes into their parent theorem.

    Returns:
      display_nodes: list of non-proof nodes, each with optional 'proof_info'
      display_edges: edges with proof endpoints redirected to theorem
      proof_map: {proof_id: theorem_id}
    """
    node_by_id = {n["id"]: n for n in nodes}
    proof_map = {}  # proof_id -> theorem_id

    for n in nodes:
        if n["type"] == "proof" and n.get("proves"):
            target_id = n["proves"]
            if target_id in node_by_id:
                proof_map[n["id"]] = target_id

    # Attach proof info to parent theorem
    display_nodes = []
    for n in nodes:
        if n["id"] in proof_map:
            # Attach to parent
            parent_id = proof_map[n["id"]]
            parent = node_by_id[parent_id]
            if "proof_info" not in parent:
                parent["proof_info"] = []
            parent["proof_info"].append(n.get("proof_strategy", ""))
            continue
        display_nodes.append(n)

    # Redirect edges: replace proof_id with its theorem_id
    display_edges = []
    seen = set()
    for e in edges:
        s = proof_map.get(e["source"], e["source"])
        t = proof_map.get(e["target"], e["target"])
        if s == t:
            continue  # skip self-loops from merging
        key = (s, t)
        if key not in seen:
            display_edges.append({"source": s, "target": t,
                                  "type": e.get("type", ""),
                                  "note": e.get("note", "")})
            seen.add(key)

    return display_nodes, display_edges, proof_map


# ── Drawing ─────────────────────────────────────────────────────────────────
def draw_dag(nodes_raw, edges_raw, out_path, figsize=None, metadata=None,
             resolution="standard"):
    """Main entry: draw a layered DAG from student-format nodes/edges.

    resolution:
      "standard" — collapse proofs into theorem boxes, hide equations/proof_steps
      "full"     — show all nodes including proofs, equations, proof_steps as separate nodes
    """
    if resolution == "full":
        # Full resolution: no merging, show everything
        nodes = list(nodes_raw)
        edges = list(edges_raw)
        proof_map = {}
    else:
        # Standard: collapse proofs AND filter out equations/proof_steps
        nodes, edges, proof_map = merge_proofs(nodes_raw, edges_raw)
        hidden_types = {"equation", "proof_step"}
        hidden_ids = {n["id"] for n in nodes if n.get("type") in hidden_types}
        nodes = [n for n in nodes if n.get("type") not in hidden_types]
        edges = [e for e in edges
                 if e["source"] not in hidden_ids and e["target"] not in hidden_ids]
    depth = compute_dag_depth(nodes, edges)

    # Group by depth level
    levels = defaultdict(list)
    for n in nodes:
        levels[depth[n["id"]]].append(n)

    # Sort within each level by section
    for d in levels:
        levels[d].sort(key=_section_sort_key)

    max_depth = max(levels.keys()) if levels else 0
    max_width = max(len(v) for v in levels.values()) if levels else 1

    # ── Box dimensions ──
    MIN_BOX_W = 3.0
    MAX_BOX_W = 6.0
    BOX_GAP_X = 0.5
    LEVEL_GAP_Y = 5.0
    HEADER_H = 0.45
    LINE_H = 0.28
    PADDING = 0.10
    CHARS_PER_UNIT = 12  # approx chars per unit of box width
    MAX_LINES_PER_SECTION = 3

    def _content_lines(n):
        """Get all content text lines for a node (for width estimation)."""
        ntype = n.get("type", "")
        lines = []
        name = n.get("name") or ""
        lines.append(f"{n['id']}: {name}" if name else n['id'])
        if ntype in ("theorem", "lemma", "corollary", "proposition"):
            for a in (n.get("assumptions") or [])[:MAX_LINES_PER_SECTION]:
                lines.append(_shorten(a, 100))
            for c in (n.get("conclusions") or [])[:MAX_LINES_PER_SECTION]:
                lines.append(_shorten(c, 100))
            for ps in (n.get("proof_info") or []):
                if ps: lines.append(_shorten(f"Proof: {ps}", 100))
        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            for x in (n.get("input") or []): lines.append(_shorten(x, 100))
            for x in (n.get("output") or []): lines.append(_shorten(x, 100))
        else:
            lines.append(_shorten(n.get("statement", ""), 150))
        return lines

    # ── First pass: compute each node's ideal width ──
    node_width = {}
    node_data = {}
    for n in nodes:
        nid = n["id"]
        node_data[nid] = n
        content = _content_lines(n)
        max_line = max(len(line) for line in content) if content else 10
        w = max(MIN_BOX_W, min(MAX_BOX_W, max_line / CHARS_PER_UNIT))
        node_width[nid] = w

    # ── Second pass: compute heights and positions ──
    node_pos = {}
    node_rect = {}

    for d in range(max_depth + 1):
        row = levels.get(d, [])
        # Compute row width using actual node widths
        row_width = sum(node_width[n["id"]] for n in row) + max(0, len(row) - 1) * BOX_GAP_X
        x_cursor = -row_width / 2

        for n in row:
            nid = n["id"]
            w = node_width[nid]
            wrap_w = max(20, int(w * CHARS_PER_UNIT))
            cy_top = -d * LEVEL_GAP_Y
            ntype = n.get("type", "")

            if ntype in ("theorem", "lemma", "corollary", "proposition"):
                assumptions = n.get("assumptions", [])
                conclusions = n.get("conclusions", [])
                proof_strategies = n.get("proof_info", [])

                assume_lines = [_shorten(a, 100) for a in assumptions]
                if len(assume_lines) > MAX_LINES_PER_SECTION:
                    assume_lines = assume_lines[:MAX_LINES_PER_SECTION] + [f"... +{len(assumptions)-MAX_LINES_PER_SECTION} more"]
                conclude_lines = [_shorten(c, 100) for c in conclusions]
                if len(conclude_lines) > MAX_LINES_PER_SECTION:
                    conclude_lines = conclude_lines[:MAX_LINES_PER_SECTION] + [f"... +{len(conclusions)-MAX_LINES_PER_SECTION} more"]
                proof_lines = [_shorten(f"Proof: {ps}", 100) for ps in proof_strategies if ps]

                n_assume = max(len(assume_lines), 1)
                n_conclude = max(len(conclude_lines), 1)
                n_proof = len(proof_lines)

                h = HEADER_H + PADDING
                h += n_assume * LINE_H + PADDING
                h += n_conclude * LINE_H + PADDING
                if n_proof > 0:
                    h += n_proof * LINE_H + PADDING
                h += PADDING
            elif ntype == "algorithm" and (n.get("input") or n.get("output")):
                in_lines = [_shorten(x, 100) for x in (n.get("input") or ["(none)"])]
                out_lines = [_shorten(x, 100) for x in (n.get("output") or ["(none)"])]
                h = HEADER_H + PADDING
                h += len(in_lines) * LINE_H + PADDING
                h += len(out_lines) * LINE_H + PADDING
                h += PADDING
            else:
                stmt = _shorten(n.get("statement", ""), 150)
                stmt_lines = _wrap(stmt, wrap_w)[:3]
                n_stmt = max(len(stmt_lines), 1)
                h = HEADER_H + n_stmt * LINE_H + 2 * PADDING

            node_pos[nid] = (x_cursor + w / 2, cy_top - h / 2)
            node_rect[nid] = (x_cursor, cy_top - h, w, h)
            x_cursor += w + BOX_GAP_X

    # ── Figure ── (auto-size based on content)
    if figsize is None:
        avg_w = sum(node_width.values()) / max(len(node_width), 1)
        fw = max(max_width * (avg_w + BOX_GAP_X) + 4, 16)
        fh = max((max_depth + 1) * LEVEL_GAP_Y + 4, 12)
        figsize = (fw, fh)

    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Draw edges first (behind boxes) ──
    for e in edges:
        src, tgt = e["source"], e["target"]
        if src not in node_rect or tgt not in node_rect:
            continue
        sx, sy_bottom, sw, sh = node_rect[src]
        tx, ty_bottom, tw, th = node_rect[tgt]

        x0 = sx + sw / 2
        y0 = sy_bottom  # bottom of source
        x1 = tx + tw / 2
        y1 = ty_bottom + th  # top of target

        ax.annotate(
            "", xy=(x1, y1), xytext=(x0, y0),
            arrowprops=dict(
                arrowstyle="-|>,head_length=0.8,head_width=0.4",
                color="#666666",
                lw=2.0,
                connectionstyle="arc3,rad=0.08" if abs(x0 - x1) > 0.5 else "arc3,rad=0",
                shrinkA=3, shrinkB=3,
            ),
        )

    # ── Draw boxes ──
    for nid, (bx, by, bw, bh) in node_rect.items():
        n = node_data[nid]
        ntype = n.get("type", "")
        colors = NODE_COLORS.get(ntype, DEFAULT_COLOR)

        # Main box background (gid for SVG click handling)
        rect = FancyBboxPatch(
            (bx, by), bw, bh,
            boxstyle="round,pad=0.05",
            facecolor=colors["body"],
            edgecolor=colors["header"],
            linewidth=1.5,
            gid=f"node_{nid}",
        )
        ax.add_patch(rect)

        cursor_y = by + bh  # start from top

        # Header
        name_str = n.get("name") or ""
        header_text = f"{nid}"
        if name_str:
            header_text += f": {_shorten(name_str, 30)}"

        header_rect = FancyBboxPatch(
            (bx, cursor_y - HEADER_H), bw, HEADER_H,
            boxstyle="round,pad=0.05",
            facecolor=colors["header"],
            edgecolor=colors["header"],
            linewidth=0,
        )
        ax.add_patch(header_rect)
        ax.text(bx + bw / 2, cursor_y - HEADER_H / 2, header_text,
                ha="center", va="center", fontsize=8.5, fontweight="bold",
                color="white")
        cursor_y -= HEADER_H + PADDING

        if ntype in ("theorem", "lemma", "corollary", "proposition"):
            # Rebuild truncated lines (matching height computation)
            assumptions = n.get("assumptions", [])
            a_lines = [_shorten(a, 70) for a in assumptions]
            if len(a_lines) > MAX_LINES_PER_SECTION:
                a_lines = a_lines[:MAX_LINES_PER_SECTION] + [f"... +{len(assumptions)-MAX_LINES_PER_SECTION} more"]
            if not a_lines:
                a_lines = ["(none)"]

            conclusions = n.get("conclusions", [])
            c_lines = [_shorten(c, 70) for c in conclusions]
            if len(c_lines) > MAX_LINES_PER_SECTION:
                c_lines = c_lines[:MAX_LINES_PER_SECTION] + [f"... +{len(conclusions)-MAX_LINES_PER_SECTION} more"]
            if not c_lines:
                c_lines = ["(none)"]

            # Assumptions
            ax.text(bx + PADDING, cursor_y, "Assume:",
                    ha="left", va="top", fontsize=8, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in a_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=7.5, color="#222",
                        fontstyle="italic")
                cursor_y -= LINE_H

            cursor_y -= PADDING * 0.3

            # Divider line
            ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                    color=colors["header"], lw=0.5, alpha=0.4)

            # Conclusions
            ax.text(bx + PADDING, cursor_y, "Conclude:",
                    ha="left", va="top", fontsize=8, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in c_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=7.5, color="#222")
                cursor_y -= LINE_H

            # Proof strategy (if merged)
            proof_strategies = n.get("proof_info", [])
            if proof_strategies:
                cursor_y -= PADDING * 0.2
                ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.1] * 2,
                        color="#999", lw=0.5, alpha=0.4)
                for ps in proof_strategies:
                    if ps:
                        ax.text(bx + PADDING, cursor_y, _shorten(f"Proof: {ps}", 70),
                                ha="left", va="top", fontsize=7.5,
                                color="#444", fontstyle="italic")
                        cursor_y -= LINE_H

        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            # Algorithm with input/output
            in_lines = [_shorten(x, 70) for x in (n.get("input") or ["(none)"])]
            out_lines = [_shorten(x, 70) for x in (n.get("output") or ["(none)"])]

            ax.text(bx + PADDING, cursor_y, "Input:",
                    ha="left", va="top", fontsize=8, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in in_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=7.5, color="#222")
                cursor_y -= LINE_H
            cursor_y -= PADDING * 0.3
            ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                    color=colors["header"], lw=0.5, alpha=0.4)
            ax.text(bx + PADDING, cursor_y, "Output:",
                    ha="left", va="top", fontsize=8, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in out_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=7.5, color="#222")
                cursor_y -= LINE_H

        else:
            # Simple box: just statement text (max 3 lines)
            dyn_wrap = max(20, int(node_width.get(nid, 4.0) * CHARS_PER_UNIT))
            stmt = _shorten(n.get("statement", ""), 150)
            stmt_lines = _wrap(stmt, dyn_wrap)[:3]
            if not stmt_lines:
                stmt_lines = [""]
            for line in stmt_lines:
                ax.text(bx + PADDING, cursor_y, line,
                        ha="left", va="top", fontsize=7.5, color="#222")
                cursor_y -= LINE_H

    # ── Legend ──
    legend_handles = []
    for ntype, cols in NODE_COLORS.items():
        if any(node_data[nid].get("type") == ntype for nid in node_data):
            legend_handles.append(
                mpatches.Patch(facecolor=cols["body"], edgecolor=cols["header"],
                               linewidth=1.5, label=ntype.title())
            )
    legend_handles.append(
        plt.Line2D([0], [0], color="#666666", lw=2.5, marker=">",
                   markersize=10, label="A supports B")
    )
    ax.legend(handles=legend_handles, loc="upper right", fontsize=11,
              frameon=False, title="Node types", title_fontsize=12)

    # ── Title (from metadata if available) ──
    if metadata and metadata.get("chapter_title"):
        ch = metadata.get("chapter", "")
        title = f"Chapter {ch}: {metadata['chapter_title']} — Knowledge Graph"
    elif metadata and metadata.get("title"):
        title = f"{metadata['title']} — Knowledge Graph"
    else:
        title = "Knowledge Graph (DAG)"
    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)

    ax.autoscale()
    ax.margins(0.05)
    try:
        plt.tight_layout()
    except Exception:
        pass  # tight_layout can fail on complex math; savefig still works
    plt.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="white")

    # Also save SVG if requested (for interactive HTML)
    svg_path = str(out_path).replace('.png', '.svg') if str(out_path).endswith('.png') else None
    if svg_path:
        # Set gid on each node rectangle for click handling
        for nid, (bx, by, bw, bh) in node_rect.items():
            # The FancyBboxPatch was already added; we tag it via node_rect for the HTML wrapper
            pass
        plt.savefig(svg_path, format='svg', bbox_inches="tight", facecolor="white")

    plt.close(fig)

    return len(nodes), len(edges), node_rect, node_data


def generate_interactive_html(data, svg_path, html_path):
    """Wrap an SVG figure in an interactive HTML page with click-to-expand detail panel."""
    from visualize_interactive import classify_and_merge
    import json as _json
    from html import escape as _esc

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    metadata = data.get("metadata", {})

    base_nodes, base_edges, step_chains, eq_map, orphan_eqs = classify_and_merge(nodes, edges)

    # Build detail data
    js_details = {}
    for n in base_nodes:
        nid = n["id"]
        js_details[nid] = {
            "name": n.get("name", ""),
            "type": n.get("type", ""),
            "section": n.get("section", ""),
            "statement": n.get("statement", ""),
            "assumptions": n.get("assumptions", []),
            "conclusions": n.get("conclusions", []),
            "proof_info": n.get("proof_info", []),
            "input": n.get("input", []),
            "output": n.get("output", []),
            "steps": [{"id": s["id"], "statement": s.get("statement","")}
                      for s in step_chains.get(nid, [])],
            "equations": [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section","")}
                          for e in eq_map.get(nid, [])],
        }

    js_orphans = [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section","")}
                  for e in orphan_eqs]

    ch = metadata.get("chapter", "")
    ch_title = metadata.get("chapter_title", "")
    title = f"Chapter {ch}: {ch_title}" if ch_title else "Knowledge Graph"

    # Read SVG content
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    # Make node rects clickable by adding onclick via regex
    import re
    def _add_onclick(m):
        nid = m.group(1)
        return 'id="node_' + nid + '" onclick="showDetail(\'' + nid + '\')" style="cursor:pointer;"'
    svg_content = re.sub(r'id="node_([^"]+)"', _add_onclick, svg_content)

    details_json = _json.dumps(js_details, ensure_ascii=True)
    orphans_json = _json.dumps(js_orphans, ensure_ascii=True)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<script>MathJax = {{tex: {{inlineMath: [['$','$']]}}, startup: {{typeset: false}}}};</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; background: #fafafa; }}
#header {{ background: #2c3e50; color: white; padding: 10px 24px; display: flex; align-items: center; justify-content: space-between; }}
#header h1 {{ margin: 0; font-size: 18px; }}
#controls button {{ padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; background: #34495e; color: white; margin-left: 8px; }}
#controls button:hover {{ background: #4a6785; }}
#main {{ display: flex; height: calc(100vh - 44px); }}
#svg-container {{ flex: 1; overflow: auto; padding: 10px; }}
#svg-container svg {{ max-width: 100%; height: auto; }}
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
/* Hover effect on clickable node rects */
[id^="node_"]:hover {{ filter: brightness(0.90); }}
</style>
</head>
<body>
<div id="header">
  <h1>{_esc(title)}</h1>
  <div id="controls">
    <button onclick="resetView()">Reset</button>
  </div>
</div>
<div id="main">
  <div id="svg-container">{svg_content}</div>
  <div id="detail-panel"></div>
</div>
<button id="orphan-toggle" onclick="toggleOrphans()">{len(js_orphans)} orphan eq{"s" if len(js_orphans) != 1 else ""}</button>
<div id="orphan-panel"><h3>Unconnected Equations</h3><div id="orphan-list"></div></div>
<script>
var DETAILS = {details_json};
var ORPHANS = {orphans_json};

function showDetail(nodeId) {{
  var panel = document.getElementById("detail-panel");
  var d = DETAILS[nodeId];
  if (!d) return;
  var h = '<h3 style="margin:0 0 8px;">' + esc(nodeId) + ': ' + esc(d.name || d.type) + '</h3>';
  h += '<div style="font-size:11px;color:#888;margin-bottom:8px;">' + d.type + (d.section ? ' (Sec ' + d.section + ')' : '') + '</div>';
  if (d.statement) h += '<div class="detail-section"><h4>Statement</h4><div style="font-size:12px;">' + esc(d.statement) + '</div></div>';
  if (d.assumptions && d.assumptions.length > 0) {{
    h += '<div class="detail-section"><h4>Assumptions</h4>';
    d.assumptions.forEach(function(a) {{ h += '<div style="font-size:11px;padding:1px 0 1px 8px;">&bull; ' + esc(a) + '</div>'; }});
    h += '</div>';
  }}
  if (d.conclusions && d.conclusions.length > 0) {{
    h += '<div class="detail-section"><h4>Conclusions</h4>';
    d.conclusions.forEach(function(c) {{ h += '<div style="font-size:11px;padding:1px 0 1px 8px;">&bull; ' + esc(c) + '</div>'; }});
    h += '</div>';
  }}
  if (d.proof_info && d.proof_info.length > 0) {{
    h += '<div class="detail-section"><h4>Proof Strategy</h4>';
    d.proof_info.forEach(function(p) {{ h += '<div style="font-size:11px;font-style:italic;">' + esc(typeof p === 'string' ? p : JSON.stringify(p)) + '</div>'; }});
    h += '</div>';
  }}
  if (d.input && d.input.length > 0) {{
    h += '<div class="detail-section"><h4>Input</h4>';
    d.input.forEach(function(x) {{ h += '<div style="font-size:11px;">&bull; ' + esc(x) + '</div>'; }});
    h += '</div>';
  }}
  if (d.output && d.output.length > 0) {{
    h += '<div class="detail-section"><h4>Output</h4>';
    d.output.forEach(function(x) {{ h += '<div style="font-size:11px;">&bull; ' + esc(x) + '</div>'; }});
    h += '</div>';
  }}
  if (d.steps && d.steps.length > 0) {{
    h += '<div class="detail-section"><h4>Proof Steps (' + d.steps.length + ')</h4>';
    d.steps.forEach(function(s, i) {{
      h += '<div class="step-item"><strong>' + s.id + '</strong>: ' + esc(s.statement) + '</div>';
      if (i < d.steps.length - 1) h += '<div class="step-arrow">&#8595;</div>';
    }});
    h += '</div>';
  }}
  if (d.equations && d.equations.length > 0) {{
    h += '<div class="detail-section"><h4>Equations (' + d.equations.length + ')</h4>';
    d.equations.forEach(function(e) {{
      h += '<div class="eq-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>';
    }});
    h += '</div>';
  }}
  panel.innerHTML = h;
  panel.className = "open";
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([panel]).catch(function(){{}});
}}
function resetView() {{
  document.getElementById("detail-panel").className = "";
  document.getElementById("detail-panel").innerHTML = "";
}}
function toggleOrphans() {{
  var p = document.getElementById("orphan-panel");
  if (p.style.display === "block") {{ p.style.display = "none"; return; }}
  var h = "";
  ORPHANS.forEach(function(e) {{ h += '<div class="orphan-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>'; }});
  document.getElementById("orphan-list").innerHTML = h;
  p.style.display = "block";
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([p]).catch(function(){{}});
}}
function esc(t) {{ return t ? t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") : ""; }}
</script>
</body>
</html>"""

    Path(html_path).write_text(html, encoding="utf-8")
    return len(base_nodes)


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="Input JSON annotation file")
    parser.add_argument("output", nargs="?", default=None, help="Output PNG (default: input with .png)")
    parser.add_argument("--resolution", choices=["standard", "full"], default="standard",
                        help="standard: collapse proofs, hide equations. full: show all nodes.")
    parser.add_argument("--html", default=None,
                        help="Also generate interactive HTML (wrapping the SVG with click-to-expand)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".png")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if not nodes:
        print("Error: No 'nodes' found in JSON.")
        sys.exit(1)

    metadata = data.get("metadata", {})
    result = draw_dag(nodes, edges, output_path, metadata=metadata,
                      resolution=args.resolution)
    n_nodes, n_edges = result[0], result[1]
    print(f"DAG saved to {output_path}  ({n_nodes} display nodes, {n_edges} edges, resolution={args.resolution})")

    # Generate interactive HTML if requested
    if args.html:
        svg_path = str(output_path).replace('.png', '.svg')
        n_html = generate_interactive_html(data, svg_path, args.html)
        print(f"Interactive HTML saved to {args.html}  ({n_html} clickable nodes)")


if __name__ == "__main__":
    main()
