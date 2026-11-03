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
from graph_io import load_graph

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

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 9}


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

def detect_anomalies_for_paper(
    paper_id: str, data: Dict[str, Any],
    max_cycles_to_report: int = 50, cycles: bool = True,
) -> Tuple[List[AnomalyRecord], Dict[str, Any]]:
    """Run all category A/B/C rules on one paper's JSON.

    Returns (csv_records, detail_dict) where:
    - csv_records: list of AnomalyRecord tuples for the summary CSV
    - detail_dict: per-paper JSON-serializable dict with the guilty nodes,
      edges, cycle lengths, etc. for each anomaly. Written to
      anomalies_detail.json by the caller.
    """
    nodes, edges = load_graph(data)
    results: List[AnomalyRecord] = []
    details: List[Dict[str, Any]] = []  # per-anomaly detail entries

    n_nodes = len(nodes)
    n_edges = len(edges)

    # Count nodes by type
    type_counts: Counter = Counter()
    for node in nodes:
        type_counts[node.get("type") or "unknown"] += 1

    n_theorem_like = sum(type_counts[t] for t in THEOREM_LIKE_TYPES)
    # For ratio checks, only count paper-original theorems (not cited/external)
    n_theorem_like_paper = sum(
        1 for n in nodes
        if n.get("type") in THEOREM_LIKE_TYPES
        and n.get("origin", "paper") == "paper"
    )
    n_proofs = type_counts.get("proof", 0)
    n_definitions = type_counts.get("definition", 0)
    n_equations = type_counts.get("equation", 0)

    # Pre-compute shared structures
    node_id_set = set(n.get("id") for n in nodes if n.get("id"))
    node_type_map = {n.get("id"): n.get("type") for n in nodes if n.get("id")}

    # =========================================================================
    # CATEGORY A — extraction probably failed (high severity)
    # =========================================================================

    # A1: empty JSON
    if n_nodes == 0:
        results.append((paper_id, "A", "empty_json", "high",
                        "0", ">=1", "No nodes extracted at all"))
        detail_dict = {"paper_id": paper_id, "n_nodes": 0, "n_edges": 0,
                       "anomalies": [{"rule": "empty_json", "severity": "high"}]}
        return results, detail_dict

    # A2: tiny paper
    if n_nodes < 3:
        results.append((paper_id, "A", "tiny_paper", "high",
                        str(n_nodes), ">=3",
                        f"Only {n_nodes} nodes extracted — probably a failed extraction"))
        details.append({
            "rule": "tiny_paper", "severity": "high",
            "node_ids": [n.get("id") for n in nodes],
        })

    # A3: no edges but has nodes
    if n_edges == 0 and n_nodes >= 3:
        results.append((paper_id, "A", "no_edges", "high",
                        "0", ">=1",
                        f"{n_nodes} nodes but 0 edges — no connectivity detected"))
        details.append({"rule": "no_edges", "severity": "high"})

    # A4: DAG has cycles (cycles=False skips it: enumerating cycles is slow at corpus scale,
    # and corpus_stats.py computes acyclicity with the validator's check)
    if cycles and _HAS_NETWORKX and n_edges > 0 and n_nodes >= 2:
        g = _build_graph(nodes, [e for e in edges if not e.get("backward")])   # as validate_annotation (graph_checks)
        if g is not None and g.number_of_nodes() > 0 and not nx.is_directed_acyclic_graph(g):
            # Collect actual cycles with their lengths and edges
            cycle_details: List[Dict[str, Any]] = []
            try:
                for i, cycle_nodes in enumerate(nx.simple_cycles(g)):
                    if i >= max_cycles_to_report:
                        break
                    # Build the edges forming this cycle
                    cycle_edges = []
                    for j in range(len(cycle_nodes)):
                        src = cycle_nodes[j]
                        tgt = cycle_nodes[(j + 1) % len(cycle_nodes)]
                        cycle_edges.append([src, tgt])
                    cycle_details.append({
                        "length": len(cycle_nodes),
                        "nodes": cycle_nodes,
                        "node_types": [node_type_map.get(n, "?") for n in cycle_nodes],
                        "edges": cycle_edges,
                    })
                n_cycles = len(cycle_details)
                # Check if there are more we didn't collect
                if n_cycles == max_cycles_to_report:
                    # There might be more; count the rest
                    extra = sum(1 for _ in nx.simple_cycles(g)) - max_cycles_to_report
                    if extra > 0:
                        n_cycles = max_cycles_to_report + extra
            except Exception:
                n_cycles = "?"
                cycle_details = []

            lengths = [c["length"] for c in cycle_details]
            results.append((paper_id, "A", "has_cycles", "high",
                            str(n_cycles), "0",
                            f"{n_cycles} cycle(s): "
                            f"lengths {min(lengths) if lengths else '?'}-{max(lengths) if lengths else '?'}"))
            details.append({
                "rule": "has_cycles", "severity": "high",
                "n_cycles": n_cycles,
                "shortest_cycle_length": min(lengths) if lengths else None,
                "longest_cycle_length": max(lengths) if lengths else None,
                "cycles": cycle_details,
            })

    # A5: all nodes isolated (no edges reference any node)
    if n_edges > 0 and n_nodes >= 3:
        connected_ids = set()
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
            details.append({"rule": "all_isolated", "severity": "high"})

    # =========================================================================
    # CATEGORY B — structural oddity (medium severity)
    # =========================================================================

    # B1: zero proofs with ≥3 paper-original theorem-like
    if n_proofs == 0 and n_theorem_like_paper >= 3:
        thm_ids = [n.get("id") for n in nodes
                   if n.get("type") in THEOREM_LIKE_TYPES
                   and n.get("origin", "paper") == "paper"]
        results.append((paper_id, "B", "zero_proofs_with_theorems", "medium",
                        f"thm={n_theorem_like_paper}, pf=0", ">=1 proof",
                        f"{n_theorem_like_paper} paper-original theorem-like but 0 proofs"))
        details.append({
            "rule": "zero_proofs_with_theorems", "severity": "medium",
            "theorem_like_ids": thm_ids,
        })

    # B2: theorems/proofs ratio outside normal range (paper-original only)
    if n_theorem_like_paper >= 5 and n_proofs > 0:
        ratio = n_proofs / n_theorem_like_paper
        if ratio < 0.3 or ratio > 3.0:
            results.append((paper_id, "B", "theorems_proofs_ratio_off", "medium",
                            f"{ratio:.2f}", "[0.3, 3.0]",
                            f"{n_proofs} proofs / {n_theorem_like_paper} paper-original theorem-like = {ratio:.2f}"))
            details.append({
                "rule": "theorems_proofs_ratio_off", "severity": "medium",
                "ratio": round(ratio, 3),
                "n_proofs": n_proofs, "n_theorem_like": n_theorem_like_paper,
            })

    # B3: orphan proofs (proof's `proves` field missing or dangling)
    orphan_proof_ids: List[Dict[str, Any]] = []
    for node in nodes:
        if node.get("type") == "proof":
            proves = node.get("proves")
            if not proves or proves not in node_id_set:
                orphan_proof_ids.append({
                    "proof_id": node.get("id"),
                    "proves_field": proves,
                    "reason": "missing" if not proves else "dangling (target not in graph)",
                })
    if orphan_proof_ids and n_proofs > 0:
        results.append((paper_id, "B", "orphan_proofs", "medium",
                        f"{len(orphan_proof_ids)}/{n_proofs}", "0",
                        f"{len(orphan_proof_ids)} of {n_proofs} proofs have no valid parent theorem"))
        details.append({
            "rule": "orphan_proofs", "severity": "medium",
            "orphan_proofs": orphan_proof_ids,
        })

    # B4: zero equations in a math paper with ≥5 nodes
    if n_equations == 0 and n_nodes >= 5:
        results.append((paper_id, "B", "zero_equations", "medium",
                        "0", ">=1",
                        f"Zero equations extracted in {n_nodes}-node math paper"))
        details.append({"rule": "zero_equations", "severity": "medium"})

    # B5: zero definitions in a math paper with ≥5 nodes (low severity)
    if n_definitions == 0 and n_nodes >= 5:
        results.append((paper_id, "B", "zero_definitions", "low",
                        "0", ">=1",
                        f"Zero definitions extracted in {n_nodes}-node paper"))
        details.append({"rule": "zero_definitions", "severity": "low"})

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
                details.append({"rule": "flat_dag", "severity": "medium", "depth": depth})

    # B7: most theorem-like nodes have no conclusions (assumption/conclusion
    #     split probably failed for this paper's style)
    if n_theorem_like >= 3:
        thm_nodes = [n for n in nodes if n.get("type") in THEOREM_LIKE_TYPES]
        n_no_conclusions = 0
        n_no_assumptions = 0
        ids_no_conclusions: List[str] = []
        ids_no_assumptions: List[str] = []
        for t in thm_nodes:
            c = t.get("conclusions", [])
            a = t.get("assumptions", [])
            has_c = bool(c and any(s.strip() for s in c if isinstance(s, str)))
            has_a = bool(a and any(s.strip() for s in a if isinstance(s, str)))
            if not has_c:
                n_no_conclusions += 1
                ids_no_conclusions.append(t.get("id", "?"))
            if not has_a:
                n_no_assumptions += 1
                ids_no_assumptions.append(t.get("id", "?"))

        if n_no_conclusions > n_theorem_like * 0.8:
            results.append((paper_id, "B", "most_theorems_no_conclusions", "medium",
                            f"{n_no_conclusions}/{n_theorem_like}", "<80%",
                            f"{n_no_conclusions} of {n_theorem_like} theorem-like nodes have no conclusions"))
            details.append({
                "rule": "most_theorems_no_conclusions", "severity": "medium",
                "n_no_conclusions": n_no_conclusions,
                "ids_no_conclusions": ids_no_conclusions[:30],
            })

        if n_no_assumptions > n_theorem_like * 0.8:
            results.append((paper_id, "B", "most_theorems_no_assumptions", "medium",
                            f"{n_no_assumptions}/{n_theorem_like}", "<80%",
                            f"{n_no_assumptions} of {n_theorem_like} theorem-like nodes have no assumptions"))
            details.append({
                "rule": "most_theorems_no_assumptions", "severity": "medium",
                "n_no_assumptions": n_no_assumptions,
                "ids_no_assumptions": ids_no_assumptions[:30],
            })

    # =========================================================================
    # CATEGORY C — content oddity (low severity)
    # =========================================================================

    # Collect text for content rules
    texts: List[str] = []
    for n in nodes:
        # T2 (Opus) JSONs use 'statement_clean' rather than 'clean_text';
        # check both before falling back to raw 'statement'. Otherwise the
        # raw_latex_in_clean_text rule fires on every T2 paper because
        # 'statement' is the unsanitised LaTeX source by design.
        text = n.get("clean_text") or n.get("statement_clean") or n.get("statement") or ""
        if text:
            texts.append(text)

    # C1: very short average text length
    if texts and n_nodes >= 5:
        avg_len = sum(len(t) for t in texts) / len(texts)
        if avg_len < 30:
            results.append((paper_id, "C", "short_clean_text", "low",
                            f"{avg_len:.1f}", ">=30",
                            f"Average text length = {avg_len:.1f} chars (LaTeX stripping may have failed)"))
            details.append({"rule": "short_clean_text", "severity": "low",
                            "avg_length": round(avg_len, 1)})

    # C2: raw LaTeX commands leaking into clean_text (> 50% of nodes)
    if texts and n_nodes >= 5:
        latex_pattern = re.compile(r"\\[a-zA-Z]+\{")
        n_leaking = sum(1 for t in texts if latex_pattern.search(t))
        if n_leaking > len(texts) * 0.5:
            results.append((paper_id, "C", "raw_latex_in_clean_text", "low",
                            f"{n_leaking}/{len(texts)}", "<50%",
                            f"{n_leaking} of {len(texts)} nodes have raw LaTeX commands in clean_text"))
            details.append({"rule": "raw_latex_in_clean_text", "severity": "low",
                            "n_leaking": n_leaking, "n_texts": len(texts)})

    # C3: missing names on >90% of nodes
    if n_nodes >= 5:
        missing_name_ids = [n.get("id") for n in nodes if not n.get("name")]
        if len(missing_name_ids) > n_nodes * 0.9:
            results.append((paper_id, "C", "missing_names", "low",
                            f"{len(missing_name_ids)}/{n_nodes}", "<90%",
                            f"{len(missing_name_ids)} of {n_nodes} nodes have no name"))
            details.append({
                "rule": "missing_names", "severity": "low",
                "missing_name_ids": missing_name_ids[:50],  # cap at 50 IDs
                "total_missing": len(missing_name_ids),
            })

    # C4: duplicate node IDs
    id_counts = Counter(n.get("id") for n in nodes if n.get("id"))
    dups = sorted([i for i, c in id_counts.items() if c > 1])
    if dups:
        results.append((paper_id, "C", "duplicate_ids", "low",
                        str(len(dups)), "0",
                        f"{len(dups)} duplicate node IDs (first few: {dups[:5]})"))
        details.append({"rule": "duplicate_ids", "severity": "low",
                        "duplicate_ids": dups})

    # C5: dangling edges (source or target not in the node set).
    # Skip `grounded_to` edges: by design their non-paper endpoint references
    # the foundation knowledge graph, not a local node, so they always look
    # dangling under this check.
    dangling_edges: List[Dict[str, str]] = []
    for e in edges:
        if e.get("type") == "grounded_to":
            continue
        s, t = e.get("source"), e.get("target")
        if (s and s not in node_id_set) or (t and t not in node_id_set):
            dangling_edges.append({"source": s, "target": t,
                                   "type": e.get("type", "?")})
    if dangling_edges:
        results.append((paper_id, "C", "dangling_edges", "low",
                        f"{len(dangling_edges)}/{n_edges}", "0",
                        f"{len(dangling_edges)} of {n_edges} edges reference nonexistent node IDs"))
        details.append({
            "rule": "dangling_edges", "severity": "low",
            "dangling_edges": dangling_edges[:50],  # cap at 50
            "total_dangling": len(dangling_edges),
        })

    # =========================================================================
    # CATEGORY D — distribution-level (NOT YET IMPLEMENTED — see module header)
    # =========================================================================
    # Planned rules (second pass over corpus-wide stats):
    #   D1: node count outside [corpus p01, corpus p99]
    #   D2: DAG depth > 2× corpus median for this paper's page count bucket
    #   D3: theorems-per-page ratio outlier

    # If no anomalies at all, emit a PASS record
    if not results:
        results.append((paper_id, "-", "pass", "none",
                        f"{n_nodes}/{n_edges}", "-",
                        f"Clean: {n_nodes} nodes, {n_edges} edges, no anomalies"))

    detail_dict: Dict[str, Any] = {
        "paper_id": paper_id,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "n_anomalies": len(details),
        "anomalies": details,
    }

    return results, detail_dict


