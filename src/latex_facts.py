#!/usr/bin/env python3
"""LaTeX facts: what a paper's source states by syntax alone, before any judgment.

The extractor (v6, v7) has two layers. This is the first: a parser that knows LaTeX
syntax and nothing else. It reads the commands any LaTeX user would recognise
(\\newtheorem, \\begin{...}/\\end{...}, \\label, \\ref, \\cite, \\section, \\appendix)
and reports what they say: which environments exist, where their bodies start
and end, what the author named them, what number the PDF prints for them, which
section they sit in, and what they reference. The second layer, the LLM, reads
these facts and does everything syntax cannot: results stated in prose, typing
environments whose name is ambiguous, assumptions and conclusions, proof steps,
dependencies with no \\ref.

Deliberately independent of the rule-based extractor and of distillation: it
imports nothing from LLMVersion/ or extractors/, and makes no judgment beyond
mapping an author-declared environment name ("Lemma") to its node type.

Offsets refer to the PREPARED source (`facts["source"]`), produced by
`prepare_source`: comments and TeX-disabled regions removed, \\input files inlined,
the paper's argument-free macros expanded. A node's `statement` is `span_text(source, start, end)`, which applies
the extraction spec's remaining mechanical cleanup (drop \\label/\\index,
collapse whitespace).

Usage:
    python3 src/latex_facts.py paper.tex                  # summary
    python3 src/latex_facts.py paper.tex --out facts.json # full facts
"""
from __future__ import annotations

import argparse
import json
import os
import bisect
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proof_structure import detect as detect_proof_structure   # noqa: E402
from latex_macros import strip_comments, group as _group        # noqa: E402
from latex_macros import LABEL_OR_INDEX as _LABEL_OR_INDEX, REF_CMDS as _REF_CMDS   # noqa: E402

# ── Mechanical cleanup (the extraction spec's permitted edits) ──────────────

_DISABLED_ENV = re.compile(r"\\begin\s*\{comment\}.*?\\end\s*\{comment\}", re.S)
# TeX's own conditionals. Anything else starting with "if" is not one: \\iff is
# logical "if and only if", and must not be counted as an opening \\if.
_TEX_CONDITIONALS = {"if", "ifx", "ifnum", "ifdim", "ifodd", "ifcase", "ifcat",
                     "ifmmode", "ifvmode", "ifhmode", "ifinner", "ifvoid", "ifhbox",
                     "ifvbox", "ifeof", "iftrue", "iffalse", "ifdefined", "ifcsname",
                     "ifincsname", "ifpdf"}
_IF_TOKEN = re.compile(r"\\(if[a-zA-Z@]*|fi|else)(?![a-zA-Z@])")
# a conditional whose value the source fixes: \iffalse, \iftrue, \if0, \if with
# two different letters (\if False: F against a), or a \newif switch
_KNOWN_IF = re.compile(r"\\(iffalse|iftrue|if[a-zA-Z@]+)(?![a-zA-Z@])"
                       r"|\\if\s*0(?![0-9])|\\if(?![a-zA-Z@])\s*([A-Za-z0-9])([A-Za-z0-9])")
_IF_IN_DEFINITION = re.compile(
    r"(?:\\let\s*\\[A-Za-z@]+\s*=?\s*"
    r"|\\[egx]?def\s*\\[A-Za-z@]+\s*(?:#\d)*\s*\{\s*"
    r"|\\(?:re|provide)?newcommand\*?\s*\{?\\[A-Za-z@]+\}?\s*(?:\[\d\])?\s*\{\s*)\Z")


def _drop_iffalse(s: str) -> str:
    """Resolve the conditionals whose value the source fixes, as TeX would.

    \\iffalse, \\if0 and \\if with two different letters are false, \\iftrue is
    true, and a \\newif switch \\ifX has the value of the last \\Xtrue / \\Xfalse
    before it (false if none). The branch TeX skips is removed with the
    \\if, \\else and \\fi tokens; the branch it reads is kept. Nested \\if...\\fi
    are respected; conditionals of unknown value are left as written."""
    switches = set(re.findall(r"\\newif\s*\\if([a-zA-Z@]+)", s))
    conditionals = _TEX_CONDITIONALS | {"if" + x for x in switches}
    i = 0
    while True:
        m = _KNOWN_IF.search(s, i)
        if not m:
            return s
        if _IF_IN_DEFINITION.search(s[max(0, m.start() - 80):m.start()]):
            i = m.end()                      # \let\ifA\iftrue, \def\c{\iffalse}: code, not a branch
            continue
        name = m.group(1)
        if name and name not in ("iffalse", "iftrue"):
            x = name[2:]
            if x not in switches or re.search(r"\\(?:newif|let|def|global)\s*\Z",
                                              s[max(0, m.start() - 12):m.start()]):
                i = m.end()                  # an unknown conditional, or a switch's declaration
                continue
            sets = re.findall(r"\\" + re.escape(x) + r"(true|false)(?![a-zA-Z@])", s[:m.start()])
            value = bool(sets) and sets[-1] == "true"
        elif name == "iftrue":
            value = True
        elif m.group(2) and m.group(2) == m.group(3):
            i = m.end()                      # \if aa: true, but too rare to resolve
            continue
        else:
            value = False
        depth, els, fi = 1, None, None
        for t in _IF_TOKEN.finditer(s, m.end()):
            tok = t.group(1)
            if tok == "fi":
                depth -= 1
            elif tok == "else":
                if depth == 1 and els is None:
                    els = t
            elif tok in conditionals:
                depth += 1
            if depth == 0:
                fi = t
                break
        if fi is None:                       # unclosed: TeX skips to the end
            return s[:m.start()] if not value else s
        if value:
            kept = s[m.end():els.start()] if els else s[m.end():fi.start()]
        else:
            kept = s[els.end():fi.start()] if els else ""
        s = s[:m.start()] + kept + s[fi.end():]
        i = m.start()                        # the kept branch may hold more conditionals


def clean_source(tex: str) -> str:
    """Comments, \\iffalse/\\if0 regions and comment environments removed;
    text after \\end{document} dropped. Everything else, including \\label and
    whitespace, is kept so offsets stay meaningful."""
    s = strip_comments(tex)
    s = _DISABLED_ENV.sub("", s)
    s = _drop_iffalse(s)
    # The paper ends at the first \end{document} after the LAST \begin{document}:
    # LaTeX ignores everything after it (leftover sections, notes), and a source
    # can hold a stub document (\begin{document}\includepdf{..}\end{document})
    # before the real one. Cleaning a cleaned source is then a no-op.
    end = s.find("\\end{document}", max(s.rfind("\\begin{document}"), 0))
    return s[:end] if end != -1 else s


# ── Preprocessing shared by every extractor: one source, before extraction ──

_INPUT = re.compile(r"(?<!\\)\\(input|include|subfile)\s*\{([^{}#]+)\}")


def read_tex(path: str, root=None, _depth: int = 0) -> str:
    """The paper's source with every \\input / \\include / \\subfile inlined.

    Comments are removed first, so a commented-out \\input is not inlined.
    Files are looked up relative to the main file's folder (as LaTeX does) and
    then the including file's: as given, then with .tex and .txt appended. An
    unresolvable file is left as the command, so nothing is invented.
    """
    from pathlib import Path
    p = Path(path)
    root = root or p.parent
    text = strip_comments(p.read_text(encoding="utf-8", errors="replace"))
    if _depth >= 8:
        return text

    def inline(m):
        name = m.group(2).strip()
        for base in dict.fromkeys((root, p.parent)):
            for cand in (base / name, base / f"{name}.tex", base / f"{name}.txt"):
                if cand.is_file():
                    return read_tex(str(cand), root, _depth + 1)
        return m.group(0)
    return _INPUT.sub(inline, text)


_ARXIV_STEM = re.compile(r"\d{4}\.\d{4,5}(v\d+)?$|[a-z\-]+(\.[A-Z]{2})?_?\d{7}(v\d+)?$")


def find_main_tex(d, files=None):
    """The main .tex among files (default: every .tex under folder d): the one named like the
    folder (a downloader's flattened <id>.tex), else arXiv-id-named, else the one with
    \\documentclass, \\begin{document} and \\title, else the largest. None if there is none."""
    from pathlib import Path
    d = Path(d)
    def key(p):
        b = p.read_bytes()[:200000]
        active = lambda cmd: bool(re.search(rb"(?m)^[^%\n]*\\" + cmd, b))   # not in a commented-out line
        return (p.stem == d.name, bool(_ARXIV_STEM.match(p.stem)), active(rb"documentclass"),
                active(rb"begin\{document\}"), active(rb"title"), p.stat().st_size)
    return max(files or (p for p in d.rglob("*.tex") if p.is_file()), key=key, default=None)


_REF = re.compile(r"\\(?:" + _REF_CMDS + r")\*?\s*\{([^}]*)\}")
_LIST_ENVS = {"enumerate", "compactenum", "inparaenum", "itemize", "compactitem", "description",
              "asparaenum", "enumerate*"}
_REF_WITH_ARG = re.compile(r"\\(?:" + _REF_CMDS + r")\*?\s*\{[^{}]*#\d[^{}]*\}")


_HEADING = re.compile(r"\\(?:part|chapter|section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{[^{}]*#\d")


def _is_ref_wrapper(body: str) -> bool:
    """Every argument of the macro is used only inside a \\ref-like command."""
    return bool(_REF_WITH_ARG.search(body)) and "#" not in _REF_WITH_ARG.sub("", body)


