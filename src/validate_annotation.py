#!/usr/bin/env python3
# CANONICAL: src/node_types.py and src/edge_types.py.
# This file is derivative; sync it whenever the canonical changes.
"""Validate a student annotation JSON for structural correctness.

Usage:
    python validate_annotation.py annotation.json

Checks:
  1. Required fields present on every node
  2. Edge targets/sources reference existing node IDs
  3. DAG property (no cycles) — cycles indicate misidentified dependencies
  4. Proof nodes reference a valid theorem/lemma via 'proves' field
  5. Level 2 nodes (proof_step, algorithm_step) reference a Level 1 parent
     of compatible type via `parent_id` (or legacy `parent_proof` /
     `parent_algorithm`).
  6. Optional `tags` field is a list of strings; unknown tag values warn
     but do not fail validation.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

# Pull canonical type set + origin validators from the single source of truth
# in node_types.py (avoid hard-coded lists going stale).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from node_types import (  # noqa: E402
    ALL_TYPES,
    ORIGIN_VALUES,
    LEVEL_1_TYPES,
    LEVEL_2_TYPES,
    LEVEL_2_PARENT_TYPE,
    TAGS_VOCABULARY,
    is_known_tag,
    has_antecedent,
    PROVABLE,
)
from edge_types import (  # noqa: E402
    ALL_TYPES as ALL_EDGE_TYPES,
    normalize_edge_type,
    get_allowed_source_types,
    get_allowed_target_types,
)


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
    valid_types = set(ALL_TYPES)

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

        # Origin field: optional, but if present must be 'paper' or 'external'.
        # Missing = defaults to 'paper' (backwards compat for legacy JSONs).
        if "origin" in n and n["origin"] not in ORIGIN_VALUES:
            warnings.append(
                f"WARNING: Node '{nid}' has unknown origin "
                f"'{n['origin']}' (expected one of {sorted(ORIGIN_VALUES)})."
            )
        if n.get("origin") == "external" and not n.get("origin_citation"):
            warnings.append(
                f"WARNING: External-origin node '{nid}' has no "
                f"'origin_citation' field; consider naming the cited source."
            )

        # Optional `tags` field: list[str]. Unknown tags warn-not-reject.
        if "tags" in n:
            tags = n["tags"]
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                errors.append(
                    f"ERROR: Node '{nid}' has malformed 'tags' field "
                    f"(must be list[str])."
                )
            else:
                ntype = n.get("type")
                vocab = TAGS_VOCABULARY.get(ntype, [])
                if vocab:
                    for t in tags:
                        if not is_known_tag(ntype, t):
                            warnings.append(
                                f"WARNING: Node '{nid}' (type='{ntype}') has "
                                f"unknown tag '{t}'; not in suggested vocabulary."
                            )

        if n.get("type") in PROVABLE:
            statement = n.get("statement") or n.get("clean_text") or ""
            # Regime A/B/C rule (see node_types.has_antecedent):
            # - Warn on missing assumptions ONLY if the statement contains
            #   an explicit antecedent marker (if/let/suppose/...). A bare
            #   inequality or identity is allowed to have empty assumptions.
            # - Warn on missing conclusions always — every theorem-like
            #   node asserts some fact.
            if not n.get("assumptions") and has_antecedent(statement):
                warnings.append(
                    f"WARNING: {n['type'].title()} '{nid}' has no "
                    f"assumptions but its statement contains an explicit "
                    f"antecedent marker (if/let/suppose/...)."
                )
            if not n.get("conclusions"):
                warnings.append(f"WARNING: {n['type'].title()} '{nid}' has no conclusions.")

        if n.get("type") == "proof":
            proves = n.get("proves")
            if not proves:
                warnings.append(f"WARNING: Proof '{nid}' has no 'proves' field.")
            elif proves not in node_ids and proves not in {nd.get("id") for nd in nodes}:
                errors.append(f"ERROR: Proof '{nid}' references '{proves}' which is not a node.")

    # --- 1b. Level 2 nodes must reference a Level 1 parent of correct type ---
    # Build a lookup of node_id -> type for cross-checking parent references.
    node_type_by_id = {nd.get("id"): nd.get("type") for nd in nodes if nd.get("id")}
    for n in nodes:
        ntype = n.get("type")
        if ntype not in LEVEL_2_TYPES:
            continue
        nid = n.get("id")
        # Accept either generic `parent_id` or legacy type-specific fields.
        legacy_field = "parent_proof" if ntype == "proof_step" else "parent_algorithm"
        parent_ref = n.get("parent_id") or n.get(legacy_field)
        if not parent_ref:
            errors.append(
                f"ERROR: Level-2 node '{nid}' (type='{ntype}') has no "
                f"'parent_id' (or legacy '{legacy_field}') reference."
            )
            continue
        if parent_ref not in node_type_by_id:
            errors.append(
                f"ERROR: Level-2 node '{nid}' references parent "
                f"'{parent_ref}' which is not a node in this annotation."
            )
            continue
        expected_parent_type = LEVEL_2_PARENT_TYPE.get(ntype)
        actual_parent_type = node_type_by_id.get(parent_ref)
        if expected_parent_type and actual_parent_type != expected_parent_type:
            errors.append(
                f"ERROR: Level-2 node '{nid}' (type='{ntype}') references "
                f"parent '{parent_ref}' of type '{actual_parent_type}'; "
                f"expected parent type '{expected_parent_type}'."
            )

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

        # Edge type validation: must be a known canonical edge type, and
        # source/target node types should match any constraints declared in
        # edge_types.EDGE_METADATA (warn-only, mirroring `parent_id` style).
        etype_raw = e.get("type") or e.get("relation_type")
        if etype_raw and etype_raw not in ALL_EDGE_TYPES:
            warnings.append(
                f"WARNING: Edge {i} ({src}→{tgt}) has unknown type "
                f"'{etype_raw}'; expected one of {sorted(ALL_EDGE_TYPES)}."
            )
        etype = normalize_edge_type(etype_raw)
        allowed_src = get_allowed_source_types(etype)
        allowed_tgt = get_allowed_target_types(etype)
        src_type = node_type_by_id.get(src)
        tgt_type = node_type_by_id.get(tgt)
        if allowed_src is not None and src_type is not None and src_type not in allowed_src:
            warnings.append(
                f"WARNING: Edge {i} type='{etype}' has source '{src}' of "
                f"type '{src_type}'; expected one of {sorted(allowed_src)}."
            )
        if allowed_tgt is not None and tgt_type is not None and tgt_type not in allowed_tgt:
            warnings.append(
                f"WARNING: Edge {i} type='{etype}' has target '{tgt}' of "
                f"type '{tgt_type}'; expected one of {sorted(allowed_tgt)}."
            )

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


def validate_file(path: Path, verbose: bool = True) -> tuple[int, int, int, int]:
    """Validate a single JSON file. Returns (nodes, edges, errors, warnings)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = validate(data)

    error_count = sum(1 for m in messages if m.startswith("ERROR"))
    warn_count = sum(1 for m in messages if m.startswith("WARNING"))
    n_nodes = len(data.get("nodes", []))
    n_edges = len(data.get("edges", []))

    if verbose:
        for msg in messages:
            print(msg)
        print(f"\n{'='*50}")
        print(f"Summary: {n_nodes} nodes, {n_edges} edges, "
              f"{error_count} errors, {warn_count} warnings")
        if error_count == 0:
            print("PASSED: Annotation is structurally valid.")
        else:
            print("FAILED: Fix errors above before proceeding.")

    return n_nodes, n_edges, error_count, warn_count


