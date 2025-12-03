#!/usr/bin/env python3
"""
math_paper_parser.py

Heuristic LaTeX parser for mathematical papers.

Features:
- Accepts local .tex file OR arXiv ID OR arXiv URL
- Downloads arXiv source tarball automatically when needed
- Extracts:
    - definitions
    - theorems / lemmas / propositions / corollaries / claims / conjectures / problems
    - proofs
    - algorithms
    - tables
- Builds a relation graph
- Can print a summary AND dump structured output to JSON
"""
from __future__ import annotations

import os
import re
import argparse
import json
import tarfile
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

try:
    from pyvis.network import Network
except Exception as e:
    print(f"[WARN] Could not load pyvis for interactive network html plot: {e}")

import requests  # pip install requests

import networkx as nx  # For drawing
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from extract_arxiv_funcs import (
    normalize_arxiv_id,
    fetch_arxiv_metadata,
    resolve_source_to_tex_local_first,
)

from config import FULL_PAPERS_DIR


# ---------------------------------------------------------------------
# Data classes for paper objects
# ---------------------------------------------------------------------


@dataclass
class MathObject:
    """Base class for all extracted objects."""
    id: str                   # internal id, e.g. T1, D3, L2
    kind: str                 # theorem, lemma, definition, proof, algorithm, table, ...
    index: int                # running index per kind (1-based)
    label: Optional[str]      # \label{...} if present
    name: Optional[str]       # optional name/heading e.g. [Strong law]
    raw_latex: str            # full LaTeX body of the environment
    clean_text: str           # LaTeX stripped of markup (best-effort)
    paper_id: Optional[str] = None  # optional arxiv id etc.


@dataclass
class Equation(MathObject):
    """Equation or displayed math block."""
    env_name: str = ""                 # e.g. 'equation', 'align', 'displaymath', 'bracket', 'dollar'
    display_type: str = "env"          # 'env', 'dollar', 'bracket'
    parent_id: Optional[str] = None    # id of theorem/definition/proof/etc. containing it (if any)


@dataclass
class TheoremLike(MathObject):
    """Theorem-like object with assumptions and statement split heuristically."""
    env_name: str = ""        # actual LaTeX env name e.g. 'theorem', 'lemma'
    assumptions: str = ""     # heuristic: 'Let/Suppose/Assume' sentences
    statement: str = ""       # rest of the text


@dataclass
class Problem(TheoremLike):
    """
    Mathematical problem / RHP / optimisation problem.

    Additional semantic fields are currently left mostly empty (None),
    but the structure is there for future use.
    """
    problem_type: Optional[str] = None     # e.g. "RHP", "optimization", "other"
    constraints: Optional[str] = None      # textual description of constraints
    objective: Optional[str] = None        # optimisation objective, if any
    existence_known: Optional[bool] = None
    uniqueness_known: Optional[bool] = None
    complexity: Optional[str] = None       # e.g. "polynomial time", "NP-hard", etc.


@dataclass
class Conjecture(TheoremLike):
    """Conjecture object; same structure as TheoremLike but separate class."""
    pass


@dataclass
class Definition(MathObject):
    env_name: str = ""


@dataclass
class Proof(MathObject):
    """Proof, optionally linked to a theorem/lemma/etc."""
    parent_id: Optional[str] = None  # id of theorem-like object this proves, if detected


@dataclass
class Algorithm(MathObject):
    """Algorithm with structured steps (heuristic)."""
    env_name: str = "algorithm"
    steps: List[Dict[str, Any]] = field(default_factory=list)  # {"type": "for/while/if/step", "text": str}


@dataclass
class TableObject(MathObject):
    """Table with parsed cells (best-effort)."""
    caption: Optional[str] = None
    cells: List[List[str]] = field(default_factory=list)  # rows x columns


@dataclass
class Relation:
    """Directed edge between two math objects."""
    source_id: str
    target_id: str
    relation_type: str   # e.g. "uses", "used_in_proof", "special_case_of", "generalization_of"


