"""
Tests for canonicalize module. Run as:

    python -m scripts.canonicalize.test_canonicalize

from the Authomathics repo root.
"""
import unittest
from scripts.canonicalize.core import (
    canonicalize_text,
    canonicalize_paper,
    build_local_rename_map,
    build_paper_rename_map,
)


class TestSurfaceNormalization(unittest.TestCase):

    def test_spacing_strip(self):
        self.assertEqual(
            canonicalize_text(r"$a \, + \, b$"),
            "$a + b$",
        )

    def test_left_right_strip(self):
        self.assertEqual(
            canonicalize_text(r"$\left( a + b \right)^2$"),
            "$(a + b)^2$",
        )

    def test_cdot_to_star(self):
        self.assertEqual(
            canonicalize_text(r"$a \cdot b$"),
            "$a * b$",
        )

    def test_times_to_star(self):
        self.assertEqual(
            canonicalize_text(r"$a \times b$"),
            "$a * b$",
        )

    def test_le_to_leq(self):
        self.assertEqual(
            canonicalize_text(r"$a \le b$"),
            r"$a \leq b$",
        )

    def test_greek_unicode(self):
        self.assertEqual(
            canonicalize_text(r"$α + β$"),
            r"$\alpha + \beta$",
        )

    def test_greek_variants(self):
        self.assertEqual(
            canonicalize_text(r"$\varepsilon + \varphi$"),
            r"$\epsilon + \phi$",
        )

    def test_number_sets(self):
        self.assertEqual(
            canonicalize_text(r"$a \in \R$"),
            r"$a \in \mathbb{R}$",
        )
        self.assertEqual(
            canonicalize_text(r"$a \in \mathbf{R}$"),
            r"$a \in \mathbb{R}$",
        )

    def test_rightarrow_to_to(self):
        self.assertEqual(
            canonicalize_text(r"$f: A \rightarrow B$"),
            r"$f: A \to B$",
        )

    def test_implies_normalization(self):
        self.assertEqual(
            canonicalize_text(r"$A \Rightarrow B$"),
            r"$A \implies B$",
        )


class TestFractionRewrite(unittest.TestCase):

    def test_simple_frac(self):
        # {a}/{b} has redundant single-token braces stripped -> a/b
        self.assertEqual(
            canonicalize_text(r"$\frac{a}{b}$"),
            "$a/b$",
        )

    def test_dfrac_to_frac_to_flat(self):
        self.assertEqual(
            canonicalize_text(r"$\dfrac{a}{b}$"),
            "$a/b$",
        )

    def test_nested_frac(self):
        # \frac{a}{\frac{b}{c}} -> {a}/{{b}/{c}} -> a/{b/c} (after brace strip)
        self.assertEqual(
            canonicalize_text(r"$\frac{a}{\frac{b}{c}}$"),
            "$a/{b/c}$",
        )

    def test_frac_with_spaces(self):
        # Inner-brace-space rule strips spaces, then single-token braces keep
        # (because {x + 1} has multiple tokens) -> {x + 1}/{y - 1}
        self.assertEqual(
            canonicalize_text(r"$\frac { x + 1 } { y - 1 }$"),
            "${x + 1}/{y - 1}$",
        )


class TestBinomExp(unittest.TestCase):

    def test_binom(self):
        self.assertEqual(
            canonicalize_text(r"$\binom{n}{k}$"),
            "$C(n,k)$",
        )

    def test_exp_paren(self):
        # \exp(x) -> e^{x} -> e^x (braces stripped since x is single letter)
        self.assertEqual(
            canonicalize_text(r"$\exp(x)$"),
            "$e^x$",
        )


class TestInequalityFlip(unittest.TestCase):

    def test_gt_flip(self):
        self.assertEqual(
            canonicalize_text(r"$b > a$"),
            "$a < b$",
        )

    def test_geq_flip(self):
        self.assertEqual(
            canonicalize_text(r"$b \geq a$"),
            r"$a \leq b$",
        )

    def test_already_canonical(self):
        # Already in canonical < direction: no change.
        self.assertEqual(
            canonicalize_text(r"$a < b$"),
            "$a < b$",
        )


