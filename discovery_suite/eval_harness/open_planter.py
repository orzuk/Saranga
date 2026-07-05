"""Plant synthetic open-problem↔resolution twins with known answers.

Strategy (offline, defensible): take a real theorem node T in paper P (year Y),
and inject an ``open_problem`` node into a DIFFERENT, EARLIER paper Q that poses
exactly T's result as an open question ("It remains open whether <statement>").
The gold link is (planted_problem_in_Q, theorem_T_in_P): a resolver that neither
side cites. Obfuscation levels reword the problem text so retrieval must match on
meaning, not surface form.

For a full-strength eval, swap the rule-based problem phrasing for an LLM
paraphraser (the `paraphraser` hook) — and complement with the retrospective
real-resolution gold described in ROADMAP §4.3.
"""
from __future__ import annotations

import copy
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parent / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from obfuscate import obfuscate  # noqa: E402

THEOREM_TYPES = {"theorem", "lemma", "proposition", "corollary"}


@dataclass
class OpenTwin:
    problem_paper_id: str
    problem_node_id: str
    theorem_paper_id: str
    theorem_node_id: str
    level: str


@dataclass
class PlantedOpen:
    papers: list
    gold: list[OpenTwin] = field(default_factory=list)

    def gold_pairs(self) -> set[frozenset]:
        return {frozenset({f"{g.problem_paper_id}::{g.problem_node_id}",
                           f"{g.theorem_paper_id}::{g.theorem_node_id}"})
                for g in self.gold}

    def gold_levels(self) -> dict[frozenset, str]:
        return {frozenset({f"{g.problem_paper_id}::{g.problem_node_id}",
                           f"{g.theorem_paper_id}::{g.theorem_node_id}"}): g.level
                for g in self.gold}


def _theorem_text(n: dict) -> str:
    body = n.get("clean_text") or n.get("statement") or ""
    if isinstance(body, list):
        body = " ".join(map(str, body))
    return str(body)


def plant_twins(
    papers: Sequence,
    *,
    n_twins: int = 40,
    levels: Sequence[str] = ("L0", "L1", "L2"),
    min_words: int = 12,
    seed: int = 11,
    paraphraser: Optional[object] = None,
) -> PlantedOpen:
    rng = random.Random(seed)
    aug = [copy.copy(p) for p in papers]
    for p in aug:
        p.nodes = [dict(n) for n in p.nodes]

    theorems = [(p, n) for p in aug for n in p.nodes
                if (n.get("type") or "").lower() in THEOREM_TYPES
                and len(_theorem_text(n).split()) >= min_words]
    if not theorems:
        raise ValueError("no eligible theorem nodes to seed twins")

    gold: list[OpenTwin] = []
    for i in range(n_twins):
        level = levels[i % len(levels)]
        src_paper, thm = rng.choice(theorems)
        # earlier target paper (year <= source year), different paper
        cands = [p for p in aug if p.paper_id != src_paper.paper_id
                 and p.year <= src_paper.year]
        if not cands:
            continue
        tgt = rng.choice(cands)

        stmt = _theorem_text(thm)
        posed = f"It remains an open problem whether the following holds. {stmt}"
        posed = obfuscate(posed, level, seed=seed + i, paraphraser=paraphraser)

        pid = f"OPENTWIN_{i}_{thm.get('id')}"
        node = {"id": pid, "type": "open_problem", "name": "Planted open problem",
                "statement": posed, "clean_text": posed, "_planted": True}
        tgt.nodes.append(node)
        gold.append(OpenTwin(
            problem_paper_id=tgt.paper_id, problem_node_id=pid,
            theorem_paper_id=src_paper.paper_id, theorem_node_id=str(thm.get("id")),
            level=level,
        ))
    return PlantedOpen(papers=aug, gold=gold)