@dataclass
class PaperGraph:
    """Container for all objects and relations in a single paper."""
    paper_id: str
    objects: Dict[str, MathObject] = field(default_factory=dict)
    relations: List[Relation] = field(default_factory=list)

    def add_object(self, obj: MathObject):
        self.objects[obj.id] = obj

    def add_relation(self, source_id: str, target_id: str, relation_type: str):
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

    # --------- serialization helpers ----------

    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain-JSON-serializable dict."""

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
        """(Optional) reconstruct from dict, if needed later."""
        cls_map = {
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
            obj = cls(**od)
            pg.objects[obj_id] = obj
        for r in d["relations"]:
            pg.relations.append(Relation(**r))
        return pg


# ---------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------


class PaperParser:
    """
    Heuristic LaTeX parser for a single paper.

    Usage:
        parser = PaperParser()
        graph = parser.parse_file("paper.tex")
    """

    # canonical mapping from LaTeX environment names to "kind"
    BASE_ENV_KIND_MAP = {
        "theorem": "theorem",
        "Theorem": "theorem",
        "thm": "theorem",

        "lemma": "lemma",
        "Lemma": "lemma",
        "lem": "lemma",

        "proposition": "proposition",
        "Proposition": "proposition",
        "prop": "proposition",

        "corollary": "corollary",
        "Corollary": "corollary",
        "cor": "corollary",

        "claim": "claim",
        "Claim": "claim",

        "definition": "definition",
        "Definition": "definition",
        "defn": "definition",
        "dfn": "definition",
        "Def": "definition",
        "Defn": "definition",

        "proof": "proof",
        "Proof": "proof",

        "algorithm": "algorithm",
        "algorithm*": "algorithm",

        "table": "table",

        "theo": "theorem",
        "conjecture": "conjecture",
        "Conjecture": "conjecture",

        "problem": "problem",
        "Problem": "problem",
    }

    THEOREM_LIKE_KINDS = {
        "theorem",
        "lemma",
        "proposition",
        "corollary",
        "claim",
        "conjecture",
        "problem",
    }

    def __init__(
        self,
        paper_id: Optional[str] = None,
        definition_mode: str = "both",  # 'manual', 'llm', or 'both'
        llm_model: str = "gpt-4o-mini",
        llm_chunk_chars: int = 8000,
    ):
        """
        Parameters
        ----------
        paper_id : Optional[str]
            Identifier for this paper.
        definition_mode : {'manual', 'llm', 'both'}
            - 'manual': only use rule-based extraction.
            - 'llm'   : only use LLM-based extraction.
            - 'both'  : use both and merge (default).
        llm_model : str
            Model name for LLM extraction (if used).
        llm_chunk_chars : int
            Max characters per chunk when calling the LLM.
        """
        self.paper_id = paper_id or "paper"
        self.definition_mode = definition_mode
        self.llm_model = llm_model
        self.llm_chunk_chars = llm_chunk_chars

        # these will be updated with \newtheorem info
        self.env_kind_map = dict(self.BASE_ENV_KIND_MAP)

    # ------------------------------------------------------------------
    # Macro / input expansion
    # ------------------------------------------------------------------

    def _expand_macros(self, text: str) -> str:
        """
        Expand simple \\newcommand / \\renewcommand macros with NO arguments.

        E.g. turns:
            \\newcommand{\\be}{\\begin{equation}}
        into removal of the definition and replacement of all '\\be' occurrences
        by '\\begin{equation}'.

        We ignore macros with arguments like \\newcommand{\\abs}[1]{...}.
        """
        pattern = re.compile(
            r"\\(?:re)?newcommand\*?\s*{\\([a-zA-Z@]+)}\s*{([^}]*)}",
            flags=re.DOTALL,
        )

        macros: Dict[str, str] = {}

        def collect_macro(m: re.Match) -> str:
            name = m.group(1)          # e.g. 'be'
            body = m.group(2)          # e.g. '\begin{equation}'
            macros[name] = body
            # remove the definition itself from the text
            return ""

        # 1) strip definitions and collect macro map
        text = pattern.sub(collect_macro, text)

        # 2) expand occurrences of each macro
        for name, body in macros.items():
            # match \name not followed by letter/@ (so we don't hit \nameXYZ)
            macro_use_pattern = re.compile(rf"\\{name}(?![A-Za-z@])")

            # IMPORTANT: use a function so 'body' is used literally (backslashes ok)
            text = macro_use_pattern.sub(lambda _: body, text)

        return text

    def _normalize_simple_ref_macros(self, text: str) -> str:
        """
        Detect simple 1-argument \\newcommand/\\renewcommand macros that
        only wrap a \\ref/\\eqref/\\autoref, and rewrite their uses to the
        underlying standard ref command.
        """
        cmd_pat = re.compile(
            r"\\(?:re)?newcommand\*?\s*{\\([A-Za-z@]+)}\s*\[(\d+)\]\s*{([^}]*)}",
            flags=re.DOTALL,
        )

        ref_macros: Dict[str, str] = {}  # name -> 'ref' | 'eqref' | 'autoref'

        def strip_and_collect(m: re.Match) -> str:
            name = m.group(1)
            nargs = int(m.group(2))
            body = m.group(3)

            if nargs != 1:
                # leave definition as-is for other passes
                return m.group(0)

            if r"\eqref{#1}" in body:
                ref_macros[name] = "eqref"
                return ""  # remove definition
            elif r"\autoref{#1}" in body:
                ref_macros[name] = "autoref"
                return ""
            elif r"\ref{#1}" in body:
                ref_macros[name] = "ref"
                return ""
            else:
                # not a simple ref wrapper
                return m.group(0)

        # 1) Remove the ref-wrapper macro definitions, record mapping
        text = cmd_pat.sub(strip_and_collect, text)

        # 2) Rewrite uses of those macros
        for name, kind in ref_macros.items():
            # match \name{something}
            use_pat = re.compile(rf"\\{name}\{{([^}}]+)\}}")
            if kind == "eqref":
                text = use_pat.sub(r"\\eqref{\1}", text)
            elif kind == "autoref":
                text = use_pat.sub(r"\\autoref{\1}", text)
            else:  # 'ref'
                text = use_pat.sub(r"\\ref{\1}", text)

        return text

    def _expand_inputs(self, text: str, base_dir: Path, depth: int = 0, max_depth: int = 5) -> str:
        """
        Recursively expand \input{...} and \include{...} commands by inlining
        the contents of those files.

        - Searches relative to base_dir.
        - Supports filenames with or without extension: tries as-is, then .tex, then .txt.
        - Stops after max_depth to avoid infinite recursion.
        - At the top level (depth == 0), also expands simple \\newcommand macros.
        """
        if depth > max_depth:
            return text

        pattern = re.compile(r"\\(input|include)\s*(?:\[[^\]]*\])?\s*{([^}]+)}")

        while True:
            m = pattern.search(text)
            if not m:
                break

            cmd = m.group(1)
            fname = m.group(2).strip()

            # ignore includes that are clearly macro arguments, like {#1}
            if "#" in fname:
                print(f"[WARN] Skipping macro-like \\{cmd}{{{fname}}} (looks like an argument, not a file)")
                text = text[: m.start()] + "" + text[m.end():]
                continue

            # Resolve path: fname, fname.tex, fname.txt
            cand_paths = [
                base_dir / fname,
                base_dir / f"{fname}.tex",
                base_dir / f"{fname}.txt",
            ]
            inc_path = None
            for cp in cand_paths:
                if cp.exists():
                    inc_path = cp
                    break

            if inc_path is None:
                print(f"[WARN] Could not resolve \\{cmd}{{{fname}}} relative to {base_dir}")
                included = ""
            else:
                try:
                    included_raw = inc_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    print(f"[WARN] Failed to read included file {inc_path}")
                    included = ""
                else:
                    included = self._expand_inputs(
                        included_raw,
                        base_dir=inc_path.parent,
                        depth=depth + 1,
                        max_depth=max_depth,
                    )

            # Inline the included text
            text = text[: m.start()] + included + text[m.end():]

        # At the top level, after all includes are inlined, expand macros
        if depth == 0:
            # 1) normalise simple ref macros (1-arg wrappers)
            text = self._normalize_simple_ref_macros(text)
            # 2) expand 0-arg macros like \be -> \begin{equation}
            text = self._expand_macros(text)

        return text

    # ------------------------------------------------------------------
    # Equations
    # ------------------------------------------------------------------

    def _extract_equations_from_body(self, body: str, parent_id: Optional[str]) -> List[Equation]:
        """
        Extract equation-like displays inside a given LaTeX body.
        """
        equations: List[Equation] = []

        # 1) Environment-based displays
        env_pattern = re.compile(
            r"\\begin{(?P<env>equation\*?|align\*?|gather\*?|multline\*?)}(?P<body>.*?)\\end{\1}",
            flags=re.DOTALL,
        )
        for m in env_pattern.finditer(body):
            env_name = m.group("env")
            inner = m.group("body")
            label, _ = self._extract_label_and_name(inner)
            clean_text = self._clean_latex_to_text(inner)
            eq = Equation(
                id="",  # will be assigned later
                kind="equation",
                index=0,
                label=label,
                name=None,
                raw_latex=m.group(0),
                clean_text=clean_text,
                env_name=env_name,
                display_type="env",
                parent_id=parent_id,
            )
            equations.append(eq)

        # 2) $$ ... $$ blocks
        dollar_pattern = re.compile(r"\$\$(?P<body>.*?)\$\$", flags=re.DOTALL)
        for m in dollar_pattern.finditer(body):
            inner = m.group("body")
            label, _ = self._extract_label_and_name(inner)
            clean_text = self._clean_latex_to_text(inner)
            eq = Equation(
                id="",
                kind="equation",
                index=0,
                label=label,
                name=None,
                raw_latex=m.group(0),
                clean_text=clean_text,
                env_name="displaymath",
                display_type="dollar",
                parent_id=parent_id,
            )
            equations.append(eq)

        # 3) \[ ... \] blocks
        bracket_pattern = re.compile(r"\\\[(?P<body>.*?)\\\]", flags=re.DOTALL)
        for m in bracket_pattern.finditer(body):
            inner = m.group("body")
            label, _ = self._extract_label_and_name(inner)
            clean_text = self._clean_latex_to_text(inner)
            eq = Equation(
                id="",
                kind="equation",
                index=0,
                label=label,
                name=None,
                raw_latex=m.group(0),
                clean_text=clean_text,
                env_name="bracket",
                display_type="bracket",
                parent_id=parent_id,
            )
            equations.append(eq)

        return equations

    def _extract_equations(self, full_text: str, containers: List[MathObject]) -> List[Equation]:
        """
        Extract equations from inside theorem/definition/proof/algorithm bodies,
        and from the full document (top-level equations).
        """
        all_eqs: List[Equation] = []
        eq_idx = 0

        # 1) equations inside containers
        for obj in containers:
            eqs_here = self._extract_equations_from_body(obj.raw_latex, parent_id=obj.id)
            for eq in eqs_here:
                eq_idx += 1
                eq.id = f"E{eq_idx}"
                eq.index = eq_idx
                all_eqs.append(eq)

        # 2) top-level equations in the full text, with no parent
        top_eqs = self._extract_equations_from_body(full_text, parent_id=None)
        for eq in top_eqs:
            eq_idx += 1
            eq.id = f"E{eq_idx}"
            eq.index = eq_idx
            all_eqs.append(eq)

        return all_eqs

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def parse_file(self, path: str | Path) -> PaperGraph:
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="ignore")

        # 1) Merge all included files AND expand simple macros
        text = self._expand_inputs(text, base_dir=path.parent)

        # 2) Restrict to document body only
        m = re.search(r"\\begin{document}(.*)\\end{document}", text, flags=re.DOTALL)
        if m:
            text = m.group(1)

        # 3) Strip comments and parse \newtheorem
        text = self._strip_comments(text)
        self._parse_newtheorem(text)

        graph = PaperGraph(paper_id=self.paper_id)

        # ---- Theorem-like objects (including propositions, problems, conjectures) ----
        theorem_like: List[TheoremLike] = self._extract_theorem_like(text)

        # ---- Definitions: manual, LLM, or both ----
        manual_defs: List[Definition] = []
        llm_defs: List[Definition] = []

        if self.definition_mode in ("manual", "both"):
            manual_defs = self._extract_definitions_manual(text)

        if self.definition_mode in ("llm", "both"):
            try:
                llm_defs = self._extract_definitions_llm(
                    text,
                    llm_type="openai",
                    provider="hosted",
                    chunk_chars=self.llm_chunk_chars,
                    model=self.llm_model,
                )
            except Exception as e:  # noqa: BLE001
                print(
                    f"[WARN] parse_file: LLM definition extraction failed with error {e}; "
                    "continuing with manual definitions only."
                )
                llm_defs = []

        if self.definition_mode == "manual":
            definitions = manual_defs
        elif self.definition_mode == "llm":
            definitions = llm_defs
        else:  # 'both'
            definitions = self._merge_definitions(manual_defs, llm_defs)

        proofs = self._extract_proofs(text)
        algorithms = self._extract_algorithms(text)
        tables = self._extract_tables(text)

        # equations inside theorem/definition/proof/algorithm bodies
        containers: List[MathObject] = theorem_like + definitions + proofs + algorithms
        equations = self._extract_equations(text, containers)

        # Register all objects in the PaperGraph
        for obj in theorem_like + definitions + proofs + algorithms + tables + equations:
            obj.paper_id = self.paper_id
            graph.add_object(obj)

        # Linking and relations
        self._link_proofs_to_theorems(graph)
        self._build_relations(graph)

        return graph

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_comments(text: str) -> str:
        """Remove LaTeX comments (%) except escaped \%."""
        lines = []
        for line in text.splitlines():
            m = re.search(r"(?<!\\)%", line)
            if m:
                line = line[: m.start()]
            lines.append(line)
        return "\n".join(lines)

    def _parse_newtheorem(self, text: str) -> None:
        """
        Parse \\newtheorem definitions and populate env_kind_map.
        """
        # Start from a sensible base
        base_map = {
            "theorem": "theorem",
            "Theorem": "theorem",
            "thm": "theorem",
            "lemma": "lemma",
            "Lemma": "lemma",
            "proposition": "proposition",
            "Proposition": "proposition",
            "corollary": "corollary",
            "Corollary": "corollary",
            "claim": "claim",
            "Claim": "claim",
            "conclusion": "conclusion",
            "Conclusion": "conclusion",
            "definition": "definition",
            "Definition": "definition",
            "remark": "remark",
            "Remark": "remark",
            "example": "example",
            "Example": "example",
            "problem": "problem",
            "Problem": "problem",
            "conjecture": "conjecture",
            "Conjecture": "conjecture",
        }
        self.env_kind_map = dict(base_map)

        # \newtheorem{env}[counter]{Printed Name}
        pattern = re.compile(
            r"\\newtheorem\s*{([^}]+)}(?:\[[^\]]+\])?\s*{([^}]+)}",
            flags=re.DOTALL,
        )

        for env_name, printed in pattern.findall(text):
            env_name = env_name.strip()
            printed_clean = re.sub(r"[^a-z]", "", printed.lower())

            kind = None
            for candidate in [
                "theorem",
                "lemma",
                "proposition",
                "corollary",
                "definition",
                "remark",
                "example",
                "claim",
                "conclusion",
                "problem",
                "conjecture",
            ]:
                if candidate in printed_clean:
                    kind = candidate
                    break

            if kind:
                self.env_kind_map[env_name] = kind

    @staticmethod
    def _clean_latex_to_text(latex: str) -> str:
        """Best-effort LaTeX -> plain text cleaner (keeps math markers)."""
        latex = re.sub(r"\\(textbf|textit|emph|mathrm|mathbf|mathit|text)\s*{([^}]*)}", r"\2", latex)
        latex = re.sub(r"\$\$(.*?)\$\$", " [MATH] ", latex, flags=re.DOTALL)
        latex = re.sub(r"\$(.*?)\$", " [MATH] ", latex, flags=re.DOTALL)
        latex = re.sub(r"\\\[(.*?)\\\]", " [MATH] ", latex, flags=re.DOTALL)
        latex = re.sub(r"\\begin{equation\*?}(.*?)\\end{equation\*?}", " [MATH] ", latex, flags=re.DOTALL)
        latex = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:{[^}]*})?", "", latex)
        latex = re.sub(r"\s+", " ", latex)
        return latex.strip()

    @staticmethod
    def _extract_label_and_name(env_body: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract \\label{...} from environment body."""
        label_match = re.search(r"\\label{([^}]*)}", env_body)
        label = label_match.group(1).strip() if label_match else None
        return label, None

    # ------------------------------------------------------------------
    # Generic environment extraction
    # ------------------------------------------------------------------

    def _extract_envs(self, text: str, env_names: List[str]) -> List[Tuple[str, str, str]]:
        """
        Generic environment extractor.

        Returns list of (env_name, opt_name, body) where:
          \begin{env_name}[opt_name] body \end{env_name}
        """
        env_pattern = (
            r"\\begin{(" + "|".join(map(re.escape, env_names)) + r")}"
            r"(?:\[(?P<opt>[^\]]*)\])?"
            r"(?P<body>.*?)"
            r"\\end{\1}"
        )
        regex = re.compile(env_pattern, flags=re.DOTALL | re.IGNORECASE)
        results = []
        for m in regex.finditer(text):
            env = m.group(1)
            opt = m.group("opt")
            body = m.group("body")
            results.append((env, opt, body))
        return results

    # ------------------------------------------------------------------
    # Theorem-like extraction (theorem / lemma / proposition / corollary /
    # claim / conjecture / problem)
    # ------------------------------------------------------------------

    def _extract_theorem_like(self, text: str) -> List[TheoremLike]:
        env_names = [
            env for env, kind in self.env_kind_map.items()
            if kind in self.THEOREM_LIKE_KINDS
        ]
        print(f"[DEBUG] theorem-like env_names: {env_names}")

        if not env_names:
            return []

        found = self._extract_envs(text, env_names)
        print(f"[DEBUG] found {len(found)} theorem-like environments")

        counters: Dict[str, int] = {k: 0 for k in self.THEOREM_LIKE_KINDS}
        objects: List[TheoremLike] = []

        for env_name, opt_name, body in found:
            kind = self.env_kind_map.get(env_name, "theorem")
            counters.setdefault(kind, 0)
            counters[kind] += 1
            idx = counters[kind]

            # ID prefix: T (theorem), L (lemma), P (proposition/problem/proof is different),
            # C (corollary/claim/conjecture), etc. For simplicity keep first letter.
            obj_id = kind[0].upper() + str(idx)

            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)
            assumptions, statement = self._split_assumptions_statement(clean_text)

            # Specialised classes for some kinds
            if kind == "problem":
                obj: TheoremLike = Problem(
                    id=obj_id,
                    kind=kind,
                    index=idx,
                    label=label,
                    name=opt_name.strip() if opt_name else None,
                    raw_latex=body,
                    clean_text=clean_text,
                    env_name=env_name,
                    assumptions=assumptions,
                    statement=statement,
                )
            elif kind == "conjecture":
                obj = Conjecture(
                    id=obj_id,
                    kind=kind,
                    index=idx,
                    label=label,
                    name=opt_name.strip() if opt_name else None,
                    raw_latex=body,
                    clean_text=clean_text,
                    env_name=env_name,
                    assumptions=assumptions,
                    statement=statement,
                )
            else:
                obj = TheoremLike(
                    id=obj_id,
                    kind=kind,
                    index=idx,
                    label=label,
                    name=opt_name.strip() if opt_name else None,
                    raw_latex=body,
                    clean_text=clean_text,
                    env_name=env_name,
                    assumptions=assumptions,
                    statement=statement,
                )

            objects.append(obj)

        return objects

    @staticmethod
    def _split_assumptions_statement(text: str) -> Tuple[str, str]:
        """
        Very heuristic split of assumptions vs statement.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        assumptions_sentences = []
        statement_sentences = []

        in_assumptions = True
        for s in sentences:
            s_strip = s.strip()
            if not s_strip:
                continue
            lower = s_strip.lower()
            if in_assumptions and (
                lower.startswith("let ")
                or lower.startswith("suppose ")
                or lower.startswith("assume ")
                or lower.startswith("given ")
            ):
                assumptions_sentences.append(s_strip)
            elif in_assumptions and (
                lower.startswith("then ")
                or lower.startswith("hence ")
                or lower.startswith("therefore ")
            ):
                in_assumptions = False
                statement_sentences.append(s_strip)
            else:
                if in_assumptions:
                    assumptions_sentences.append(s_strip)
                else:
                    statement_sentences.append(s_strip)

        return " ".join(assumptions_sentences), " ".join(statement_sentences)

    # ------------------------------------------------------------------
    # Definitions (manual + optional LLM)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_inline_text(text: str, max_len: int = 80) -> str:
        """
        Simple cleaner for inline/short texts.
        """
        text = re.sub(r"\s+", " ", text)
        text = text.strip(" \t\n\r.,;:()[]{}")
        if len(text) > max_len:
            text = text[: max_len - 3] + "..."
        return text

    def _extract_definitions_manual(self, text: str) -> List[Definition]:
        """
        Extract Definition objects using only heuristic / rule-based methods.

        Includes:
        A. Definition environments defined via \\newtheorem (env_kind_map=='definition').
        B. Textual 'Definition 2.1.' style markers.
        C1. Inline 'We define X as/by/to be ...'.
        C2. Inline 'X is defined as/to be ...'.
        C3. Inline 'Let X be ...' (for things like 'Let \\phi be a p×p matrix-valued function...').
        """
        objects: List[Definition] = []
        idx = 0

        # --- A. Environment-based definitions ---
        env_names = [env for env, kind in self.env_kind_map.items() if kind == "definition"]
        if env_names:
            env_defs = self._extract_envs(text, env_names)
            for env_name, opt_name, body in env_defs:
                idx += 1
                obj_id = f"D{idx}"
                label, _ = self._extract_label_and_name(body)
                clean_text = self._clean_latex_to_text(body)
                objects.append(
                    Definition(
                        id=obj_id,
                        kind="definition",
                        index=idx,
                        label=label,
                        name=opt_name.strip() if opt_name else None,
                        raw_latex=body,
                        clean_text=clean_text,
                        env_name=env_name,
                    )
                )

        # --- B. Textual 'Definition 2.1.' style definitions ---
        definition_text_pattern = re.compile(
            r"(?:^|\n)\s*(?:\\noindent\s*)?"
            r"(?:\\textbf\{)?Definition\s+([0-9]+(?:\.[0-9]+)*)\.?(?:\})?\s*"
            r"(?P<body>.*?)"
            r"(?=(?:^|\n)\s*(?:\\noindent\s*)?(?:\\textbf\{)?Definition\s+[0-9]|"
            r"\\begin\{|\\section\b|\\subsection\b|\\end{document})",
            flags=re.DOTALL,
        )

        for m in definition_text_pattern.finditer(text):
            idx += 1
            number = m.group(1)
            body = m.group("body")
            obj_id = f"D{idx}"
            name = f"Definition {number}"
            clean_text = self._clean_latex_to_text(body)
            objects.append(
                Definition(
                    id=obj_id,
                    kind="definition",
                    index=idx,
                    label=None,
                    name=name,
                    raw_latex=body,
                    clean_text=clean_text,
                    env_name="textual",
                )
            )

        # --- C. Inline textual definitions -------------------------------

        # C1: "We (also) define X as/by/to be ..." (case insensitive)
        inline_define_pattern = re.compile(
            r"(?P<full>"
            r"(?:We\s+)?(?:also\s+)?define\s+"
            r"(?P<name>[^.]{1,80}?)"
            r"\s*(?:as|by|to\s+be|:=|=)"
            r"[^.]*\.)",
            flags=re.IGNORECASE | re.DOTALL,
        )

        # C2: "X is defined as/to be ..." (case insensitive)
        inline_defined_as_pattern = re.compile(
            r"(?P<full>"
            r"(?P<name>[^.]{1,80}?)"
            r"\s+is\s+defined\s+"
            r"(?:as|to\s+be)\s"
            r"[^.]*\.)",
            flags=re.IGNORECASE | re.DOTALL,
        )

        # C3: "Let X be ..." used for defining an object.
        # Example: "Let \\phi be a p×p matrix-valued function that has Fourier series expansion..."
        inline_let_pattern = re.compile(
            r"(?P<full>"
            r"(?:Let|let)\s+"
            r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_]+))"
            r"[^.]{0,200}?"          # up to some descriptive text
            r"\s+be\s+[^.]*\.)",
            flags=re.DOTALL,
        )

        def extract_name_hint(raw_name: str) -> str:
            raw_name = raw_name.strip()
            m_math = re.search(r"\$(.+?)\$", raw_name)
            if m_math:
                return self._normalize_inline_text(m_math.group(1), max_len=80)
            return self._normalize_inline_text(self._clean_latex_to_text(raw_name), max_len=80)

        def add_inline_definition(match: re.Match, source: str):
            nonlocal idx, objects
            full = match.group("full")
            name_raw = match.group("name")

            name_hint = extract_name_hint(name_raw)
            clean_text = self._clean_latex_to_text(full)
            idx += 1
            obj_id = f"D{idx}"
            objects.append(
                Definition(
                    id=obj_id,
                    kind="definition",
                    index=idx,
                    label=None,
                    name=name_hint or None,
                    raw_latex=full,
                    clean_text=clean_text,
                    env_name=source,
                )
            )

        for m in inline_define_pattern.finditer(text):
            add_inline_definition(m, "inline_define")

        for m in inline_defined_as_pattern.finditer(text):
            add_inline_definition(m, "inline_defined_as")

        for m in inline_let_pattern.finditer(text):
            add_inline_definition(m, "inline_let")

        print(f"[INFO] _extract_definitions_manual: found {len(objects)} definitions (all kinds).")
        return objects

    # Backwards-compatible wrapper
    def _extract_definitions(self, text: str) -> List[Definition]:
        return self._extract_definitions_manual(text)

    # ------------------------------------------------------------------
    # LLM-based definitions
    # ------------------------------------------------------------------

    def _extract_definitions_llm(
        self,
        text: str,
        llm_type: str = "openai",
        provider: str = "hosted",
        chunk_chars: int = 8000,
        base_prompt: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ) -> List[Definition]:
        """
        Use an LLM to extract definitions directly from LaTeX text.
        """
        if llm_type != "openai" or provider != "hosted":
            print(
                f"[WARN] _extract_definitions_llm: llm_type={llm_type}, "
                f"provider={provider} not implemented (returning empty list)."
            )
            return []

        try:
            import openai  # type: ignore[import]
        except ImportError:
            print(
                "[WARN] _extract_definitions_llm: openai package not installed. "
                "Run `pip install openai` and set OPENAI_API_KEY."
            )
            return []

        if not os.getenv("OPENAI_API_KEY"):
            print(
                "[WARN] _extract_definitions_llm: OPENAI_API_KEY not set; "
                "skipping LLM extraction."
            )
            return []

        if base_prompt is None:
            base_prompt = (
                "You are a LaTeX-aware mathematical text parser.\n\n"
                "Task: From the following LaTeX fragment, extract ONLY *definitions*:\n"
                "places where the authors introduce a new mathematical object, "
                "notation, or concept. Include both formal 'Definition' style text "
                "and informal sentences like 'We define...', 'Let X be...', "
                "'is defined as', etc.\n\n"
                "For each definition, return a JSON object with fields:\n"
                "  - raw_latex: exact LaTeX snippet for the definition (one or a few sentences).\n"
                "  - short_name: very short label (1–6 words) or symbol, e.g. 'Toeplitz matrix T_phi'.\n"
                "  - clean_text: plain English explanation (no LaTeX commands, but you may keep math symbols).\n"
                "  - anchor: a short diagnostic string (first 60–80 characters of the definition).\n\n"
                "Return a *pure JSON array* of such objects, with no extra text before or after.\n"
            )

        client = openai.ChatCompletion  # type: ignore[attr-defined]

        def call_llm(chunk_text: str) -> List[dict]:
            try:
                response = client.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You extract structured data from LaTeX."},
                        {
                            "role": "user",
                            "content": base_prompt + "\n\n```latex\n" + chunk_text + "\n```",
                        },
                    ],
                    temperature=0.1,
                )
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] _extract_definitions_llm: OpenAI API error: {e}")
                return []

            try:
                text_out = response["choices"][0]["message"]["content"]
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] _extract_definitions_llm: unexpected response format: {e}")
                return []

            text_out = text_out.strip()
            if text_out.startswith("```"):
                text_out = re.sub(r"^```[a-zA-Z]*\s*", "", text_out)
                text_out = re.sub(r"```$", "", text_out).strip()

            try:
                data = json.loads(text_out)
            except json.JSONDecodeError:
                print(
                    "[WARN] _extract_definitions_llm: model output not valid JSON; "
                    "skipping this chunk."
                )
                return []

            if not isinstance(data, list):
                print(
                    "[WARN] _extract_definitions_llm: model output is not a JSON array; "
                    "skipping this chunk."
                )
                return []

            return data

        llm_defs: List[Definition] = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = min(len(text), start + chunk_chars)
            chunk = text[start:end]
            chunk_index += 1
            print(f"[DEBUG] _extract_definitions_llm: processing chunk {chunk_index}")

            json_defs = call_llm(chunk)
            for d in json_defs:
                raw = d.get("raw_latex") or ""
                short_name = d.get("short_name") or ""
                clean = d.get("clean_text") or ""
                anchor = d.get("anchor") or ""

                raw = str(raw)
                short_name = str(short_name)
                clean = str(clean)
                anchor = str(anchor)

                def_obj = Definition(
                    id="",
                    kind="definition",
                    index=0,
                    label=None,
                    name=short_name.strip() or None,
                    raw_latex=raw,
                    clean_text=clean.strip() or anchor.strip() or "",
                    env_name="llm",
                )
                llm_defs.append(def_obj)

            start = end

        print(f"[INFO] _extract_definitions_llm: collected {len(llm_defs)} LLM definitions.")
        return llm_defs

    @staticmethod
    def _jaccard_similarity(a: str, b: str) -> float:
        """
        Simple word-level Jaccard similarity between two short texts.
        """

        def to_set(s: str) -> set[str]:
            s = s.lower()
            s = re.sub(r"[^\w\s]", " ", s)
            tokens = [t for t in s.split() if t]
            return set(tokens)

        A = to_set(a)
        B = to_set(b)
        if not A or not B:
            return 0.0
        return len(A & B) / len(A | B)

    def _merge_definitions(
        self,
        manual_defs: List[Definition],
        llm_defs: List[Definition],
        similarity_threshold: float = 0.7,
    ) -> List[Definition]:
        """
        Merge manual and LLM-derived definitions with de-duplication.
        """
        merged: List[Definition] = []

        for d in manual_defs:
            merged.append(d)

        def is_duplicate(candidate: Definition, existing: List[Definition]) -> bool:
            for d in existing:
                name1 = (candidate.name or "").lower()
                name2 = (d.name or "").lower()
                if name1 and name2:
                    if name1 == name2:
                        return True
                    if len(name1) > 5 and (name1 in name2 or name2 in name1):
                        return True

                c1 = candidate.clean_text or ""
                c2 = d.clean_text or ""
                if not c1 or not c2:
                    continue
                if len(c1) > 20 and c1 in c2:
                    return True
                if len(c2) > 20 and c2 in c1:
                    return True

                sim = self._jaccard_similarity(c1, c2)
                if sim >= similarity_threshold:
                    return True

            return False

        for llm_def in llm_defs:
            if is_duplicate(llm_def, merged):
                continue
            merged.append(llm_def)

        for idx, d in enumerate(merged, start=1):
            d.index = idx
            d.id = f"D{idx}"

        print(
            f"[INFO] _merge_definitions: {len(manual_defs)} manual + "
            f"{len(llm_defs)} LLM -> {len(merged)} merged."
        )
        return merged

    # ------------------------------------------------------------------
    # Proofs
    # ------------------------------------------------------------------

    def _extract_proofs(self, text: str) -> List[Proof]:
        """Extract proofs (environment-based and textual)."""
        proofs: List[Proof] = []
        idx = 0

        # A. Standard \begin{proof}...\end{proof}
        env_pattern = re.compile(
            r"\\begin{proof}(?:\[(?P<opt>[^\]]*)\])?(?P<body>.*?)\\end{proof}",
            flags=re.DOTALL,
        )
        for m in env_pattern.finditer(text):
            header_opt = m.group("opt") or ""
            body = m.group("body")
            raw = m.group(0)

            label, name = self._extract_label_and_name(body)
            clean = self._clean_latex_to_text(body)

            idx += 1
            proof = Proof(
                id=f"P{idx}",
                kind="proof",
                index=idx,
                label=label,
                name=name,
                raw_latex=raw,
                clean_text=clean,
                parent_id=None,
            )

            mref = re.search(r"\\(?:ref|eqref|autoref){([^}]+)}", header_opt)
            if not mref:
                mref = re.search(r"\\(?:ref|eqref|autoref){([^}]+)}", body[:300])
            if mref:
                proof._target_theorem_label = mref.group(1)  # type: ignore[attr-defined]

            proofs.append(proof)

        # B. Textual proofs: \noindent{\sc Proof ...}: ...
        text_proof_pattern = re.compile(
            r"\\noindent\s*{\s*\\sc\s*([^}]*)}\s*:(?P<body>.*?)"
            r"(?=(\\noindent\s*{\s*\\sc)|\\section\b|\\subsection\b|"
            r"\\begin{[A-Za-z]+}|\\end{document})",
            flags=re.DOTALL,
        )

        for m in text_proof_pattern.finditer(text):
            header = m.group(1)
            body = m.group("body")
            raw = text[m.start():m.end()]

            label, name = self._extract_label_and_name(raw)
            clean = self._clean_latex_to_text(raw)

            idx += 1
            proof = Proof(
                id=f"P{idx}",
                kind="proof",
                index=idx,
                label=label,
                name=name,
                raw_latex=raw,
                clean_text=clean,
                parent_id=None,
            )

            mref = re.search(r"\\(?:ref|eqref|autoref){([^}]+)}", header)
            if mref:
                proof._target_theorem_label = mref.group(1)  # type: ignore[attr-defined]

            proofs.append(proof)

        return proofs

    # ------------------------------------------------------------------
    # Algorithms
    # ------------------------------------------------------------------

    def _extract_algorithms(self, text: str) -> List[Algorithm]:
        env_names = ["algorithm", "algorithm*"]
        found = self._extract_envs(text, env_names)
        idx = 0
        objects: List[Algorithm] = []

        for env_name, opt_name, body in found:
            idx += 1
            obj_id = "A" + str(idx)
            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)
            steps = self._parse_algorithm_steps(body)

            obj = Algorithm(
                id=obj_id,
                kind="algorithm",
                index=idx,
                label=label,
                name=opt_name.strip() if opt_name else None,
                raw_latex=body,
                clean_text=clean_text,
                env_name=env_name,
                steps=steps,
            )
            objects.append(obj)
        return objects

    @staticmethod
    def _parse_algorithm_steps(body: str) -> List[Dict[str, Any]]:
        """
        Very rough parser for algorithm pseudo-code.
        """
        steps = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            line_plain = re.sub(r"\\item\s*", "", line)
            line_plain = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:{[^}]*})?", "", line_plain)
            text = re.sub(r"\s+", " ", line_plain).strip()
            if not text:
                continue
            lower = text.lower()
            step_type = "step"
            if lower.startswith("for "):
                step_type = "for"
            elif lower.startswith("while "):
                step_type = "while"
            elif lower.startswith("if "):
                step_type = "if"
            steps.append({"type": step_type, "text": text})
        return steps

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def _extract_tables(self, text: str) -> List[TableObject]:
        """Extract \\begin{table} bodies and parse internal tabular as cells."""
        env_names = ["table"]
        found = self._extract_envs(text, env_names)
        idx = 0
        objects: List[TableObject] = []

        for env_name, opt_name, body in found:
            idx += 1
            obj_id = "TBL" + str(idx)
            label, _ = self._extract_label_and_name(body)
            caption = None
            cap_match = re.search(r"\\caption{([^}]*)}", body, flags=re.DOTALL)
            if cap_match:
                caption = cap_match.group(1).strip()
            cells = self._parse_tabular_cells(body)
            clean_text = self._clean_latex_to_text(body)
            obj = TableObject(
                id=obj_id,
                kind="table",
                index=idx,
                label=label,
                name=None,
                raw_latex=body,
                clean_text=clean_text,
                caption=caption,
                cells=cells,
            )
            objects.append(obj)
        return objects

    @staticmethod
    def _parse_tabular_cells(table_body: str) -> List[List[str]]:
        """Best-effort parsing of tabular rows inside a table."""
        m = re.search(
            r"\\begin{tabular}{[^}]*}(.*?)\\end{tabular}",
            table_body,
            flags=re.DOTALL,
        )
        if not m:
            return []
        tab_body = m.group(1)
        rows_raw = re.split(r"\\\\", tab_body)
        rows: List[List[str]] = []
        for row in rows_raw:
            row = row.strip()
            if not row or r"\hline" in row:
                continue
            cols = [re.sub(r"\s+", " ", c.strip()) for c in row.split("&")]
            cols = [c for c in cols if c]
            if cols:
                rows.append(cols)
        return rows

    # ------------------------------------------------------------------
    # Linking & relations
    # ------------------------------------------------------------------

    @staticmethod
    def _sort_objects_by_occurrence(graph: PaperGraph) -> List[MathObject]:
        # crude sort by kind then index
        return sorted(graph.objects.values(), key=lambda o: (o.kind, o.index))

    def _link_proofs_to_theorems(self, graph: PaperGraph) -> None:
        """
        Set proof.parent_id for each Proof object.

        Strategy:
        1. If the proof has a header-derived label, link to that theorem-like object.
        2. Otherwise, try the first \ref / \eqref / \autoref inside the proof body
           that points to a theorem-like.
        3. If all fails, link to the nearest preceding theorem-like by index.
        """
        label_to_theorem_id: Dict[str, str] = {}
        for obj in graph.objects.values():
            if isinstance(obj, TheoremLike) and getattr(obj, "label", None):
                label_to_theorem_id[obj.label] = obj.id

        proofs = [o for o in graph.objects.values() if isinstance(o, Proof)]
        theorems = [o for o in graph.objects.values() if isinstance(o, TheoremLike)]
        theorems_sorted = sorted(theorems, key=lambda t: t.index)

        ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")

        for proof in proofs:
            # 1. header-based label
            target_from_header = getattr(proof, "_target_theorem_label", None)
            if target_from_header and target_from_header in label_to_theorem_id:
                proof.parent_id = label_to_theorem_id[target_from_header]
                continue

            # 2. first ref in the proof body that points to a theorem-like
            raw = getattr(proof, "raw_latex", "") or ""
            m = ref_pattern.search(raw)
            if m:
                lbl = m.group(1)
                if lbl in label_to_theorem_id:
                    proof.parent_id = label_to_theorem_id[lbl]
                    continue

            # 3. nearest preceding theorem-like by index
            prev_candidates = [t for t in theorems_sorted if t.index <= proof.index]
            if prev_candidates:
                parent = prev_candidates[-1]
                proof.parent_id = parent.id

    def _build_relations(self, graph: PaperGraph):
        """
        Build relations between objects using:
        - \ref/\eqref/\autoref{label} patterns in theorem statements and proofs
        - phrase heuristics for 'special case of', 'generalization of'
        - equations belonging to parent environments
        - name-based heuristic for definitions
        """
        label_to_id: Dict[str, str] = {}
        for obj in graph.objects.values():
            if getattr(obj, "label", None):
                label_to_id[obj.label] = obj.id

        ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")

        # 1. References inside proofs -> 'used_in_proof' edges
        for obj in graph.objects.values():
            if not isinstance(obj, Proof):
                continue
            raw = getattr(obj, "raw_latex", "") or ""
            for label in ref_pattern.findall(raw):
                target_id = label_to_id.get(label)
                if target_id and obj.parent_id:
                    graph.add_relation(
                        source_id=target_id,
                        target_id=obj.parent_id,
                        relation_type="used_in_proof",
                    )

        # 2. References inside theorem-like statements -> 'uses'
        for obj in graph.objects.values():
            if not isinstance(obj, TheoremLike):
                continue
            raw = getattr(obj, "raw_latex", "") or ""
            for label in ref_pattern.findall(raw):
                target_id = label_to_id.get(label)
                if target_id:
                    graph.add_relation(
                        source_id=target_id,
                        target_id=obj.id,
                        relation_type="uses",
                    )

        # 3. Explicit "Definition~\ref{...}" -> uses_definition
        def_pat = re.compile(r"Definition~?\\(?:ref|eqref|autoref)\{([^}]+)\}")
        for obj in graph.objects.values():
            if isinstance(obj, Definition):
                continue
            raw = getattr(obj, "raw_latex", "") or ""
            for label in def_pat.findall(raw):
                target_id = label_to_id.get(label)
                if target_id:
                    graph.add_relation(
                        source_id=target_id,
                        target_id=obj.id,
                        relation_type="uses_definition",
                    )

        # 4. Heuristic: "special case of ..." / "generalization of ..."
        spec_pat = re.compile(
            r"special case of .*?\\(?:ref|eqref|autoref)\{([^}]+)\}",
            flags=re.IGNORECASE | re.DOTALL,
        )
        gen_pat = re.compile(
            r"generalization of .*?\\(?:ref|eqref|autoref)\{([^}]+)\}",
            flags=re.IGNORECASE | re.DOTALL,
        )

        for obj in graph.objects.values():
            raw = getattr(obj, "raw_latex", "") or ""
            for m in spec_pat.finditer(raw):
                label = m.group(1)
                target_id = label_to_id.get(label)
                if target_id:
                    graph.add_relation(
                        source_id=obj.id,
                        target_id=target_id,
                        relation_type="special_case_of",
                    )
            for m in gen_pat.finditer(raw):
                label = m.group(1)
                target_id = label_to_id.get(label)
                if target_id:
                    graph.add_relation(
                        source_id=obj.id,
                        target_id=target_id,
                        relation_type="generalization_of",
                    )

        # 5. Equations belonging to a parent object
        for obj in graph.objects.values():
            if isinstance(obj, Equation) and obj.parent_id:
                graph.add_relation(
                    source_id=obj.id,
                    target_id=obj.parent_id,
                    relation_type="in_environment_of",
                )

        # 6. Name-based heuristic for definitions: if definition.name appears in obj.raw_latex
        definition_objs = [o for o in graph.objects.values() if isinstance(o, Definition)]
        for d_obj in definition_objs:
            name = (d_obj.name or "").strip()
            if not name or len(name) > 60:
                continue
            pattern = re.escape(name)
            for other in graph.objects.values():
                if other.id == d_obj.id or isinstance(other, Definition):
                    continue
                raw = getattr(other, "raw_latex", "") or ""
                if not raw:
                    continue
                if re.search(pattern, raw):
                    graph.add_relation(
                        source_id=d_obj.id,
                        target_id=other.id,
                        relation_type="uses_definition",
                    )

    # ---------------------------------------------------------------------
    # Input resolution: local path / arXiv ID / URL
    # ---------------------------------------------------------------------


def flatten_tex_file(input_path: Path, output_path: Path, max_depth: int = 5) -> None:
    """
    Read a LaTeX file, recursively inline \input/\include, expand simple macros,
    and write the result to output_path. Keeps the full preamble+document.
    """
    parser = PaperParser(paper_id=output_path.stem)
    text = input_path.read_text(encoding="utf-8", errors="ignore")
    flat = parser._expand_inputs(text, base_dir=input_path.parent, max_depth=max_depth)
    output_path.write_text(flat, encoding="utf-8")


def resolve_source_to_tex(source: str):
    """
    Very thin wrapper for CLI usage only.
    If source is a local .tex file, use it.
    Otherwise treat as arXiv ID and defer to resolve_source_to_tex_local_first().
    """
    p = Path(source)
    if p.exists() and p.is_file():
        return p, p.stem

    base_id = normalize_arxiv_id(source)
    md = fetch_arxiv_metadata([base_id + "v1"])[base_id + "v1"]

    return resolve_source_to_tex_local_first(
        base_id=base_id,
        meta=md,
        full_papers_dir=Path(FULL_PAPERS_DIR),
        verbose=False,
    )


# ---------------------------------------------------------------------
# Network drawing
# ---------------------------------------------------------------------


def paper_to_network(
    paper: Union[PaperGraph, str, Path],
    out_png: str,
    node_label_attr: str = "id",
    include_kinds: Optional[List[str]] = None,
    include_relation_types: Optional[List[str]] = None,
    figsize: Tuple[int, int] = (12, 8),
) -> nx.DiGraph:
    """
    Build and draw a network of math objects in a paper.
    """
    if isinstance(paper, PaperGraph):
        graph = paper
    else:
        p = Path(paper)
        data = json.loads(p.read_text(encoding="utf-8"))
        graph = PaperGraph.from_dict(data)

    G = nx.DiGraph()

    for obj_id, obj in graph.objects.items():
        if include_kinds is not None and obj.kind not in include_kinds:
            continue
        G.add_node(
            obj_id,
            kind=obj.kind,
            label=getattr(obj, "label", None),
            name=getattr(obj, "name", None),
        )

    for rel in graph.relations:
        if include_relation_types is not None and rel.relation_type not in include_relation_types:
            continue
        if rel.source_id in G.nodes and rel.target_id in G.nodes:
            G.add_edge(rel.source_id, rel.target_id, relation=rel.relation_type)

    if len(G.nodes) == 0:
        print("[WARN] paper_to_network: graph has no nodes, nothing to draw.")
        return G

    node_labels: Dict[str, str] = {}
    for node in G.nodes:
        obj = graph.objects[node]
        if node_label_attr == "label" and getattr(obj, "label", None):
            node_labels[node] = obj.label
        elif node_label_attr == "name" and getattr(obj, "name", None):
            node_labels[node] = obj.name
        else:
            node_labels[node] = obj.id

    equation_nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == "equation"]
    proof_nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == "proof"]

    isolated_equations = [n for n in equation_nodes if G.degree(n) == 0]
    eq_connected = [n for n in equation_nodes if n not in isolated_equations]

    statement_kinds = {
        "theorem",
        "lemma",
        "proposition",
        "corollary",
        "claim",
        "conjecture",
        "problem",
    }
    orphan_proofs: List[str] = []
    for p in proof_nodes:
        neighbors = set(G.predecessors(p)) | set(G.successors(p))
        if not any(G.nodes[n].get("kind") in statement_kinds for n in neighbors):
            orphan_proofs.append(p)

    nodes_for_spring = [
        n for n in G.nodes if n not in isolated_equations and n not in orphan_proofs
    ]

    pos: Dict[str, Tuple[float, float]] = {}

    if nodes_for_spring:
        H = G.subgraph(nodes_for_spring).copy()
        pos_main = nx.spring_layout(H, seed=42)

        xs = [xy[0] for xy in pos_main.values()]
        ys = [xy[1] for xy in pos_main.values()]
        max_abs = max(
            max((abs(x) for x in xs), default=1.0),
            max((abs(y) for y in ys), default=1.0),
        )
        scale = 1.5 / max_abs
        for n, (x, y) in pos_main.items():
            pos[n] = (x * scale, y * scale)

    if orphan_proofs:
        m = max(len(orphan_proofs) - 1, 1)
        for i, n in enumerate(sorted(orphan_proofs)):
            y = 1.5 - 3.0 * i / m
            pos[n] = (-3.0, y)

    if isolated_equations:
        m = max(len(isolated_equations) - 1, 1)
        for i, n in enumerate(sorted(isolated_equations)):
            y = 1.5 - 3.0 * i / m
            pos[n] = (3.0, y)

    if not pos:
        if len(G.nodes) == 1:
            only = next(iter(G.nodes))
            pos[only] = (0.0, 0.0)
        else:
            pos_tmp = nx.spring_layout(G, seed=42)
            for n, (x, y) in pos_tmp.items():
                pos[n] = (x, y)

    kind_color_map = {
        "theorem": "red",
        "lemma": "orange",
        "proposition": "darkred",
        "corollary": "salmon",
        "claim": "pink",
        "definition": "green",
        "problem": "darkblue",
        "conjecture": "magenta",
        "proof": "purple",
        "algorithm": "grey",
        "table": "saddlebrown",
        "equation": "royalblue",
    }

    node_colors: List[str] = []
    node_sizes: List[float] = []

    for node, data in G.nodes(data=True):
        kind = data.get("kind")
        color = kind_color_map.get(kind, "lightgrey")
        node_colors.append(color)
        if kind == "equation":
            node_sizes.append(200.0)
        else:
            node_sizes.append(800.0)

    plt.figure(figsize=figsize)

    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=node_colors,
        node_size=node_sizes,
    )

    nx.draw_networkx_edges(
        G,
        pos,
        arrows=True,
        arrowstyle="->",
        arrowsize=15,
        connectionstyle="arc3,rad=0.1",
    )

    nx.draw_networkx_labels(
        G,
        pos,
        labels=node_labels,
        font_size=8,
    )

    plt.axis("off")

    used_kinds = sorted({data.get("kind") for _, data in G.nodes(data=True)})
    legend_handles = []
    for k in used_kinds:
        color = kind_color_map.get(k, "lightgrey")
        label = k
        legend_handles.append(mpatches.Patch(color=color, label=label))
    if legend_handles:
        plt.legend(
            handles=legend_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.05),
            ncol=min(len(legend_handles), 4),
            frameon=False,
        )

    plt.tight_layout()
    plt.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"[INFO] Saved paper graph visualization to {out_png}")
    return G


def paper_to_interactive_html(paper: Dict[str, Any], out_html: str) -> None:
    net = Network(height="800px", width="100%", directed=True)
    objects = paper["objects"]
    relations = paper["relations"]

    for oid, obj in objects.items():
        kind = obj.get("kind", "unknown")
        short = obj.get("label") or oid
        if isinstance(short, str) and len(short) > 40:
            short = short[:37] + "..."

        title = obj.get("clean_text") or obj.get("raw_latex") or ""
        net.add_node(
            oid,
            label=short,
            title=title,
            group=kind,
        )

    for rel in relations:
        src = rel["source"]
        tgt = rel["target"]
        if src in objects and tgt in objects:
            net.add_edge(src, tgt, title=rel.get("relation_type"))

    net.show(out_html)


# ---------------------------------------------------------------------
# Command-line usage
# ---------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Parse a LaTeX file / arXiv paper and extract math objects + relations."
    )
    parser.add_argument(
        "source",
        type=str,
        help="Path to .tex file OR arXiv id (e.g. 2101.12345) OR arXiv URL",
    )
    parser.add_argument(
        "--paper-id",
        type=str,
        default=None,
        help="Optional paper id override (otherwise derived from path or arXiv id).",
    )
    parser.add_argument(
        "--out-json",
        type=str,
        default=None,
        help="If provided, save structured output (PaperGraph) to this JSON file.",
    )
    args = parser.parse_args()

    tex_path, inferred_id = resolve_source_to_tex(args.source)
    paper_id = args.paper_id or inferred_id

    pp = PaperParser(paper_id=paper_id)
    graph = pp.parse_file(tex_path)

    print(f"Parsed paper_id={graph.paper_id} from {tex_path}")
    kinds_count: Dict[str, int] = {}
    for obj in graph.objects.values():
        kinds_count[obj.kind] = kinds_count.get(obj.kind, 0) + 1

    print("Object counts by kind:")
    for kind, cnt in sorted(kinds_count.items()):
        print(f"  {kind:12s}: {cnt}")

    print("\nSample theorem/lemma (if any):")
    for obj in graph.objects.values():
        if isinstance(obj, TheoremLike):
            print(f"- {obj.id} [{obj.kind}] label={obj.label} name={obj.name}")
            print(f"  assumptions: {obj.assumptions[:200]}...")
            print(f"  statement  : {obj.statement[:200]}...\n")
            break

    print("Relations (first 20):")
    for src, tgt, rtype in graph.as_edge_list()[:20]:
        print(f"  {src} --{rtype}--> {tgt}")

    if args.out_json:
        out_path = Path(args.out_json)
        out_path.write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")
        print(f"\n[INFO] Saved structured output to {out_path}")

    try:
        out_png = f"{paper_id}_graph.png"
        paper_to_network(
            paper=graph,
            out_png=out_png,
            node_label_attr="id",
            include_kinds=[
                "theorem",
                "lemma",
                "proposition",
                "corollary",
                "claim",
                "conjecture",
                "problem",
                "definition",
                "proof",
                "equation",
            ],
            include_relation_types=None,
        )
    except Exception as e:
        print(f"[WARN] Could not draw network: {e}")


if __name__ == "__main__":
    main()
