import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import networkx as nx
import math

from math_classes import PaperGraph  # type: ignore


def _load_paper_like(
    paper: Union[PaperGraph, str, Path, Dict[str, Any]]
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Normalize different inputs to (objects, relations).

    Supports:
      - PaperGraph instance (with .objects and .relations)
      - path/str to a JSON file produced by PaperGraph.to_dict()
      - already-loaded dict with 'objects' / 'relations'
    """
    if isinstance(paper, dict) and "objects" in paper and "relations" in paper:
        return paper["objects"], paper["relations"]

    if isinstance(paper, (str, Path)):
        path = Path(paper)
        with path.open("r", encoding="utf8") as f:
            data = json.load(f)
        return data["objects"], data["relations"]

    # PaperGraph-like
    if hasattr(paper, "objects") and hasattr(paper, "relations"):
        objects_dict: Dict[str, Dict[str, Any]] = {}
        for oid, obj in paper.objects.items():
            d = getattr(obj, "to_dict", lambda: obj.__dict__)()
            objects_dict[oid] = d
        relations_list: List[Dict[str, Any]] = []
        for r in paper.relations:
            if isinstance(r, dict):
                relations_list.append(r)
            else:
                relations_list.append(
                    {
                        "source_id": getattr(r, "source_id"),
                        "target_id": getattr(r, "target_id"),
                        "relation_type": getattr(r, "relation_type"),
                        "category": getattr(r, "category", None),
                        "directed": getattr(r, "directed", True),
                        "symmetric": getattr(r, "symmetric", False),
                        "metadata": getattr(r, "metadata", {}),
                    }
                )
        return objects_dict, relations_list

    raise TypeError(f"Unsupported paper type: {type(paper)}")


def paper_to_network(
    paper: Union[PaperGraph, str, Path, Dict[str, Any]],
    out_png: Union[str, Path],
    node_label_attr: str = "label",
    include_kinds: Optional[List[str]] = None,
    include_relation_types: Optional[List[str]] = None,
    figsize: Tuple[float, float] = (16, 10),
) -> nx.DiGraph:
    """
    Visualize a paper as a network with theorem-boxes.

    - Every theorem/lemma/proposition/claim/conjecture/problem is drawn as
      a rectangular "big node".
    - Its proof(s) and key supporting results live inside that rectangle.
    - Definitions occupy a separate band at the top.
    - Relation types are rendered with different edge styles.

    include_kinds / include_relation_types are accepted for backwards
    compatibility; currently they are used as filters on the final graph.
    """

    objects, relations = _load_paper_like(paper)

    # Optional filtering by kind
    if include_kinds is not None:
        objects = {oid: od for oid, od in objects.items() if od.get("kind") in include_kinds}

    # Optional filtering by relation_type
    if include_relation_types is not None:
        relations = [r for r in relations if r.get("relation_type") in include_relation_types]

    CONTAINER_KINDS = {
        "theorem",
        "lemma",
        "proposition",
        "corollary",
        "claim",
        "conjecture",
        "problem",
    }
    DEF_KIND = "definition"
    PROOF_KIND = "proof"

    # normalize 'kind'
    for oid, od in objects.items():
        if not od.get("kind"):
            k = od.get("__class__")
        else:
            k = od["kind"]
        if k in (
            "TheoremLike",
            "Theorem",
            "Lemma",
            "Proposition",
            "Corollary",
            "Claim",
            "Conjecture",
            "Problem",
        ):
            env = od.get("env_name")
            if env in CONTAINER_KINDS:
                k = env
            else:
                k = "theorem"
        od["kind"] = k

    # ------------------ which nodes live in which theorem box? ------------------
    box_children: Dict[str, List[str]] = {
        oid: [] for oid, od in objects.items() if od["kind"] in CONTAINER_KINDS
    }

    # explicit 'has_part' children (proofs, equations, etc.)
    for r in relations:
        if r.get("relation_type") == "has_part" and r["source_id"] in box_children:
            if r["target_id"] in objects:  # filtered-out nodes might be missing
                box_children[r["source_id"]].append(r["target_id"])

    # proofs -> which theorem do they belong to?
    proof_parent: Dict[str, str] = {}
    for box_id, kids in box_children.items():
        for kid in kids:
            if objects.get(kid, {}).get("kind") == PROOF_KIND:
                proof_parent[kid] = box_id

    # lemmas/props used inside proofs get drawn inside the theorem box too
    for r in relations:
        if r.get("relation_type") != "uses":
            continue
        src = r["source_id"]
        tgt = r["target_id"]
        if src in proof_parent and objects.get(tgt, {}).get("kind") in CONTAINER_KINDS:
            box_id = proof_parent[src]
            if tgt not in box_children[box_id]:
                box_children[box_id].append(tgt)

    # ensure the container itself is inside its own box
    for box_id in box_children:
        if box_id not in box_children[box_id]:
            box_children[box_id].insert(0, box_id)

    # ------------------ group-level graph: boxes + definitions ------------------
    group_nodes: List[str] = list(box_children.keys()) + [
        oid for oid, od in objects.items() if od["kind"] == DEF_KIND
    ]

    group_G = nx.DiGraph()
    group_G.add_nodes_from(group_nodes)
    for r in relations:
        if r.get("relation_type") == "uses":
            s, t = r["source_id"], r["target_id"]
            if s in group_nodes and t in group_nodes:
                group_G.add_edge(s, t)

    if not group_G.nodes:
        group_G.add_nodes_from(group_nodes)

    group_pos = nx.spring_layout(
        group_G, seed=42, k=1.0 / max(len(group_nodes), 1)
    )

    # lift definitions to a top band
    if group_nodes:
        max_y = max(y for (_, y) in group_pos.values())
        y_def = max_y + 0.5
        for oid in group_nodes:
            if objects.get(oid, {}).get("kind") == DEF_KIND:
                x, _ = group_pos[oid]
                group_pos[oid] = (x, y_def)

    # ------------------ positions for all nodes ------------------
    pos: Dict[str, Tuple[float, float]] = {}

    # nodes inside boxes: small grid around the box center
    for box_id, kids in box_children.items():
        if not kids:
            continue
        cx, cy = group_pos.get(box_id, (0.0, 0.0))
        n = len(kids)
        cols = min(3, max(1, int(round(math.sqrt(n)))))
        rows = int(math.ceil(n / cols))
        dx, dy = 0.08, 0.10
        for idx, oid in enumerate(kids):
            if oid not in objects:
                continue
            r_ = idx // cols
            c_ = idx % cols
            x = cx + (c_ - (cols - 1) / 2) * dx
            y = cy - (r_ - (rows - 1) / 2) * dy
            pos[oid] = (x, y)

    # group nodes not already placed (definitions, box centers)
    for oid in group_nodes:
        if oid not in pos and oid in objects:
            pos[oid] = group_pos.get(oid, (0.0, 0.0))

    # any remaining nodes (rare) → origin cluster
    for oid in objects.keys():
        if oid not in pos:
            pos[oid] = (0.0, 0.0)

    # ------------------ full graph ------------------
    G = nx.DiGraph()
    G.add_nodes_from(objects.keys())
    for r in relations:
        if r.get("directed", True):
            s, t = r["source_id"], r["target_id"]
            if s in G.nodes and t in G.nodes:
                G.add_edge(
                    s,
                    t,
                    relation_type=r.get("relation_type"),
                )

    # ------------------ visual styles ------------------
    kind_colors = {
        "definition": "#2ca02c",
        "lemma": "#ff7f0e",
        "theorem": "#d62728",
        "proposition": "#8c564b",
        "corollary": "#9467bd",
        "claim": "#e377c2",
        "conjecture": "#17becf",
        "problem": "#1f77b4",
        "proof": "#7f7f7f",
        "equation": "#cccccc",
    }

    node_sizes: Dict[str, float] = {}
    for oid, od in objects.items():
        k = od["kind"]
        if k == DEF_KIND:
            node_sizes[oid] = 900
        elif k in CONTAINER_KINDS:
            node_sizes[oid] = 900
        elif k == PROOF_KIND:
            node_sizes[oid] = 600
        else:
            node_sizes[oid] = 500

    fig, ax = plt.subplots(figsize=figsize)

    # draw nodes by kind
    for kind, color in kind_colors.items():
        nodes_of_kind = [oid for oid, od in objects.items() if od["kind"] == kind]
        if not nodes_of_kind:
            continue
        nx.draw_networkx_nodes(
            G,
            pos,
            nodelist=nodes_of_kind,
            node_color=color,
            node_size=[node_sizes[n] for n in nodes_of_kind],
            edgecolors="black",
            linewidths=0.5,
            ax=ax,
        )

    # theorem boxes (always, even if a theorem has only itself)
    for box_id, kids in box_children.items():
        box_nodes = [oid for oid in kids if oid in pos]
        if not box_nodes:
            continue
        xs = [pos[oid][0] for oid in box_nodes]
        ys = [pos[oid][1] for oid in box_nodes]
        pad_x, pad_y = 0.06, 0.08
        min_x, max_x = min(xs) - pad_x, max(xs) + pad_x
        min_y, max_y = min(ys) - pad_y, max(ys) + pad_y
        rect = mpatches.FancyBboxPatch(
            (min_x, min_y),
            max_x - min_x,
            max_y - min_y,
            boxstyle="round,pad=0.02",
            linewidth=1.0,
            edgecolor="#ff6666",
            facecolor="none",
            alpha=0.7,
        )
        ax.add_patch(rect)

    # edges by relation_type
    edges_by_type: Dict[str, List[Tuple[str, str]]] = {}
    for u, v, data_e in G.edges(data=True):
        rtype = data_e.get("relation_type", "uses")
        edges_by_type.setdefault(rtype, []).append((u, v))

    edge_styles = {
        "uses": dict(color="tab:blue", style="solid", width=2.0, alpha=0.8),
        "depends_on": dict(color="tab:purple", style="solid", width=2.0, alpha=0.8),
        "follows_from": dict(color="tab:green", style="dashed", width=2.0, alpha=0.8),
        "has_part": dict(color="tab:gray", style="dotted", width=1.5, alpha=0.7),
        "related_to": dict(color="tab:orange", style="dashed", width=2.0, alpha=0.8),
        "generalizes": dict(color="tab:red", style="dashdot", width=2.0, alpha=0.8),

        # NEW
        "mentions_concept": dict(color="black", style="dotted", width=1.2, alpha=0.6),
    }

    for rtype, edge_list in edges_by_type.items():
        style = edge_styles.get(rtype, edge_styles["uses"])
        nx.draw_networkx_edges(
            G,
            pos,
            edgelist=edge_list,
            arrowstyle="->",
            arrowsize=10,
            width=style["width"],
            alpha=style["alpha"],
            style=style["style"],
            edge_color=style["color"],
            ax=ax,
        )

    # labels (inside nodes)
    labels: Dict[str, str] = {}
    for oid, od in objects.items():
        if node_label_attr == "label":
            lab = od.get("label") or od.get("name") or oid
        elif node_label_attr == "name":
            lab = od.get("name") or od.get("label") or oid
        else:
            lab = oid
        labels[oid] = lab

    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=7,
        ax=ax,
    )

    # legend for node kinds and edge styles (including dotted)
    legend_handles = []
    for kind, color in kind_colors.items():
        if any(od["kind"] == kind for od in objects.values()):
            legend_handles.append(mpatches.Patch(color=color, label=kind))

    edge_legend = []
    for rtype, style in edge_styles.items():
        if rtype not in edges_by_type:
            continue
        edge_legend.append(
            Line2D(
                [0],
                [0],
                color=style["color"],
                lw=style["width"],
                linestyle=style["style"],
                label=rtype,
                marker=">",
                markersize=6,
                markevery=(1, 1),
            )
        )

    if legend_handles or edge_legend:
        ax.legend(
            handles=legend_handles + edge_legend,
            fontsize=7,
            loc="upper left",
            frameon=True,
        )

    ax.set_axis_off()
    plt.tight_layout()
    out_path = Path(out_png)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    return G