def resolve_paths(args: list[str]) -> list[Path]:
    """Resolve a list of paths/globs/directories to JSON files."""
    import glob
    files = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            files.extend(sorted(p.glob("*.json")))
        elif "*" in arg or "?" in arg:
            files.extend(sorted(Path(m) for m in glob.glob(arg)))
        elif p.is_file():
            files.append(p)
        else:
            print(f"WARNING: '{arg}' not found, skipping.")
    return files


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_annotation.py <file.json | directory | glob-pattern> ...")
        print("Examples:")
        print("  python validate_annotation.py annotation.json")
        print("  python validate_annotation.py papers/gold/")
        print("  python validate_annotation.py 'papers/gold/paper*.json'")
        print("  python validate_annotation.py file1.json file2.json file3.json")
        sys.exit(1)

    files = resolve_paths(sys.argv[1:])

    if not files:
        print("No JSON files found.")
        sys.exit(1)

    # Single file: verbose output
    if len(files) == 1:
        _, _, errors, _ = validate_file(files[0], verbose=True)
        sys.exit(1 if errors > 0 else 0)

    # Multiple files: summary table
    total_nodes, total_edges, total_errors, total_warnings = 0, 0, 0, 0
    results = []

    for f in files:
        try:
            n, e, errs, warns = validate_file(f, verbose=False)
            status = "PASS" if errs == 0 else "FAIL"
            results.append((f.name, n, e, errs, warns, status))
            total_nodes += n
            total_edges += e
            total_errors += errs
            total_warnings += warns
        except Exception as ex:
            results.append((f.name, 0, 0, 1, 0, f"ERROR: {ex}"))
            total_errors += 1

    # Print table
    print(f"\n{'File':<35} {'Nodes':>6} {'Edges':>6} {'Errors':>7} {'Warns':>6} {'Status':>6}")
    print("-" * 72)
    for name, n, e, errs, warns, status in results:
        print(f"{name:<35} {n:>6} {e:>6} {errs:>7} {warns:>6} {status:>6}")
    print("-" * 72)
    print(f"{'TOTAL':<35} {total_nodes:>6} {total_edges:>6} {total_errors:>7} {total_warnings:>6}")
    print(f"\n{len(files)} files validated: "
          f"{sum(1 for r in results if r[5] == 'PASS')} passed, "
          f"{sum(1 for r in results if r[5] != 'PASS')} failed.")

    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
