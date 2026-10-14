"""Read a paper graph: (nodes, edges) from the unified JSON, or from the legacy
{objects, relations} schema (objects as an id-keyed dict or a list)."""
import json
from pathlib import Path


def load_graph(src) -> tuple[list, list]:
    """src: a path or an already-loaded dict. Types are returned as stored (see node_types /
    edge_types to normalise them); a legacy relation without a type is 'uses'."""
    d = src if isinstance(src, dict) else json.loads(Path(src).read_text(encoding="utf-8"))
    if "nodes" in d:
        return d.get("nodes") or [], d.get("edges") or []
    objs = d.get("objects") or {}
    nodes = [dict(o, id=o.get("id", k), type=o.get("type", o.get("kind"))) for k, o in
             (objs.items() if isinstance(objs, dict) else ((o.get("id"), o) for o in objs))]
    edges = [{"source": r.get("source_id") or r.get("source"), "target": r.get("target_id") or r.get("target"),
              "type": r.get("relation_type") or r.get("type") or "uses"} for r in d.get("relations") or []]
    return nodes, edges
