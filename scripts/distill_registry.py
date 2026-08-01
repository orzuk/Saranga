#!/usr/bin/env python3
"""
Rule registry for distillation v2 — stable UIDs, non-destructive gating, recycling.

Fixes three defects measured in the v1 sequential run
(`merged_eval_silver_001_011_v3`, 17 papers):

1. **Rule identity is not stable.** `aggregate` regenerates the whole rules file
   from scratch each paper, so names churn (0 of 10 definition rules survived by
   name from step_05 to step_06) and bodies are lightly rewritten. A rule's
   lifetime is therefore untrackable, and "new rules per paper" — the paper's
   sub-linearity metric — actually measures file regeneration, not accumulation.

2. **Pruning is transient.** `prune_rules` comments rules out in the .py source,
   but the next paper's `aggregate` rewrites that file from the suggestion list,
   which carries no record of what was pruned. Observed: cumulative pruned count
   *falls* across steps (13 -> 12 -> 9 -> 4 -> 3), which is only possible if
   prunes are being undone.

3. **Cost is quadratic and hits the context wall.** The aggregate prompt re-sends
   every suggestion ever made: 19K input tokens at paper 1, 184K at paper 17
   (+~11K/paper). A 200K-context model runs out around paper 18-19 — which is
   almost certainly why the v1 run stopped at 17.

Design
------
The registry is the single source of truth for *what rules exist*; the generated
`.py` file is a **projection** of the active subset, never the authority.

- Every pattern minted gets a monotonic ``uid`` that is never reused.
- Rules are never deleted — only their ``status`` changes
  (``active`` / ``retired``). Gating is a flag, not commented-out code, so a
  prune can be undone and an alpha sweep needs no file snapshots.
- Per-rule ``(tp, fp)`` are cached per paper, so FDR at any alpha is a lookup.
- **Recycling:** before paying for LLM generation, retired rules are tested
  against the new paper's dark-knowledge items. A rule retired at paper 6 for a
  high FDR can legitimately return at paper 12 when new evidence lowers it.

This module is pure bookkeeping — no LLM calls, no imports from the pipeline —
so it is cheap to test and safe to reuse.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

# Codegen must emit this above each module-level pattern so UIDs survive a
# regeneration. Parsed back by `parse_uids_from_source`.
UID_MARKER = re.compile(r'^#\s*@uid:(\d+)\s*$', re.M)
PATTERN_DEF = re.compile(r'^([A-Z][A-Z0-9_]*)\s*=\s*re\.compile', re.M)

STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"


@dataclass
class Rule:
    uid: int
    name: str                     # current variable name (may change)
    group: str                    # definition / proof / theoremlike / ...
    pattern_src: str              # RAW source of the re.compile(...) argument — compilable
    born_paper: str               # paper that first caused this rule to exist
    pattern_key: str = ""         # normalized form — identity only, NEVER compiled
    status: str = STATUS_ACTIVE
    # per-paper hit counts: {paper_id: {"tp": n, "fp": n}}
    stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    history: List[str] = field(default_factory=list)   # audit trail
    aliases: List[str] = field(default_factory=list)   # previous names

    def regex(self):
        """Compile the actual pattern.

        Uses `pattern_src` (raw), never `pattern_key`: normalization strips
        whitespace *inside* the expression, which would silently corrupt any
        regex containing a literal space.
        """
        import ast, re as _re
        try:
            node = ast.parse("f(" + self.pattern_src + ")", mode="eval").body
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                return _re.compile(node.args[0].value, _re.DOTALL)
        except (SyntaxError, ValueError, _re.error):
            pass
        try:
            return _re.compile(self.pattern_src, _re.DOTALL)
        except _re.error:
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


def normalize_pattern(src: str) -> str:
    """Whitespace/comment-insensitive form used for identity matching.

    v1 rewrote rule bodies between steps, so exact-match identity fails (0 hits
    across step_05 -> step_17). Normalizing recovers most of it; the rest is
    handled by explicit UID carry-through in codegen.
    """
    s = re.sub(r'#.*', '', src)
    return re.sub(r'\s+', '', s)


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
    def by_pattern(self, group: str, pattern_src: str) -> Optional[Rule]:
        key = normalize_pattern(pattern_src)
        for r in self.rules.values():
            if r.group == group and r.pattern_key == key:
                return r
        return None

    def mint(self, name: str, group: str, pattern_src: str, born_paper: str) -> Rule:
        """Create a new rule, or return the existing one with the same body.

        Returning the existing rule is what makes UIDs stable across the
        rewrites that broke v1: a lightly-renamed but identical pattern keeps
        its original identity instead of looking like a brand-new rule.
        """
        found = self.by_pattern(group, pattern_src)
        if found is not None:
            if found.name != name:
                found.aliases.append(found.name)
                found.history.append(f"renamed {found.name}->{name} @{born_paper}")
                found.name = name
            return found
        r = Rule(uid=self._next_uid, name=name, group=group,
                 pattern_src=pattern_src,
                 pattern_key=normalize_pattern(pattern_src),
                 born_paper=born_paper)
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

    # -- recycling -------------------------------------------------------
    def recycle_candidates(self, dark_items: List[str], paper_text: str,
                           group: Optional[str] = None,
                           min_match: int = 1) -> List[Rule]:
        """Retired rules that would catch >=min_match of this paper's misses.

        Pure CPU. Run before paying for LLM generation: if an already-known rule
        covers the gap, there is nothing to generate. Directly counteracts the
        v1 pathology where a pruned rule was silently re-invented under a new
        name on a later paper.
        """
        import difflib
        out = []
        for r in self.retired(group):
            pat = r.regex()
            if pat is None:
                continue                      # unparseable source — skip, never crash
            spans = [m.group(0) for m in pat.finditer(paper_text)]
            if not spans:
                continue
            hits = 0
            for item in dark_items:
                it = normalize_pattern(item)
                for s in spans:
                    if difflib.SequenceMatcher(None, it, normalize_pattern(s)).ratio() >= 0.7:
                        hits += 1
                        break
            if hits >= min_match:
                out.append((hits, r))
        out.sort(key=lambda x: -x[0])
        return [r for _, r in out]

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

    def per_paper_deltas(self) -> List[dict]:
        """True added/retired/revived per paper — needs the history trail."""
        rows = []
        for p in self.papers_seen:
            born = sum(1 for r in self.rules.values() if r.born_paper == p)
            ret = sum(1 for r in self.rules.values()
                      for h in r.history if h.startswith("active->retired") and p in h)
            rev = sum(1 for r in self.rules.values()
                      for h in r.history if "recycled" in h and p in h)
            rows.append({"paper": p, "minted": born, "retired": ret, "revived": rev})
        return rows


# ---------------------------------------------------------------------------
# codegen <-> registry glue
# ---------------------------------------------------------------------------

def parse_uids_from_source(src: str) -> Dict[str, int]:
    """Map pattern variable name -> uid, from ``# @uid:N`` markers.

    Codegen is instructed to emit the marker immediately above each pattern; a
    missing marker just means that pattern is treated as new.
    """
    out: Dict[str, int] = {}
    lines = src.split("\n")
    pending: Optional[int] = None
    for line in lines:
        m = UID_MARKER.match(line.strip())
        if m:
            pending = int(m.group(1))
            continue
        d = PATTERN_DEF.match(line)
        if d:
            if pending is not None:
                out[d.group(1)] = pending
            pending = None
        elif line.strip() and not line.strip().startswith("#"):
            pending = None
    return out


def extract_patterns(src: str) -> Dict[str, str]:
    """Map pattern variable name -> raw source of its ``re.compile(...)`` call."""
    out: Dict[str, str] = {}
    for m in re.finditer(r'^([A-Z][A-Z0-9_]*)\s*=\s*re\.compile\(', src, re.M):
        name = m.group(1)
        i = src.index("(", m.end() - 1)
        depth, j = 0, i
        while j < len(src):
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out[name] = src[i + 1:j]
    return out