def _uses_braced(source: str, name: str, arity: int) -> bool:
    """Every use of \\name (outside its definitions) takes `arity` braced
    arguments, so discarding them cannot swallow a closing brace."""
    if "@" in name:
        return False
    for m in re.finditer(r"\\" + re.escape(name) + r"(?![A-Za-z@])", source):
        before = source[max(0, m.start() - 40):m.start()]
        if re.search(r"\\(?:new|renew|provide)command\*?\s*\{?$|\\def\s*$", before):
            continue                                    # the definition itself
        j = m.end()
        for _ in range(arity):
            while j < len(source) and source[j].isspace():
                j += 1
            if j >= len(source) or source[j] != "{":
                return False
            depth = 0
            while j < len(source):
                depth += {"{": 1, "}": -1}.get(source[j], 0)
                j += 1
                if depth == 0:
                    break
    return True


def expand_macros(source: str) -> str:
    """Expand the paper's own argument-free macros, its operators, and its
    \\ref wrappers; remove their definitions.

    - \\newcommand / \\renewcommand / \\providecommand / \\def without arguments:
      each use is replaced by the body (\\gr -> \\Gamma, \\be -> \\begin{equation}).
      A macro whose body contains itself is left alone.
    - \\DeclareMathOperator{\\rank}{rank}: each \\rank becomes the operator name.
    - \\ref wrappers, macros whose arguments are used only inside \\ref-like
      commands: \\newcommand{\\eqnref}[1]{Eq.~\\eqref{#1}} turns \\eqnref{x} into
      Eq.~\\eqref{x}, \\newcommand{\\erefs}[2]{(\\ref{eq:#1}--\\ref{eq:#2})} likewise,
      so every reference is a standard \\ref the finishing step turns into an edge.
    - Macros that discard their arguments (\\newcommand{\\ignore}[1]{}): each use
      is removed with its arguments, as in the PDF.
    - Sectioning wrappers (\\newcommand{\\resection}[1]{\\setcounter{equation}{0}\\section{#1}}):
      each use is expanded, so the paper's sections are found.
    Other macros with arguments are kept as written. Reading the definitions
    and substituting them are latex_macros' (one implementation of each,
    shared with the macro glossary and the renderer). Run on the cleaned
    source (comments already removed).
    """
    from latex_macros import read_definitions, expand_macros as _expand
    defs, cut = {}, []
    for name, d in read_definitions(source, clean=False, spans=True).items():
        body = d["expansion"]
        if d["form"] == "environment" or d.get("optional_default") is not None:
            continue
        if re.search(r"\\(?:@|futurelet|expandafter|csname|afterassignment)", body):
            continue                                    # TeX internals: keep the call
        if re.search(r"\\" + re.escape(name) + r"(?![A-Za-z@])", body):
            continue                                    # self-referencing
        discard = not body.strip() and d["arity"] > 0
        if discard and not _uses_braced(source, name, d["arity"]):
            continue                                    # internal or bare-argument use: keep
        heading = d["arity"] > 0 and _HEADING.search(body) and _uses_braced(source, name, d["arity"])
        if d["arity"] == 0 or _is_ref_wrapper(body) or discard or heading:
            defs[name] = d
            cut.extend(d["spans"])           # every copy: an uncut one would be expanded
    if not defs:
        return source
    out, pos = [], 0
    for a, b in sorted(cut):
        if a >= pos:
            out.append(source[pos:a])
            pos = b
    out.append(source[pos:])
    return _expand("".join(out), defs)


def prepare_source(tex: str) -> str:
    """The single preprocessing step every extractor uses before extraction:
    clean (comments, disabled text, after \\end{document}), then expand macros.
    Idempotent, so applying it to an already prepared source changes nothing.
    Expansion repeats until stable, because expanding one macro can reveal new
    definitions (\\newcommand{\\nc}{\\newcommand} then \\nc{\\I}{\\mathbf{I}})."""
    s = _BEGIN_SPACE.sub(r"\\\1{", clean_source(tex))       # \end {equation} -> \end{equation}
    for _ in range(4):
        new = expand_macros(s)
        if new == s:
            break
        s = new
    # a label or reference key broken across lines reads as one space, as in LaTeX
    return _KEY_BREAK.sub(lambda m: m.group(1) + re.sub(r"\s*\n\s*", " ", m.group(2)) + "}", s)


_BEGIN_SPACE = re.compile(r"\\(begin|end)\s+\{")
_KEY_BREAK = re.compile(r"(\\[A-Za-z]*(?:ref|label)\*?\s*\{)([^{}]*\n[^{}]*)\}")




_AFTER_NEWLINE = re.compile(r"\*?\s*(?:\[[^\]]*\])?")   # the * and [length] of a \\ line break


def span_text(source: str, start: int, end: int) -> str:
    """The verbatim `statement` for a span: drop \\label/\\index, collapse whitespace."""
    s = _LABEL_OR_INDEX.sub("", source[start:end])
    return re.sub(r"\s+", " ", s).strip()




# ── Environment names → node types (the author's own word, not a judgment) ──

_NAME_TO_TYPE = {
    "theorem": "theorem", "lemma": "lemma", "proposition": "proposition",
    "corollary": "corollary", "claim": "claim", "fact": "claim",
    "observation": "claim", "conjecture": "conjecture", "definition": "definition",
    "definitions": "definition", "notation": "definition", "example": "example",
    "examples": "example", "exercise": "exercise", "problem": "problem",
    "open problem": "open_problem", "question": "open_problem",
    "open question": "open_problem", "remark": "remark", "remarks": "remark",
    "note": "remark", "assumption": "assumption", "assumptions": "assumption",
    "hypothesis": "assumption", "condition": "assumption", "algorithm": "algorithm",
    "proof": "proof",
}

# Environments some document classes define without a \newtheorem in the paper.
# Environment names whose meaning is standard even when no \\newtheorem in the
# source declares them (see theorem_declarations).
_UNDECLARED_STANDARD = {
    "theorem": "Theorem", "thm": "Theorem", "theo": "Theorem",
    "lemma": "Lemma", "lem": "Lemma", "proposition": "Proposition", "prop": "Proposition",
    "corollary": "Corollary", "cor": "Corollary", "claim": "Claim", "fact": "Fact",
    "observation": "Observation", "conjecture": "Conjecture", "conj": "Conjecture",
    "definition": "Definition", "defn": "Definition", "dfn": "Definition", "defi": "Definition",
    "def": "Definition", "notation": "Notation", "example": "Example", "exa": "Example",
    "exm": "Example", "exam": "Example", "ex": "Example", "exercise": "Exercise",
    "problem": "Problem", "question": "Question", "openproblem": "Open problem",
    "openquestion": "Open question", "open": "Open problem",
    "remark": "Remark", "rem": "Remark", "rmk": "Remark", "note": "Note",
    "assumption": "Assumption", "assumptions": "Assumptions", "hypothesis": "Hypothesis",
    "theor": "Theorem", "lemm": "Lemma", "propo": "Proposition", "propos": "Proposition",
    "coro": "Corollary", "corr": "Corollary", "corro": "Corollary", "corol": "Corollary",
    "defin": "Definition", "rema": "Remark", "remk": "Remark", "examp": "Example",
    "conjec": "Conjecture", "obs": "Observation", "assum": "Assumption", "assump": "Assumption",
    "hyp": "Hypothesis", "quest": "Question",
}

_CLASS_PREDEFINED = {
    "llncs": ["theorem", "lemma", "corollary", "proposition", "definition", "example",
              "exercise", "problem", "remark", "claim", "conjecture", "note",
              "property", "question", "solution", "case"],
    "svjour3": ["theorem", "lemma", "corollary", "proposition", "definition", "example",
                "exercise", "problem", "remark", "claim", "conjecture", "note",
                "property", "question", "solution", "case"],
    "svmult": ["theorem", "lemma", "corollary", "proposition", "definition", "example",
               "exercise", "problem", "remark", "claim", "conjecture", "note",
               "property", "question", "solution", "case"],
}
# classes that declare their theorem environments, sharing one counter numbered within sections:
# class -> (shared counter, {env: printed name})
_CLASS_NAMED = {"acmart": ("theorem", {e: e.capitalize() for e in ("theorem", "conjecture", "proposition", "lemma",
                                                                      "corollary", "example", "definition")}),
                "lmcs": ("thm", {"thm": "Theorem", "cor": "Corollary", "lem": "Lemma", "prop": "Proposition", "defi": "Definition",
                         "conj": "Conjecture", "exa": "Example", "rem": "Remark", "asm": "Assumption", "prob": "Problem",
                         "oprob": "Open Problem", "nota": "Notation", "fact": "Fact", "clm": "Claim", "obs": "Observation",
                         "conv": "Convention", "qu": "Question", "defis": "Definitions", "rems": "Remarks", "exas": "Examples"})}

_ALGORITHM_ENVS = {"algorithm", "algorithm*", "algorithm2e", "algorithm2e*", "algorithmic", "procedure", "function"}
_EQUATION_ENVS = {"equation", "multline", "align", "gather", "eqnarray", "flalign", "alignat",
                  "numcases", "subnumcases"}


# Titles that name a node type without being one of the standard names, as
# papers use them (the type each received in the silver corpus).
_TITLE_SYNONYMS = {
    "statement": "proposition", "result": "theorem", "comment": "remark",
    "interpretation": "remark", "reformulation": "remark", "reduction rule": "algorithm",
    "variant": "definition", "setup": "assumption", "convention": "definition",
    "construction": "definition", "property": "claim", "procedure": "algorithm",
}
# A type word inside a longer title: "Hahn-Banach Theorem", "Theorem A", "Lemma B1",
# "Definition/Remark" (the first type word decides).
_TITLE_WORDS = {
    "theorem": "theorem", "theorems": "theorem", "lemma": "lemma", "lemmas": "lemma",
    "lemmata": "lemma", "proposition": "proposition", "propositions": "proposition",
    "corollary": "corollary", "corollaries": "corollary", "claim": "claim",
    "fact": "claim", "observation": "claim", "conjecture": "conjecture",
    "definition": "definition", "definitions": "definition", "notation": "definition",
    "example": "example", "examples": "example", "exercise": "exercise",
    "question": "open_problem", "remark": "remark", "remarks": "remark", "note": "remark",
    "assumption": "assumption", "assumptions": "assumption", "hypothesis": "assumption",
    "algorithm": "algorithm", "problem": "problem",
}


