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
    "lemma":       {"header": "#D35400", "body": "#F5CBA7"},
    "corollary":   {"header": "#943126", "body": "#F2D7D5"},
    "algorithm":   {"header": "#2471A3", "body": "#D4E6F1"},
    "equation":    {"header": "#5DADE2", "body": "#EBF5FB"},
    "proposition": {"header": "#B03A2E", "body": "#FADBD8"},
    "proof":       {"header": "#566573", "body": "#D5D8DC"},
    "proof_step":  {"header": "#839192", "body": "#E8E8E8"},
    "claim":       {"header": "#E74C3C", "body": "#FDEDEC"},
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

# Regex-based fixes: commands like \ge that are prefixes of valid commands (\geq)
# Must use regex with word boundary to avoid breaking \geq -> \geqq
import re as _re
_LATEX_REGEX_FIXES = [
    (_re.compile(r'\\ge(?!q)'), r'\\geq'),
    (_re.compile(r'\\le(?!q|ft)'), r'\\leq'),
    (_re.compile(r'\\ne(?!g|wcommand)'), r'\\neq'),
]

def _sanitize_math(text):
    """Replace unsupported LaTeX commands with matplotlib-compatible equivalents."""
    if not text:
        return text
    for old, new in _LATEX_FIXES.items():
        text = text.replace(old, new)
    for pattern, repl in _LATEX_REGEX_FIXES:
        text = pattern.sub(repl, text)
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

    # Attach proof info to parent theorem (reset first to avoid duplication on repeated calls)
    for n in nodes:
        if n.get("type") != "proof":
            node_by_id[n["id"]]["proof_info"] = []

    display_nodes = []
    for n in nodes:
        if n["id"] in proof_map:
            parent_id = proof_map[n["id"]]
            parent = node_by_id[parent_id]
            parent.setdefault("proof_info", [])
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
             resolution="standard", show_legend=True):
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
                arrowstyle="-|>,head_length=1.2,head_width=0.6",
                color="#333333",
                lw=2.5,
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
                ha="center", va="center", fontsize=12, fontweight="bold",
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
                    ha="left", va="top", fontsize=11, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in a_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=10.5, color="#222",
                        fontstyle="italic")
                cursor_y -= LINE_H

            cursor_y -= PADDING * 0.3

            # Divider line
            ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                    color=colors["header"], lw=0.5, alpha=0.4)

            # Conclusions
            ax.text(bx + PADDING, cursor_y, "Conclude:",
                    ha="left", va="top", fontsize=11, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in c_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=10.5, color="#222")
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
                                ha="left", va="top", fontsize=10.5,
                                color="#444", fontstyle="italic")
                        cursor_y -= LINE_H

        elif ntype == "algorithm" and (n.get("input") or n.get("output")):
            # Algorithm with input/output
            in_lines = [_shorten(x, 70) for x in (n.get("input") or ["(none)"])]
            out_lines = [_shorten(x, 70) for x in (n.get("output") or ["(none)"])]

            ax.text(bx + PADDING, cursor_y, "Input:",
                    ha="left", va="top", fontsize=11, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in in_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=10.5, color="#222")
                cursor_y -= LINE_H
            cursor_y -= PADDING * 0.3
            ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                    color=colors["header"], lw=0.5, alpha=0.4)
            ax.text(bx + PADDING, cursor_y, "Output:",
                    ha="left", va="top", fontsize=11, fontweight="bold", color="#333")
            cursor_y -= LINE_H * 0.7
            for line in out_lines:
                ax.text(bx + PADDING + 0.1, cursor_y, f"• {line}",
                        ha="left", va="top", fontsize=10.5, color="#222")
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
                        ha="left", va="top", fontsize=10.5, color="#222")
                cursor_y -= LINE_H

    # ── Ghost nodes (external dependencies) drawn in the SVG but hidden ──
    from link_to_foundation import build_foundation_index, link_paper
    _fg_index = build_foundation_index(None)
    _fg_matches = link_paper(nodes_raw, _fg_index, min_term_len=5)

    # Separate Case 2: references in proof steps (not base nodes)
    _base_ids = set(node_data.keys())
    _ghost_map = {}  # foundation_name -> set of base node IDs that reference it
    for m in _fg_matches:
        if m["node_id"] not in _base_ids:
            # Find parent base node
            parent = m["node_id"]
            for nr in nodes_raw:
                if nr["id"] == parent and nr.get("proves") and nr["proves"] in _base_ids:
                    parent = nr["proves"]
                    break
            if parent in _base_ids:
                _ghost_map.setdefault(m["foundation_name"], set()).add(parent)
    _ghost_map = {k: list(v) for k, v in _ghost_map.items()}

    if _ghost_map and node_rect:
        # Position ghost nodes in a row ABOVE the top layer
        all_tops = [by + bh for (bx, by, bw, bh) in node_rect.values()]
        ghost_y_top = max(all_tops) + LEVEL_GAP_Y * 0.8
        ghost_w = MIN_BOX_W * 1.1
        ghost_h = HEADER_H + LINE_H * 1.5 + PADDING
        ghost_names = sorted(_ghost_map.keys())
        total_ghost_w = len(ghost_names) * ghost_w + (len(ghost_names) - 1) * BOX_GAP_X * 0.5
        ghost_start_x = -total_ghost_w / 2

        ghost_rects = {}  # name -> (x, y, w, h)
        for gi, gname in enumerate(ghost_names):
            gx = ghost_start_x + gi * (ghost_w + BOX_GAP_X * 0.5)
            gy = ghost_y_top

            # Draw ghost node box with header (like regular nodes)
            grect = FancyBboxPatch(
                (gx, gy - ghost_h), ghost_w, ghost_h,
                boxstyle="round,pad=0.05",
                facecolor="#E8E8E8", edgecolor="#777777",
                linewidth=1.5, linestyle="dashed",
                gid=f"ghost_box_{gi}",
            )
            ax.add_patch(grect)
            # Header bar
            gheader = FancyBboxPatch(
                (gx, gy - HEADER_H), ghost_w, HEADER_H,
                boxstyle="round,pad=0.05",
                facecolor="#777777", edgecolor="#777777",
                linewidth=0,
                gid=f"ghost_header_{gi}",
            )
            ax.add_patch(gheader)
            # Name in header
            short_name = gname if len(gname) <= 22 else gname[:19] + "..."
            ax.text(gx + ghost_w / 2, gy - HEADER_H / 2, short_name,
                    ha="center", va="center", fontsize=10, fontweight="bold",
                    color="white", gid=f"ghost_text_{gi}")
            # References below header
            refs_str = "→ " + ", ".join(_ghost_map[gname])
            ax.text(gx + ghost_w / 2, gy - HEADER_H - LINE_H * 0.7, refs_str,
                    ha="center", va="center", fontsize=8.5, color="#555",
                    gid=f"ghost_refs_{gi}")

            ghost_rects[gname] = (gx, gy - ghost_h, ghost_w, ghost_h)

            # Draw dashed edges to target nodes
            from matplotlib.patches import FancyArrowPatch
            for ti, target_id in enumerate(_ghost_map[gname]):
                if target_id in node_rect:
                    tx, ty, tw, th = node_rect[target_id]
                    arrow = FancyArrowPatch(
                        (gx + ghost_w / 2, gy - ghost_h),
                        (tx + tw / 2, ty + th),
                        arrowstyle="-|>,head_length=0.8,head_width=0.35",
                        color="#999999", lw=1.5,
                        linestyle="dashed",
                        connectionstyle="arc3,rad=0.05",
                        shrinkA=3, shrinkB=3,
                        gid=f"ghost_edge_{gi}_{ti}",
                    )
                    ax.add_patch(arrow)

    # ── Misc/Orphan equations box ──
    # Count orphan equations from the FULL node list (before filtering)
    all_eq_nodes = [n for n in nodes_raw if n.get("type") == "equation"]
    orphan_eqs = [n for n in all_eq_nodes if n.get("context") == "orphan" or not n.get("context")]
    # Also count equations not connected to any displayed node
    displayed_ids = set(node_data.keys())
    edge_targets = set()
    for e in edges_raw:
        if e["source"] in displayed_ids:
            edge_targets.add(e["target"])
        if e["target"] in displayed_ids:
            edge_targets.add(e["source"])
    truly_orphan = [n for n in all_eq_nodes if n["id"] not in edge_targets and n["id"] not in displayed_ids]
    n_orphan = len(set(n["id"] for n in orphan_eqs + truly_orphan))

    if n_orphan > 0 and node_rect:
        # Position: same height as the bottom layer, to the right
        misc_w = MAX_BOX_W
        misc_h = HEADER_H + LINE_H + 2 * PADDING
        all_bottoms = [by for (bx, by, bw, bh) in node_rect.values()]
        all_rights = [bx + bw for (bx, by, bw, bh) in node_rect.values()]
        # Find the bottom-most row's top position
        bottom_y = min(all_bottoms)
        bottom_tops = [by + bh for (bx, by, bw, bh) in node_rect.values() if abs(by - bottom_y) < LEVEL_GAP_Y * 0.3]
        misc_top = max(bottom_tops) if bottom_tops else min(all_bottoms) + 1.0
        misc_y = misc_top - misc_h
        misc_x = max(all_rights) + BOX_GAP_X

        misc_rect = FancyBboxPatch(
            (misc_x, misc_y), misc_w, misc_h,
            boxstyle="round,pad=0.05",
            facecolor="#F2E6D9",
            edgecolor="#795548",
            linewidth=1.5,
            gid="node___orphan__",
        )
        ax.add_patch(misc_rect)

        header_rect = FancyBboxPatch(
            (misc_x, misc_y + misc_h - HEADER_H), misc_w, HEADER_H,
            boxstyle="round,pad=0.05",
            facecolor="#795548",
            edgecolor="#795548",
            linewidth=0,
        )
        ax.add_patch(header_rect)
        ax.text(misc_x + misc_w / 2, misc_y + misc_h - HEADER_H / 2,
                f"Misc ({n_orphan} equations)",
                ha="center", va="center", fontsize=12, fontweight="bold", color="white")
        ax.text(misc_x + misc_w / 2, misc_y + PADDING + LINE_H / 2,
                "Unconnected equations",
                ha="center", va="center", fontsize=10.5, color="#555")

    # ── Legend ──
    if show_legend:
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
        ax.legend(handles=legend_handles, loc="upper right", fontsize=13,
                  frameon=False, title="Node types", title_fontsize=14)

    # ── Title (from metadata if available) ──
    if metadata and metadata.get("chapter_title"):
        ch = metadata.get("chapter", "")
        title = f"Chapter {ch}: {metadata['chapter_title']} — Knowledge Graph"
    elif metadata and metadata.get("title"):
        title = f"{metadata['title']} — Knowledge Graph"
    else:
        title = "Knowledge Graph (DAG)"
    ax.set_title(title, fontsize=18, fontweight="bold", pad=15)

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

    # Foundation graph linking
    from link_to_foundation import build_foundation_index, link_paper, WELL_KNOWN
    index = build_foundation_index(None)  # built-in index only
    matches = link_paper(nodes, index)

    # Separate Case 1 (repeat: node exists) vs Case 2 (ghost: referenced but no node)
    base_ids = {n["id"] for n in base_nodes}
    case1_matches = {}  # node_id -> list of foundation names
    case2_ghosts = {}   # foundation_name -> list of node_ids that reference it
    for m in matches:
        if m["node_id"] in base_ids:
            # Case 1: existing node matches foundation
            case1_matches.setdefault(m["node_id"], []).append(m["foundation_name"])
        else:
            # Case 2: match in a proof step or equation, not a base node
            # Find which base node this proof step belongs to
            parent = m["node_id"]
            # Check if it's a proof step — find its parent theorem
            for n in nodes:
                if n["id"] == parent and n.get("parent_proof"):
                    # Find which theorem the proof proves
                    for n2 in nodes:
                        if n2["id"] == n["parent_proof"] and n2.get("proves"):
                            parent = n2["proves"]
                            break
                    break
                if n["id"] == parent and n.get("proves"):
                    parent = n["proves"]
                    break
            if parent in base_ids:
                case2_ghosts.setdefault(m["foundation_name"], set()).add(parent)

    # Convert sets to lists for JSON
    case2_ghosts = {k: list(v) for k, v in case2_ghosts.items()}

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
            "equations": [{"id": e["id"], "statement": e.get("statement",""), "section": e.get("section",""),
                          "context": e.get("context",""), "parent_step": e.get("parent_step","")}
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

    # Add foundation links to detail data
    for nid, fnames in case1_matches.items():
        if nid in js_details:
            js_details[nid]["foundation_links"] = list(set(fnames))

    details_json = _json.dumps(js_details, ensure_ascii=True)
    orphans_json = _json.dumps(js_orphans, ensure_ascii=True)
    ghosts_json = _json.dumps(case2_ghosts, ensure_ascii=True)
    case1_json = _json.dumps(case1_matches, ensure_ascii=True)

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
#header .hint {{ font-size: 12px; color: #aaa; font-style: italic; margin-left: 12px; }}
#controls button {{ padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; background: #34495e; color: white; margin-left: 8px; }}
#controls button:hover {{ background: #4a6785; }}
.legend {{ display: flex; gap: 14px; flex-wrap: wrap; padding: 8px 24px; background: #f5f5f5; border-bottom: 1px solid #eee; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 12px; }}
.legend-color {{ width: 16px; height: 16px; border-radius: 3px; border: 1.5px solid #777; }}
#main {{ display: flex; height: calc(100vh - 82px); }}
#svg-container {{ flex: 1; overflow: auto; padding: 10px; cursor: grab; }}
#svg-container svg {{ transform-origin: 0 0; }}
#detail-panel {{ width: 0; overflow-y: auto; background: white; border-left: 1px solid #ddd; transition: width 0.3s; }}
#detail-panel.open {{ width: 380px; padding: 16px; }}
.detail-section {{ margin-bottom: 12px; }}
.detail-section h4 {{ margin: 0 0 6px; color: #444; font-size: 13px; text-transform: uppercase; }}
.step-item {{ background: #f0f0f0; border-left: 3px solid #839192; padding: 6px 10px; font-size: 13px; margin-bottom: 4px; border-radius: 0 3px 3px 0; }}
.step-arrow {{ text-align: center; color: #aaa; font-size: 14px; }}
.eq-item {{ background: #d4e6f1; border-left: 3px solid #5dade2; padding: 6px 10px; font-size: 13px; margin-bottom: 4px; border-radius: 0 3px 3px 0; }}
.orphan-item {{ background: #fef9e7; border-left: 3px solid #f39c12; padding: 6px 10px; font-size: 13px; margin-bottom: 4px; }}
#orphan-panel {{ position: fixed; bottom: 16px; right: 16px; background: white; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); max-width: 350px; max-height: 400px; overflow-y: auto; display: none; padding: 12px; z-index: 100; }}
#orphan-toggle {{ display: none; }}
/* Hover effect on clickable node rects */
[id^="node_"]:hover {{ filter: brightness(0.90); }}
.ghost-node {{ display: inline-block; margin: 4px 8px; padding: 8px 14px; background: #E0E0E0; border: 1.5px solid #757575; border-radius: 5px; font-size: 13px; color: #333; cursor: pointer; vertical-align: top; white-space: normal; max-width: 220px; }}
.ghost-node:hover {{ background: #BDBDBD; }}
.ghost-node .ghost-label {{ font-weight: bold; font-size: 13px; }}
.ghost-node .ghost-refs {{ font-size: 11px; color: #666; margin-top: 3px; }}
</style>
</head>
<body>
<div id="header">
  <h1>{_esc(title)}<span class="hint">— click nodes for detailed description</span></h1>
  <div id="controls">
    <button onclick="resetView()">Reset</button>
    <button onclick="zoomIn()">Zoom +</button>
    <button onclick="zoomOut()">Zoom -</button>
    <button onclick="zoomFit()">Fit</button>
  </div>
</div>
<div class="legend">
  <div class="legend-item"><div class="legend-color" style="background:#D5F5E3;border-color:#27AE60;"></div>Definition</div>
  <div class="legend-item"><div class="legend-color" style="background:#FADBD8;border-color:#C0392B;"></div>Theorem</div>
  <div class="legend-item"><div class="legend-color" style="background:#F5CBA7;border-color:#D35400;"></div>Lemma</div>
  <div class="legend-item"><div class="legend-color" style="background:#F2D7D5;border-color:#943126;"></div>Corollary</div>
  <div class="legend-item"><div class="legend-color" style="background:#D4E6F1;border-color:#2471A3;"></div>Algorithm</div>
  <div class="legend-item" style="margin-left:12px;"><span style="font-size:18px;color:#555;">&#8594;</span> A supports B</div>
  <div class="legend-item" style="margin-left:12px;"><button onclick="toggleGhosts()" id="ghost-btn" style="padding:4px 12px;border:1.5px solid #757575;border-radius:4px;background:#E0E0E0;cursor:pointer;font-size:12px;color:#333;">Show external dependencies</button></div>
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
var GHOSTS = {ghosts_json};
var CASE1 = {case1_json};

var _lastDetailNode = null;
function showDetail(nodeId) {{
  var panel = document.getElementById("detail-panel");
  // Toggle: click same node again to close
  if (_lastDetailNode === nodeId && panel.className === "open") {{
    panel.className = "";
    panel.innerHTML = "";
    _lastDetailNode = null;
    return;
  }}
  _lastDetailNode = nodeId;
  // Special case: orphan/misc node
  if (nodeId === '__orphan__') {{
    var h = '<h3 style="margin:0 0 8px;font-size:16px;">Misc: Unconnected Equations</h3>';
    h += '<div style="font-size:12px;color:#888;margin-bottom:10px;">Equations not linked to any theorem or proof step</div>';
    ORPHANS.forEach(function(e) {{
      h += '<div class="eq-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>';
    }});
    if (ORPHANS.length === 0) h += '<div style="color:#888;">No orphan equations.</div>';
    panel.innerHTML = h;
    panel.className = "open";
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([panel]).catch(function(){{}});
    return;
  }}
  var d = DETAILS[nodeId];
  if (!d) return;
  var h = '<h3 style="margin:0 0 8px;font-size:16px;">' + esc(nodeId) + ': ' + esc(d.name || d.type) + '</h3>';
  h += '<div style="font-size:12px;color:#888;margin-bottom:4px;">' + d.type + (d.section ? ' (Sec ' + d.section + ')' : '') + '</div>';
  // Foundation graph link badge (Case 1: known result)
  if (d.foundation_links && d.foundation_links.length > 0) {{
    h += '<div style="display:inline-block;padding:2px 8px;background:#E3F2FD;border:1px solid #2471A3;border-radius:3px;font-size:11px;color:#2471A3;margin-bottom:8px;">&#128218; Known result: ' + d.foundation_links.map(esc).join(', ') + '</div>';
  }}
  // Pre-build equation maps by context
  var eqsByCtx = {{statement:[], assumption:[], conclusion:[], orphan:[]}};
  var eqsByStep = {{}};
  if (d.equations) {{
    d.equations.forEach(function(e) {{
      if (e.parent_step) {{
        if (!eqsByStep[e.parent_step]) eqsByStep[e.parent_step] = [];
        eqsByStep[e.parent_step].push(e);
      }} else if (e.context && eqsByCtx[e.context]) {{
        eqsByCtx[e.context].push(e);
      }} else {{
        eqsByCtx.orphan.push(e);
      }}
    }});
  }}
  var eqTag = function(e) {{ return '<span style="color:#2471A3;font-size:11px;"> (' + e.id + ')</span>'; }};
  var eqBlock = function(e) {{ return '<div style="margin:2px 0 2px 12px;padding:3px 8px;background:#EBF5FB;border-left:2px solid #5DADE2;font-size:12px;">' + esc(e.id) + ': ' + esc(e.statement) + '</div>'; }};

  // Statement + inline statement equations
  if (d.statement) {{
    h += '<div class="detail-section"><h4>Statement</h4><div style="font-size:14px;">' + esc(d.statement) + '</div>';
    eqsByCtx.statement.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  // Assumptions + inline assumption equations
  if ((d.assumptions && d.assumptions.length > 0) || eqsByCtx.assumption.length > 0) {{
    h += '<div class="detail-section"><h4>Assumptions</h4>';
    if (d.assumptions) d.assumptions.forEach(function(a) {{ h += '<div style="font-size:13px;padding:2px 0 2px 10px;">&bull; ' + esc(a) + '</div>'; }});
    eqsByCtx.assumption.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  // Conclusions + inline conclusion equations
  if ((d.conclusions && d.conclusions.length > 0) || eqsByCtx.conclusion.length > 0) {{
    h += '<div class="detail-section"><h4>Conclusions</h4>';
    if (d.conclusions) d.conclusions.forEach(function(c) {{ h += '<div style="font-size:13px;padding:2px 0 2px 10px;">&bull; ' + esc(c) + '</div>'; }});
    eqsByCtx.conclusion.forEach(function(e) {{ h += eqBlock(e); }});
    h += '</div>';
  }}
  // Proof strategy
  if (d.proof_info && d.proof_info.length > 0) {{
    h += '<div class="detail-section"><h4>Proof Strategy</h4>';
    d.proof_info.forEach(function(p) {{
      if (Array.isArray(p)) {{
        p.forEach(function(item) {{ h += '<div style="font-size:13px;font-style:italic;">&bull; ' + esc(item) + '</div>'; }});
      }} else {{
        h += '<div style="font-size:13px;font-style:italic;">' + esc(p) + '</div>';
      }}
    }});
    h += '</div>';
  }}
  // Algorithm input/output
  if (d.input && d.input.length > 0) {{
    h += '<div class="detail-section"><h4>Input</h4>';
    d.input.forEach(function(x) {{ h += '<div style="font-size:13px;">&bull; ' + esc(x) + '</div>'; }});
    h += '</div>';
  }}
  if (d.output && d.output.length > 0) {{
    h += '<div class="detail-section"><h4>Output</h4>';
    d.output.forEach(function(x) {{ h += '<div style="font-size:13px;">&bull; ' + esc(x) + '</div>'; }});
    h += '</div>';
  }}
  // Proof steps with inline equations
  if (d.steps && d.steps.length > 0) {{
    h += '<div class="detail-section"><h4>Proof Steps (' + d.steps.length + ')</h4>';
    d.steps.forEach(function(s, i) {{
      h += '<div class="step-item"><strong>' + s.id + '</strong>: ' + esc(s.statement);
      if (eqsByStep[s.id]) {{
        eqsByStep[s.id].forEach(function(e) {{ h += eqBlock(e); }});
      }}
      h += '</div>';
      if (i < d.steps.length - 1) h += '<div class="step-arrow">&#8595;</div>';
    }});
    h += '</div>';
  }}
  // Orphan equations (collapsible)
  if (eqsByCtx.orphan.length > 0) {{
    h += '<div class="detail-section"><h4 style="cursor:pointer;" onclick="toggleEqPanel(this)">Unplaced Equations (' + eqsByCtx.orphan.length + ') &#9660;</h4>';
    h += '<div style="display:none;">';
    eqsByCtx.orphan.forEach(function(e) {{
      h += '<div class="eq-item"><strong>' + e.id + '</strong> (Sec ' + e.section + '): ' + esc(e.statement) + '</div>';
    }});
    h += '</div></div>';
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
// Ghost nodes (external dependencies)
function toggleGhosts() {{
  var svgEl = document.querySelector("#svg-container svg");
  var ghostEls = svgEl ? svgEl.querySelectorAll('[id^="ghost_"]') : [];
  var btn = document.getElementById("ghost-btn");
  var isShowing = btn.dataset.showing === "1";
  if (!isShowing) {{
    btn.dataset.showing = "1";
    btn.textContent = "Hide external dependencies";
    ghostEls.forEach(function(el) {{ el.style.display = ""; }});
  }} else {{
    btn.dataset.showing = "0";
    btn.textContent = "Show external dependencies";
    ghostEls.forEach(function(el) {{ el.style.display = "none"; }});
  }}
}}
function showGhostDetail(nameOrEl) {{
  var name = (typeof nameOrEl === 'string') ? nameOrEl : nameOrEl;
  var panel = document.getElementById("detail-panel");
  var refs = GHOSTS[name] || [];
  var h = '<h3 style="margin:0 0 8px;font-size:16px;">' + esc(name) + '</h3>';
  h += '<div style="font-size:12px;color:#795548;margin-bottom:10px;">External dependency (from Foundation Graph)</div>';
  h += '<div class="detail-section"><h4>Referenced by</h4>';
  refs.forEach(function(nid) {{
    var d = DETAILS[nid];
    var label = d ? (nid + ': ' + (d.name || d.type)) : nid;
    h += '<div style="font-size:13px;padding:2px 0 2px 10px;cursor:pointer;color:#2471A3;" data-nid="' + nid + '" onclick="showDetail(this.dataset.nid)">&bull; ' + esc(label) + '</div>';
  }});
  h += '</div>';
  panel.innerHTML = h;
  panel.className = "open";
}}


function toggleEqPanel(el) {{
  var panel = el.nextElementSibling;
  if (panel) panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}}
function esc(t) {{ return t ? t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;") : ""; }}

// Hide ghost elements on load (wait for SVG to render)
window.addEventListener("load", function() {{
  var svgEl = document.querySelector("#svg-container svg");
  if (svgEl) {{
    // Hide all ghost elements (boxes, headers, text, refs, edges)
    var all = svgEl.querySelectorAll('[id^="ghost_"]');
    all.forEach(function(el) {{ el.style.display = "none"; }});
  }}
}});

var currentZoom = 1.0;
var svgEl = document.querySelector("#svg-container svg");
function applyZoom() {{
  if (svgEl) svgEl.style.transform = "scale(" + currentZoom + ")";
}}
function zoomIn() {{ currentZoom = Math.min(currentZoom * 1.3, 5.0); applyZoom(); }}
function zoomOut() {{ currentZoom = Math.max(currentZoom / 1.3, 0.2); applyZoom(); }}
function zoomFit() {{ currentZoom = 1.0; applyZoom(); }}

// Mouse wheel zoom on the SVG container
document.getElementById("svg-container").addEventListener("wheel", function(e) {{
  e.preventDefault();
  if (e.deltaY < 0) {{ currentZoom = Math.min(currentZoom * 1.1, 5.0); }}
  else {{ currentZoom = Math.max(currentZoom / 1.1, 0.2); }}
  applyZoom();
}}, {{passive: false}});
</script>
</body>
</html>"""

    Path(html_path).write_text(html, encoding="utf-8")
    return len(base_nodes)


# ── CLI ─────────────────────────────────────────────────────────────────────
def resolve_paths(args_list):
    """Resolve a list of paths/globs/directories to JSON files."""
    import glob as _glob
    files = []
    for arg in args_list:
        p = Path(arg)
        if p.is_dir():
            files.extend(sorted(p.glob("*.json")))
        elif "*" in arg or "?" in arg:
            files.extend(sorted(Path(m) for m in _glob.glob(arg)))
        elif p.is_file():
            files.append(p)
        else:
            print(f"WARNING: '{arg}' not found, skipping.")
    return files


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Visualize knowledge graph annotation(s) as DAG images.",
        epilog="Examples:\n"
               "  python visualize_annotation.py annotation.json\n"
               "  python visualize_annotation.py papers/gold/\n"
               "  python visualize_annotation.py 'papers/gold/paper*.json'\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="+", help="JSON file(s), directory, or glob pattern")
    parser.add_argument("-o", "--output", default=None, help="Output PNG path (single file only)")
    parser.add_argument("--resolution", choices=["standard", "full"], default="standard",
                        help="standard: collapse proofs, hide equations. full: show all nodes.")
    parser.add_argument("--html", action="store_true",
                        help="Also generate interactive HTML for each file")
    parser.add_argument("--html-only", action="store_true",
                        help="Generate only interactive HTML (no PNG)")
    args = parser.parse_args()

    files = resolve_paths(args.input)
    if not files:
        print("No JSON files found.")
        sys.exit(1)

    do_html = args.html or args.html_only
    do_png = not args.html_only

    for i, input_path in enumerate(files):
        if len(files) > 1:
            print(f"\n[{i+1}/{len(files)}] {input_path.name}")

        if args.output and len(files) == 1:
            output_path = Path(args.output)
        else:
            output_path = input_path.with_suffix(".png")

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        if not nodes:
            print(f"  WARNING: No 'nodes' found in {input_path.name}, skipping.")
            continue

        metadata = data.get("metadata", {})

        if do_png:
            result = draw_dag(nodes, edges, output_path, metadata=metadata,
                              resolution=args.resolution)
            n_nodes, n_edges = result[0], result[1]
            print(f"  -> {output_path} ({n_nodes} nodes, {n_edges} edges)")

        if do_html:
            import os
            svg_only_path = str(output_path).replace('.png', '_nolegend.svg')
            draw_dag(nodes, edges, svg_only_path.replace('.svg', '.png'), metadata=metadata,
                     resolution=args.resolution, show_legend=False)
            html_path = input_path.with_suffix(".html")
            n_html = generate_interactive_html(data, svg_only_path, str(html_path))
            for tmp in [svg_only_path, svg_only_path.replace('.svg', '.png')]:
                if os.path.exists(tmp):
                    os.remove(tmp)
            print(f"  -> {html_path} ({n_html} clickable nodes)")

    if len(files) > 1:
        print(f"\nDone: {len(files)} graphs generated.")


if __name__ == "__main__":
    main()
