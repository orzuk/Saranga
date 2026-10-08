"""Fast tests for the meaning verifiers (verify_meaning, verify_symbols).

Run from the repo root:
    python3 -m unittest scripts.canonicalize.test_verify
The full corpus run is a separate command (see verify_meaning.py).
"""
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import core
from . import verify_meaning as VM

try:
    import sympy  # noqa: F401
    from sympy.parsing.latex import parse_latex
    parse_latex("x")
    HAVE_PARSER = True
except Exception:  # noqa: BLE001 -- antlr4 runtime missing
    HAVE_PARSER = False


def _swap_around_geq(text: str) -> str:
    """A planted bad rule: swap the single tokens next to \\geq and flip it,
    the old `x^2 \\geq 0` -> `x^0 \\leq 2` bug."""
    return re.sub(r"(\S)\s*\\geq\s*(\S)", lambda m: f"{m.group(2)} \\leq {m.group(1)}", text)


@unittest.skipUnless(HAVE_PARSER, "needs antlr4-python3-runtime==4.11 for sympy.parse_latex")
class MeaningTests(unittest.TestCase):

    def test_planted_bad_flip_is_caught_and_located(self):
        with mock.patch.object(core, "_flip_inequalities", _swap_around_geq):
            r = VM.check_formula(r"$x^2 \geq 0$")
        self.assertEqual(r["canonical"], r"$V1^0 \leq 2$")
        self.assertEqual(r["status"], "violation")
        self.assertTrue(r["phase"].startswith("15"), r["phase"])
        self.assertIn("point", r["violation"])

    def test_planted_bad_rename_is_caught(self):
        # a rename that sends two variables to the same name
        real = core._apply_rename_in_math
        bad = lambda s, m: real(s, m).replace("V2", "V1")
        with mock.patch.object(core, "_apply_rename_in_math", bad):
            r = VM.check_formula(r"$x + 2y$")
        self.assertEqual(r["status"], "violation")
        self.assertTrue(r["phase"].startswith("18"), r["phase"])

    def test_real_canonicalizer_passes_fixed_set(self):
        formulas = [
            r"$x^2 \geq 0$",
            r"$\frac{a}{b}^2 + c$",
            r"$\exp(x)^2 \le \frac{1}{2} y$",
            r"$a \geq b + c$",
            r"$\frac{1}{2}x > y$",
            r"$\sqrt{x+1} \ge \ln(y)$",
            r"\begin{equation*} \dfrac{a+b}{c} = \left(d - f\right)^{2} \end{equation*}",
            r"\[ a \le b \le c \]",
            r"$$\varphi(x) \neq \theta_1$$",
            r"$x_{i+1} = \alpha x_i$",
        ]
        for f in formulas:
            with self.subTest(f=f):
                r = VM.check_formula(f)
                self.assertEqual(r["status"], "ok", r)
                self.assertFalse(r["drift"])

    def test_formerly_open_bugs_are_fixed(self):
        # each was a confirmed violation before the fix of its bug class
        for f in [r"\begin{align} a &= 1 \\ 2 &= b \end{align}",         # \  ate \\
                  r"$|V(ux)| \leq |V(u)|$",                              # letter runs
                  r"$\frac{y}{z}!$",                                       # postfix !
                  r"\begin{alignat*}{2}e^{n!} &> \alpha\\ &\ge n\end{alignat*}",
                  r"$$n \overset{(a)}{>} \frac{2}{x}^{\alpha} \geq \theta$$",
                  r"$D_{\omega}d$"]:
            with self.subTest(f=f):
                r = VM.check_formula(f)
                self.assertEqual(r["status"], "ok", r)
                self.assertFalse(r["drift"])
                self.assertFalse(r["unbraced_v_script"])

    def test_skip_is_not_a_pass(self):
        r = VM.check_formula(r"$\int_0^1 f(x)\,dx \in \mathbb{R}$")
        self.assertEqual(r["status"], "skip")
        self.assertTrue(r["reason"])

    def test_relation_compared_as_a_whole(self):
        ctx = VM.make_ctx(None)
        status, _, _ = VM.compare(r"$a \geq b$", r"$b \leq a$", "canon", ctx, 1)
        self.assertEqual(status, "ok")
        ctx = VM.make_ctx(None)
        status, info, _ = VM.compare(r"$a \geq b \geq c$", r"$b \leq a \geq c$", "canon", ctx, 1)
        self.assertEqual(status, "violation")

    def test_replay_matches_pipeline(self):
        for f in [r"$x^2 \geq 0$", r"\begin{align*} a &\le b \\ c &= d \end{align*}"]:
            m = core.build_local_rename_map(f)
            stages, o, c = VM.replay(f, m, core._greek_variants_for(f))
            self.assertEqual(o + stages[-1][1] + c,
                             core._canonicalize_math_segment(f, m, core._greek_variants_for(f)))

    def test_fuzzer_is_deterministic(self):
        self.assertEqual(VM.fuzz_formulas(20, 3), VM.fuzz_formulas(20, 3))


@unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftoppm"), "needs pdflatex, pdftoppm")
class SymbolTests(unittest.TestCase):

    def test_planted_merge_and_safe_rule(self):
        from . import verify_symbols as VS
        with tempfile.TemporaryDirectory() as d:
            merge = VS.classify({"table": "RULES_RELATIONS", "key": r"\leq", "value": "<"}, Path(d), 0)
            safe = VS.classify({"table": "RULES_RELATIONS", "key": r"\le", "value": r"\leq"}, Path(d), 1)
            assumed = VS.classify({"table": "RULES_NUMBER_SETS", "key": r"\R", "value": r"\mathbb{R}"},
                                  Path(d), 2)
        self.assertEqual(merge["status"], "MERGE")
        self.assertTrue(merge.get("needs_review"))
        self.assertEqual(safe["status"], "SAFE")
        self.assertEqual(assumed["status"], "SAFE")
        self.assertIn(r"\R", assumed["assumes_definition"])


if __name__ == "__main__":
    unittest.main()
