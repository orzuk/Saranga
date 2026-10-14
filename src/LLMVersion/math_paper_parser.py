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
import sys as _sys
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

# LaTeX syntax -- inlining \input files, cleaning, macro expansion, and which
# environments and displays exist where -- comes from the shared module
# src/latex_facts.py, the same one the LLM extraction pipeline uses. This
# parser builds its objects from those facts.
_SRC_DIR = str(Path(__file__).resolve().parent.parent)
if _SRC_DIR not in _sys.path:
    _sys.path.insert(0, _SRC_DIR)
import latex_facts  # noqa: E402

# Rule modules are loaded once per process. The parser asks for a rule module
# per node type per paper, and the generated group importer re-executes a
# group file (thousands of lines, hundreds of patterns) on every call; with
# more patterns than Python's regex cache holds, every reload also recompiled
# every pattern. Only files named distilled_rules.py are cached, and not under
# SARANGA_REGEX_REFERENCE=1 (the plain path, kept to verify the speed-ups).
_RULE_MODULES: Dict[str, Any] = {}


def _cache_rule_modules() -> None:
    import importlib.machinery as _ilm
    if os.environ.get("SARANGA_REGEX_REFERENCE", "") == "1" or \
            getattr(importlib.util.module_from_spec, "_rule_cache", False):
        return
    orig_from_spec = importlib.util.module_from_spec
    orig_exec = _ilm.SourceFileLoader.exec_module

    def key(origin):
        """The file's real location and version. The path alone is not enough:
        <type>_eval/distilled_rules.py is a symlink that points at whichever
        rule set is installed, and distillation rewrites rule files in place,
        so a path-keyed cache served the previous rule set's module."""
        try:
            st = os.stat(origin)
            return (os.path.realpath(origin), st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def module_from_spec(spec):
        origin = getattr(spec, "origin", None)
        if not (origin and origin.endswith("distilled_rules.py")):
            return orig_from_spec(spec)
        k = key(origin)
        if k is not None and k in _RULE_MODULES:
            return _RULE_MODULES[k]
        mod = orig_from_spec(spec)
        mod.__rule_key__ = k
        return mod

    def exec_module(self, module):
        k = getattr(module, "__rule_key__", None)
        if k is None:
            return orig_exec(self, module)
        if _RULE_MODULES.get(k) is module:
            return
        # compiled from source, not from __pycache__: the bytecode cache sits
        # next to the symlink and trusts the source's mtime (in seconds) and
        # size, so two rule files of equal size written in the same second
        # would share stale bytecode. Each version is compiled once anyway.
        with open(module.__spec__.origin, encoding="utf-8") as fh:
            code = compile(fh.read(), module.__spec__.origin, "exec")
        exec(code, module.__dict__)
        _RULE_MODULES[k] = module

    module_from_spec._rule_cache = True
    importlib.util.module_from_spec = module_from_spec
    _ilm.SourceFileLoader.exec_module = exec_module


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



# A \ref preceded by one of these points at a result without relying on it
# ("as in the proof of Lemma 3", "as eventually proved in Theorem 5", "unlike
# Theorem 2"); such edges are written with "mention": true. "see Lemma 3" and
# "by Lemma 3" are real uses and are NOT listed.
_MENTION_CUE = re.compile(
    r"(?:\b(?:as|just)\s+in\s+the\s+proof\s+of"
    r"|\b(?:same|similar|analogous)\s+(?:proof|argument|way|reasoning|line)\s+(?:as|to)(?:\s+in)?(?:\s+the\s+proof\s+of)?"
    r"|\b(?:similarly|analogously)\s+to(?:\s+the\s+proof\s+of)?"
    r"|\buse\s+exactly\s+the\s+proof\s+of"
    r"|\b(?:will\s+be|is|are|was|be|eventually|later)\s+(?:proved|proven|shown|established)\s+(?:later\s+)?in"
    r"|\b(?:ingredients?|step)\s+(?:of|in)\s+the\s+proof\s+of"
    r"|\bused\s+in\s+the\s+proof\s+of"
    r"|\b(?:generali[sz]es|generali[sz]ation\s+of|extends|extension\s+of|strengthens|improves(?:\s+on)?|unlike|in\s+contrast\s+(?:to|with))"
    # the PROOF of a result (its argument, a figure "Proof of Lemma 3"), or
    # its CONDITIONS ("satisfy the assumptions of Theorem 2"): neither relies
    # on the result being true
    r"|\bproofs?\s+of"
    r"|\b(?:conditions?|assumptions?|hypothes[ie]s|setting|notation|framework)\s+(?:of|in)"
    r")\s*(?:the\s+)?(?:[A-Z][a-z]+\.?|[a-z]+)?[\s~]*$",
    re.IGNORECASE)


def _ref_context(raw: str, pos: int, width: int = 90) -> str:
    """The text just before a \\ref, whitespace and ~ normalised."""
    return re.sub(r"[\s~]+", " ", raw[max(0, pos - width):pos])

class PaperParser:
    """
    Heuristic LaTeX parser for a single paper.

    Usage:
        parser = PaperParser()
        graph = parser.parse_file("paper.tex")
    """

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
            extraction_mode: str = "rules",  # 'rules', 'llm', or 'both' (LLM modes call a paid API)
            llm_model: str = "gpt-4o-mini",
            llm_chunk_chars: int = 30000,
            llm_provider: str = "openai",
            extract_inline_let: bool = False,
            custom_prompt_file: Optional[str] = None,
            structure_types: Optional[List[str]] = None,
            rules_dir: Optional[str | Path] = None,
    ):
        """
        Parameters
        ----------
        paper_id : Optional[str]
            Identifier for this paper.
        extraction_mode : {'rules', 'llm', 'both'}
            - 'rules' : only use rule-based extraction (default).
            - 'llm'   : only use LLM-based extraction.
            - 'both'  : use both and merge.
        llm_model : str
            Model name for LLM extraction (if used).
        llm_chunk_chars : int
            Max characters per chunk when calling the LLM.
        structure_types : List[str], optional
            Which structure types to extract via LLM (default: ["definition"]).
        rules_dir : str | Path, optional
            Where to look for ``<type>_eval/distilled_rules.py``. Defaults to
            this file's directory, i.e. the promoted production rules that the
            14 ``src/LLMVersion/*_eval/distilled_rules.py`` symlinks point at
            (the v6 sentence rules, extractors/rules/silver_v6__sentence_rules_haiku__2026-10).

            Pass this to run against a specific distillation's output without
            touching global state. Until it existed the ONLY way to choose a
            rule set was to repoint those symlinks, which every distillation
            run does temporarily -- so "which rules produced this result" was a
            filesystem fact at the moment of the parse rather than a property
            of the call, and a downstream job running alongside a distillation
            would silently pick up whatever was installed at that instant.
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
        self.rules_dir = Path(rules_dir) if rules_dir else Path(__file__).resolve().parent
        # Say which rules are in play, once per parser. Results differ between
        # rule sets, so a run whose logs do not record this cannot be
        # reproduced or compared against another.
        if self.extraction_mode in ("rules", "both"):
            print(f"[INFO] distilled rules: {self._describe_rules()}")
            _cache_rule_modules()


    # ------------------------------------------------------------------
    # Equations
    # ------------------------------------------------------------------

    _DISPLAY_TYPE = {"$$": ("displaymath", "dollar"), "\\[": ("bracket", "bracket")}

    def _extract_equations(self, full_text: str, containers: List[MathObject]) -> List[Equation]:
        """
        One Equation per displayed formula, numbered or not, from the facts'
        `displays` (equation environments, \\[..\\] and $$..$$). Its parent is the
        innermost container (theorem, definition, proof, ...) whose source span
        holds it; a display outside every container has no parent.
        """
        spans = []
        for obj in containers:
            start = getattr(obj, "_source_pos", None)
            if start is None:
                continue
            end = getattr(obj, "_source_end", None) or start + len(obj.raw_latex or "")
            spans.append((start, end, obj.id))
        all_eqs: List[Equation] = []
        off = self._off
        displays = [d for d in self._facts["displays"] if d["outer_start"] >= off]
        for i, d in enumerate(displays, start=1):
            o_start, o_end = d["outer_start"] - off, d["outer_end"] - off
            inside = [s for s in spans if s[0] <= o_start and o_end <= s[1]]
            parent = min(inside, key=lambda s: s[1] - s[0])[2] if inside else None
            env_name, display_type = self._DISPLAY_TYPE.get(d["env"], (d["env"], "env"))
            inner = full_text[d["start"] - off:d["end"] - off]
            eq = Equation(
                id=f"E{i}",
                kind="equation",
                index=i,
                label=d["labels"][0] if d["labels"] else None,
                name=None,
                raw_latex=full_text[o_start:o_end],
                clean_text=self._clean_latex_to_text(inner),
                env_name=env_name,
                display_type=display_type,
                parent_id=parent,
            )
            eq._source_pos = o_start
            all_eqs.append(eq)
        return all_eqs

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def parse_file(self, path: str | Path) -> PaperGraph:
        path = Path(path)
        # Per-pattern time budgets are per-document; reset them here so a
        # pattern is judged on this paper, not on the accumulated total of
        # every paper the process has seen. Quarantines are NOT reset.
        try:
            import rule_guard
            # install_global, not just guard_module. guard_module wraps only
            # module-level compiled patterns; generated rule files also call
            # re.search(pattern_string, text) directly -- 8 such calls in one
            # definition file -- and those go through re._compile, never
            # touching re.compile. Guarding only the named patterns is how a
            # runaway slipped through a guard that had been tested and shown
            # to work: the test used install_global, the parser did not.
            # This also covers the base parser's own inline patterns, which
            # are compiled inside functions and equally invisible otherwise.
            rule_guard.install_global(threshold=self.DISTILLED_RULE_TIMEOUT_S,
                                      budget=self.DISTILLED_RULE_BUDGET_S)
            rule_guard.new_document()
        except Exception as _e:
            # NOT a silent pass. This swallowed a TypeError from a wrong
            # keyword once, so the guard was never installed at all -- and the
            # only symptom was the absence of a log line, which looks exactly
            # like "no slow rules found". A guard that fails silently is worse
            # than no guard, because it is trusted.
            print(f"[WARN] rule_guard NOT installed ({type(_e).__name__}: {_e}); "
                  f"regexes run UNGUARDED and a runaway can hang this parse",
                  file=_sys.stderr, flush=True)
        # The paper as every extractor sees it (latex_facts): \input files
        # inlined, comments and disabled text removed, the paper's own macros
        # expanded; its environments and displays located once. Extraction
        # reads the document body; `self._off` maps facts offsets into it.
        self._facts = latex_facts.extract_facts(latex_facts.read_tex(str(path)))
        source = self._facts["source"]
        begin = source.find("\\begin{document}")
        self._off = begin + len("\\begin{document}") if begin != -1 else 0
        text = source[self._off:]

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

            # remark / example / assumption — the "simpleenv" group. Wired as
            # of the v5.1 60-paper distillation; until then these rules were
            # generated on every run and never applied, so ~40% of the
            # teacher's output for a typical paper was dead code that could not
            # move F1 no matter how good it was.
            #
            # Left OFF originally for a real reason, recorded here so it is not
            # rediscovered the hard way: on the ORIGINAL small distillation the
            # simpleenv rules lifted train pooled F1 by +0.063 but only +0.006
            # on held-out math and -0.002 on held-out ML — i.e. they overfit.
            # The stated condition for enabling was "re-distil them on more
            # papers first". Set APPLY_SIMPLEENV_DISTILLED = False to restore
            # the old behaviour and measure the difference on held-out data.
            if self.APPLY_SIMPLEENV_DISTILLED:
                for _stype in ("remark", "example", "assumption"):
                    _distilled = self._apply_distilled_rules(text, _stype)
                    if not _distilled:
                        continue
                    if _stype == "remark":
                        remarks = self._merge_objects(remarks, _distilled)
                    elif _stype == "example":
                        examples = self._merge_objects(examples, _distilled)
                    else:
                        assumptions = self._merge_objects(assumptions, _distilled)

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
    def _clean_latex_to_text(latex: str) -> str:
        """Best-effort LaTeX -> plain text cleaner (preserves math content)."""
        from latex_clean import clean_latex_to_text
        return clean_latex_to_text(latex)

    # ------------------------------------------------------------------
    # Environments, from latex_facts
    # ------------------------------------------------------------------

    def _extract_envs(self, text: str, kinds) -> List[Tuple[str, Optional[str], str, int, int, dict]]:
        """
        The paper's environments of the given node types ("lemma", "proof",
        "algorithm", ...), as latex_facts found and typed them: declared names,
        standard names, nesting and optional titles are all handled there.

        Returns (env_name, opt_name, body, start, end, fact); start/end index
        `text`, the document body.
        """
        off, src = self._off, self._facts["source"]
        return [(f["env"], f["optarg"], src[f["start"]:f["end"]],
                 f["outer_start"] - off, f["outer_end"] - off, f)
                for f in self._facts["facts"]
                if f["kind"] != "equation" and f["type"] in kinds and f["outer_start"] >= off
                and not f.get("duplicate_of")]       # a restated copy: the later one is kept

    def _named_envs(self, names) -> List[Tuple[str, Optional[str], str, int, int]]:
        """
        Environments by name (any case, starred or not) that are not node types:
        tables, verbatim, pseudocode. Returns (env_name, opt_name, body, start, end).
        """
        want = {n.lower().rstrip("*") for n in names}
        off, src = self._off, self._facts["source"]
        out = []
        for e in self._facts["environments"]:
            if e["env"].lower().rstrip("*") not in want or e["outer_start"] < off:
                continue
            body, opt = src[e["start"]:e["end"]], None
            m = re.match(r"\s*\[([^\]]*)\]", body)          # placement [htbp] or a title
            if m:
                opt, body = m.group(1), body[m.end():]
            out.append((e["env"], opt, body, e["outer_start"] - off, e["outer_end"] - off))
        return out

    def _fact_by_id(self, fid: str) -> dict:
        return next((f for f in self._facts["facts"] if f["id"] == fid), {})

    @staticmethod
    def _label(fact: dict) -> Optional[str]:
        """The environment's own \\label (not one of an equation inside it)."""
        return fact["labels"][0] if fact.get("labels") else None

    # ------------------------------------------------------------------
    # Theorem-like extraction (theorem / lemma / proposition / corollary /
    # claim / conjecture / problem)
    # ------------------------------------------------------------------

    def _extract_theorem_like(self, text: str) -> List[TheoremLike]:
        found = self._extract_envs(text, self.THEOREM_LIKE_KINDS)
        print(f"[DEBUG] found {len(found)} theorem-like environments")

        counters: Dict[str, int] = {k: 0 for k in self.THEOREM_LIKE_KINDS}
        objects: List[TheoremLike] = []

        for env_name, opt_name, body, source_pos, source_end, fact in found:
            kind = fact["type"]
            counters.setdefault(kind, 0)
            counters[kind] += 1
            idx = counters[kind]

            # Use STRUCTURE_TYPE_CONFIG prefix if available, else first letter
            config = STRUCTURE_TYPE_CONFIG.get(kind)
            prefix = config["id_prefix"] if config else kind[0].upper()
            obj_id = prefix + str(idx)

            label = self._label(fact)
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
            obj._source_end = source_end
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
        A. Definition environments (latex_facts type 'definition').
        B. Textual 'Definition 2.1.' style markers.
        C1. Inline 'We define X as/by/to be ...'.
        C2. Inline 'X is defined as/to be ...'.
        C3. Inline 'Let X be ...' (for things like 'Let \\phi be a p×p matrix-valued function...').
        """
        objects: List[Definition] = []
        idx = 0

        # --- A. Environment-based definitions ---
        env_defs = self._extract_envs(text, {"definition"})
        for env_name, opt_name, body, source_pos, source_end, fact in env_defs:
            idx += 1
            obj_id = f"D{idx}"
            label = self._label(fact)
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
            d._source_end = source_end
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
                           "claim", "conjecture", "problem", "proof",
                           "algorithm"}
        # (Fix-a2) Pseudocode / verbatim blocks: their "let X be ..." and
        # "... is defined as ..." lines are code, not prose definitions.
        _mask_bodies = [e[2] for e in self._extract_envs(text, _mask_env_kinds)]
        _mask_bodies += [e[2] for e in self._named_envs(
            ("algorithm", "algorithmic", "algorithmics", "algorithm2e",
             "verbatim", "lstlisting", "minted"))]
        for body in _mask_bodies:
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
            r"(?:We\s+)?\b(?:say|call)\b\s+(?:that\s+)?"  # \b stops 'reCALL'
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
            # (Fix-e) Stop the name look-back at the nearest sentence end OR
            # structural boundary, so the span never swallows preamble /
            # section headers / list markers.
            _cuts = [prefix.rfind(".")]
            for _mk in ("\n\n", "\\section", "\\subsection", "\\maketitle",
                        "\\begin", "\\end", "\\item", "\\State", "\\par", "}"):
                _p = prefix.rfind(_mk)
                if _p >= 0:
                    _cuts.append(_p + len(_mk) - 1)
            _best = max(_cuts)
            name_start = start_search + (_best + 1 if _best >= 0 else 0)
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
            ct = re.sub(r"\s+", " ", (obj.clean_text or "").strip().lower())
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
    #: Apply distilled rules for remark/example/assumption. See the note at
    #: the simpleenv block in parse_file for why this was off, and what the
    #: evidence was. Flip to False to restore pre-v5.1 behaviour.
    #: Wall-clock budget (seconds) for ONE regex match. A pattern that
    #: exceeds it is quarantined for the rest of the process and commented
    #: out at source -- see rule_guard. Per-MATCH, not per-paper, so it can
    #: be tight: a healthy pattern returns in milliseconds. 0 disables.
    DISTILLED_RULE_TIMEOUT_S = 5.0

    #: Total seconds ONE pattern may spend on ONE document across all its
    #: calls. The per-call cap misses the commoner failure -- not one
    #: catastrophic match but tens of thousands of merely-slow ones, which is
    #: what actually stalled the v5.1 run. 0 disables.
    DISTILLED_RULE_BUDGET_S = 10.0

    APPLY_SIMPLEENV_DISTILLED = True

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
        # simpleenv types have no class of their own: _extract_simple_envs
        # builds Definition objects with `kind` set to the target type.
        # Distilled results must be wrapped identically, or _merge_objects
        # would be comparing different classes for the same kind.
        'remark': 'Definition',
        'example': 'Definition',
        'assumption': 'Definition',
        'algorithm': 'Algorithm',
        'table': 'TableObject',
    }

    def _describe_rules(self) -> str:
        """Which rule set is actually in play, resolved through the symlink.

        The 14 <type>_eval/distilled_rules.py entries are normally symlinks
        into some run's snapshot, so printing the symlink path says nothing --
        every run looks identical. Resolving it names the run that produced the
        rules, which is the thing a result needs recorded against it.
        """
        probe = self.rules_dir / "definition_eval" / "distilled_rules.py"
        if not probe.exists():
            probe = self.rules_dir / "distilled_rules.py"
        if not probe.exists():
            return f"NONE (no distilled_rules.py under {self.rules_dir})"
        try:
            real = probe.resolve()
        except OSError:
            return f"{probe} (unresolvable)"
        # Count patterns where they actually live. A merged run's
        # distilled_rules.py is a combined IMPORTER that re-exports from
        # groups/<g>/distilled_rules.py and deliberately holds no patterns of
        # its own -- counting it reports 0 for every run, which reads as
        # "no rules loaded" and is the opposite of the truth.
        def _count(f):
            try:
                return sum(1 for ln in f.read_text(encoding="utf-8").splitlines()
                           if not ln.lstrip().startswith("#") and "re.compile(" in ln)
            except Exception:
                return 0
        groups = real.parent / "groups"
        units = real.parent / "unit_rules.json"
        if units.is_file():                     # sentence rules (scripts/distill_units.py)
            try:
                import json as _json
                n = sum(1 for r in _json.loads(units.read_text(encoding="utf-8")).get("rules", [])
                        if r.get("active", True))
            except Exception:
                n = 0
            where = f"{n} sentence rule(s)"
        elif groups.is_dir():
            n = sum(_count(g) for g in groups.glob("*/distilled_rules.py"))
            where = f"{n} pattern(s) across {len(list(groups.glob('*/distilled_rules.py')))} group(s)"
        else:
            n = _count(real)
            where = f"{n} pattern(s)"

        # Name the run the way a human refers to it: the snapshot under the run
        # directory, not whichever folder happens to sit under LLMVersion.
        run = real.parent.name
        if run.startswith("step_") or run == "_baseline":
            run = f"{real.parent.parent.parent.name}/{run}"
        via = " (symlink)" if probe.is_symlink() else ""
        return f"{run}{via}, {where} — {real}"

    _WARNED_MISSING: set = set()

    def _apply_distilled_rules(self, text: str, structure_type: str) -> List[MathObject]:
        """Load and apply distilled rules for a structure type if available.

        Looks for {structure_type}_eval/distilled_rules.py relative to this file's
        directory. If found, imports extract_distilled_{structure_type}(text) and
        converts returned dicts to MathObject instances.
        """
        # Two accepted layouts:
        #   <dir>/<type>_eval/distilled_rules.py  -- the production symlink tree
        #   <dir>/distilled_rules.py              -- a run/extractor directory,
        #       whose root file is the merged importer that re-exports every
        #       extract_distilled_<type> from groups/. Accepting it is what lets
        #       --rules-dir point straight at an extractor instead of requiring
        #       the 14 symlinks to be re-pointed first.
        rules_path = self.rules_dir / f"{structure_type}_eval" / "distilled_rules.py"
        if not rules_path.is_file():
            rules_path = self.rules_dir / "distilled_rules.py"

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

        # Guard every pattern this file defines. A rule that cannot finish is
        # not a rule: the first match to blow the budget disables that pattern
        # for the rest of the process and comments it out at source, so the
        # next run never loads it. Wrapping here (rather than timing the whole
        # extract_fn) is what makes the offender identifiable by name — timing
        # the composed function only tells you the group was slow, which is how
        # 26 good definition rules were once thrown away for one bad one.
        try:
            import rule_guard
            rule_guard.configure(threshold=self.DISTILLED_RULE_TIMEOUT_S,
                                 budget=self.DISTILLED_RULE_BUDGET_S)
            rule_guard.guard_module(mod, source_path=str(rules_path))
        except Exception as e:
            print(f"[WARN] rule_guard unavailable ({e}); "
                  f"distilled rules run unguarded")

        extract_fn = getattr(mod, func_name, None)
        if extract_fn is None:
            key = (str(rules_path), func_name)       # once per rule set, not once per paper
            if key not in PaperParser._WARNED_MISSING:
                PaperParser._WARNED_MISSING.add(key)
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
        # A generated rule can return anything; one malformed item must not
        # abort the whole paper's parse.
        raw_results = [r for r in raw_results if isinstance(r, dict)
                       and isinstance(r.get('raw_latex'), str) and r['raw_latex'].strip()]
        for i, item in enumerate(raw_results, 1):
            raw_latex = item['raw_latex']
            clean_text = item.get('clean_text')
            if not isinstance(clean_text, str) or not clean_text.strip():
                clean_text = self._clean_latex_to_text(raw_latex)
            name = item.get('name')
            env_name = item.get('env_name', 'distilled')

            kwargs = dict(
                # Full type name, not its first letter. `structure_type[0]`
                # collided across three families -- corollary/claim/conjecture,
                # proof/proposition/problem, algorithm/assumption -- and the
                # per-type counter restarts at 1, so the n-th distilled
                # proposition and the n-th distilled proof were both DIST_P<n>.
                # PaperGraph.add_object is `self.objects[obj.id] = obj`, so the
                # later one silently replaced the earlier: ~0.78% of objects
                # dropped, 45% of papers affected, and *which* object survived
                # varied with dict iteration order between processes.
                id=f"DIST_{structure_type.upper()}{i}",
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
            # Theorem-like distilled nodes get the same assumption/conclusion
            # split as env-extracted ones (otherwise they count as neither,
            # deflating the corpus-wide with-assumptions/with-conclusions rate).
            if cls in (TheoremLike, Conjecture, Problem):
                split_src = clean_text or self._clean_latex_to_text(raw_latex)
                assumptions, conclusions = self._split_assumptions_conclusions(split_src)
                kwargs['assumptions'] = assumptions
                kwargs['conclusions'] = conclusions
            if cls == Proof:
                kwargs['parent_id'] = None

            try:
                obj = cls(**kwargs)
            except Exception as e:
                print(f"[WARN] Could not create {class_name} from distilled rule {i}: {e}")
                continue
            # Its place in the paper, so document order (and the proof linker,
            # which reads it) does not depend on the order rules were applied:
            # without it, ties broke differently between runs.
            pos = text.find(raw_latex) if raw_latex else -1
            if pos >= 0:
                obj._source_pos = pos
                obj._source_end = pos + len(raw_latex)
            objects.append(obj)

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
            return "".join(getattr(b, "text", "") for b in message.content
                           if getattr(b, "type", "text") == "text")  # skip thinking blocks
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

        found = self._extract_envs(text, {target_kind})
        objects: List[Definition] = []

        for idx, (env_name, opt_name, body, source_pos, source_end, fact) in enumerate(found, start=1):
            label = self._label(fact)
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
            obj._source_end = source_end
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

        # 2. Per-type prompt file in repo-level prompts/ directory.
        # The official catalog of all prompts lives at <repo_root>/prompts/.
        # Path: src/LLMVersion/math_paper_parser.py -> ../../prompts/
        script_dir = Path(__file__).parent
        type_prompt = script_dir.parent.parent / "prompts" / f"{structure_type}_prompt.txt"
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

        Dedup is by clean_text, with a CONTAINMENT fallback: a distilled rule
        often re-extracts a structure the base parser already found but with a
        slightly different span (different boundary), so exact-text matching
        misses it and both copies get emitted (a duplicate). We therefore also
        drop a candidate whose token set is largely contained in (or contains)
        an already-kept same-type object. When the distilled version carries a
        name the base version lacks, backfill it.

        Containment is computed on `raw_latex` re-cleaned through THIS parser's
        cleaner, never on the stored `clean_text`. The two sides do not share a
        normalizer: env-extracted objects carry `_clean_latex_to_text` output
        (math survives as stripped words) while each distilled_rules.py ships its
        own local `_clean_latex` (math collapses to the literal token `[MATH]`,
        unknown commands are deleted). Comparing those directly drove containment
        of genuinely identical statements below the threshold, so re-extractions
        of theorems/lemmas the base parser already had survived as duplicate
        nodes -- the dominant source of distillation's apparent precision loss.
        """
        if not llm_objs:
            return manual_objs

        # Containment threshold mirrors the silver-eval matcher (0.7).
        CONTAIN_TH = 0.7

        try:                      # the scorer's own token sets (match_modes / node_similarity),
            from match_modes import tokens as _score_tokens   # so "duplicate" means what it
        except Exception:         # means when the output is scored
            _score_tokens = None

        def _tokens(o):
            src = getattr(o, "raw_latex", "") or o.clean_text or ""
            if _score_tokens is not None:
                return set(_score_tokens(src))
            return set(self._clean_latex_to_text(src).lower().split())

        seen_texts = set()
        text_to_obj = {}
        kept_tokens = []  # (token_set, obj) for every object already in `merged`
        for d in manual_objs:
            txt = (d.clean_text or "").strip().lower()
            seen_texts.add(txt)
            text_to_obj[txt] = d
            kept_tokens.append((_tokens(d), d))

        merged = list(manual_objs)
        for d in llm_objs:
            txt = (d.clean_text or "").strip().lower()
            # 1) exact-text duplicate (an empty text is not evidence of anything)
            if txt and txt in seen_texts:
                existing = text_to_obj.get(txt)
                if existing and not existing.name and d.name:
                    existing.name = d.name
                continue
            # 2) containment duplicate (same-type span overlap)
            dt = _tokens(d)
            dup_of = None
            if dt:
                for kt, ko in kept_tokens:
                    if not kt:
                        continue
                    if len(dt & kt) / min(len(dt), len(kt)) >= CONTAIN_TH:
                        dup_of = ko
                        break
            if dup_of is not None:
                if not dup_of.name and d.name:
                    dup_of.name = d.name
                continue
            # 3) genuinely new structure
            merged.append(d)
            seen_texts.add(txt)
            text_to_obj[txt] = d
            kept_tokens.append((dt, d))

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
        found = self._extract_envs(text, {"proof"})

        objects: List[Proof] = []
        idx = 0

        # If the optional proof header includes something like \ref{thm:main},
        # we want to capture that label.
        header_ref_pattern = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")

        for env_name, opt_name, body, source_pos, source_end, fact in found:
            idx += 1
            obj_id = f"R{idx}"  # Unique id for proofs; prefix doesn't matter elsewhere.

            label = self._label(fact)
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
            proof._source_end = source_end

            # The proved result where syntax states it: \begin{proof}[Proof of
            # Theorem~\ref{x}], else latex_facts' `proves` (a proof right after
            # its theorem). Stored as that theorem's label for the linker.
            if opt_name:
                m = header_ref_pattern.search(opt_name)
                if m:
                    # Not a dataclass field; just an auxiliary attribute.
                    setattr(proof, "_target_theorem_label", m.group(1))
            if getattr(proof, "_target_theorem_label", None) is None and fact.get("proves"):
                target = self._label(self._fact_by_id(fact["proves"]))
                if target:
                    setattr(proof, "_target_theorem_label", target)

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
            m_label = re.search(r"\\label\{([^}]*)\}", body)
            label = m_label.group(1).strip() if m_label else None
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
        found = self._extract_envs(text, {"algorithm"})

        objects: List[Algorithm] = []
        idx = 0

        for env_name, opt_name, body, source_pos, source_end, fact in found:
            idx += 1
            obj_id = f"A{idx}"

            label = self._label(fact)
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
            alg._source_end = source_end
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
        found = self._named_envs(["table"])

        objects: List[TableObject] = []
        idx = 0
        caption_pattern = re.compile(r"\\caption\s*{([^}]*)}", flags=re.DOTALL)

        for env_name, opt_name, body, source_pos, source_end in found:
            idx += 1
            obj_id = f"Tb{idx}"

            m_label = re.search(r"\\label\{([^}]*)\}", body)
            label = m_label.group(1).strip() if m_label else None
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
          2. For each proof, in this order:
             a) proof._target_theorem_label (from the proof header, or
                latex_facts' proof-right-after-its-theorem);
             b) adjacency: the proof is the first proof after a theorem-like
                object, with only equations / tables / distilled prose
                fragments in between;
             c) the first \\ref/\\eqref/\\autoref in the body that names a
                theorem-like object (proofs cite EARLIER results all the
                time, so this comes after adjacency);
          3. As a fallback, if still unresolved, attach the proof to the
             nearest previous theorem-like object in document order.
          A proof made by a distilled sentence rule (id DIST_*) is a prose
          fragment ("It is easy to see...", "All together, ... as proved in
          Theorem 3"): it is attached only by (a) or by adjacency with nothing
          but equations in between, and otherwise proves nothing. Attaching it
          to whatever result came last turned its references into
          dependencies of that result and closed false cycles.
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
        order = list(graph.objects.values())          # document order (sorted by _source_pos)
        skip_kinds = {"equation", "table"}
        # A gap longer than this between a result and the next proof is not
        # "right after it" (a proof deferred to a later section).
        max_gap = 2000

        def _adjacent_result(i: int, distilled: bool) -> Optional[str]:
            p = order[i]
            for j in range(i - 1, -1, -1):
                o = order[j]
                if o.kind in skip_kinds:
                    continue
                if not distilled and str(o.id).startswith("DIST_") and o.kind != "proof":
                    continue                       # a prose fragment between result and proof
                if o.kind in self.THEOREM_LIKE_KINDS:
                    end = getattr(o, "_source_end", None)
                    if end is None:
                        end = (getattr(o, "_source_pos", 0) or 0) + len(getattr(o, "raw_latex", "") or "")
                    pos = getattr(p, "_source_pos", None)
                    if pos is not None and pos - end > max_gap:
                        return None
                    return o.id
                return None                        # a definition, another proof, ...
            return None

        # --- pass 1: header label, adjacency, body ref ---
        for i, obj in enumerate(order):
            if obj.kind != "proof":
                continue
            distilled = str(obj.id).startswith("DIST_")

            parent_id: Optional[str] = getattr(obj, "parent_id", None)
            parent_source: Optional[str] = getattr(obj, "_parent_link_source", None)

            # (a) From header-based target label: proof._target_theorem_label
            if parent_id is None:
                target_label = getattr(obj, "_target_theorem_label", None)
                if target_label and target_label in label_to_theorem_id:
                    parent_id = label_to_theorem_id[target_label]
                    parent_source = "header_label"

            # (b) The first proof right after a result proves that result
            if parent_id is None:
                adj = _adjacent_result(i, distilled)
                if adj is not None:
                    parent_id, parent_source = adj, "adjacent"
            if distilled:
                if parent_id is not None:
                    setattr(obj, "parent_id", parent_id)
                    setattr(obj, "_parent_link_source", parent_source)
                    linked_count += 1
                else:
                    setattr(obj, "_no_parent", True)   # a fragment: proves nothing
                continue

            # (c) From first \ref/\eqref/\autoref in the proof body
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
            if parent_id is not None or last_thm_id is None or getattr(obj, "_no_parent", False):
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
        r"""
        Populate graph.relations with links between the extracted math objects,
        using the new relation ontology.

        We currently add:

          1. Structural edges (canonical types per schema lock):
             - proof 'proves' theorem-like (proof → theorem)
             - container 'uses' equation (equation depends on container)
             - algorithm 'resolves' problem (nearest preceding problem;
               edge problem → algorithm)
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

            key = (obj.id, parent_id, "uses")
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
        # 2c. Structural edges: algorithm 'resolves' problem
        #     Link each algorithm to the nearest preceding problem node.
        #     Canonical direction: problem (source) → algorithm (target).
        # ------------------------------------------------------------------

        resolves_count = 0
        obj_ids = list(graph.objects.keys())
        for i, obj_id in enumerate(obj_ids):
            obj = graph.objects[obj_id]
            if obj.kind != "algorithm":
                continue
            # Walk backwards to find nearest preceding problem
            for j in range(i - 1, -1, -1):
                candidate = graph.objects[obj_ids[j]]
                if candidate.kind == "problem":
                    key = (candidate.id, obj.id, "resolves")
                    if key not in existing:
                        graph.add_relation(
                            source_id=candidate.id,
                            target_id=obj.id,
                            relation_type="resolves",
                            category="structural",
                            metadata={"source": "proximity", "confidence": 0.5},
                        )
                        existing.add(key)
                        resolves_count += 1
                    break

        # ------------------------------------------------------------------
        # 2d. Structural edges: concept --illustrates--> example
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
                    key = (candidate.id, obj.id, "illustrates")    # concept -> example/exercise (edge_types)
                    if key not in existing:
                        graph.add_relation(
                            source_id=candidate.id,
                            target_id=obj.id,
                            relation_type="illustrates",
                            category="structural",
                            metadata={"source": "proximity", "confidence": 0.5},
                        )
                        existing.add(key)
                        illustrates_count += 1
                    break

        # ------------------------------------------------------------------
        # 2e. Structural edges: concept --tests--> exercise
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
                    key = (candidate.id, obj.id, "tests")    # concept -> example/exercise (edge_types)
                    if key not in existing:
                        graph.add_relation(
                            source_id=candidate.id,
                            target_id=obj.id,
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

        ref_pattern = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref)\{([^}]+)\}")
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

                key = (target_id, obj.id, "uses")
                if key in existing:
                    continue

                meta = {"ref_label": lbl, "source": "latex_ref", "confidence": 1.0}
                if _MENTION_CUE.search(_ref_context(raw, m.start())):
                    # "as in the proof of Lemma 3", "as eventually proved in
                    # Theorem 5": the text points at the result without
                    # relying on it. Kept, but not a dependency.
                    meta["mention"] = True
                graph.add_uses(user_id=obj.id, used_id=target_id, metadata=meta)
                existing.add(key)
                uses_ref_count += 1

        # ------------------------------------------------------------------
        # 4. Low-confidence 'uses' edges via TERM REUSE.
        #
        #    A node that introduces a distinctive named term -- a definition
        #    (definiendum), or a *named* theorem-like result / assumption -- is
        #    linked to any other node whose text reuses that term verbatim
        #    (term-provider -> user). Restores + generalizes the keyword-overlap
        #    heuristic removed in bf1f6ef, tightened to whole-term matches.
        #    This is the dominant *recoverable* cause of Opus edges
        #    (definition->result, definition->definition, assumption->result,
        #    result->result for named results). Edges tagged confidence=0.3 so
        #    downstream consumers (viz / eval) can filter them. The residual
        #    result->result edges with no textual trace are genuinely semantic
        #    (LLM-only) and are intentionally NOT produced here.
        # ------------------------------------------------------------------

        _STOP = {
            "the", "a", "an", "and", "or", "of", "in", "for", "to", "is",
            "are", "be", "we", "this", "that", "such", "by", "with", "let",
            "denote", "define", "definition", "where", "then", "from", "given",
        }
        # LaTeX / math artifacts and generic words too common to identify a
        # specific concept (would over-match as a lone token).
        _GENERIC = {
            "infty", "mathcal", "mathbb", "mathbf", "function", "vector",
            "matrix", "value", "values", "number", "point", "points", "space",
            "variable", "variables", "problem", "result", "results", "case",
            "set", "sets", "element", "elements", "property", "properties",
            "theorem", "lemma", "proof", "proposition", "corollary",
        }

        def _term_tokens(obj) -> list:
            # definitions carry the defined term in `definiendum`; results /
            # assumptions carry their optional name in `name`.
            if getattr(obj, "kind", None) == "definition":
                term = getattr(obj, "definiendum", None) or getattr(obj, "name", None) or ""
            else:
                term = getattr(obj, "name", None) or ""
            toks = [w for w in re.findall(r"[a-zA-Z]+", term.lower())
                    if len(w) >= 4 and w not in _STOP and w not in _GENERIC]
            # Distinctive term only: a multi-word phrase, or one long token
            # (e.g. "laplacian"). Lone short/generic tokens are dropped.
            if len(toks) == 1 and len(toks[0]) < 8:
                return []
            return toks

        term_source_kinds = {"definition", "assumption"} | self.THEOREM_LIKE_KINDS
        term_target_kinds = (
            {"definition", "proof", "algorithm", "assumption", "remark", "example"}
            | self.THEOREM_LIKE_KINDS
        )
        sources = [
            (obj.id, toks) for obj in graph.objects.values()
            if obj.kind in term_source_kinds and (toks := _term_tokens(obj))
        ]
        uses_term_count = 0
        if sources:
            for user in graph.objects.values():
                if user.kind not in term_target_kinds:
                    continue
                txt = (getattr(user, "clean_text", "")
                       or getattr(user, "raw_latex", "") or "").lower()
                if not txt:
                    continue
                user_parent = getattr(user, "parent_id", None)
                for src_id, toks in sources:
                    if src_id == user.id or user_parent == src_id:
                        # skip self and a result's own proof (already 'proves')
                        continue
                    if not all(re.search(r"\b" + re.escape(t) + r"\b", txt) for t in toks):
                        continue
                    key = (src_id, user.id, "uses")
                    if key in existing:
                        continue
                    graph.add_uses(
                        user_id=user.id,
                        used_id=src_id,
                        metadata={
                            "source": "term_reuse",
                            "confidence": 0.3,
                            "term": " ".join(toks),
                        },
                    )
                    existing.add(key)
                    uses_term_count += 1

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

        # Replace graph.relations with the accumulated ones
        graph.relations = relations + graph.relations[len(relations):]

        # ------------------------------------------------------------------
        # 5. Break remaining cycles (all lengths) across ALL edge types.
        #    The acyclicity metric (corpus_stats) is computed over the full
        #    directed graph, so a cycle may MIX a low-confidence 'uses'
        #    (term_reuse, conf 0.3) edge with a structural 'proves' /
        #    'illustrates' edge -- which a 'uses'-only breaker can never see.
        #    Repeatedly find one cycle and drop its weakest edge (lowest
        #    confidence; tie-break: source appearing latest in the document),
        #    so structural edges survive and the weak edge that closed the
        #    loop is the one cut. Runs AFTER every edge type has been added.
        # ------------------------------------------------------------------

        doc_order2 = {obj_id: i for i, obj_id in enumerate(graph.objects)}

        def _edge_confidence(rel) -> float:
            meta = getattr(rel, "metadata", {}) or {}
            c = meta.get("confidence")
            return float(c) if c is not None else 1.0

        cycle_removed = 0
        # Each pass removes >=1 edge, so the edge count bounds the iterations.
        for _ in range(len(graph.relations) + 1):
            # adjacency: source_id -> list of (target_id, index into relations)
            adj: Dict[str, List[tuple]] = {}
            for i, r in enumerate(graph.relations):
                adj.setdefault(r.source_id, []).append((r.target_id, i))

            WHITE, GRAY, BLACK = 0, 1, 2
            color: Dict[str, int] = {}
            parent_edge: Dict[str, tuple] = {}  # node -> (parent_id, rel_index)
            cycle_edge_idxs = None
            for start in list(adj.keys()):
                if color.get(start, WHITE) != WHITE:
                    continue
                stack = [(start, 0)]
                color[start] = GRAY
                while stack:
                    node, k = stack[-1]
                    nbrs = adj.get(node, [])
                    if k < len(nbrs):
                        stack[-1] = (node, k + 1)
                        nxt, ridx = nbrs[k]
                        nc = color.get(nxt, WHITE)
                        if nc == GRAY:
                            # back-edge node->nxt closes a cycle; walk parents
                            # from node up to nxt to collect the cycle's edges.
                            idxs = [ridx]
                            cur = node
                            while cur != nxt:
                                p, pidx = parent_edge[cur]
                                idxs.append(pidx)
                                cur = p
                            cycle_edge_idxs = idxs
                            break
                        elif nc == WHITE:
                            color[nxt] = GRAY
                            parent_edge[nxt] = (node, ridx)
                            stack.append((nxt, 0))
                    else:
                        color[node] = BLACK
                        stack.pop()
                if cycle_edge_idxs is not None:
                    break

            if cycle_edge_idxs is None:
                break  # graph is acyclic

            # Drop the weakest edge on the cycle: lowest confidence first,
            # then the edge whose source appears latest in the document.
            def _weakness(ri):
                r = graph.relations[ri]
                return (_edge_confidence(r), -doc_order2.get(r.source_id, 0))

            victim = min(cycle_edge_idxs, key=_weakness)
            vr = graph.relations[victim]
            existing.discard((vr.source_id, vr.target_id, vr.relation_type))
            graph.relations.pop(victim)
            cycle_removed += 1

        if cycle_removed:
            print(f"[INFO] _build_relations: broke {cycle_removed} cross-type cycle edge(s) to enforce DAG.")

        structural_total = proves_count + resolves_count + illustrates_count + tests_count
        if structural_total or equation_edge_count or uses_ref_count or uses_term_count:
            print(
                "[INFO] _build_relations: "
                f"added {proves_count} 'proves', "
                f"{resolves_count} 'resolves', "
                f"{illustrates_count} 'illustrates', "
                f"{tests_count} 'tests' edges, "
                f"{equation_edge_count} 'uses' (equation), "
                f"{uses_ref_count} 'uses' (ref), "
                f"{uses_term_count} 'uses' (term_reuse)."
            )
