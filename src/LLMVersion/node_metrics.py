#!/usr/bin/env python3
"""Node-level metrics: predicted nodes of one paper against its reference nodes.

Every metric works on the whole paper at once, on (type, text) items, and
returns a CREDIT per item: how much each prediction counts as correct (the
precision numerator) and how much each reference node counts as found (the
recall numerator). Pooled over items and papers:

    precision = sum(prediction credits) / number of predictions
    recall    = sum(reference credits)  / number of reference nodes

Overlap is token containment, |A n B| / min(|A|, |B|) (match_modes.sym_containment),
and a pair qualifies at overlap >= threshold (0.7).

  m1g  (headline)  one-to-one; a pair earns the TYPE COMPATIBILITY of its two
                   types (node_similarity.type_compat: same type 1.0, theorem vs
                   claim 0.8, unlisted pairs 0.2, proof vs definition 0.0);
                   pairs are taken greedily by compatibility x overlap, ties
                   broken by Jaccard (the closer length wins). With identical
                   types it is the type-match criterion of span-level IE
                   evaluation (MUC-5, SemEval-2013 Task 9.1), with an overlap
                   threshold in place of exact boundaries.
  m1   strict      the same, credit 1 for the same type and 0 otherwise.
  m3   nesting-ok  m1, plus: a prediction counts if >= `cover` of its tokens lie
                   inside ANY reference node; a reference node counts as found
                   if the predictions of its type together cover >= `cover` of
                   it. Kept as a diagnostic: it rewards splitting a node into
                   pieces (each piece counts as correct).

A new metric is a function with the signature of `_m1g` added to METRICS.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))                  # src/, for node_similarity
import match_modes as mm                                    # noqa: E402
import node_similarity as ns                                # noqa: E402

THRESHOLD = 0.7
COVER = 0.7


def _jaccard(a, b) -> float:
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def _one_to_one(P, G, weight, th):
    """Greedy one-to-one pairing: pairs with overlap >= th and weight > 0, best
    weight x overlap first, then the closer length. Returns {i: (j, weight)}."""
    pairs = []
    for i, (tp, a) in enumerate(P):
        for j, (tg, b) in enumerate(G):
            w = weight(tp, tg)
            if w <= 0:
                continue
            ov = mm.sym_containment(a, b)
            if ov >= th:
                pairs.append((w * ov, _jaccard(a, b), i, j, w))
    pairs.sort(key=lambda x: (-x[0], -x[1], x[2], x[3]))
    out, used = {}, set()
    for _s, _jac, i, j, w in pairs:
        if i in out or j in used:
            continue
        out[i] = (j, w)
        used.add(j)
    return out


def _credits(P, G, weight, th):
    m = _one_to_one(P, G, weight, th)
    pc = [m[i][1] if i in m else 0.0 for i in range(len(P))]
    gc = [0.0] * len(G)
    for i, (j, w) in m.items():
        gc[j] = w
    return pc, gc


def _m1g(P, G, th=THRESHOLD, cover=COVER):
    return _credits(P, G, ns.type_compat, th)


def _m1(P, G, th=THRESHOLD, cover=COVER):
    return _credits(P, G, lambda a, b: 1.0 if a == b else 0.0, th)


def _m3(P, G, th=THRESHOLD, cover=COVER):
    pc, gc = _m1(P, G, th, cover)
    for i, (_t, a) in enumerate(P):              # inside some reference node, any type
        if not pc[i] and any(b and mm.coverage(a, b) >= cover for _tg, b in G):
            pc[i] = 1.0
    for j, (tg, b) in enumerate(G):              # covered by the predictions of its type
        if gc[j] or not b:
            continue
        same = [a for tp, a in P if tp == tg]
        if any(mm.sym_containment(a, b) >= th for a in same) or \
                (same and mm.coverage(b, set().union(*same)) >= cover):
            gc[j] = 1.0
    return pc, gc


METRICS = {"m1g": _m1g, "m1": _m1, "m3": _m3}


def score(preds, golds, metric: str = "m1g", threshold: float = THRESHOLD,
          cover: float = COVER):
    """(prediction credits, reference credits) for one paper. `preds` and
    `golds` are [(type, text)]."""
    P = [(t, mm.tokens(x)) for t, x in preds]
    G = [(t, mm.tokens(x)) for t, x in golds]
    return METRICS[metric](P, G, threshold, cover)
