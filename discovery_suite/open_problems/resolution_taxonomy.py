"""T-OPEN O4 — the resolution relationship taxonomy, shared by every judge.

Ported from Method E (`prompts/method_e_judge.txt`), which classifies an
(open problem O, candidate theorem T) pair on a seven-way RELATIONSHIP axis and
then rolls that up to a coarse verdict. O4 previously emitted only the coarse
verdict (YES / PARTIAL / NO), which collapsed five very different situations —
a direct proof and an accidental resolution via a new tool were the same label.

Two axes, kept separate on purpose:

  RELATIONSHIP  the fine label; this is the one to analyse.
  VERDICT       the coarse roll-up, DERIVED from the relationship.

The verdict vocabulary stays O4's own YES / PARTIAL / NO rather than Method E's
YES / MAYBE / NO, so every existing verdicts CSV, gold file and downstream
filter keeps working unchanged; PARTIAL is exactly Method E's MAYBE bucket.
`normalize()` accepts MAYBE and maps it to PARTIAL, so a model that answers in
Method E's vocabulary is still parsed correctly.

Two labels are NOT model choices — callers set them:
  UNSPECIFIED  a verdict came back but no parsable relationship line
  PARSE_ERROR  the API call itself failed
"""
from __future__ import annotations

import re

# ── the taxonomy ─────────────────────────────────────────────────────────────
# label -> (verdict roll-up, one-line gloss used in the prompt)
RELATIONSHIPS: dict[str, tuple[str, str]] = {
    "DIRECT": ("YES",
               "T proves exactly what O asks (or its negation)."),
    "GENERALIZES": ("YES",
                    "T proves a more general statement; O follows as a "
                    "corollary or instance."),
    "SPECIAL_HARD": ("YES",
                     "T proves a special case that, via a standard reduction "
                     "known in the field, implies the general question in O."),
    "INDIRECT_TOOL": ("YES",
                      "T uses a method, theorem, or breakthrough M that did not "
                      "exist when O was posed, and applies M in a way that "
                      "resolves O. T does NOT necessarily cite O; the connection "
                      "runs through M. This is the canonical \"accidental "
                      "resolution via new technique\" pattern — high discovery "
                      "value, so do not downgrade it to UNRELATED merely because "
                      "the two papers share no vocabulary."),
    "COUNTER": ("YES",
                "T (or its proof / counterexample) refutes O."),
    "SPECIAL_CORNER": ("PARTIAL",
                       "T proves a special case that is partial progress on O "
                       "but does NOT settle it."),
    "UNRELATED": ("NO",
                  "T and O concern different objects or claims."),
}

VALID_RELATIONSHIPS = frozenset(RELATIONSHIPS)

# Caller-set, never model-chosen.
UNSPECIFIED = "UNSPECIFIED"
PARSE_ERROR = "PARSE_ERROR"

VERDICTS = ("YES", "PARTIAL", "NO")
# Verdicts that count as a hit downstream (retrieval gold, citation gate,
# discovery shortlist). Kept as one definition so the arms cannot drift.
POSITIVE_VERDICTS = frozenset({"YES", "PARTIAL"})
# Relationships that are a genuine resolution, not just progress toward one.
STRONG_RELATIONSHIPS = frozenset(
    r for r, (v, _) in RELATIONSHIPS.items() if v == "YES")


def verdict_for(relationship: str) -> str | None:
    """Coarse verdict for a relationship label, or None if not a model label."""
    ent = RELATIONSHIPS.get((relationship or "").strip().upper())
    return ent[0] if ent else None


def is_positive(verdict: str) -> bool:
    """True for the verdicts that count as a hit. Accepts Method E's MAYBE."""
    v = (verdict or "").strip().upper()
    return ("PARTIAL" if v == "MAYBE" else v) in POSITIVE_VERDICTS


# ── prompt blocks ────────────────────────────────────────────────────────────
def taxonomy_block(indent: str = "  ") -> str:
    """The label menu, formatted for inlining into a judge prompt."""
    width = max(len(r) for r in RELATIONSHIPS)
    lines = []
    for rel, (_verdict, gloss) in RELATIONSHIPS.items():
        head = f"{indent}{rel.ljust(width)}  "
        body = _wrap(gloss, 74 - len(head))
        lines.append(head + body[0])
        lines.extend(" " * len(head) + b for b in body[1:])
    return "\n".join(lines)


def rollup_block(indent: str = "  ") -> str:
    """The RELATIONSHIP -> VERDICT mapping, formatted for the prompt."""
    groups: dict[str, list[str]] = {}
    for rel, (verdict, _g) in RELATIONSHIPS.items():
        groups.setdefault(verdict, []).append(rel)
    return "\n".join(
        f"{indent}{v.ljust(7)} if {', '.join(groups[v])}"
        + (" or the evidence is ambiguous" if v == "PARTIAL" else "")
        for v in VERDICTS if v in groups)


