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
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

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
        inline_let_pattern = re.compile(
            r"(?P<full>"
            r"(?:Let|let)\s+"
            r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_]+))"
            r"[^.]{0,200}?"
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
    # LLM-based definitions (stub implementation)
    # ------------------------------------------------------------------

    def _extract_definitions_llm(
        self,
        text: str,
        llm_type: str = "openai",
        provider: str = "hosted",
        chunk_chars: int = 8000,
        model: str = "gpt-4o-mini",
    ) -> List[Definition]:
        """
        Stub for LLM-based definition extraction.

        Right now we don't actually call any LLM here; we just return an empty list.
        This keeps the pipeline working when definition_mode is 'both' or 'llm'
        without crashing, and you can later plug in a real implementation.
        """
        # If you later want real LLM extraction, implement it here.
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

        for env_name, opt_name, body in found:
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

            # Optional: header-based theorem label from \begin{proof}[...]
            if opt_name:
                m = header_ref_pattern.search(opt_name)
                if m:
                    # Not a dataclass field; just an auxiliary attribute.
                    setattr(proof, "_target_theorem_label", m.group(1))

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

        for env_name, opt_name, body in found:
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
                input_signature=input_sig,
                output_signature=output_sig,
            )
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

        for env_name, opt_name, body in found:
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
          3. If found, set proof.parent_id = theorem_id.

        Relation edges (proof -> theorem, 'proves') are added later in
        _build_relations based on proof.parent_id.
        """
        # 1. label -> theorem-like object id
        label_to_theorem_id: Dict[str, str] = {}
        for obj_id, obj in graph.objects.items():
            if obj.kind in self.THEOREM_LIKE_KINDS and getattr(obj, "label", None):
                label_to_theorem_id[obj.label] = obj_id  # type: ignore[arg-type]

        if not label_to_theorem_id:
            return

        # pattern for \ref{label}, \eqref{label}, \autoref{label}
        ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")

        linked_count = 0

        for obj in graph.objects.values():
            if obj.kind != "proof":
                continue

            parent_id: Optional[str] = getattr(obj, "parent_id", None)

            # (a) From header-based target label: proof._target_theorem_label
            if parent_id is None:
                target_label = getattr(obj, "_target_theorem_label", None)
                if target_label and target_label in label_to_theorem_id:
                    parent_id = label_to_theorem_id[target_label]

            # (b) From first \ref/\eqref/\autoref in the proof body
            if parent_id is None:
                raw = getattr(obj, "raw_latex", "")
                for m in ref_pattern.finditer(raw):
                    lbl = m.group(1)
                    if lbl in label_to_theorem_id:
                        parent_id = label_to_theorem_id[lbl]
                        break

            if parent_id is not None:
                setattr(obj, "parent_id", parent_id)
                linked_count += 1

        if linked_count:
            print(f"[INFO] _link_proofs_to_theorems: linked {linked_count} proofs to theorems.")

    # ------------------------------------------------------------------
    # Build relations (edges) between objects
    # ------------------------------------------------------------------

    def _build_relations(self, graph: PaperGraph) -> None:
        """
        Populate graph.relations with Relation objects describing links between
        the extracted math objects.

        Currently we add:
          - 'proves'           : proof -> theorem-like object (if parent_id set)
          - 'contains_equation': container (thm/def/proof/alg) -> equation
          - 'refers_to'        : any object -> another object mentioned via
                                 \\ref/\\eqref/\\autoref in its raw_latex
        """
        relations: List[Relation] = list(graph.relations)  # start from any existing ones

        # For deduplication
        existing: set[tuple[str, str, str]] = {
            (r.source_id, r.target_id, r.relation_type) for r in relations
        }

        # 1. Map labels -> object IDs for all labeled objects
        label_to_id: Dict[str, str] = {}
        for obj_id, obj in graph.objects.items():
            lbl = getattr(obj, "label", None)
            if lbl:
                label_to_id[lbl] = obj_id

        # 2. 'proves' edges: proof -> theorem-like (via parent_id)
        proves_count = 0
        for obj in graph.objects.values():
            if obj.kind != "proof":
                continue
            parent_id = getattr(obj, "parent_id", None)
            if not parent_id:
                continue
            key = (obj.id, parent_id, "proves")
            if key not in existing:
                relations.append(Relation(source_id=obj.id, target_id=parent_id, relation_type="proves"))
                existing.add(key)
                proves_count += 1

        # 3. 'contains_equation' edges: container -> equation (via Equation.parent_id)
        contains_count = 0
        for obj in graph.objects.values():
            if not isinstance(obj, Equation):
                continue
            parent_id = getattr(obj, "parent_id", None)
            if not parent_id:
                continue
            key = (parent_id, obj.id, "contains_equation")
            if key not in existing:
                relations.append(Relation(source_id=parent_id, target_id=obj.id, relation_type="contains_equation"))
                existing.add(key)
                contains_count += 1

        # 4. 'refers_to' edges: any object -> another object with matching label
        ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")
        refers_count = 0

        for obj in graph.objects.values():
            raw = getattr(obj, "raw_latex", "")
            if not raw:
                continue

            for m in ref_pattern.finditer(raw):
                lbl = m.group(1)
                target_id = label_to_id.get(lbl)
                if not target_id or target_id == obj.id:
                    continue
                key = (obj.id, target_id, "refers_to")
                if key not in existing:
                    relations.append(
                        Relation(
                            source_id=obj.id,
                            target_id=target_id,
                            relation_type="refers_to",
                        )
                    )
                    existing.add(key)
                    refers_count += 1

        graph.relations = relations

        if proves_count or contains_count or refers_count:
            print(
                "[INFO] _build_relations: "
                f"added {proves_count} 'proves', "
                f"{contains_count} 'contains_equation', "
                f"{refers_count} 'refers_to' relations."
            )



def paper_to_network(
    paper: Union["PaperGraph", str, Path],
    out_png: str,
    node_label_attr: str = "id",
    include_kinds: Optional[List[str]] = None,
    include_relation_types: Optional[List[str]] = None,
    figsize: Tuple[int, int] = (12, 8),
) -> nx.DiGraph:
    """
    Build and draw a network of math objects in a paper and save it as a PNG.

    Parameters
    ----------
    paper : PaperGraph | str | Path
        Either:
          - a PaperGraph instance; or
          - path to a JSON file produced by PaperGraph.to_dict().
    out_png : str
        Path to the PNG file to write.
    node_label_attr : {'id', 'label', 'name'}
        Which attribute to use for node labels.
    include_kinds : list[str] or None
        If given, only include objects whose .kind is in this list.
    include_relation_types : list[str] or None
        If given, only include relations whose .relation_type is in this list.
    figsize : (w, h)
        Figure size in inches.
    """
    # ---- 1. Load / normalize PaperGraph ----
    if isinstance(paper, PaperGraph):
        graph = paper
    else:
        p = Path(paper)
        data = json.loads(p.read_text(encoding="utf-8"))
        # If you’re using math_classes.PaperGraph with from_dict:
        try:
            graph = PaperGraph.from_dict(data)  # type: ignore[attr-defined]
        except AttributeError:
            # Old-style PaperGraph with no from_dict: assume dict structure
            graph = PaperGraph(paper_id=data.get("paper_id", "paper"))
            for obj_id, od in data.get("objects", {}).items():
                # minimal reconstruction; if you have math_classes you won't hit this.
                kind = od.get("kind", "object")
                raw_latex = od.get("raw_latex", "")
                clean_text = od.get("clean_text", "")
                label = od.get("label")
                name = od.get("name")
                index = od.get("index", 0)
                graph.objects[obj_id] = MathObject(
                    id=obj_id,
                    kind=kind,
                    index=index,
                    label=label,
                    name=name,
                    raw_latex=raw_latex,
                    clean_text=clean_text,
                )
            for r in data.get("relations", []):
                graph.relations.append(
                    Relation(
                        source_id=r["source_id"],
                        target_id=r["target_id"],
                        relation_type=r["relation_type"],
                    )
                )

    objects = graph.objects

    # ---- 2. Build a directed graph ----
    G = nx.DiGraph()

    # nodes
    for obj_id, obj in objects.items():
        if include_kinds is not None and obj.kind not in include_kinds:
            continue
        G.add_node(
            obj_id,
            kind=obj.kind,
        )

    # edges
    for rel in graph.relations:
        src = getattr(rel, "source_id", getattr(rel, "source", None))
        tgt = getattr(rel, "target_id", getattr(rel, "target", None))
        rtype = getattr(rel, "relation_type", None)

        if src is None or tgt is None:
            continue
        if src not in G.nodes or tgt not in G.nodes:
            # skip relations involving filtered-out nodes
            continue
        if include_relation_types is not None and rtype not in include_relation_types:
            continue

        G.add_edge(src, tgt, relation_type=rtype)

    if G.number_of_nodes() == 0:
        print("[WARN] paper_to_network: no nodes to draw (check include_kinds filter).")
        return G

    # ---- 3. Layout ----
    pos = nx.spring_layout(G, seed=42)

    # ---- 4. Colors & labels ----
    kind_color_map: Dict[str, str] = {
        "theorem": "red",
        "lemma": "orange",
        "proposition": "darkred",
        "corollary": "salmon",
        "claim": "pink",
        "definition": "green",
        "problem": "darkblue",
        "conjecture": "magenta",
        "proof": "purple",
        "algorithm": "brown",
        "table": "gray",
        "equation": "black",
    }

    # group nodes by kind
    kinds_present = sorted({d.get("kind", "other") for _, d in G.nodes(data=True)})

    plt.figure(figsize=figsize)

    for kind in kinds_present:
        nodes_of_kind = [n for n, d in G.nodes(data=True) if d.get("kind") == kind]
        if not nodes_of_kind:
            continue
        color = kind_color_map.get(kind, "lightgray")
        nx.draw_networkx_nodes(
            G,
            pos,
            nodelist=nodes_of_kind,
            node_color=color,
            node_size=400,
            alpha=0.9,
        )

    nx.draw_networkx_edges(
        G,
        pos,
        arrowstyle="->",
        arrowsize=10,
        alpha=0.4,
    )

    # labels
    node_labels: Dict[str, str] = {}
    for node in G.nodes():
        obj = objects.get(node)
        if obj is None:
            node_labels[node] = node
            continue

        if node_label_attr == "label" and getattr(obj, "label", None):
            node_labels[node] = obj.label  # type: ignore[assignment]
        elif node_label_attr == "name" and getattr(obj, "name", None):
            node_labels[node] = obj.name  # type: ignore[assignment]
        else:
            node_labels[node] = obj.id

    nx.draw_networkx_labels(
        G,
        pos,
        labels=node_labels,
        font_size=8,
    )

    # legend
    legend_handles = []
    for kind in kinds_present:
        color = kind_color_map.get(kind, "lightgray")
        legend_handles.append(mpatches.Patch(color=color, label=kind))
    if legend_handles:
        plt.legend(
            handles=legend_handles,
            fontsize=8,
            loc="best",
            frameon=True,
        )

    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_png, bbox_inches="tight")
    plt.close()

    print(f"[INFO] paper_to_network: saved figure to {out_png}")
    return G
