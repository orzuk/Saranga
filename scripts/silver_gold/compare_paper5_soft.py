#!/usr/bin/env python3
"""Re-run the paper5 manual-vs-LLM 10-way comparison with soft metrics.

For each LLM-extracted graph in
    /mnt/g/My Drive/Research/Automath/alignment_benchmark/papers/paper5/gold_*.json
align it (Hungarian, jaccard_sim, alpha=0.5) against the manual gold:
    /mnt/g/My Drive/Research/Automath/alignment_benchmark/papers/paper5/Sinkhorn_graph_manual.json
and report BOTH strict (threshold-based) and soft (threshold-free) P/R/F1
for nodes and edges.

Manual JSON has annotator-only fields (origin, origin_citation, formal_label)
that the LLM JSONs lack. They are stripped IN MEMORY before alignment.

Output:
  - JSON per-pair details to manual_gold_comparison_soft.json
  - Markdown table to stdout, sorted by node_f1_soft DESC
"""
import json
import os
import sys
from pathlib import Path

# Make src/ importable
HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))

from graph_alignment import (  # noqa: E402
    align_graphs, jaccard_sim, soft_metrics, edge_sim,
)


PAPER5_DIR = Path(
    "/mnt/g/My Drive/Research/Automath/alignment_benchmark/papers/paper5"
)
MANUAL_FILE = PAPER5_DIR / "Sinkhorn_graph_manual.json"
OUTPUT_JSON = PAPER5_DIR / "manual_gold_comparison_soft.json"

MANUAL_ONLY_FIELDS = ("origin", "origin_citation", "formal_label")


def strip_manual_fields(graph: dict) -> dict:
    """Return a new graph dict with manual-only fields stripped from nodes."""
    new = {k: v for k, v in graph.items() if k != "nodes"}
    new["nodes"] = []
    for n in graph.get("nodes", []):
        nn = {k: v for k, v in n.items() if k not in MANUAL_ONLY_FIELDS}
        new["nodes"].append(nn)
    return new


def strict_metrics(matching, llm_graph, manual_graph,
                   sigma_fn=jaccard_sim, alpha=0.5, threshold=0.5):
    """Strict threshold-based P/R/F1 for nodes and edges (the legacy path).

    A matched pair counts as TP iff sigma >= threshold. An edge is matched
    iff both endpoints strict-match AND edge_sim == 1.0 (same edge type).
    """
    a_by_id = {n["id"]: n for n in llm_graph.get("nodes", [])}
    b_by_id = {n["id"]: n for n in manual_graph.get("nodes", [])}

    n_ext = len(llm_graph.get("nodes", []))
    n_gold = len(manual_graph.get("nodes", []))

    strict_pairs = []
    for aid, bid in matching.items():
        if aid in a_by_id and bid in b_by_id:
            s = sigma_fn(a_by_id[aid], b_by_id[bid])
            if s >= threshold:
                strict_pairs.append((aid, bid, s))
    tp_n = len(strict_pairs)
    p_n = tp_n / n_ext if n_ext else 0.0
    r_n = tp_n / n_gold if n_gold else 0.0
    f1_n = (2 * p_n * r_n / (p_n + r_n)) if (p_n + r_n) else 0.0

    # Strict edges: both endpoints must be strict-matched AND edge type matches
    strict_match_set = {aid: bid for aid, bid, _ in strict_pairs}
    edges_a = llm_graph.get("edges", [])
    edges_b = manual_graph.get("edges", [])
    n_ea, n_eb = len(edges_a), len(edges_b)

    edges_b_by_pair = {}
    for e in edges_b:
        edges_b_by_pair.setdefault((e["source"], e["target"]), []).append(e)

    edge_tp = 0
    for e1 in edges_a:
        s1 = strict_match_set.get(e1["source"])
        t1 = strict_match_set.get(e1["target"])
        if not (s1 and t1):
            continue
        for e2 in edges_b_by_pair.get((s1, t1), []):
            if edge_sim(e1, e2) == 1.0:
                edge_tp += 1
                break

    p_e = edge_tp / n_ea if n_ea else 0.0
    r_e = edge_tp / n_eb if n_eb else 0.0
    f1_e = (2 * p_e * r_e / (p_e + r_e)) if (p_e + r_e) else 0.0

    return {
        "node_precision": p_n, "node_recall": r_n, "node_f1": f1_n,
        "node_tp_strict": tp_n,
        "edge_precision": p_e, "edge_recall": r_e, "edge_f1": f1_e,
        "edge_tp_strict": edge_tp,
        "strict_matched_pairs": [
            {"a_id": a, "b_id": b, "sigma": s} for a, b, s in strict_pairs
        ],
    }


