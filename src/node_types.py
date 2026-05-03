"""
Canonical node type definitions for the Authomathics knowledge graph.

Single source of truth. All pipeline modules import from here.
See src/annotation_schema.md for the full specification.

Schema lock revision: 2026-04-28
- Adds `open_problem`, `assumption`, `algorithm_step` to the type set.
- Splits `problem` (named formal mathematical problem) from `open_problem`
  (unsolved mathematical question).
- Introduces explicit Level 1 (paper-level) and Level 2 (sub-block)
  groupings.
- Adds optional `TAGS_VOCABULARY` for the per-type `tags: list[str]` field.
"""

# ── Node types ──────────────────────────────────────────────────────────

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

# Proof decomposition (Level 2 — optional fine-grained resolution):
#   proof_step — one logical move within a proof. First-class node, NOT a
#   nested array inside PROOF. Linked back to its parent via the
#   `parent_proof` field (str: id of the PROOF node) or generic `parent_id`.
#   Equations can attach to a specific proof_step via `parent_step`.
#   Emitted only when extraction runs at "with_proof_steps" granularity;
#   omitted at the default "theorem_level" granularity.
PROOF_STEP = "proof_step"

# Algorithm decomposition (Level 2 — optional fine-grained resolution):
#   algorithm_step — one numbered line of pseudocode within an algorithm
#   node. Linked back to its parent ALGORITHM via `parent_algorithm`
#   (or generic `parent_id`). Emitted only at fine-grained granularity.
ALGORITHM_STEP = "algorithm_step"

# Pedagogical
EXAMPLE = "example"
EXERCISE = "exercise"         # pedagogical problem for the reader

# Other mathematical content
#
# PROBLEM vs. OPEN_PROBLEM (split as of 2026-04-28):
#   PROBLEM        — a *named or formulated formal mathematical problem*:
#                    optimization formulations ("argmin f(x) s.t. Ax<=b"),
#                    decision problems ("3-SAT"), named problems with
#                    attached algorithms / complexity / hardness ("the
#                    knapsack problem", "the isoperimetric problem").
#                    Semantically the object the paper STUDIES — algorithms
#                    SOLVE it, complexity discussions BOUND it.
#                    Does NOT cover open mathematical questions — those
#                    are now `open_problem`.
#   OPEN_PROBLEM   — an unsolved mathematical *question* with no known
#                    solution. Examples: "Are there infinitely many odd
#                    perfect numbers?", the Riemann Hypothesis posed as
#                    an open question, "Is P = NP?". Semantically similar
#                    to CONJECTURE (theorem-like in spirit), but content-
#                    wise more like a question without a stated answer.
#                    Distinct from PROBLEM (which is formal/named) and
#                    EXERCISE (which is pedagogical).
PROBLEM = "problem"
OPEN_PROBLEM = "open_problem"

EQUATION = "equation"
ALGORITHM = "algorithm"
REMARK = "remark"

# Setup / standing assumptions block:
#   ASSUMPTION — a `\begin{assumption}` block declaring standing
#   assumptions for a section, theorem cluster, or paper. Common in
#   stats / optimization papers ("(A1) f is convex; (A2) X is bounded").
#   Distinct from the per-theorem `assumptions` field, which lives
#   inside a theorem-like node.
ASSUMPTION = "assumption"

# ── Origin field ─────────────────────────────────────────────────────────
# Every node has an optional "origin" field indicating whether the node
# represents a contribution of the paper being extracted ("paper", default)
# or a cited prior result the paper invokes but does not establish
# ("external" — e.g., a classical theorem like "Sinkhorn 1967" or a
# baseline algorithm used for comparison).
#
# External nodes additionally carry an optional "origin_citation" string
# (free text or BibTeX key, e.g., "Sinkhorn 1967", "Villani 2009 §6.1").
# See manuscript appendix "Origin attribution" for the canonical rule.

ORIGIN_PAPER = "paper"
ORIGIN_EXTERNAL = "external"
ORIGIN_VALUES = {ORIGIN_PAPER, ORIGIN_EXTERNAL}
DEFAULT_ORIGIN = ORIGIN_PAPER


