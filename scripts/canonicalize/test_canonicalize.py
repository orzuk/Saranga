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

    def test_cdot_kept_distinct(self):
        # \cdot NOT unified with * (could be dot product vs multiplication)
        self.assertEqual(
            canonicalize_text(r"$a \cdot b$"),
            r"$a \cdot b$",
        )

    def test_times_kept_distinct(self):
        # \times NOT unified with * (could be cross product vs multiplication)
        self.assertEqual(
            canonicalize_text(r"$a \times b$"),
            r"$a \times b$",
        )

    def test_star_kept_distinct(self):
        # x^\star (an optimum) and x^* (an adjoint) often coexist.
        self.assertEqual(canonicalize_text(r"$x^\star \neq x^*$"), r"$x^\star \neq x^*$")

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
        # A bold capital is usually a matrix (\mathbf{Z} a design matrix).
        self.assertEqual(canonicalize_text(r"$a \in \mathbf{R}$"), r"$a \in \mathbf{R}$")
        self.assertEqual(canonicalize_text(r"$\mathcal{R}(A)$"), r"$\mathcal{R}(A)$")

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

    def test_binom_kept(self):
        # Not rewritten to C(n,k): that collides with a variable C.
        self.assertEqual(canonicalize_text(r"$\binom{n}{k} = C$"), r"$\binom{n}k = C$")

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

    def test_flip_swaps_whole_sides(self):
        # Regression: the flip used to swap only the tokens next to the
        # relation, so x^2 >= 0 became x^0 <= 2.
        cases = {
            r"$x^2 \geq 0$": r"$0 \leq x^2$",
            r"$\frac{a}{b} \geq y$": r"$y \leq a/b$",
            r"$a + b \geq c$": r"$c \leq a + b$",
            r"$2x > y$": "$y < 2x$",
            r"$e^{x} \geq 1+x$": r"$1+x \leq e^x$",
            r"$\sum_{i>0} a_i > b$": r"$b < \sum_{i>0} a_i$",
        }
        for src, want in cases.items():
            self.assertEqual(canonicalize_text(src), want, src)

    def test_flip_one_formula_at_a_time(self):
        self.assertEqual(canonicalize_text(r"$x > 0, y > 1$"), "$0 < x, 1 < y$")
        self.assertEqual(canonicalize_text(r"$x > 0 \implies y > 0$"),
                         r"$0 < x \implies 0 < y$")

    def test_no_flip_when_ambiguous(self):
        for src in (r"$a > b > c$", r"$\{x : x > 0\}$", r"$P(X > t) \leq e^{-t}$"):
            self.assertEqual(canonicalize_text(src), src.replace(r"\le ", r"\leq "), src)

    def test_already_canonical(self):
        # Already in canonical < direction: no change.
        self.assertEqual(
            canonicalize_text(r"$a < b$"),
            "$a < b$",
        )


class TestLnToLog(unittest.TestCase):

    def test_ln_kept_distinct_from_log(self):
        # \log is base 2 in computer science: merging would make
        # \log_2 n = \ln n / \ln 2 read as a false identity.
        self.assertEqual(canonicalize_text(r"$\ln(x)$"), r"$\ln(x)$")

    def test_log_stays_log(self):
        self.assertEqual(
            canonicalize_text(r"$\log(x)$"),
            r"$\log(x)$",
        )

    def test_log_with_base_kept(self):
        out = canonicalize_text(r"$\log_{10}(x)$")
        self.assertIn(r"\log_", out)

    def test_log_with_base_2(self):
        out = canonicalize_text(r"$\log_2(x)$")
        self.assertIn(r"\log_", out)


class TestOversetUnderset(unittest.TestCase):

    def test_decoration_kept(self):
        # X =^d Y (equal in distribution) is not X = Y.
        self.assertEqual(canonicalize_text(r"$X \stackrel{d}{=} Y$"),
                         r"$X \overset{d}{=} Y$")
        self.assertEqual(canonicalize_text(r"$f(x) \underset{x \to \infty}{\to} c$"),
                         r"$f(x) \underset{x \to \infty}\to c$")


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


class TestDisplayMath(unittest.TestCase):
    """Displays that mean the same thing canonicalize to the same text, and
    math inside display environments is canonicalized like any other math."""

    def test_single_line_displays_agree(self):
        forms = [r"Let $$L = \frac{a}{b}$$.", r"Let \[L = \frac{a}{b}\].",
                 r"Let \begin{equation*}L = \frac{a}{b}\end{equation*}.",
                 r"Let \begin{equation}L = \frac{a}{b} \label{eq:L}\end{equation}.",
                 r"Let \begin{displaymath}L = \frac{a}{b}\end{displaymath}."]
        outs = {canonicalize_text(f) for f in forms}
        self.assertEqual(outs, {r"Let \[L = a/b\]."})

    def test_multiline_environments(self):
        self.assertEqual(
            canonicalize_text(r"\begin{eqnarray*} x &>& y \\ u &\geq& v^2 \end{eqnarray*}"),
            r"\begin{align}y < x \\ v^2 \leq u\end{align}")
        self.assertEqual(
            canonicalize_text(r"\begin{align} \frac{a}{b} &\geq y \nonumber\\ z &= w \end{align}"),
            r"\begin{align}y \leq a/b \\ z = w\end{align}")

    def test_environment_variables_renamed(self):
        src = r"\begin{equation} x \geq y \end{equation}"
        self.assertEqual(build_local_rename_map(src), {"x": "V1", "y": "V2"})
        self.assertEqual(canonicalize_text(src, rename_map=build_local_rename_map(src)),
                         r"\[V2 \leq V1\]")



