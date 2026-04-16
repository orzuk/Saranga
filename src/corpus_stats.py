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
    "n_thm_with_assumptions", "n_thm_with_conclusions",
    "n_thm_with_both", "n_thm_with_neither",
    "total_assumptions", "total_conclusions",
    "avg_assumptions_per_thm", "avg_conclusions_per_thm",
    "dag_acyclic", "dag_depth",
    "n_has_part_edges", "n_uses_edges", "n_keyword_edges",
    "n_orphan_proofs", "n_isolated_nodes",
    "n_foundation_edges", "n_grounded_to", "n_mentions_concept",
    "n_distinct_foundation_targets",
    "n_foundation_specific", "n_foundation_generic",
    "n_distinct_foundation_specific",
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

    # Assumption/conclusion statistics for theorem-like nodes
    n_with_assumptions = 0
    n_with_conclusions = 0
    n_with_both = 0
    n_with_neither = 0
    total_assumptions = 0
    total_conclusions = 0
    for node in nodes:
        if node.get("type") in THEOREM_LIKE_TYPES:
            a = node.get("assumptions", [])
            c = node.get("conclusions", [])
            has_a = bool(a and any(s.strip() for s in a if isinstance(s, str)))
            has_c = bool(c and any(s.strip() for s in c if isinstance(s, str)))
            if has_a:
                n_with_assumptions += 1
            if has_c:
                n_with_conclusions += 1
            if has_a and has_c:
                n_with_both += 1
            if not has_a and not has_c:
                n_with_neither += 1
            total_assumptions += len(a) if isinstance(a, list) else 0
            total_conclusions += len(c) if isinstance(c, list) else 0

    n_tl = stats["n_theorem_like"]
    stats["n_thm_with_assumptions"] = n_with_assumptions
    stats["n_thm_with_conclusions"] = n_with_conclusions
    stats["n_thm_with_both"] = n_with_both
    stats["n_thm_with_neither"] = n_with_neither
    stats["total_assumptions"] = total_assumptions
    stats["total_conclusions"] = total_conclusions
    stats["avg_assumptions_per_thm"] = round(total_assumptions / n_tl, 2) if n_tl else 0
    stats["avg_conclusions_per_thm"] = round(total_conclusions / n_tl, 2) if n_tl else 0

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

    # Foundation graph links
    # These are populated by the `link` operation (link_to_foundation.py).
    # If `link` hasn't been run, all counts are 0 — which is informative.
    FOUNDATION_EDGE_TYPES = {"grounded_to", "mentions_concept"}
    foundation_targets = set()
    foundation_targets_specific = set()
    n_grounded = 0
    n_mentions = 0
    n_generic = 0
    n_specific = 0
    for e in edges:
        etype = e.get("type") or ""
        if etype in FOUNDATION_EDGE_TYPES:
            t = e.get("target")
            is_generic = e.get("generic", False)
            if t:
                foundation_targets.add(t)
                if not is_generic:
                    foundation_targets_specific.add(t)
            if etype == "grounded_to":
                n_grounded += 1
            elif etype == "mentions_concept":
                n_mentions += 1
            if is_generic:
                n_generic += 1
            else:
                n_specific += 1
    stats["n_foundation_edges"] = n_grounded + n_mentions
    stats["n_grounded_to"] = n_grounded
    stats["n_mentions_concept"] = n_mentions
    stats["n_distinct_foundation_targets"] = len(foundation_targets)
    stats["n_foundation_specific"] = n_specific
    stats["n_foundation_generic"] = n_generic
    stats["n_distinct_foundation_specific"] = len(foundation_targets_specific)

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

    def _line(label, key):
        return f"  {label}{_total(key):>8,}   (avg {_avg(key):.1f})"

    print(f"[stats] ========== Corpus Summary ({n} papers) ==========")
    print(_line("Total nodes:      ", "n_nodes"))
    print(_line("Total edges:      ", "n_edges"))
    print(_line("Theorem-like:     ", "n_theorem_like"))
    print(_line("  theorems:       ", "n_theorems"))
    print(_line("  lemmas:         ", "n_lemmas"))
    print(_line("  propositions:   ", "n_propositions"))
    print(_line("  corollaries:    ", "n_corollaries"))
    print(_line("  claims:         ", "n_claims"))
    print(_line("  conjectures:    ", "n_conjectures"))
    print(_line("  problems:       ", "n_problems"))
    # Assumption/conclusion breakdown
    tl_total = _total("n_theorem_like")
    tl_with_a = _total("n_thm_with_assumptions")
    tl_with_c = _total("n_thm_with_conclusions")
    tl_with_both = _total("n_thm_with_both")
    tl_with_neither = _total("n_thm_with_neither")
    pct_a = f"{100*tl_with_a/tl_total:.0f}%" if tl_total else "n/a"
    pct_c = f"{100*tl_with_c/tl_total:.0f}%" if tl_total else "n/a"
    pct_both = f"{100*tl_with_both/tl_total:.0f}%" if tl_total else "n/a"
    pct_neither = f"{100*tl_with_neither/tl_total:.0f}%" if tl_total else "n/a"
    print(f"  Assumptions/conclusions (of {tl_total} theorem-like):")
    print(f"    with assumptions:   {tl_with_a:>6,}  ({pct_a})")
    print(f"    with conclusions:   {tl_with_c:>6,}  ({pct_c})")
    print(f"    with both:          {tl_with_both:>6,}  ({pct_both})")
    print(f"    with neither:       {tl_with_neither:>6,}  ({pct_neither})")
    print(f"    avg assumptions/thm: {_avg('avg_assumptions_per_thm'):.1f}")
    print(f"    avg conclusions/thm: {_avg('avg_conclusions_per_thm'):.1f}")
    print(_line("Definitions:      ", "n_definitions"))
    print(_line("Proofs:           ", "n_proofs"))
    print(_line("Equations:        ", "n_equations"))
    print(_line("Algorithms:       ", "n_algorithms"))
    print(_line("Tables:           ", "n_tables"))
    print(f"  DAG acyclic:      {acyclic_count}/{n} ({100*acyclic_count/n:.0f}%)")
    print(f"  DAG depth:        max={max_depth}, avg={avg_depth:.1f}")
    print(_line("Orphan proofs:    ", "n_orphan_proofs"))
    print(_line("Isolated nodes:   ", "n_isolated_nodes"))
    # Foundation graph links (populated by the `link` operation)
    n_found = _total("n_foundation_edges")
    n_targets = _total("n_distinct_foundation_targets")
    if n_found > 0:
        n_spec = _total("n_foundation_specific")
        n_gen = _total("n_foundation_generic")
        n_spec_targets = _total("n_distinct_foundation_specific")
        print(f"  Foundation links:  {n_found:>8,}   (avg {_avg('n_foundation_edges'):.1f})")
        print(f"    specific:        {n_spec:>8,}   ({n_spec_targets} distinct terms)")
        print(f"    generic (df>10%):{n_gen:>8,}")
        print(f"    grounded_to:     {_total('n_grounded_to'):>8,}")
        print(f"    mentions_concept:{_total('n_mentions_concept'):>8,}")
        print(f"    distinct targets:{n_targets:>8,}")
    else:
        print(f"  Foundation links:         0   (run --operations link to populate)")


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
