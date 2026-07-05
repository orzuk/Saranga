"""Obfuscation levels for planted plagiarism (known-answer injection).

Mirrors the PAN corpus none/low/high axis, extended to the semantic levels the
old pipeline could not detect. L0-L1 are deterministic & API-free (good for CI /
fast loops). L2+ can optionally call an LLM via a ``paraphraser`` callback; a
rule-based fallback keeps them runnable offline, but the *honest* semantic
levels should use the LLM before trusting the detection-vs-obfuscation curve.

    L0 verbatim     copy unchanged
    L1 light        synonym + variable renaming + sentence reorder (rule-based)
    L2 paraphrase   meaning-preserving rewrite (LLM if given, else heavy rules)
    L3 structural   split/reorder into a differently-shaped statement (LLM)
    L4 conceptual   restate the idea in other vocabulary (LLM)
"""
from __future__ import annotations

import random
import re
from typing import Callable, Optional

Paraphraser = Callable[[str, int], str]  # (text, level) -> rewritten text

LEVELS = ["L0", "L1", "L2", "L3", "L4"]

# Small, domain-flavored synonym table for the rule-based levels.
_SYNONYMS = {
    "theorem": "result", "lemma": "claim", "prove": "establish",
    "proof": "argument", "shows": "demonstrates", "implies": "yields",
    "assume": "suppose", "hence": "therefore", "thus": "so",
    "bound": "estimate", "obtain": "derive", "if": "whenever",
    "number": "count", "graph": "network", "function": "map",
    "set": "collection", "sequence": "series", "algorithm": "procedure",
}
_VAR = re.compile(r"\b([a-zA-Z])\b")


def _synonym_swap(text: str, rng: random.Random, p: float = 0.6) -> str:
    def repl(m: re.Match) -> str:
        w = m.group(0)
        low = w.lower()
        if low in _SYNONYMS and rng.random() < p:
            rep = _SYNONYMS[low]
            return rep.capitalize() if w[:1].isupper() else rep
        return w
    return re.sub(r"[A-Za-z]+", repl, text)


def _rename_vars(text: str, rng: random.Random) -> str:
    """Consistently rename single-letter variables (notation obfuscation)."""
    letters = sorted({m.group(1) for m in _VAR.finditer(text)})
    if not letters:
        return text
    pool = [c for c in "abcdefghijklmnpqrstuvwxyz" if c not in letters]
    rng.shuffle(pool)
    mapping = {old: pool[i] for i, old in enumerate(letters) if i < len(pool)}
    return _VAR.sub(lambda m: mapping.get(m.group(1), m.group(1)), text)


def _reorder_sentences(text: str, rng: random.Random) -> str:
    sents = re.split(r"(?<=[.;])\s+", text)
    if len(sents) > 2:
        rng.shuffle(sents)
    return " ".join(sents)


def obfuscate(text: str, level: str, *, seed: int = 0,
              paraphraser: Optional[Paraphraser] = None) -> str:
    """Return an obfuscated version of `text` at the given level."""
    if not text:
        return text
    rng = random.Random(seed)
    if level == "L0":
        return text
    if level == "L1":
        return _reorder_sentences(_rename_vars(_synonym_swap(text, rng), rng), rng)
    lvl_int = LEVELS.index(level)
    if paraphraser is not None:
        return paraphraser(text, lvl_int)
    # Offline fallback for L2-L4: progressively heavier rule-based scrambling.
    out = _synonym_swap(text, rng, p=0.9)
    out = _rename_vars(out, rng)
    out = _reorder_sentences(out, rng)
    if lvl_int >= 3:
        words = out.split()
        rng.shuffle(words)  # destroys structure; placeholder for real LLM L3/L4
        out = " ".join(words)
    return out