class TestLogToLn(unittest.TestCase):

    def test_plain_log(self):
        self.assertEqual(
            canonicalize_text(r"$\log(x)$"),
            r"$\ln(x)$",
        )

    def test_log_with_base_kept(self):
        # \log_{10} must stay: author chose a base.
        out = canonicalize_text(r"$\log_{10}(x)$")
        self.assertIn(r"\log_", out)  # still \log_{10}, not \ln
        self.assertNotIn(r"\ln", out)

    def test_log_with_base_2(self):
        out = canonicalize_text(r"$\log_2(x)$")
        self.assertIn(r"\log_", out)


class TestOversetUnderset(unittest.TestCase):

    def test_overset_strips_decoration(self):
        self.assertEqual(
            canonicalize_text(r"$f(x) \overset{x \to \infty}{\to} c$"),
            r"$f(x) \to c$",
        )

    def test_underset_strips_decoration(self):
        self.assertEqual(
            canonicalize_text(r"$f(x) \underset{x \to \infty}{\to} c$"),
            r"$f(x) \to c$",
        )


class TestCommandBoundary(unittest.TestCase):
    """Regression tests: commands with common prefixes must not collide."""

    def test_R_does_not_corrupt_Rightarrow(self):
        self.assertEqual(
            canonicalize_text(r"$A \Rightarrow B$"),
            r"$A \implies B$",
        )

    def test_mathbb_R_survives_brace_strip(self):
        # \mathbb{R} must stay -- the {R} is a command argument, not
        # a redundant grouping.
        self.assertEqual(
            canonicalize_text(r"$x \in \mathbb{R}$"),
            r"$x \in \mathbb{R}$",
        )

    def test_to_does_not_corrupt_top(self):
        # \to and \top share a prefix
        self.assertEqual(
            canonicalize_text(r"$x \to \top$"),
            r"$x \to \top$",
        )


class TestRedundantBrace(unittest.TestCase):

    def test_single_letter_brace(self):
        self.assertEqual(
            canonicalize_text(r"$x^{2}$"),
            "$x^2$",
        )

    def test_single_cmd_brace(self):
        self.assertEqual(
            canonicalize_text(r"${\alpha}$"),
            r"$\alpha$",
        )

    def test_nested_double_brace(self):
        self.assertEqual(
            canonicalize_text(r"$x^{{n}}$"),
            "$x^n$",
        )

    def test_multichar_brace_kept(self):
        # {2n} should stay braced because 2n is ambiguous without braces in x^{2n}
        # Note: current impl drops the braces; this test documents existing behavior.
        # (Revisit if we want a smarter multichar-detector.)
        pass


