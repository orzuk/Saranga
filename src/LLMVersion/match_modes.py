"""Selectable match modes for distillation scoring: M1 strict, M3 nested-ok.

Why this exists
---------------
The distillation pipeline decides two things by matching extractions against
the silver gold:

  * `prune_rules`  — is this extraction a false discovery? (drives the FDR gate)
  * `identify_dark_knowledge` — did the rules miss this gold item? (drives what
    we pay the LLM to write rules for)

Both used one rule: same type, one-to-one, containment >= 0.7. An audit of 395
base-parser "false positives" found only 9 were content the silver has nothing
for. The rest were nesting (47%), span boundaries (26%), duplicates (14%) and
type confusion (11%). So the gate was killing rules over labelling conventions.

The dominant case is a definition sitting inside a proof: the silver keeps the
proof as ONE node, our rules pull the definition out of it, and that scores as a
false positive. Or anticipated exactly this — `corpus/silver/STATS_80_checkpoint.md`
caveat 4: "Nested statements: ~1.8% of characters appear in two nodes ...
Accepted; de-duplicate at evaluation time (B1)." M3 is that de-duplication.

Modes
-----
M1  same type, greedy one-to-one, symmetric containment >= threshold.
    Byte-for-byte today's behaviour. Default everywhere.
M3  M1, plus: an extraction is not a false discovery if it is *contained in*
    any gold node of ANY type (`cover` of its tokens accounted for), and a gold
    item counts as found if the UNION of extractions covers it. Granularity- and
    label-blind by construction.

M3 is defined as a superset of M1 (`m1_matched or supported`) so it can never
call something a false discovery that M1 accepted. The gate only ever loosens,
which is what makes the switch safe to land.

Known blind spot, stated because it bit us once
-----------------------------------------------
M3 precision does NOT penalise duplication: a duplicate re-extraction is still
"contained in a gold node", so emitting the same statement five times costs
nothing. The `_merge_objects` dedup bug would have been invisible under M3.
Always report a duplication rate alongside it — see `count_duplicates`.

Similarity comes from the shared stack (`src/node_similarity.py`,
`Profile.SILVER`); this module adds no tokenizer of its own.
"""

from __future__ import annotations

MODES = ("m1", "m3")
DEFAULT_MODE = "m1"
DEFAULT_COVER = 0.7

#: Suggested FDR gate per mode. M1's 0.5 was tuned against a signal that is
#: ~98% labelling noise; under M3 that noise is gone, so the same alpha would
#: almost never trip and pruning would silently stop happening.
DEFAULT_ALPHA = {"m1": 0.5, "m3": 0.1}


def _ns():
    from node_similarity import Profile, tokenize, containment_sets
    return Profile, tokenize, containment_sets


def tokens(text):
    """Token set under the silver profile — the shared tokenizer, not a new one."""
    Profile, tokenize, _ = _ns()
    return tokenize(text or "", profile=Profile.SILVER)


def sym_containment(a, b):
    """|A n B| / min(|A|,|B|) — the metric the pipeline already matches on."""
    _, _, containment_sets = _ns()
    return containment_sets(a, b)


def coverage(part, whole):
    """|part n whole| / |part| — how much of `part` is accounted for by `whole`.

    One-sided on purpose. `sym_containment` uses min() as the denominator, which
    makes any short span inside a long node score 1.0 and is exactly what made
    nesting look like type confusion when we first measured it.
    """
    if not part:
        return 0.0
    return len(part & whole) / len(part)


def greedy_matched(ext_tokens, gold_tokens, threshold):
    """Indices of extractions matched one-to-one, highest similarity first.

    NOTE — faithful to production, including a bug. `sort(reverse=True)` on
    `(sim, i, j)` breaks ties by list index, and ties at 1.0 are common because
    ANY fully-nested span containment-matches its container at 1.0. So a nested
    definition can outrank the verbatim proof for the same gold node, and the
    EXACT match is then recorded as a false positive. Reproduced deliberately:
    M1 must stay byte-for-byte comparable with published numbers. M3 is immune,
    since the loser is rescued by the support test. Worth measuring separately —
    it likely inflates the M1 false-positive count on its own.
    """
    pairs = []
    for i, e in enumerate(ext_tokens):
        for j, g in enumerate(gold_tokens):
            s = sym_containment(e, g)
            if s >= threshold:
                pairs.append((s, i, j))
    pairs.sort(reverse=True)
    me, mg = set(), set()
    for _s, i, j in pairs:
        if i in me or j in mg:
            continue
        me.add(i)
        mg.add(j)
    return me


def classify_extractions(ext_texts, gold_texts, threshold, *, mode=DEFAULT_MODE,
                         support_texts=None, cover=DEFAULT_COVER):
    """Per-extraction True == counts as a hit (not a false discovery).

    `gold_texts`   gold of the type/group being scored (M1 pairs against these)
    `support_texts` gold of EVERY type in the paper. M3 only. The dominant
                   nesting case crosses groups (a definition inside a proof), so
                   scoping support to the group would miss precisely the case
                   this mode exists for. Falls back to `gold_texts` if omitted.
    """
    ext = [tokens(t) for t in ext_texts]
    gold = [tokens(t) for t in gold_texts]
    matched = greedy_matched(ext, gold, threshold)
    if mode == "m1":
        return [i in matched for i in range(len(ext))]

    support = [tokens(t) for t in (support_texts if support_texts is not None
                                   else gold_texts)]
    out = []
    for i, e in enumerate(ext):
        if i in matched:                      # M3 is a superset of M1
            out.append(True)
            continue
        out.append(any(coverage(e, g) >= cover for g in support if g))
    return out


def gold_is_found(gold_text, ext_texts, threshold, *, mode=DEFAULT_MODE,
                  cover=DEFAULT_COVER):
    """Did the rules already account for this gold item?

    Drives dark-knowledge selection, so it decides what we pay the LLM for.
    Under M3 a gold item counts as found when the UNION of extractions covers
    it — several nodes jointly covering one gold node is decomposition, not a
    miss, and generating a rule for it would only add a duplicate.
    """
    g = tokens(gold_text)
    if not g:
        return False
    ext = [tokens(t) for t in ext_texts]
    if mode == "m1":
        return any(sym_containment(e, g) >= threshold for e in ext)
    if any(sym_containment(e, g) >= threshold for e in ext):
        return True
    union = set().union(*ext) if ext else set()
    return coverage(g, union) >= cover


def count_duplicates(ext_texts, threshold=DEFAULT_COVER):
    """How many extractions restate one already emitted — M3's blind spot.

    Report this next to any M3 figure. Pairwise on the cleaned token sets, so a
    span re-extracted with slightly different boundaries still counts.
    """
    ext = [tokens(t) for t in ext_texts]
    dup = 0
    kept = []
    for e in ext:
        if not e:
            continue
        if any(sym_containment(e, k) >= threshold for k in kept):
            dup += 1
        else:
            kept.append(e)
    return dup
