"""Edge-to-edge comparison — the simple sibling of `node_similarity`.

Edges in this schema carry no text of their own: an edge is
`{source, target, type, confidence}`. So edge similarity is entirely
structural and decomposes into three independent questions:

  1. do the ENDPOINTS correspond?   (needs a node correspondence, supplied by
     the caller — `graph_similarity` computes it)
  2. is the DIRECTION the same?     (A→B vs B→A)
  3. are the TYPES compatible?      (`uses` vs `generalizes` are near-synonyms
     by the schema's own admission; `uses` vs `proves` are not)

Direction is scored, not gated. `evaluate_extraction` already established the
convention that a correct edge stated backwards is worth partial credit
(`flipped_factor=0.5`) rather than counting as both a miss and a spurious edge —
the same double-penalty this project has been removing elsewhere.

Type compatibility mirrors `edge_types.py`: `generalizes`/`specializes` are
documented there as SUBTYPES of `uses`, so labelling one as the other is a
refinement disagreement, not a wrong edge.
"""
from __future__ import annotations

# ── Edge-type compatibility ──────────────────────────────────────────────────
# Grounded in edge_types.py's own grouping: DEPENDENCY_TYPES = {uses,
# generalizes, specializes}; STRUCTURAL_TYPES = {proves, solves, illustrates,
# tests, resolves}. Within-group confusions are cheap, cross-group are not.
EDGE_TYPE_COMPAT = {
    # generalizes/specializes ARE uses, refined. Calling one plain `uses` is
    # under-specification, not error.
    ("uses", "generalizes"): 0.8,
    ("uses", "specializes"): 0.8,
    # ...but generalizes vs specializes is a direction error in disguise.
    ("generalizes", "specializes"): 0.3,
    # Structural pairs that annotators genuinely confuse.
    ("proves", "uses"): 0.4,
    ("solves", "uses"): 0.4,
    ("illustrates", "uses"): 0.4,
    ("tests", "illustrates"): 0.6,
    ("resolves", "proves"): 0.5,
    ("solves", "resolves"): 0.5,
}

EDGE_TYPE_UNKNOWN = 0.15   # different types, no listed affinity
FLIPPED_FACTOR = 0.5       # credit for a correct edge stated backwards


def edge_type_compat(ta, tb, table=None, unknown=EDGE_TYPE_UNKNOWN):
    """Symmetric edge-type compatibility. Same type = 1.0."""
    if ta == tb:
        return 1.0
    table = EDGE_TYPE_COMPAT if table is None else table
    if (ta, tb) in table:
        return table[(ta, tb)]
    if (tb, ta) in table:
        return table[(tb, ta)]
    return unknown


def edge_key(edge, node_map=None):
    """(source, target) with node ids translated through `node_map`.

    `node_map` maps ids in this graph to shared correspondence ids (for
    n:m groups, several nodes map to the same group id).
    """
    s, t = edge.get("source"), edge.get("target")
    if node_map is not None:
        s, t = node_map.get(s, s), node_map.get(t, t)
    return s, t


def edge_sim(edge_a, edge_b, *, map_a=None, map_b=None,
             use_type=True, flipped_factor=FLIPPED_FACTOR):
    """Similarity of two edges in [0, 1].

    0 unless the endpoints correspond. Same direction scores the type
    compatibility; reversed direction scores it times `flipped_factor`.
    """
    sa, ta = edge_key(edge_a, map_a)
    sb, tb = edge_key(edge_b, map_b)
    if sa == ta or sb == tb:          # self-loop (e.g. an intra-group edge)
        return 0.0
    if (sa, ta) == (sb, tb):
        direction = 1.0
    elif (sa, ta) == (tb, sb):
        direction = flipped_factor
    else:
        return 0.0
    if not use_type:
        return direction
    return direction * edge_type_compat(edge_a.get("type", ""),
                                        edge_b.get("type", ""))


def match_edges(edges_a, edges_b, *, map_a=None, map_b=None, use_type=True,
                flipped_factor=FLIPPED_FACTOR, drop_intra_group=True):
    """Align two edge sets given a node correspondence.

    Returns (matches, only_a, only_b) where each match is
    `(edge_a, edge_b, sim, flipped)`.

    `drop_intra_group` removes edges whose endpoints collapse to the SAME
    correspondence id. Those are an artefact of n:m node grouping: if one
    extractor emits a single theorem "A and B" and the other splits it into A
    and B with an edge between them, that edge has no counterpart by
    construction and must not be counted against either side.
    """
    def prep(edges, nmap):
        out = []
        for e in edges:
            s, t = edge_key(e, nmap)
            if drop_intra_group and s == t:
                continue
            out.append((e, (s, t)))
        return out

    ea, eb = prep(edges_a, map_a), prep(edges_b, map_b)
    index = {}
    for j, (e, key) in enumerate(eb):
        index.setdefault(key, []).append(j)

    used_b, matches = set(), []
    unmatched_a = []
    for e, (s, t) in ea:
        cand = [j for j in index.get((s, t), []) if j not in used_b]
        flipped = False
        if not cand:
            cand = [j for j in index.get((t, s), []) if j not in used_b]
            flipped = bool(cand)
        if not cand:
            unmatched_a.append(e)
            continue
        # among candidates prefer the most type-compatible
        best = max(cand, key=lambda j: edge_type_compat(
            e.get("type", ""), eb[j][0].get("type", "")))
        used_b.add(best)
        sim = edge_sim(e, eb[best][0], map_a=map_a, map_b=map_b,
                       use_type=use_type, flipped_factor=flipped_factor)
        matches.append((e, eb[best][0], sim, flipped))
    unmatched_b = [e for j, (e, _) in enumerate(eb) if j not in used_b]
    return matches, unmatched_a, unmatched_b


def edge_metrics(matches, n_a, n_b):
    """Strict and soft edge P/R/F1.

    Strict counts a match as 1 regardless of direction/type; soft uses the
    similarity, so a flipped or mistyped edge lands between 0 and 1 instead of
    being scored as a clean hit or a clean miss.
    """
    strict = len(matches)
    soft = sum(s for _, _, s, _ in matches)
    flipped = sum(1 for _, _, _, f in matches if f)

    def prf(hit):
        p = hit / n_a if n_a else 0.0
        r = hit / n_b if n_b else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        return p, r, f

    ps, rs, fs = prf(strict)
    pf, rf, ff = prf(soft)
    return {
        "n_a": n_a, "n_b": n_b, "matched": strict, "flipped": flipped,
        "precision": ps, "recall": rs, "f1": fs,
        "precision_soft": pf, "recall_soft": rf, "f1_soft": ff,
    }


def edge_type_confusion(matches):
    """{(type_a, type_b): n} over matched edges — the labelling signal, kept
    out of the retrieval number."""
    from collections import Counter
    c = Counter()
    for a, b, *_ in matches:
        c[(a.get("type", ""), b.get("type", ""))] += 1
    return c
