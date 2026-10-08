"""
Schema-text generator for runtime prompt assembly (Option B).

Renders the canonical node/edge type definitions from `node_types.py` and
`edge_types.py` as natural-language LLM prompt text. Prompt files contain
placeholders (`{{SCHEMA_BLOCK}}`, `{{TAGS_FOR_THIS_TYPE}}`) that get filled
in here, so editing the schema in one place (`src/node_types.py`,
`src/edge_types.py`) automatically updates every extraction prompt.

CLI: ``python3 src/schema_for_prompts.py --verbosity standard``

Public API:
    get_schema_block(verbosity="standard") -> str
    get_tags_for_type(node_type) -> str
    render_prompt(prompt_text, node_type_for_tags=None) -> str
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Ensure local imports work whether this is run as a module or as a script.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import node_types as NT  # noqa: E402  (local import after sys.path tweak)
import edge_types as ET  # noqa: E402


# ── Type-group buckets (presentation order in the schema block) ─────────

_THEOREM_LIKE_ORDER = [
    NT.THEOREM, NT.LEMMA, NT.PROPOSITION,
    NT.COROLLARY, NT.CLAIM, NT.CONJECTURE,
]
_FOUNDATIONAL_ORDER = [NT.DEFINITION, NT.PROOF]
_PEDAGOGICAL_ORDER = [NT.EXAMPLE, NT.EXERCISE]
_OTHER_LEVEL1_ORDER = [
    NT.PROBLEM, NT.OPEN_PROBLEM, NT.ASSUMPTION,
    NT.EQUATION, NT.ALGORITHM, NT.REMARK,
]
_LEVEL2_ORDER = [NT.PROOF_STEP, NT.ALGORITHM_STEP]

# Edge-type presentation order.
_EDGE_ORDER = [
    ET.USES, ET.GENERALIZES, ET.SPECIALIZES,
    ET.PROVES, ET.ILLUSTRATES, ET.TESTS, ET.RESOLVES,
]


# ── One-line descriptions per type (kept short for "standard" verbosity) ─

_TYPE_ONE_LINER = {
    NT.THEOREM:        "labeled or numbered theorem; carries assumptions and conclusions",
    NT.LEMMA:          "labeled or numbered lemma; subordinate result used to prove a theorem",
    NT.PROPOSITION:    "labeled or numbered proposition; intermediate proven result",
    NT.COROLLARY:      "labeled or numbered corollary; consequence of a previous result",
    NT.CLAIM:          "informal assertion (\"Claim\", \"Fact\", \"Observation\") with a statement",
    NT.CONJECTURE:     "explicitly labeled unproven claim with a stated believed answer",
    NT.DEFINITION:     "formal introduction of a named concept (\\begin{definition}, \"We define X as...\")",
    NT.PROOF:          "proof of a theorem-like result; linked via a `proves` edge",
    NT.EXAMPLE:        "worked illustration of a concept; linked via `illustrates`",
    NT.EXERCISE:       "pedagogical problem for the reader; linked via `tests`",
    NT.PROBLEM:        "named or formulated formal mathematical problem (optimization, decision, ...)",
    NT.OPEN_PROBLEM:   "unsolved mathematical question with no known solution (e.g. \"is P=NP?\")",
    NT.EQUATION:       "explicitly labeled / numbered equation referenced by number",
    NT.ALGORITHM:      "pseudocode or step-by-step procedure",
    NT.REMARK:         "author observation that adds context but is not a theorem or definition",
    NT.ASSUMPTION:     "\\begin{assumption} block declaring standing assumptions for a section/theorem cluster",
    NT.PROOF_STEP:     "one logical move within a proof; references parent PROOF via `parent_id`",
    NT.ALGORITHM_STEP: "one numbered pseudocode line within an algorithm; references parent ALGORITHM via `parent_id`",
}

_EDGE_ONE_LINER = {
    ET.USES:        "B uses A — generic dependency (default)",
    ET.GENERALIZES: "B generalizes A — B is more general than A (subtype of `uses`)",
    ET.SPECIALIZES: "B specializes A — B is a special case of A (subtype of `uses`)",
    ET.PROVES:      "B proves A — B is a proof establishing theorem A",
    ET.ILLUSTRATES: "B illustrates A — B is an example demonstrating concept A",
    ET.TESTS:       "B tests A — B is an exercise testing concept A",
    ET.RESOLVES:    ("B resolves A — B is a theorem-like result settling "
                     "problem/open_problem/conjecture A, or an algorithm "
                     "solving problem A"),
}


# ── Verbose docstring extraction ────────────────────────────────────────

def _extract_type_docstring(node_type: str) -> str:
    """Pull the canonical multi-line description for `node_type` from the
    one-liner table; the full per-type prose lives as comments in
    node_types.py and is not Python-importable. Falls back to a stub.
    """
    return _TYPE_ONE_LINER.get(node_type, f"(no description for {node_type})")


# ── Main API ────────────────────────────────────────────────────────────

def get_schema_block(verbosity: str = "standard") -> str:
    """Render the schema as natural-language LLM prompt text.

    Parameters
    ----------
    verbosity : {"compact", "standard", "verbose"}
        compact   — 1-line list of types per group (tight token budget)
        standard  — one-line description per type (default)
        verbose   — full description per type, plus tags vocabulary, plus
                    Level 1 / Level 2 explanation

    Returns
    -------
    str : a multi-line block suitable for substitution into a prompt.
    """
    if verbosity not in {"compact", "standard", "verbose"}:
        raise ValueError(
            f"verbosity must be one of compact/standard/verbose, got {verbosity!r}"
        )

    n_l1 = len(NT.LEVEL_1_TYPES)
    n_l2 = len(NT.LEVEL_2_TYPES)

    lines: list[str] = []
    lines.append(f"NODE TYPES ({n_l1} Level-1, {n_l2} Level-2):")
    lines.append("")

    if verbosity == "compact":
        lines.append(
            f"Theorem-like ({len(_THEOREM_LIKE_ORDER)}): "
            + ", ".join(_THEOREM_LIKE_ORDER) + "."
        )
        lines.append(
            f"Foundational ({len(_FOUNDATIONAL_ORDER)}): "
            + ", ".join(_FOUNDATIONAL_ORDER) + "."
        )
        lines.append(
            f"Pedagogical ({len(_PEDAGOGICAL_ORDER)}): "
            + ", ".join(_PEDAGOGICAL_ORDER) + "."
        )
        lines.append(
            f"Other content ({len(_OTHER_LEVEL1_ORDER)}): "
            + ", ".join(_OTHER_LEVEL1_ORDER) + "."
        )
        lines.append(
            f"Level-2 sub-block ({len(_LEVEL2_ORDER)}; when to emit them: \"Level-2 steps\"): "
            + ", ".join(_LEVEL2_ORDER) + "."
        )
        lines.append("")
        edge_order = _EDGE_ORDER
        lines.append(
            f"EDGE TYPES ({len(edge_order)}): " + ", ".join(edge_order) + "."
        )
        lines.append("")
        lines.append(
            "(See src/node_types.py for full per-type docstrings and tags vocabulary.)"
        )
        return "\n".join(lines)

    # standard / verbose share the per-type-listing structure
    lines.append(
        f"Theorem-like ({len(_THEOREM_LIKE_ORDER)}): "
        + ", ".join(_THEOREM_LIKE_ORDER) + "."
    )
    lines.append("Carry assumptions and conclusions field splits.")
    lines.append("")
    if verbosity == "verbose":
        for t in _THEOREM_LIKE_ORDER:
            lines.append(f"  - {t}: {_extract_type_docstring(t)}")
        lines.append("")

    lines.append(
        f"Foundational ({len(_FOUNDATIONAL_ORDER)}): "
        + ", ".join(_FOUNDATIONAL_ORDER) + "."
    )
    lines.append("")
    if verbosity == "verbose":
        for t in _FOUNDATIONAL_ORDER:
            lines.append(f"  - {t}: {_extract_type_docstring(t)}")
        lines.append("")

    lines.append(
        f"Pedagogical ({len(_PEDAGOGICAL_ORDER)}): "
        + ", ".join(_PEDAGOGICAL_ORDER) + "."
    )
    lines.append("")
    if verbosity == "verbose":
        for t in _PEDAGOGICAL_ORDER:
            lines.append(f"  - {t}: {_extract_type_docstring(t)}")
        lines.append("")

    lines.append(
        f"Other content ({len(_OTHER_LEVEL1_ORDER)}): "
        + ", ".join(_OTHER_LEVEL1_ORDER) + "."
    )
    lines.append("")
    if verbosity == "verbose":
        for t in _OTHER_LEVEL1_ORDER:
            lines.append(f"  - {t}: {_extract_type_docstring(t)}")
        lines.append("")

    lines.append(
        f"Level-2 sub-block ({len(_LEVEL2_ORDER)}; when to emit them: \"Level-2 steps\"): "
        + ", ".join(_LEVEL2_ORDER) + "."
    )
    if verbosity == "verbose":
        lines.append("Emitted only at fine-grained granularity "
                     "(`with_proof_steps` / `with_algo_steps`). Each Level-2 "
                     "node references its Level-1 parent via `parent_id`.")
        lines.append("")
        for t in _LEVEL2_ORDER:
            lines.append(f"  - {t}: {_extract_type_docstring(t)}")
    lines.append("")

    # ── Edge types ──
    edge_order = _EDGE_ORDER
    lines.append(
        f"EDGE TYPES ({len(edge_order)}): " + ", ".join(edge_order) + "."
    )
    if verbosity == "standard":
        lines.append("Direction: A → B reads \"B [edge] A\" (B depends on A).")
    if verbosity == "verbose":
        lines.append("")
        lines.append("Direction: arrow A → B means \"A supports B\" / "
                     "\"B depends on A\". Edge name reads \"B [type] A\".")
        for e in edge_order:
            lines.append(f"  - {e}: {_EDGE_ONE_LINER[e]}")
    lines.append("")

    # ── Verbose extras: tags vocabulary + Level-1/Level-2 explanation ──
    if verbosity == "verbose":
        lines.append("LEVEL 1 vs LEVEL 2:")
        lines.append("  Level 1 — paper-level nodes (16 types). Always extracted.")
        lines.append("  Level 2 — sub-block nodes (proof_step, algorithm_step). "
                     "Emitted only when caller requests fine-grained granularity. "
                     "Each Level-2 node MUST reference its Level-1 parent via "
                     "`parent_id`.")
        lines.append("")
        lines.append("TAGS VOCABULARY (optional `tags: list[str]` per node;")
        lines.append("validators warn but do NOT reject unknown tags):")
        for t, tags in NT.TAGS_VOCABULARY.items():
            lines.append(f"  {t}: [{', '.join(tags)}]")
        lines.append("")

    lines.append(
        "(See src/node_types.py for full per-type docstrings and tags vocabulary.)"
    )
    return "\n".join(lines)


def get_tags_for_type(node_type: str) -> str:
    """Render the suggested tags vocabulary for a single node type as a
    short prompt-friendly string. Returns an empty string if the type has
    no published tag vocabulary.
    """
    if not node_type:
        return ""
    canon = NT.normalize_node_type(node_type)
    tags = NT.TAGS_VOCABULARY.get(canon)
    if not tags:
        return ""
    return (
        f"Suggested tags for `{canon}` (controlled vocabulary; pick zero or "
        f"more, lower_snake_case): {', '.join(tags)}."
    )


def render_prompt(prompt_text: str, node_type_for_tags: str | None = None) -> str:
    """Substitute `{{SCHEMA_BLOCK}}` and `{{TAGS_FOR_THIS_TYPE}}` placeholders
    in a prompt template. Use this everywhere a prompt is loaded for an
    LLM call. `<!-- ... -->` comments are notes for maintainers and are
    removed, so the model never sees them.
    """
    prompt_text = re.sub(r"<!--.*?-->\n?", "", prompt_text, flags=re.S)
    rendered = prompt_text.replace("{{SCHEMA_BLOCK}}", get_schema_block("standard"))
    if "{{TAGS_FOR_THIS_TYPE}}" in rendered:
        if node_type_for_tags is None:
            rendered = rendered.replace("{{TAGS_FOR_THIS_TYPE}}", "")
        else:
            rendered = rendered.replace(
                "{{TAGS_FOR_THIS_TYPE}}",
                get_tags_for_type(node_type_for_tags),
            )
    return rendered


# ── CLI ─────────────────────────────────────────────────────────────────

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Render the canonical schema as LLM prompt text.",
    )
    parser.add_argument(
        "--verbosity",
        choices=["compact", "standard", "verbose"],
        default="standard",
        help="How much detail to include (default: standard).",
    )
    parser.add_argument(
        "--tags-for",
        default=None,
        help="If given, also print the per-type tags string for this node type.",
    )
    args = parser.parse_args()

    print(get_schema_block(args.verbosity))
    if args.tags_for:
        print()
        print(f"-- TAGS FOR {args.tags_for} --")
        print(get_tags_for_type(args.tags_for))


if __name__ == "__main__":
    _main()
