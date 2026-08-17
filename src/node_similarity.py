"""Single source of truth for comparing two knowledge-graph nodes.

Every place in the project that asks "how similar are these two nodes?" should
come here — cross-paper alignment (`graph_alignment`), extraction evaluation
(`evaluate_extraction`), rule distillation (`distillation_analysis`,
`silver_distillation_sequential`), and the discovery tasks. Comparing two
*papers* and comparing two *extractions of the same paper* are the same
operation with different flags, so they must not drift apart.

Before this module there were six text-similarity implementations, four
`node_text`s and three type policies. They disagreed materially: the same
`\\begin{theorem}...` vs bare-statement pair scored 0.643 / 0.737 / 1.000
depending on which module you called, `\\alpha` tokenised as `alpha` in one and
`\\alpha` in another, and empty-vs-empty was 1.0 in one and 0.0 elsewhere. A
`threshold=0.5` therefore meant different things in different files.

PROFILES — behaviour-preserving migration
-----------------------------------------
Unifying the code must not silently move anyone's numbers, so each historical
behaviour is preserved as a named profile. Callers migrate by naming their
current profile (numbers unchanged), and switching to CANONICAL later is then a
deliberate, reviewable decision rather than a side effect of refactoring.

METRICS
-------
"jaccard" | "containment" (lexical set metrics) | "embedding" (cosine over
sentence embeddings, via scripts/embedding_sigma.py, imported lazily).

  ALIGNMENT     graph_alignment.py       LaTeX-command-aware tokens, no braces
  EXTRACTION    evaluate_extraction.py   punctuation-stripped (loses backslashes)
  DISTILLATION  distillation_analysis    LaTeX + brace/dollar tokens
  SILVER        silver_distillation_seq  DISTILLATION + clean_latex_to_text
  CANONICAL     recommended default      == ALIGNMENT tokens, explicit empties

TYPE HANDLING
-------------
Type is a *graded* signal, not a gate. `TYPE_COMPAT` scores theorem↔proposition
at 0.9 because that confusion is near-meaningless for retrieval. Three policies
are available (`TypePolicy`); scoring type-blind and reporting a separate
type-confusion matrix is what keeps a mislabelled-but-correctly-found node from
being punished twice (once as FP under one type, once as FN under the other).

GRANULARITY
-----------
Level-2 nodes (`proof_step`, `algorithm_step`) are a *decomposition* of their
parent's span, not new content. An extractor that does not emit steps must not
be penalised against one that does, so `collapse_to_level1()` normalises both
sides before matching. See its docstring.
"""
from __future__ import annotations

import re
from enum import Enum

# ── Thresholds ───────────────────────────────────────────────────────────────
# One place, so "0.5" means the same thing everywhere. Historical values are
# kept under their own names rather than silently harmonised.
THRESHOLD_ALIGNMENT = 0.5      # cross-paper node alignment
THRESHOLD_EXTRACTION = 0.5     # extraction vs gold
THRESHOLD_DISTILLATION = 0.7   # rule-vs-silver matching
THRESHOLD_DEFAULT = 0.5


class Profile(str, Enum):
    ALIGNMENT = "alignment"
    EXTRACTION = "extraction"
    DISTILLATION = "distillation"
    SILVER = "silver"
    CANONICAL = "canonical"


class TypePolicy(str, Enum):
    BLIND = "blind"       # ignore type entirely; report confusion separately
    GRADED = "graded"     # multiply similarity by TYPE_COMPAT (alignment default)
    STRICT = "strict"     # zero unless types are equal (legacy hard gate)


