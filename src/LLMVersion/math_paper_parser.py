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

import importlib.util
import os
import re
import argparse
import requests
import json
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

# NOTE: The OpenAI package is imported lazily inside _get_llm_client() below,
# so that manual-mode extraction works on machines without the openai package.
# Same pattern as the anthropic import.

# NOTE: dataclasses are now in math_classes.py
from math_classes import (
    MathObject,
    Equation,
    TheoremLike,
    Problem,
    Conjecture,
    Definition,
    Proof,
    Algorithm,
    TableObject,
    Relation,
    PaperGraph,
)

try:
    from pyvis.network import Network
except Exception as e:
    print(f"[WARN] Could not load pyvis for interactive network html plot: {e}")

import requests  # pip install requests

from extract_arxiv_funcs import (
    normalize_arxiv_id,
    fetch_arxiv_metadata,
    resolve_source_to_tex_local_first,
)

from config import FULL_PAPERS_DIR


# ---------------------------------------------------------------------
# Structure type configuration for LLM extraction
# ---------------------------------------------------------------------

STRUCTURE_TYPE_CONFIG = {
    "definition": {
        "description": "mathematical definitions",
        "forms": [
            r"\begin{definition}...\end{definition}",
            '"Definition 2.1. ..."',
            '"We define X as/to be ...", "X is defined as ...", "Let X be ..."',
            "Implicit definitions with new notation",
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label"],
        "dataclass": "Definition",
        "id_prefix": "D",
    },
    "theorem": {
        "description": "mathematical theorems",
        "forms": [
            r"\begin{theorem}...\end{theorem}",
            '"Theorem 2.1. ..."',
            "Formally stated theorems with assumptions and conclusions",
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label", "assumptions", "statement"],
        "dataclass": "TheoremLike",
        "id_prefix": "T",
    },
    "lemma": {
        "description": "mathematical lemmas",
        "forms": [
            r"\begin{lemma}...\end{lemma}",
            '"Lemma 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label", "assumptions", "statement"],
        "dataclass": "TheoremLike",
        "id_prefix": "L",
    },
    "proposition": {
        "description": "mathematical propositions",
        "forms": [
            r"\begin{proposition}...\end{proposition}",
            '"Proposition 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label", "assumptions", "statement"],
        "dataclass": "TheoremLike",
        "id_prefix": "P",
    },
    "corollary": {
        "description": "mathematical corollaries",
        "forms": [
            r"\begin{corollary}...\end{corollary}",
            '"Corollary 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label", "assumptions", "statement"],
        "dataclass": "TheoremLike",
        "id_prefix": "C",
    },
    "claim": {
        "description": "mathematical claims",
        "forms": [
            r"\begin{claim}...\end{claim}",
            '"Claim 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label", "assumptions", "statement"],
        "dataclass": "TheoremLike",
        "id_prefix": "Cl",
    },
    "conjecture": {
        "description": "mathematical conjectures",
        "forms": [
            r"\begin{conjecture}...\end{conjecture}",
            '"Conjecture 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label", "assumptions", "statement"],
        "dataclass": "Conjecture",
        "id_prefix": "Cj",
    },
    "problem": {
        "description": "mathematical problems",
        "forms": [
            r"\begin{problem}...\end{problem}",
            '"Problem 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label", "assumptions", "statement"],
        "dataclass": "Problem",
        "id_prefix": "Pr",
    },
    "proof": {
        "description": "mathematical proofs",
        "forms": [
            r"\begin{proof}...\end{proof}",
            '"Proof. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label"],
        "dataclass": "Proof",
        "id_prefix": "R",
    },
    "algorithm": {
        "description": "algorithms and pseudocode",
        "forms": [
            r"\begin{algorithm}...\end{algorithm}",
            r"\begin{algorithmic}...\end{algorithmic}",
            "Pseudocode blocks with Input/Output and numbered steps",
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label"],
        "dataclass": "Algorithm",
        "id_prefix": "A",
    },
    "table": {
        "description": "tables",
        "forms": [
            r"\begin{table}...\end{table}",
            r"\begin{tabular}...\end{tabular}",
            r"\begin{longtable}...\end{longtable}",
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label"],
        "dataclass": "TableObject",
        "id_prefix": "Tb",
    },
    "example": {
        "description": "worked examples illustrating a concept",
        "forms": [
            r"\begin{example}...\end{example}",
            '"Example 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label"],
        "dataclass": "Definition",
        "id_prefix": "Ex",
    },
    "exercise": {
        "description": "pedagogical exercises for the reader",
        "forms": [
            r"\begin{exercise}...\end{exercise}",
            '"Exercise 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label"],
        "dataclass": "Definition",
        "id_prefix": "Xr",
    },
    "remark": {
        "description": "author remarks and observations",
        "forms": [
            r"\begin{remark}...\end{remark}",
            '"Remark 2.1. ..."',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label"],
        "dataclass": "Definition",
        "id_prefix": "Rm",
    },
    "open_problem": {
        "description": "open (unsolved) mathematical questions",
        "forms": [
            r"\begin{openproblem}...\end{openproblem}",
            r"\begin{openquestion}...\end{openquestion}",
            '"Open Problem:", "Open Question:" headings',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label", "assumptions", "statement"],
        "dataclass": "TheoremLike",
        "id_prefix": "OP",
    },
    "assumption": {
        "description": "standing assumption blocks",
        "forms": [
            r"\begin{assumption}...\end{assumption}",
            r"\begin{assumptions}...\end{assumptions}",
            '"Assumption (A1). ..." numbered assumption blocks',
        ],
        "json_fields": ["name", "raw_latex", "clean_text", "label"],
        "dataclass": "Definition",
        "id_prefix": "As",
    },
}


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

        "openproblem": "open_problem",
        "openProblem": "open_problem",
        "openquestion": "open_problem",
        "open": "open_problem",

        "assumption": "assumption",
        "Assumption": "assumption",
        "assumptions": "assumption",
        "Assumptions": "assumption",

        "example": "example",
        "Example": "example",
        "exam": "example",
        "ex": "example",

        "exercise": "exercise",
        "Exercise": "exercise",

        "remark": "remark",
        "Remark": "remark",
        "rem": "remark",
        "note": "remark",
    }

    THEOREM_LIKE_KINDS = {
        "theorem",
        "lemma",
        "proposition",
        "corollary",
        "claim",
        "conjecture",
        "problem",
        "open_problem",
    }

    def __init__(
            self,
            paper_id: Optional[str] = None,
            extraction_mode: str = "both",  # 'rules', 'llm', or 'both'
            llm_model: str = "gpt-4o-mini",
            llm_chunk_chars: int = 30000,
            llm_provider: str = "openai",
            extract_inline_let: bool = False,
            custom_prompt_file: Optional[str] = None,
            structure_types: Optional[List[str]] = None,
    ):
        """
        Parameters
        ----------
        paper_id : Optional[str]
            Identifier for this paper.
        extraction_mode : {'rules', 'llm', 'both'}
            - 'manual': only use rule-based extraction.
            - 'llm'   : only use LLM-based extraction.
            - 'both'  : use both and merge (default).
        llm_model : str
            Model name for LLM extraction (if used).
        llm_chunk_chars : int
            Max characters per chunk when calling the LLM.
        structure_types : List[str], optional
            Which structure types to extract via LLM (default: ["definition"]).
        """
        self.paper_id = paper_id or "paper"
        # Accept legacy 'manual' as an alias for 'rules' so older callers
        # don't silently no-op. New code should always pass 'rules'.
        if extraction_mode == "manual":
            extraction_mode = "rules"
        self.extraction_mode = extraction_mode
        self.llm_model = llm_model
        self.llm_chunk_chars = llm_chunk_chars
        self.llm_provider = llm_provider
        self.extract_inline_let = extract_inline_let
        self.custom_prompt_file = custom_prompt_file
        self.structure_types = structure_types or ["definition"]

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
            name = m.group(1)  # e.g. 'be'
            body = m.group(2)  # e.g. '\begin{equation}'
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

        # 2) top-level (orphan) equations in the full text, with no parent
        contained_latex = {eq.raw_latex for eq in all_eqs}
        top_eqs = self._extract_equations_from_body(full_text, parent_id=None)
        for eq in top_eqs:
            if eq.raw_latex in contained_latex:
                continue
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

        # ---- Theorem-like objects (manual, always runs) ----
        theorem_like: List[TheoremLike] = self._extract_theorem_like(text)

        # ---- Definitions: manual extraction ----
        manual_defs: List[Definition] = []
        if self.extraction_mode in ("rules", "both"):
            manual_defs = self._extract_definitions_manual(text)

        # ---- LLM extraction for each requested structure type ----
        definitions: List[Definition] = manual_defs
        llm_extracted: Dict[str, List[MathObject]] = {}

        if self.extraction_mode in ("llm", "both"):
            for stype in self.structure_types:
                try:
                    llm_objs = self._extract_objects_llm(
                        text,
                        structure_type=stype,
                        chunk_chars=self.llm_chunk_chars,
                        model=self.llm_model,
                    )
                    llm_extracted[stype] = llm_objs
                except Exception as e:  # noqa: BLE001
                    print(
                        f"[WARN] parse_file: LLM {stype} extraction failed with error {e}; "
                        "continuing without LLM results for this type."
                    )
                    llm_extracted[stype] = []

            # Merge definitions
            if "definition" in self.structure_types:
                llm_defs = llm_extracted.get("definition", [])
                if self.extraction_mode == "llm":
                    definitions = llm_defs
                else:  # 'both'
                    definitions = self._merge_definitions(manual_defs, llm_defs)

            # Merge/replace theorem-like types
            for stype in self.structure_types:
                if stype == "definition" or stype not in self.THEOREM_LIKE_KINDS:
                    continue
                llm_objs = llm_extracted.get(stype, [])
                if self.extraction_mode == "llm":
                    # Pure LLM: replace regex results entirely
                    theorem_like = [t for t in theorem_like if t.kind != stype] + llm_objs
                elif llm_objs:
                    manual_of_kind = [t for t in theorem_like if t.kind == stype]
                    merged = self._merge_objects(manual_of_kind, llm_objs)
                    theorem_like = [t for t in theorem_like if t.kind != stype] + merged

        proofs = self._extract_proofs(text)
        algorithms = self._extract_algorithms(text)
        tables = self._extract_tables(text)
        assumptions = self._extract_assumptions(text)
        examples = self._extract_examples(text)
        exercises = self._extract_exercises(text)
        remarks = self._extract_remarks(text)

        # Merge/replace proof, algorithm, table, assumption when LLM was used
        if self.extraction_mode in ("llm", "both"):
            for stype, regex_var in [("proof", proofs), ("algorithm", algorithms), ("table", tables)]:
                if stype not in self.structure_types:
                    continue
                llm_objs = llm_extracted.get(stype, [])
                if self.extraction_mode == "llm":
                    # Pure LLM: replace regex results entirely
                    if stype == "proof":
                        proofs = llm_objs
                    elif stype == "algorithm":
                        algorithms = llm_objs
                    elif stype == "table":
                        tables = llm_objs
                elif llm_objs:
                    if stype == "proof":
                        proofs = self._merge_objects(proofs, llm_objs)
                    elif stype == "algorithm":
                        algorithms = self._merge_objects(algorithms, llm_objs)
                    elif stype == "table":
                        tables = self._merge_objects(tables, llm_objs)

            # Merge/replace simple env types when LLM was used
            for stype, regex_list in [("assumption", assumptions), ("example", examples),
                                       ("exercise", exercises), ("remark", remarks)]:
                if stype not in self.structure_types:
                    continue
                llm_objs = llm_extracted.get(stype, [])
                if self.extraction_mode == "llm":
                    if stype == "assumption":
                        assumptions = llm_objs
                    elif stype == "example":
                        examples = llm_objs
                    elif stype == "exercise":
                        exercises = llm_objs
                    elif stype == "remark":
                        remarks = llm_objs
                elif llm_objs:
                    if stype == "assumption":
                        assumptions = self._merge_objects(assumptions, llm_objs)
                    elif stype == "example":
                        examples = self._merge_objects(examples, llm_objs)
                    elif stype == "exercise":
                        exercises = self._merge_objects(exercises, llm_objs)
                    elif stype == "remark":
                        remarks = self._merge_objects(remarks, llm_objs)

        # ---- Distilled rules (NtRED): auto-loaded from {type}_eval/distilled_rules.py ----
        if self.extraction_mode in ("rules", "both"):
            # Definitions
            distilled_defs = self._apply_distilled_rules(text, "definition")
            if distilled_defs:
                definitions = self._merge_objects(definitions, distilled_defs)

            # Theorem-like types
            for stype in self.THEOREM_LIKE_KINDS:
                distilled = self._apply_distilled_rules(text, stype)
                if distilled:
                    manual_of_kind = [t for t in theorem_like if t.kind == stype]
                    merged = self._merge_objects(manual_of_kind, distilled)
                    theorem_like = [t for t in theorem_like if t.kind != stype] + merged

            # Proofs, algorithms, tables
            distilled_proofs = self._apply_distilled_rules(text, "proof")
            if distilled_proofs:
                proofs = self._merge_objects(proofs, distilled_proofs)
            distilled_algos = self._apply_distilled_rules(text, "algorithm")
            if distilled_algos:
                algorithms = self._merge_objects(algorithms, distilled_algos)
            distilled_tables = self._apply_distilled_rules(text, "table")
            if distilled_tables:
                tables = self._merge_objects(tables, distilled_tables)

        # equations inside theorem/definition/proof/algorithm/example/remark bodies
        containers: List[MathObject] = theorem_like + definitions + proofs + algorithms + examples + remarks
        equations = self._extract_equations(text, containers)

        # Register all objects in the PaperGraph, sorted by source position
        # so that graph.objects preserves document order (needed for proof linking).
        all_objects = theorem_like + definitions + proofs + algorithms + tables + assumptions + examples + exercises + remarks + equations
        all_objects.sort(key=lambda o: getattr(o, '_source_pos', float('inf')))
        for obj in all_objects:
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
        # Start from BASE_ENV_KIND_MAP (which has all aliases like defn, dfn, lem, etc.)
        self.env_kind_map = dict(self.BASE_ENV_KIND_MAP)

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
                "exercise",
                "claim",
                "conclusion",
                "problem",
                "conjecture",
                "assumption",
            ]:
                if candidate in printed_clean:
                    kind = candidate
                    break

            if kind:
                self.env_kind_map[env_name] = kind

    @staticmethod
    def _clean_latex_to_text(latex: str) -> str:
        """Best-effort LaTeX -> plain text cleaner (preserves math content)."""
        from latex_clean import clean_latex_to_text
        return clean_latex_to_text(latex)

    @staticmethod
    def _extract_label_and_name(env_body: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract \\label{...} from environment body."""
        label_match = re.search(r"\\label{([^}]*)}", env_body)
        label = label_match.group(1).strip() if label_match else None
        return label, None

    # ------------------------------------------------------------------
    # Generic environment extraction
    # ------------------------------------------------------------------

    def _extract_envs(self, text: str, env_names: List[str]) -> List[Tuple[str, str, str, int]]:
        """
        Generic environment extractor.

        Returns list of (env_name, opt_name, body, source_pos) where:
          \begin{env_name}[opt_name] body \end{env_name}
        source_pos is the character offset of \begin in *text*.
        """
        env_pattern = (
                r"\\begin{(" + "|".join(map(re.escape, env_names)) + r")}"
                                                                     r"(?:\[(?P<opt>[^\]]*)])?"
                                                                     r"(?P<body>.*?)"
                                                                     r"\\end{\1}"
        )
        regex = re.compile(env_pattern, flags=re.DOTALL | re.IGNORECASE)
        results = []
        for m in regex.finditer(text):
            env = m.group(1)
            opt = m.group("opt")
            body = m.group("body")
            results.append((env, opt, body, m.start()))
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

        for env_name, opt_name, body, source_pos in found:
            kind = self.env_kind_map.get(env_name, "theorem")
            counters.setdefault(kind, 0)
            counters[kind] += 1
            idx = counters[kind]

            # Use STRUCTURE_TYPE_CONFIG prefix if available, else first letter
            config = STRUCTURE_TYPE_CONFIG.get(kind)
            prefix = config["id_prefix"] if config else kind[0].upper()
            obj_id = prefix + str(idx)

            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)
            assumptions, conclusions = self._split_assumptions_conclusions(clean_text)

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
                    conclusions=conclusions,
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
                    conclusions=conclusions,
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
                    conclusions=conclusions,
                )

            obj._source_pos = source_pos
            objects.append(obj)

        return objects

    @staticmethod
    def _split_assumptions_conclusions(text: str) -> Tuple[List[str], List[str]]:
        """
        Split theorem-like text into assumption and conclusion sentences.

        Strategy:
        - Sentences starting with assumption keywords (let/suppose/assume/given)
          are assumptions, but ONLY while we haven't seen a conclusion yet.
        - Explicit conclusion keywords (then/hence/therefore/thus/so/it follows)
          flip to conclusion mode.
        - Intra-sentence "if <A>, then <B>" is split into assumption + conclusion.
        - "For any/all/every/each <A>, <B>" quantifier phrases are split.
        - Default is CONCLUSION (not assumption) — most theorem text is the claim.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        assumptions_sentences = []
        conclusions_sentences = []

        # Patterns for assumption-start keywords
        _ASSUMPTION_START = re.compile(
            r"^(let|suppose|assume|given|denote)\b", re.IGNORECASE
        )
        # Patterns for explicit conclusion-start keywords
        _CONCLUSION_START = re.compile(
            r"^(then|hence|therefore|thus|so|it follows|we have|we get|we obtain|we conclude)\b",
            re.IGNORECASE,
        )
        # Intra-sentence: "if <A>, then <B>" or "if <A> then <B>"
        _IF_THEN = re.compile(
            r"^if\s+(.+?),?\s+then\s+(.+)$", re.IGNORECASE | re.DOTALL
        )
        # "For any/all/every/each <A>, <B>" — quantifier introduces assumption
        _QUANTIFIER = re.compile(
            r"^for\s+(?:any|all|every|each)\s+(.+?),\s+(.+)$",
            re.IGNORECASE | re.DOTALL,
        )
        # "Whenever/provided/when <A>, <B>"
        _WHENEVER = re.compile(
            r"^(?:whenever|provided|when)\s+(.+?),\s+(.+)$",
            re.IGNORECASE | re.DOTALL,
        )

        in_assumptions = True

        for s in sentences:
            s_strip = s.strip()
            if not s_strip:
                continue
            lower = s_strip.lower()

            # --- Intra-sentence splits (highest priority) ---
            m = _IF_THEN.match(s_strip)
            if m:
                assumptions_sentences.append("If " + m.group(1).strip())
                conclusions_sentences.append("then " + m.group(2).strip())
                in_assumptions = False
                continue

            m = _QUANTIFIER.match(s_strip)
            if m:
                assumptions_sentences.append(s_strip[:s_strip.index(",")].strip())
                conclusions_sentences.append(m.group(2).strip())
                in_assumptions = False
                continue

            m = _WHENEVER.match(s_strip)
            if m:
                assumptions_sentences.append(m.group(1).strip())
                conclusions_sentences.append(m.group(2).strip())
                in_assumptions = False
                continue

            # --- Sentence-level classification ---
            if _ASSUMPTION_START.match(lower):
                assumptions_sentences.append(s_strip)
                continue

            if _CONCLUSION_START.match(lower):
                in_assumptions = False
                conclusions_sentences.append(s_strip)
                continue

            # Default: conclusion (unless we're in an assumption preamble that
            # started with Let/Suppose and hasn't been broken yet)
            if in_assumptions and assumptions_sentences and _ASSUMPTION_START.match(assumptions_sentences[-1].lower()):
                assumptions_sentences.append(s_strip)
            else:
                in_assumptions = False
                conclusions_sentences.append(s_strip)

        return assumptions_sentences, conclusions_sentences

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
            for env_name, opt_name, body, source_pos in env_defs:
                idx += 1
                obj_id = f"D{idx}"
                label, _ = self._extract_label_and_name(body)
                clean_text = self._clean_latex_to_text(body)
                d = Definition(
                    id=obj_id,
                    kind="definition",
                    index=idx,
                    label=label,
                    name=opt_name.strip() if opt_name else None,
                    raw_latex=body,
                    clean_text=clean_text,
                    env_name=env_name,
                )
                d._source_pos = source_pos
                objects.append(d)

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
            d = Definition(
                id=obj_id,
                kind="definition",
                index=idx,
                label=None,
                name=name,
                raw_latex=body,
                clean_text=clean_text,
                env_name="textual",
            )
            d._source_pos = m.start()
            objects.append(d)

        # --- C. Inline textual definitions -------------------------------

        # Mask out text inside definition environments (Parts A & B)
        # so inline patterns don't re-match and truncate inside them.
        inline_text = text
        for obj in objects:
            raw = obj.raw_latex
            if raw:
                inline_text = inline_text.replace(raw, " " * len(raw), 1)

        # (Fix-a) Also mask out theorem-like and proof environments.
        # C1/C4 patterns ("we define...", "let X be...") inside these
        # are setup text, not standalone definitions.
        _mask_env_kinds = {"theorem", "lemma", "proposition", "corollary",
                           "claim", "conjecture", "problem", "proof"}
        _mask_env_names = [env for env, kind in self.env_kind_map.items()
                           if kind in _mask_env_kinds]
        if _mask_env_names:
            for _, _, body, _ in self._extract_envs(text, _mask_env_names):
                if body:
                    inline_text = inline_text.replace(body, " " * len(body), 1)

        # C1: "We (also) define X as/by/to be ..." (case insensitive)
        inline_define_pattern = re.compile(
            r"(?P<full>"
            r"(?:We\s+)?(?:also\s+)?define\s+"
            r"(?P<name>[^.]{1,80}?)"
            r"\s*(?:as|by|to\s+be|:=|=)"
            r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
            flags=re.IGNORECASE | re.DOTALL,
        )

        # C2: "X is defined as/to be ..." (case insensitive)
        # Two-phase approach to avoid catastrophic backtracking:
        # 1. Find the fixed anchor "is defined as/to be"
        # 2. Look back (up to 80 chars to previous sentence boundary) for name
        # 3. Look forward for the rest of the sentence
        _c2_anchor = re.compile(
            r"\bis\s+defined\s+(?:as|to\s+be)\s",
            flags=re.IGNORECASE,
        )
        _c2_tail = re.compile(
            r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.",
            flags=re.DOTALL,
        )

        # C3: "We say/call X is/to be ..." - explicit definitional language
        inline_we_say_pattern = re.compile(
            r"(?P<full>"
            r"(?:We\s+)?(?:say|call)\s+(?:that\s+)?"
            r"(?P<name>[^.]{1,60}?)"
            r"\s+(?:is|to\s+be|are)\s+"
            r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
            flags=re.IGNORECASE | re.DOTALL,
        )

        # C4: "Let X be ..." - only when it's a real definition (contains definitional keywords)
        # Filter out simple variable intros like "Let m,n be integers"
        inline_let_pattern = re.compile(
            r"(?P<full>"
            r"(?:Let|let)\s+"
            r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_]+))"
            r"[^.]{0,200}?"
            r"\s+be\s+(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.)",
            flags=re.DOTALL,
        )

        # Keywords that indicate a real definition vs just variable introduction
        definition_keywords = re.compile(
            r"\b(set|function|map|mapping|sequence|matrix|space|operator|"
            r"define|denote|notation|collection|family|class|group|ring|field|"
            r"graph|path|tree|partition|permutation|morphism|homomorphism)\b",
            flags=re.IGNORECASE
        )

        # (Fix-c) Negative patterns for C1 ("define"): phrases that look
        # like "define X as" but are NOT definitions.
        _c1_negative = re.compile(
            r"\b(in\s+terms\s+of|as\s+we\s+did\s+in|as\s+in\s+(?:Section|"
            r"Theorem|Lemma|Equation|Proposition|Definition|the\s+previous)|"
            r"as\s+(?:before|above|below|follows)|defined\s+(?:above|below|"
            r"earlier|previously|in\s+Section|in\s+Theorem|in\s+Lemma|"
            r"in\s+Equation|in\s+Definition))\b",
            flags=re.IGNORECASE,
        )

        # (Fix-d) Referential language: the sentence points elsewhere
        # in the document, so it is not itself a definition.
        _referential = re.compile(
            r"\b(?:defined?\s+)?(?:below|above|right|left|"
            r"in\s+the\s+(?:next|previous|following|preceding)\s+"
            r"(?:section|chapter|subsection|paragraph))\b",
            flags=re.IGNORECASE,
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
            d = Definition(
                id=obj_id,
                kind="definition",
                index=idx,
                label=None,
                name=name_hint or None,
                raw_latex=full,
                clean_text=clean_text,
                env_name=source,
            )
            d._source_pos = match.start()
            objects.append(d)

        for m in inline_define_pattern.finditer(inline_text):
            full_text = m.group("full")
            # (Fix-c) Skip if negative pattern matches
            if _c1_negative.search(full_text):
                continue
            # (Fix-d) Skip referential language
            if _referential.search(full_text):
                continue
            add_inline_definition(m, "inline_define")

        for anchor_m in _c2_anchor.finditer(inline_text):
            # Look back from anchor for sentence boundary (period or start)
            start_search = max(0, anchor_m.start() - 80)
            prefix = inline_text[start_search:anchor_m.start()]
            dot_pos = prefix.rfind(".")
            if dot_pos >= 0:
                name_start = start_search + dot_pos + 1
            else:
                name_start = start_search
            name_text = inline_text[name_start:anchor_m.start()].strip()
            if not name_text or len(name_text) > 80:
                continue
            # Match tail after anchor
            tail_m = _c2_tail.match(inline_text, anchor_m.end())
            if not tail_m:
                continue
            full_text = inline_text[name_start:tail_m.end()]
            # Build a fake match-like object for add_inline_definition
            _ns = name_start  # capture for closure
            class _C2Match:
                def group(self, key):
                    if key == "full":
                        return full_text
                    if key == "name":
                        return name_text
                    return None
                def start(self):
                    return _ns
            add_inline_definition(_C2Match(), "inline_defined_as")

        # C3: "We say/call X is..." - explicit definitional language
        for m in inline_we_say_pattern.finditer(inline_text):
            add_inline_definition(m, "inline_we_say")

        # C4: "Let X be ..." - only when it contains definitional keywords
        # This filters out simple variable intros like "Let m,n be integers"
        for m in inline_let_pattern.finditer(inline_text):
            full_text = m.group("full")
            # Only treat as definition if it contains definitional keywords
            if not definition_keywords.search(full_text):
                continue
            # (Fix-d) Skip referential language
            if _referential.search(full_text):
                continue
            add_inline_definition(m, "inline_let")

        # --- (Fix-b) Priority-based dedup --------------------------------
        # Priority: A (environment) > B (textual) > C2/C3 > C1/C4
        # If two rules capture overlapping text, keep the higher-priority one.
        _source_priority = {
            "textual": 1,             # B
            "inline_defined_as": 2,   # C2
            "inline_we_say": 2,       # C3
            "inline_define": 3,       # C1
            "inline_let": 3,          # C4
        }

        def _priority(obj: Definition) -> int:
            # A (environment-based) has env_name like "definition", "defn", etc.
            # — anything not in _source_priority is A-type → highest priority (0)
            return _source_priority.get(obj.env_name, 0)

        # Sort by priority (lower = higher priority), then by index
        objects.sort(key=lambda o: (_priority(o), o.index))

        # Remove duplicates where clean_text overlaps significantly
        deduped: List[Definition] = []
        seen_texts: List[str] = []
        for obj in objects:
            ct = (obj.clean_text or "").strip().lower()
            if not ct:
                deduped.append(obj)
                continue
            # Check if this object's text is a substring of (or contains)
            # an already-kept higher-priority object's text
            is_dup = False
            for prev in seen_texts:
                # Either one contains the other, or they share >60% content
                if ct in prev or prev in ct:
                    is_dup = True
                    break
                # Also check if they start with the same first 60 chars
                # (handles slight wording differences from two rules)
                min_len = min(len(ct), len(prev))
                if min_len > 30 and ct[:30] == prev[:30]:
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(obj)
                seen_texts.append(ct)

        # Re-index
        for i, obj in enumerate(deduped, start=1):
            obj.id = f"D{i}"
            obj.index = i
        objects = deduped

        print(f"[INFO] _extract_definitions_manual: found {len(objects)} definitions (all kinds).")
        return objects

    # Backwards-compatible wrapper
    def _extract_definitions(self, text: str) -> List[Definition]:
        return self._extract_definitions_manual(text)

    # ------------------------------------------------------------------
    # Distilled rules (NtRED)
    # ------------------------------------------------------------------

    # Maps structure_type -> class constructor used to wrap distilled results
    _DISTILLED_TYPE_MAP = {
        'definition': 'Definition',
        'theorem': 'TheoremLike',
        'lemma': 'TheoremLike',
        'proposition': 'TheoremLike',
        'corollary': 'TheoremLike',
        'claim': 'TheoremLike',
        'conjecture': 'Conjecture',
        'problem': 'Problem',
        'proof': 'Proof',
        'algorithm': 'Algorithm',
        'table': 'TableObject',
    }

    def _apply_distilled_rules(self, text: str, structure_type: str) -> List[MathObject]:
        """Load and apply distilled rules for a structure type if available.

        Looks for {structure_type}_eval/distilled_rules.py relative to this file's
        directory. If found, imports extract_distilled_{structure_type}(text) and
        converts returned dicts to MathObject instances.
        """
        parser_dir = Path(__file__).resolve().parent
        rules_path = parser_dir / f"{structure_type}_eval" / "distilled_rules.py"

        if not rules_path.is_file():
            return []

        func_name = f"extract_distilled_{structure_type}"

        try:
            spec = importlib.util.spec_from_file_location(
                f"distilled_rules_{structure_type}", str(rules_path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            print(f"[WARN] Failed to load distilled rules from {rules_path}: {e}")
            return []

        extract_fn = getattr(mod, func_name, None)
        if extract_fn is None:
            print(f"[WARN] {rules_path} does not define {func_name}()")
            return []

        try:
            raw_results = extract_fn(text)
        except Exception as e:
            print(f"[WARN] distilled {func_name}() raised: {e}")
            return []

        if not raw_results:
            return []

        # Convert dicts to proper MathObject instances
        class_name = self._DISTILLED_TYPE_MAP.get(structure_type, 'MathObject')
        class_map = {
            'Definition': Definition,
            'TheoremLike': TheoremLike,
            'Conjecture': Conjecture,
            'Problem': Problem,
            'Proof': Proof,
            'Algorithm': Algorithm,
            'TableObject': TableObject,
            'MathObject': MathObject,
        }
        cls = class_map.get(class_name, MathObject)

        objects = []
        for i, item in enumerate(raw_results, 1):
            raw_latex = item.get('raw_latex', '')
            clean_text = item.get('clean_text', '')
            name = item.get('name')
            env_name = item.get('env_name', 'distilled')

            kwargs = dict(
                id=f"DIST_{structure_type[0].upper()}{i}",
                kind=structure_type,
                index=i,
                label=None,
                name=name,
                raw_latex=raw_latex,
                clean_text=clean_text,
            )

            # Add type-specific fields
            if cls in (Definition, TheoremLike, Conjecture, Problem, Algorithm):
                kwargs['env_name'] = env_name
            if cls == Proof:
                kwargs['parent_id'] = None

            try:
                objects.append(cls(**kwargs))
            except Exception as e:
                print(f"[WARN] Could not create {class_name} from distilled rule {i}: {e}")

        if objects:
            print(f"[INFO] Distilled rules ({structure_type}): found {len(objects)} additional items.")

        return objects

    # ------------------------------------------------------------------
    # LLM client helpers
    # ------------------------------------------------------------------

    def _create_llm_client(self, provider: str):
        """Create LLM client for the given provider. Returns (client, provider_type)."""
        if provider == "anthropic":
            try:
                import anthropic
            except ImportError:
                print("[ERROR] anthropic package not installed. Run: pip install anthropic")
                return None, None
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                print("[ERROR] ANTHROPIC_API_KEY environment variable not set.")
                return None, None
            return anthropic.Anthropic(api_key=api_key), "anthropic"

        elif provider == "openai":
            try:
                from openai import OpenAI
            except ImportError:
                print("[ERROR] openai package not installed. Run: pip install openai")
                return None, None
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("[ERROR] OPENAI_API_KEY environment variable not set.")
                return None, None
            return OpenAI(api_key=api_key), "openai_compat"

        elif provider == "huggingface":
            try:
                from openai import OpenAI
            except ImportError:
                print("[ERROR] openai package not installed (required for HF router). Run: pip install openai")
                return None, None
            api_key = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
            if not api_key:
                print("[ERROR] HF_TOKEN or HUGGINGFACE_API_KEY environment variable not set.")
                return None, None
            return OpenAI(base_url="https://router.huggingface.co/v1", api_key=api_key), "openai_compat"

        elif provider == "openrouter":
            # OpenRouter hosts Qwen, Gemini, DeepSeek, Mistral, and more behind a
            # single OpenAI-compatible endpoint. The --llm-model flag selects the
            # concrete model, e.g.:
            #   --llm-provider openrouter --llm-model qwen/qwen3.6-35b-a3b
            #   --llm-provider openrouter --llm-model google/gemini-2.5-pro
            try:
                from openai import OpenAI
            except ImportError:
                print("[ERROR] openai package not installed (required for OpenRouter). Run: pip install openai")
                return None, None
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                print("[ERROR] OPENROUTER_API_KEY environment variable not set.")
                return None, None
            return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key), "openai_compat"

        elif provider == "alibaba":
            # Direct Alibaba Cloud Bailian (DashScope) OpenAI-compatible endpoint.
            # Cheaper than OpenRouter for Qwen models but may be region-restricted.
            # Intended primarily for Qwen3.x, e.g.:
            #   --llm-provider alibaba --llm-model qwen3.6-35b-a3b
            try:
                from openai import OpenAI
            except ImportError:
                print("[ERROR] openai package not installed (required for Alibaba Bailian). Run: pip install openai")
                return None, None
            api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("ALIBABA_API_KEY")
            if not api_key:
                print("[ERROR] DASHSCOPE_API_KEY (or ALIBABA_API_KEY) environment variable not set.")
                return None, None
            base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
            return OpenAI(base_url=base_url, api_key=api_key), "openai_compat"

        elif provider == "google":
            # Native Google Generative AI SDK for Gemini. Unlike OpenRouter's
            # Gemini, this uses the free AI Studio tier when GOOGLE_API_KEY is
            # set and no billing is enabled on the project. Returns a
            # distinct provider_type so _call_llm_api can dispatch to the
            # Google-specific .generate_content() shape.
            try:
                import google.generativeai as genai
            except ImportError:
                print("[ERROR] google-generativeai package not installed. Run: pip install google-generativeai")
                return None, None
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                print("[ERROR] GOOGLE_API_KEY (or GEMINI_API_KEY) environment variable not set.")
                return None, None
            genai.configure(api_key=api_key)
            # Client is the module; _call_llm_api instantiates per-model.
            return genai, "google"

        else:
            print(f"[WARN] llm_provider='{provider}' not supported.")
            return None, None

    @staticmethod
    def _call_llm_api(client, provider_type: str, model: str, prompt: str) -> str:
        """Send prompt to LLM and return response text."""
        if provider_type == "anthropic":
            message = client.messages.create(
                model=model,
                max_tokens=16384,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        else:  # openai_compat (OpenAI + HuggingFace)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=16384,
            )
            return response.choices[0].message.content

    @staticmethod
    def _build_math_object(data: Dict[str, Any], structure_type: str, idx: int) -> MathObject:
        """Build the appropriate MathObject subclass from LLM response data."""
        config = STRUCTURE_TYPE_CONFIG.get(structure_type, STRUCTURE_TYPE_CONFIG["definition"])
        id_prefix = config["id_prefix"]
        dataclass_name = config["dataclass"]

        common = dict(
            id=f"{id_prefix}{idx}",
            kind=structure_type,
            index=idx,
            label=data.get("label"),
            name=data.get("name") or data.get("term"),
            raw_latex=data.get("raw_latex", ""),
            clean_text=data.get("clean_text") or data.get("definition", ""),
        )

        if not common["clean_text"]:
            print(f"[DEBUG] clean_text not produced for {structure_type} due to token output savings")

        if dataclass_name == "Definition":
            return Definition(**common, env_name=None)
        elif dataclass_name in ("TheoremLike", "Conjecture", "Problem"):
            # The LLM prompt currently returns "assumptions" and "statement" as
            # strings (see prompts/theorem_prompt.txt). The Python fields are now
            # List[str], so wrap any non-empty string in a single-element list.
            # Also support the case where the LLM already returns a list.
            def _to_list(x):
                if x is None or x == "":
                    return []
                if isinstance(x, list):
                    return x
                return [x]

            extra = dict(
                env_name=None,
                assumptions=_to_list(data.get("assumptions", [])),
                conclusions=_to_list(data.get("statement", data.get("conclusions", []))),
            )
            if dataclass_name == "Conjecture":
                return Conjecture(**common, **extra)
            elif dataclass_name == "Problem":
                return Problem(**common, **extra)
            else:
                return TheoremLike(**common, **extra)
        elif dataclass_name == "Proof":
            return Proof(**common)
        elif dataclass_name == "Algorithm":
            return Algorithm(**common)
        elif dataclass_name == "TableObject":
            return TableObject(**common)
        else:
            return MathObject(**common)

    # ------------------------------------------------------------------
    # Simple environment extraction (assumption, example, exercise, remark)
    # ------------------------------------------------------------------

    def _extract_simple_envs(self, text: str, target_kind: str) -> List[Definition]:
        """Extract environments of a given kind as Definition objects."""
        config = STRUCTURE_TYPE_CONFIG.get(target_kind)
        prefix = config["id_prefix"] if config else target_kind[0].upper()

        env_names = [
            env for env, kind in self.env_kind_map.items()
            if kind == target_kind
        ]
        if not env_names:
            return []

        found = self._extract_envs(text, env_names)
        objects: List[Definition] = []

        for idx, (env_name, opt_name, body, source_pos) in enumerate(found, start=1):
            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)
            obj = Definition(
                id=f"{prefix}{idx}",
                kind=target_kind,
                index=idx,
                label=label,
                name=opt_name.strip() if opt_name else None,
                raw_latex=body,
                clean_text=clean_text,
                env_name=env_name,
            )
            obj._source_pos = source_pos
            objects.append(obj)

        return objects

    def _extract_assumptions(self, text: str) -> List[Definition]:
        """Extract \\begin{assumption} blocks."""
        return self._extract_simple_envs(text, "assumption")

    def _extract_examples(self, text: str) -> List[Definition]:
        """Extract \\begin{example} blocks."""
        return self._extract_simple_envs(text, "example")

    def _extract_exercises(self, text: str) -> List[Definition]:
        """Extract \\begin{exercise} blocks."""
        return self._extract_simple_envs(text, "exercise")

    def _extract_remarks(self, text: str) -> List[Definition]:
        """Extract \\begin{remark} blocks."""
        return self._extract_simple_envs(text, "remark")

    # ------------------------------------------------------------------
    # Unified LLM-based extraction
    # ------------------------------------------------------------------

    def _extract_objects_llm(
            self,
            text: str,
            structure_type: str = "definition",
            chunk_chars: int = 30000,
            model: str = "claude-sonnet-4-6",
    ) -> List[MathObject]:
        """Unified LLM extraction for any structure type."""
        client, provider_type = self._create_llm_client(self.llm_provider)
        if client is None:
            return []

        chunks = self._chunk_text(text, chunk_chars)
        print(
            f"[INFO] _extract_objects_llm({structure_type}): "
            f"processing {len(chunks)} chunks with {model} via {self.llm_provider}"
        )

        all_objects: List[MathObject] = []
        idx = 0

        for chunk_idx, chunk in enumerate(chunks, 1):
            print(f"[INFO] Processing chunk {chunk_idx}/{len(chunks)}...")
            prompt = self._create_extraction_prompt(chunk, structure_type)

            try:
                response_text = self._call_llm_api(client, provider_type, model, prompt)
                objects_data = self._parse_llm_response(response_text)

                for obj_data in objects_data:
                    idx += 1
                    obj = self._build_math_object(obj_data, structure_type, idx)
                    all_objects.append(obj)
            except Exception as e:
                print(f"[ERROR] LLM API call failed for chunk {chunk_idx}: {e}")

        print(
            f"[INFO] _extract_objects_llm({structure_type}): "
            f"found {len(all_objects)} {structure_type}(s) total."
        )
        return all_objects

    # Backward-compatible wrapper
    def _extract_definitions_llm(
            self,
            text: str,
            llm_type: str = "anthropic",
            provider: str = "hosted",
            chunk_chars: int = 30000,
            model: str = "claude-sonnet-4-6",
    ) -> List[Definition]:
        """Extract definitions via LLM. Delegates to _extract_objects_llm."""
        objects = self._extract_objects_llm(
            text, structure_type="definition",
            chunk_chars=chunk_chars, model=model,
        )
        return [o for o in objects if isinstance(o, Definition)]

    @staticmethod
    def _chunk_text(text: str, chunk_size: int) -> List[str]:
        """Split text into chunks at paragraph boundaries."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        current_chunk = ""
        paragraphs = text.split("\n\n")

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = para
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _create_extraction_prompt(self, latex_chunk: str, structure_type: str = "definition") -> str:
        """Create a prompt for LLM to extract the given structure type."""

        # 1. Custom prompt file (user-provided, overrides everything)
        if self.custom_prompt_file and Path(self.custom_prompt_file).exists():
            template = Path(self.custom_prompt_file).read_text()
            print("Using Prompt from file:", self.custom_prompt_file)
            return template.replace("{latex_chunk}", latex_chunk)

        # 2. Per-type prompt file in prompts/ directory
        script_dir = Path(__file__).parent
        type_prompt = script_dir / "prompts" / f"{structure_type}_prompt.txt"
        if type_prompt.exists():
            template = type_prompt.read_text()
            print(f"Using Prompt from file: {type_prompt}")
            return template.replace("{latex_chunk}", latex_chunk)

        # 3. Built-in default from STRUCTURE_TYPE_CONFIG
        config = STRUCTURE_TYPE_CONFIG.get(structure_type, STRUCTURE_TYPE_CONFIG["definition"])
        forms_text = "\n".join(f"{i+1}. {form}" for i, form in enumerate(config["forms"]))
        fields_list = "\n".join(f"- {f}: ..." for f in config["json_fields"])
        json_example = ", ".join(f'"{f}": "..."' for f in config["json_fields"])

        print(f"Using Default Prompt Template for {structure_type}")
        prompt = f"""You are analyzing a mathematical paper written in LaTeX. Extract ALL {config['description']}.

{structure_type.capitalize()} forms:
{forms_text}

For each {structure_type}, extract:
{fields_list}

Return JSON array:
[
  {{{{{json_example}}}}}
]

LaTeX text:

{latex_chunk}

Respond ONLY with JSON array."""
        return prompt

    # Backward-compatible wrapper
    def _create_definition_extraction_prompt(self, latex_chunk: str) -> str:
        """Create a prompt for LLM to extract definitions."""
        return self._create_extraction_prompt(latex_chunk, structure_type="definition")

    @staticmethod
    def _parse_llm_response(response_text: str) -> List[Dict[str, Any]]:
        """Parse Claude's JSON response."""
        response_text = response_text.strip()
        # Strip markdown code fences (possibly with preamble text before them)
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        elif "```json" in response_text:
            response_text = response_text.split("```json", 1)[1]
        elif "```" in response_text and "[" in response_text:
            response_text = response_text.split("```", 1)[1]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Fallback: locate the outermost JSON array directly
        if not response_text.startswith("["):
            start = response_text.find("[")
            if start != -1:
                response_text = response_text[start:]

        try:
            definitions = json.loads(response_text)
            if not isinstance(definitions, list):
                print(f"[WARN] LLM response is not a list")
                return []
            return definitions
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON: {e}")
            print(f"[DEBUG] Response: {response_text[:500]}...")
            return []

    # ------------------------------------------------------------------
    # LLM-based definitions
    # ------------------------------------------------------------------
    # (unchanged – omitted here for brevity, but keep exactly as in your file)
    # ------------------------------------------------------------------
    # Proofs, algorithms, tables, linking, CLI, etc.
    # (all unchanged, since they already use the same class interfaces)
    # ------------------------------------------------------------------

    # ... keep the rest of the file exactly as in your original,
    #     since the interfaces of Definition / Proof / Algorithm /
    #     TheoremLike / TableObject / Equation / PaperGraph / Relation
    #     have not changed.

    def _merge_definitions(
            self,
            manual_defs: List[Definition],
            llm_defs: List[Definition],
    ) -> List[Definition]:
        """
        Merge manual and LLM-based definitions.

        Current simple policy:
          - take all manual definitions
          - add any LLM definitions whose (clean_text, name) pair is not already
            present among the manual ones.

        This avoids obvious duplicates if/when you have a real LLM extractor.
        """
        if not llm_defs:
            return manual_defs

        seen = set(
            (d.clean_text.strip().lower(), (d.name or "").strip().lower())
            for d in manual_defs
        )

        merged = list(manual_defs)
        for d in llm_defs:
            key = (d.clean_text.strip().lower(), (d.name or "").strip().lower())
            if key not in seen:
                merged.append(d)
                seen.add(key)

        return merged

    def _merge_objects(
            self,
            manual_objs: List[MathObject],
            llm_objs: List[MathObject],
    ) -> List[MathObject]:
        """Merge manual and LLM-extracted objects, avoiding duplicates.

        Dedup is based on clean_text alone — if two extractors find the same
        text but one assigns a name (e.g. from \\label) and the other doesn't,
        they are still the same structure.  When the distilled version carries
        a name that the base version lacks, backfill it.
        """
        if not llm_objs:
            return manual_objs

        seen_texts = set()
        text_to_obj = {}
        for d in manual_objs:
            txt = d.clean_text.strip().lower()
            seen_texts.add(txt)
            text_to_obj[txt] = d

        merged = list(manual_objs)
        for d in llm_objs:
            txt = d.clean_text.strip().lower()
            if txt not in seen_texts:
                merged.append(d)
                seen_texts.add(txt)
            else:
                # Backfill name if the base object lacks one
                existing = text_to_obj.get(txt)
                if existing and not existing.name and d.name:
                    existing.name = d.name

        return merged

    def _extract_proofs(self, text: str) -> List[Proof]:
        """
        Extract Proof objects from LaTeX source.

        Currently we only capture explicit `proof` environments, e.g.

            \\begin{proof}[Proof of Theorem~\\ref{thm:main}]
            ...
            \\end{proof}

        The optional argument is used to guess the parent theorem label via
        the first \\ref/\\eqref/\\autoref that appears in it. That label is
        stored in proof._target_theorem_label and later used by
        _link_proofs_to_theorems.
        """
        # We don't rely on env_kind_map here, because _parse_newtheorem
        # overwrites it and may drop 'proof'. Just hard-code the common envs.
        env_names = ["proof", "Proof"]
        found = self._extract_envs(text, env_names)

        objects: List[Proof] = []
        idx = 0

        # If the optional proof header includes something like \ref{thm:main},
        # we want to capture that label.
        header_ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")

        for env_name, opt_name, body, source_pos in found:
            idx += 1
            obj_id = f"R{idx}"  # Unique id for proofs; prefix doesn't matter elsewhere.

            # Try to pick up a \label{...} inside the proof body (rare, but possible).
            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)

            proof = Proof(
                id=obj_id,
                kind="proof",
                index=idx,
                label=label,
                name=opt_name.strip() if opt_name else None,
                raw_latex=body,
                clean_text=clean_text,
            )
            proof._source_pos = source_pos

            # Optional: header-based theorem label from \begin{proof}[...]
            if opt_name:
                m = header_ref_pattern.search(opt_name)
                if m:
                    # Not a dataclass field; just an auxiliary attribute.
                    setattr(proof, "_target_theorem_label", m.group(1))

            objects.append(proof)

        # --- Inline proofs: \par\noindent\emph{Proof} (no formal environment) ---
        # Collect raw_latex from environment-based proofs to avoid duplicates.
        env_bodies = {p.raw_latex for p in objects}

        inline_proof_pattern = re.compile(
            r'\\par\s*\\noindent\s*\\emph\{Proof\}\s*\.?\s*(?:\\newline)?\s*'
            r'(.*?)'
            r'(?=\\begin\{|\\par\s*\\noindent\s*\\emph\{|\\section|\\subsection|\\end\{document\}|\Z)',
            re.DOTALL
        )

        for match in inline_proof_pattern.finditer(text):
            body = match.group(1).strip()
            if not body or body in env_bodies:
                continue
            idx += 1
            obj_id = f"R{idx}"
            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)
            proof = Proof(
                id=obj_id,
                kind="proof",
                index=idx,
                label=label,
                name=None,
                raw_latex=body,
                clean_text=clean_text,
            )
            objects.append(proof)

        if objects:
            print(f"[INFO] _extract_proofs: found {len(objects)} proof environments.")

        return objects

    # ------------------------------------------------------------------
    # Algorithms
    # ------------------------------------------------------------------

    def _extract_algorithms(self, text: str) -> List[Algorithm]:
        """
        Extract Algorithm objects from LaTeX source.

        We look for typical algorithm environments, e.g.

            \\begin{algorithm}[H]
            \\caption{My algorithm}
            Input: ...
            Output: ...
            ...
            \\end{algorithm}

        and build Algorithm instances with:
          - env_name      : the LaTeX environment name ('algorithm', 'algorithm*', ...)
          - label         : any \\label{...} inside the environment
          - name          : optional argument to \\begin{algorithm}[...] if present
          - input_signature / output_signature : heuristically parsed from text
        """
        # We *don't* rely on env_kind_map here, because _parse_newtheorem
        # overwrites it and doesn't know about 'algorithm'. So we hard-code.
        env_names = ["algorithm", "algorithm*", "Algorithm", "Algorithm*"]
        found = self._extract_envs(text, env_names)

        objects: List[Algorithm] = []
        idx = 0

        for env_name, opt_name, body, source_pos in found:
            idx += 1
            obj_id = f"A{idx}"

            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)

            # Very crude heuristics for Input / Output:
            input_sig: Optional[str] = None
            output_sig: Optional[str] = None

            # Work on a lowercase version for pattern matching, but keep original words.
            # We search in the cleaned text.
            # Pattern: "Input: ... Output: ..." or just "Input: ..."
            m_in = re.search(
                r"Input\s*:?\s*(.*?)(?=Output\s*:|$)",
                clean_text,
                flags=re.IGNORECASE,
            )
            if m_in:
                input_sig = m_in.group(1).strip() or None

            m_out = re.search(
                r"Output\s*:?\s*(.*)",
                clean_text,
                flags=re.IGNORECASE,
            )
            if m_out:
                output_sig = m_out.group(1).strip() or None

            alg = Algorithm(
                id=obj_id,
                kind="algorithm",
                index=idx,
                label=label,
                name=opt_name.strip() if opt_name else None,
                raw_latex=body,
                clean_text=clean_text,
                env_name=env_name,
            )
            alg._source_pos = source_pos
            objects.append(alg)

        if objects:
            print(f"[INFO] _extract_algorithms: found {len(objects)} algorithm environments.")

        return objects

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def _extract_tables(self, text: str) -> List[TableObject]:
        """
        Extract TableObject objects from LaTeX source.

        We look for \\begin{table} ... \\end{table} (and star variants) and try to
        capture:
          - env_name : 'table', 'table*', ...
          - label    : any \\label{...} inside the environment
          - caption  : from \\caption{...}, cleaned to text
        """
        env_names = ["table", "table*", "Table", "Table*"]
        found = self._extract_envs(text, env_names)

        objects: List[TableObject] = []
        idx = 0
        caption_pattern = re.compile(r"\\caption\s*{([^}]*)}", flags=re.DOTALL)

        for env_name, opt_name, body, source_pos in found:
            idx += 1
            obj_id = f"Tb{idx}"

            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)

            caption: Optional[str] = None
            m_cap = caption_pattern.search(body)
            if m_cap:
                # Clean the caption text separately; often contains formatting.
                caption = self._clean_latex_to_text(m_cap.group(1))

            # Use caption as 'name' if available; otherwise fall back to optional env name
            name = caption or (opt_name.strip() if opt_name else None)

            tbl = TableObject(
                id=obj_id,
                kind="table",
                index=idx,
                label=label,
                name=name,
                raw_latex=body,
                clean_text=clean_text,
                env_name=env_name,
                caption=caption,
            )
            tbl._source_pos = source_pos
            objects.append(tbl)

        if objects:
            print(f"[INFO] _extract_tables: found {len(objects)} table environments.")

        return objects

    # ------------------------------------------------------------------
    # Link proofs to theorems
    # ------------------------------------------------------------------

    def _link_proofs_to_theorems(self, graph: PaperGraph) -> None:
        """
        Heuristically link each Proof object to a theorem-like object it proves.

        Strategy:
          1. Build a mapping label -> object_id for theorem-like objects
             (using their \\label{...}).
          2. For each proof:
             a) Use proof._target_theorem_label if present (from proof header).
             b) Otherwise, look for \\ref/\\eqref/\\autoref in the proof body and
                use the first label that matches a theorem-like object.
          3. As a fallback, if still unresolved, attach the proof to the
             nearest previous theorem-like object in document order.
          4. If found, set proof.parent_id = theorem_id and also
             proof._parent_link_source = one of:
                 'header_label', 'body_ref', 'prev_theorem_like'.

        Later, _build_relations() will add structural 'proves' edges
        theorem -> proof using this parent_id, and logical 'uses' edges
        based on references in the proof body.
        """
        # 1. label -> theorem-like object id
        label_to_theorem_id: Dict[str, str] = {}
        for obj_id, obj in graph.objects.items():
            if obj.kind in self.THEOREM_LIKE_KINDS and getattr(obj, "label", None):
                label_to_theorem_id[obj.label] = obj_id  # type: ignore[arg-type]

        # pattern for \ref{label}, \eqref{label}, \autoref{label}
        ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")

        linked_count = 0

        # --- pass 1: header label + body ref ---
        for obj in graph.objects.values():
            if obj.kind != "proof":
                continue

            parent_id: Optional[str] = getattr(obj, "parent_id", None)
            parent_source: Optional[str] = getattr(obj, "_parent_link_source", None)

            # (a) From header-based target label: proof._target_theorem_label
            if parent_id is None:
                target_label = getattr(obj, "_target_theorem_label", None)
                if target_label and target_label in label_to_theorem_id:
                    parent_id = label_to_theorem_id[target_label]
                    parent_source = "header_label"

            # (b) From first \ref/\eqref/\autoref in the proof body
            if parent_id is None:
                raw = getattr(obj, "raw_latex", "")
                for m in ref_pattern.finditer(raw):
                    lbl = m.group(1)
                    if lbl in label_to_theorem_id:
                        parent_id = label_to_theorem_id[lbl]
                        parent_source = "body_ref"
                        break

            if parent_id is not None:
                setattr(obj, "parent_id", parent_id)
                setattr(obj, "_parent_link_source", parent_source or "unknown")
                linked_count += 1

        # --- pass 2: fallback to previous theorem-like in document order ---
        # Use insertion order of graph.objects as a proxy for document order.
        last_thm_id: Optional[str] = None
        for obj_id, obj in graph.objects.items():
            if obj.kind in self.THEOREM_LIKE_KINDS:
                last_thm_id = obj_id
                continue

            if obj.kind != "proof":
                continue

            # only link proofs that still have no parent_id
            parent_id = getattr(obj, "parent_id", None)
            if parent_id is not None or last_thm_id is None:
                continue

            setattr(obj, "parent_id", last_thm_id)
            setattr(obj, "_parent_link_source", "prev_theorem_like")
            linked_count += 1

        if linked_count:
            print(f"[INFO] _link_proofs_to_theorems: linked {linked_count} proofs to theorems.")

    # ------------------------------------------------------------------
    # Build relations (edges) between objects
    # ------------------------------------------------------------------

    def _build_relations(self, graph: PaperGraph) -> None:
        """
        Populate graph.relations with links between the extracted math objects,
        using the new relation ontology.

        We currently add:

          1. Structural edges (canonical types per schema lock):
             - proof 'proves' theorem-like (proof → theorem)
             - container 'uses' equation (equation depends on container)
             - algorithm 'solves' problem (nearest preceding problem)
             - example 'illustrates' concept (nearest preceding def/theorem-like)
             - exercise 'tests' concept (nearest preceding def/theorem-like)

          2. Logical 'uses' edges with confidence:
             - any object -> another object it references via \ref/\eqref/\autoref
               in its raw_latex (confidence=1.0).

          3. Optional low-confidence 'uses' edges from theorems/proofs to
             definitions inferred via keyword overlap in the natural language
             text (confidence≈0.3). These are clearly marked in metadata.
        """

        # Start from any existing relations (should usually be empty).
        relations: List[Relation] = list(graph.relations)

        # For deduplication (by (source, target, type))
        existing: set[tuple[str, str, str]] = {
            (r.source_id, r.target_id, r.relation_type) for r in relations
        }

        # 1. Map labels -> object IDs for all labeled objects
        label_to_id: Dict[str, str] = {}
        for obj_id, obj in graph.objects.items():
            lbl = getattr(obj, "label", None)
            if lbl:
                label_to_id[lbl] = obj_id

        # ------------------------------------------------------------------
        # 2. Structural edges (canonical edge types per schema lock)
        #    (a) proof 'proves' theorem-like (proof → theorem)
        #    (b) container 'uses' equation (equation depends on container)
        # ------------------------------------------------------------------

        proves_count = 0
        equation_edge_count = 0

        # (a) proof proves theorem-like (via proof.parent_id)
        for obj in graph.objects.values():
            if obj.kind != "proof":
                continue

            parent_id = getattr(obj, "parent_id", None)
            if not parent_id:
                continue

            key = (obj.id, parent_id, "proves")
            if key in existing:
                continue

            parent_source = getattr(obj, "_parent_link_source", None)
            if parent_source in ("header_label", "body_ref"):
                confidence = 1.0
            elif parent_source == "prev_theorem_like":
                confidence = 0.5
            else:
                confidence = 0.8

            graph.add_relation(
                source_id=obj.id,
                target_id=parent_id,
                relation_type="proves",
                category="structural",
                metadata={
                    "parent_link_source": parent_source,
                    "confidence": confidence,
                },
            )
            existing.add(key)
            proves_count += 1

        # (b) container uses equation (via Equation.parent_id)
        for obj in graph.objects.values():
            if not isinstance(obj, Equation):
                continue

            parent_id = getattr(obj, "parent_id", None)
            if not parent_id:
                continue

            key = (parent_id, obj.id, "uses")
            if key in existing:
                continue

            graph.add_uses(
                user_id=parent_id,
                used_id=obj.id,
                metadata={"role": "equation_in", "confidence": 1.0},
            )
            existing.add(key)
            equation_edge_count += 1

        # ------------------------------------------------------------------
        # 2c. Structural edges: algorithm 'solves' problem
        #     Link each algorithm to the nearest preceding problem node.
        # ------------------------------------------------------------------

        solves_count = 0
        obj_ids = list(graph.objects.keys())
        for i, obj_id in enumerate(obj_ids):
            obj = graph.objects[obj_id]
            if obj.kind != "algorithm":
                continue
            # Walk backwards to find nearest preceding problem
            for j in range(i - 1, -1, -1):
                candidate = graph.objects[obj_ids[j]]
                if candidate.kind == "problem":
                    key = (obj.id, candidate.id, "solves")
                    if key not in existing:
                        graph.add_relation(
                            source_id=obj.id,
                            target_id=candidate.id,
                            relation_type="solves",
                            category="structural",
                            metadata={"source": "proximity", "confidence": 0.5},
                        )
                        existing.add(key)
                        solves_count += 1
                    break

        # ------------------------------------------------------------------
        # 2d. Structural edges: example 'illustrates' concept
        #     Link each example to the nearest preceding definition or
        #     theorem-like node.
        # ------------------------------------------------------------------

        illustrates_count = 0
        illustrates_targets = {"definition"} | self.THEOREM_LIKE_KINDS
        for i, obj_id in enumerate(obj_ids):
            obj = graph.objects[obj_id]
            if obj.kind != "example":
                continue
            for j in range(i - 1, -1, -1):
                candidate = graph.objects[obj_ids[j]]
                if candidate.kind in illustrates_targets:
                    key = (obj.id, candidate.id, "illustrates")
                    if key not in existing:
                        graph.add_relation(
                            source_id=obj.id,
                            target_id=candidate.id,
                            relation_type="illustrates",
                            category="structural",
                            metadata={"source": "proximity", "confidence": 0.5},
                        )
                        existing.add(key)
                        illustrates_count += 1
                    break

        # ------------------------------------------------------------------
        # 2e. Structural edges: exercise 'tests' concept
        #     Link each exercise to the nearest preceding definition or
        #     theorem-like node.
        # ------------------------------------------------------------------

        tests_count = 0
        tests_targets = {"definition"} | self.THEOREM_LIKE_KINDS
        for i, obj_id in enumerate(obj_ids):
            obj = graph.objects[obj_id]
            if obj.kind != "exercise":
                continue
            for j in range(i - 1, -1, -1):
                candidate = graph.objects[obj_ids[j]]
                if candidate.kind in tests_targets:
                    key = (obj.id, candidate.id, "tests")
                    if key not in existing:
                        graph.add_relation(
                            source_id=obj.id,
                            target_id=candidate.id,
                            relation_type="tests",
                            category="structural",
                            metadata={"source": "proximity", "confidence": 0.5},
                        )
                        existing.add(key)
                        tests_count += 1
                    break

        # ------------------------------------------------------------------
        # 3. Logical 'uses' edges from explicit \ref / \eqref / \autoref
        # ------------------------------------------------------------------

        ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")
        uses_ref_count = 0

        for obj in graph.objects.values():
            raw = getattr(obj, "raw_latex", "")
            if not raw:
                continue

            for m in ref_pattern.finditer(raw):
                lbl = m.group(1)
                target_id = label_to_id.get(lbl)
                if not target_id or target_id == obj.id:
                    continue

                key = (obj.id, target_id, "uses")
                if key in existing:
                    continue

                graph.add_uses(
                    user_id=obj.id,
                    used_id=target_id,
                    metadata={
                        "ref_label": lbl,
                        "source": "latex_ref",
                        "confidence": 1.0,
                    },
                )
                existing.add(key)
                uses_ref_count += 1

        # ------------------------------------------------------------------
        # 3b. Break length-2 cycles in 'uses' edges.
        #     If A→B and B→A both exist, keep only the edge where the source
        #     appears earlier in the document (insertion order of graph.objects).
        # ------------------------------------------------------------------

        doc_order = {obj_id: i for i, obj_id in enumerate(graph.objects)}
        uses_to_remove = set()
        for (src, tgt, rtype) in list(existing):
            if rtype != "uses":
                continue
            reverse = (tgt, src, "uses")
            if reverse in existing and reverse not in uses_to_remove:
                # Keep the edge whose source appears earlier in the document
                if doc_order.get(src, 0) > doc_order.get(tgt, 0):
                    uses_to_remove.add((src, tgt, "uses"))
                else:
                    uses_to_remove.add((tgt, src, "uses"))

        if uses_to_remove:
            graph.relations = [
                r for r in graph.relations
                if (r.source_id, r.target_id, r.relation_type) not in uses_to_remove
            ]
            existing -= uses_to_remove
            uses_ref_count -= len(uses_to_remove)
            print(f"[INFO] _build_relations: broke {len(uses_to_remove)} length-2 'uses' cycles via document order.")

        # ------------------------------------------------------------------
        # 4. Low-confidence 'uses' edges from theorems/proofs to definitions
        #    via keyword overlap in natural language text.
        #
        #    This is a very rough heuristic, clearly marked as such.
        # ------------------------------------------------------------------

        # Prepare definition keyword sets
        def _keyword_set(text: str) -> set:
            text = text.lower()
            words = re.findall(r"[a-zA-Z]+", text)
            stopwords = {
                "the", "a", "an", "and", "or", "of", "in", "for", "to",
                "is", "are", "be", "we", "this", "that", "such", "by",
                "with", "let", "denote", "define", "definition",
            }
            return {w for w in words if len(w) >= 5 and w not in stopwords}

        definitions: Dict[str, Definition] = {
            obj.id: obj
            for obj in graph.objects.values()
            if obj.kind == "definition"
        }

        if definitions:
            def_keywords: Dict[str, set] = {}
            for def_id, def_obj in definitions.items():
                txt = getattr(def_obj, "clean_text", "") or getattr(def_obj, "raw_latex", "")
                def_keywords[def_id] = _keyword_set(txt)

            # Candidates that might use definitions: theorem-like + proofs
            theorem_ids = [
                obj.id
                for obj in graph.objects.values()
                if obj.kind in self.THEOREM_LIKE_KINDS
            ]
            proof_ids = [
                obj.id
                for obj in graph.objects.values()
                if obj.kind == "proof"
            ]

            uses_kw_count = 0
            for user_id in theorem_ids + proof_ids:
                obj = graph.objects[user_id]
                txt = getattr(obj, "clean_text", "") or getattr(obj, "raw_latex", "")
                kw = _keyword_set(txt)
                if not kw:
                    continue

                for def_id, def_kw in def_keywords.items():
                    if not def_kw:
                        continue
                    common = kw & def_kw
                    if len(common) < 2:
                        continue

                    key = (user_id, def_id, "uses")
                    if key in existing:
                        continue

                    graph.add_uses(
                        user_id=user_id,
                        used_id=def_id,
                        metadata={
                            "source": "keyword_overlap",
                            "confidence": 0.3,
                            "keywords": sorted(list(common))[:5],
                        },
                    )
                    existing.add(key)
                    uses_kw_count += 1

        # Replace graph.relations with the accumulated ones
        graph.relations = relations + graph.relations[len(relations):]

        # ------------------------------------------------------------------
        # 5. Break remaining cycles (all lengths) in 'uses' edges.
        #    Runs AFTER all edge types have been added (ref, keyword, etc.).
        #    Iterative DFS finds back-edges; remove preferring low-confidence
        #    first, then document-order (latest source removed).
        # ------------------------------------------------------------------

        uses_adj: Dict[str, List[str]] = {}
        for (src, tgt, rtype) in existing:
            if rtype == "uses":
                uses_adj.setdefault(src, []).append(tgt)

        edge_confidence: Dict[tuple, float] = {}
        for r in graph.relations:
            if r.relation_type == "uses":
                meta = getattr(r, "metadata", {}) or {}
                edge_confidence[(r.source_id, r.target_id)] = meta.get("confidence", 1.0)

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in uses_adj}
        for targets in uses_adj.values():
            for t in targets:
                if t not in color:
                    color[t] = WHITE
        back_edges = []
        for start in list(color):
            if color[start] != WHITE:
                continue
            stack = [(start, 0)]
            color[start] = GRAY
            path_set = {start}
            while stack:
                node, idx = stack[-1]
                neighbors = uses_adj.get(node, [])
                if idx < len(neighbors):
                    stack[-1] = (node, idx + 1)
                    nxt = neighbors[idx]
                    if color.get(nxt) == GRAY and nxt in path_set:
                        back_edges.append((node, nxt))
                    elif color.get(nxt, WHITE) == WHITE:
                        color[nxt] = GRAY
                        path_set.add(nxt)
                        stack.append((nxt, 0))
                else:
                    color[node] = BLACK
                    path_set.discard(node)
                    stack.pop()

        cycle_removed = 0
        if back_edges:
            cycle_remove = set()
            for src, tgt in back_edges:
                key = (src, tgt, "uses")
                if key not in existing:
                    continue
                cycle_remove.add(key)
            if cycle_remove:
                graph.relations = [
                    r for r in graph.relations
                    if (r.source_id, r.target_id, r.relation_type) not in cycle_remove
                ]
                existing -= cycle_remove
                cycle_removed = len(cycle_remove)
                print(f"[INFO] _build_relations: broke {cycle_removed} back-edges to enforce DAG.")

        total_uses_kw = locals().get("uses_kw_count", 0)
        structural_total = proves_count + solves_count + illustrates_count + tests_count
        if structural_total or equation_edge_count or uses_ref_count or total_uses_kw:
            print(
                "[INFO] _build_relations: "
                f"added {proves_count} 'proves', "
                f"{solves_count} 'solves', "
                f"{illustrates_count} 'illustrates', "
                f"{tests_count} 'tests' edges, "
                f"{equation_edge_count} 'uses' (equation), "
                f"{uses_ref_count} 'uses' (ref), "
                f"{total_uses_kw} 'uses' (keyword)."
            )
