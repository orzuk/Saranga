#!/usr/bin/env python3
"""
math_paper_parser.py

Heuristic LaTeX parser for mathematical papers.

Features:
- Accepts local .tex file OR arXiv ID OR arXiv URL
- Downloads arXiv source tarball automatically when needed
- Extracts:
    - definitions
    - theorems / lemmas / propositions / corollaries / claims / conjectures
    - proofs
    - algorithms
    - tables
- Builds a relation graph
- Can print a summary AND dump structured output to JSON
"""

from __future__ import annotations
import re
import argparse
import json
import tarfile
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

import requests  # pip install requests

import networkx as nx  # For drawing
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches



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
        "Theorem": "theorem",      # NEW
        "thm": "theorem",

        "lemma": "lemma",
        "Lemma": "lemma",          # NEW
        "lem": "lemma",

        "proposition": "proposition",
        "Proposition": "proposition",   # NEW
        "prop": "proposition",

        "corollary": "corollary",
        "Corollary": "corollary",       # NEW
        "cor": "corollary",

        "claim": "claim",
        "Claim": "claim",               # NEW

        "definition": "definition",
        "Definition": "definition",     # NEW
        "defn": "definition",

        "proof": "proof",               # environment version
        "Proof": "proof",               # NEW (rare)

        "algorithm": "algorithm",
        "algorithm*": "algorithm",

        "table": "table",

        # common variants
        "theo": "theorem",
        "conjecture": "conjecture",
        "Conjecture": "conjecture",     # NEW
    }


    THEOREM_LIKE_KINDS = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"}

    def __init__(self, paper_id: Optional[str] = None):
        self.paper_id = paper_id or "paper"
        # these will be updated with \newtheorem info
        self.env_kind_map = dict(self.BASE_ENV_KIND_MAP)


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

        Examples it will catch:

            \\newcommand{\\eq}[1]{(\\ref{#1})}
            \\newcommand{\\Eq}[1]{Equation~\\eqref{#1}}
            \\renewcommand{\\thmref}[1]{Theorem~\\ref{#1}}

        After this pass:

            \\eq{lbl}    -> \\ref{lbl}
            \\Eq{lbl}    -> \\eqref{lbl}
            \\thmref{t1} -> \\ref{t1}

        (we don't preserve the surrounding English words, we just normalise
        the reference part so later regexes see \\ref/\\eqref.)
        """
        # Find 1-arg newcommand/renewcommand with a body
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

            # NEW: ignore includes that are clearly macro arguments, like {#1}
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
                    # recursively expand inputs inside the included file
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

    # ---- equations ----

    def _extract_equations_from_body(self, body: str, parent_id: Optional[str]) -> List[Equation]:
        """
        Extract equation-like displays inside a given LaTeX body.

        We look for:
          - \\begin{equation}, equation*, align, align*, gather, multline, etc.
          - $$ ... $$
          - \\[ ... \\]

        parent_id: id of the containing object (theorem/definition/proof/algorithm), or None.
        """
        equations: List[Equation] = []

        # 1) Environment-based displays: equation, align, gather, multline
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
                raw_latex=m.group(0),  # full environment
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
        and optionally from the full document (top-level equations).

        For now we focus on equations inside containers, since those
        are the most semantically relevant.
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

        # 2) (optional) top-level equations in the full text, with no parent
        # Uncomment if you want them:
        top_eqs = self._extract_equations_from_body(full_text, parent_id=None)
        for eq in top_eqs:
            eq_idx += 1
            eq.id = f"E{eq_idx}"
            eq.index = eq_idx
            all_eqs.append(eq)

        return all_eqs



    # ------------------ public entry point ---------------------------

    def parse_file(self, path: str | Path) -> PaperGraph:
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="ignore")

        # 1) Merge all included files AND expand simple macros
        text = self._expand_inputs(text, base_dir=path.parent)

        # 2) Restrict to document body only
        m = re.search(r"\\begin{document}(.*)\\end{document}", text, flags=re.DOTALL)
        if m:
            text = m.group(1)

        # 3) Now do normal preprocessing & parsing
        text = self._strip_comments(text)
        self._parse_newtheorem(text)

        graph = PaperGraph(paper_id=self.paper_id)

        # Extract core environments
        theorem_like = self._extract_theorem_like(text)
        definitions = self._extract_definitions(text)
        proofs = self._extract_proofs(text)
        algorithms = self._extract_algorithms(text)
        tables = self._extract_tables(text)

        # equations inside theorem/definition/proof/algorithm bodies
        containers: List[MathObject] = theorem_like + definitions + proofs + algorithms
        equations = self._extract_equations(text, containers)

        for obj in theorem_like + definitions + proofs + algorithms + tables + equations:
            obj.paper_id = self.paper_id
            graph.add_object(obj)

        self._link_proofs_to_theorems(graph)
        self._build_relations(graph)

        return graph

    # ------------------ low-level helpers ---------------------------

    @staticmethod
    def _strip_comments(text: str) -> str:
        """Remove LaTeX comments (%) except escaped \%."""
        lines = []
        for line in text.splitlines():
            # remove unescaped %
            m = re.search(r"(?<!\\)%", line)
            if m:
                line = line[: m.start()]
            lines.append(line)
        return "\n".join(lines)

    def _parse_newtheorem(self, text: str) -> None:
        """
        Parse \\newtheorem definitions and populate env_kind_map.

        Handles both:
            \newtheorem{theorem}{Theorem}
            \newtheorem{lemma}[theorem]{\sc Lemma\rm}

        and classifies environments by the printed name (the second argument),
        so that envs like 'thm' or 'Theorem' also get mapped to 'theorem'.
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
        }
        self.env_kind_map = dict(base_map)

        # \newtheorem{env}[counter]{Printed Name}
        pattern = re.compile(
            r"\\newtheorem\s*{([^}]+)}(?:\[[^\]]+\])?\s*{([^}]+)}",
            flags=re.DOTALL,
        )

        for env_name, printed in pattern.findall(text):
            env_name = env_name.strip()
            # Normalize printed name by stripping non-letters
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
            ]:
                if candidate in printed_clean:
                    kind = candidate
                    break

            if kind:
                self.env_kind_map[env_name] = kind


    @staticmethod
    def _clean_latex_to_text(latex: str) -> str:
        """Best-effort LaTeX -> plain text cleaner (keeps math markers)."""
        # remove common formatting commands
        latex = re.sub(r"\\(textbf|textit|emph|mathrm|mathbf|mathit|text)\s*{([^}]*)}", r"\2", latex)
        # replace math with [MATH] tokens
        latex = re.sub(r"\$\$(.*?)\$\$", " [MATH] ", latex, flags=re.DOTALL)
        latex = re.sub(r"\$(.*?)\$", " [MATH] ", latex, flags=re.DOTALL)
        latex = re.sub(r"\\\[(.*?)\\\]", " [MATH] ", latex, flags=re.DOTALL)
        latex = re.sub(r"\\begin{equation\*?}(.*?)\\end{equation\*?}", " [MATH] ", latex, flags=re.DOTALL)
        # remove LaTeX commands
        latex = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:{[^}]*})?", "", latex)
        # remove multiple spaces/newlines
        latex = re.sub(r"\s+", " ", latex)
        return latex.strip()

    @staticmethod
    def _extract_label_and_name(env_body: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract \\label{...} from environment body."""
        label_match = re.search(r"\\label{([^}]*)}", env_body)
        label = label_match.group(1).strip() if label_match else None
        return label, None

    # ------------------ environment extraction ----------------------

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

    # ---- theorem-like ----

    def _extract_theorem_like(self, text: str) -> List[TheoremLike]:
        # envs whose kind is one of the canonical theorem-like kinds
        env_names = [
            env for env, kind in self.env_kind_map.items()
            if kind in self.THEOREM_LIKE_KINDS
        ]
        print(f"[DEBUG] theorem-like env_names: {env_names}")

        if not env_names:
            return []

        # find all \begin{env} ... \end{env} occurrences
        found = self._extract_envs(text, env_names)
        print(f"[DEBUG] found {len(found)} theorem-like environments")

        # counters per kind: theorem, lemma, proposition, ...
        counters: Dict[str, int] = {k: 0 for k in self.THEOREM_LIKE_KINDS}
        objects: List[TheoremLike] = []

        for env_name, opt_name, body in found:
            kind = self.env_kind_map.get(env_name, "theorem")
            counters.setdefault(kind, 0)
            counters[kind] += 1
            idx = counters[kind]

            # ID: T1, L2, P3, C4, ...
            obj_id = kind[0].upper() + str(idx)

            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)
            assumptions, statement = self._split_assumptions_statement(clean_text)

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

        We treat initial sentences starting with 'Let', 'Suppose', 'Assume', 'Given'
        as assumptions, and if we see 'Then', 'Hence', 'Therefore' starting a sentence,
        we split there.
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

    # ---- definitions ----

    def _extract_definitions(self, text: str) -> List[Definition]:
        env_names = [env for env, kind in self.env_kind_map.items() if kind == "definition"]
        if not env_names:
            return []

        found = self._extract_envs(text, env_names)
        idx = 0
        objects: List[Definition] = []

        for env_name, opt_name, body in found:
            idx += 1
            obj_id = "D" + str(idx)
            label, _ = self._extract_label_and_name(body)
            clean_text = self._clean_latex_to_text(body)
            obj = Definition(
                id=obj_id,
                kind="definition",
                index=idx,
                label=label,
                name=opt_name.strip() if opt_name else None,
                raw_latex=body,
                clean_text=clean_text,
                env_name=env_name,
            )
            objects.append(obj)
        return objects

    # ---- proofs ----

    def _extract_proofs(self, text: str) -> List[Proof]:
        proofs: List[Proof] = []
        idx = 0

        # --- A. Standard \begin{proof}...\end{proof} (if present) ---
        env_pattern = re.compile(
            r"\\begin{proof}(?P<body>.*?)\\end{proof}",
            flags=re.DOTALL,
        )
        for m in env_pattern.finditer(text):
            body = m.group("body")
            label, name = self._extract_label_and_name(body)
            clean = self._clean_latex_to_text(body)
            idx += 1
            proofs.append(
                Proof(
                    id=f"P{idx}",
                    kind="proof",
                    index=idx,
                    label=label,
                    name=name,
                    raw_latex=m.group(0),
                    clean_text=clean,
                    parent_id=None,  # will be set in _link_proofs_to_theorems
                )
            )

        # --- B. Textual proofs: \noindent{\sc Proof ...}: ... ---
        # Pattern: \noindent{\sc <header>}:(body ...)
        text_proof_pattern = re.compile(
            r"\\noindent\s*{\s*\\sc\s*([^}]*)}\s*:(?P<body>.*?)"
            r"(?=(\\noindent\s*{\s*\\sc)|\\section\b|\\subsection\b|"
            r"\\begin{[A-Za-z]+}|\\end{document})",
            flags=re.DOTALL,
        )

        for m in text_proof_pattern.finditer(text):
            header = m.group(1)           # e.g. "Proof of Theorem~\ref{T22VII18.1}"
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
                parent_id=None,  # to be filled
            )

            # Try to capture the theorem label from the header, e.g. \ref{T22VII18.1}
            mref = re.search(r"\\ref{([^}]+)}", header)
            if mref:
                # We'll use this in _link_proofs_to_theorems
                proof._target_theorem_label = mref.group(1)  # type: ignore[attr-defined]

            proofs.append(proof)

        return proofs


    # ---- algorithms ----

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
        Very rough parser for algorithm pseudo-code:
        - split by lines
        - tag lines starting with 'for', 'while', 'if' (after trimming LaTeX)
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

    # ---- tables ----

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

    # ------------------ linking & relations -------------------------

    @staticmethod
    def _sort_objects_by_occurrence(graph: PaperGraph) -> List[MathObject]:
        # crude sort by id prefix then index
        return sorted(graph.objects.values(), key=lambda o: (o.kind, o.index))

    def _link_proofs_to_theorems(self, graph: PaperGraph) -> None:
        """
        Set proof.parent_id for each Proof object.

        Strategy:
        1. If the proof has a header-derived label (e.g. Proof of Theorem~\ref{...}),
           link to that theorem-like object.
        2. Otherwise, link to the nearest preceding theorem-like by index.
        """
        # Build label -> theorem-like id map
        label_to_theorem_id: Dict[str, str] = {}
        for obj in graph.objects.values():
            if isinstance(obj, TheoremLike) and getattr(obj, "label", None):
                label_to_theorem_id[obj.label] = obj.id

        # Collect proofs and theorem-like objects, sorted by index
        proofs = [o for o in graph.objects.values() if isinstance(o, Proof)]
        theorems = [o for o in graph.objects.values() if isinstance(o, TheoremLike)]
        theorems_sorted = sorted(theorems, key=lambda t: t.index)

        for proof in proofs:
            # 1. Try header-based label: proof._target_theorem_label
            target_from_header = getattr(proof, "_target_theorem_label", None)
            if target_from_header and target_from_header in label_to_theorem_id:
                proof.parent_id = label_to_theorem_id[target_from_header]
                continue

            # 2. Fallback: nearest preceding theorem-like by index
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
        """
        # mapping label -> id
        label_to_id: Dict[str, str] = {}
        for obj in graph.objects.values():
            if getattr(obj, "label", None):
                label_to_id[obj.label] = obj.id

        # generic reference pattern (ref / eqref / autoref)
        ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")

        # 1. References inside proofs -> "used_in_proof"
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

        # 2. References inside theorem-like statements -> "uses"
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

        # 3. Definitions used anywhere -> "uses_definition"
        #    Allow ref/eqref/autoref after "Definition"
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

        # 4. Heuristic: special case / generalization phrasing
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

        # 5. Equations belonging to a parent object (theorem/definition/proof/algorithm)
        for obj in graph.objects.values():
            if isinstance(obj, Equation) and obj.parent_id:
                graph.add_relation(
                    source_id=obj.id,
                    target_id=obj.parent_id,
                    relation_type="in_environment_of",
                )

# ---------------------------------------------------------------------
# Input resolution: local path / arXiv ID / URL
# ---------------------------------------------------------------------


ARXIV_ID_RE = re.compile(r"^(?:arXiv:)?(\d{4}\.\d{4,5})(v\d+)?$")


def is_arxiv_id(s: str) -> Optional[str]:
    """Return normalized arXiv id (without version) if s looks like one, else None."""
    m = ARXIV_ID_RE.match(s.strip())
    if m:
        return m.group(1)
    return None


def extract_arxiv_id_from_url(url: str) -> Optional[str]:
    """
    Very simple arXiv URL parser.
    Supports e.g.:
      https://arxiv.org/abs/2101.12345
      https://arxiv.org/pdf/2101.12345.pdf
      https://arxiv.org/src/2101.12345v1
    """
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", url)
    if m:
        return m.group(1)
    return None


def fetch_arxiv_source(arxiv_id: str) -> Path:
    """
    Download arXiv source tarball to a temp dir and return path to the main .tex file.

    Strategy:
    - download https://arxiv.org/e-print/<id> (source tarball)
    - if content-type looks like PDF/HTML -> likely no source; raise
    - extract to tempdir
    - identify candidate main .tex files:
        * those containing '\\begin{document}'
        * if none, fall back to previous 'largest .tex' heuristic
    - among candidates, prefer file named <id>.tex if it exists, else
      just take the first candidate.
    """
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    tmpdir = Path(tempfile.mkdtemp(prefix=f"arxiv_{arxiv_id}_"))
    tar_path = tmpdir / "source.tar"
    print(f"[INFO] Downloading arXiv source {arxiv_id} from {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "pdf" in content_type.lower() or "html" in content_type.lower():
        raise RuntimeError(
            f"arXiv source for {arxiv_id} does not appear to be available "
            f"(Content-Type: {content_type}). Try a different paper with TeX source."
        )

    tar_path.write_bytes(resp.content)

    try:
        with tarfile.open(tar_path, "r:*") as tf:
            tf.extractall(tmpdir)
    except tarfile.ReadError as e:
        snippet = resp.content[:200].decode("latin1", errors="replace")
        raise RuntimeError(
            f"Could not open arXiv source for {arxiv_id} as a tar archive: {e}\n"
            f"First 200 bytes:\n{snippet}\n"
            f"This usually means the TeX source is not publicly available for this paper."
        ) from e

    tex_files = list(tmpdir.rglob("*.tex"))
    if not tex_files:
        raise RuntimeError(f"No .tex files found in arXiv source for {arxiv_id}")

    # Prefer .tex files that actually contain \begin{document}
    doc_candidates = []
    for p in tex_files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "\\begin{document}" in text:
            doc_candidates.append(p)

    candidates = doc_candidates if doc_candidates else tex_files

    # Prefer <id>.tex if present among candidates
    for p in candidates:
        if p.name == f"{arxiv_id}.tex":
            return p

    # Otherwise choose the largest among candidates
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]


def resolve_source_to_tex(source: str) -> Tuple[Path, str]:
    """
    Resolve an input string to a local .tex Path and a paper_id.

    Cases:
    - existing local path -> use it, paper_id = stem
    - arxiv id like '2101.12345' or 'arXiv:2101.12345' -> download
    - arxiv URL -> extract ID -> download
    """
    p = Path(source)
    if p.exists() and p.is_file():
        return p, p.stem

    # maybe arxiv id
    arxiv_id = is_arxiv_id(source)
    if not arxiv_id and source.startswith("http"):
        arxiv_id = extract_arxiv_id_from_url(source)

    if arxiv_id:
        tex_path = fetch_arxiv_source(arxiv_id)
        return tex_path, arxiv_id

    raise FileNotFoundError(f"Cannot resolve source '{source}' as local file or arXiv id/url")


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

    Layout:
      - All equations on the RIGHT side
      - All other objects on the LEFT side
      -> effectively a two-sided (almost bipartite) graph.

    Node colors:
      - theorem / lemma / proposition / corollary: shades of red/orange
      - definition: green
      - proof: purple
      - algorithm: grey
      - table: brown
      - equation: blue
      - anything else: lightgrey

    Edges:
      - directed, drawn with arrows, direction is as stored in the PaperGraph.
    """
    # 1. Ensure we have a PaperGraph object
    if isinstance(paper, PaperGraph):
        graph = paper
    else:
        p = Path(paper)
        data = json.loads(p.read_text(encoding="utf-8"))
        graph = PaperGraph.from_dict(data)

    # 2. Build networkx graph
    G = nx.DiGraph()

    # Add nodes with attributes (kind, label, name)
    for obj_id, obj in graph.objects.items():
        if include_kinds is not None and obj.kind not in include_kinds:
            continue
        G.add_node(
            obj_id,
            kind=obj.kind,
            label=getattr(obj, "label", None),
            name=getattr(obj, "name", None),
        )

    # Add edges with relation types, applying filter if needed
    for rel in graph.relations:
        if include_relation_types is not None and rel.relation_type not in include_relation_types:
            continue
        if rel.source_id in G.nodes and rel.target_id in G.nodes:
            G.add_edge(rel.source_id, rel.target_id, relation=rel.relation_type)

    # If there are no nodes, nothing to draw
    if len(G.nodes) == 0:
        print("[WARN] paper_to_network: graph has no nodes, nothing to draw.")
        return G

    # 3. Prepare labels: id / label / name
    node_labels: Dict[str, str] = {}
    for node in G.nodes:
        obj = graph.objects[node]
        if node_label_attr == "label" and getattr(obj, "label", None):
            node_labels[node] = obj.label
        elif node_label_attr == "name" and getattr(obj, "name", None):
            node_labels[node] = obj.name
        else:
            node_labels[node] = obj.id

    # 4. Compute a two-sided layout:
    #    - left side: non-equations
    #    - right side: equations only
    equation_nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == "equation"]
    other_nodes = [n for n in G.nodes if n not in equation_nodes]

    n_other = max(len(other_nodes), 1)
    n_eq = max(len(equation_nodes), 1)

    pos: Dict[str, Tuple[float, float]] = {}

    # left column x=0.0
    if len(other_nodes) == 1:
        pos[other_nodes[0]] = (0.0, 0.0)
    else:
        for i, node in enumerate(sorted(other_nodes)):
            y = 1.0 - 2.0 * i / (n_other - 1)  # spread in [-1,1]
            pos[node] = (0.0, y)

    # right column x=1.0
    if len(equation_nodes) == 1:
        pos[equation_nodes[0]] = (1.0, 0.0)
    else:
        for j, node in enumerate(sorted(equation_nodes)):
            y = 1.0 - 2.0 * j / (n_eq - 1)  # spread in [-1,1]
            pos[node] = (1.0, y)

    # 5. Colors by kind
    kind_color_map = {
        "theorem": "red",
        "lemma": "orangered",
        "proposition": "darkred",
        "corollary": "salmon",
        "definition": "green",
        "proof": "purple",
        "algorithm": "grey",
        "table": "saddlebrown",
        "equation": "royalblue",
    }

    node_colors = []
    for node, data in G.nodes(data=True):
        kind = data.get("kind")
        node_colors.append(kind_color_map.get(kind, "lightgrey"))

    # 6. Draw with matplotlib
    plt.figure(figsize=figsize)

    # Draw nodes
    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=node_colors,
        node_size=800,
    )

    # Draw directed edges with arrows
    nx.draw_networkx_edges(
        G,
        pos,
        arrows=True,
        arrowstyle="->",
        arrowsize=15,
        connectionstyle="arc3,rad=0.1",  # slight curvature so overlapping edges are visible
    )

    # Draw labels
    nx.draw_networkx_labels(
        G,
        pos,
        labels=node_labels,
        font_size=8,
    )

    plt.axis("off")

    # 7. Legend: only for kinds that actually appear
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


# ---------------------------------------------------------------------
# Command-line usage
# ---------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Parse a LaTeX file / arXiv paper and extract math objects + relations.")
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

    # summary
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

    # --- draw network and save to PNG ---
    try:
        out_png = f"{paper_id}_graph.png"
        paper_to_network(
            paper=graph,
            out_png=out_png,
            node_label_attr="id",  # or 'label' / 'name'
            include_kinds=["theorem", "lemma", "proposition", "corollary", "definition", "proof",  "equation"],
            include_relation_types=None,  # or e.g. ["used_in_proof", "uses_definition"]
        )
    except Exception as e:
        print(f"[WARN] Could not draw network: {e}")



if __name__ == "__main__":
    main()
