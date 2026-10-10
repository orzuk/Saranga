#!/usr/bin/env python3
"""
Rule registry: stable identities, non-destructive gating, per-paper statistics.

The registry is the single source of truth for which rules exist. Every rule
gets a monotonic ``uid`` that is never reused; rules are never deleted, only
their ``status`` changes (``active`` / ``retired``), with an audit trail in
``history``. Per-rule true/false positives are kept per paper, so a rule's
false-discovery rate on any set of papers is a lookup.

A rule is a regex (``pattern_src``, compiled with ``spec["flags"]``) plus a
small algorithm-specific record ``spec`` (for the unit distillation: the node
type, how much text a match claims, an optional context condition). Identity
is ``pattern_key``: the regex and the spec together, so the same regex with a
different type or span is a different rule.

Pure bookkeeping: no LLM calls, no imports from the pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"


@dataclass
class Rule:
    uid: int
    name: str                     # short readable name (may change)
    group: str                    # what the rule produces (node type, or rule group)
    pattern_src: str              # the regex itself
    born_paper: str               # where it was first proposed (paper or round)
    pattern_key: str = ""         # identity: regex + spec, never compiled
    status: str = STATUS_ACTIVE
    # per-paper hit counts: {paper_id: {"tp": n, "fp": n}}
    stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    history: List[str] = field(default_factory=list)   # audit trail
    aliases: List[str] = field(default_factory=list)   # previous names
    spec: Dict = field(default_factory=dict)           # algorithm-specific fields

    def regex(self):
        """The compiled pattern, or None if it does not compile. Flags come from
        spec["flags"] (letters of re's inline flags: "i", "s", "m", "x")."""
        flags = 0
        for ch in str(self.spec.get("flags", "")):
            flags |= {"i": re.I, "s": re.S, "m": re.M, "x": re.X}.get(ch, 0)
        try:
            return re.compile(self.pattern_src, flags)
        except re.error:
            return None

    # -- derived ---------------------------------------------------------
    def totals(self, papers: Optional[List[str]] = None):
        keys = self.stats.keys() if papers is None else [p for p in papers if p in self.stats]
        tp = sum(self.stats[k].get("tp", 0) for k in keys)
        fp = sum(self.stats[k].get("fp", 0) for k in keys)
        return tp, fp

    def fdr(self, papers: Optional[List[str]] = None) -> float:
        """FP / (FP + TP). A rule with no observations gets 1.0 (maximally
        suspect) — same convention as prune_rules, so gating agrees with it."""
        tp, fp = self.totals(papers)
        return fp / (fp + tp) if (fp + tp) else 1.0


def rule_key(pattern_src: str, spec: Optional[Dict] = None) -> str:
    """Identity of a rule: the exact regex plus its spec. Nothing is stripped from
    the regex (a space, a '#' or a newline can be part of what it matches)."""
    return json.dumps([pattern_src, spec or {}], sort_keys=True)


class RuleRegistry:
    """Append-only registry of every rule ever minted."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.rules: Dict[int, Rule] = {}
        self._next_uid = 1
        self.papers_seen: List[str] = []

    # -- persistence -----------------------------------------------------
    @classmethod
    def load(cls, path) -> "RuleRegistry":
        r = cls(path)
        p = Path(path)
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            r._next_uid = d.get("next_uid", 1)
            r.papers_seen = d.get("papers_seen", [])
            for raw in d.get("rules", []):
                r.rules[raw["uid"]] = Rule(**raw)
        return r

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "next_uid": self._next_uid,
            "papers_seen": self.papers_seen,
            "rules": [asdict(x) for x in sorted(self.rules.values(), key=lambda r: r.uid)],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # -- minting / lookup ------------------------------------------------
    def by_pattern(self, group: str, pattern_src: str,
                   spec: Optional[Dict] = None) -> Optional[Rule]:
        key = rule_key(pattern_src, spec)
        for r in self.rules.values():
            if r.group == group and r.pattern_key == key:
                return r
        return None

    def mint(self, name: str, group: str, pattern_src: str, born_paper: str,
             spec: Optional[Dict] = None) -> Rule:
        """Create a new rule, or return the existing one with the same regex and
        spec (a renamed but identical rule keeps its uid)."""
        found = self.by_pattern(group, pattern_src, spec)
        if found is not None:
            if found.name != name:
                found.aliases.append(found.name)
                found.history.append(f"renamed {found.name}->{name} @{born_paper}")
                found.name = name
            return found
        r = Rule(uid=self._next_uid, name=name, group=group,
                 pattern_src=pattern_src,
                 pattern_key=rule_key(pattern_src, spec),
                 born_paper=born_paper, spec=dict(spec or {}))
        r.history.append(f"minted @{born_paper}")
        self.rules[r.uid] = r
        self._next_uid += 1
        return r

    # -- stats -----------------------------------------------------------
    def record(self, uid: int, paper_id: str, tp: int, fp: int) -> None:
        r = self.rules[uid]
        r.stats[paper_id] = {"tp": int(tp), "fp": int(fp)}

    def note_paper(self, paper_id: str) -> None:
        if paper_id not in self.papers_seen:
            self.papers_seen.append(paper_id)

    # -- gating (non-destructive) ----------------------------------------
    def apply_gate(self, alpha: float, papers: Optional[List[str]] = None,
                   keep_unobserved: bool = True) -> Dict[str, int]:
        """Set status from FDR <= alpha. Reversible: nothing is deleted.

        `keep_unobserved` keeps rules that have fired on nothing yet (they have
        no evidence against them, and retiring them would make the very first
        gate wipe every freshly-minted rule).
        """
        act = ret = 0
        for r in self.rules.values():
            tp, fp = r.totals(papers)
            if (tp + fp) == 0 and keep_unobserved:
                new = STATUS_ACTIVE
            else:
                new = STATUS_ACTIVE if r.fdr(papers) <= alpha else STATUS_RETIRED
            if new != r.status:
                r.history.append(
                    f"{r.status}->{new} @alpha={alpha:.2f} fdr={r.fdr(papers):.2f}")
                r.status = new
            act += (new == STATUS_ACTIVE)
            ret += (new == STATUS_RETIRED)
        return {"active": act, "retired": ret}

    def active(self, group: Optional[str] = None) -> List[Rule]:
        return [r for r in self.rules.values()
                if r.status == STATUS_ACTIVE and (group is None or r.group == group)]

    def retired(self, group: Optional[str] = None) -> List[Rule]:
        return [r for r in self.rules.values()
                if r.status == STATUS_RETIRED and (group is None or r.group == group)]

    def retire_with(self, rule: "Rule", reason: str) -> None:
        """Retire one rule, recording why (nothing is deleted)."""
        if rule.status != STATUS_RETIRED:
            rule.history.append(f"{rule.status}->{STATUS_RETIRED} ({reason})")
            rule.status = STATUS_RETIRED

    def revive(self, uid: int, paper_id: str, reason: str = "recycled") -> None:
        r = self.rules[uid]
        r.history.append(f"{r.status}->active @{paper_id} ({reason})")
        r.status = STATUS_ACTIVE

    # -- reporting -------------------------------------------------------
    def lineage_table(self) -> List[dict]:
        """Per-rule life story — the table v1 could not produce."""
        rows = []
        for r in sorted(self.rules.values(), key=lambda x: x.uid):
            tp, fp = r.totals()
            rows.append({
                "uid": r.uid, "name": r.name, "group": r.group,
                "born": r.born_paper, "status": r.status,
                "papers_fired": len(r.stats), "tp": tp, "fp": fp,
                "fdr": round(r.fdr(), 3),
                "revivals": sum(1 for h in r.history if "recycled" in h),
                "renames": len(r.aliases),
            })
        return rows
