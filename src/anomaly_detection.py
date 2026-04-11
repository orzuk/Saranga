#!/usr/bin/env python3
"""
Anomaly detection for extracted paper JSONs.

Scans a directory of unified-schema JSONs and flags structural or content-
wise weirdness for manual review. Designed to be run as a post-processing
step after `parse`, either via `run_pipeline.py --operations anomalies` or
directly as a CLI tool.

Rule categories:
    A — "extraction probably failed"   (high severity)
    B — "structural oddity"            (medium severity)
    C — "content oddity"               (low severity)
    D — (TBD) distribution-level anomalies, needs corpus-wide stats:
           * node count far from corpus median (<1% or >99% percentile)
           * extreme DAG depth for the paper's page count
           * theorems-per-page ratio outlier
        These require a second pass after all per-paper anomalies are
        collected. Not implemented in this first version.

Usage as standalone CLI:
    python src/anomaly_detection.py --out-dir ./out_math_co_1000 --verbose

Usage as pipeline operation:
    python src/run_pipeline.py --operations anomalies --out-dir ./out_math_co_1000

Output: anomalies_report.csv in the out-dir, columns:
    paper_id, category, rule, severity, value, threshold, message
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import networkx as nx
    _HAS_NETWORKX = True
except ImportError:
    _HAS_NETWORKX = False


# --- schema constants ---------------------------------------------------------

# Node types in the unified schema that count as "theorem-like"
THEOREM_LIKE_TYPES = {
    "theorem", "lemma", "proposition", "corollary",
    "claim", "conjecture", "problem",
}

# Node types that should usually exist in a math paper
EXPECTED_TYPES = {"theorem", "definition", "proof", "equation"}


# --- anomaly record type ------------------------------------------------------

# Tuple layout: (paper_id, category, rule, severity, value, threshold, message)
AnomalyRecord = Tuple[str, str, str, str, str, str, str]

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


# --- schema compatibility helper ---------------------------------------------

def _get_nodes_edges(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (nodes_list, edges_list) from a paper JSON, handling both schemas.

    Unified schema (preferred): {metadata, nodes: [...], edges: [...]}
    Legacy schema (tolerated):  {paper_id, objects: {id: {...}}, relations: [{...}]}
    """
    if "nodes" in data:
        return data.get("nodes", []) or [], data.get("edges", []) or []

    if "objects" in data:
        objs = data.get("objects", {}) or {}
        rels = data.get("relations", []) or []
        nodes: List[Dict[str, Any]] = []
        for obj_id, obj in objs.items():
            node = dict(obj)
            node.setdefault("id", obj_id)
            if "kind" in node and "type" not in node:
                node["type"] = node["kind"]
            nodes.append(node)
        edges: List[Dict[str, Any]] = []
        for rel in rels:
            edge = {
                "source": rel.get("source_id") or rel.get("source"),
                "target": rel.get("target_id") or rel.get("target"),
                "type": rel.get("relation_type") or rel.get("type"),
            }
            edges.append(edge)
        return nodes, edges

    return [], []


def _build_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]):
    """Build a networkx DiGraph from nodes/edges (or return None if networkx missing)."""
    if not _HAS_NETWORKX:
        return None
    g = nx.DiGraph()
    for n in nodes:
        nid = n.get("id")
        if nid:
            g.add_node(nid)
    for e in edges:
        s = e.get("source")
        t = e.get("target")
        if s and t:
            g.add_edge(s, t)
    return g


# --- the rules ---------------------------------------------------------------