def normalize_origin(raw_origin: str | None) -> str:
    """Normalize an origin string. Default is 'paper' when missing/unknown.

    Backwards compatibility: nodes without an `origin` field are assumed
    to be paper-internal (the field was added after initial extractions).
    """
    if not raw_origin:
        return DEFAULT_ORIGIN
    o = str(raw_origin).strip().lower()
    if o in ORIGIN_VALUES:
        return o
    return DEFAULT_ORIGIN


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
    DEFINITION:    {"concept", "model", "estimator", "loss_function", "metric",
                    "notation", "space", "operator"},
    THEOREM:       {"existence", "uniqueness", "convergence", "bound",
                    "characterization", "equivalence", "impossibility",
                    "classification"},
    LEMMA:         {"technical", "auxiliary", "key"},
    PROPOSITION:   {"existence", "uniqueness", "convergence", "bound",
                    "characterization", "equivalence"},
    COROLLARY:     {"consequence", "special_case"},
    CLAIM:         {"existence", "bound", "convergence", "characterization"},
    CONJECTURE:    {"open", "folklore"},
    PROOF:         {"direct", "contradiction", "induction", "construction",
                    "probabilistic", "combinatorial", "algebraic"},
    PROOF_STEP:    {"setup", "introduce_variable", "apply_lemma", "case_split",
                    "induction_step", "contradiction_setup", "algebraic_manipulation",
                    "substitute", "bound_estimate", "invoke_identity", "conclude", "other"},
    ALGORITHM_STEP:{"initialize", "loop", "branch", "update", "return", "other"},
    EXAMPLE:       {"illustrative", "counterexample", "computational", "applied"},
    EXERCISE:      {"computational", "theoretical", "proof_exercise", "programming"},
    PROBLEM:       {"optimization", "decision", "search", "counting", "sampling",
                    "estimation", "feasibility", "enumeration"},
    OPEN_PROBLEM:  {"famous", "named", "folklore"},
    ALGORITHM:     {"exact", "approximation", "heuristic", "randomized", "online",
                    "greedy", "iterative"},
    EQUATION:      {"identity", "inequality", "recursion", "differential", "bound"},
    REMARK:        {"historical", "technical", "motivational"},
    ASSUMPTION:    {"standing", "regularity", "structural", "distributional",
                    "asymptotic"},
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

# Open problem:
#   first_posed:         str | null   — "Erdős 1949", "Hilbert 1900 (#8)", etc.
#   prize:               str | null   — "Clay Millennium Prize", etc.
OPEN_PROBLEM_EXTRA_FIELDS = {"first_posed", "prize"}

# Proof:
#   proves:              str          — ID of the theorem this proves
#   proof_strategy:      str | null   — alias for subclass (backward compat)
PROOF_EXTRA_FIELDS = {"proves", "proof_strategy"}

# Proof step:
#   parent_proof:        str          — ID of the PROOF node this step belongs to
#                                       (legacy; `parent_id` is the new generic name)
#   parent_id:           str          — generic Level 2 → Level 1 parent reference
#   step_order:          int | null   — sequential index within the proof (1-based)
#   depends_on_step_ids: list[str]    — step IDs within same proof that this step uses
#   uses_node_ids:       list[str]    — external nodes (lemmas/defs) invoked in this step
#   move_type:           str | null   — optional tag: setup / apply_lemma / case_split /
#                                         induction / contradiction / algebraic_manipulation /
#                                         substitute / bound_estimate / invoke_identity /
#                                         conclude / other
PROOF_STEP_EXTRA_FIELDS = {"parent_proof", "parent_id", "step_order",
                           "depends_on_step_ids", "uses_node_ids", "move_type"}

# Algorithm step:
#   parent_algorithm:    str          — ID of the ALGORITHM node this step belongs to
#                                       (legacy; `parent_id` is the new generic name)
#   parent_id:           str          — generic Level 2 → Level 1 parent reference
#   step_order:          int | null   — sequential index within the algorithm (1-based)
#   pseudocode:          str | null   — the pseudocode line itself
ALGORITHM_STEP_EXTRA_FIELDS = {"parent_algorithm", "parent_id", "step_order",
                               "pseudocode"}

# Equation (optional enrichment when attached to a proof step):
#   parent_step:         str | null   — ID of a proof_step node that derives this equation
EQUATION_EXTRA_FIELDS = {"parent_step"}

# Assumption:
#   scope:               str | null   — section/theorem ID(s) covered by this assumption
#   label_token:         str | null   — short tag like "(A1)", "(H2)"
ASSUMPTION_EXTRA_FIELDS = {"scope", "label_token"}

# ── Tag vocabulary ──────────────────────────────────────────────────────
# Optional `tags: list[str]` field on each node. The vocabulary below is a
# *suggestion* set; extractors may emit subsets; validators warn but do NOT
# reject unknown tags. Keep tags lower_snake_case.