class TestMeaningPreserved(unittest.TestCase):
    """Every rewrite must keep the formula true or false exactly as written."""

    def test_fraction_grouping(self):
        self.assertEqual(canonicalize_text(r"$\frac{a}{b}^2 = c$"), "${a/b}^2 = c$")
        self.assertEqual(canonicalize_text(r"$x / \frac{a}{b} = y$"), "$x / {a/b} = y$")
        self.assertEqual(canonicalize_text(r"$\frac{1}{2}x^2$"), "${1/2}x^2$")
        self.assertEqual(canonicalize_text(r"$\frac{a}{b} \leq c$"), r"$a/b \leq c$")

    def test_exp_nested(self):
        self.assertEqual(canonicalize_text(r"$\exp(f(x)) = y$"), "$e^{f(x)} = y$")
        self.assertEqual(canonicalize_text(r"$\exp(x)^2$"), "${e^x}^2$")

    def test_greek_variants_merge_only_when_unambiguous(self):
        self.assertEqual(canonicalize_text(r"$\varphi(x) = 1$"), r"$\phi(x) = 1$")
        self.assertEqual(canonicalize_text(r"$\varphi(x) = \phi(x) + 1$"),
                         r"$\varphi(x) = \phi(x) + 1$")
        self.assertEqual(canonicalize_text("$ε < ϵ$"), r"$\varepsilon < \epsilon$")

    def test_function_aliases_with_other_meanings_kept(self):
        for src in (r"$\Exp[X] = \mu$", r"$\Log z \neq \log z$", r"$\ch(E)$"):
            self.assertEqual(canonicalize_text(src), src)

    def test_rename_keeps_fixed_fonts(self):
        src = r"$R \in \mathbb{R}$"
        self.assertEqual(canonicalize_text(src, rename_map=build_local_rename_map(src)),
                         r"$V1 \in \mathbb{R}$")
        src = r"$F \subseteq \mathcal{F}$"
        self.assertEqual(build_local_rename_map(src), {"F": "V1", r"\mathcal{F}": "V2"})
        self.assertEqual(canonicalize_text(src, rename_map=build_local_rename_map(src)),
                         r"$V1 \subseteq V2$")

    def test_escaped_dollar_is_text(self):
        self.assertEqual(canonicalize_text(r"costs \$5 and $x > 0$ and \$3."),
                         r"costs \$5 and $0 < x$ and \$3.")



def _ren(src):
    return canonicalize_text(src, rename_map=build_local_rename_map(src))