def _title_words(display: str) -> str:
    """A printed title as plain lower-case words: "\\it \\bf{Remark}\\/" -> "remark"."""
    d = re.sub(r"\\[a-zA-Z]+\s*", " ", display)
    return re.sub(r"[^a-z]+", " ", d.lower()).strip()


def _name_to_type(display: str | None) -> str | None:
    """A node type from an environment's printed title: an exact standard name,
    a known synonym, or else the first type word in the title."""
    if not display:
        return None
    d = re.sub(r"\\[a-zA-Z]+\s*", "", display)      # "\bf Theorem" -> "Theorem"
    d = re.sub(r"[{}]", "", d).strip().lower()
    if d in _NAME_TO_TYPE:
        return _NAME_TO_TYPE[d]
    words = _title_words(display)
    if words in _NAME_TO_TYPE:
        return _NAME_TO_TYPE[words]
    if words in _TITLE_SYNONYMS:
        return _TITLE_SYNONYMS[words]
    for w in words.split():
        if w in _TITLE_WORDS:
            return _TITLE_WORDS[w]
    return None


# Environments that are not mathematical content: never a fact.
_IGNORED_TITLE = re.compile(r"acknowledg|thanks|funding|dedicat|data availability|"
                            r"author contributions?|competing interests?|conflicts? of interest|"
                            r"keywords")


def _is_proof_env(env: str, decl: dict) -> bool:
    """proof, proof*, and the papers' own proof environments (proofs, scproof,
    a \\newtheorem{Proof}{Proof}): named like a proof, or titled "Proof"."""
    if re.fullmatch(r"[A-Za-z]*(?:proof|Proof|PROOF)s?(?:of|Of)?\*?", env):
        return True
    if re.fullmatch(r"(?:proof|Proof)(?:outline|Outline|sketch|Sketch|idea|Idea)\*?", env):
        return True
    if env.rstrip("*").lower() in ("pf", "prf", "demo", "dem", "demostracion", "preuve",
                                   "beweis", "dimostrazione", "proofof"):
        return True
    # a name with spaces: \newenvironment{Proof of lemma}{...}{...}
    if re.fullmatch(r"(?:proof|proofs)(?:\s+of)?(?:\s+[a-z]+)*", env.rstrip("*").lower()):
        return True
    d = decl.get(env)
    if not d or not d["display"]:
        return False
    shown = re.sub(r"[{}]", "", re.sub(r"\\[a-zA-Z]+\s*", "", d["display"])).strip()
    return _name_to_type(d["display"]) == "proof" or bool(re.match(r"Proofs?\b", shown))


def theorem_declarations(source: str) -> dict[str, dict]:
    """env name -> {display, counter, within, starred} from the preamble and class."""
    decl: dict[str, dict] = {}
    m = re.search(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", source)
    cls = m.group(1).strip() if m else ""
    for env in _CLASS_PREDEFINED.get(cls, []):
        decl[env] = {"display": env.capitalize(), "counter": None, "within": None,
                     "starred": False, "source": f"class:{cls}"}
    ctr, named = _CLASS_NAMED.get(cls.lower(), ("", {}))
    for env, display in named.items():
        decl[env] = {"display": display, "counter": ctr, "within": "section", "starred": False,
                     "source": f"{cls}.cls"}                  # numbering known: replayed
    for m in re.finditer(r"\\(?:sp)?newtheorem(\*?)", source):
        starred = bool(m.group(1))
        env, j = _group(source, m.end())
        if env is None:
            continue
        shared, j2 = _group(source, j, "[", "]")
        j = j2 if shared is not None else j
        display, j = _group(source, j)
        if display is None:
            continue
        within, _ = _group(source, j, "[", "]")
        env = env.strip()
        decl[env] = {"display": display.strip(),
                     "counter": None if starred else (shared.strip() if shared else env),
                     "within": within.strip() if within else None,
                     "starred": starred, "source": "newtheorem"}
    for m in re.finditer(r"\\declaretheorem\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}", source):
        opts, env = m.group(1) or "", m.group(2).strip()
        name = re.search(r"name\s*=\s*\{?([^,}\]]+)", opts)
        sibling = re.search(r"(?:sibling|sharenumber)\s*=\s*([^,\]]+)", opts)
        within = re.search(r"(?:parent|numberwithin)\s*=\s*([^,\]]+)", opts)
        starred = "numbered=no" in opts.replace(" ", "")
        decl[env] = {"display": name.group(1).strip() if name else env.capitalize(),
                     "counter": None if starred else (sibling.group(1).strip() if sibling else env),
                     "within": within.group(1).strip() if within else None,
                     "starred": starred, "source": "declaretheorem"}
    for m in re.finditer(r"\\newproof\s*\{([^}]*)\}\s*\{([^}]*)\}", source):   # elsarticle
        decl.setdefault(m.group(1).strip(), {"display": m.group(2).strip(), "counter": None,
                                             "within": None, "starred": True,
                                             "source": "newproof"})
    # Wrapper environments: \newenvironment{remark}{\begin{rmk}\em}{\end{rmk}} is
    # the theorem environment it opens, under another name (same counter and title).
    # An environment whose opening code prints a "Proof" heading is a proof
    # environment: \newenvironment{prf}{\noindent{\bf Proof.}}{\hfill$\Box$}.
    for m in re.finditer(r"\\(?:re)?newenvironment\*?\s*\{([^}]+)\}", source):
        name, j = m.group(1).strip(), m.end()
        for _opt in range(2):
            o, j2 = _group(source, j, "[", "]")
            if o is None:
                break
            j = j2
        begin_code, _ = _group(source, j)
        shown = re.sub(r"\\[a-zA-Z]+\*?|[{}\[\]$]|\d+(?:pt|mm|em|ex)", " ", begin_code or "")
        if name not in decl and re.match(r"\s*Proof\b", shown):
            decl[name] = {"display": "Proof", "counter": None, "within": None,
                          "starred": True, "source": "newenvironment"}
    for _ in range(2):                    # twice, for a wrapper of a wrapper
        for m in re.finditer(r"\\(?:re)?newenvironment\*?\s*\{([^}]+)\}", source):
            name, j = m.group(1).strip(), m.end()
            for _opt in range(2):         # [nargs][default]
                o, j2 = _group(source, j, "[", "]")
                if o is None:
                    break
                j = j2
            begin_code, _ = _group(source, j)
            inner = re.match(r"\s*\\begin\s*\{([^}]+)\}", begin_code or "")
            if inner and inner.group(1).strip() in decl and name not in decl:
                decl[name] = dict(decl[inner.group(1).strip()],
                                  source=f"wrapper:{inner.group(1).strip()}")
    # A standard name the paper uses but never declares is defined by a class or
    # package we do not see (a journal class such as arxbj, a missing .sty):
    # it is still that environment. Its numbering is unknown.
    for m in re.finditer(r"\\begin\s*\{([A-Za-z]+)(\*?)\}", source):
        env, star = m.group(1) + m.group(2), m.group(2)
        display = _UNDECLARED_STANDARD.get(m.group(1).lower())
        if display and env not in decl:
            decl[env] = {"display": display, "counter": None, "within": None,
                         "starred": bool(star), "source": "undeclared"}
    # Counters numbered within another theorem's counter inherit its `within`.
    for env, d in decl.items():
        c = d["counter"]
        if c and c != env and c in decl and d["within"] is None:
            d["within"] = decl[c]["within"]
    return decl


# ── Shorthand macros for environments (\be ... \ee, \Eq{...}) ───────────────

def env_aliases(source: str) -> tuple[dict, dict, dict, dict]:
    """Macros whose whole body is \\begin{X}, \\end{X}, or \\begin{X}#1\\end{X}.

    Returns (begin_alias, end_alias, wrap_alias, nonumber_alias): macro name ->
    environment (or, for the last, -> \\nonumber).
    Only these exact shapes are recognised; any other macro is left alone.
    """
    begin, end, wrap, nonum = {}, {}, {}, {}
    pat = re.compile(r"\\(?:re)?newcommand\*?\s*\{?\\([a-zA-Z]+)\}?\s*(\[\d\])?\s*\{"
                     r"|\\def\s*\\([a-zA-Z]+)\s*(#1)?\s*\{")
    for m in pat.finditer(source):
        name = m.group(1) or m.group(3)
        nargs = m.group(2) or m.group(4)
        body, _ = _group(source, m.end() - 1)
        if body is None:
            continue
        b = body.strip()
        mb = re.fullmatch(r"\\begin\s*\{([^}]+)\}", b)
        me = re.fullmatch(r"\\end\s*\{([^}]+)\}", b)
        mw = re.fullmatch(r"\\begin\s*\{([^}]+)\}\s*#1\s*\\end\s*\{\1\}", b)
        if mw and nargs:
            wrap[name] = mw.group(1)
        elif mb and not nargs:
            begin[name] = mb.group(1)
        elif me and not nargs:
            end[name] = me.group(1)
        elif re.fullmatch(r"\\(?:nonumber|notag)", b) and not nargs:
            nonum[name] = b
    return begin, end, wrap, nonum


def label_ref_aliases(source: str) -> tuple[dict, dict]:
    """One-argument macros that set a label or make a reference, e.g.
    \\newcommand{\\enum}[1]{\\label{#1}} or \\newcommand{\\eref}[1]{(\\ref{#1})}.
    Returns (label_aliases, ref_aliases): macro name -> key template ("eq:#1")."""
    lab, ref = {}, {}
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\([a-zA-Z]+)\}?\s*\[1\]\s*\{"
                         r"|\\def\s*\\([a-zA-Z]+)\s*#1\s*\{", source):
        name = m.group(1) or m.group(2)
        body, _ = _group(source, m.end() - 1)
        if body is None:
            continue
        ml = re.search(r"\\label\s*\{([^{}]*#1[^{}]*)\}", body)
        mr = re.search(r"\\(?:eq)?ref\s*\{([^{}]*#1[^{}]*)\}", body)
        if ml:
            lab[name] = ml.group(1).strip()          # key template, e.g. "eq:#1"
        elif mr:
            ref[name] = mr.group(1).strip()
    return lab, ref


