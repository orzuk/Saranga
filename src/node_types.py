"""
Canonical node type definitions for the SARANGA knowledge graph.

Single source of truth. All pipeline modules import from here.
See src/annotation_schema.md for the full specification.
"""

# ── The 13 canonical node types ─────────────────────────────────────────

# Theorem-like: have assumptions + conclusions, can be proved
THEOREM = "theorem"
LEMMA = "lemma"
PROPOSITION = "proposition"
COROLLARY = "corollary"
CLAIM = "claim"
CONJECTURE = "conjecture"

# Definition
DEFINITION = "definition"

# Proof
PROOF = "proof"

# Pedagogical
EXAMPLE = "example"
EXERCISE = "exercise"         # pedagogical problem for the reader

# Other mathematical content
PROBLEM = "problem"           # named math problem being studied (closer to conjecture)
EQUATION = "equation"
ALGORITHM = "algorithm"
REMARK = "remark"

# ── Extra fields per type ────────────────────────────────────────────────
# These are OPTIONAL structured fields on specific node types.
# Extractors populate them when the information is available.

# Algorithm extra fields:
#   solves:              str | null   — ID of the problem node this algorithm solves
#   algorithm_class:     str | null   — "exact" | "approximation" | "heuristic" |
#                                       "randomized" | "online" | "greedy"
#   approximation_ratio: str | null   — e.g. "1.5", "O(log n)", "2-epsilon", null if exact
#   complexity:          str | null   — time complexity, e.g. "O(n^2)", "O(m log m)"
#   space_complexity:    str | null   — space complexity (optional)
ALGORITHM_FIELDS = {"solves", "algorithm_class", "approximation_ratio",
                    "complexity", "space_complexity"}

# Problem extra fields:
#   problem_class:       str | null   — "optimization" | "decision" | "search" |
#                                       "counting" | "sampling" | "other"
#   complexity_class:    str | null   — "P" | "NP-hard" | "NP-complete" | "PSPACE" |
#                                       "undecidable" | "unknown" | "open"
#   approximability:     str | null   — "PTAS" | "FPTAS" | "APX-hard" |
#                                       "inapproximable" | null
PROBLEM_FIELDS = {"problem_class", "complexity_class", "approximability"}

# ── Groupings ────────────────────────────────────────────────────────────

# Theorem-like: nodes that state a mathematical claim with assumptions/conclusions
THEOREM_LIKE = {THEOREM, LEMMA, PROPOSITION, COROLLARY, CLAIM, CONJECTURE}

# Provable: theorem-like nodes that can have a proof (excludes conjecture)
PROVABLE = {THEOREM, LEMMA, PROPOSITION, COROLLARY, CLAIM}

# Pedagogical: nodes primarily for teaching
PEDAGOGICAL = {EXAMPLE, EXERCISE}

# All node types (14 total)
ALL_TYPES = (
    THEOREM_LIKE
    | {DEFINITION, PROOF, PROBLEM, EQUATION, ALGORITHM, REMARK}
    | PEDAGOGICAL
)

# ── Backward compatibility ──────────────────────────────────────────────

DEPRECATED_MAP = {
    # No type renames — problem and exercise are DISTINCT types.
    "thm": THEOREM,         # abbreviation sometimes used
    "lem": LEMMA,
    "prop": PROPOSITION,
    "cor": COROLLARY,
    "def": DEFINITION,
    "pf": PROOF,
    "rem": REMARK,
    "ex": EXAMPLE,
    "alg": ALGORITHM,
    "eq": EQUATION,
}


def normalize_node_type(raw_type: str | None) -> str:
    """Normalize a node type string to canonical form."""
    if not raw_type:
        return THEOREM  # safe default
    t = raw_type.strip().lower()
    if t in DEPRECATED_MAP:
        return DEPRECATED_MAP[t]
    if t in ALL_TYPES:
        return t
    return t  # unknown — pass through, don't silently drop
