#!/usr/bin/env python3
"""Unit rules: how a distilled rule of the unit algorithm turns prose into nodes.

A unit rule is a record (see scripts/distill_units.py, which learns them):

    {"uid": 7, "name": "we_say_def", "type": "definition",
     "regex": "\\bwe\\s+say\\b", "flags": "i", "span": "1",
     "precision": 0.93}

It is tried on every prose sentence of a paper (src/prose_units.py: outside
environments, proofs and floats). Where `regex` matches a sentence, that
sentence is the ANCHOR of a node of type `type`, and `span` says how far the
node extends from it:

    "1".."4"   that many sentences, within the anchor's region
    "para"     to the end of the anchor's paragraph (at most MAX_SPAN sentences)

When several rules fire on one sentence the one with the highest measured
precision decides; a sentence already inside an emitted node cannot anchor
another. The same function serves distillation (scoring a candidate rule) and
the parser (through a generated distilled_rules.py importer), so a rule behaves
identically in both.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))          # src/, for latex_facts, prose_units

MAX_SPAN = 8
SPANS = ("1", "2", "3", "4", "para")
_FLAGS = {"i": re.I, "s": re.S, "m": re.M, "x": re.X}


def compile_rule(rule: dict):
    """The rule's compiled regex, or None if it does not compile."""
    flags = 0
    for ch in str(rule.get("flags", "")):
        flags |= _FLAGS.get(ch, 0)
    try:
        return re.compile(rule["regex"], flags)
    except (re.error, KeyError, TypeError):
        return None


def span_end(sents, i: int, span: str) -> int:
    """Index of the last sentence of a node anchored at sentence i."""
    s = sents[i]
    if span == "para":
        j = i
        while (j + 1 < len(sents) and j + 1 - i < MAX_SPAN
               and sents[j + 1].region == s.region and sents[j + 1].para == s.para):
            j += 1
        return j
    n = int(span) if span.isdigit() else 1
    j = i
    while j + 1 < len(sents) and j + 1 - i < n and sents[j + 1].region == s.region:
        j += 1
    return j


def fires(compiled, text: str) -> bool:
    try:
        return compiled.search(text) is not None
    except Exception:
        return False


def fire_set(compiled, text: str, sents) -> set:
    """Indices of the sentences where a compiled rule fires."""
    return {i for i, s in enumerate(sents) if fires(compiled, text[s.start:s.end])}


def select(sents, rules: list[dict], fire_sets: dict) -> list[dict]:
    """The nodes a rule set produces, given where each rule fires
    (`fire_sets`: uid -> sentence indices). The most precise rule firing on a
    sentence decides; a sentence inside an emitted node anchors no other.
    Returns [{type, start, end, first, last, uid}] in document order."""
    order = sorted(rules, key=lambda r: (-float(r.get("precision", 0)), r.get("uid", 0)))
    at = {}
    for r in order:
        for i in fire_sets.get(r.get("uid"), ()):
            at.setdefault(i, r)
    out, covered = [], -1
    for i in sorted(at):
        if i <= covered:
            continue
        r = at[i]
        j = span_end(sents, i, str(r.get("span", "1")))
        out.append({"type": r["type"], "start": sents[i].start, "end": sents[j].end,
                    "first": i, "last": j, "uid": r.get("uid")})
        covered = j
    return out


def apply_rules(text: str, sents, rules: list[dict]) -> list[dict]:
    """Nodes produced by `rules` on one paper (`sents`: prose_units.sentences)."""
    fire_sets = {}
    for r in rules:
        c = compile_rule(r)
        if c is not None:
            fire_sets[r.get("uid")] = fire_set(c, text, sents)
    return select(sents, rules, fire_sets)


# ---- runtime: the parser's view ------------------------------------------------

_CACHE: dict = {}


def _sentences_of(text: str):
    import latex_facts
    import prose_units
    return prose_units.sentences(latex_facts.extract_facts(text))


def extract(text: str, rules_path: str) -> list[dict]:
    """Distilled nodes for the parser, in its result format. `text` is what the
    parser hands distilled rules (the prepared document body); `rules_path` a
    unit_rules.json. Cached per (text, rule file), since the parser asks once
    per node type."""
    try:
        stamp = os.path.getmtime(rules_path)
    except OSError:
        return []
    key = (hashlib.sha1(text.encode("utf-8", "replace")).hexdigest(), rules_path, stamp)
    if key not in _CACHE:
        if len(_CACHE) > 8:
            _CACHE.clear()
        with open(rules_path, encoding="utf-8") as fh:
            rules = [r for r in json.load(fh).get("rules", []) if r.get("active", True)]
        try:
            from latex_clean import clean_latex_to_text as _clean
        except Exception:
            def _clean(s):
                return s
        nodes = apply_rules(text, _sentences_of(text), rules)
        _CACHE[key] = [{"raw_latex": text[n["start"]:n["end"]],
                        "clean_text": _clean(text[n["start"]:n["end"]]),
                        "name": None, "env_name": "distilled",
                        "rule_name": f"unit_{n['uid']}", "structure_type": n["type"]}
                       for n in nodes]
    return _CACHE[key]


IMPORTER = '''# AUTO-GENERATED by scripts/distill_units.py: distilled unit rules.
# The rules are data (unit_rules.json next to this file); unit_rules.py applies
# them, the same code that scored them during distillation.
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.realpath(__file__))
_RULES = _os.path.join(_HERE, "unit_rules.json")
_sys.path.insert(0, {llm_dir!r})
import unit_rules as _ur


def extract_distilled_all(text):
    return _ur.extract(text, _RULES)
'''


def write_importer(snapshot_dir: str, types) -> str:
    """distilled_rules.py for a snapshot holding unit_rules.json: one
    extract_distilled_<type>(text) per node type, as the parser expects."""
    lines = [IMPORTER.format(llm_dir=_HERE)]
    for t in types:
        lines.append(f"\ndef extract_distilled_{t}(text):\n"
                     f"    return [d for d in _ur.extract(text, _RULES) "
                     f"if d['structure_type'] == {t!r}]\n")
    path = os.path.join(snapshot_dir, "distilled_rules.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(lines))
    return path
