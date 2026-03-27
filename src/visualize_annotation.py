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
    """Shorten text, but never cut inside a $...$ math expression."""
    if not text:
        return ""
    text = _sanitize_math(text)
    if len(text) <= maxlen:
        return text
    # Find a safe cut point: not inside $...$
    cut = maxlen - 3
    # Count $ signs before cut point; if odd, we're inside math
    n_dollars = text[:cut].count("$")
    if n_dollars % 2 == 1:
        # Inside math — extend to closing $
        next_dollar = text.find("$", cut)
        if next_dollar != -1 and next_dollar < len(text):
            cut = next_dollar + 1
            if cut >= len(text):
                return text
    return text[:cut] + "..."


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
def draw_dag(nodes_raw, edges_raw, out_path, figsize=None, metadata=None):
    """Main entry: draw a layered DAG from student-format nodes/edges."""

    nodes, edges, proof_map = merge_proofs(nodes_raw, edges_raw)
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

        # Main box background
        rect = FancyBboxPatch(
            (bx, by), bw, bh,
            boxstyle="round,pad=0.05",
            facecolor=colors["body"],
            edgecolor=colors["header"],
            linewidth=1.5,
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
    plt.close(fig)

    return len(nodes), len(edges)


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_suffix(".png")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if not nodes:
        print("Error: No 'nodes' found in JSON.")
        sys.exit(1)

    metadata = data.get("metadata", {})
    n_nodes, n_edges = draw_dag(nodes, edges, output_path, metadata=metadata)
    print(f"DAG saved to {output_path}  ({n_nodes} display nodes, {n_edges} edges)")


if __name__ == "__main__":
    main()