# --- batch driver -------------------------------------------------------------

def detect_anomalies_in_dir(
    out_dir: str, verbose: bool = False,
) -> Tuple[List[AnomalyRecord], List[Dict[str, Any]], int, int]:
    """Walk out_dir for paper-graph JSON files and run all rules on each.

    Returns (records_list, detail_list, n_json_files_scanned, n_papers_flagged).

    - records_list: flat list of AnomalyRecord tuples for the summary CSV
    - detail_list: list of per-paper detail dicts (only flagged papers) for
      anomalies_detail.json, containing the guilty nodes, edges, cycle
      lengths, missing-name IDs, etc.

    Skips stray JSONs that don't look like unified paper graphs (e.g. a
    README.json extracted from an arXiv source tarball). A file is considered
    a paper graph if it parses as a dict with a 'nodes' or 'objects' key.
    """
    out_path = Path(out_dir)
    if not out_path.exists():
        return [], [], 0, 0

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
    all_details: List[Dict[str, Any]] = []
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

        records, detail = detect_anomalies_for_paper(paper_id, data)
        has_real_anomaly = any(r[3] != "none" for r in records)
        if has_real_anomaly:
            n_flagged += 1
            all_details.append(detail)  # only store details for flagged papers
        all_records.extend(records)
        if verbose:
            for r in records:
                if r[3] != "none":  # skip PASS rows in verbose output
                    print(f"[anomalies] {r[0]} [{r[1]}.{r[2]}] sev={r[3]}: {r[6]}")

    return all_records, all_details, len(json_paths_with_data), n_flagged


def write_anomalies_detail(detail_list: List[Dict[str, Any]], out_path: str) -> None:
    """Write per-paper anomaly details to JSON.

    Only includes flagged papers (not PASS). Each entry has the guilty
    nodes, edges, cycle lengths, missing-name IDs, etc.
    """
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(detail_list, f, indent=2, default=str)


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

    records, detail_list, n_scanned, n_flagged = detect_anomalies_in_dir(
        args.out_dir, verbose=args.verbose
    )

    report_path = args.report_path or str(Path(args.out_dir) / "anomalies_report.csv")
    write_anomalies_report(records, report_path)

    detail_path = str(Path(args.out_dir) / "anomalies_detail.json")
    write_anomalies_detail(detail_list, detail_path)

    print(f"[anomalies] scanned {n_scanned} papers, flagged {n_flagged} "
          f"({len(records)} total anomaly records)")
    print(f"[anomalies] report  -> {report_path}")
    print(f"[anomalies] details -> {detail_path}")

    # Quick severity breakdown
    sev = Counter(r[3] for r in records)
    if sev:
        print(f"[anomalies] by severity: "
              f"high={sev.get('high', 0)}, medium={sev.get('medium', 0)}, low={sev.get('low', 0)}")


if __name__ == "__main__":
    main()