# ── Type compatibility ───────────────────────────────────────────────────────
# Moved verbatim from graph_alignment.py — that module re-exports these names,
# so the table has exactly one definition.
TYPE_COMPAT = {
    ("theorem", "lemma"): 0.9,
    ("theorem", "proposition"): 0.9,
    ("theorem", "corollary"): 0.85,
    ("theorem", "claim"): 0.8,
    ("lemma", "proposition"): 0.9,
    ("lemma", "corollary"): 0.85,
    ("lemma", "claim"): 0.8,
    ("proposition", "corollary"): 0.85,
    ("proposition", "claim"): 0.8,
    ("corollary", "claim"): 0.8,
    ("conjecture", "theorem"): 0.7,
    ("conjecture", "lemma"): 0.7,
    ("conjecture", "proposition"): 0.7,
    ("conjecture", "corollary"): 0.65,
    ("conjecture", "claim"): 0.75,
    ("conjecture", "problem"): 0.8,
    ("problem", "theorem"): 0.5,
    ("problem", "conjecture"): 0.8,
    ("problem", "definition"): 0.7,
    ("definition", "theorem"): 0.1,
    ("definition", "lemma"): 0.1,
    ("definition", "proposition"): 0.1,
    ("definition", "corollary"): 0.1,
    ("definition", "claim"): 0.1,
    ("definition", "conjecture"): 0.1,
    ("proof", "theorem"): 0.05,
    ("proof", "lemma"): 0.05,
    ("proof", "definition"): 0.0,
    ("example", "exercise"): 0.6,
    ("example", "theorem"): 0.1,
    ("example", "definition"): 0.2,
    ("exercise", "theorem"): 0.1,
    ("exercise", "definition"): 0.2,
    ("algorithm", "theorem"): 0.1,
    ("algorithm", "definition"): 0.1,
    ("algorithm", "proof"): 0.1,
    ("algorithm", "example"): 0.3,
    ("algorithm", "problem"): 0.35,
    ("equation", "theorem"): 0.2,
    ("equation", "definition"): 0.55,
    ("equation", "lemma"): 0.2,
    ("equation", "proof"): 0.1,
    ("remark", "theorem"): 0.1,
    ("remark", "definition"): 0.1,
    ("remark", "proof"): 0.1,
    ("remark", "example"): 0.3,
    ("property", "proposition"): 0.95,
    ("property", "theorem"): 0.9,
    ("property", "lemma"): 0.85,
    ("property", "corollary"): 0.85,
    ("property", "claim"): 0.85,
    ("fact", "proposition"): 0.9,
    ("fact", "theorem"): 0.85,
    ("fact", "lemma"): 0.85,
    ("fact", "claim"): 0.9,
    ("fact", "remark"): 0.5,
    ("observation", "remark"): 0.85,
    ("observation", "claim"): 0.85,
    ("observation", "proposition"): 0.7,
    ("principle", "theorem"): 0.85,
    ("principle", "proposition"): 0.85,
    ("principle", "claim"): 0.8,
    ("result", "theorem"): 0.85,
    ("result", "proposition"): 0.85,
}

# Pairs NOT in the historical table that the corpus says are real confusions.
# Kept OPT-IN so migrating changes no numbers: pass
# `table={**TYPE_COMPAT, **TYPE_COMPAT_PROPOSED}` to opt in. Measured on the
# tier1 eval dumps, `problem`->`equation` and step<->parent were the common
# unlisted confusions.
TYPE_COMPAT_PROPOSED = {
    ("proof", "proof_step"): 0.7,
    ("algorithm", "algorithm_step"): 0.7,
    ("problem", "equation"): 0.4,
    ("problem", "open_problem"): 0.85,
    ("open_problem", "conjecture"): 0.8,
    ("assumption", "definition"): 0.5,
}

TYPE_COMPAT_UNKNOWN = 0.1  # different types, no listed affinity


def type_compat(ta, tb, table=None, unknown=TYPE_COMPAT_UNKNOWN):
    """Symmetric type-compatibility score. Same type = 1.0."""
    if ta == tb:
        return 1.0
    table = TYPE_COMPAT if table is None else table
    if (ta, tb) in table:
        return table[(ta, tb)]
    if (tb, ta) in table:
        return table[(tb, ta)]
    return unknown


# ── Tokenizers ───────────────────────────────────────────────────────────────
_TOKEN_ALIGNMENT = re.compile(r"[a-zA-Z]+|\\[a-zA-Z]+|[0-9]+")
_TOKEN_DISTILL = re.compile(r"\\[a-zA-Z]+|[a-zA-Z]+|[0-9]+|\$|[{}()[\]]")
_EXTRACTION_PUNCT = ".,;:!?()[]{}\"'`\\/|<>=+-*^~#@$%&_"


