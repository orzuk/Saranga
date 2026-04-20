#!/usr/bin/env python3
"""Visualize the alignment between two mathematical knowledge graphs.

Given two paper JSONs and an alignment JSON (with match groups and
unmatched lists), build a "combined graph" internally where each group of
matched nodes collapses into a single merged super-node.  We run the layered
DAG layout from :mod:`visualize_annotation` on that merged graph and reuse
the shared (x, y) positions to render either

    * mode "B" – one combined graph with color-coded node origins, or
    * mode "C" – two side-by-side graphs sharing positions for matched nodes.

Usage
-----
    from visualize_alignment import draw_alignment
    draw_alignment(g1_json, g2_json, align_json, out_png, mode="B")
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import re as _re
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["mathtext.fontset"] = "cm"
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# Reuse everything from the annotation visualizer
from visualize_annotation import (
    NODE_COLORS, DEFAULT_COLOR,
    MIN_BOX_W, MAX_BOX_W, BOX_GAP_X, LEVEL_GAP_Y,
    HEADER_H, LINE_H, PADDING, CHARS_PER_UNIT,
    compute_dag_depth, merge_proofs, _prepare_for_display, _wrap,
    _has_tall_math, _shorten,
)


# ── Alignment data model ────────────────────────────────────────────────────
def _load(path):
    with open(path) as f:
        return json.load(f)


def _detect_match_keys(matches, nodes1_ids, nodes2_ids):
    """Auto-detect which keys in match dicts refer to paper1 vs paper2 nodes."""
    if not matches:
        return "paper_a_nodes", "paper_b_nodes"
    # Collect all candidate keys (ending in _nodes)
    for m in matches:
        candidate_keys = [k for k in m if k.endswith("_nodes")]
        if len(candidate_keys) >= 2:
            # Try each pair and see which maps to which paper's node IDs
            for i, k1 in enumerate(candidate_keys):
                for k2 in candidate_keys[i+1:]:
                    ids1 = set(m.get(k1, []) or [])
                    ids2 = set(m.get(k2, []) or [])
                    if ids1 & nodes1_ids and ids2 & nodes2_ids:
                        return k1, k2
                    if ids2 & nodes1_ids and ids1 & nodes2_ids:
                        return k2, k1
    return "paper_a_nodes", "paper_b_nodes"


def _build_group_map(matches, nodes1_ids, nodes2_ids,
                     key_a=None, key_b=None):
    """Return (group_id_of, groups) where each group is a tuple of
    (set(paper1_ids), set(paper2_ids)).

    Each match in the list becomes ONE group. Nodes appearing in multiple
    matches are assigned to their FIRST match only (no transitive union).
    This preserves the DAG structure: if nodes at different depths appear
    in different matches, they stay as separate nodes rather than being
    collapsed into a single node which would shorten paths.

    Nodes not in any match become singleton groups on their respective side.
    """
    if key_a is None or key_b is None:
        key_a, key_b = _detect_match_keys(matches, nodes1_ids, nodes2_ids)

    group_of: Dict[Tuple[str, str], str] = {}
    group_list: List[Tuple[str, set, set]] = []
    next_gid = 0

    # Process only STRONG matches for merging (exact/analogous).
    # Partial matches are drawn as dashed cross-edges later (not merged).
    STRONG = {"exact", "analogous"}
    for m in matches:
        if m.get("match_type", "").lower() not in STRONG:
            continue
        p1 = [n for n in m.get(key_a, []) if n in nodes1_ids
              and ("1", n) not in group_of]
        p2 = [n for n in m.get(key_b, []) if n in nodes2_ids
              and ("2", n) not in group_of]
        if not p1 or not p2:
            continue  # one-sided match after dedup → skip
        gid = f"G{next_gid}"
        next_gid += 1
        s1, s2 = set(p1), set(p2)
        for nid in s1:
            group_of[("1", nid)] = gid
        for nid in s2:
            group_of[("2", nid)] = gid
        group_list.append((gid, s1, s2))

    # Unmatched nodes → singleton groups
    for nid in sorted(nodes1_ids):
        if ("1", nid) not in group_of:
            gid = f"G{next_gid}"
            next_gid += 1
            group_of[("1", nid)] = gid
            group_list.append((gid, {nid}, set()))
    for nid in sorted(nodes2_ids):
        if ("2", nid) not in group_of:
            gid = f"G{next_gid}"
            next_gid += 1
            group_of[("2", nid)] = gid
            group_list.append((gid, set(), {nid}))

    return group_of, group_list


def _merge_group_node(gid, s1, s2, nbi1, nbi2):
    """Build a synthetic node for a group, picking representative fields."""
    # priority: definition < lemma < theorem < corollary for header color choice
    priority = {"definition": 0, "lemma": 1, "proposition": 2,
                "theorem": 3, "corollary": 4, "algorithm": 5, "claim": 6}
    candidates = [nbi1[n] for n in s1 if n in nbi1] + \
                 [nbi2[n] for n in s2 if n in nbi2]
    if not candidates:
        return {"id": gid, "type": "definition", "name": gid}
    # pick node with highest-priority type for color, shortest name for header
    candidates.sort(key=lambda n: (priority.get(n.get("type", ""), 99),
                                    len(n.get("name") or "")))
    rep = candidates[0]
    ids1 = sorted(s1)
    ids2 = sorted(s2)
    label_ids = " / ".join(ids1 + ids2)
    return {
        "id": gid,
        "type": rep.get("type", "definition"),
        "name": rep.get("name") or label_ids,
        "statement": rep.get("statement", ""),
        "assumptions": rep.get("assumptions", []),
        "conclusions": rep.get("conclusions", []),
        "proof_info": rep.get("proof_info", []),
        "_paper1_ids": ids1,
        "_paper2_ids": ids2,
        "section": rep.get("section", "99"),
    }


def _build_combined(graph1, graph2, alignment):
    """Return (combined_nodes, combined_edges, group_of, group_list)."""
    # First merge proofs inside each paper (so we reuse the same logic)
    n1, e1, _ = merge_proofs(list(graph1["nodes"]), list(graph1["edges"]))
    n2, e2, _ = merge_proofs(list(graph2["nodes"]), list(graph2["edges"]))
    # Drop equations / proof_steps like draw_dag does in "standard" resolution
    hide = {"equation", "proof_step"}
    hidden1 = {n["id"] for n in n1 if n.get("type") in hide}
    hidden2 = {n["id"] for n in n2 if n.get("type") in hide}
    n1 = [n for n in n1 if n["id"] not in hidden1]
    n2 = [n for n in n2 if n["id"] not in hidden2]
    e1 = [e for e in e1 if e["source"] not in hidden1 and e["target"] not in hidden1]
    e2 = [e for e in e2 if e["source"] not in hidden2 and e["target"] not in hidden2]

    nbi1 = {n["id"]: n for n in n1}
    nbi2 = {n["id"]: n for n in n2}

    group_of, group_list = _build_group_map(alignment.get("matches", []),
                                            set(nbi1), set(nbi2))

    combined_nodes = []
    for gid, s1, s2 in group_list:
        combined_nodes.append(_merge_group_node(gid, s1, s2, nbi1, nbi2))

    # combine edges after relabeling to group ids
    seen = set()
    combined_edges = []
    for e in e1:
        s = group_of.get(("1", e["source"]))
        t = group_of.get(("1", e["target"]))
        if s is None or t is None or s == t:
            continue
        key = (s, t, "1")
        if key in seen:
            continue
        seen.add(key)
        combined_edges.append({"source": s, "target": t, "_origin": "1"})
    for e in e2:
        s = group_of.get(("2", e["source"]))
        t = group_of.get(("2", e["target"]))
        if s is None or t is None or s == t:
            continue
        key = (s, t, "2")
        if key in seen:
            continue
        seen.add(key)
        combined_edges.append({"source": s, "target": t, "_origin": "2"})

    return combined_nodes, combined_edges, group_of, group_list, n1, n2, e1, e2


# ── Layout on the combined graph (mirrors draw_dag's positioning logic) ─────
def _line_h(line):
    if _has_tall_math(line):
        return LINE_H * 2.5
    elif "$" in str(line):
        return LINE_H * 1.5
    return LINE_H


def _node_height(n, wrap_w):
    ntype = n.get("type", "")
    MAX_LINES = 3
    if ntype in ("theorem", "lemma", "corollary", "proposition", "claim"):
        a_lines, c_lines, p_lines = [], [], []
        for a in (n.get("assumptions") or [])[:MAX_LINES]:
            a_lines.extend(_wrap(_prepare_for_display(a), wrap_w) or [""])
        for c in (n.get("conclusions") or [])[:MAX_LINES]:
            c_lines.extend(_wrap(_prepare_for_display(c), wrap_w) or [""])
        for ps in (n.get("proof_info") or []):
            if ps:
                p_lines.extend(_wrap(_prepare_for_display(f"Proof: {ps}"), wrap_w))
        ah = sum(_line_h(l) for l in a_lines) or LINE_H
        ch = sum(_line_h(l) for l in c_lines) or LINE_H
        h = HEADER_H + PADDING + ah + PADDING + ch + PADDING
        if p_lines:
            h += len(p_lines) * LINE_H + PADDING
        h += PADDING
    else:
        raw = n.get("statement", "") or n.get("proof_strategy", "") or ""
        stmt_lines = _wrap(_prepare_for_display(raw), wrap_w)[:5] or [""]
        h = HEADER_H + sum(_line_h(l) for l in stmt_lines) + 2 * PADDING
    return h


def _layout(nodes, edges, box_w=4.2, group_info=None):
    """Assign (x, y, w, h) to each node using topological depth and section sort.

    If group_info provided (gid -> (s1, s2)), shared nodes are placed in the
    center of each row, with Candes-Tao-unique nodes on left and Donoho-unique
    on right, so the shared backbone is visually centered.
    """
    depth = compute_dag_depth(nodes, edges)
    levels = defaultdict(list)
    for n in nodes:
        levels[depth[n["id"]]].append(n)

    def _origin_key(n):
        if not group_info:
            return 1
        s1, s2 = group_info.get(n["id"], (set(), set()))
        if s1 and s2:
            return 1  # shared: center
        elif s1:
            return 0  # p1 only: left
        else:
            return 2  # p2 only: right

    def _sec_key(n):
        sec = n.get("section", "99")
        try:
            parts = [float(x) for x in str(sec).split(".")]
        except Exception:
            parts = [99]
        return (_origin_key(n), parts, n["id"])
    for d in levels:
        levels[d].sort(key=_sec_key)

    max_depth = max(levels.keys()) if levels else 0
    wrap_w = max(20, int(box_w * CHARS_PER_UNIT) - 4)

    positions = {}  # id -> (cx, cy, w, h)
    rects = {}      # id -> (x, y, w, h) (bottom-left corner)
    for d in range(max_depth + 1):
        row = levels.get(d, [])
        widths = [box_w for _ in row]
        total = sum(widths) + max(0, len(row) - 1) * BOX_GAP_X
        x = -total / 2
        cy_top = -d * LEVEL_GAP_Y
        for n, w in zip(row, widths):
            h = _node_height(n, wrap_w)
            positions[n["id"]] = (x + w / 2, cy_top - h / 2, w, h)
            rects[n["id"]] = (x, cy_top - h, w, h)
            x += w + BOX_GAP_X
    return positions, rects


# ── Box drawing helpers ─────────────────────────────────────────────────────
def _draw_box(ax, bx, by, bw, bh, node, *, header_color=None, body_color=None,
              border_color=None, border_lw=1.5, alpha=1.0, show_body=True,
              dim_factor=1.0, id_override=None):
    """Render a single node box at (bx, by) with width bw and height bh.

    Reused for both modes.  If ``show_body`` is False, only the header bar
    is drawn (useful for a compact side-by-side).
    """
    ntype = node.get("type", "")
    colors = NODE_COLORS.get(ntype, DEFAULT_COLOR)
    hcol = header_color or colors["header"]
    bcol = body_color or colors["body"]
    ecol = border_color or colors["header"]

    # Body
    rect = FancyBboxPatch(
        (bx, by), bw, bh,
        boxstyle="round,pad=0.05",
        facecolor=bcol, edgecolor=ecol,
        linewidth=border_lw, alpha=alpha,
    )
    ax.add_patch(rect)

    # Header
    header_rect = FancyBboxPatch(
        (bx, by + bh - HEADER_H), bw, HEADER_H,
        boxstyle="round,pad=0.05",
        facecolor=hcol, edgecolor=hcol,
        linewidth=0, alpha=alpha,
    )
    ax.add_patch(header_rect)

    # Header text
    nid_show = id_override if id_override is not None else node["id"]
    name = node.get("name") or ""
    # Strip redundant type prefixes since the ID already encodes the type
    # E.g. "Theorem 1: Near-optimal recovery" -> "Near-optimal recovery"
    name = _re.sub(
        r'^\s*(?:Theorem|Lemma|Corollary|Proposition|Definition|Claim|Proof|Algorithm)'
        r'\s+[\d\.]+\s*[:\-]\s*', '', name, flags=_re.IGNORECASE)
    # Also strip a bare leading "Theorem N/Lemma N" without colon
    name = _re.sub(
        r'^\s*(?:Theorem|Lemma|Corollary|Proposition|Definition|Claim|Proof|Algorithm)'
        r'\s+[\d\.]+\s*', '', name, flags=_re.IGNORECASE)
    max_header_chars = max(18, int(bw * 9) - 2)
    avail = max(6, max_header_chars - len(nid_show) - 2)
    header_text = nid_show if not name else f"{nid_show}: {_shorten(name, min(avail, 40))}"
    fs = 12
    if len(header_text) > max_header_chars:
        fs = max(8, 12 * max_header_chars / len(header_text))
    ax.text(bx + bw / 2, by + bh - HEADER_H / 2, header_text,
            ha="center", va="center", fontsize=fs, fontweight="bold",
            color="white", alpha=alpha)

    if not show_body:
        return

    cursor_y = by + bh - HEADER_H - PADDING
    wrap_w = max(20, int(bw * CHARS_PER_UNIT) - 4)
    ntype = node.get("type", "")
    MAX_LINES = 3
    body_fs = 10.5

    if ntype in ("theorem", "lemma", "corollary", "proposition", "claim"):
        a_lines, c_lines = [], []
        for a in (node.get("assumptions") or [])[:MAX_LINES]:
            a_lines.extend(_wrap(_prepare_for_display(a), wrap_w) or [""])
        for c in (node.get("conclusions") or [])[:MAX_LINES]:
            c_lines.extend(_wrap(_prepare_for_display(c), wrap_w) or [""])
        if not a_lines:
            a_lines = ["(none)"]
        if not c_lines:
            c_lines = ["(none)"]

        ax.text(bx + PADDING, cursor_y, "Assume:",
                ha="left", va="top", fontsize=11, fontweight="bold",
                color="#333", alpha=alpha)
        cursor_y -= LINE_H * 0.7
        for line in a_lines:
            ax.text(bx + PADDING + 0.1, cursor_y, f"\u2022 {line}",
                    ha="left", va="top", fontsize=body_fs, color="#222",
                    fontstyle="italic", alpha=alpha)
            cursor_y -= _line_h(line)
        cursor_y -= PADDING * 0.3
        ax.plot([bx + 0.15, bx + bw - 0.15], [cursor_y + PADDING * 0.2] * 2,
                color=ecol, lw=0.5, alpha=0.4 * alpha)
        ax.text(bx + PADDING, cursor_y, "Conclude:",
                ha="left", va="top", fontsize=11, fontweight="bold",
                color="#333", alpha=alpha)
        cursor_y -= LINE_H * 0.7
        for line in c_lines:
            ax.text(bx + PADDING + 0.1, cursor_y, f"\u2022 {line}",
                    ha="left", va="top", fontsize=body_fs, color="#222", alpha=alpha)
            cursor_y -= _line_h(line)
    else:
        raw = node.get("statement", "") or node.get("proof_strategy", "") or ""
        stmt_lines = _wrap(_prepare_for_display(raw), wrap_w)[:5] or [""]
        for line in stmt_lines:
            ax.text(bx + PADDING, cursor_y, line,
                    ha="left", va="top", fontsize=body_fs, color="#222",
                    alpha=alpha)
            cursor_y -= _line_h(line)


def _draw_edge(ax, src_rect, tgt_rect, color="#333", lw=2.0, style="-",
               alpha=1.0, rad=None):
    sx, sy, sw, sh = src_rect
    tx, ty, tw, th = tgt_rect
    x0 = sx + sw / 2
    y0 = sy  # bottom of source
    x1 = tx + tw / 2
    y1 = ty + th  # top of target
    if rad is None:
        rad = 0.08 if abs(x0 - x1) > 0.5 else 0
    ax.annotate(
        "", xy=(x1, y1), xytext=(x0, y0),
        arrowprops=dict(
            arrowstyle="-|>,head_length=1.0,head_width=0.5",
            color=color, lw=lw, alpha=alpha,
            linestyle=style,
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=3, shrinkB=3,
        ),
    )


# ── Color scheme for alignment — strong contrast ────────────────────────────
# Paper 1 (Candes-Tao): saturated blue
# Paper 2 (Donoho): saturated red
# Shared (matched nodes/edges): saturated purple (= red + blue), emphasized
P1_TINT = {"header": "#1A5490", "body": "#AED6F1"}   # strong blue
P2_TINT = {"header": "#A93226", "body": "#F5B7B1"}   # strong red
SHARED_TINT = {"header": "#5B2C6F", "body": "#E1BEE7"}  # strong purple
SHARED_BORDER = "#4A148C"   # deep purple for emphasis


# ── Mode B: one combined graph ──────────────────────────────────────────────
def _draw_mode_B(combined_nodes, combined_edges, group_list,
                 positions, rects, out_path,
                 paper1_name="Paper A", paper2_name="Paper B"):
    # Figure size
    xs = [bx for (bx, by, bw, bh) in rects.values()]
    xs_r = [bx + bw for (bx, by, bw, bh) in rects.values()]
    ys = [by for (bx, by, bw, bh) in rects.values()]
    ys_t = [by + bh for (bx, by, bw, bh) in rects.values()]
    graph_w = max(xs_r) - min(xs)
    graph_h = max(ys_t) - min(ys)
    figsize = (max(graph_w * 0.9 + 4, 18), max(graph_h * 0.55 + 4, 12))
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.set_aspect("equal")
    ax.axis("off")

    # Build group metadata (shared/p1-only/p2-only)
    group_info = {gid: (s1, s2) for gid, s1, s2 in group_list}

    # Detect shared edges: edges present in BOTH papers (same src, tgt pair
    # where both endpoints are shared merged nodes).
    # Group edges by (src, tgt) pair; if both origins present → shared edge.
    edge_origins = {}  # (src, tgt) -> set of origins
    for e in combined_edges:
        key = (e["source"], e["target"])
        edge_origins.setdefault(key, set()).add(e["_origin"])

    shared_edge_keys = {k for k, origins in edge_origins.items() if len(origins) == 2}

    # Draw non-shared edges first (thin, dimmed), then shared edges on top (thick, bold)
    drawn_shared = set()
    for e in combined_edges:
        src_r = rects.get(e["source"])
        tgt_r = rects.get(e["target"])
        if not src_r or not tgt_r:
            continue
        key = (e["source"], e["target"])
        if key in shared_edge_keys:
            if key in drawn_shared:
                continue  # only draw once
            drawn_shared.add(key)
            # Shared edge: thick purple, emphasized
            _draw_edge(ax, src_r, tgt_r, color=SHARED_BORDER, lw=4.0,
                       alpha=1.0, rad=0.0)
        else:
            if e["_origin"] == "1":
                color = P1_TINT["header"]
                rad = -0.15
            else:
                color = P2_TINT["header"]
                rad = 0.15
            # Non-shared: slightly faded to make shared stand out
            _draw_edge(ax, src_r, tgt_r, color=color, lw=1.8, alpha=0.55, rad=rad)

    # Draw non-shared nodes first (slightly faded), then shared nodes on top
    # (emphasized with thick border, saturated color, full opacity).
    node_by_id = {n["id"]: n for n in combined_nodes}

    # Pass 1: unique nodes (faded)
    for gid, (bx, by, bw, bh) in rects.items():
        node = node_by_id[gid]
        s1, s2 = group_info[gid]
        if s1 and s2:
            continue  # draw shared in pass 2
        if s1:
            hcol, bcol = P1_TINT["header"], P1_TINT["body"]
            border = P1_TINT["header"]
        else:
            hcol, bcol = P2_TINT["header"], P2_TINT["body"]
            border = P2_TINT["header"]
        label = " = ".join(sorted(s1)) if s1 else " = ".join(sorted(s2))
        _draw_box(ax, bx, by, bw, bh, node,
                  header_color=hcol, body_color=bcol,
                  border_color=border, border_lw=1.5,
                  alpha=0.6,  # more faded so shared really stand out
                  id_override=label)

    # Pass 2: shared nodes (emphasized — thick border, full opacity, larger ~10%)
    for gid, (bx, by, bw, bh) in rects.items():
        node = node_by_id[gid]
        s1, s2 = group_info[gid]
        if not (s1 and s2):
            continue
        # Enlarge by 10% — grow outward from center
        grow_w = bw * 0.10
        grow_h = bh * 0.10
        bx2 = bx - grow_w / 2
        by2 = by - grow_h / 2
        bw2 = bw + grow_w
        bh2 = bh + grow_h
        label = " = ".join(sorted(s1)) + " \u2194 " + " = ".join(sorted(s2))
        _draw_box(ax, bx2, by2, bw2, bh2, node,
                  header_color=SHARED_TINT["header"],
                  body_color=SHARED_TINT["body"],
                  border_color=SHARED_BORDER,
                  border_lw=6.0,  # much thicker border
                  alpha=1.0,
                  id_override=label)

    # Legend
    handles = [
        mpatches.Patch(facecolor=SHARED_TINT["body"], edgecolor=SHARED_BORDER,
                       linewidth=5.0, label="Shared nodes (matched)"),
        mpatches.Patch(facecolor=P1_TINT["body"], edgecolor=P1_TINT["header"],
                       linewidth=2.0, label=f"{paper1_name} only"),
        mpatches.Patch(facecolor=P2_TINT["body"], edgecolor=P2_TINT["header"],
                       linewidth=2.0, label=f"{paper2_name} only"),
        plt.Line2D([0], [0], color=SHARED_BORDER, lw=4.0,
                   label="Shared edge (both papers)"),
        plt.Line2D([0], [0], color=P1_TINT["header"], lw=2.0, alpha=0.55,
                   label=f"{paper1_name} edge"),
        plt.Line2D([0], [0], color=P2_TINT["header"], lw=2.0, alpha=0.55,
                   label=f"{paper2_name} edge"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=14,
              frameon=True, framealpha=0.95)

    ax.set_title(f"{paper1_name} (blue) \u2194 {paper2_name} (red)"
                 " — combined knowledge graph",
                 fontsize=18, fontweight="bold", pad=16)
    ax.autoscale()
    ax.margins(0.05)
    try:
        plt.tight_layout()
    except Exception:
        pass
    plt.savefig(str(out_path), dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ── Mode C: side-by-side sharing positions ──────────────────────────────────
def _draw_mode_C(combined_nodes, group_list, group_of,
                 n1, n2, e1, e2, positions, rects, out_path,
                 paper1_name="Paper A", paper2_name="Paper B"):
    # For each original node, its rect comes from the group containing it.
    def rect_for(side, nid):
        gid = group_of.get((side, nid))
        return rects.get(gid) if gid else None

    # Build per-side node lookup
    nbi1 = {n["id"]: n for n in n1}
    nbi2 = {n["id"]: n for n in n2}

    # Figure: two panels side by side
    xs = [bx for (bx, by, bw, bh) in rects.values()]
    xs_r = [bx + bw for (bx, by, bw, bh) in rects.values()]
    ys = [by for (bx, by, bw, bh) in rects.values()]
    ys_t = [by + bh for (bx, by, bw, bh) in rects.values()]
    graph_w = max(xs_r) - min(xs)
    graph_h = max(ys_t) - min(ys)
    panel_fw = max(graph_w * 0.8 + 3, 14)
    fig_h = max(graph_h * 0.55 + 4, 12)
    figsize = (panel_fw * 2, fig_h)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=figsize,
                                   gridspec_kw={"wspace": 0.02})
    for ax in (axL, axR):
        ax.set_aspect("equal")
        ax.axis("off")

    # Build shared status lookup
    shared_gids = {gid for gid, s1, s2 in group_list if s1 and s2}
    group_info = {gid: (s1, s2) for gid, s1, s2 in group_list}

    def draw_side(ax, side, node_by_id, edges, panel_color, panel_name,
                  ghost_node_by_id, ghost_group_info):
        # 1. Draw ghost placeholders for nodes only present on the OTHER side
        #    (so the mental overlay is complete but the ghosts are dim).
        for gid, (gx, gy, gw, gh) in rects.items():
            info_s1, info_s2 = group_info[gid]
            if side == "1":
                local_set = info_s1
            else:
                local_set = info_s2
            if local_set:
                continue
            # Ghost: node exists on other side only
            ghost = ghost_node_by_id.get(gid)
            if not ghost:
                continue
            _draw_box(ax, gx, gy, gw, gh, ghost,
                      header_color="#999999", body_color="#F0F0F0",
                      border_color="#999999", border_lw=1.0,
                      alpha=0.55, show_body=False,
                      id_override="(" + (
                          " = ".join(sorted(info_s1 or info_s2)) + ")"))

        # 2. Draw real edges for this paper
        for e in edges:
            sr = rect_for(side, e["source"])
            tr = rect_for(side, e["target"])
            if not sr or not tr:
                continue
            _draw_edge(ax, sr, tr, color=panel_color, lw=2.2, alpha=0.9)

        # 3. Draw real nodes for this paper
        #    If the node is in a shared group, color it gold; else panel tint.
        for gid, (gx, gy, gw, gh) in rects.items():
            info_s1, info_s2 = group_info[gid]
            local_set = info_s1 if side == "1" else info_s2
            if not local_set:
                continue
            is_shared = gid in shared_gids
            # Find the representative node on THIS side. If the group has
            # multiple nodes on this side, just show a merged label.
            local_ids = sorted(local_set)
            # Pick first node on this side as the visible one
            rep_id = local_ids[0]
            rep_node = node_by_id[rep_id]
            if is_shared:
                hcol, bcol = SHARED_TINT["header"], SHARED_TINT["body"]
                border = SHARED_BORDER
                lw = 3.0
            else:
                hcol, bcol = panel_color_scheme["header"], panel_color_scheme["body"]
                border = panel_color_scheme["header"]
                lw = 1.8
            label = " = ".join(local_ids)
            _draw_box(ax, gx, gy, gw, gh, rep_node,
                      header_color=hcol, body_color=bcol,
                      border_color=border, border_lw=lw,
                      id_override=label)

        ax.set_title(panel_name, fontsize=20, fontweight="bold", pad=12,
                     color=panel_color)

    # Build ghost nodes: for each group, pick a representative from the
    # OTHER side to display when ghosting on this side.
    def pick_ghost(side_set, lookup):
        for nid in sorted(side_set):
            if nid in lookup:
                return lookup[nid]
        return None

    ghost_for_L = {}
    ghost_for_R = {}
    for gid, s1, s2 in group_list:
        if not s1:  # L-panel should show ghost from s2
            ghost_for_L[gid] = pick_ghost(s2, nbi2)
        if not s2:
            ghost_for_R[gid] = pick_ghost(s1, nbi1)

    global panel_color_scheme
    panel_color_scheme = P1_TINT
    draw_side(axL, "1", nbi1, e1, P1_TINT["header"],
              paper1_name, ghost_for_L, group_info)
    panel_color_scheme = P2_TINT
    draw_side(axR, "2", nbi2, e2, P2_TINT["header"],
              paper2_name, ghost_for_R, group_info)

    # Shared axis limits so positions truly align visually
    all_x0 = min(bx for (bx, by, bw, bh) in rects.values())
    all_x1 = max(bx + bw for (bx, by, bw, bh) in rects.values())
    all_y0 = min(by for (bx, by, bw, bh) in rects.values())
    all_y1 = max(by + bh for (bx, by, bw, bh) in rects.values())
    pad_x = (all_x1 - all_x0) * 0.05
    pad_y = (all_y1 - all_y0) * 0.05
    for ax in (axL, axR):
        ax.set_xlim(all_x0 - pad_x, all_x1 + pad_x)
        ax.set_ylim(all_y0 - pad_y, all_y1 + pad_y)

    # Shared legend below
    handles = [
        mpatches.Patch(facecolor=SHARED_TINT["body"], edgecolor=SHARED_BORDER,
                       linewidth=2.5, label="Matched across both papers"),
        mpatches.Patch(facecolor=P1_TINT["body"], edgecolor=P1_TINT["header"],
                       linewidth=1.5, label=f"{paper1_name} only"),
        mpatches.Patch(facecolor=P2_TINT["body"], edgecolor=P2_TINT["header"],
                       linewidth=1.5, label=f"{paper2_name} only"),
        mpatches.Patch(facecolor="#F4F4F4", edgecolor="#BBBBBB",
                       linewidth=1.0, label="Ghost (exists in other paper only)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=13,
               frameon=True, framealpha=0.95, bbox_to_anchor=(0.5, 0.01))

    fig.suptitle(f"{paper1_name} \u2194 {paper2_name} — side-by-side with shared positions",
                 fontsize=20, fontweight="bold", y=0.98)
    try:
        plt.tight_layout(rect=(0, 0.05, 1, 0.96))
    except Exception:
        pass
    plt.savefig(str(out_path), dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ── Public entry point ──────────────────────────────────────────────────────
def _paper_short_name(paper_json: dict) -> str:
    """Extract a short display name from a paper JSON (title or first author)."""
    title = paper_json.get("title", "")
    authors = paper_json.get("authors", [])
    if title:
        # Truncate long titles
        short = title if len(title) <= 40 else title[:37] + "..."
        return short
    if authors:
        first = authors[0] if isinstance(authors[0], str) else str(authors[0])
        return first.split()[-1]  # last name
    return "Paper"


def draw_alignment(graph1_json, graph2_json, alignment_json, output_path,
                   mode: str = "B"):
    """Render an alignment visualization.

    mode: "B" for combined graph, "C" for side-by-side with shared positions.
    """
    g1 = _load(graph1_json)
    g2 = _load(graph2_json)
    align = _load(alignment_json)

    # Extract paper names from metadata
    meta = align.get("metadata", {})
    p1_meta = meta.get("paper_a", {})
    p2_meta = meta.get("paper_b", {})
    paper1_name = p1_meta.get("short_name") or p1_meta.get("title") or _paper_short_name(g1)
    paper2_name = p2_meta.get("short_name") or p2_meta.get("title") or _paper_short_name(g2)
    # Truncate if too long
    if len(paper1_name) > 40:
        paper1_name = paper1_name[:37] + "..."
    if len(paper2_name) > 40:
        paper2_name = paper2_name[:37] + "..."

    combined_nodes, combined_edges, group_of, group_list, \
        n1, n2, e1, e2 = _build_combined(g1, g2, align)

    # Build group_info for layout: gid -> (s1, s2)
    group_info_for_layout = {gid: (s1, s2) for gid, s1, s2 in group_list}
    positions, rects = _layout(combined_nodes, combined_edges, box_w=4.2,
                                group_info=group_info_for_layout)

    mode = mode.upper()
    if mode == "B":
        _draw_mode_B(combined_nodes, combined_edges, group_list,
                     positions, rects, output_path,
                     paper1_name=paper1_name, paper2_name=paper2_name)
    elif mode == "C":
        _draw_mode_C(combined_nodes, group_list, group_of,
                     n1, n2, e1, e2, positions, rects, output_path,
                     paper1_name=paper1_name, paper2_name=paper2_name)
    else:
        raise ValueError(f"Unknown mode: {mode}  (use 'B' or 'C')")
    return output_path


# ── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("graph1_json")
    ap.add_argument("graph2_json")
    ap.add_argument("alignment_json")
    ap.add_argument("output")
    ap.add_argument("--mode", default="B", choices=["B", "C"])
    args = ap.parse_args()
    draw_alignment(args.graph1_json, args.graph2_json, args.alignment_json,
                   args.output, mode=args.mode)
    print(f"wrote {args.output}")