# ── Main pass ───────────────────────────────────────────────────────────────

_SEC_LEVEL = {"part": -1, "chapter": 0, "section": 1, "subsection": 2, "subsubsection": 3}
_MULTILINE_EQ = _EQUATION_ENVS - {"equation", "multline"}
_ALG_LINE_CMD = (r"STATE|State|IF|If|ELSIF|ElsIf|ELSE|Else|ENDIF|EndIf|FOR|For|FORALL|ForAll|"
                 r"ENDFOR|EndFor|WHILE|While|ENDWHILE|EndWhile|REPEAT|Repeat|UNTIL|Until|"
                 r"LOOP|Loop|ENDLOOP|EndLoop|RETURN|Function|Procedure")


def _token_regex(aliases: set[str]) -> re.Pattern:
    alias = (r"|\\(?P<alias>" + "|".join(sorted(map(re.escape, aliases), key=len, reverse=True))
             + r")(?![a-zA-Z])") if aliases else ""
    return re.compile(
        r"\\(?P<sec>part|chapter|section|subsection|subsubsection)(?P<sstar>\*?)(?![a-zA-Z])"
        r"|\\(?P<appendix>appendix)(?![a-zA-Z])"
        r"|\\begin\s*\{(?P<begin>[^}]+)\}"
        r"|\\end\s*\{(?P<end>[^}]+)\}"
        r"|\\label\s*\{(?P<label>[^}]*)\}"
        r"|\\(?P<refcmd>" + _REF_CMDS + r")\*?\s*\{(?P<ref>[^}]*)\}"
        r"|\\(?P<citecmd>cite[a-zA-Z]*)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{(?P<cite>[^}]*)\}"
        r"|\\(?P<item>item)(?![a-zA-Z])"
        r"|\\(?P<caption>caption)(?![a-zA-Z])"
        r"|\\(?P<nonumber>nonumber|notag)(?![a-zA-Z])"
        r"|(?P<newline>\\\\)"
        r"|\\(?P<algline>" + _ALG_LINE_CMD + r")(?![a-zA-Z])"
        + alias)


def _brace_depth(s: str, start: int, end: int) -> int:
    """Unescaped { minus } in s[start:end]: a \\\\ inside \\substack{...} is not a line break."""
    seg = re.sub(r"\\.", "", s[start:end])   # drop escaped chars: \{ \} \\
    return seg.count("{") - seg.count("}")


_STYLE = {"arabic": str, "Alph": lambda n: _alph(n), "alph": lambda n: _alph(n).lower(),
          "Roman": lambda n: _roman(n), "roman": lambda n: _roman(n).lower()}


def _roman(n: int) -> str:
    out = ""
    for v, r in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                 (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + r, n - v
    return out


def counter_formats(source: str, counters: set[str]) -> tuple[dict, dict, set]:
    r"""How the paper prints and resets its counters, where it says so explicitly.

    Returns (formats, resets, unknown):
      formats  counter -> list of parts: ("sec",) | ("lit", text) | ("ctr", style)
               from \renewcommand{\theX}{...} or \def\theX{...}
      resets   counter -> "section" from \@addtoreset / \counterwithin / \numberwithin
      unknown  counters whose numbering we cannot replay: set or advanced by hand,
               defined more than once, or printed by a format we do not parse.
    Numbers for an unknown counter are reported as null, never guessed.
    """
    formats, resets, unknown = {}, {}, set()
    defs: dict[str, list[str]] = {}
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\the([a-zA-Z]+)\}?\s*\{"
                         r"|\\def\s*\\the([a-zA-Z]+)\s*\{", source):
        ctr = m.group(1) or m.group(2)
        if ctr not in counters:
            continue                       # \theta, \therefore, ...
        body, _ = _group(source, m.end() - 1)
        if body is not None:
            defs.setdefault(ctr, []).append(body)
    for ctr, bodies in defs.items():
        if len(set(b.strip() for b in bodies)) > 1:
            unknown.add(ctr)
            continue
        parts, rest = [], bodies[0].strip()
        while rest:
            m = (re.match(r"\\thesection", rest) or re.match(r"\\arabic\s*\{section\}", rest))
            if m:
                parts.append(("sec",))
            elif (m := re.match(r"\\thechapter|\\arabic\s*\{chapter\}", rest)):
                parts.append(("chap",))
            elif (m := re.match(r"\\(arabic|Alph|alph|Roman|roman)\s*\{" + re.escape(ctr) + r"\}", rest)):
                parts.append(("ctr", m.group(1)))
            elif (m := re.match(r"[0-9A-Za-z.\-]+", rest)):
                parts.append(("lit", m.group(0)))
            else:
                unknown.add(ctr)
                break
            rest = rest[m.end():].lstrip()
        else:
            formats[ctr] = parts
    for m in re.finditer(r"\\@addtoreset\s*\{([^}]*)\}\s*\{([^}]*)\}"
                         r"|\\counterwithin\*?\s*\{([^}]*)\}\s*\{([^}]*)\}"
                         r"|\\numberwithin\s*\{([^}]*)\}\s*\{([^}]*)\}", source):
        ctr = (m.group(1) or m.group(3) or m.group(5)).strip()
        within = (m.group(2) or m.group(4) or m.group(6)).strip()
        resets[ctr] = within
        star = m.group(0).startswith("\\counterwithin*") or m.group(0).startswith("\\@addtoreset")
        if m.group(5) or (m.group(3) and not star):
            formats.setdefault(ctr, [({"section": "sec", "chapter": "chap"}[within],), ("lit", "."),
                                     ("ctr", "arabic")]) if within in ("section", "chapter") else unknown.add(ctr)
    # \setcounter{equation}{0} next to every \section is the old way to number within sections
    by_hand: dict[str, list[bool]] = {}
    for m in re.finditer(r"\\(?:setcounter|addtocounter|stepcounter|refstepcounter)\s*\{([^}]*)\}",
                         source):
        ctr = m.group(1).strip()
        if ctr in counters:
            zero = re.match(r"\s*\{\s*0\s*\}", source[m.end():])
            near = zero and (re.match(r"\s*\\section(?![a-zA-Z*])", source[m.end() + zero.end():])
                             or re.search(r"\\section\s*\{[^{}]*\}\s*$", source[max(0, m.start() - 300):m.start()]))
            by_hand.setdefault(ctr, []).append(bool(near) and m.group(0).startswith("\\setcounter"))
    for ctr, at_sections in by_hand.items():
        if all(at_sections) and ctr not in resets:
            resets[ctr] = "section"
        else:
            unknown.add(ctr)
    return formats, resets, unknown