def _wrap(text: str, width: int) -> list[str]:
    import textwrap
    return textwrap.wrap(text, max(30, width)) or [""]


RELATIONSHIP_CHOICES = " | ".join(RELATIONSHIPS)

#: The shared answer-format footer. Every O4 judge must emit these four lines so
#: one parser serves them all.
RESPONSE_FORMAT = (
    "Answer in exactly this format:\n"
    f"RELATIONSHIP: {RELATIONSHIP_CHOICES}\n"
    "VERDICT: YES | PARTIAL | NO\n"
    "SAME_OBJECT: YES | NO\n"
    "JUSTIFICATION: <1-3 sentences>"
)


def classification_block() -> str:
    """The full 'classify then roll up' instruction body for a judge prompt."""
    return (
        "Classify the relationship as exactly one of:\n"
        + taxonomy_block()
        + "\n\nThen roll that up to a verdict:\n"
        + rollup_block()
        + "\n\nSAME_OBJECT is a separate axis: YES only if the two statements "
        "really are about the same mathematical object/quantity, whatever the "
        "relationship. \\-macros (e.g. \\CR, \\SymSubMP) are paper-specific; "
        "judge whether the objects truly coincide, not the wording."
    )


# ── response parsing ─────────────────────────────────────────────────────────
_FIELD_RE = {
    "relationship": re.compile(r"^\s*RELATIONSHIP\s*:\s*(.+)$", re.I | re.M),
    "verdict": re.compile(r"^\s*VERDICT\s*:\s*(.+)$", re.I | re.M),
    "same_object": re.compile(r"^\s*SAME_OBJECT\s*:\s*(.+)$", re.I | re.M),
}
_JUSTIFICATION_RE = re.compile(r"^\s*JUSTIFICATION\s*:\s*(.+)$",
                               re.I | re.M | re.S)
# The model sometimes decorates the label ("**DIRECT**", "DIRECT — because …").
_LABEL_RE = re.compile(r"[A-Z_]+")


def _label(raw: str | None) -> str:
    if not raw:
        return ""
    m = _LABEL_RE.search(raw.upper().replace("*", " "))
    return m.group(0) if m else ""


def parse_response(raw: str) -> dict:
    """Parse a judge reply into
    {relationship, verdict, same_object, justification, mismatch, raw}.

    The RELATIONSHIP is authoritative: when it is a valid label, the verdict is
    derived from it and any contradicting VERDICT line is overridden (and
    flagged via `mismatch`), because the fine label is the more considered
    answer and the roll-up is mechanical. When no valid relationship comes back
    we fall through to the model's own verdict, and only if that is missing too
    do we default to UNRELATED/NO — the same fail-safe Method E uses, so a
    malformed reply can never manufacture a discovery.
    """
    text = raw or ""
    rel = _label(m.group(1) if (m := _FIELD_RE["relationship"].search(text)) else "")
    stated = _label(m.group(1) if (m := _FIELD_RE["verdict"].search(text)) else "")
    if stated == "MAYBE":
        stated = "PARTIAL"
    same = _label(m.group(1) if (m := _FIELD_RE["same_object"].search(text)) else "")
    just = (m.group(1).strip() if (m := _JUSTIFICATION_RE.search(text)) else "")

    mismatch = False
    if rel in VALID_RELATIONSHIPS:
        verdict = verdict_for(rel)
        mismatch = bool(stated) and stated != verdict
    elif stated in VERDICTS:
        rel, verdict = UNSPECIFIED, stated
    else:
        rel, verdict = "UNRELATED", "NO"

    return {
        "relationship": rel,
        "verdict": verdict,
        "same_object": same if same in ("YES", "NO") else "",
        "justification": " ".join(just.split())[:500],
        "mismatch": mismatch,
        "raw": text,
    }


def error_result(exc: object) -> dict:
    """The row to record when the judge call itself failed."""
    return {"relationship": PARSE_ERROR, "verdict": "NO", "same_object": "",
            "justification": f"judge error: {exc}", "mismatch": False, "raw": ""}


def counts(rows, key="relationship") -> dict[str, int]:
    """Ordered tally over the taxonomy (declaration order, then the extras)."""
    order = list(RELATIONSHIPS) + [UNSPECIFIED, PARSE_ERROR]
    tally = {k: 0 for k in order}
    for r in rows:
        lab = str(r.get(key, "") or "").upper()
        tally[lab] = tally.get(lab, 0) + 1
    return {k: v for k, v in tally.items() if v}
