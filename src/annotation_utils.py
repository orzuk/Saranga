#!/usr/bin/env python3
"""
annotation_utils.py

Utilities for working with the unified annotation JSON format.
See annotation_schema.md for the full specification.
"""

from typing import Any, Dict, List, Set

# Fields to keep in the student-minimal format
_STUDENT_NODE_FIELDS: Set[str] = {
    "id", "type", "name", "statement", "section",
    "assumptions", "conclusions",
    "proves", "proof_strategy",
}

_STUDENT_EDGE_FIELDS: Set[str] = {"source", "target"}


def strip_to_student_format(annotation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strip a full (research) annotation to the student-minimal format.

    Keeps only the fields listed in annotation_schema.md under "Student (minimal)".
    """
    result: Dict[str, Any] = {}

    if "metadata" in annotation:
        result["metadata"] = annotation["metadata"]

    if "nodes" in annotation:
        result["nodes"] = []
        for node in annotation["nodes"]:
            stripped = {k: v for k, v in node.items() if k in _STUDENT_NODE_FIELDS}
            result["nodes"].append(stripped)

    if "edges" in annotation:
        result["edges"] = []
        for edge in annotation["edges"]:
            stripped = {k: v for k, v in edge.items() if k in _STUDENT_EDGE_FIELDS}
            result["edges"].append(stripped)

    return result


def validate_unified_format(annotation: Dict[str, Any]) -> List[str]:
    """
    Quick validation of a unified-format annotation dict.

    Returns a list of warning/error strings (empty = valid).
    """
    errors = []

    if not isinstance(annotation.get("nodes"), list):
        errors.append("Missing or invalid 'nodes' (expected list)")
        return errors

    if not isinstance(annotation.get("edges"), list):
        errors.append("Missing or invalid 'edges' (expected list)")

    node_ids = set()
    for i, node in enumerate(annotation["nodes"]):
        if "id" not in node:
            errors.append(f"Node {i}: missing 'id'")
        else:
            if node["id"] in node_ids:
                errors.append(f"Node {i}: duplicate id '{node['id']}'")
            node_ids.add(node["id"])

        if "type" not in node:
            errors.append(f"Node {i}: missing 'type'")

        if "statement" not in node:
            errors.append(f"Node {i} ({node.get('id', '?')}): missing 'statement'")

    for i, edge in enumerate(annotation.get("edges", [])):
        if "source" not in edge:
            errors.append(f"Edge {i}: missing 'source'")
        if "target" not in edge:
            errors.append(f"Edge {i}: missing 'target'")
        if edge.get("source") and edge["source"] not in node_ids:
            errors.append(f"Edge {i}: source '{edge['source']}' not in node ids")
        if edge.get("target") and edge["target"] not in node_ids:
            errors.append(f"Edge {i}: target '{edge['target']}' not in node ids")

    return errors
