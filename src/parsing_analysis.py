#!/usr/bin/env python3
"""
parsing_analysis.py

Post-processing analysis for parsed math papers (JSONs produced by math_paper_parser).

Features (per-paper):
- Count objects by kind (theorem, lemma, definition, proof, equation, etc.)
- Count edges and edges by relation_type
- Count isolated nodes and isolated nodes by kind
- Count "orphan proofs" (proofs not connected to any theorem-like object)

Global (across all papers):
- Print summary statistics (means, medians) for key kinds
- Produce simple plots:
    * Histogram of #objects of each kind per paper
    * Histogram of #edges per paper
    * Bar plot of total #edges by relation_type

Usage:
    python parsing_analysis.py /path/to/full_papers/json_root \
        --out-dir /path/to/analysis_plots
"""

import argparse
import json
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean, median

import matplotlib.pyplot as plt
import networkx as nx

from math_paper_parser import PaperGraph


# --------------------------------------------------------------------
# Helpers to build NetworkX and analyze one paper
# --------------------------------------------------------------------


def build_networkx(pg: PaperGraph) -> nx.DiGraph:
    """
    Build a simple NetworkX DiGraph from a PaperGraph.
    Nodes: math object IDs, with 'kind' attribute.
    Edges: relations, with 'relation' attribute = relation_type.
    """
    G = nx.DiGraph()
    # nodes
    for oid, obj in pg.objects.items():
        G.add_node(oid, kind=obj.kind)
    # edges
    for rel in pg.relations:
        if rel.source_id in pg.objects and rel.target_id in pg.objects:
            G.add_edge(rel.source_id, rel.target_id, relation=rel.relation_type)
    return G


def analyze_graph(pg: PaperGraph) -> dict:
    """
    Return a dict with diagnostic stats for one parsed paper.
    """
    G = build_networkx(pg)

    # Object kinds (theorem, lemma, definition, proof, equation, etc.)
    kinds = Counter(obj.kind for obj in pg.objects.values())

    # Edges and relation types
    num_edges = G.number_of_edges()
    edge_types = Counter(nx.get_edge_attributes(G, "relation").values())

    # Degree stats / isolated nodes
    deg = dict(G.degree())
    isolated_nodes = [n for n, d in deg.items() if d == 0]
    iso_by_kind = Counter(pg.objects[n].kind for n in isolated_nodes)

    # Orphan proofs = proofs not connected to any theorem/lemma/...
    statement_kinds = {
        "theorem",
        "lemma",
        "proposition",
        "corollary",
        "claim",
        "conjecture",
    }
    orphan_proofs = []
    for n, data in G.nodes(data=True):
        if data.get("kind") != "proof":
            continue
        nbrs = set(G.predecessors(n)) | set(G.successors(n))
        if not any(G.nodes[m].get("kind") in statement_kinds for m in nbrs):
            orphan_proofs.append(n)

    return {
        "num_objects": len(pg.objects),
        "kinds": dict(kinds),
        "num_edges": num_edges,
        "edge_types": dict(edge_types),
        "num_isolated": len(isolated_nodes),
        "isolated_by_kind": dict(iso_by_kind),
        "num_orphan_proofs": len(orphan_proofs),
        "orphan_proofs": orphan_proofs,
    }


# --------------------------------------------------------------------
# Aggregation and plotting
# --------------------------------------------------------------------


def aggregate_stats(rows):
    """
    Build global summary statistics from the per-paper rows.
    """
    if not rows:
        return {}

    # collect all kinds that appear anywhere
    all_kinds = sorted({k for r in rows for k in r["kinds"].keys()})

    per_kind_counts = {k: [] for k in all_kinds}
    edges_per_paper = []
    isolated_per_paper = []
    orphan_proofs_per_paper = []
    total_edge_types = Counter()

    for r in rows:
        edges_per_paper.append(r["num_edges"])
        isolated_per_paper.append(r["num_isolated"])
        orphan_proofs_per_paper.append(r["num_orphan_proofs"])
        total_edge_types.update(r["edge_types"])
        for k in all_kinds:
            per_kind_counts[k].append(r["kinds"].get(k, 0))

    summary = {
        "all_kinds": all_kinds,
        "per_kind_counts": per_kind_counts,
        "edges_per_paper": edges_per_paper,
        "isolated_per_paper": isolated_per_paper,
        "orphan_proofs_per_paper": orphan_proofs_per_paper,
        "total_edge_types": dict(total_edge_types),
    }

    # Add simple descriptive stats (mean / median) for readability
    summary["per_kind_stats"] = {
        k: {
            "mean": mean(vals),
            "median": median(vals),
        }
        for k, vals in per_kind_counts.items()
    }
    summary["edges_stats"] = {
        "mean": mean(edges_per_paper),
        "median": median(edges_per_paper),
    }

    return summary


