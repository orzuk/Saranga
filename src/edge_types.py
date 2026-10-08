"""
Canonical edge type definitions for the Authomathics knowledge graph.

Single source of truth. All pipeline modules import from here.
See src/annotation_schema.md for the full specification.

Direction convention:
    Arrow A → B means "A supports B" / "B depends on A".
    Edge name reads "B [type] A" (target's action on source).

Count: 7 internal edge types (3 dependency + 4 structural) plus 1 external
edge type (`grounded_to`). The internal set is what most pipeline code
treats as the "edge taxonomy".
"""

# ── The canonical edge types ────────────────────────────────────────────

# Dependency edges: B depends on A
USES = "uses"                   # generic dependency (default)
GENERALIZES = "generalizes"     # B generalizes A (subtype of uses)
SPECIALIZES = "specializes"     # B specializes A (subtype of uses)

# Structural edges
PROVES = "proves"               # B proves A (proof → theorem)
ILLUSTRATES = "illustrates"     # B illustrates A (example → concept)
TESTS = "tests"                 # B tests A (exercise → concept)
RESOLVES = "resolves"           # B resolves A (problem/open_problem/conjecture → theorem-like or algorithm)

# External edges
GROUNDED_TO = "grounded_to"     # linked to foundation graph entry

# ── Groupings ────────────────────────────────────────────────────────────

# All dependency types (generalizes/specializes imply uses)
DEPENDENCY_TYPES = {USES, GENERALIZES, SPECIALIZES}

# All structural types
STRUCTURAL_TYPES = {PROVES, ILLUSTRATES, TESTS, RESOLVES}
# Backward-compat alias matching the naming used elsewhere in the codebase.
STRUCTURAL_EDGES = STRUCTURAL_TYPES

# All internal edge types (excludes grounded_to)
ALL_INTERNAL_TYPES = DEPENDENCY_TYPES | STRUCTURAL_TYPES

# All edge types including external
ALL_TYPES = ALL_INTERNAL_TYPES | {GROUNDED_TO}

# The manuscript-advertised canonical edge taxonomy: 3 dependency + 4
# structural = 7 edge types. Excludes `grounded_to` (external foundation-linker
# edge); use `ALL_TYPES` for the full set.
ALL_EDGE_TYPES = ALL_INTERNAL_TYPES


# ── Source/target type constraints (theorem-like target sets) ───────────
#
# These are descriptive constraints used by validators to warn (not error)
# when an edge's endpoints don't match the canonical source/target types.
# Imported from node_types.py lazily inside functions to avoid a circular
# import at module load time.

def _theorem_like_provable() -> set[str]:
    """Theorem-like node types that can be 'settled' (excludes conjecture)."""
    from node_types import PROVABLE  # noqa: WPS433
    return set(PROVABLE)


# Per-edge metadata: human-readable description, group, and (optional)
# allowed source / target node-type sets. Source/target sets are computed
# lazily via callables to avoid circular imports with node_types.py.
EDGE_METADATA = {
    USES: {
        "group": "dependency",
        "description": "B uses A — generic dependency (default).",
    },
    GENERALIZES: {
        "group": "dependency",
        "description": "B generalizes A — B is more general than A.",
    },
    SPECIALIZES: {
        "group": "dependency",
        "description": "B specializes A — B is a special case of A.",
    },
    PROVES: {
        "group": "structural",
        "description": "B proves A — proof node B establishes theorem-like A.",
        "source_types": lambda: {"proof"},
        "target_types": _theorem_like_provable,
    },
    # NOTE (2026-07-30): ILLUSTRATES / TESTS previously declared the
    # *actor* as the source (example/exercise), which contradicted the
    # module's own direction convention ("arrow A → B means A supports B / B
    # depends on A"). They now follow the uniform dependency convention: the
    # prerequisite is the source, the dependent thing is the target. So an
    # example DEPENDS ON the concept it illustrates → concept → example.
    ILLUSTRATES: {
        "group": "structural",
        "description": "B illustrates A — arrow concept → example; the example "
                       "(target) demonstrates the concept (source).",
        "target_types": lambda: {"example"},
    },
    TESTS: {
        "group": "structural",
        "description": "B tests A — arrow concept → exercise; the exercise "
                       "(target) tests the concept (source).",
        "target_types": lambda: {"exercise"},
    },
    RESOLVES: {
        "group": "structural",
        "description": (
            "B resolves A — B settles A: a theorem-like result settles a "
            "problem, open_problem or conjecture, or an algorithm solves a "
            "problem."
        ),
        "source_types": lambda: {"problem", "open_problem", "conjecture"},
        "target_types": lambda: _theorem_like_provable() | {"algorithm"},
    },
    GROUNDED_TO: {
        "group": "external",
        "description": "Node linked to a foundation knowledge-graph entry.",
    },
}


# ── Backward compatibility: old type names → canonical ───────────────────

DEPRECATED_MAP = {
    "dependency":    USES,
    "follows_from":  USES,
    "has_part":      PROVES,       # old "has_part" was used for proof→theorem
    "about":         TESTS,        # renamed to "tests"
}


def normalize_edge_type(raw_type: str | None) -> str:
    """Normalize an edge type string to canonical form.

    Handles: None/empty → "uses", deprecated names → canonical,
    already-canonical → pass through.
    """
    if not raw_type:
        return USES
    t = raw_type.strip().lower()
    if t in DEPRECATED_MAP:
        return DEPRECATED_MAP[t]
    if t in ALL_TYPES:
        return t
    return USES  # unknown → default


def is_dependency(edge_type: str) -> bool:
    """True if this edge type represents a logical dependency."""
    return normalize_edge_type(edge_type) in DEPENDENCY_TYPES


def get_allowed_source_types(edge_type: str) -> set[str] | None:
    """Return the canonical allowed source-node-type set for `edge_type`,
    or None if the edge type imposes no source-type constraint.
    """
    meta = EDGE_METADATA.get(normalize_edge_type(edge_type), {})
    src = meta.get("source_types")
    return src() if callable(src) else src


def get_allowed_target_types(edge_type: str) -> set[str] | None:
    """Return the canonical allowed target-node-type set for `edge_type`,
    or None if the edge type imposes no target-type constraint.
    """
    meta = EDGE_METADATA.get(normalize_edge_type(edge_type), {})
    tgt = meta.get("target_types")
    return tgt() if callable(tgt) else tgt

# ── Edge field names ─────────────────────────────────────────────────────
# Every edge in the v5.1 silver corpus carries exactly these four, and
# `source`/`target` were declared nowhere until now.
REQUIRED_EDGE_FIELDS = (
    "source",      # the node relied upon
    "target",      # the node that depends on it
    "type",        # from ALL_EDGE_TYPES
    "confidence",  # 0-1
)
# `backward`: true on an edge that points against the paper's reading order, a
# forward reference ("by Lemma 5 below") or an induction step using the result
# itself. Acyclicity is required of the graph without these edges.
OPTIONAL_EDGE_FIELDS = ("note", "backward")
ALL_EDGE_FIELDS = REQUIRED_EDGE_FIELDS + OPTIONAL_EDGE_FIELDS