def detect_anomalies_for_paper(paper_id: str, data: Dict[str, Any]) -> List[AnomalyRecord]:
    """Run all category A/B/C rules on one paper's JSON. Returns list of records."""
    nodes, edges = _get_nodes_edges(data)
    results: List[AnomalyRecord] = []

    n_nodes = len(nodes)
    n_edges = len(edges)

    # Count nodes by type
    type_counts: Counter = Counter()
    for node in nodes:
        type_counts[node.get("type") or "unknown"] += 1

    n_theorem_like = sum(type_counts[t] for t in THEOREM_LIKE_TYPES)
    n_proofs = type_counts.get("proof", 0)
    n_definitions = type_counts.get("definition", 0)
    n_equations = type_counts.get("equation", 0)

    # =========================================================================
    # CATEGORY A — extraction probably failed (high severity)
    # =========================================================================

    # A1: empty JSON
    if n_nodes == 0:
        results.append((paper_id, "A", "empty_json", "high",
                        "0", ">=1", "No nodes extracted at all"))
        return results  # nothing else worth checking

    # A2: tiny paper
    if n_nodes < 3:
        results.append((paper_id, "A", "tiny_paper", "high",
                        str(n_nodes), ">=3",
                        f"Only {n_nodes} nodes extracted — probably a failed extraction"))

    # A3: no edges but has nodes
    if n_edges == 0 and n_nodes >= 3:
        results.append((paper_id, "A", "no_edges", "high",
                        "0", ">=1",
                        f"{n_nodes} nodes but 0 edges — no connectivity detected"))

    # A4: DAG has cycles
    if _HAS_NETWORKX and n_edges > 0 and n_nodes >= 2:
        g = _build_graph(nodes, edges)
        if g is not None and g.number_of_nodes() > 0 and not nx.is_directed_acyclic_graph(g):
            try:
                n_cycles = sum(1 for _ in nx.simple_cycles(g))
            except Exception:
                n_cycles = "?"
            results.append((paper_id, "A", "has_cycles", "high",
                            str(n_cycles), "0",
                            f"Dependency graph contains {n_cycles} cycle(s)"))

    # A5: all nodes isolated (no edges reference any node)
    if n_edges > 0 and n_nodes >= 3:
        connected_ids = set()
        node_id_set = set(n.get("id") for n in nodes if n.get("id"))
        for e in edges:
            s, t = e.get("source"), e.get("target")
            if s and s in node_id_set:
                connected_ids.add(s)
            if t and t in node_id_set:
                connected_ids.add(t)
        if len(connected_ids) == 0:
            results.append((paper_id, "A", "all_isolated", "high",
                            "0", ">=1",
                            f"{n_edges} edges but none reference any node in the graph"))

    # =========================================================================
    # CATEGORY B — structural oddity (medium severity)
    # =========================================================================

    # B1: zero proofs with ≥3 theorem-like (the 2505.19072 case)
    if n_proofs == 0 and n_theorem_like >= 3:
        results.append((paper_id, "B", "zero_proofs_with_theorems", "medium",
                        f"thm={n_theorem_like}, pf=0", ">=1 proof",
                        f"{n_theorem_like} theorem-like objects but 0 proofs"))

    # B2: theorems/proofs ratio outside normal range
    if n_theorem_like >= 5 and n_proofs > 0:
        ratio = n_proofs / n_theorem_like
        if ratio < 0.3 or ratio > 3.0:
            results.append((paper_id, "B", "theorems_proofs_ratio_off", "medium",
                            f"{ratio:.2f}", "[0.3, 3.0]",
                            f"{n_proofs} proofs / {n_theorem_like} theorem-like = {ratio:.2f}"))

    # B3: orphan proofs (proof's `proves` field missing or dangling)
    node_id_set = set(n.get("id") for n in nodes if n.get("id"))
    n_orphan_proofs = 0
    for node in nodes:
        if node.get("type") == "proof":
            proves = node.get("proves")
            if not proves or proves not in node_id_set:
                n_orphan_proofs += 1
    if n_orphan_proofs > 0 and n_proofs > 0:
        results.append((paper_id, "B", "orphan_proofs", "medium",
                        f"{n_orphan_proofs}/{n_proofs}", "0",
                        f"{n_orphan_proofs} of {n_proofs} proofs have no valid parent theorem"))

    # B4: zero equations in a math paper with ≥5 nodes
    if n_equations == 0 and n_nodes >= 5:
        results.append((paper_id, "B", "zero_equations", "medium",
                        "0", ">=1",
                        f"Zero equations extracted in {n_nodes}-node math paper"))

    # B5: zero definitions in a math paper with ≥5 nodes (low severity)
    if n_definitions == 0 and n_nodes >= 5:
        results.append((paper_id, "B", "zero_definitions", "low",
                        "0", ">=1",
                        f"Zero definitions extracted in {n_nodes}-node paper"))

    # B6: completely flat DAG (depth 0 or 1) on a paper with ≥5 nodes
    if _HAS_NETWORKX and n_nodes >= 5 and n_edges > 0:
        g = _build_graph(nodes, edges)
        if g is not None and nx.is_directed_acyclic_graph(g):
            try:
                depth = nx.dag_longest_path_length(g)
            except Exception:
                depth = 0
            if depth <= 1:
                results.append((paper_id, "B", "flat_dag", "medium",
                                str(depth), ">=2",
                                f"DAG depth = {depth} on {n_nodes}-node paper (essentially flat)"))

    # =========================================================================
    # CATEGORY C — content oddity (low severity)
    # =========================================================================

    # Collect text for content rules
    texts: List[str] = []
    for n in nodes:
        text = n.get("clean_text") or n.get("statement") or ""
        if text:
            texts.append(text)

    # C1: very short average text length (stripping / OCR failure indicator)
    if texts and n_nodes >= 5:
        avg_len = sum(len(t) for t in texts) / len(texts)
        if avg_len < 30:
            results.append((paper_id, "C", "short_clean_text", "low",
                            f"{avg_len:.1f}", ">=30",
                            f"Average text length = {avg_len:.1f} chars (LaTeX stripping may have failed)"))

    # C2: raw LaTeX commands leaking into clean_text (> 50% of nodes)
    if texts and n_nodes >= 5:
        latex_pattern = re.compile(r"\\[a-zA-Z]+\{")
        n_leaking = sum(1 for t in texts if latex_pattern.search(t))
        if n_leaking > len(texts) * 0.5:
            results.append((paper_id, "C", "raw_latex_in_clean_text", "low",
                            f"{n_leaking}/{len(texts)}", "<50%",
                            f"{n_leaking} of {len(texts)} nodes have raw LaTeX commands in clean_text"))

    # C3: missing names on >90% of nodes
    if n_nodes >= 5:
        n_missing_names = sum(1 for n in nodes if not n.get("name"))
        if n_missing_names > n_nodes * 0.9:
            results.append((paper_id, "C", "missing_names", "low",
                            f"{n_missing_names}/{n_nodes}", "<90%",
                            f"{n_missing_names} of {n_nodes} nodes have no name"))

    # C4: duplicate node IDs
    id_counts = Counter(n.get("id") for n in nodes if n.get("id"))
    dups = sorted([i for i, c in id_counts.items() if c > 1])
    if dups:
        results.append((paper_id, "C", "duplicate_ids", "low",
                        str(len(dups)), "0",
                        f"{len(dups)} duplicate node IDs (first few: {dups[:5]})"))

    # C5: dangling edges (source or target not in the node set)
    n_dangling = 0
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if (s and s not in node_id_set) or (t and t not in node_id_set):
            n_dangling += 1
    if n_dangling > 0:
        results.append((paper_id, "C", "dangling_edges", "low",
                        f"{n_dangling}/{n_edges}", "0",
                        f"{n_dangling} of {n_edges} edges reference nonexistent node IDs"))

    # =========================================================================
    # CATEGORY D — distribution-level (NOT YET IMPLEMENTED — see module header)
    # =========================================================================
    # These rules need a second pass over the collected results + corpus stats.
    # Planned rules:
    #   D1: node count outside [corpus p01, corpus p99]
    #   D2: DAG depth > 2 × corpus median for this paper's page count bucket
    #   D3: theorems-per-page ratio outlier
    # Implementation approach: collect per-paper stats in a first pass, compute
    # corpus medians/percentiles in a second pass, flag outliers in a third pass.
    # Deferred to post-NeurIPS.

    return results