# Theorem-like vocabulary is shared across THEOREM/LEMMA/PROPOSITION/COROLLARY/
# CLAIM. Defined once here and reused below to keep the lists aligned.
_THEOREM_LIKE_TAGS = [
    # core logical shape
    "existence", "uniqueness", "inequality", "equality", "monotonicity",
    "convergence", "bound", "characterization", "decomposition", "equivalence",
    # quantitative / asymptotic flavor
    "convergence_rate", "asymptotic", "limit", "threshold",
    "lower_bound", "upper_bound", "approximation", "moment_bound",
    "oracle_inequality", "matrix_inequality", "moment_inequality",
    # probabilistic flavor
    "concentration", "high_probability", "martingale", "deviation",
    "stability", "minimax",
    # achievability / phase / recovery flavor
    "achievability", "impossibility", "phase_transition", "exact_recovery",
    # domain hooks Opus emits frequently
    "spectral", "kernel", "polynomial_time", "sphere", "positive_definite",
    "random_matrix", "stochastic_gradient", "decoding", "interpolation",
    "training", "metric", "sufficient_condition", "expansion", "gluing",
    "dual_certificate", "dual", "bias", "variance", "strong_convexity",
    "iterative_construction", "hermite", "control", "technical", "degree",
    "combinatorial", "sampling", "fisher_information", "statistics",
    "coupling", "comparison", "mean_squared_error",
]

TAGS_VOCABULARY = {
    THEOREM:      list(_THEOREM_LIKE_TAGS),
    LEMMA:        list(_THEOREM_LIKE_TAGS),
    PROPOSITION:  list(_THEOREM_LIKE_TAGS),
    COROLLARY:    list(_THEOREM_LIKE_TAGS),
    CLAIM:        list(_THEOREM_LIKE_TAGS),
    PROOF:        ["induction", "contradiction", "direct", "contrapositive",
                   "probabilistic", "combinatorial", "analytic", "geometric",
                   "case_analysis", "construction",
                   "gronwall", "proof_sketch", "embedding",
                   "chain_of_inequalities", "polynomial_bound", "hermite",
                   "data_processing", "markov_chain", "kernel"],
    DEFINITION:   ["inductive", "recursive", "axiomatic", "constructive",
                   "notation", "equivalent_form",
                   "foundational", "kernel", "sparsity", "set", "events",
                   "function_class", "spectral", "concentration", "smoothness",
                   "covariance", "geometric", "random", "structural",
                   "distributional", "variance", "concept", "risk", "dual",
                   "feature_map", "map", "ntk", "expectation", "convexity",
                   "limit", "positive_definite", "information",
                   "restricted_isometry", "restricted_orthogonality",
                   "random_graph", "community_detection", "gradient",
                   "dynamics", "empirical_distribution"],
    PROBLEM:      ["optimization", "decision", "named", "feasibility",
                   "counting", "enumeration",
                   "combinatorial", "np_hard", "linear_program", "convex",
                   "relaxation", "estimation", "regression", "sdp",
                   "decoding", "convex_relaxation", "stochastic",
                   "logistic_regression", "named_problem", "application",
                   "error_correction", "distributed", "entropy_regularized"],
    OPEN_PROBLEM: ["famous", "named", "open", "extension", "open_question",
                   "nonparametric", "bias_correction", "resampling"],
    ALGORITHM:    ["iterative", "greedy", "divide_and_conquer", "dp",
                   "randomized", "approximation", "online",
                   "spectral", "clustering", "distributed", "ensemble",
                   "stochastic_gradient", "sgd", "newton", "first_order",
                   "single_pass", "single_round", "convex_relaxation",
                   "polynomial_time", "np_hard", "linear_program", "sdp",
                   "fixed_point", "boosting", "regression", "averaging",
                   "tree", "implementation", "epoch", "subsampling",
                   "stochastic", "convex_optimization", "matrix_scaling",
                   "neural_network", "min_norm", "warm_start",
                   "dual_coordinate", "two_stage", "vectorized",
                   "bias_correction", "baseline", "linear_least_squares",
                   "non_convex", "combinatorial"],
    EXAMPLE:      ["empirical", "numerical", "simulation", "real_data",
                   "counterexample", "benchmark", "classification", "runtime",
                   "synthetic", "experiment", "mnist", "logistic_regression",
                   "pca", "necessity", "image_classification", "ensemble",
                   "neural_network", "convergence_study", "complexity",
                   "complexity_study", "boosting", "fourier", "convergence",
                   "compressed_sensing", "visualization"],
    REMARK:       ["interpretation", "counterexample", "numerical",
                   "parametrization", "asymptotic", "scaling", "technique",
                   "discussion", "tuning", "implementation_note",
                   "implementation", "bound", "conjecture", "measure_zero",
                   "kernel", "optimization", "vectorization", "gpgpu",
                   "bisection", "inductive_bias"],
    EQUATION:     ["dynamics", "update_rule", "spectral", "objective",
                   "sufficient_condition", "limit", "lagrangian", "threshold",
                   "kernel_ridge", "map", "regularized_ot", "inequality"],
    ASSUMPTION:   ["smoothness", "curvature", "regularity", "strong_convexity",
                   "restricted_eigenvalue", "moments", "boundedness",
                   "distributional"],
    # PROOF_STEP and ALGORITHM_STEP rely on the structured `subclass` field
    # for semantic role; tags are intentionally not enumerated here.
}


