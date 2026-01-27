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
import requests
import json
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from openai import OpenAI

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
            llm_chunk_chars: int = 30000,
            llm_provider: str = "openai",
            extract_inline_let: bool = False,
            custom_prompt_file: Optional[str] = None,
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
        self.llm_provider = llm_provider
        self.extract_inline_let = extract_inline_let
        self.custom_prompt_file = custom_prompt_file

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
                    llm_type="anthropic",
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

        # C3: "We say/call X is/to be ..." - explicit definitional language
        inline_we_say_pattern = re.compile(
            r"(?P<full>"
            r"(?:We\s+)?(?:say|call)\s+(?:that\s+)?"
            r"(?P<name>[^.]{1,60}?)"
            r"\s+(?:is|to\s+be|are)\s+"
            r"[^.]*\.)",
            flags=re.IGNORECASE | re.DOTALL,
        )

        # C4: "Let X be ..." - only when it's a real definition (contains definitional keywords)
        # Filter out simple variable intros like "Let m,n be integers"
        inline_let_pattern = re.compile(
            r"(?P<full>"
            r"(?:Let|let)\s+"
            r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\_]+))"
            r"[^.]{0,200}?"
            r"\s+be\s+[^.]*\.)",
            flags=re.DOTALL,
        )

        # Keywords that indicate a real definition vs just variable introduction
        definition_keywords = re.compile(
            r"\b(set|function|map|mapping|sequence|matrix|space|operator|"
            r"define|denote|notation|collection|family|class|group|ring|field|"
            r"graph|path|tree|partition|permutation|morphism|homomorphism)\b",
            flags=re.IGNORECASE
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

        # C3: "We say/call X is..." - explicit definitional language
        for m in inline_we_say_pattern.finditer(text):
            add_inline_definition(m, "inline_we_say")

        # C4: "Let X be ..." - only when it contains definitional keywords
        # This filters out simple variable intros like "Let m,n be integers"
        for m in inline_let_pattern.finditer(text):
            full_text = m.group("full")
            # Only treat as definition if it contains definitional keywords
            if definition_keywords.search(full_text):
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
            llm_type: str = "anthropic",
            provider: str = "hosted",
            chunk_chars: int = 30000,
            model: str = "claude-sonnet-4-20250514",
    ) -> List[Definition]:
        actual_provider = getattr(self, 'llm_provider', llm_type)

        if actual_provider == "openai":
            return self._extract_definitions_openai(text, chunk_chars, model)
        elif actual_provider == "anthropic":
            return self._extract_definitions_anthropic(text, chunk_chars, model)
        elif actual_provider == "huggingface":  # ADD THIS
            return self._extract_definitions_huggingface(text, chunk_chars, model)
        else:
            print(f"[WARN] llm_provider='{actual_provider}' not supported.")
            return []

    def _extract_definitions_anthropic(
            self,
            text: str,
            chunk_chars: int,
            model: str,
    ) -> List[Definition]:
        """Anthropic-specific extraction."""
        try:
            import anthropic
        except ImportError:
            print("[ERROR] anthropic package not installed. Run: pip install anthropic")
            return []

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("[ERROR] ANTHROPIC_API_KEY environment variable not set.")
            return []

        client = anthropic.Anthropic(api_key=api_key)
        chunks = self._chunk_text(text, chunk_chars)
        print(f"[INFO] _extract_definitions_anthropic: processing {len(chunks)} chunks with {model}")

        all_definitions: List[Definition] = []
        idx = 0

        for chunk_idx, chunk in enumerate(chunks, 1):
            print(f"[INFO] Processing chunk {chunk_idx}/{len(chunks)}...")
            prompt = self._create_definition_extraction_prompt(chunk)

            try:
                message = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                response_text = message.content[0].text
                definitions_data = self._parse_llm_response(response_text)

                for def_data in definitions_data:
                    idx += 1
                    all_definitions.append(
                        Definition(
                            id=f"D{idx}",
                            kind="definition",
                            index=idx,
                            label=def_data.get("label"),
                            name=def_data.get("name"),
                            raw_latex=def_data.get("raw_latex", ""),
                            clean_text=def_data.get("clean_text", ""),
                            env_name=None,
                        )
                    )
            except Exception as e:
                print(f"[ERROR] Anthropic API call failed for chunk {chunk_idx}: {e}")

        print(f"[INFO] _extract_definitions_anthropic: found {len(all_definitions)} definitions total.")
        return all_definitions

    def _extract_definitions_openai(
            self,
            text: str,
            chunk_chars: int,
            model: str,
    ) -> List[Definition]:
        """OpenAI-specific extraction."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("[ERROR] OPENAI_API_KEY environment variable not set.")
            return []

        client = OpenAI(api_key=api_key)
        chunks = self._chunk_text(text, chunk_chars)
        print(f"[INFO] _extract_definitions_openai: processing {len(chunks)} chunks with {model}")

        all_definitions: List[Definition] = []
        idx = 0

        for chunk_idx, chunk in enumerate(chunks, 1):
            print(f"[INFO] Processing chunk {chunk_idx}/{len(chunks)}...")
            prompt = self._create_definition_extraction_prompt(chunk)

            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                )
                response_text = response.choices[0].message.content
                definitions_data = self._parse_llm_response(response_text)

                for def_data in definitions_data:
                    idx += 1
                    all_definitions.append(
                        Definition(
                            id=f"D{idx}",
                            kind="definition",
                            index=idx,
                            label=def_data.get("label"),
                            name=def_data.get("name"),
                            raw_latex=def_data.get("raw_latex", ""),
                            clean_text=def_data.get("clean_text", ""),
                            env_name=None,
                        )
                    )
            except Exception as e:
                print(f"[ERROR] OpenAI API call failed for chunk {chunk_idx}: {e}")

        print(f"[INFO] _extract_definitions_openai: found {len(all_definitions)} definitions total.")
        return all_definitions

    def _extract_definitions_huggingface(
            self,
            text: str,
            chunk_chars: int,
            model: str,
    ) -> List[Definition]:
        """Extract definitions using Hugging Face's OpenAI-compatible API."""
        api_key = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
        if not api_key:
            print("[ERROR] HF_TOKEN or HUGGINGFACE_API_KEY environment variable not set.")
            return []

        client = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=api_key,
        )

        chunks = self._chunk_text(text, chunk_chars)
        print(f"[INFO] _extract_definitions_huggingface: processing {len(chunks)} chunks with {model}")

        all_definitions: List[Definition] = []
        idx = 0

        for chunk_index, chunk in enumerate(chunks, 1):
            print(f"[INFO] Processing chunk {chunk_index}/{len(chunks)} with Hugging Face API")
            prompt = self._create_definition_extraction_prompt(chunk)

            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.3
                )

                response_text = completion.choices[0].message.content
                definitions_data = self._parse_llm_response(response_text)

                for def_data in definitions_data:
                    idx += 1
                    all_definitions.append(
                        Definition(
                            id=f"D{idx}",
                            kind="definition",
                            index=idx,
                            label=def_data.get("label"),
                            name=def_data.get("name") or def_data.get("term"),
                            raw_latex=def_data.get("raw_latex", ""),
                            clean_text=def_data.get("clean_text") or def_data.get("definition", ""),
                            env_name=None,
                        )
                    )
            except Exception as e:
                print(f"[ERROR] Hugging Face API call failed for chunk {chunk_index}: {e}")

        print(f"[INFO] _extract_definitions_huggingface: found {len(all_definitions)} definitions total.")
        return all_definitions

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

    def _create_definition_extraction_prompt(self, latex_chunk: str) -> str:
        """Create a prompt for LLM to extract definitions.
        """

        # if prompt file is available:
        if self.custom_prompt_file and Path(self.custom_prompt_file).exists():
            template = Path(self.custom_prompt_file).read_text()
            print("Using Prompt from file:", self.custom_prompt_file)
            return template.replace("{latex_chunk}", latex_chunk)

        # otherwise use default prompt
        print("Using Default Prompt Template - No custom prompt file provided.")
        prompt = f"""You are analyzing a mathematical paper written in LaTeX. Extract ALL mathematical definitions.

Definition forms:
1. \\begin{{definition}}...\\end{{definition}}
2. "Definition 2.1. ..."
3. "We define X as/to be ...", "X is defined as ...", "Let X be ..."
4. Implicit definitions with new notation

For each definition, extract:
- name: Short descriptive name
- raw_latex: Original LaTeX text (preserve ALL math notation)
- clean_text: Human-readable version (keep [MATH] for formulas)
- label: Any \\label{{...}} or null

Return JSON array:
[
  {{
    "name": "descriptive name",
    "raw_latex": "original LaTeX",
    "clean_text": "readable text",
    "label": "label or null"
  }}
]

LaTeX text:

{latex_chunk}

Respond ONLY with JSON array."""
        return prompt

    @staticmethod
    def _parse_llm_response(response_text: str) -> List[Dict[str, Any]]:
        """Parse Claude's JSON response."""
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

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
          3. As a fallback, if still unresolved, attach the proof to the
             nearest previous theorem-like object in document order.
          4. If found, set proof.parent_id = theorem_id and also
             proof._parent_link_source = one of:
                 'header_label', 'body_ref', 'prev_theorem_like'.

        Later, _build_relations() will add structural 'has_part' edges
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

          1. Structural 'has_part' edges:
             - theorem-like / definition / algorithm -> proof/equation
               (based on parent_id + roles, with confidence depending on how
               the parent_id was inferred).

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
        # 2. Structural 'has_part' edges
        #    (a) theorem-like / other containers have_part their proofs
        #    (b) containers have_part their equations
        # ------------------------------------------------------------------

        has_part_proof_count = 0
        has_part_equation_count = 0

        # (a) theorem-like has_part proof (via proof.parent_id)
        for obj in graph.objects.values():
            if obj.kind != "proof":
                continue

            parent_id = getattr(obj, "parent_id", None)
            if not parent_id:
                continue

            key = (parent_id, obj.id, "has_part")
            if key in existing:
                continue

            parent_source = getattr(obj, "_parent_link_source", None)
            if parent_source in ("header_label", "body_ref"):
                confidence = 1.0
            elif parent_source == "prev_theorem_like":
                confidence = 0.5
            else:
                confidence = 0.8

            graph.add_has_part(
                whole_id=parent_id,
                part_id=obj.id,
                metadata={
                    "role": "proof_of",
                    "parent_link_source": parent_source,
                    "confidence": confidence,
                },
            )
            existing.add(key)
            has_part_proof_count += 1

        # (b) container has_part equation (via Equation.parent_id)
        for obj in graph.objects.values():
            if not isinstance(obj, Equation):
                continue

            parent_id = getattr(obj, "parent_id", None)
            if not parent_id:
                continue

            key = (parent_id, obj.id, "has_part")
            if key in existing:
                continue

            graph.add_has_part(
                whole_id=parent_id,
                part_id=obj.id,
                metadata={"role": "equation_in", "confidence": 1.0},
            )
            existing.add(key)
            has_part_equation_count += 1

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

        total_uses_kw = locals().get("uses_kw_count", 0)
        if has_part_proof_count or has_part_equation_count or uses_ref_count or total_uses_kw:
            print(
                "[INFO] _build_relations: "
                f"added {has_part_proof_count} 'has_part' (proof) edges, "
                f"{has_part_equation_count} 'has_part' (equation) edges, "
                f"{uses_ref_count} 'uses' (ref) edges, "
                f"{total_uses_kw} 'uses' (keyword) edges."
            )
