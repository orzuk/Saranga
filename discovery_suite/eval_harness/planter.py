"""Plant known-answer positives into the corpus for evaluation.

Fixes the old pipeline's core weakness — no arXiv ground truth. We copy a
*source* node into a *target* paper at a chosen obfuscation level and record the
(source, planted) pair as gold. A detector's job is to re-surface these; the
detection-vs-obfuscation curve is read off the recovery rate per level.

Returns augmented papers (deep-ish copies; originals untouched) plus a gold list.
The planter never mutates the input Paper objects.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Optional, Sequence

from obfuscate import LEVELS, Paraphraser, obfuscate


@dataclass
class PlantRecord:
    target_paper_id: str
    target_node_id: str        # id of the injected node
    source_paper_id: str
    source_node_id: str
    level: str
    node_type: str


@dataclass
class PlantedCorpus:
    papers: list                # augmented Paper-like objects (with .nodes)
    gold: list[PlantRecord] = field(default_factory=list)

    def gold_pairs(self) -> set[frozenset]:
        """Undirected gold as {planted_key, source_key} frozensets."""
        return {
            frozenset({f"{g.source_paper_id}::{g.source_node_id}",
                       f"{g.target_paper_id}::{g.target_node_id}"})
            for g in self.gold
        }


def _eligible(node: dict, min_words: int) -> bool:
    body = node.get("clean_text") or node.get("statement") or ""
    if isinstance(body, list):
        body = " ".join(map(str, body))
    return len(str(body).split()) >= min_words


def plant(
    papers: Sequence,
    *,
    n_plants: int = 60,
    levels: Sequence[str] = tuple(LEVELS[:3]),   # L0,L1,L2 by default
    min_words: int = 12,
    seed: int = 7,
    paraphraser: Optional[Paraphraser] = None,
) -> PlantedCorpus:
    """Inject `n_plants` reuse cases, evenly spread across `levels`."""
    rng = random.Random(seed)
    aug = [copy.copy(p) for p in papers]
    for p in aug:
        p.nodes = [dict(n) for n in p.nodes]   # shallow-copy node dicts
    by_id = {p.paper_id: p for p in aug}

    # Candidate source nodes with enough text.
    sources: list[tuple[str, dict]] = [
        (p.paper_id, n) for p in aug for n in p.nodes if _eligible(n, min_words)
    ]
    if len(sources) < 2:
        raise ValueError("not enough eligible source nodes to plant")

    gold: list[PlantRecord] = []
    for i in range(n_plants):
        level = levels[i % len(levels)]
        src_pid, src_node = rng.choice(sources)
        # Choose a distinct target paper.
        tgt = rng.choice(aug)
        tries = 0
        while tgt.paper_id == src_pid and tries < 10:
            tgt = rng.choice(aug)
            tries += 1
        if tgt.paper_id == src_pid:
            continue

        body = src_node.get("clean_text") or src_node.get("statement") or ""
        if isinstance(body, list):
            body = " ".join(map(str, body))
        obf = obfuscate(str(body), level, seed=seed + i, paraphraser=paraphraser)

        new_id = f"PLANT_{i}_{src_node.get('id')}"
        new_node = dict(src_node)
        new_node["id"] = new_id
        new_node["clean_text"] = obf
        new_node["statement"] = obf
        new_node["_planted"] = True
        tgt.nodes.append(new_node)

        gold.append(PlantRecord(
            target_paper_id=tgt.paper_id, target_node_id=new_id,
            source_paper_id=src_pid, source_node_id=str(src_node.get("id")),
            level=level, node_type=str(src_node.get("type", "")),
        ))
    return PlantedCorpus(papers=aug, gold=gold)
