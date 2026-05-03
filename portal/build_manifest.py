#!/usr/bin/env python3
"""
Build portal/data/manifest.json by walking data/{tier1,tier2,tier3-sample,pairs}/.

For each paper JSON, extracts:
    paper_id, title, n_nodes, top_node_types, tier
For each pair JSON, extracts:
    pair_id, paper_a_id, paper_a_title, paper_b_id, paper_b_title,
    relation_type, n_matches

Tolerates both schema shapes:
    - Tier-1 / older: {"metadata": {...}, "nodes": [...], "edges": [...]}
    - v2 / silver:    {"title": ..., "blocks": [...], "relations": [...], ...}
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _read_json(p: Path) -> dict[str, Any] | None:
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  warn: could not parse {p.name}: {e}")
        return None


def summarize_paper(path: Path, tier: int) -> dict[str, Any] | None:
    data = _read_json(path)
    if data is None:
        return None

    # Determine paper_id: prefer explicit, fall back to filename stem.
    if "metadata" in data and isinstance(data["metadata"], dict):
        meta = data["metadata"]
        title = meta.get("title") or ""
        paper_id_raw = meta.get("paper_id") or meta.get("arxiv_id")
    else:
        title = data.get("title") or ""
        paper_id_raw = data.get("paper_id") or data.get("arxiv_id")

    paper_id = paper_id_raw or path.stem
    # Normalize the id used by the URL: must equal the JSON filename (no .json).
    file_id = path.stem

    # Collect node types.
    node_iter: list[dict[str, Any]] = []
    if isinstance(data.get("nodes"), list):
        node_iter = data["nodes"]
    elif isinstance(data.get("blocks"), list):
        node_iter = data["blocks"]

    type_counter: Counter[str] = Counter()
    for n in node_iter:
        t = n.get("type") if isinstance(n, dict) else None
        if t:
            type_counter[t] += 1

    return {
        "paper_id": file_id,           # what URL ?id= expects
        "display_id": str(paper_id),   # human-readable id from inside the JSON
        "title": title,
        "n_nodes": len(node_iter),
        "top_node_types": type_counter.most_common(6),
        "tier": tier,
    }


def summarize_pair(path: Path) -> dict[str, Any] | None:
    data = _read_json(path)
    if data is None:
        return None

    meta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
    a = meta.get("paper_a", {}) if isinstance(meta.get("paper_a"), dict) else {}
    b = meta.get("paper_b", {}) if isinstance(meta.get("paper_b"), dict) else {}

    matches = data.get("matches", [])
    n_matches = len(matches) if isinstance(matches, list) else 0

    return {
        "pair_id": path.stem,                     # what URL ?id= expects
        "alignment_name": meta.get("alignment_name") or path.stem,
        "paper_a_id": a.get("arxiv_id") or "",
        "paper_a_title": a.get("title") or "",
        "paper_b_id": b.get("arxiv_id") or "",
        "paper_b_title": b.get("title") or "",
        "relation_type": meta.get("relation_type") or "",
        "n_matches": n_matches,
        "annotator": meta.get("annotator") or "",
    }


def walk_papers(subdir: str, tier: int) -> list[dict[str, Any]]:
    d = DATA / subdir
    if not d.exists():
        print(f"  (skip: {subdir} does not exist)")
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        s = summarize_paper(p, tier)
        if s is not None:
            out.append(s)
    print(f"  {subdir}: {len(out)} papers")
    return out


def walk_pairs() -> list[dict[str, Any]]:
    d = DATA / "pairs"
    if not d.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        s = summarize_pair(p)
        if s is not None:
            out.append(s)
    print(f"  pairs: {len(out)} pair alignments")
    return out


def main() -> None:
    print(f"Building manifest from {DATA} ...")
    manifest = {
        "papers": {
            "tier1": walk_papers("tier1", 1),
            "tier2": walk_papers("tier2", 2),
            "tier3": walk_papers("tier3-sample", 3),
        },
        "pairs": walk_pairs(),
    }

    out_path = DATA / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    total_papers = sum(len(v) for v in manifest["papers"].values())
    print(f"Wrote {out_path}  ({total_papers} papers, {len(manifest['pairs'])} pairs)")


if __name__ == "__main__":
    main()
