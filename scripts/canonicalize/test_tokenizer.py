"""Tests for math_tokenizer.py"""
import unittest
from scripts.canonicalize.math_tokenizer import (
    math_tokenize, soft_jaccard, hard_jaccard, token_sim,
)


class TestMathTokenize(unittest.TestCase):

    def test_basic_words_and_commands(self):
        tokens = math_tokenize(r"Let $x \in \mathbb{R}$")
        self.assertIn("let", tokens)
        self.assertIn("x", tokens)
        self.assertIn(r"\mathbb", tokens)
        self.assertIn(r"\in", tokens)

    def test_operators_detected(self):
        tokens = math_tokenize(r"$a + b * c$")
        self.assertIn("arith_plus", tokens)
        self.assertIn("arith_mul", tokens)
        self.assertIn("a", tokens)
        self.assertIn("b", tokens)

    def test_different_operators_different_tokens(self):
        t1 = math_tokenize(r"$a + b$")
        t2 = math_tokenize(r"$a * b$")
        self.assertIn("arith_plus", t1)
        self.assertNotIn("arith_mul", t1)
        self.assertIn("arith_mul", t2)
        self.assertNotIn("arith_plus", t2)

    def test_norm_detected(self):
        tokens = math_tokenize(r"$\|x\|_2$")
        self.assertIn("struct_norm", tokens)
        self.assertIn("struct_norm_2", tokens)

    def test_norm_without_subscript(self):
        tokens = math_tokenize(r"$\|x\|$")
        self.assertIn("struct_norm", tokens)

    def test_power_detected(self):
        tokens = math_tokenize(r"$x^2 + y^{10}$")
        self.assertIn("struct_pow_2", tokens)
        self.assertIn("struct_pow_10", tokens)

    def test_relation_lt(self):
        tokens = math_tokenize(r"$a < b$")
        self.assertIn("rel_lt", tokens)

    def test_relation_command(self):
        tokens = math_tokenize(r"$a \leq b$")
        self.assertIn(r"\leq", tokens)       # natural token
        self.assertIn("rel_leq", tokens)      # constructed token

    def test_set_braces(self):
        tokens = math_tokenize(r"$\{x | x > 0\}$")
        self.assertIn("struct_set", tokens)

    def test_bigop(self):
        tokens = math_tokenize(r"$\sum_{i=1}^n x_i$")
        self.assertIn(r"\sum", tokens)
        self.assertIn("struct_bigop_sum", tokens)


class TestTokenSim(unittest.TestCase):

    def test_identical(self):
        self.assertEqual(token_sim("norm_2", "norm_2"), 1.0)

    def test_constructed_same_category_diff_param(self):
        s = token_sim("struct_norm_2", "struct_norm_1")
        self.assertEqual(s, 0.7)

    def test_constructed_same_regardless_of_name_length(self):
        # The key property: norm_2/norm_1 gets SAME score as pow_2/pow_1
        s1 = token_sim("struct_norm_2", "struct_norm_1")
        s2 = token_sim("struct_pow_2", "struct_pow_1")
        self.assertEqual(s1, s2)  # both 0.7, no naming artifact

    def test_arith_plus_minus(self):
        s = token_sim("arith_plus", "arith_minus")
        self.assertEqual(s, 0.3)

    def test_arith_plus_mul(self):
        s = token_sim("arith_plus", "arith_mul")
        self.assertEqual(s, 0.1)

    def test_rel_leq_geq(self):
        s = token_sim("rel_leq", "rel_geq")
        self.assertEqual(s, 0.5)

    def test_rel_leq_lt(self):
        s = token_sim("rel_leq", "rel_lt")
        self.assertEqual(s, 0.8)

    def test_constructed_vs_natural(self):
        self.assertEqual(token_sim("arith_plus", "continuous"), 0.0)

    def test_natural_morphological(self):
        # Same root: isometry vs isometric
        s = token_sim("isometry", "isometric")
        self.assertGreater(s, 0.8)

    def test_natural_unrelated(self):
        s = token_sim("matrix", "probability")
        self.assertLess(s, 0.5)

    def test_bigop_similarity(self):
        s = token_sim("struct_bigop_sum", "struct_bigop_prod")
        self.assertEqual(s, 0.3)


class TestSoftJaccard(unittest.TestCase):

    def test_identical_sets(self):
        s = soft_jaccard({"a", "b"}, {"a", "b"})
        self.assertEqual(s, 1.0)

    def test_disjoint_natural(self):
        s = soft_jaccard({"cat", "dog"}, {"fish", "bird"})
        self.assertLess(s, 0.3)

    def test_soft_beats_hard_on_near_miss(self):
        tokens_a = {"struct_norm_2", "x", "rel_leq"}
        tokens_b = {"struct_norm_1", "x", "rel_geq"}
        hard = hard_jaccard(tokens_a, tokens_b)
        soft = soft_jaccard(tokens_a, tokens_b)
        self.assertGreater(soft, hard)

    def test_operators_add_discrimination(self):
        # With operators as tokens, a+b and a*b are now distinguishable
        t1 = math_tokenize("$a + b$")
        t2 = math_tokenize("$a * b$")
        t3 = math_tokenize("$a + b$")
        self.assertGreater(soft_jaccard(t1, t3), soft_jaccard(t1, t2))


if __name__ == "__main__":
    unittest.main()