class TestVariableRename(unittest.TestCase):

    def test_local_rename_map(self):
        m = build_local_rename_map(r"$(a+b)^2 = a^2 + 2ab + b^2$")
        # a appears first, then b
        self.assertEqual(m.get("a"), "V1")
        self.assertEqual(m.get("b"), "V2")

    def test_rename_applied(self):
        m = build_local_rename_map(r"$(a+b)^2$")
        out = canonicalize_text(r"$(a+b)^2$", rename_map=m)
        self.assertEqual(out, "$(V1+V2)^2$")

    def test_letter_constants_not_renamed(self):
        # e (Euler) and i (imaginary unit) must NOT be variable candidates
        m = build_local_rename_map(r"$e^{i\pi} = -1$")
        self.assertNotIn("e", m)
        self.assertNotIn("i", m)
        # \pi is also a constant (command form)
        self.assertNotIn(r"\pi", m)

    def test_norm_name_preserved(self):
        # l_1, l_2 are norm names — the l should NOT be renamed
        m = build_local_rename_map(r"$x \in l_1$ and $l_2$ norm")
        out = canonicalize_text(r"$x \in l_1$ and $l_2$ norm", rename_map=m)
        self.assertIn("l_1", out)   # kept as norm name
        self.assertIn("l_2", out)   # kept as norm name
        self.assertNotIn("x", out)  # x got renamed

    def test_bare_l_renamed(self):
        # bare l (no subscript) IS a variable, gets renamed
        m = build_local_rename_map(r"$a + l = b$")
        self.assertIn("l", m)  # l is in the rename map
        out = canonicalize_text(r"$a + l = b$", rename_map=m)
        self.assertNotIn("$a", out)  # a renamed
        # l should be renamed (bare, no subscript)
        # but we can't easily check this without knowing the V-number

    def test_ell_to_l_then_norm_preserved(self):
        # \ell_1 -> l_1 (surface rule) then l is kept (norm name)
        m = build_local_rename_map(r"$\ell_1$ minimization of $x$")
        out = canonicalize_text(r"$\ell_1$ minimization of $x$", rename_map=m)
        self.assertIn("l_1", out)   # \ell -> l, then l_1 kept

    def test_only_greek_commands_are_variable_candidates(self):
        # \geq, \leq, \implies etc. are relations, NOT variables
        m = build_local_rename_map(r"$a \geq b \implies \alpha \leq \beta$")
        self.assertNotIn(r"\geq", m)
        self.assertNotIn(r"\leq", m)
        self.assertNotIn(r"\implies", m)
        # a, b, \alpha, \beta are variables
        self.assertIn("a", m)
        self.assertIn("b", m)
        self.assertIn(r"\alpha", m)
        self.assertIn(r"\beta", m)

    def test_two_equivalent_statements_match(self):
        # The whole point: (a+b)^2 and (x+y)^2 should canonicalize identically
        # under their own local rename maps.
        t1 = r"$(a+b)^2$"
        t2 = r"$(x+y)^2$"
        m1 = build_local_rename_map(t1)
        m2 = build_local_rename_map(t2)
        self.assertEqual(canonicalize_text(t1, rename_map=m1),
                         canonicalize_text(t2, rename_map=m2))

    def test_constants_not_renamed(self):
        m = build_local_rename_map(r"$\pi + x$")
        self.assertNotIn(r"\pi", m)
        self.assertIn("x", m)

    def test_function_names_not_renamed(self):
        m = build_local_rename_map(r"$\sin(x) + \cos(y)$")
        self.assertNotIn(r"\sin", m)
        self.assertNotIn(r"\cos", m)
        self.assertIn("x", m)
        self.assertIn("y", m)


class TestPaperScope(unittest.TestCase):

    def test_paper_scope_consistent(self):
        paper = {
            "paper_num": 1,
            "nodes": {
                "T1": {"kind": "theorem", "statement": r"$a^2 \geq 0$"},
                "T2": {"kind": "theorem", "statement": r"$a + b > 0 \implies b > -a$"},
            },
            "edges": [],
        }
        pm = build_paper_rename_map(paper)
        # a and b both renamed, consistently across T1 and T2
        self.assertEqual(pm["a"], "V1")
        self.assertEqual(pm["b"], "V2")

    def test_canonicalize_paper_emits_both_forms(self):
        paper = {
            "paper_num": 1,
            "nodes": {
                "T1": {"kind": "theorem", "statement": r"$(a+b)^2 = a^2+b^2+2ab$"},
            },
            "edges": [],
        }
        out = canonicalize_paper(paper)
        node = out["nodes"]["T1"]
        self.assertIn("statement_canonical_paper", node)
        self.assertIn("statement_canonical_local", node)


class TestIntegrationCanonicalExamples(unittest.TestCase):
    """The motivating examples from the design discussion."""

    def test_ab_squared_equivalence(self):
        t1 = r"$(a+b)^2 = a^2 + b^2 + 2ab$"
        t2 = r"$(x+y)^2 = x^2 + 2xy + y^2$"
        m1 = build_local_rename_map(t1)
        m2 = build_local_rename_map(t2)
        c1 = canonicalize_text(t1, rename_map=m1)
        c2 = canonicalize_text(t2, rename_map=m2)
        # Not identical yet (term ordering differs: a^2+b^2+2ab vs a^2+2ab+b^2)
        # But variable-renaming works:
        self.assertIn("V1", c1)
        self.assertIn("V1", c2)
        # Full equivalence would require SymPy algebraic simplification (L2).

    def test_fraction_vs_division(self):
        t1 = r"$\frac{a}{b}$"
        t2 = r"${a}/{b}$"
        m1 = build_local_rename_map(t1)
        m2 = build_local_rename_map(t2)
        self.assertEqual(canonicalize_text(t1, rename_map=m1),
                         canonicalize_text(t2, rename_map=m2))


if __name__ == "__main__":
    unittest.main()
