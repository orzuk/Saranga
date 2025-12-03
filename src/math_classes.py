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
    caption: Optional[str] = None
    cells: List[List[str]] = field(default_factory=list)  # rows x columns


# ---------------------------------------------------------------------
# Relations & PaperGraph
# ---------------------------------------------------------------------


@dataclass
class Relation:
    """
    Directed edge between two math objects.

    Examples:
        - theorem uses lemma
        - proof proves theorem
        - algorithm relies on theorem
        - equation is in_environment_of a theorem
    """
    source_id: str
    target_id: str
    relation_type: str   # e.g. "uses", "used_in_proof", "special_case_of", "generalization_of"


@dataclass
class PaperGraph:
    """
    Container for all objects and relations in a single paper.

    This is the main thing you serialize to JSON.
    """
    paper_id: str
    objects: Dict[str, MathObject] = field(default_factory=dict)
    relations: List[Relation] = field(default_factory=list)

    # ----- basic object / relation management -----

    def add_object(self, obj: MathObject) -> None:
        self.objects[obj.id] = obj

    def add_relation(self, source_id: str, target_id: str, relation_type: str) -> None:
        if source_id in self.objects and target_id in self.objects:
            self.relations.append(Relation(source_id, target_id, relation_type))

    def get_by_label(self, label: str) -> Optional[MathObject]:
        for obj in self.objects.values():
            if obj.label == label:
                return obj
        return None

    def as_edge_list(self) -> List[Tuple[str, str, str]]:
        """Return (source_id, target_id, relation_type) triples."""
        return [(r.source_id, r.target_id, r.relation_type) for r in self.relations]

    # ----- serialization helpers -----

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to a plain JSON-serializable dict.

        We attach a "__class__" key so that from_dict can reconstruct the
        concrete subclass (TheoremLike, Definition, Algorithm, ...).
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

        pg = PaperGraph(paper_id=d["paper_id"])

        for obj_id, od in d["objects"].items():
            cls_name = od.pop("__class__", "MathObject")
            cls = cls_map.get(cls_name, MathObject)
            obj = cls(**od)  # type: ignore[arg-type]
            pg.objects[obj_id] = obj

        for r in d["relations"]:
            pg.relations.append(Relation(**r))

        return pg