def normalize_tag(tag: str) -> str:
    """Normalize a tag string for vocabulary lookup.

    Opus extractors mix kebab-case ('lower-bound') and snake_case
    ('lower_bound'), and occasionally vary capitalization. We fold both
    into snake_case + lowercase before matching against the vocabulary.
    """
    if not isinstance(tag, str):
        return tag
    return tag.lower().replace("-", "_")


def is_known_tag(node_type: str, tag: str) -> bool:
    """Return True if `tag` (after normalization) is in the suggested
    vocabulary for `node_type`.

    Validators should warn on unknown tags but NOT reject them — extractors
    may emit type-specific tags outside the published vocabulary.
    """
    vocab = TAGS_VOCABULARY.get(node_type, [])
    return normalize_tag(tag) in {normalize_tag(t) for t in vocab}


# ── Antecedent detection (used by validator for assumptions check) ──────
# A theorem-like statement that contains one of these conditional markers
# is expected to populate the `assumptions` field. Statements without any
# marker are treated as bare facts (single inequality, identity, etc.) and
# are allowed to leave `assumptions` empty (Regimes B2 / C in the schema doc).

ANTECEDENT_MARKERS = (
    "if ", "let ", "suppose ", "assume ", "given ", "provided ",
    "for all ", "for every ", "for any ", "where ", "consider ", "fix ",
)


def has_antecedent(statement: str) -> bool:
    """True if the statement contains an explicit conditional marker that
    should populate `assumptions`. Used to suppress spurious warnings on
    bare-inequality and identity-style theorems."""
    if not statement or not isinstance(statement, str):
        return False
    s = " " + statement.lower() + " "
    return any(m in s for m in ANTECEDENT_MARKERS)


# ── Groupings ────────────────────────────────────────────────────────────

# Theorem-like: nodes that state a mathematical claim with assumptions/conclusions
THEOREM_LIKE = {THEOREM, LEMMA, PROPOSITION, COROLLARY, CLAIM, CONJECTURE}

# Provable: theorem-like nodes that can have a proof (excludes conjecture)
PROVABLE = {THEOREM, LEMMA, PROPOSITION, COROLLARY, CLAIM}

# Pedagogical: nodes primarily for teaching
PEDAGOGICAL = {EXAMPLE, EXERCISE}

# Proof / algorithm decomposition nodes (Level 2 — emitted only at fine-grained granularity)
PROOF_DECOMPOSITION = {PROOF_STEP}
ALGORITHM_DECOMPOSITION = {ALGORITHM_STEP}

# ── Level 1 / Level 2 split ─────────────────────────────────────────────
# Level 1: top-level paper-content nodes. Default extraction granularity.
# Level 2: sub-block nodes (proof_step, algorithm_step). Emitted only at
#          fine-grained granularity (`with_proof_steps` / `with_algo_steps`).
# Each Level 2 node MUST reference its Level 1 parent via `parent_id`
# (or the legacy type-specific field `parent_proof` / `parent_algorithm`).

LEVEL_1_TYPES = {
    THEOREM, LEMMA, PROPOSITION, COROLLARY, CLAIM, CONJECTURE,
    DEFINITION, PROOF, EXAMPLE, EXERCISE,
    PROBLEM, OPEN_PROBLEM,
    EQUATION, ALGORITHM, REMARK, ASSUMPTION,
}  # 16 types

LEVEL_2_TYPES = {PROOF_STEP, ALGORITHM_STEP}  # 2 types

# All node types (16 + 2 = 18)
ALL_TYPES = LEVEL_1_TYPES | LEVEL_2_TYPES

# Compatibility map: which Level 1 parent type each Level 2 type belongs to.
LEVEL_2_PARENT_TYPE = {
    PROOF_STEP:     PROOF,
    ALGORITHM_STEP: ALGORITHM,
}


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
    "step": PROOF_STEP,     # sometimes proof-steps are tagged just "step"
    "proof-step": PROOF_STEP,
    "proofstep": PROOF_STEP,
    "algorithm-step": ALGORITHM_STEP,
    "algo-step": ALGORITHM_STEP,
    "algostep": ALGORITHM_STEP,
    "open-problem": OPEN_PROBLEM,
    "openproblem": OPEN_PROBLEM,
    "open_question": OPEN_PROBLEM,
    "assum": ASSUMPTION,
    "assumptions": ASSUMPTION,
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
