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

# ── Rigor field ──────────────────────────────────────────────────────────
# Every node has an optional "rigor" field indicating how rigorous the
# justification is. Orthogonal to "type" (which reflects the author's label).
# A math "Claim 1" with proof = rigor:formal. A physics heuristic = rigor:heuristic.

RIGOR_LEVELS = {
    "formal",       # precise statement, rigorous proof (pure math, CS theory)
    "semi_formal",  # precise statement, proof sketch or "standard arguments" (math stats)
    "heuristic",    # result believed true, justified by physical/intuitive argument (physics)
    "numerical",    # supported by simulation/computation, no analytical proof (applied ML, bio)
    "conjectural",  # stated without justification
}

# Rigor classification of arXiv categories and book topics
RIGOROUS_CATEGORIES = {
    "math.CO", "math.PR", "math.AG", "math.NT", "math.LO", "math.GR",
    "math.AT", "math.FA", "math.CA", "math.RT", "math.AC", "math.DG",
    "cs.DS", "cs.CC", "cs.CG", "cs.FL", "cs.DM", "cs.LO",
    "math.OC",  # mostly rigorous
}
MIXED_CATEGORIES = {
    "stat.ML", "cs.LG", "cs.AI", "cs.CV", "cs.CL",  # mix of rigorous + heuristic
    "stat.ME", "stat.TH",  # stat.TH is rigorous; stat.ME is mixed
}
HEURISTIC_CATEGORIES = {
    "physics", "cond-mat", "hep-th", "quant-ph",  # mostly heuristic
    "q-bio", "eess.SP",  # bio, signal processing
}


# ── Universal subclass field ─────────────────────────────────────────────
# Every node type has an optional "subclass" field that gives a finer
# categorization. Valid values depend on the node type.

SUBCLASS_VALUES = {
    DEFINITION:  {"concept", "model", "estimator", "loss_function", "metric",
                  "notation", "space", "operator"},
    THEOREM:     {"existence", "uniqueness", "convergence", "bound",
                  "characterization", "equivalence", "impossibility",
                  "classification"},
    LEMMA:       {"technical", "auxiliary", "key"},
    PROPOSITION: {"existence", "uniqueness", "convergence", "bound",
                  "characterization", "equivalence"},
    COROLLARY:   {"consequence", "special_case"},
    CLAIM:       {"existence", "bound", "convergence", "characterization"},
    CONJECTURE:  {"open", "folklore"},
    PROOF:       {"direct", "contradiction", "induction", "construction",
                  "probabilistic", "combinatorial", "algebraic"},
    EXAMPLE:     {"illustrative", "counterexample", "computational", "applied"},
    EXERCISE:    {"computational", "theoretical", "proof_exercise", "programming"},
    PROBLEM:     {"optimization", "decision", "search", "counting", "sampling",
                  "estimation"},
    ALGORITHM:   {"exact", "approximation", "heuristic", "randomized", "online",
                  "greedy", "iterative"},
    EQUATION:    {"identity", "inequality", "recursion", "differential", "bound"},
    REMARK:      {"historical", "technical", "motivational"},
}

# ── Type-specific extra fields (beyond subclass) ────────────────────────
# These carry structured information unique to certain node types.

# Algorithm:
#   solves:              str | null   — ID of the problem node this algorithm solves
#   approximation_ratio: str | null   — e.g. "1.5", "O(log n)", null if exact
#   complexity:          str | null   — time complexity, e.g. "O(n^2)"
#   space_complexity:    str | null   — space complexity
ALGORITHM_EXTRA_FIELDS = {"solves", "approximation_ratio", "complexity",
                          "space_complexity"}

# Problem:
#   complexity_class:    str | null   — "P", "NP-hard", "NP-complete", etc.
#   approximability:     str | null   — "PTAS", "FPTAS", "APX-hard", etc.
PROBLEM_EXTRA_FIELDS = {"complexity_class", "approximability"}

# Proof:
#   proves:              str          — ID of the theorem this proves
#   proof_strategy:      str | null   — alias for subclass (backward compat)
PROOF_EXTRA_FIELDS = {"proves", "proof_strategy"}

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
