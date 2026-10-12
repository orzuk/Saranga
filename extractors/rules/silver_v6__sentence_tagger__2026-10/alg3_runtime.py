#!/usr/bin/env python3
"""alg3 at parse time: the learned sentence tagger applied to one paper.

Copied into an extractor directory next to sentence_model.json and
alg3_features.py; distilled_rules.py there calls extract(text). Pure Python
(no numpy, no scikit-learn): a weighted sum per class over the sentence's
features, a softmax, the per-type thresholds, and the same decoding as training.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.realpath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import alg3_features as FT                                   # noqa: E402

MAX_SPAN = 8
_MODEL = None
_CACHE: dict = {}


def _model():
    global _MODEL
    if _MODEL is None:
        with open(os.path.join(_HERE, "sentence_model.json"), encoding="utf-8") as fh:
            _MODEL = json.load(fh)
    return _MODEL


def _probs(table: dict, feats: dict) -> list:
    z = list(table["intercept"])
    W = table["weights"]
    for name, v in feats.items():
        w = W.get(name)
        if w is not None:
            for k in range(len(z)):
                z[k] += w[k] * v
    m = max(z)
    e = [math.exp(x - m) for x in z]
    s = sum(e)
    return [x / s for x in e]


def span_end(sents, i: int, span: str) -> int:
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


def tag(text: str, fx: dict, sents: list) -> list:
    """[{type, start, end, first, last, p}] for one paper."""
    M = _model()
    A, S, tau = M["anchor"], M["span"], M["tau"]
    classes = A["classes"]
    none = classes.index("none")
    pv = FT.PaperView(text, fx, sents)
    feats = [FT.sentence_features(pv, i) for i in range(len(sents))]
    P = [_probs(A, f) for f in feats]
    if M.get("stage2"):                   # second pass: neighbours' first-pass probabilities
        B = M["stage2"]
        P2 = []
        for i, f in enumerate(feats):
            g = dict(f)
            g.update(FT.context_features(P, i, sents, classes))
            P2.append(_probs(B, g))
        P = P2
    out, covered = [], -1
    for i in range(len(sents)):
        if i <= covered:
            continue
        p = list(P[i])
        p[none] = -1.0
        c = max(range(len(p)), key=p.__getitem__)
        t = classes[c]
        if p[c] < tau.get(t, 1.01):
            continue
        sp = _probs(S, FT.span_features(pv, i, t))
        span = S["classes"][max(range(len(sp)), key=sp.__getitem__)]
        j = span_end(sents, i, span)
        out.append({"type": t, "start": sents[i].start, "end": sents[j].end,
                    "first": i, "last": j, "p": round(p[c], 4)})
        covered = j
    return out


def extract(text: str) -> list:
    """Distilled nodes in the parser's result format, cached per text."""
    key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
    if key not in _CACHE:
        if len(_CACHE) > 8:
            _CACHE.clear()
        import latex_facts
        import prose_units
        fx = latex_facts.extract_facts(text)
        sents = prose_units.sentences(fx)
        try:
            from latex_clean import clean_latex_to_text as _clean
        except Exception:                                    # noqa: BLE001
            def _clean(s):
                return s
        _CACHE[key] = [{"raw_latex": text[n["start"]:n["end"]],
                        "clean_text": _clean(text[n["start"]:n["end"]]),
                        "name": None, "env_name": "distilled",
                        "rule_name": f"alg3_p{n['p']}", "structure_type": n["type"]}
                       for n in tag(text, fx, sents)]
    return _CACHE[key]
