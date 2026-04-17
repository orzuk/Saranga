"""
Canonical edge type definitions for the SARANGA knowledge graph.

Single source of truth. All pipeline modules import from here.
See src/annotation_schema.md for the full specification.

Direction convention:
    Arrow A → B means "A supports B" / "B depends on A".
    Edge name reads "B [type] A" (target's action on source).
"""

# ── The 6 canonical edge types ──────────────────────────────────────────

# Dependency edges: B depends on A
USES = "uses"                   # generic dependency (default)
GENERALIZES = "generalizes"     # B generalizes A (subtype of uses)
SPECIALIZES = "specializes"     # B specializes A (subtype of uses)

# Structural edges
PROVES = "proves"               # B proves A (proof → theorem)
ILLUSTRATES = "illustrates"     # B illustrates A (example → concept)
TESTS = "tests"                 # B tests A (exercise → concept)

# External edges
GROUNDED_TO = "grounded_to"     # linked to foundation graph entry

# ── Groupings ────────────────────────────────────────────────────────────

# All dependency types (generalizes/specializes imply uses)
DEPENDENCY_TYPES = {USES, GENERALIZES, SPECIALIZES}

# All structural types
STRUCTURAL_TYPES = {PROVES, ILLUSTRATES, TESTS}

# All internal edge types (excludes grounded_to)
ALL_INTERNAL_TYPES = DEPENDENCY_TYPES | STRUCTURAL_TYPES

# All edge types including external
ALL_TYPES = ALL_INTERNAL_TYPES | {GROUNDED_TO}

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
