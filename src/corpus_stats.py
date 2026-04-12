#!/usr/bin/env python3
"""
Per-paper corpus statistics for extracted knowledge graphs.

Scans a directory of unified-schema JSONs and produces corpus_stats.csv with
one row per paper. Designed to be loaded directly into pandas for the NeurIPS
paper's Section 6.4 (arXiv extraction at scale) without re-parsing JSONs.

Usage as pipeline operation:
    python src/run_pipeline.py --operations stats --out-dir ./out_math_co_1000

Usage as standalone CLI:
    python src/corpus_stats.py --out-dir ./out_math_co_1000 --verbose

Output columns:
    paper_id, n_nodes, n_edges,
    n_theorems, n_lemmas, n_propositions, n_corollaries, n_claims,
    n_conjectures, n_problems, n_definitions, n_proofs, n_algorithms,
    n_equations, n_tables, n_other,
    n_theorem_like (sum of the 7 theorem-like types),
    dag_acyclic (bool), dag_depth (int, -1 if cyclic),
    n_has_part_edges, n_uses_edges, n_keyword_edges,
    n_orphan_proofs, n_isolated_nodes
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import networkx as nx
    _HAS_NETWORKX = True
except ImportError:
    _HAS_NETWORKX = False


# Node types that count as "theorem-like" (matches anomaly_detection.py)
THEOREM_LIKE_TYPES = {
    "theorem", "lemma", "proposition", "corollary",
    "claim", "conjecture", "problem",
}

# All node types we track individually (rest → "other")
TRACKED_TYPES = [
    "theorem", "lemma", "proposition", "corollary", "claim",
    "conjecture", "problem", "definition", "proof", "algorithm",
    "equation", "table",
]

# CSV column order
STAT_COLUMNS = [
    "paper_id",
    "n_nodes", "n_edges",
    "n_theorems", "n_lemmas", "n_propositions", "n_corollaries", "n_claims",
    "n_conjectures", "n_problems", "n_definitions", "n_proofs", "n_algorithms",
    "n_equations", "n_tables", "n_other",
    "n_theorem_like",
    "dag_acyclic", "dag_depth",
    "n_has_part_edges", "n_uses_edges", "n_keyword_edges",
    "n_orphan_proofs", "n_isolated_nodes",
]


def _get_nodes_edges(data: Dict[str, Any]):
    """Return (nodes_list, edges_list) handling both schemas."""
    if "nodes" in data:
        return data.get("nodes", []) or [], data.get("edges", []) or []
    if "objects" in data:
        objs = data.get("objects", {}) or {}
        rels = data.get("relations", []) or []
        nodes = []
        for obj_id, obj in objs.items():
            node = dict(obj)
            node.setdefault("id", obj_id)
            if "kind" in node and "type" not in node:
                node["type"] = node["kind"]
            nodes.append(node)
        edges = []
        for rel in rels:
            edges.append({
                "source": rel.get("source_id") or rel.get("source"),
                "target": rel.get("target_id") or rel.get("target"),
                "type": rel.get("relation_type") or rel.get("type"),
            })
        return nodes, edges
    return [], []


def compute_paper_stats(paper_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute all per-paper statistics from a single JSON. Returns a dict."""
    nodes, edges = _get_nodes_edges(data)

    n_nodes = len(nodes)
    n_edges = len(edges)

    # Node type counts
    type_counts: Counter = Counter()
    for node in nodes:
        type_counts[node.get("type") or "unknown"] += 1

    stats: Dict[str, Any] = {
        "paper_id": paper_id,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
    }

    # Per-type counts
    for t in TRACKED_TYPES:
        col_name = f"n_{t}s" if not t.endswith("s") else f"n_{t}"
        # Normalize column names to match STAT_COLUMNS
        stats[col_name] = type_counts.get(t, 0)
    # Fix naming: the column names use plural forms matching STAT_COLUMNS
    stats["n_theorems"] = type_counts.get("theorem", 0)
    stats["n_lemmas"] = type_counts.get("lemma", 0)
    stats["n_propositions"] = type_counts.get("proposition", 0)
    stats["n_corollaries"] = type_counts.get("corollary", 0)
    stats["n_claims"] = type_counts.get("claim", 0)
    stats["n_conjectures"] = type_counts.get("conjecture", 0)
    stats["n_problems"] = type_counts.get("problem", 0)
    stats["n_definitions"] = type_counts.get("definition", 0)
    stats["n_proofs"] = type_counts.get("proof", 0)
    stats["n_algorithms"] = type_counts.get("algorithm", 0)
    stats["n_equations"] = type_counts.get("equation", 0)
    stats["n_tables"] = type_counts.get("table", 0)
    stats["n_other"] = sum(
        c for t, c in type_counts.items() if t not in set(TRACKED_TYPES)
    )
    stats["n_theorem_like"] = sum(type_counts[t] for t in THEOREM_LIKE_TYPES)

    # Edge type counts
    edge_types: Counter = Counter()
    for e in edges:
        etype = e.get("type") or "unknown"
        edge_types[etype] += 1
    stats["n_has_part_edges"] = edge_types.get("has_part", 0) + edge_types.get("proves", 0)
    stats["n_uses_edges"] = edge_types.get("uses", 0) + edge_types.get("dependency", 0)
    # Keyword edges are "uses" edges created from keyword matching — we can't
    # distinguish them from ref-based "uses" at the JSON level (both have
    # type="uses"). So n_uses_edges includes both. n_keyword_edges is set to 0
    # here; Yaron's extractor logs the breakdown but it's not in the JSON.
    stats["n_keyword_edges"] = 0

    # Orphan proofs
    node_id_set = set(n.get("id") for n in nodes if n.get("id"))
    n_orphan = 0
    for node in nodes:
        if node.get("type") == "proof":
            proves = node.get("proves")
            if not proves or proves not in node_id_set:
                n_orphan += 1
    stats["n_orphan_proofs"] = n_orphan

    # Isolated nodes (no incoming or outgoing edges)
    connected = set()
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s:
            connected.add(s)
        if t:
            connected.add(t)
    stats["n_isolated_nodes"] = sum(
        1 for n in nodes
        if n.get("id") and n["id"] not in connected
    )

    # DAG properties
    if _HAS_NETWORKX and n_nodes > 0:
        g = nx.DiGraph()
        for n in nodes:
            nid = n.get("id")
            if nid:
                g.add_node(nid)
        for e in edges:
            s, t = e.get("source"), e.get("target")
            if s and t:
                g.add_edge(s, t)
        is_dag = nx.is_directed_acyclic_graph(g)
        stats["dag_acyclic"] = is_dag
        if is_dag:
            try:
                stats["dag_depth"] = nx.dag_longest_path_length(g)
            except Exception:
                stats["dag_depth"] = 0
        else:
            stats["dag_depth"] = -1
    else:
        stats["dag_acyclic"] = True if n_edges == 0 else None
        stats["dag_depth"] = 0

    return stats


