#!/usr/bin/env python3
"""
math_classes.py

Mid-level ontology for mathematical papers.

This file defines the reusable data model (classes and relations) that represent
mathematical content: theorems, lemmas, definitions, proofs, algorithms, etc.

Parsing / extraction logic (from LaTeX, Lean, etc.) should live elsewhere
(e.g. in `math_paper_parser.py`) and populate these classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Type


# ---------------------------------------------------------------------
# Generic spans / semantic chunks
# ---------------------------------------------------------------------


@dataclass
class Span:
    """
    Generic semantic span inside an object.

    Examples:
        - an assumption sentence
        - a conclusion sentence
        - an algorithm input parameter constraint
        - a remark about a special case

    'kind' is free-form but you may want to standardize:
        "assumption", "conclusion", "condition", "input_param",
        "output_param", "precondition", "postcondition", "step",
        "example", "remark", ...
    """
    kind: str
    text: str
    start: Optional[int] = None      # character offset in raw_latex, if known
    end: Optional[int] = None        # character offset in raw_latex, if known
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------
# Base object
# ---------------------------------------------------------------------


@dataclass
class MathObject:
    """
    Base class for all extracted mathematical objects.

    NOTE: This is intentionally close to your original MathObject so that
    existing parsing code remains compatible.
    """
    id: str
    kind: str                 # theorem, lemma, definition, proof, algorithm, table, equation, ...
    index: int                # running index per kind (1-based)
    label: Optional[str]      # \label{...} if present
    name: Optional[str]       # optional name/heading e.g. [Strong law]
    raw_latex: str            # full LaTeX body of the environment (or snippet)
    clean_text: str           # LaTeX stripped of markup (best-effort)
    paper_id: Optional[str] = None

    # semantic substructure (optional; parsers can fill or leave empty)
    spans: List[Span] = field(default_factory=list)


# ---------------------------------------------------------------------
# Equations
# ---------------------------------------------------------------------


@dataclass
class Equation(MathObject):
    """
    Equation or displayed math block.

    - 'env_name' is the LaTeX environment or display type (equation, align, etc.)
    - 'display_type' indicates how it was found: env / dollar / bracket
    - 'parent_id' is the id of the containing object (theorem, proof, etc.), if any.
    """
    env_name: str = ""
    display_type: str = "env"        # 'env', 'dollar', 'bracket'
    parent_id: Optional[str] = None


# ---------------------------------------------------------------------
# Theorem-like objects
# ---------------------------------------------------------------------


@dataclass
class TheoremLike(MathObject):
    """
    Theorem-like object with an assumptions/statement split (heuristic).

    'kind' is one of: 'theorem', 'lemma', 'proposition', 'corollary',
                      'claim', 'conjecture', 'problem'.

    For compatibility with existing code, we keep 'assumptions' and
    'statement' as plain strings, and optionally also provide Span lists
    for finer structure later.
    """
    env_name: str = ""        # actual LaTeX env name e.g. 'theorem', 'lemma'
    assumptions: str = ""     # heuristic assumptions text ("Let / Suppose / Assume ...")
    statement: str = ""       # heuristic statement text ("Then ...")

    # Optional finer structure (currently not populated by the heuristic parser,
    # but available for future LLM / rule-based enrichments).
    assumption_spans: List[Span] = field(default_factory=list)
    statement_spans: List[Span] = field(default_factory=list)


@dataclass
class Problem(TheoremLike):
    """
    Mathematical problem / RHP / optimisation problem.

    These semantic fields are optional and can be filled by more specialized
    parsers later.
    """
    problem_type: Optional[str] = None     # e.g. "RHP", "optimization", "other"
    constraints: Optional[str] = None      # textual description of constraints
    objective: Optional[str] = None        # optimization objective, if any
    existence_known: Optional[bool] = None
    uniqueness_known: Optional[bool] = None
    complexity: Optional[str] = None       # e.g. "polynomial time", "NP-hard", etc.


@dataclass
class Conjecture(TheoremLike):
    """Conjecture object; same structure as TheoremLike but separate class."""
    pass


# ---------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------


@dataclass
class Definition(MathObject):
    """
    Definition of a concept or notation.

    For now we keep the minimal env_name (for LaTeX) and optional higher-level
    structure for the 'definiendum' and related parts. The heuristic parser
    currently only fills env_name, but LLM/rule-based passes can enrich.
    """
    env_name: str = ""

    # Optional higher-level decomposition (can be None / empty)
    definiendum: Optional[Span] = None        # the thing being defined
    genus: Optional[Span] = None              # "is a square matrix", "is a norm", ...
    differentia: List[Span] = field(default_factory=list)   # distinguishing conditions
    equivalences: List[Span] = field(default_factory=list)  # "equivalently, ..."
    notation_introduced: List[Span] = field(default_factory=list)  # new symbols


# ---------------------------------------------------------------------
# Proofs
# ---------------------------------------------------------------------


@dataclass
class Proof(MathObject):
    """
    Proof, optionally linked to a theorem/lemma/etc.

    - parent_id is the id of the theorem-like object this proves (if known).
    - steps can be filled later with a more structured proof decomposition.
    """
    parent_id: Optional[str] = None
    strategy_tags: List[str] = field(default_factory=list)    # e.g. ["induction", "by contradiction"]
    steps: List[Span] = field(default_factory=list)


# ---------------------------------------------------------------------
# Algorithms
# ---------------------------------------------------------------------


@dataclass
class AlgoParam:
    """
    Algorithm parameter (input / output / hyperparameter).
    """
    name: str
    role: str                        # "input", "output", "hyperparameter"
    type: Optional[str] = None       # e.g. "matrix", "real", "integer"
    description: Optional[str] = None
    constraints: List[Span] = field(default_factory=list)


@dataclass
class AlgoStep:
    """
    A single algorithm step (semantic), separate from the raw text.

    The existing parser fills the raw 'steps: List[Dict[str, Any]]' in Algorithm;
    this class is here for richer structure later.
    """
    index: int
    text: str
    step_type: str = "step"          # "for", "while", "if", "step", ...
    modifies: List[str] = field(default_factory=list)
    uses: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Algorithm(MathObject):
    """
    Algorithm with structured steps (heuristic + optional enriched structure).

    NOTE: 'steps: List[Dict[str, Any]]' is kept for backward-compatibility with
    your current parser. You can gradually move to 'structured_steps' if desired.
    """
    env_name: str = "algorithm"
    steps: List[Dict[str, Any]] = field(default_factory=list)          # legacy: {"type": "...", "text": str}
    structured_steps: List[AlgoStep] = field(default_factory=list)     # richer structure

    input_params: List[AlgoParam] = field(default_factory=list)
    output_params: List[AlgoParam] = field(default_factory=list)
    preconditions: List[Span] = field(default_factory=list)
    postconditions: List[Span] = field(default_factory=list)


# ---------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------


@dataclass
class TableObject(MathObject):
    """
    Table with parsed cells (best-effort).
    """
    env_name: Optional[str] = None  # e.g. "table", "tabular", "longtable"
    caption: Optional[str] = None
    cells: List[List[str]] = field(default_factory=list)  # rows x columns


# ---------------------------------------------------------------------
# Relations & PaperGraph
# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
# Relations & PaperGraph
# ---------------------------------------------------------------------


# Canonical relation type names (just constants to avoid typos)
REL_USES = "uses"                  # proof/theorem/algorithm uses X
REL_DEPENDS_ON = "depends_on"      # theorem depends on X (one of several)
REL_FOLLOWS_FROM = "follows_from"  # A follows_from B (B ⇒ A)

REL_HAS_PART = "has_part"          # structural: A has_part B

REL_GENERALIZES = "generalizes"    # conceptual: A generalizes B (more general → more specific)
REL_RELATED_TO = "related_to"      # conceptual (usually symmetric, weak)
REL_EQUIVALENT_TO = "equivalent_to"  # conceptual, symmetric equivalence

# Simple mapping from relation_type to a coarse category
RELATION_CATEGORY_MAP: Dict[str, str] = {
    REL_USES: "logical",
    REL_DEPENDS_ON: "logical",
    REL_FOLLOWS_FROM: "logical",
    REL_HAS_PART: "structural",
    REL_GENERALIZES: "conceptual",
    REL_RELATED_TO: "conceptual",
    REL_EQUIVALENT_TO: "conceptual",
}


def infer_relation_category(relation_type: str) -> str:
    """
    Given a relation_type string, return a coarse category:
    'logical', 'structural', 'conceptual', or 'other'.

    This is used as a default when adding relations.
    """
    return RELATION_CATEGORY_MAP.get(relation_type, "other")


@dataclass
class Relation:
    """
    Directed (or symmetric) edge between two math objects.

    Canonical directions:

        uses(A, B):
            - A is a proof/theorem/algorithm that uses B in its text/proof.

        depends_on(A, B):
            - Theorem/Result A depends on B as one of its prerequisites.
              (If B is invalid, the proof of A collapses.)

        follows_from(A, B):
            - A follows from B; B ⇒ A. Typically corollaries or special cases.
              (Once B is known, A is almost immediate.)

        has_part(A, B):
            - A has_part B (A is a whole, B is a part, e.g. theorem has_part proof).

        generalizes(A, B):
            - A generalizes B (A is more general, B is a special case).
              Inverse view: B specializes A.

        related_to(A, B), equivalent_to(A, B):
            - Conceptual relations. Usually treated as symmetric.
    """
    source_id: str
    target_id: str
    relation_type: str               # e.g. "uses", "depends_on", "follows_from", ...

    # Extra structure to help with visualization / filtering
    category: str = "logical"        # "logical", "structural", "conceptual", "other"
    directed: bool = True            # True for canonical directed relations
    symmetric: bool = False          # True for symmetric conceptual relations
    metadata: Dict[str, Any] = field(default_factory=dict)  # free-form extras


@dataclass
class PaperGraph:
    """
    Container for all objects and relations in a single paper.

    This is the main thing you serialize to JSON and later visualize.
    """
    paper_id: Optional[str]
    objects: Dict[str, MathObject] = field(default_factory=dict)
    relations: List[Relation] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Basic object / relation management
    # ------------------------------------------------------------------

    def add_object(self, obj: MathObject) -> None:
        """Register a MathObject in the graph."""
        self.objects[obj.id] = obj

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        *,
        category: Optional[str] = None,
        directed: bool = True,
        symmetric: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a generic relation.

        - Only canonical directions should be stored (e.g. generalizes, not specializes).
        - If category is None, it is inferred from relation_type.
        - 'symmetric=True' can be used for relations like equivalent_to / related_to,
          and your visualization can treat them as undirected edges.
        """
        if source_id not in self.objects or target_id not in self.objects:
            # silently ignore or raise; for now, ignore
            return

        if category is None:
            category = infer_relation_category(relation_type)

        if metadata is None:
            metadata = {}

        self.relations.append(
            Relation(
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                category=category,
                directed=directed,
                symmetric=symmetric,
                metadata=metadata,
            )
        )

    # ------------------------------------------------------------------
    # Typed helper methods for common relations
    # ------------------------------------------------------------------

    # --- logical relations ---

    def add_uses(self, user_id: str, used_id: str, **kwargs: Any) -> None:
        """
        user_id uses used_id (proof/theorem/algorithm uses lemma/definition/equation).
        """
        self.add_relation(user_id, used_id, REL_USES, category="logical", directed=True, **kwargs)

    def add_depends_on(self, theorem_id: str, prereq_id: str, **kwargs: Any) -> None:
        """
        theorem_id depends_on prereq_id as one of several prerequisites.

        Canonical direction: theorem_id → prereq_id.
        """
        self.add_relation(theorem_id, prereq_id, REL_DEPENDS_ON, category="logical", directed=True, **kwargs)

    def add_follows_from(self, consequence_id: str, premise_id: str, **kwargs: Any) -> None:
        """
        consequence_id follows_from premise_id (premise ⇒ consequence).

        Canonical direction: consequence_id → premise_id.
        """
        self.add_relation(consequence_id, premise_id, REL_FOLLOWS_FROM, category="logical", directed=True, **kwargs)

    # --- structural relations ---

    def add_has_part(self, whole_id: str, part_id: str, **kwargs: Any) -> None:
        """
        whole_id has_part part_id.

        Canonical direction: whole_id → part_id.

        Inverse view (not stored): part_id is_part_of whole_id.
        """
        self.add_relation(whole_id, part_id, REL_HAS_PART, category="structural", directed=True, **kwargs)

    # --- conceptual relations ---

    def add_generalizes(self, more_general_id: str, more_specific_id: str, **kwargs: Any) -> None:
        """
        more_general_id generalizes more_specific_id.

        Canonical direction: more_general_id → more_specific_id.

        Inverse view: more_specific_id specializes more_general_id.
        """
        self.add_relation(more_general_id, more_specific_id, REL_GENERALIZES, category="conceptual", directed=True, **kwargs)

    def add_related_to(self, a_id: str, b_id: str, **kwargs: Any) -> None:
        """
        a_id related_to b_id (weak conceptual relation, usually symmetric).

        Implementation: store a single edge a_id → b_id with symmetric=True
        and let visualization treat it as undirected. If you want a fully
        symmetric representation, you can call this twice with swapped ids.
        """
        self.add_relation(a_id, b_id, REL_RELATED_TO, category="conceptual", directed=False, symmetric=True, **kwargs)

    def add_equivalent_to(self, a_id: str, b_id: str, **kwargs: Any) -> None:
        """
        a_id equivalent_to b_id (conceptual equivalence, symmetric).

        Again, we store one canonical edge with symmetric=True, and let
        visualization treat it as an undirected edge between a_id and b_id.
        """
        self.add_relation(a_id, b_id, REL_EQUIVALENT_TO, category="conceptual", directed=False, symmetric=True, **kwargs)

    # ------------------------------------------------------------------
    # Query helpers: outgoing / incoming edges
    # ------------------------------------------------------------------

    def outgoing(self, obj_id: str, relation_type: Optional[str] = None) -> List[Relation]:
        """
        All relations with source == obj_id, optionally filtered by relation_type.
        """
        return [
            r for r in self.relations
            if r.source_id == obj_id and (relation_type is None or r.relation_type == relation_type)
        ]

    def incoming(self, obj_id: str, relation_type: Optional[str] = None) -> List[Relation]:
        """
        All relations with target == obj_id, optionally filtered by relation_type.
        """
        return [
            r for r in self.relations
            if r.target_id == obj_id and (relation_type is None or r.relation_type == relation_type)
        ]

    # ------------------------------------------------------------------
    # Derived inverse views for canonical pairs
    # ------------------------------------------------------------------

    # --- generalizes / specializes ---

    def specializations_of(self, general_id: str) -> List[str]:
        """
        Return IDs of objects that are special cases of the given object.

        These are targets of generalizes(general_id, ·).
        """
        return [
            r.target_id
            for r in self.outgoing(general_id, REL_GENERALIZES)
        ]

    def generalizations_of(self, specific_id: str) -> List[str]:
        """
        Return IDs of objects that generalize the given object.

        These are sources of generalizes(·, specific_id).
        """
        return [
            r.source_id
            for r in self.incoming(specific_id, REL_GENERALIZES)
        ]

    # --- has_part / is_part_of ---

    def parts_of(self, whole_id: str) -> List[str]:
        """
        Return IDs of objects that are parts of the given whole object.

        These are targets of has_part(whole_id, ·).
        """
        return [
            r.target_id
            for r in self.outgoing(whole_id, REL_HAS_PART)
        ]

    def whole_of(self, part_id: str) -> List[str]:
        """
        Return IDs of objects that the given object is a part of.

        These are sources of has_part(·, part_id).
        """
        return [
            r.source_id
            for r in self.incoming(part_id, REL_HAS_PART)
        ]

    # ------------------------------------------------------------------
    # Convenience: edge list for graph libraries
    # ------------------------------------------------------------------

    def as_edge_list(self) -> List[Tuple[str, str, str]]:
        """
        Return (source_id, target_id, relation_type) triples.

        This is a minimal view; for richer graph libraries you may instead
        use self.relations directly (with category/metadata).
        """
        return [(r.source_id, r.target_id, r.relation_type) for r in self.relations]

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to a plain JSON-serializable dict.

        For each MathObject we attach a "__class__" key so that from_dict
        can reconstruct the concrete subclass (TheoremLike, Definition, Algorithm, ...).
        """

        def obj_to_dict(o: MathObject) -> Dict[str, Any]:
            d = asdict(o)
            d["__class__"] = o.__class__.__name__
            return d

        return {
            "paper_id": self.paper_id,
            "objects": {obj_id: obj_to_dict(obj) for obj_id, obj in self.objects.items()},
            "relations": [asdict(r) for r in self.relations],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PaperGraph":
        """
        Reconstruct a PaperGraph from a dict produced by to_dict().

        This is handy if you want to deserialize later and still get
        the correct subclasses.
        """
        cls_map: Dict[str, Type[MathObject]] = {
            "MathObject": MathObject,
            "TheoremLike": TheoremLike,
            "Problem": Problem,
            "Conjecture": Conjecture,
            "Definition": Definition,
            "Proof": Proof,
            "Algorithm": Algorithm,
            "TableObject": TableObject,
            "Equation": Equation,
        }

        pg = PaperGraph(paper_id=d.get("paper_id"))

        for obj_id, od in d.get("objects", {}).items():
            cls_name = od.pop("__class__", "MathObject")
            cls = cls_map.get(cls_name, MathObject)
            obj = cls(**od)  # type: ignore[arg-type]
            pg.objects[obj_id] = obj

        for r in d.get("relations", []):
            # Backwards-compatible: older JSON may not have category/directed/symmetric/metadata
            if "category" not in r:
                r["category"] = infer_relation_category(r.get("relation_type", ""))
            if "directed" not in r:
                r["directed"] = True
            if "symmetric" not in r:
                r["symmetric"] = False
            if "metadata" not in r:
                r["metadata"] = {}
            pg.relations.append(Relation(**r))

        return pg