def tokenize(text, profile=Profile.CANONICAL):
    """Token SET for `text` under `profile`.

    Profiles differ in how they treat LaTeX. ALIGNMENT/CANONICAL keep control
    sequences whole (`\\alpha`); EXTRACTION strips backslashes as punctuation
    (so `\\in` collides with the English word "in" — preserved only for
    backward compatibility); DISTILLATION additionally emits `$`, braces and
    brackets as tokens, which inflates similarity between any two LaTeX spans.
    """
    if not text:
        return set()
    text = str(text)
    if profile == Profile.EXTRACTION:
        text = text.lower()
        for ch in _EXTRACTION_PUNCT:
            text = text.replace(ch, " ")
        return set(text.split())
    if profile in (Profile.DISTILLATION, Profile.SILVER):
        return set(_TOKEN_DISTILL.findall(text))
    return set(t.lower() for t in _TOKEN_ALIGNMENT.findall(text))


def normalize_latex(text):
    """Whitespace/format/citation normalisation used by the distillation path."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text))
    text = re.sub(r"\\textit\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\textbf\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\emph\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\cite\{[^}]+\}", "", text)
    text = re.sub(r"~\\cite\{[^}]+\}", "", text)
    return text.strip().lower()


def _prepare(text, profile):
    """Profile-specific text preparation applied before tokenising."""
    if profile in (Profile.DISTILLATION, Profile.SILVER):
        if profile == Profile.SILVER:
            try:                                    # optional dependency
                from latex_clean import clean_latex_to_text
                text = clean_latex_to_text(text or "").lower()
            except Exception:
                pass
        return normalize_latex(text)
    return text


# ── Node text ────────────────────────────────────────────────────────────────
def node_text(node, *, include_name=True, include_type=False,
              prefer_clean_text=False):
    """Concatenated text content of a node.

    `include_name` is on by default (alignment behaviour); `evaluate_extraction`
    historically omitted it, so it passes include_name=False.
    """
    parts = []
    if include_type:
        t = node.get("type") or node.get("kind") or ""
        if t:
            parts.append("[%s]" % t)
    if include_name and node.get("name"):
        parts.append(str(node["name"]))
    if prefer_clean_text and node.get("clean_text"):
        parts.append(str(node["clean_text"]))
    elif node.get("statement"):
        parts.append(str(node["statement"]))
    for fld in ("assumptions", "conclusions"):
        v = node.get(fld)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
        elif v:
            parts.append(str(v))
    return " ".join(parts)


def node_proof_text(node):
    """Proof-side text: `proof_strategy` only (empty for non-proof nodes)."""
    v = node.get("proof_strategy")
    return str(v) if v else ""


# ── Set metrics ──────────────────────────────────────────────────────────────
def jaccard_sets(a, b, *, empty_empty=0.0):
    """|A ∩ B| / |A ∪ B|.

    `empty_empty` exists because the historical implementations disagreed:
    evaluate_extraction returned 1.0 for two empty texts, everything else 0.0.
    """
    if not a and not b:
        return empty_empty
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def containment_sets(a, b, *, empty_empty=0.0):
    """|A ∩ B| / min(|A|, |B|) — right metric when one side systematically
    over- or under-spans the other (e.g. env header included vs not)."""
    if not a and not b:
        return empty_empty
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


_METRICS = {"jaccard": jaccard_sets, "containment": containment_sets}


# ---------------------------------------------------------------------------
# Run-wide match metric — ONE variable, on purpose
# ---------------------------------------------------------------------------
# The distillation stack has two similarity wrappers:
#   silver_distillation_sequential.jaccard_similarity  (Profile.SILVER)
#   distillation_analysis.jaccard_similarity           (Profile.DISTILLATION)
# The first scores baseline/post metrics, the second scores the prune gate.
# They used to hold SEPARATE module globals, so a caller that set one and not
# the other silently scored the two halves of a run by different metrics —
# choose containment, still prune on jaccard. 14 of 16 call sites set only one.
#
# Both wrappers now read THIS variable at call time, so the two cannot diverge.
# Set it through set_match_metric() rather than assigning module globals.
MATCH_METRIC = "jaccard"


def set_match_metric(metric: str) -> str:
    """Set the run-wide match metric. Returns the previous value."""
    global MATCH_METRIC
    if metric not in _METRICS:
        raise ValueError(
            f"unknown match metric {metric!r}; expected one of {sorted(_METRICS)}")
    prev, MATCH_METRIC = MATCH_METRIC, metric
    return prev


def get_match_metric() -> str:
    return MATCH_METRIC


# ── Embedding backend ────────────────────────────────────────────────────────
# A third way to ask "how similar are these two nodes?": embed both texts and
# take cosine. Lexical and embedding similarity fail differently — Jaccard
# cannot see that "is bounded" and "is finite" agree, and cosine cannot see
# that one span is literally a substring of another — so this is a selectable
# metric, not a replacement.
#
# The heavy dependency (sentence-transformers) is imported lazily, so nothing
# here costs anything unless `metric="embedding"` is actually requested.
# Implementation lives in scripts/embedding_sigma.py, which already has the
# model singleton, an lru_cache over texts, and precompute_paper_embeddings().
_embedding_module = None


def _load_embedding_module():
    global _embedding_module
    if _embedding_module is None:
        import os
        import sys as _sys
        scripts = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        try:
            import embedding_sigma as _mod
        except ImportError as e:                       # pragma: no cover
            raise ImportError(
                "metric='embedding' needs sentence-transformers "
                "(pip install sentence-transformers). Underlying error: %s" % e)
        _embedding_module = _mod
    return _embedding_module


def embedding_available():
    """True if the embedding backend can actually run here.

    Probes the heavy dependency itself: embedding_sigma imports fine with only
    numpy present, and would not fail until the model is first loaded.
    """
    try:
        import importlib.util
        if importlib.util.find_spec("sentence_transformers") is None:
            return False
        _load_embedding_module()
        return True
    except Exception:
        return False


def embed_node(node):
    """Vector for a node, via scripts/embedding_sigma (cached)."""
    return _load_embedding_module().embed_node(node)


def embedding_node_sim(node_a, node_b, *, use_type=True):
    """Cosine similarity of the two node embeddings, optionally damped by
    `type_compat` — the same composition the lexical path uses, so switching
    metric does not silently switch type policy too."""
    mod = _load_embedding_module()
    return mod.sigma(node_a, node_b) if use_type else mod.sigma_no_type(
        node_a, node_b)


def text_sim(text_a, text_b, *, profile=Profile.CANONICAL, metric="jaccard",
             empty_empty=None):
    """Similarity between two raw strings under `profile`."""
    if empty_empty is None:
        empty_empty = 1.0 if profile == Profile.EXTRACTION else 0.0
    ta = tokenize(_prepare(text_a, profile), profile)
    tb = tokenize(_prepare(text_b, profile), profile)
    return _METRICS[metric](ta, tb, empty_empty=empty_empty)


def node_sim(node_a, node_b, *, profile=Profile.CANONICAL, metric="jaccard",
             type_policy=TypePolicy.GRADED, text_fn=None, **text_kw):
    """Similarity between two nodes: text similarity, modulated by type policy.

    `metric` selects the backend: "jaccard" and "containment" are lexical set
    metrics; "embedding" is cosine over sentence embeddings (lazy, optional
    dependency). They fail differently and are meant to be chosen per task —
    see the embedding-backend note above.

    BLIND  -> pure text similarity (use this for retrieval, and report a
              type-confusion matrix separately)
    GRADED -> text × type_compat  (cross-paper alignment default)
    STRICT -> 0 unless types are equal (legacy; double-penalises type confusion)
    """
    if metric == "embedding":
        # embedding_sigma applies type_compat itself, so route the policy
        # through rather than multiplying twice.
        return embedding_node_sim(node_a, node_b,
                                  use_type=type_policy == TypePolicy.GRADED)
    get = text_fn or (lambda n: node_text(n, **text_kw))
    s = text_sim(get(node_a), get(node_b), profile=profile, metric=metric)
    if type_policy == TypePolicy.BLIND:
        return s
    ta, tb = node_a.get("type", ""), node_b.get("type", "")
    if type_policy == TypePolicy.STRICT:
        return s if ta == tb else 0.0
    return s * type_compat(ta, tb)


# ── Hierarchy ────────────────────────────────────────────────────────────────
LEVEL2_TYPES = ("proof_step", "algorithm_step")


def collapse_to_level1(nodes, edges=None, level2_types=LEVEL2_TYPES):
    """Fold Level-2 step nodes into their parents so two extractions can be
    compared at a common granularity.

    A step is a decomposition of its parent's verbatim span, not new content.
    Comparing a stepless extraction against a stepped one without collapsing
    turns every step in the richer graph into a false negative, which measures
    granularity rather than quality.

    The parent's text becomes parent ∪ children (a union, not a replacement)
    because some extractors leave the parent thin and put the substance in the
    steps; the union is symmetric and loses nothing either way. Steps whose
    parent is absent are promoted to a synthetic parent so their content still
    participates. Edges incident to a step are lifted onto its parent, since
    otherwise edge metrics break as soon as one side emits steps.

    Returns (nodes, edges) with no Level-2 nodes. Inputs are not mutated.
    """
    by_id = {n.get("id"): n for n in nodes}
    kids = {}
    for n in nodes:
        if n.get("type") in level2_types:
            kids.setdefault(n.get("parent_id"), []).append(n)

    out, remap = [], {}
    for n in nodes:
        if n.get("type") in level2_types:
            parent = by_id.get(n.get("parent_id"))
            remap[n.get("id")] = parent.get("id") if parent else n.get("id")
            if parent is not None:
                continue
        m = dict(n)
        children = kids.get(n.get("id"), [])
        if children:
            children = sorted(children, key=lambda c: c.get("step_order") or 0)
            extra = " ".join(str(c.get("statement") or "") for c in children)
            m["statement"] = ((m.get("statement") or "") + " " + extra).strip()
            m["n_steps_collapsed"] = len(children)
        out.append(m)

    # Steps orphaned by a missing parent: keep them, retyped to the parent type.
    for pid, children in kids.items():
        if pid in by_id:
            continue
        children = sorted(children, key=lambda c: c.get("step_order") or 0)
        base = dict(children[0])
        base["id"] = pid or base.get("id")
        base["type"] = ("proof" if base.get("type") == "proof_step"
                        else "algorithm")
        base["statement"] = " ".join(str(c.get("statement") or "")
                                     for c in children).strip()
        base["n_steps_collapsed"] = len(children)
        base.pop("parent_id", None)
        base.pop("step_order", None)
        for c in children:
            remap[c.get("id")] = base["id"]
        out.append(base)

    if edges is None:
        return out, None
    lifted, seen = [], set()
    for e in edges:
        s = remap.get(e.get("source"), e.get("source"))
        t = remap.get(e.get("target"), e.get("target"))
        if s == t:                      # step->parent edges become self-loops
            continue
        key = (s, t, e.get("type"))
        if key in seen:
            continue
        seen.add(key)
        m = dict(e)
        m["source"], m["target"] = s, t
        lifted.append(m)
    return out, lifted


def step_support(nodes, level2_types=LEVEL2_TYPES):
    """Which parents this extraction decomposed — for reporting step coverage
    as a capability, instead of hiding it inside F1."""
    return {n.get("parent_id") for n in nodes
            if n.get("type") in level2_types and n.get("parent_id")}


def type_confusion(matches):
    """Confusion counter over matched pairs: {(type_a, type_b): n}.

    Feed this the pairs a BLIND match produced; it is the number that should
    carry the typing signal once typing no longer distorts retrieval.
    """
    from collections import Counter
    c = Counter()
    for a, b, *_ in matches:
        c[(a.get("type", ""), b.get("type", ""))] += 1
    return c