def compute_corpus_stats(out_dir: str, verbose: bool = False) -> Tuple[List[Dict[str, Any]], int]:
    """Scan all paper-graph JSONs in out_dir, return (stats_list, n_scanned)."""
    out_path = Path(out_dir)
    if not out_path.exists():
        return [], 0

    excluded = {
        "status_log.csv", "validate_report.csv", "anomalies_report.csv",
        "evaluation_results.csv", "corpus_stats.csv",
    }
    candidates = sorted(out_path.rglob("*.json"))
    candidates = [p for p in candidates if p.name not in excluded]

    all_stats: List[Dict[str, Any]] = []
    n_skipped = 0
    for jp in candidates:
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            n_skipped += 1
            continue
        if not isinstance(data, dict):
            n_skipped += 1
            continue
        if "nodes" not in data and "objects" not in data:
            n_skipped += 1
            continue

        paper_id = (
            (data.get("metadata") or {}).get("paper_id")
            or data.get("paper_id")
            or jp.stem.replace("_manual", "").replace("_anthropic", "")
                      .replace("_openai", "").replace("_huggingface", "")
        )
        stats = compute_paper_stats(paper_id, data)
        all_stats.append(stats)

    if verbose:
        print(f"[stats] computed stats for {len(all_stats)} papers "
              f"(skipped {n_skipped} non-paper files)")

    return all_stats, len(all_stats)


def write_corpus_stats(stats_list: List[Dict[str, Any]], out_path: str) -> None:
    """Write per-paper stats to CSV, sorted by paper_id."""
    stats_sorted = sorted(stats_list, key=lambda s: s.get("paper_id", ""))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=STAT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(stats_sorted)


def print_summary(stats_list: List[Dict[str, Any]]) -> None:
    """Print a quick summary table to stdout."""
    if not stats_list:
        print("[stats] no papers to summarize")
        return

    n = len(stats_list)
    def _avg(key):
        vals = [s.get(key, 0) for s in stats_list if s.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0

    def _total(key):
        return sum(s.get(key, 0) for s in stats_list)

    acyclic_count = sum(1 for s in stats_list if s.get("dag_acyclic"))
    depths = [s["dag_depth"] for s in stats_list if s.get("dag_depth", -1) >= 0]
    max_depth = max(depths) if depths else 0
    avg_depth = sum(depths) / len(depths) if depths else 0

    print(f"[stats] ========== Corpus Summary ({n} papers) ==========")
    print(f"  Total nodes:      {_total('n_nodes'):>8,}   (avg {_avg('n_nodes'):.1f} per paper)")
    print(f"  Total edges:      {_total('n_edges'):>8,}   (avg {_avg('n_edges'):.1f} per paper)")
    print(f"  Theorem-like:     {_total('n_theorem_like'):>8,}   (avg {_avg('n_theorem_like'):.1f})")
    print(f"    theorems:       {_total('n_theorems'):>8,}")
    print(f"    lemmas:         {_total('n_lemmas'):>8,}")
    print(f"    propositions:   {_total('n_propositions'):>8,}")
    print(f"    corollaries:    {_total('n_corollaries'):>8,}")
    print(f"  Definitions:      {_total('n_definitions'):>8,}")
    print(f"  Proofs:           {_total('n_proofs'):>8,}")
    print(f"  Equations:        {_total('n_equations'):>8,}")
    print(f"  Algorithms:       {_total('n_algorithms'):>8,}")
    print(f"  Tables:           {_total('n_tables'):>8,}")
    print(f"  DAG acyclic:      {acyclic_count}/{n} ({100*acyclic_count/n:.0f}%)")
    print(f"  DAG depth:        max={max_depth}, avg={avg_depth:.1f}")
    print(f"  Orphan proofs:    {_total('n_orphan_proofs'):>8,}")
    print(f"  Isolated nodes:   {_total('n_isolated_nodes'):>8,}")


# --- standalone CLI -----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compute per-paper statistics from extracted JSONs."
    )
    parser.add_argument("--out-dir", required=True,
                        help="Directory containing JSONs to scan.")
    parser.add_argument("--report-path", default=None,
                        help="Output CSV path (default: OUT_DIR/corpus_stats.csv).")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    stats_list, n_scanned = compute_corpus_stats(args.out_dir, verbose=args.verbose)

    report_path = args.report_path or str(Path(args.out_dir) / "corpus_stats.csv")
    write_corpus_stats(stats_list, report_path)
    print(f"[stats] wrote {n_scanned} rows to {report_path}")

    print_summary(stats_list)


if __name__ == "__main__":
    main()