# --- batch driver -------------------------------------------------------------

def detect_anomalies_in_dir(out_dir: str, verbose: bool = False) -> Tuple[List[AnomalyRecord], int, int]:
    """Walk out_dir for paper-graph JSON files and run all rules on each.

    Returns (records_list, n_json_files_scanned, n_papers_flagged).

    Skips stray JSONs that don't look like unified paper graphs (e.g. a
    README.json extracted from an arXiv source tarball). A file is considered
    a paper graph if it parses as a dict with a 'nodes' or 'objects' key.
    """
    out_path = Path(out_dir)
    if not out_path.exists():
        return [], 0, 0

    excluded = {
        "status_log.csv", "validate_report.csv", "anomalies_report.csv",
        "evaluation_results.csv",
    }
    candidate_paths = sorted(out_path.rglob("*.json"))
    candidate_paths = [p for p in candidate_paths if p.name not in excluded]

    # First pass: filter to only files that look like paper graphs.
    # We parse once here, reuse the parsed data in the main loop below to
    # avoid double-parsing.
    json_paths_with_data: List[Tuple[Path, Dict[str, Any]]] = []
    n_skipped_stray = 0
    for p in candidate_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            # JSON parse failures are themselves an anomaly worth recording.
            # We'll turn this into a record later; for now carry a sentinel.
            json_paths_with_data.append((p, {"__parse_error__": str(e)}))
            continue
        if not isinstance(data, dict):
            n_skipped_stray += 1
            continue
        if "nodes" not in data and "objects" not in data:
            n_skipped_stray += 1
            continue
        json_paths_with_data.append((p, data))

    if verbose:
        print(f"[anomalies] scanning {len(json_paths_with_data)} paper-graph JSON files "
              f"in {out_dir} (skipped {n_skipped_stray} stray JSONs)")

    all_records: List[AnomalyRecord] = []
    n_flagged = 0
    for jp, data in json_paths_with_data:
        if "__parse_error__" in data:
            all_records.append((jp.stem, "A", "json_parse_error", "high",
                                data["__parse_error__"], "valid JSON",
                                f"Failed to parse {jp.name}: {data['__parse_error__']}"))
            n_flagged += 1
            continue

        # Best-effort paper_id extraction (try metadata, top-level, then filename)
        paper_id = (
            (data.get("metadata") or {}).get("paper_id")
            or data.get("paper_id")
            or jp.stem.replace("_manual", "").replace("_anthropic", "")
                      .replace("_openai", "").replace("_huggingface", "")
        )

        records = detect_anomalies_for_paper(paper_id, data)
        if records:
            n_flagged += 1
            all_records.extend(records)
            if verbose:
                for r in records:
                    print(f"[anomalies] {r[0]} [{r[1]}.{r[2]}] sev={r[3]}: {r[6]}")

    return all_records, len(json_paths), n_flagged


