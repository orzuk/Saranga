#!/usr/bin/env python3
"""Validate a student annotation JSON for structural correctness.

Usage:
    python validate_annotation.py annotation.json

Checks:
  1. Required fields present on every node
  2. Edge targets/sources reference existing node IDs
  3. DAG property (no cycles) — cycles indicate misidentified dependencies
  4. Proof nodes reference a valid theorem/lemma via 'proves' field
"""
import json
import sys
from pathlib import Path
from collections import defaultdict


def validate(data: dict) -> list[str]:
    """Return list of error/warning messages. Empty = all good."""
    errors = []
    warnings = []

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if not nodes:
        errors.append("ERROR: No nodes found.")
        return errors

    # --- 1. Required fields ---
    node_ids = set()
    valid_types = {"definition", "theorem", "lemma", "corollary", "proof",
                   "algorithm", "equation", "proposition", "example", "remark"}

    for i, n in enumerate(nodes):
        nid = n.get("id")
        if not nid:
            errors.append(f"ERROR: Node at index {i} has no 'id' field.")
            continue
        if nid in node_ids:
            errors.append(f"ERROR: Duplicate node ID '{nid}'.")
        node_ids.add(nid)

        if not n.get("type"):
            errors.append(f"ERROR: Node '{nid}' has no 'type' field.")
        elif n["type"] not in valid_types:
            warnings.append(f"WARNING: Node '{nid}' has unusual type '{n['type']}'.")

        if not n.get("statement") and not n.get("clean_text"):
            warnings.append(f"WARNING: Node '{nid}' has no 'statement' field.")

        if n.get("type") in ("theorem", "lemma", "corollary"):
            if not n.get("assumptions"):
                warnings.append(f"WARNING: {n['type'].title()} '{nid}' has no assumptions.")
            if not n.get("conclusions"):
                warnings.append(f"WARNING: {n['type'].title()} '{nid}' has no conclusions.")

        if n.get("type") == "proof":
            proves = n.get("proves")
            if not proves:
                warnings.append(f"WARNING: Proof '{nid}' has no 'proves' field.")
            elif proves not in node_ids and proves not in {nd.get("id") for nd in nodes}:
                errors.append(f"ERROR: Proof '{nid}' references '{proves}' which is not a node.")

    # --- 2. Edge references ---
    for i, e in enumerate(edges):
        src = e.get("source")
        tgt = e.get("target")
        if not src or not tgt:
            errors.append(f"ERROR: Edge at index {i} missing 'source' or 'target'.")
            continue
        if src not in node_ids:
            errors.append(f"ERROR: Edge source '{src}' is not a valid node ID.")
        if tgt not in node_ids:
            errors.append(f"ERROR: Edge target '{tgt}' is not a valid node ID.")
        if src == tgt:
            errors.append(f"ERROR: Self-loop on node '{src}'.")

    # --- 3. DAG check (cycle detection) ---
    adj = defaultdict(list)
    in_degree = defaultdict(int)
    all_nodes_in_graph = set()
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src and tgt and src in node_ids and tgt in node_ids:
            adj[src].append(tgt)
            in_degree[tgt] += 0  # ensure key exists
            in_degree[src] += 0
            all_nodes_in_graph.add(src)
            all_nodes_in_graph.add(tgt)

    # Kahn's algorithm
    queue = [n for n in all_nodes_in_graph if in_degree[n] == 0]
    # Recompute in-degrees properly
    in_deg = defaultdict(int)
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src and tgt and src in node_ids and tgt in node_ids:
            in_deg[tgt] += 1
    queue = [n for n in all_nodes_in_graph if in_deg[n] == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adj[node]:
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)

    if visited < len(all_nodes_in_graph):
        # Find nodes in cycle(s)
        cycle_nodes = {n for n in all_nodes_in_graph if in_deg[n] > 0}
        errors.append(
            f"ERROR: Graph contains a cycle! Nodes involved: {sorted(cycle_nodes)}. "
            f"Mathematical dependencies should form a DAG (no circular reasoning). "
            f"Check if an edge direction is reversed."
        )
    else:
        depth = compute_depth(adj, all_nodes_in_graph, in_deg)
        max_depth = max(depth.values()) if depth else 0
        warnings.append(f"INFO: DAG verified. {len(all_nodes_in_graph)} nodes in graph, "
                        f"max depth {max_depth}.")

    # --- 4. Disconnected nodes ---
    connected = all_nodes_in_graph
    disconnected = node_ids - connected
    if disconnected:
        warnings.append(f"WARNING: {len(disconnected)} node(s) have no edges: {sorted(disconnected)}")

    return errors + warnings


def compute_depth(adj, nodes, in_deg_orig):
    """Compute longest-path depth for each node in a DAG."""
    in_deg = defaultdict(int)
    for n in nodes:
        for tgt in adj[n]:
            in_deg[tgt] += 1
    depth = {n: 0 for n in nodes}
    queue = [n for n in nodes if in_deg[n] == 0]
    while queue:
        node = queue.pop(0)
        for neighbor in adj[node]:
            depth[neighbor] = max(depth[neighbor], depth[node] + 1)
            in_deg[neighbor] -= 1
            if in_deg[neighbor] == 0:
                queue.append(neighbor)
    return depth


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = Path(sys.argv[1])
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = validate(data)

    error_count = sum(1 for m in messages if m.startswith("ERROR"))
    warn_count = sum(1 for m in messages if m.startswith("WARNING"))
    info_count = sum(1 for m in messages if m.startswith("INFO"))

    for msg in messages:
        print(msg)

    print(f"\n{'='*50}")
    n_nodes = len(data.get("nodes", []))
    n_edges = len(data.get("edges", []))
    print(f"Summary: {n_nodes} nodes, {n_edges} edges, "
          f"{error_count} errors, {warn_count} warnings")

    if error_count == 0:
        print("PASSED: Annotation is structurally valid.")
    else:
        print("FAILED: Fix errors above before proceeding.")

    sys.exit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