def _alph(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def extract_facts(tex: str) -> dict:
    """Facts about a paper's LaTeX source. See the module docstring."""
    source = prepare_source(tex)
    decl = theorem_declarations(source)
    a_begin, a_end, a_wrap, a_nonum = env_aliases(source)
    body_start = source.find("\\begin{document}")
    body_start = body_start if body_start != -1 else 0

    # Events in document order: the tokenizer's matches, plus the synthetic
    # \end that a wrapper macro (\Eq{...}) implies at its closing brace.
    events = []
    a_label, a_ref = label_ref_aliases(source)
    aliases = set(a_begin) | set(a_end) | set(a_wrap) | set(a_nonum) | set(a_label) | set(a_ref)
    for m in _token_regex(aliases).finditer(source, body_start):
        if m.groupdict().get("alias"):
            name = m.group("alias")
            if name in a_wrap:
                arg_start = source.find("{", m.end())
                _, close = _group(source, m.end())
                events.append((m.start(), "begin", a_wrap[name], arg_start + 1, m))
                events.append((close - 1, "end", a_wrap[name], close, m))
            elif name in a_begin:
                events.append((m.start(), "begin", a_begin[name], m.end(), m))
            elif name in a_nonum:
                events.append((m.start(), "nonumber", None, m.end(), m))
            elif name in a_label or name in a_ref:
                arg, close = _group(source, m.end())
                if arg is not None:
                    tmpl = a_label.get(name) or a_ref.get(name)
                    events.append((m.start(), "labelx" if name in a_label else "refx",
                                   tmpl.replace("#1", arg.strip()), close, m))
            else:
                events.append((m.start(), "end", a_end[name], m.end(), m))
        elif m.group("begin"):
            events.append((m.start(), "begin", m.group("begin").strip(), m.end(), m))
        elif m.group("end"):
            events.append((m.start(), "end", m.group("end").strip(), m.end(), m))
        else:
            events.append((m.start(), "tok", None, m.end(), m))
    events.sort(key=lambda e: e[0])
    # \(re)newenvironment definitions written in the body hold \begin/\end
    # fragments that are formatting code, not content.
    defs = _newenvironment_spans(source, body_start)
    if defs:
        events = [e for e in events if not any(a <= e[0] < b for a, b in defs)]

    facts: list[dict] = []
    sections: list[dict] = []
    labels: dict[str, dict] = {}
    refs: list[dict] = []
    cites: list[dict] = []

    sec_ctr = {0: 0, 1: 0, 2: 0, 3: 0}
    in_appendix = False
    # a book or report: chapters are numbered, sections are chapter.section, and the
    # class numbers equations within chapters
    chaptered = re.search(r"\\chapter\*?\s*[\[{]", source[body_start:]) is not None
    thm_ctr: dict[str, int] = {}
    thm_counters = {d["counter"] for d in decl.values() if d["counter"]}
    formats, resets, unknown = counter_formats(     # before expansion, which consumes \renewcommand{\theX}
        clean_source(tex), thm_counters | {"equation", "section", "subsection", "subsubsection"})
    if chaptered and "equation" not in formats and "equation" not in unknown:
        formats["equation"] = [("chap",), ("lit", "."), ("ctr", "arabic")]
        resets.setdefault("equation", "chapter")
    for env, d in decl.items():          # a theorem counter's reset/format, from its declaration
        c = d["counter"]
        if c and d["within"] and c not in resets:
            resets[c] = d["within"]
    eq_ctr = 0
    sub_eq: str | None = None            # number of an open subequations block
    sub_ctr = 0                          # its lines: (sub_eq)a, (sub_eq)b, ...
    just_closed: tuple | None = None     # (fact, end offset): a \label right after \end{env} is its

    stack: list[dict] = []               # open captured environments (facts)
    open_envs: list[str] = []            # every open environment
    open_spans: list[tuple[int, int]] = []    # (\begin offset, body start), parallel to open_envs
    environments: list[dict] = []        # the span of every environment, whatever its name
    # LaTeX's \label refers to the last \refstepcounter in the current group;
    # \begin opens a group, \end restores the target the group started with.
    target: dict | None = None
    group_targets: list = []
    line_labels: list[str] = []          # labels waiting for a multi-line equation's line number
    line_nonumber = False

    def sec_number(level: int) -> str:
        # the appendix letters the top level (its sections, when no \chapter follows it)
        first = 0 if chaptered and not (in_appendix and sec_ctr[0] == 0) else 1
        top = _alph(sec_ctr[first]) if in_appendix else str(sec_ctr[first])
        return ".".join([top] + [str(sec_ctr[k]) for k in range(first + 1, level + 1)])

    def render(ctr: str, n: int, default_within: str | None) -> str | None:
        if ctr in unknown:
            return None
        parts = formats.get(ctr)
        if parts is None:
            if default_within in _SEC_LEVEL and _SEC_LEVEL[default_within] >= 0:
                return f"{sec_number(_SEC_LEVEL[default_within])}.{n}"
            return str(n) if default_within is None else None
        out = ""
        for p in parts:
            out += (sec_number(1) if p[0] == "sec" else sec_number(0) if p[0] == "chap"
                    else p[1] if p[0] == "lit" else _STYLE[p[1]](n))
        return out

    def eq_number() -> str | None:
        nonlocal eq_ctr
        eq_ctr += 1
        return render("equation", eq_ctr, None)

    def enclosing() -> str | None:
        for f in reversed(stack):
            if f["kind"] != "equation":
                return f["id"]
        return None

    def add_label(key: str, kind: str, id_: str | None, number: str | None):
        labels.setdefault(key, {"kind": kind, "id": id_, "number": number,
                                "enclosing": enclosing()})
        if id_:
            obj = next((f for f in reversed(stack) if f["id"] == id_), None)
            if obj is not None:
                obj["labels"].append(key)
            for s in sections:
                if s["id"] == id_:
                    s["labels"].append(key)

    def close_eq_line(fact: dict, pos: int, final: bool = False):
        nonlocal line_labels, line_nonumber, sub_ctr
        row = {"start": fact.get("_line_start", fact["start"]), "end": pos, "number": None, "labels": []}
        fact.setdefault("_rows", []).append(row)   # for _split_rows
        numbered = not fact["env"].endswith("*") and not line_nonumber
        if numbered:
            fact["printed"] = True            # LaTeX prints a number, computable or not
        if numbered and sub_eq is not None:
            sub_ctr += 1
            num = f"{sub_eq}{_alph(sub_ctr).lower()}"
        else:
            num = eq_number() if numbered else None
        if not numbered and not fact["env"].endswith("*") and not final:
            line_nonumber = False             # amsmath: a \label on a \notag line
            return                            # takes the next numbered line's number
        for key in line_labels:
            add_label(key, "equation", fact["id"], num)
        row["number"], row["labels"] = num, list(line_labels)
        if num and fact["number"] is None:
            fact["number"] = num
        line_labels, line_nonumber = [], False

    def handle_label(key: str, pos: int | None = None):
        if (pos is not None and just_closed is not None
                and not source[just_closed[1]:pos].strip()):
            f = just_closed[0]                # \end{lemma}\label{...}: the lemma's label
            labels.setdefault(key, {"kind": "env", "id": f["id"], "number": f["number"],
                                    "enclosing": f["parent"]})
            f["labels"].append(key)
            return
        top = stack[-1] if stack else None
        if top and top["kind"] == "equation":
            line_labels.append(key)
        elif target is not None:
            add_label(key, target["kind"], target["id"], target["number"])
        else:
            add_label(key, "unknown", None, None)
        if pos is not None and key in labels:
            labels[key].setdefault("offset", pos)

    def handle_ref(key: str, cmd: str, pos: int):   # "a,b" is split after the walk
        r = {"cmd": cmd, "key": key.strip(), "offset": pos, "in": stack[-1]["id"] if stack else None}
        refs.append(r)
        for f in stack:
            f["refs"].append(r["key"])

    def heading(level: int, starred: bool, k: int, pos: int):
        """A sectioning command at `pos`; its [short] and {title} arguments start at `k`."""
        nonlocal eq_ctr, target
        short, k2 = _group(source, k, "[", "]")          # \subsection[short]{long}
        if short is not None:
            k = k2
        title, _ = _group(source, k)
        if title is None or "#" in title:              # no title, or a macro's body
            return
        number = None
        if not starred and level >= (0 if chaptered else 1):
            sec_ctr[level] += 1
            for lv in range(level + 1, 4):
                sec_ctr[lv] = 0
            names = {0: "chapter", 1: "section", 2: "subsection", 3: "subsubsection"}
            reset_by = {names[lv] for lv in range(level, 4)}
            for c, within in resets.items():
                if within in reset_by:
                    if c == "equation":
                        eq_ctr = 0
                    else:
                        thm_ctr[c] = 0
            top = "chapter" if chaptered else "section"
            number = None if names[level] in unknown or top in unknown else sec_number(level)
        sec = {"id": f"S{len(sections) + 1}", "level": level,
               "title": re.sub(r"\s+", " ", _LABEL_OR_INDEX.sub("", title)).strip(),
               "number": number, "start": pos, "labels": []}
        sections.append(sec)
        target = {"kind": "section", "id": sec["id"], "number": number}

    for pos, ev, env, after, m in events:
        if ev == "begin" and env == "appendix":     # \begin{appendix} acts like \appendix
            open_envs.append(env)
            open_spans.append((pos, after))
            group_targets.append(target)
            in_appendix = True
            sec_ctr.update({0: 0, 1: 0, 2: 0, 3: 0} if chaptered else {1: 0, 2: 0, 3: 0})
            continue
        if ev == "begin":
            open_envs.append(env)
            open_spans.append((pos, after))
            group_targets.append(target)
            base = env.rstrip("*")
            if base in ("section", "subsection", "subsubsection"):   # \begin{section}{Title}
                heading(_SEC_LEVEL[base], env.endswith("*"), after, pos)
                continue
            if base == "subequations":
                sub_eq = eq_number()
                sub_ctr = 0
                target = {"kind": "equation", "id": None, "number": sub_eq}
                continue
            kind_env = env                       # the environment that decides the kind
            j = after
            opt = None
            if base == "restatable":             # thmtools: [title]{theorem}{\macroname}
                o, j2 = _group(source, j, "[", "]")
                inner, j3 = _group(source, j2 if o is not None else j)
                name_arg, j4 = _group(source, j3) if inner is not None else (None, j)
                if inner is None or name_arg is None:
                    continue
                opt, kind_env, j = o, inner.strip(), j4
            is_proof = _is_proof_env(kind_env, decl)
            captured = (kind_env in decl or is_proof or kind_env in _ALGORITHM_ENVS
                        or kind_env.rstrip("*") in _EQUATION_ENVS)
            if captured and kind_env in decl and _IGNORED_TITLE.search(
                    _title_words(decl[kind_env]["display"] or "") + " " + kind_env.lower()):
                captured = False                      # acknowledgements and the like
            if not captured:
                continue
            if base not in _EQUATION_ENVS and base not in ("algorithmic", "restatable"):
                o, j2 = _group(source, j, "[", "]")
                if o is not None:
                    opt, j = o, j2
            d = decl.get(kind_env)
            number = None
            if d and d["counter"]:
                thm_ctr[d["counter"]] = thm_ctr.get(d["counter"], 0) + 1
                n = thm_ctr[d["counter"]]
                if d["source"].startswith("class:"):
                    number = None                       # class numbering not replayed
                else:
                    number = render(d["counter"], n, d["within"])
            if is_proof:
                kind, ntype, display = "proof", "proof", "Proof"
            elif kind_env in _ALGORITHM_ENVS:
                kind, ntype, display = "algorithm", "algorithm", "Algorithm"
            elif kind_env.rstrip("*") in _EQUATION_ENVS:
                kind, ntype, display = "equation", "equation", None
            else:
                kind, display = "theorem_env", d["display"]
                ntype = _name_to_type(display) or (
                    None if (display or "").strip() else _name_to_type(
                        _UNDECLARED_STANDARD.get(kind_env.rstrip("*").lower(), "")))
            fact = {"id": f"F{len(facts) + 1}", "kind": kind, "env": env,
                    "display": display, "type": ntype, "optarg": opt, "number": number,
                    "labels": [], "refs": [], "cites": [],
                    "section": sections[-1]["id"] if sections else None,
                    "outer_start": pos, "start": j, "end": None, "outer_end": None,
                    "parent": stack[-1]["id"] if stack else None}
            facts.append(fact)
            stack.append(fact)
            if kind == "theorem_env":
                target = {"kind": "env", "id": fact["id"], "number": number}
            elif kind == "algorithm" and env != "algorithmic":
                target = {"kind": "env", "id": fact["id"], "number": number}
            elif kind == "equation":
                # Numbered when the line ends, not when it opens: a \\nonumber
                # anywhere in it suppresses the number.
                line_labels, line_nonumber = [], False
                target = None                         # labels wait for the line's number
        elif ev == "nonumber":                        # a \nonumber shorthand such as \nn
            line_nonumber = True
        elif ev == "labelx":                          # a \label shorthand such as \enum{x}
            handle_label(env)
        elif ev == "refx":                            # a \ref shorthand such as \eref{x}
            handle_ref(env, "alias", pos)
        elif ev == "end":
            if stack and stack[-1]["env"] == env:
                f = stack[-1]
                if f["kind"] == "equation" and env.rstrip("*") in _MULTILINE_EQ:
                    last_line = source[f.get("_line_start", f["start"]):pos]
                    if last_line.strip() or line_labels:
                        close_eq_line(f, pos, final=True)
                elif f["kind"] == "equation":
                    close_eq_line(f, pos, final=True)
                stack.pop()
                f["end"], f["outer_end"] = pos, after
                if f["kind"] != "equation":
                    just_closed = (f, after)
            if env.rstrip("*") == "subequations":
                sub_eq = None
            if env in open_envs:
                while open_envs:
                    top = open_envs.pop()
                    o_start, b_start = open_spans.pop()
                    target = group_targets.pop() if group_targets else None
                    if top == env:
                        environments.append({"env": env, "outer_start": o_start,
                                             "start": b_start, "end": pos, "outer_end": after})
                        break
        else:
            g = m
            if g.group("sec"):
                heading(_SEC_LEVEL[g.group("sec")], bool(g.group("sstar")), g.end(), pos)
            elif g.group("appendix"):
                in_appendix = True
                sec_ctr.update({0: 0, 1: 0, 2: 0, 3: 0} if chaptered else {1: 0, 2: 0, 3: 0})
            elif g.group("label") is not None:
                handle_label(g.group("label").strip(), g.start())
            elif g.group("newline"):
                top = stack[-1] if stack else None
                if top and top["kind"] == "equation" and top["env"].rstrip("*") in _MULTILINE_EQ \
                        and open_envs and open_envs[-1] == top["env"] \
                        and _brace_depth(source, top["start"], pos) == 0:
                    close_eq_line(top, pos)
                    top["_line_start"] = _AFTER_NEWLINE.match(source, g.end()).end()
            elif g.groupdict().get("nonumber"):
                line_nonumber = True
            elif g.group("item"):
                if open_envs and open_envs[-1] in _LIST_ENVS:
                    target = {"kind": "item", "id": None, "number": None}
            elif g.group("caption"):
                alg = next((f for f in reversed(stack) if f["kind"] == "algorithm"), None)
                target = ({"kind": "env", "id": alg["id"], "number": None} if alg
                          else {"kind": "float", "id": None, "number": None})
            elif g.group("algline"):
                if open_envs and open_envs[-1] == "algorithmic":
                    target = {"kind": "line", "id": None, "number": None}
            elif g.group("ref") is not None:
                handle_ref(g.group("ref"), g.group("refcmd"), pos)
            elif g.group("cite") is not None:
                keys = [k.strip() for k in g.group("cite").split(",") if k.strip()]
                cites.append({"keys": keys, "offset": pos,
                              "in": stack[-1]["id"] if stack else None})
                for f in stack:
                    f["cites"].extend(keys)

    for f in facts:                       # unclosed environments end at document end
        if f["end"] is None:
            f["end"] = f["outer_end"] = len(source)
        f["statement"] = span_text(source, f["start"], f["end"])
    split = {}
    for r in refs:                        # "a,b" is one label if the paper has it, else a list
        k = r["key"]
        split[k] = [k] if (k in labels or "," not in k) else [x.strip() for x in k.split(",") if x.strip()]
    refs[:] = [dict(r, key=k) for r in refs for k in split[r["key"]]]
    for f in facts:
        f["refs"] = [k for key in f["refs"] for k in split.get(key, [key])]
    _manual_facts(source, body_start, facts, sections, refs, cites, labels)
    for r in refs:
        t = labels.get(r["key"])
        r["target"] = (t["id"] or t["enclosing"]) if t else None
    _associate_proofs(facts, labels, source)
    _type_by_evidence(facts, source)
    _mark_duplicates(facts, labels)
    for f in facts:                       # author structure inside each proof
        if f["kind"] == "proof":
            nested = [g["outer_start"] - f["start"] for g in facts
                      if g["kind"] == "proof" and g["parent"] == f["id"]]
            st = detect_proof_structure(source[f["start"]:f["end"]], nested)
            for item in st["labels"] + st["claims"]:
                item["offset"] += f["start"]
            st["paragraph_breaks"] = [b + f["start"] for b in st["paragraph_breaks"]]
            f["structure"] = st
    number_index = {}
    for f in facts:
        if f["number"] and f["display"]:
            number_index[f"{_clean_display(f['display'])} {f['number']}"] = f["id"]
    # Every display, numbered or not: the equation environments, plus \[..\] and
    # $$..$$, which are not environments. Not facts (see below), but syntax.
    displays = [{k: f[k] for k in ("env", "start", "end", "outer_start", "outer_end",
                                   "labels", "number")}
                for f in facts if f["kind"] == "equation"]
    displays += _bare_displays(source, body_start, facts)
    displays.sort(key=lambda d: d["outer_start"])
    facts = _split_rows(facts, labels, refs, cites, source)
    environments.sort(key=lambda e: e["outer_start"])
    # Equations are facts only when the paper can point at them: a \label, or a
    # printed number that prose can cite as "(3)". An unnumbered display is
    # part of the text of the node that contains it, exactly like inline math.
    facts = [f for f in facts if f["kind"] != "equation" or f["labels"] or f["number"]
             or f.get("printed")]
    for f in facts:
        f.pop("printed", None)
    # an algorithmic block inside an algorithm float is the same algorithm, not a second one
    kinds = {f["id"]: f["kind"] for f in facts}
    facts = [f for f in facts if not (f["env"] == "algorithmic" and f["parent"]
                                      and kinds.get(f["parent"]) == "algorithm")]
    # Pseudocode lines, from the same parser that numbers them (algorithm_lines):
    # each algorithm fact lists its printed lines with their spans and the index
    # of the loop or branch line they sit in.
    from algorithm_lines import find_blocks
    algs = [f for f in facts if f["kind"] == "algorithm"]
    for b in find_blocks(source):
        holders = [f for f in algs if f["outer_start"] <= b.start < f["outer_end"]]
        if not holders:
            continue
        fact = min(holders, key=lambda f: f["outer_end"] - f["outer_start"])
        shift = len(fact.setdefault("lines", []))
        fact["lines_numbered"] = b.numbered
        for ln in b.lines:
            fact["lines"].append({"number": ln.number, "kind": ln.kind, "start": ln.start,
                                  "end": ln.end, "label": ln.label,
                                  "parent": None if ln.parent is None else ln.parent + shift})
    # A heading inside an environment (\subsection{Step 1} in a long proof) is
    # part of that environment; only the others divide the paper. `inside` is
    # the innermost fact containing the heading, or None for a top-level one.
    for sec in sections:
        holders = [f for f in facts if f["kind"] != "equation"
                   and f["outer_start"] < sec["start"] < f["outer_end"]]
        sec["inside"] = (min(holders, key=lambda f: f["outer_end"] - f["outer_start"])["id"]
                         if holders else None)
    by_sec = {sec["id"]: k for k, sec in enumerate(sections)}
    for f in facts:                       # a fact's section is the last heading of the paper,
        k = by_sec.get(f["section"])      # not a \subsection{Step 1} inside an environment
        while k is not None and k >= 0 and sections[k]["inside"] is not None:
            k -= 1
        f["section"] = sections[k]["id"] if k is not None and k >= 0 else None
    # section titles: \ref{key} rendered as the number it prints (rule 12: no raw refs)
    for sec in sections:
        sec["title"] = _REF.sub(lambda m: (labels.get(m.group(1).strip()) or {}).get("number")
                                or m.group(1).strip(), sec["title"])
    return {"source": source, "declarations": decl,
            "aliases": {"begin": a_begin, "end": a_end, "wrap": a_wrap, "nonumber": a_nonum},
            "facts": facts, "sections": sections, "labels": labels, "refs": refs,
            "cites": cites, "number_index": number_index,
            "environments": environments, "displays": displays}


# A row of a multi-line display that continues the previous row's formula has an
# empty first cell ("&= z", "&\\le \\dots", "&\\quad + c", eqnarray's "&=& z"), or, in a
# display without alignment (gather), opens with a relation ("= z", "\\le \\dots").
_ROW_PREFIX = re.compile(r"(?:\s+|\\(?:label|tag\*?)\s*\{[^{}]*\}"
                         r"|\\(?:nonumber|notag|displaystyle|nn|q?quad|enspace|thinspace|medspace|thickspace)(?![a-zA-Z])"
                         r"|\\[,;:! ]|\\(?:hspace|hskip|phantom|hphantom|vphantom)\*?\s*(?:\{[^{}]*\}|-?[\d.]+\s*[a-z]+)"
                         r"|^\[\s*-?[\d.]+\s*(?:pt|mm|cm|em|ex|in|bp)\s*\])")
_ROW_REL = re.compile(
    r"(?:=|<|>|\+|:=|\\(?:le|leq|ge|geq|leqq|geqq|leqslant|geqslant|ne|neq|approx|sim|simeq|cong|equiv"
    r"|lesssim|gtrsim|lessapprox|gtrapprox|ll|gg|subset|subseteq|subsetneq|supset|supseteq|to|mapsto"
    r"|rightarrow|longrightarrow|Rightarrow|Longrightarrow|leftarrow|Leftarrow|Longleftarrow|iff|implies"
    r"|impliedby|Leftrightarrow|Longleftrightarrow|propto|preceq|succeq|prec|succ|asymp|cdot|times|pm|mp"
    r"|coloneqq|eqqcolon|triangleq|doteq|stackrel|overset|underset)(?![a-zA-Z]))")
_ROW_TEXT = re.compile(r"\\(?:text|mbox|textrm|textup|textnormal|mathrm\{\s*(?:and|or|where)\b)|\\(?:short)?intertext\b")
# multi-line displays whose rows may be separate equations (numcases rows are cases of one)
_SPLIT_ENVS = _MULTILINE_EQ - {"numcases", "subnumcases"}


def _row_continues(text: str) -> bool:
    """Does a row of an align continue the previous row's formula (no left-hand side of its own)?"""
    def strip(t):
        prev = None
        while t != prev:
            prev, t = t, _ROW_PREFIX.sub("", t, count=1) if _ROW_PREFIX.match(t) else t
        return t
    text = strip(text)
    if not text:
        return True                       # an empty row joins
    if text.startswith("&"):              # empty first cell: no left-hand side, unless a text
        return not _ROW_TEXT.match(strip(text.lstrip("&")))   # connective opens a new one
    return bool(_ROW_REL.match(text))


def _split_rows(facts: list[dict], labels: dict, refs: list[dict], cites: list[dict],
                source: str) -> list[dict]:
    r"""One equation fact per equation of a multi-line display.

    An align whose numbered rows each have their own left-hand side ("a &= b (1) \\ c &= d
    (2)") holds two equations the paper cites separately, so it becomes one fact per
    row group: a row that continues the previous formula ("&= z", "&\le ...") joins its
    group, and so does a row with no number and no label. A chain ("x &= y (1) \\ &= z
    (2)") stays one fact carrying all its labels. The display (`displays`) stays whole."""
    n = max((int(f["id"][1:]) for f in facts if f["id"][1:].isdigit()), default=0)
    out = []
    for f in facts:
        rows = f.pop("_rows", None)
        f.pop("_line_start", None)
        if f["kind"] != "equation" or f["env"].rstrip("*") not in _SPLIT_ENVS or not rows or len(rows) < 2:
            out.append(f)
            continue
        groups = [[rows[0]]]
        for r in rows[1:]:
            (groups[-1].append(r) if _row_continues(source[r["start"]:r["end"]].strip())
             else groups.append([r]))
        pointable = [g for g in groups if any(r["number"] or r["labels"] for r in g)]
        if len(pointable) < 2:
            out.append(f)
            continue
        merged = []                       # a group with no number and no label joins the one before
        for g in groups:
            if merged and not any(r["number"] or r["labels"] for r in g):
                merged[-1] += g
            elif merged and not any(r["number"] or r["labels"] for r in merged[-1]):
                merged[-1] += g           # ... or, at the start, the one after
            else:
                merged.append(list(g))
        parts = []
        for k, g in enumerate(merged):
            start = f["start"] if k == 0 else g[0]["start"]
            it = re.match(r"\s*\\(?:short)?intertext\s*(?=\{)", source[start:f["end"]])
            if it:                            # \intertext{and} is prose between two equations
                _, close = _group(source, start + it.end())
                start = close if close else start
            end = f["end"] if k == len(merged) - 1 else g[-1]["end"]
            if k:
                n += 1
            keys = [key for r in g for key in r["labels"]]
            num = next((r["number"] for r in g if r["number"]), None)
            parts.append(dict(f, id=f["id"] if k == 0 else f"F{n}", start=start, end=end,
                              outer_start=f["outer_start"] if k == 0 else start,
                              outer_end=f["outer_end"] if k == len(merged) - 1 else end,
                              number=num, labels=keys, statement=span_text(source, start, end),
                              refs=[r["key"] for r in refs if r.get("in") == f["id"] and start <= r["offset"] < end],
                              cites=[c for x in cites if x.get("in") == f["id"] and start <= x["offset"] < end
                                     for c in x["keys"]]))
        stray = [key for key in f["labels"] if not any(key in p["labels"] for p in parts)]
        parts[0]["labels"] = stray + parts[0]["labels"]   # a label the rows did not record stays first
        for p in parts:
            for key in p["labels"]:
                if key in labels and labels[key].get("id") == f["id"]:
                    labels[key]["id"] = p["id"]
            for r in refs:
                if r.get("in") == f["id"] and p["start"] <= r["offset"] < p["end"]:
                    r["in"] = p["id"]
            for x in cites:
                if x.get("in") == f["id"] and p["start"] <= x["offset"] < p["end"]:
                    x["in"] = p["id"]
        for r in refs:
            t = labels.get(r["key"])
            if t and r.get("target") == f["id"]:
                r["target"] = t["id"] or t["enclosing"]
        out.extend(parts)
    return out


_SPACING_TAIL = re.compile(r"(?:\s|\\(?:par|medskip|smallskip|bigskip|newline|noindent)(?![a-zA-Z])"
                           r"|\\\\|\\vspace\*?\s*\{[^{}]*\}|\\vskip\s*-?[\d.]+\s*[a-z]+)+\Z")
# A proof written by hand: a "Proof" heading at the start of a line, in a font
# switch or a font command ({\bf Proof.}, \noindent{\it Proof of Theorem~\ref{x}.},
# \emph{Proof:}, \mbox{\em Proof.}), after optional spacing commands.
_MANUAL_PROOF = re.compile(
    r"(?m)^[ \t]*(?P<pre>(?:\\(?:noindent|par|medskip|smallskip|bigskip|indent)(?![a-zA-Z])\s*"
    r"|\\vspace\*?\s*\{[^{}]*\}\s*|\\vskip\s*-?[\d.]+\s*[a-z]+\s*)*)"
    r"(?P<open>\{\s*\\(?:bf|it|em|sc|sl|bfseries|itshape|scshape|slshape)(?![a-zA-Z])"
    r"|\\(?:textbf|textit|emph|textsc|textsl|mbox|underline)\s*\{)"
    r"\s*(?:\\(?:textbf|textit|emph|bf|it|em|sc|sl)(?![a-zA-Z])\s*\{?\s*)?Proof(?![a-zA-Z])")
# where a hand-written proof ends: its last end-of-proof mark before the next structure
_QED = re.compile(r"\\(?:qed|qedhere|Box|square|blacksquare|qedsymbol|endproof|QED|qedsquare"
                  r"|hfill\s*\$\s*\\(?:Box|square|blacksquare)\s*\$)(?![a-zA-Z])"
                  r"|Q\.\s?E\.\s?D\.?")
_EQNO = re.compile(r"\\l?eqno\s*(\([^()$]*\)|\{[^{}]*\}|[^\s$]+)")


def _manual_facts(source: str, body_start: int, facts: list[dict], sections: list[dict],
                  refs: list[dict], cites: list[dict], labels: dict) -> None:
    """Facts LaTeX states without an environment: hand-written proofs and
    hand-numbered displays ($$ ... \\eqno(3) $$). Added to `facts` in document order.

    A hand-written proof starts at its heading and ends at its last end-of-proof
    mark (\\qed, \\Box, ...) before the next theorem-like environment, heading or
    hand-written proof; with no mark it ends there (`end_basis`). A heading inside
    a proof environment is a part of that proof, not a new proof."""
    n = max((int(f["id"][1:]) for f in facts), default=0)
    blocks = [f for f in facts if f["kind"] != "equation"]

    def container(a: int, b: int):
        holders = [f for f in blocks if f["outer_start"] <= a and b <= f["outer_end"]]
        return min(holders, key=lambda f: f["outer_end"] - f["outer_start"]) if holders else None

    def section_at(pos: int):
        top = [s for s in sections if s["start"] < pos]
        return top[-1]["id"] if top else None

    heads = []
    for m in _MANUAL_PROOF.finditer(source, body_start):
        g0 = m.start("open") if m.group("open").startswith("{") else m.end("open") - 1
        title, close = _group(source, g0)
        if title is None:
            continue
        shown = re.sub(r"\s+", " ", re.sub(r"\\(?:textbf|textit|emph|bf|it|em|sc|sl|hspace\*?\{[^}]*\}|,|;|quad)", " ",
                                           title).replace("{", "").replace("}", "")).strip()
        if not shown.startswith("Proof") or len(shown) > 150:
            continue
        if any(f["kind"] == "proof" and f["start"] <= m.start("open") < f["end"] for f in blocks):
            continue                                  # a part of a proof environment
        heads.append((m.start("pre"), close, title.strip()))
    added = []
    for k, (a, close, title) in enumerate(heads):
        parent = container(a, close)
        bound = min([f["outer_start"] for f in blocks if f["outer_start"] > a
                     and f["kind"] in ("theorem_env", "proof", "algorithm")
                     and (parent is None or f["parent"] == parent["id"])]
                    + [s["start"] for s in sections if s["start"] > a]
                    + ([heads[k + 1][0]] if k + 1 < len(heads) else [])
                    + ([parent["end"]] if parent else [len(source)]))
        marks = list(_QED.finditer(source, close, bound))
        end, basis = (marks[-1].end(), "qed") if marks else (bound, "next_structure")
        if marks and re.match(r"[ \t]*\$", source[end:end + 4]):
            end = source.index("$", end) + 1          # the mark's math: \hfill $Q.E.D.$
        t = _SPACING_TAIL.search(source, close, end)
        if t and t.start() > close:
            end = t.start()                           # trailing spacing is not the proof
        n += 1
        f = {"id": f"F{n}", "kind": "proof", "env": None, "display": "Proof", "type": "proof",
             "optarg": title, "number": None, "labels": [], "cites": [],
             "refs": [r["key"] for r in refs if close <= r["offset"] < end],
             "section": section_at(a), "outer_start": a, "start": close, "end": end,
             "outer_end": end, "parent": parent["id"] if parent else None,
             "manual": True, "end_basis": basis}
        f["cites"] = [k_ for c in cites if close <= c["offset"] < end for k_ in c["keys"]]
        f["statement"] = span_text(source, f["start"], f["end"])
        added.append(f)
    for d in _bare_displays(source, body_start, facts):
        body = source[d["start"]:d["end"]]
        e = _EQNO.search(body)
        if not e:
            continue
        parent = container(d["outer_start"], d["outer_end"])
        n += 1
        num = e.group(1).strip("(){} ")
        for key in d["labels"]:                       # the walk bound them to the section
            labels[key] = dict(labels.get(key, {}), kind="equation", id=f"F{n}", number=num,
                               enclosing=parent["id"] if parent else None)
        added.append({"id": f"F{n}", "kind": "equation", "env": d["env"], "display": None,
                      "type": "equation", "optarg": None,
                      "number": num, "labels": d["labels"],
                      "refs": [r["key"] for r in refs if d["start"] <= r["offset"] < d["end"]],
                      "cites": [], "section": section_at(d["outer_start"]),
                      "outer_start": d["outer_start"], "start": d["start"], "end": d["end"],
                      "outer_end": d["outer_end"], "parent": parent["id"] if parent else None,
                      "statement": span_text(source, d["start"], d["end"])})
    for f in added:                                   # what a hand-written proof contains is its
        if f["kind"] != "proof":
            continue
        for g in facts + added:
            if g is not f and f["start"] <= g["outer_start"] < f["end"] and g["parent"] == f["parent"]:
                g["parent"] = f["id"]
    facts.extend(added)
    facts.sort(key=lambda f: (f["outer_start"], -f["outer_end"]))


def _bare_displays(source: str, start: int, facts: list[dict]) -> list[dict]:
    """\\[..\\] and $$..$$ displays from `start` on, outside equation environments.

    `\\[` opens a display only when its backslash is itself unescaped: in
    `\\\\[2pt]` (a line break with spacing) it does not.
    """
    toks = []
    for m in re.finditer(r"(\\+)([\[\]])|(?<!\\)\$\$", source[start:]):
        if m.group(1) is None:
            toks.append((start + m.start(), "$$"))
        elif len(m.group(1)) % 2 == 1:
            toks.append((start + m.end() - 2, "\\" + m.group(2)))
    eqs = sorted((f["outer_start"], f["outer_end"]) for f in facts if f["kind"] == "equation")
    eq_starts = [a for a, _b in eqs]
    eq_reach, r = [], -1                             # the farthest end among equations starting <= each start
    for _a, b in eqs:
        r = max(r, b)
        eq_reach.append(r)

    def in_equation(a, b):                           # some equation spans [a, b]
        k = bisect.bisect_right(eq_starts, a)
        return k > 0 and eq_reach[k - 1] >= b
    out, opened = [], None
    for pos, tok in toks:
        if opened is None:
            if tok in ("\\[", "$$"):
                opened = (pos, tok)
            continue
        o_pos, o_tok = opened
        if (o_tok, tok) in (("\\[", "\\]"), ("$$", "$$")):
            if "\n\n" not in source[o_pos + 2:pos].strip() and not in_equation(o_pos, pos + 2):
                body = source[o_pos + 2:pos]
                out.append({"env": o_tok, "start": o_pos + 2, "end": pos,
                            "outer_start": o_pos, "outer_end": pos + 2,
                            "labels": re.findall(r"\\label\s*\{([^{}]*)\}", body),
                            "number": None})
            opened = None
        elif tok in ("\\[", "$$"):                 # unclosed: restart at the new opener
            opened = (pos, tok)
    return out


def _newenvironment_spans(source: str, start: int) -> list[tuple[int, int]]:
    """Spans of \\newenvironment / \\renewenvironment definitions from `start` on."""
    out = []
    for m in re.finditer(r"\\(?:re)?newenvironment\*?\s*\{[^{}]*\}", source[start:]):
        j = start + m.end()
        for _ in range(2):                    # [nargs] [default]
            arg, k = _group(source, j, "[", "]")
            if arg is None:
                break
            j = k
        for _ in range(2):                    # {begin code} {end code}
            arg, k = _group(source, j)
            if arg is None:
                break
            j = k
        out.append((start + m.start(), j))
    return out


def _clean_display(display: str) -> str:
    d = re.sub(r"\\[a-zA-Z]+\s*", "", display)
    return re.sub(r"[{}]", "", d).strip().lower()


from node_types import THEOREM_LIKE as _THEOREM_LIKE


def _associate_proofs(facts: list[dict], labels: dict, source: str) -> None:
    """A proof's target, where syntax states it.

    `optarg`: \\begin{proof}[Proof of Theorem~\\ref{x}] names the result.
    `adjacent`: the proof begins right after a theorem-like environment ends,
    with only whitespace between them (the amsthm convention).
    Otherwise None: that is a judgment for the LLM.
    """
    by_end = {}
    for f in facts:
        if f["kind"] == "theorem_env" and f["type"] in _THEOREM_LIKE:
            by_end[f["outer_end"]] = f
    for f in facts:
        if f["kind"] != "proof":
            continue
        f["proves"], f["proves_basis"] = None, None
        if f["optarg"]:
            for key in _REF.findall(f["optarg"]):
                t = labels.get(key.strip())
                if t and t["kind"] == "env":
                    f["proves"], f["proves_basis"] = t["id"], "optarg"
                    break
        if f["proves"] is None:
            prev_end = max((e for e in by_end if e <= f["outer_start"]), default=None)
            gap = source[prev_end:f["outer_start"]] if prev_end is not None else None
            # only whitespace between them, or the opening of a wrapper (\new{\begin{proof})
            if gap is not None and not re.sub(r"\\[A-Za-z]+\s*\{|\{|\s", "", gap):
                f["proves"], f["proves_basis"] = by_end[prev_end]["id"], "adjacent"


# A declared block of unknown type is still a node; its type comes from what it
# does, and only from evidence that leaves little doubt.
_DEFINES = re.compile(r"\b(?:is|are)\s+(?:called|said\s+to\s+be|defined\s+(?:as|by|to\s+be))\b"
                      r"|\bwe\s+(?:say|call|define|write)\b|\bis\s+termed\b")


def _type_by_evidence(facts: list[dict], source: str) -> None:
    """Type an untyped theorem-style block: a proof right after it makes it a
    result (claim); a definitional phrase makes it a definition. `type_basis`
    records which; a block with neither stays untyped."""
    proofs = [f for f in facts if f["kind"] == "proof"]
    for f in facts:
        if f["kind"] != "theorem_env" or f["type"] is not None:
            continue
        nxt = min((p for p in proofs if p["outer_start"] >= f["outer_end"]),
                  key=lambda p: p["outer_start"], default=None)
        if nxt is not None and not source[f["outer_end"]:nxt["outer_start"]].strip():
            f["type"], f["type_basis"] = "claim", "followed_by_proof"
            if nxt.get("proves") is None:
                nxt["proves"], nxt["proves_basis"] = f["id"], "adjacent"
        elif _DEFINES.search(f["statement"]):
            f["type"], f["type_basis"] = "definition", "defining_phrase"


_RESULT_TYPES = _THEOREM_LIKE | {"definition", "remark", "example", "assumption", "problem",
                                 "open_problem", "exercise", "algorithm"}


def _mark_duplicates(facts: list[dict], labels: dict) -> None:
    """A result the paper declares to be a restatement of a later one is one node:
    the later copy (in the body, with its proof) is kept and the earlier one gets
    `duplicate_of`. Only the declared form is used: an optional argument or an
    that points at a later result: \\begin{maintheorem}[= Theorem~\\ref{x}],
    [see Theorem~\\ref{x}]. Similar text is not evidence: on the silver
    corpus most near-identical environments are separate statements (the same
    setup sentence in two sections, a theorem and its variant)."""
    blocks = [f for f in facts if f["kind"] == "theorem_env" and f["type"] in _RESULT_TYPES]
    by_id = {f["id"]: f for f in blocks}
    for f in blocks:
        head = f.get("optarg") or ""             # [= Theorem~\ref{x}], [see Theorem~\ref{x}]
        if not re.match(r"\s*(?:=|see\b|cf\b|restat|repeat)", head, re.I):
            continue
        for key in _REF.findall(head):
            t = labels.get(key.strip())
            g = by_id.get(t["id"]) if t else None
            if g is not None and g is not f and g["outer_start"] > f["outer_start"]:
                f["duplicate_of"], f["duplicate_basis"] = g["id"], "declared"
                break


def summary(fx: dict) -> str:
    from collections import Counter
    kinds = Counter((f["kind"], f["type"]) for f in fx["facts"])
    resolved = sum(r["target"] is not None for r in fx["refs"])
    proves = Counter(f.get("proves_basis") for f in fx["facts"] if f["kind"] == "proof")
    lines = [f"declared environments: {len(fx['declarations'])}",
             f"facts: {len(fx['facts'])}  sections: {len(fx['sections'])}  "
             f"labels: {len(fx['labels'])}",
             f"refs: {len(fx['refs'])} ({resolved} resolve to a label in this paper)",
             f"proofs: {dict(proves)}"]
    for (k, t), n in sorted(kinds.items(), key=lambda x: -x[1]):
        lines.append(f"  {n:5d}  {k:12s} {t}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tex")
    ap.add_argument("--out", help="write the full facts as JSON")
    args = ap.parse_args()
    fx = extract_facts(read_tex(args.tex))
    print(summary(fx))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(fx, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