def main():
    with open(MANUAL_FILE) as f:
        manual_raw = json.load(f)
    manual = strip_manual_fields(manual_raw)
    n_manual_nodes = len(manual.get("nodes", []))
    n_manual_edges = len(manual.get("edges", []))
    print(f"Manual: {MANUAL_FILE.name}  "
          f"{n_manual_nodes} nodes, {n_manual_edges} edges")

    llm_files = sorted(
        f for f in os.listdir(PAPER5_DIR)
        if f.startswith("gold_") and f.endswith(".json")
        and not f.endswith(".bak")
    )
    print(f"LLM files: {len(llm_files)}")

    rows = []
    detail = {
        "manual_file": MANUAL_FILE.name,
        "manual_nodes": n_manual_nodes,
        "manual_edges": n_manual_edges,
        "stripped_fields": list(MANUAL_ONLY_FIELDS),
        "f1_strict_threshold": 0.5,
        "sigma": "jaccard_sim (with type compat; problem<->definition=0.7)",
        "alignment": "Hungarian iterative (align_graphs alpha=0.5)",
        "results": {},
    }

    for fname in llm_files:
        with open(PAPER5_DIR / fname) as f:
            llm_graph = json.load(f)
        n_llm = len(llm_graph.get("nodes", []))
        n_llm_edges = len(llm_graph.get("edges", []))

        # LLM = graph_a (predicted), Manual = graph_b (gold)
        result = align_graphs(llm_graph, manual, sigma_fn=jaccard_sim,
                              alpha=0.5, threshold=0.0)
        matching = result["matching"]

        soft = soft_metrics(matching, llm_graph, manual,
                            sigma_fn=jaccard_sim, alpha=0.5)
        strict = strict_metrics(matching, llm_graph, manual,
                                sigma_fn=jaccard_sim, alpha=0.5,
                                threshold=0.5)

        rows.append({
            "file": fname,
            "n_llm_nodes": n_llm,
            "n_llm_edges": n_llm_edges,
            "node_f1": strict["node_f1"],
            "node_f1_soft": soft["f1_soft"],
            "edge_f1": strict["edge_f1"],
            "edge_f1_soft": soft["edge_f1_soft"],
        })

        detail["results"][fname] = {
            "n_llm_nodes": n_llm,
            "n_llm_edges": n_llm_edges,
            "n_manual_nodes": n_manual_nodes,
            "n_manual_edges": n_manual_edges,
            "n_matched_any": len(matching),
            "hungarian_total_score": result["score"],
            "hungarian_node_score": result["node_score"],
            "hungarian_edge_score": result["edge_score"],
            "strict": strict,
            "soft": soft,
        }

    # Sort by node_f1_soft DESC
    rows.sort(key=lambda r: r["node_f1_soft"], reverse=True)

    print()
    print("| File | #nodes | node_F1 (strict) | node_F1_soft | edge_F1 (strict) | edge_F1_soft |")
    print("|------|--------|------------------|--------------|------------------|--------------|")
    for r in rows:
        print(f"| {r['file']} | {r['n_llm_nodes']} | "
              f"{r['node_f1']:.3f} | {r['node_f1_soft']:.3f} | "
              f"{r['edge_f1']:.3f} | {r['edge_f1_soft']:.3f} |")

    with open(OUTPUT_JSON, "w") as f:
        json.dump(detail, f, indent=2)
    print(f"\nWrote details to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
