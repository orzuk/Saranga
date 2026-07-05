"""Plant an alignment clone: a notation-perturbed copy with KNOWN correspondence.

Take one paper, mechanically rename variables / swap synonyms / reword each node
(and optionally reorder), producing a "translated" copy whose node↔node gold
mapping we know exactly. The aligner's job is to recover that permutation; we
score the fraction of nodes matched to their true image vs perturbation strength.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parent / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import Paper  # noqa: E402
from obfuscate import obfuscate  # noqa: E402


def clone_perturbed(paper: Paper, level: str = "L1", *, seed: int = 0,
                    paraphraser=None) -> tuple[Paper, dict[str, str]]:
    """Return (clone_paper, gold_mapping orig_node_id -> clone_node_id)."""
    mapping: dict[str, str] = {}
    new_nodes = []
    for i, n in enumerate(paper.nodes):
        oid = str(n.get("id"))
        cid = f"C_{oid}"
        mapping[oid] = cid
        m = dict(n)
        m["id"] = cid
        body = n.get("clean_text") or n.get("statement") or ""
        if isinstance(body, list):
            body = " ".join(map(str, body))
        obf = obfuscate(str(body), level, seed=seed + i, paraphraser=paraphraser)
        m["clean_text"] = obf
        m["statement"] = obf
        if m.get("name"):
            m["name"] = obfuscate(str(m["name"]), level, seed=seed + 1000 + i,
                                  paraphraser=paraphraser)
        new_nodes.append(m)

    new_edges = []
    for e in paper.edges:
        s, t = str(e.get("source")), str(e.get("target"))
        if s in mapping and t in mapping:
            ce = dict(e)
            ce["source"], ce["target"] = mapping[s], mapping[t]
            new_edges.append(ce)

    clone = Paper(paper_id=f"{paper.paper_id}__clone", year=paper.year,
                  category=paper.category, path=paper.path,
                  nodes=new_nodes, edges=new_edges)
    return clone, mapping


def alignment_accuracy(matching: dict[str, str], gold: dict[str, str]) -> float:
    """Fraction of gold node pairs the matching recovered."""
    if not gold:
        return 0.0
    correct = sum(1 for o, c in gold.items() if matching.get(o) == c)
    return correct / len(gold)