def write_anomalies_report(records: List[AnomalyRecord], out_path: str) -> None:
    """Write anomaly records to CSV, sorted by severity then category then paper_id."""
    records_sorted = sorted(
        records,
        key=lambda r: (_SEVERITY_ORDER.get(r[3], 9), r[1], r[0], r[2]),
    )
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "paper_id", "category", "rule", "severity",
            "value", "threshold", "message",
        ])
        writer.writerows(records_sorted)


# --- standalone CLI -----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scan a directory of paper JSONs for structural / content "
                    "anomalies and write a report CSV."
    )
    parser.add_argument("--out-dir", required=True,
                        help="Directory containing JSONs to scan (will recurse).")
    parser.add_argument("--report-path", default=None,
                        help="Output report CSV path (default: OUT_DIR/anomalies_report.csv).")
    parser.add_argument("--verbose", action="store_true",
                        help="Print each flagged paper as it's found.")
    args = parser.parse_args()

    records, n_scanned, n_flagged = detect_anomalies_in_dir(args.out_dir, verbose=args.verbose)

    report_path = args.report_path or str(Path(args.out_dir) / "anomalies_report.csv")
    write_anomalies_report(records, report_path)

    print(f"[anomalies] scanned {n_scanned} papers, flagged {n_flagged} "
          f"({len(records)} total anomaly records)")
    print(f"[anomalies] report written to {report_path}")

    # Quick severity breakdown
    sev = Counter(r[3] for r in records)
    if sev:
        print(f"[anomalies] by severity: "
              f"high={sev.get('high', 0)}, medium={sev.get('medium', 0)}, low={sev.get('low', 0)}")


if __name__ == "__main__":
    main()