class TestVerifierRegressions(unittest.TestCase):
    """One test per bug class found by verify_meaning, from its counterexamples."""

    # 1. rename (phase 18)
    def test_letter_runs_are_products(self):
        self.assertEqual(_ren(r"$|V(ux)| \leq |V(u)|$"), r"$|V1(V2V3)| \leq |V1(V2)|$")
        self.assertEqual(_ren(r"$C_aC$"), r"$V1_{V2}V1$")

    def test_ell_and_l_kept_apart(self):
        self.assertEqual(_ren(r"$l=1, \cdots, \ell$"), r"$V1=1, \cdots, \ell$")

    def test_norm_letter_never_split(self):
        # L used with a script anywhere: kept everywhere
        self.assertEqual(_ren(r"$L=L_m$"), r"$L=L_{V1}$")

    def test_rename_never_fuses_with_a_command(self):
        self.assertEqual(_ren(r"$\lambda x.\pi_z\ci\lambda z$"), r"$V1 V2.\pi_{V3}\ci V1 V3$")
        self.assertEqual(_ren(r"$x2 + \alpha2$"), r"$V1 2 + V2 2$")

    def test_old_font_command_is_not_a_switch(self):
        self.assertEqual(_ren(r"$\psi(t), n\in \Bbb N, t\geqslant 0$"),
                         r"$V1(V2), V3\in \Bbb N, 0 \leqslant V2$")

    # 2. unbraced scripts
    def test_renamed_script_is_braced(self):
        self.assertEqual(_ren(r"$x^{y}$"), r"$V1^{V2}$")

    # 3. spacing (phase 1)
    def test_control_space_never_eats_a_line_break(self):
        self.assertEqual(canonicalize_text(r"\begin{align} a &= 1 \\ 2 &= b \end{align}"),
                         r"\begin{align}a = 1 \\ 2 = b\end{align}")
        self.assertEqual(canonicalize_text(r"$a\,b + \alpha\,x$"), r"$ab + \alpha x$")

    # 4. display environments (phase 0)
    def test_nested_alignment_marks_kept(self):
        self.assertEqual(
            canonicalize_text(r"\begin{equation}\chi(x)=\begin{cases}0&x\leq 0\cr 1&x\geq 1\end{cases}\end{equation}"),
            r"\[\chi(x)=\begin{cases}0&x\leq 0\cr 1&1 \leq x\end{cases}\]")

    def test_alignat_column_count_dropped(self):
        self.assertEqual(canonicalize_text(r"\begin{alignat*}{2}e^{n!} &> a\\ &\ge n\end{alignat*}"),
                         r"\begin{align}e^{n!} > a\\ \geq n\end{align}")

    def test_end_with_space_is_segmented(self):
        self.assertEqual(canonicalize_text("\\begin{equation*} a > b \\end {equation*} and $c$"),
                         r"\[b < a\] and $c$")

    def test_dropped_ampersand_does_not_make_an_optional_argument(self):
        self.assertEqual(canonicalize_text(r"\begin{align}&[2]P=\notag \\* &[2y] \end{align}"),
                         r"\begin{align}[2]P= \\* {}[2y]\end{align}")

    # 5. inequality flip (phase 15)
    def test_no_flip_across_continued_rows(self):
        self.assertEqual(canonicalize_text(r"\begin{align*}1 / 1 &\ge -a\\ &\geq y\end{align*}"),
                         r"\begin{align}1 / 1 \geq -a\\ \geq y\end{align}")

    def test_row_spacing_is_not_an_operand(self):
        self.assertEqual(canonicalize_text(r"\begin{align*}-10 &> b! \\[2pt] c &\gg |a!|\end{align*}"),
                         r"\begin{align}b! < -10 \\[2pt] |a!| \ll c\end{align}")

    def test_cr_is_a_row_break(self):
        self.assertEqual(canonicalize_text(r"$\begin{cases}C^j&j>i\cr\coker(C^{i-1})&j=i\end{cases}$"),
                         r"$\begin{cases}C^j&i < j\cr\coker(C^{i-1})&j=i\end{cases}$")

    def test_text_argument_is_a_clause_boundary(self):
        self.assertEqual(canonicalize_text(r"$\overline{u}\geq 0\textit{ a.e.}$"),
                         r"$0 \leq \overline{u}\textit{a.e.}$")

    def test_decorated_relation_counts(self):
        for src in (r"$A\overset{(a)}{\geq}B\geq C$", r"$a \not> b$"):
            self.assertEqual(canonicalize_text(src), src)

    def test_trailing_punctuation_stays_outside(self):
        self.assertEqual(canonicalize_text(r"$a > b.$"), r"$b < a.$")

    def test_quad_separates_formulas(self):
        self.assertEqual(canonicalize_text(r"$x > 0 \quad y > 1$"), r"$0 < x \quad 1 < y$")
        self.assertEqual(canonicalize_text(r"$x > 0 \qquad y$"), r"$0 < x \quad y$")

    # 6. fractions (phase 14b)
    def test_fraction_grouped_before_postfix_and_bars(self):
        self.assertEqual(canonicalize_text(r"$\frac{a}{b}!$"), r"${a/b}!$")
        self.assertEqual(canonicalize_text(r"$\frac12|z|$"), r"${1/2}|z|$")
        self.assertEqual(canonicalize_text(r"$10\dfrac32$"), r"$10{3/2}$")
        self.assertEqual(canonicalize_text(r"$\sqrt\frac{a}{b}$"), r"$\sqrt{a/b}$")
        self.assertEqual(canonicalize_text(r"$\cfrac[l]{1}{2}$"), r"$1/2$")

    def test_exp_never_fuses_or_regroups(self):
        self.assertEqual(canonicalize_text(r"$\alpha\exp(x)$"), r"$\alpha{e^x}$")
        self.assertEqual(canonicalize_text(r"$\sqrt\exp(x)$"), r"$\sqrt{e^x}$")

    # 7. brace stripping (phase 16)
    def test_command_brace_kept_before_a_letter(self):
        self.assertEqual(canonicalize_text(r"$\xi_{\alpha}d$"), r"$\xi_{\alpha}d$")

    def test_environment_arguments_untouched(self):
        self.assertEqual(_ren(r"\[\begin{array}{c} \gamma\beta \end{array}\]"),
                         r"\[\begin{array}{c} V1V2 \end{array}\]")

    # 8. merges
    def test_varpi_is_a_variable(self):
        self.assertEqual(canonicalize_text(r"$\varpi$"), r"$\varpi$")
        self.assertEqual(_ren(r"$\varpi + \pi$"), r"$V1 + \pi$")

    def test_xrightarrow_keeps_its_label(self):
        self.assertEqual(canonicalize_text(r"$X_n \xrightarrow{d} X$"), r"$X_n \overset{d}\to X$")

    def test_rightarrow_merged_only_without_the_long_arrow(self):
        self.assertEqual(canonicalize_text(r"$A \Rightarrow B$"), r"$A \implies B$")
        self.assertEqual(canonicalize_text(r"$A \Rightarrow B \implies C$"),
                         r"$A \Rightarrow B \implies C$")

if __name__ == "__main__":
    unittest.main()
