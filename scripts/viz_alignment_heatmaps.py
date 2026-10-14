#!/usr/bin/env python3
"""Side-by-side σ heatmaps (Jaccard vs Embedding) for alignment benchmark pairs.

For each positive pair, produces:
  1. Two heatmaps (Jaccard, Embedding) with gold pairs outlined in red.
  2. A scatter/violin plot comparing σ values for gold-matched vs non-matched
     pairs across both methods.

Usage::

    python scripts/viz_alignment_heatmaps.py \
        --paper-a papers/paper101_gold.json \
        --paper-b papers/paper102_gold.json \
        --alignment alignments/jl_alignment.json \
        --key-a paper105_nodes --key-b paper106_nodes \
        --pair-name JL \
        --outdir heatmaps/

    # Or batch mode from a benchmark config:
    python scripts/viz_alignment_heatmaps.py \
        --config config/benchmark_config.json \
        --outdir heatmaps/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize

# ---------------------------------------------------------------------------
# Imports from the repo
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from graph_alignment import jaccard_sim, type_compat  # noqa: E402
from embedding_sigma import sigma as embedding_sigma  # noqa: E402
from graph_alignment_eval import load_json, parse_gold_pairs, resolve_path  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_nodes(paper_json: dict) -> list[dict]:
    """Return nodes as a list (handle both list and dict formats)."""
    nodes = paper_json.get("nodes", [])
    if isinstance(nodes, dict):
        nodes = list(nodes.values())
    return nodes


def sort_nodes(nodes: list[dict]) -> list[dict]:
    """Sort nodes by type then id for consistent heatmap ordering."""
    type_order = {
        "definition": 0, "theorem": 1, "lemma": 2, "proposition": 3,
        "corollary": 4, "claim": 5, "conjecture": 6, "problem": 7,
        "equation": 8, "algorithm": 9, "proof": 10, "example": 11,
        "exercise": 12, "remark": 13, "table": 14,
    }
    return sorted(nodes, key=lambda n: (
        type_order.get(n.get("type", ""), 99),
        n.get("id", ""),
    ))


def compute_sim_matrix(nodes_a, nodes_b, sigma_fn):
    """Return (n_a × n_b) similarity matrix."""
    n_a, n_b = len(nodes_a), len(nodes_b)
    mat = np.zeros((n_a, n_b))
    for i, a in enumerate(nodes_a):
        for j, b in enumerate(nodes_b):
            mat[i, j] = sigma_fn(a, b)
    return mat


def node_label(n: dict) -> str:
    """Short label for heatmap axis: 'id (type)'."""
    nid = n.get("id", "?")
    ntype = (n.get("type") or n.get("kind") or "")[:4]
    name = n.get("name", "")[:25]
    if name:
        return f"{nid}\n{name}"
    return f"{nid} ({ntype})"


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_heatmap_pair(nodes_a, nodes_b, gold_pairs, pair_name,
                      outdir, mat_jaccard=None, mat_embed=None):
    """Plot side-by-side Jaccard and Embedding heatmaps with gold overlays."""
    n_a, n_b = len(nodes_a), len(nodes_b)
    id_a = [n["id"] for n in nodes_a]
    id_b = [n["id"] for n in nodes_b]

    # Gold pair mask
    gold_mask = np.zeros((n_a, n_b), dtype=bool)
    for ai, aid in enumerate(id_a):
        for bj, bid in enumerate(id_b):
            if (aid, bid) in gold_pairs:
                gold_mask[ai, bj] = True

    labels_a = [node_label(n) for n in nodes_a]
    labels_b = [node_label(n) for n in nodes_b]

    # Figure size scales with number of nodes
    cell_size = 0.55
    fig_w = max(12, 2 * n_b * cell_size + 4)
    fig_h = max(5, n_a * cell_size + 2)

    fig, axes = plt.subplots(1, 2, figsize=(fig_w, fig_h))

    for ax, mat, title in [
        (axes[0], mat_jaccard, f"{pair_name} — Jaccard"),
        (axes[1], mat_embed, f"{pair_name} — Embedding (BGE-M3)"),
    ]:
        if mat is None:
            ax.set_visible(False)
            continue

        im = ax.imshow(mat, cmap="viridis", aspect="auto",
                       vmin=0, vmax=max(0.01, mat.max()),
                       interpolation="nearest")

        # Overlay gold pairs with red rectangles
        for i in range(n_a):
            for j in range(n_b):
                if gold_mask[i, j]:
                    rect = mpatches.Rectangle(
                        (j - 0.5, i - 0.5), 1, 1,
                        linewidth=2.5, edgecolor="red", facecolor="none",
                    )
                    ax.add_patch(rect)
                # Show similarity value in cell if matrix is small enough
                if n_a <= 20 and n_b <= 20:
                    color = "white" if mat[i, j] < mat.max() * 0.6 else "black"
                    ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center",
                            fontsize=6, color=color)

        ax.set_xticks(range(n_b))
        ax.set_yticks(range(n_a))
        ax.set_xticklabels(labels_b, rotation=60, ha="right", fontsize=7)
        ax.set_yticklabels(labels_a, fontsize=7)
        ax.set_xlabel("Paper B nodes")
        ax.set_ylabel("Paper A nodes")
        ax.set_title(title, fontsize=11, fontweight="bold")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    # Legend
    legend_patch = mpatches.Patch(edgecolor="red", facecolor="none",
                                   linewidth=2, label="Gold pair")
    fig.legend(handles=[legend_patch], loc="upper center", ncol=1, fontsize=9)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = Path(outdir) / f"{pair_name}_heatmaps.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved heatmap: {out_path}")
    return out_path


def plot_scatter_comparison(nodes_a, nodes_b, gold_pairs, pair_name,
                            outdir, mat_jaccard, mat_embed):
    """Scatter/violin: gold-matched σ values vs non-matched, for both methods."""
    id_a = [n["id"] for n in nodes_a]
    id_b = [n["id"] for n in nodes_b]

    gold_j, nongold_j = [], []
    gold_e, nongold_e = [], []

    for i, aid in enumerate(id_a):
        for j, bid in enumerate(id_b):
            is_gold = (aid, bid) in gold_pairs
            if is_gold:
                gold_j.append(mat_jaccard[i, j])
                gold_e.append(mat_embed[i, j])
            else:
                nongold_j.append(mat_jaccard[i, j])
                nongold_e.append(mat_embed[i, j])

    if not gold_j:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))

    # Panel 1: Box/strip plot
    data = [nongold_j, gold_j, nongold_e, gold_e]
    labels = ["Jaccard\nnon-gold", "Jaccard\ngold",
              "Embedding\nnon-gold", "Embedding\ngold"]
    colors = ["#BBDEFB", "#1565C0", "#C8E6C9", "#2E7D32"]

    bp = axes[0].boxplot(data, tick_labels=labels, patch_artist=True, widths=0.5)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    axes[0].set_ylabel("σ value")
    axes[0].set_title(f"{pair_name} — Gold vs Non-gold σ", fontsize=10)
    axes[0].grid(axis="y", alpha=0.3)

    # Panel 2: Scatter — Jaccard σ vs Embedding σ, colored by gold/non-gold
    axes[1].scatter(nongold_j, nongold_e, alpha=0.3, s=15, c="#999999",
                    label="Non-gold", zorder=2)
    axes[1].scatter(gold_j, gold_e, alpha=0.9, s=50, c="red", marker="*",
                    label="Gold", zorder=3)
    axes[1].set_xlabel("Jaccard σ")
    axes[1].set_ylabel("Embedding σ")
    axes[1].set_title(f"{pair_name} — Jaccard vs Embedding", fontsize=10)
    axes[1].legend(fontsize=8)
    axes[1].set_xlim(-0.02, max(0.1, max(nongold_j + gold_j) * 1.1))
    axes[1].set_ylim(-0.02, max(0.1, max(nongold_e + gold_e) * 1.1))
    axes[1].plot([0, 1], [0, 1], "--", color="#CCCCCC", lw=0.8, zorder=1)
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    out_path = Path(outdir) / f"{pair_name}_scatter.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved scatter: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Single-pair driver
# ---------------------------------------------------------------------------

def process_pair(paper_a_path, paper_b_path, alignment_path,
                 key_a, key_b, pair_name, outdir):
    """Load data, compute matrices, generate plots for one pair."""
    ga = load_json(paper_a_path)
    gb = load_json(paper_b_path)
    align = load_json(alignment_path)

    nodes_a = sort_nodes(get_nodes(ga))
    nodes_b = sort_nodes(get_nodes(gb))
    gold_pairs = parse_gold_pairs(align, key_a, key_b)

    print(f"\n[{pair_name}] A={len(nodes_a)} nodes, B={len(nodes_b)} nodes, "
          f"gold={len(gold_pairs)} pairs")

    # Compute similarity matrices
    mat_j = compute_sim_matrix(nodes_a, nodes_b, jaccard_sim)
    mat_e = compute_sim_matrix(nodes_a, nodes_b, embedding_sigma)

    Path(outdir).mkdir(parents=True, exist_ok=True)

    plot_heatmap_pair(nodes_a, nodes_b, gold_pairs, pair_name,
                      outdir, mat_j, mat_e)
    plot_scatter_comparison(nodes_a, nodes_b, gold_pairs, pair_name,
                            outdir, mat_j, mat_e)


# ---------------------------------------------------------------------------
# Batch mode: read benchmark_config.json
# ---------------------------------------------------------------------------

def batch_from_config(config_path: str, outdir: str,
                      course_papers_dir: str | None = None):
    """Run heatmaps for all positive pairs in a benchmark config."""
    config_path = Path(config_path).resolve()
    config_dir = config_path.parent
    cfg = load_json(config_path)

    paths = {k: v for k, v in cfg.items()
             if isinstance(v, str) and (k.endswith("_papers_dir")
                                        or k == "alignments_dir")}
    if course_papers_dir:
        paths["course_papers_dir"] = course_papers_dir

    for pair_cfg in cfg.get("positive_pairs", []):
        name = pair_cfg["name"]
        ga_path = resolve_path(pair_cfg["graph_A"], paths, config_dir)
        gb_path = resolve_path(pair_cfg["graph_B"], paths, config_dir)

        if not ga_path.exists() or not gb_path.exists():
            print(f"\n[{name}] SKIP — missing paper JSON")
            continue

        if "alignment" not in pair_cfg:
            print(f"\n[{name}] SKIP — no alignment specified")
            continue

        align_path = resolve_path(pair_cfg["alignment"], paths, config_dir)
        if not align_path.exists():
            print(f"\n[{name}] SKIP — alignment file missing: {align_path}")
            continue

        process_pair(
            ga_path, gb_path, align_path,
            pair_cfg.get("key_A", "paper_a_nodes"),
            pair_cfg.get("key_B", "paper_b_nodes"),
            name, outdir,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate Jaccard vs Embedding heatmaps for alignment pairs"
    )
    parser.add_argument("--config", help="Benchmark config JSON (batch mode)")
    parser.add_argument("--paper-a", help="Paper A JSON (single-pair mode)")
    parser.add_argument("--paper-b", help="Paper B JSON (single-pair mode)")
    parser.add_argument("--alignment", help="Gold alignment JSON (single-pair mode)")
    parser.add_argument("--key-a", default="paper_a_nodes",
                        help="Key name for paper A nodes in alignment JSON")
    parser.add_argument("--key-b", default="paper_b_nodes",
                        help="Key name for paper B nodes in alignment JSON")
    parser.add_argument("--pair-name", default="pair",
                        help="Name for this pair (used in filenames)")
    parser.add_argument("--outdir", default="heatmaps/",
                        help="Output directory for PNGs")
    parser.add_argument("--course-papers-dir", default=None,
                        help="Override course_papers_dir path")
    args = parser.parse_args()

    if args.config:
        batch_from_config(args.config, args.outdir, args.course_papers_dir)
    elif args.paper_a and args.paper_b and args.alignment:
        process_pair(args.paper_a, args.paper_b, args.alignment,
                     args.key_a, args.key_b, args.pair_name, args.outdir)
    else:
        parser.error("Provide either --config (batch) or "
                     "--paper-a + --paper-b + --alignment (single pair)")


if __name__ == "__main__":
    main()