def make_plots(rows, summary, out_dir: Path):
    """
    Produce plots and save them as PNGs.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    all_kinds = summary["all_kinds"]
    per_kind_counts = summary["per_kind_counts"]
    edges_per_paper = summary["edges_per_paper"]
    total_edge_types = summary["total_edge_types"]

    num_papers = len(rows)

    # 1. Histogram of counts per kind per paper
    for kind in all_kinds:
        vals = per_kind_counts[kind]
        plt.figure()
        plt.hist(vals, bins=20, edgecolor="black")
        plt.title(f"Distribution of #{kind} per paper (n={num_papers})")
        plt.xlabel(f"#{kind} in paper")
        plt.ylabel("Number of papers")
        plt.tight_layout()
        plt.savefig(out_dir / f"hist_{kind}_per_paper.png", dpi=200)
        plt.close()

    # 2. Histogram of #edges per paper
    plt.figure()
    plt.hist(edges_per_paper, bins=20, edgecolor="black")
    plt.title(f"Distribution of #edges per paper (n={num_papers})")
    plt.xlabel("#edges in paper graph")
    plt.ylabel("Number of papers")
    plt.tight_layout()
    plt.savefig(out_dir / "hist_edges_per_paper.png", dpi=200)
    plt.close()

    # 3. Bar plot of edge types summed across all papers
    if total_edge_types:
        labels = list(total_edge_types.keys())
        counts = [total_edge_types[k] for k in labels]
        plt.figure(figsize=(max(6, len(labels) * 0.8), 4))
        plt.bar(range(len(labels)), counts)
        plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
        plt.ylabel("Total number of edges")
        plt.title("Total edges by relation_type (all papers)")
        plt.tight_layout()
        plt.savefig(out_dir / "bar_edge_types.png", dpi=200)
        plt.close()


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Analyze parsed paper graphs (JSON) and produce summary stats + plots."
    )
    parser.add_argument(
        "root_dir",
        type=str,
        help="Directory under which *.json PaperGraph files live (searched recursively).",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Directory to save analysis plots (default: ROOT_DIR/analysis_plots).",
    )
    args = parser.parse_args()

    root = Path(args.root_dir)
    out_dir = Path(args.out_dir) if args.out_dir else root / "analysis_plots"

    rows = []
    for json_path in sorted(root.rglob("*.json")):
        paper_id = json_path.stem
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Failed to read {json_path}: {e}")
            continue

        try:
            pg = PaperGraph.from_dict(data)
        except Exception as e:
            print(f"[WARN] Failed to reconstruct PaperGraph for {json_path}: {e}")
            continue

        stats = analyze_graph(pg)
        stats["paper_id"] = paper_id
        rows.append(stats)

    if not rows:
        print("[INFO] No JSON PaperGraph files found, nothing to analyze.")
        return

    # Per-paper printout (compact)
    for r in rows:
        print("\n=== ", r["paper_id"], " ===")
        print("Kinds:", r["kinds"])
        print(
            "Edges:", r["num_edges"],
            "| Isolated:", r["num_isolated"],
            "| Orphan proofs:", r["num_orphan_proofs"],
        )
        print("Edge types:", r["edge_types"])
        print("Isolated by kind:", r["isolated_by_kind"])

    # Global summary + plots
    summary = aggregate_stats(rows)

    print("\n=== GLOBAL SUMMARY ===")
    print("Total papers:", len(rows))
    print("Mean / median #edges per paper:", summary["edges_stats"])
    print("Mean / median #objects per kind:")
    for k, stats in summary["per_kind_stats"].items():
        print(f"  {k:15s} mean={stats['mean']:.2f}  median={stats['median']:.2f}")

    print("\nTotal edges by relation_type:", summary["total_edge_types"])

    print(f"\n[INFO] Saving plots to: {out_dir}")
    make_plots(rows, summary, out_dir)
    print("[INFO] Done.")


if __name__ == "__main__":
    main()
