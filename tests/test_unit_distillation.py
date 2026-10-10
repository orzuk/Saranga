"""Regression tests for the unit distillation and the bugs fixed with it.

Runs without pytest:  python3 tests/test_unit_distillation.py

No network, no API key: the teacher is never called here (an end-to-end run
uses tests/stub_teacher, see docs/distillation_units.md).
"""
import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    sys.path.insert(0, str(p))

import latex_facts as L            # noqa: E402
import prose_units as U            # noqa: E402
import unit_rules as UR            # noqa: E402
from distill_registry import RuleRegistry   # noqa: E402

FAILS = []


def check(got, want, why):
    if got != want:
        FAILS.append(f"{why}\n     got  {got!r}\n     want {want!r}")


def sentences_of(body: str):
    tex = "\\documentclass{article}\\begin{document}\n" + body + "\n\\end{document}"
    fx = L.extract_facts(tex)
    src = fx["source"]
    return [re.sub(r"\s+", " ", src[s.start:s.end]) for s in U.sentences(fx)], fx


# ---- prose units: where sentences end -------------------------------------------
ss, _ = sentences_of("We say $x$ is good. Then $y$ is bad, e.g. here. Fig. 2 shows it.")
check(ss, ["We say $x$ is good.", "Then $y$ is bad, e.g. here.", "Fig. 2 shows it."],
      "sentence ends; no break after an abbreviation")

ss, _ = sentences_of("For instance, the result\n\\[\nx = 1.\n\\]\nindicates that $a$ holds. Next.")
check(ss[0].startswith("For instance, the result") and ss[0].endswith("holds."), True,
      "a display inside a sentence does not end it")

ss, _ = sentences_of("Notice $$a=b$$ for all $u$. Then a $5 \\$ cost. Done.")
check(len(ss), 3, "$$ ... $$ is not two inline formulas (scanner, not regex)")

ss, _ = sentences_of("A first paragraph.\n\nA second one.")
check(len(ss), 2, "a paragraph break ends a sentence")

ss, fx = sentences_of("Prose before.\n\\begin{theorem}\nInside a theorem.\n\\end{theorem}\nProse after.")
check(ss, ["Prose before.", "Prose after."], "environment facts are not prose")

# ---- unit rules: span options and selection ----------------------------------------
_, fx = sentences_of("We say $A$ holds. It is $B$.\n\nWe say $C$. Then $D$. And $E$.")
sents = U.sentences(fx)
check(UR.span_end(sents, 0, "1"), 0, "span 1")
check(UR.span_end(sents, 0, "para"), 1, "span para stops at the paragraph break")
check(UR.span_end(sents, 2, "2"), 3, "span 2")
rules = [{"uid": 1, "type": "definition", "regex": r"^We say", "flags": "", "span": "para",
          "precision": 0.9},
         {"uid": 2, "type": "claim", "regex": r"\bsay\b", "flags": "", "span": "1",
          "precision": 0.5},
         {"uid": 3, "type": "remark", "regex": r"^It is", "flags": "", "span": "1",
          "precision": 0.99}]
nodes = UR.apply_rules(fx["source"], sents, rules)
check([(n["type"], n["first"], n["last"]) for n in nodes],
      [("definition", 0, 1), ("definition", 2, 4)],
      "the most precise firing rule decides; a sentence inside a node anchors no other")

# ---- registry: identity, retirement, persistence ----------------------------------------
d = tempfile.mkdtemp()
reg = RuleRegistry(Path(d) / "reg.json")
a = reg.mint("a", "definition", r"\bwe say\b", "r1", {"span": "1", "flags": "i"})
b = reg.mint("b", "definition", r"\bwe say\b", "r1", {"span": "1", "flags": "i"})
c = reg.mint("c", "definition", r"\bwe say\b", "r1", {"span": "para", "flags": "i"})
check((a.uid == b.uid, a.uid != c.uid), (True, True), "identity = regex + spec")
reg.retire_with(c, "test")
reg.save()
reg2 = RuleRegistry.load(Path(d) / "reg.json")
check([r.status for r in sorted(reg2.rules.values(), key=lambda r: r.uid)],
      ["active", "retired"], "retirement persists")
check(bool(reg2.rules[a.uid].regex().flags & re.I), True, "flags come from the spec")

# ---- rule_guard: a positional flag is a flag, not a start position ----------------------
cases = [lambda: re.findall(r"^ab", "xx\nAB\nab", re.M | re.I),
         lambda: re.search(r"hello", "HELLO", re.I).group(0),
         lambda: re.sub(r"a", "b", "AaA", 0, re.I),
         lambda: re.split(r"b", "aBc", 0, re.I)]
before = [f() for f in cases]
import rule_guard                                   # noqa: E402
rule_guard.install_global(threshold=5)
check([f() for f in cases], before, "guarded re.* with positional flags = plain re.*")

# ---- the parser's rule-module cache follows the installed file, not the path -----------
import math_paper_parser                            # noqa: E402,F401  (installs the cache)
math_paper_parser._cache_rule_modules()
d = Path(tempfile.mkdtemp())
(d / "one").mkdir()
(d / "two").mkdir()
(d / "one" / "distilled_rules.py").write_text("WHICH = 'one'\n")
(d / "two" / "distilled_rules.py").write_text("WHICH = 'two'  # same size would be fine too\n")
link = d / "distilled_rules.py"


def load(target):
    if link.is_symlink():
        link.unlink()
    link.symlink_to(target)
    spec = importlib.util.spec_from_file_location("x", str(link))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.WHICH


check([load(d / "one" / "distilled_rules.py"), load(d / "two" / "distilled_rules.py"),
       load(d / "one" / "distilled_rules.py")], ["one", "two", "one"],
      "a re-pointed symlink loads the new rule module")

# ---- FDR prune: a pruned pattern listed by name in a rule table must stay importable ------
import distillation_analysis as DA                  # noqa: E402
_src = ("import re\n_PAT_A = re.compile(\n    r\"we say\", re.I)\n_PAT_B = re.compile(r\"is called\")\n"
        "RULES = [(\"_PAT_A\", _PAT_A), (\"_PAT_B\", _PAT_B)]\n"
        "def extract_distilled_definition(text):\n"
        "    return [m.group(0) for _n, p in RULES for m in p.finditer(text)]\n")
_ns = {}
exec(compile("".join(DA._comment_out_rule_block(_src.splitlines(keepends=True), "_PAT_A", ["p"], 0)),
             "rules", "exec"), _ns)
check(_ns["extract_distilled_definition"]("We say x. It is called y."), ["is called"],
      "a pruned pattern is rebound to a never-matching one, so references survive")

# ---- the unit algorithm's helpers --------------------------------------------------------
import distill_units as D                           # noqa: E402
check(D.signature(r"We say that a set is \emph{open} if it is \cite{x}."),
      ("we say", ("emph", "cite")), "signature: cue phrase and markup")
check(D.signature(r"Let $X$ be a space.")[0], "let", "signature: opening cue")

if FAILS:
    print(f"{len(FAILS)} FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("all unit-distillation checks pass")
