"""Text views — how a typed graph node becomes a string for an embedder.

Two orthogonal axes, both of which Or asked to be ablatable rather than fixed:

  CONTEXT      does the vector describe the statement alone, or the statement
               together with the definitions/assumptions it links to?
  CANONICAL    is the notation α-renamed (``$G$``, ``$H$`` -> ``V1``, ``V2``,
               fractions/binomials/inequalities normalized) or left as written?

Four views:

  node           statement only. The baseline.
  ctx-concat     statement + a typed block of its graph neighbours, one string,
                 one forward pass. True contextual embedding.
  ctx-late       NOT a text view — a vector view. We record each node's
                 neighbour keys + weights here; the sweep combines the already
                 cached neighbour vectors as
                     v = normalize(α·v_node + (1-α)·Σ wᵢ·v_nbrᵢ)
                 so it costs no extra GPU time and α is swept post-hoc.
  concepts-only  just the grounded_to foundation concept names. An ablation:
                 how much of the signal is pure concept grounding?

IMPORTANT — this module deliberately does NOT use ``shared.corpus.node_norm_text``.
That function lowercases and strips punctuation, which is right for token Jaccard
and actively harmful for a transformer: it destroys casing, operators and sentence
structure the model was trained on. Here we use the math-PRESERVING
``clean_latex_to_text`` and only collapse whitespace.

Graph context is read from the real tier3 edge schema:
  * ``uses``        source=node, target=the definition/equation/lemma it depends on
  * ``grounded_to`` source=foundation concept name (external), target=node
                    carrying ``idf`` and ``generic`` — we keep the non-generic,
                    high-idf ones. This signal exists in every tier3 JSON and is
                    currently discarded by every retrieval method we have.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
_REPO = _SUITE.parent
for _p in (_SUITE, _REPO, _REPO / "src", _REPO / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from LLMVersion.latex_clean import clean_latex_to_text  # math-preserving
except Exception:  # pragma: no cover - cleaner optional
    clean_latex_to_text = None

try:
    from canonicalize import canonicalize_text, build_local_rename_map, build_paper_rename_map
except Exception:  # pragma: no cover - canonicalization optional
    canonicalize_text = None
    build_local_rename_map = build_paper_rename_map = None


# ── node type roles ──────────────────────────────────────────────────────────

QUERY_TYPES = {"open_problem", "conjecture"}
QUERY_TYPES_WIDE = QUERY_TYPES | {"problem"}
# Matches o1_retrieve.THEOREM_TYPES so the dense and lexical arms retrieve over
# exactly the same candidate population (otherwise the comparison is unfair).
DOC_TYPES = {"theorem", "lemma", "proposition", "corollary", "claim"}
# Nodes that are never retrieved themselves but carry context for those that are.
CTX_ONLY_TYPES = {"definition", "assumption", "notation", "equation", "remark", "example"}

# Neighbour preference when the budget forces a choice: what a theorem *rests on*
# is more identifying than what merely appears nearby.
_CTX_TYPE_RANK = {
    "definition": 0, "assumption": 1, "notation": 2, "theorem": 3, "lemma": 3,
    "proposition": 3, "corollary": 4, "claim": 4, "equation": 5, "remark": 6,
    "example": 7,
}
_CTX_EDGE_TYPES = ("uses", "depends_on", "specializes", "generalizes")

_WS = re.compile(r"\s+")
_NULLISH = {"", "none", "null", "[]", "{}", "nan"}


def _s(value) -> str:
    """A node field as a usable string.

    tier3 JSONs stringify absent values as the literal ``"None"`` and empty lists
    as ``"[]"`` (they round-tripped through a DataFrame), so a plain truthiness
    check is not enough — ``node["name"]`` is very often the string ``"None"``.
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(x) for x in value if x is not None)
    text = str(value).strip()
    return "" if text.lower() in _NULLISH else text


def _collapse(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def _clean(latex: str) -> str:
    """LaTeX -> readable math-preserving text (falls back to raw collapse)."""
    if not latex:
        return ""
    if clean_latex_to_text is not None:
        try:
            return _collapse(clean_latex_to_text(latex))
        except Exception:
            pass
    return _collapse(latex)


# ── canonicalization ─────────────────────────────────────────────────────────

def rename_map_for_paper(nodes: Sequence[dict]) -> dict:
    """Paper-scoped α-rename map (variables numbered in first-occurrence order
    across the whole paper). Used with ``--canon-scope paper``."""
    if build_paper_rename_map is None:
        return {}
    try:
        return build_paper_rename_map({"nodes": list(nodes)})
    except Exception:
        return {}


def _canon(latex: str, scope: str, paper_map: Optional[dict]) -> str:
    """Canonicalize LaTeX, then clean it to text.

    Order matters: ``canonicalize_text`` segments on ``$…$`` delimiters, which
    ``clean_latex_to_text`` removes. Canonicalize first, clean second.

    scope='local' renumbers variables per node (V1 = first variable in THIS
    statement) — that is what makes two papers' notations line up pairwise, and
    is what src/embedding_sigma.py already prefers via ``*_canonical_local``.
    scope='paper' numbers across the whole paper (more internally consistent,
    less comparable across papers). Both are offered; local is the default.
    """
    if not latex or canonicalize_text is None:
        return _clean(latex)
    try:
        if scope == "paper":
            rmap = paper_map or {}
        elif scope == "local":
            rmap = build_local_rename_map(latex) if build_local_rename_map else {}
        else:  # 'none' — structural rewrites only, no variable renaming
            rmap = {}
        return _clean(canonicalize_text(latex, rename_map=rmap))
    except Exception:
        return _clean(latex)


# ── node text ────────────────────────────────────────────────────────────────

def _node_source_latex(node: dict) -> str:
    """The best LaTeX-ish source for a node.

    Prefer ``raw_latex``: the base parser masks ``clean_text``/``statement`` math
    to ``[MATH]``, which is blind to the actual mathematics AND inconsistent with
    distilled nodes whose stored text is unmasked (the exact bug fixed in
    sweep_open by ``--text-source raw``). Fall back to the stored fields only when
    raw_latex is missing.
    """
    raw = _s(node.get("raw_latex"))
    if raw:
        return raw
    return _s(node.get("statement")) or _s(node.get("clean_text"))


def node_text(node: dict, *, canonical: bool = False, scope: str = "local",
              paper_map: Optional[dict] = None, with_type: bool = True) -> str:
    """The ``node`` view: ``[type] Name\\nStatement``."""
    src = _node_source_latex(node)
    body = _canon(src, scope, paper_map) if canonical else _clean(src)
    name = _s(node.get("name"))
    if name and canonical:
        name = _canon(name, scope, paper_map)
    elif name:
        name = _clean(name)
    head = f"[{_s(node.get('type')).lower()}]" if with_type else ""
    parts = [p for p in (head, name) if p]
    line = " ".join(parts)
    return f"{line}\n{body}".strip() if line else body


# ── graph context ────────────────────────────────────────────────────────────

@dataclass
class Neighbour:
    key: str            # local node id
    ntype: str
    weight: float
    text: str


def _index_edges(edges: Sequence[dict]) -> tuple[dict, dict]:
    """(uses-style out-adjacency, grounded_to concepts per node id)."""
    out: dict[str, list[tuple[str, float]]] = {}
    concepts: dict[str, list[tuple[float, str]]] = {}
    for e in edges:
        etype = _s(e.get("type")).lower()
        src, tgt = _s(e.get("source")), _s(e.get("target"))
        if not src or not tgt:
            continue
        if etype in _CTX_EDGE_TYPES:
            out.setdefault(src, []).append((tgt, float(e.get("confidence") or 1.0)))
        elif etype == "grounded_to":
            # grounded_to points concept -> node: source is an EXTERNAL foundation
            # name ("Definition:Lexicographic Order"), target is the paper node.
            # `generic` may arrive as a bool or as the string "True" — tier3 JSONs
            # stringify a lot of fields, so don't test identity against True.
            if str(e.get("generic")).lower() in ("true", "1"):
                continue  # 'finite set', 'function' — true of half the corpus
            name = src.split(":", 1)[-1].strip()
            if name:
                concepts.setdefault(tgt, []).append((float(e.get("idf") or 0.0), name))
    return out, concepts


def concept_names(node_id: str, concepts: dict, *, limit: int = 8) -> list[str]:
    """Non-generic grounded_to concept names for a node, most distinctive first."""
    got = concepts.get(node_id) or []
    got.sort(key=lambda x: (-x[0], x[1]))
    seen, out = set(), []
    for _idf, name in got:
        low = name.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(name)
        if len(out) >= limit:
            break
    return out


def neighbours_of(
    node_id: str,
    nodes_by_id: dict,
    adjacency: dict,
    *,
    depth: int = 1,
    max_neighbours: int = 4,
) -> list[Neighbour]:
    """Graph neighbours that define the meaning of ``node_id``.

    BFS over ``uses``-style out-edges: what the statement depends on. Depth-2
    neighbours are damped by 0.5 per hop so a definition used directly outranks
    one reached through an equation. Ordering is fully deterministic (rank, then
    -weight, then id) so the same node always yields the same context string —
    embeddings must be reproducible across runs and machines.
    """
    seen = {node_id}
    frontier = [(node_id, 1.0)]
    found: list[Neighbour] = []
    for hop in range(max(0, depth)):
        nxt: list[tuple[str, float]] = []
        for nid, w in frontier:
            for tgt, conf in sorted(adjacency.get(nid, [])):
                if tgt in seen:
                    continue
                seen.add(tgt)
                nb = nodes_by_id.get(tgt)
                if nb is None:
                    continue
                ntype = _s(nb.get("type")).lower()
                weight = w * conf * (0.5 ** hop)
                found.append(Neighbour(key=tgt, ntype=ntype, weight=weight, text=""))
                nxt.append((tgt, weight))
        frontier = nxt
        if not frontier:
            break
    found.sort(key=lambda n: (_CTX_TYPE_RANK.get(n.ntype, 9), -n.weight, n.key))
    return found[:max_neighbours]


def render_context(
    head: str,
    neighbours: Sequence[Neighbour],
    concepts: Sequence[str],
    *,
    bodies: Optional[dict] = None,
    max_chars: int = 600,
    per_neighbour_chars: int = 220,
) -> str:
    """The ``ctx-concat`` view: node text + a typed, budgeted neighbour block.

    ``head`` is the already-rendered node view (raw or canonical) — passed in
    rather than recomputed, because canonicalization runs at ~240 nodes/s and
    doing it twice per node doubles the cost of the whole text-store stage.
    ``bodies`` maps neighbour key -> body text in the matching raw/canonical
    flavour, so the canonical context is canonical all the way down.
    """
    block: list[str] = []
    if concepts:
        block.append("concepts: " + "; ".join(concepts))
    budget = max_chars
    for nb in neighbours:
        if budget <= 0:
            break
        body = (bodies.get(nb.key) if bodies else nb.text) or nb.text
        body = body[:per_neighbour_chars].strip()
        if not body:
            continue
        line = f"uses [{nb.ntype}] {body}"[:budget]
        block.append(line)
        budget -= len(line)
    return head if not block else head + "\n" + "\n".join(block)


# ── the per-node record the text store persists ──────────────────────────────

@dataclass
class NodeRecord:
    key: str
    paper_id: str
    year: int
    yymm: int
    category: str
    ntype: str
    role: str                      # query | doc | ctx
    text_raw: str
    text_canon: str
    ctx_raw: str
    ctx_canon: str
    concepts: str
    ctx_keys: list = field(default_factory=list)      # for the ctx-late vector view
    ctx_weights: list = field(default_factory=list)
    n_words: int = 0
    sha1: str = ""

    def as_row(self) -> dict:
        return {
            "key": self.key, "paper_id": self.paper_id, "year": self.year,
            "yymm": self.yymm, "category": self.category, "ntype": self.ntype,
            "role": self.role, "text_raw": self.text_raw,
            "text_canon": self.text_canon, "ctx_raw": self.ctx_raw,
            "ctx_canon": self.ctx_canon, "concepts": self.concepts,
            "ctx_keys": json.dumps(self.ctx_keys),
            "ctx_weights": json.dumps([round(w, 4) for w in self.ctx_weights]),
            "n_words": self.n_words, "sha1": self.sha1,
        }


ROW_COLUMNS = ["key", "paper_id", "year", "yymm", "category", "ntype", "role",
               "text_raw", "text_canon", "ctx_raw", "ctx_canon", "concepts",
               "ctx_keys", "ctx_weights", "n_words", "sha1"]


def yymm_of(paper_id: str, year: int) -> int:
    """arXiv YYMM as an int; falls back to ``year*100`` for old-style ids.

    Month granularity matters: a 'resolution' posted two months BEFORE the
    problem is a false positive that year-granularity filtering lets through —
    the same tightening triage_open.py applies downstream.
    """
    head = str(paper_id).split("::", 1)[0].split(".", 1)[0]
    if head.isdigit() and len(head) == 4:
        return int(head)
    return int(year) * 100


def role_of(ntype: str, query_types: Iterable[str]) -> Optional[str]:
    if ntype in set(query_types):
        return "query"
    if ntype in DOC_TYPES:
        return "doc"
    if ntype in CTX_ONLY_TYPES:
        return "ctx"
    return None


def paper_records(
    paper,
    *,
    query_types: Iterable[str] = QUERY_TYPES,
    canon_scope: str = "local",
    ctx_canon_scope: str = "paper",
    with_canon: bool = True,
    ctx_depth: int = 1,
    max_neighbours: int = 4,
    max_ctx_chars: int = 600,
    min_words: int = 6,
    keep_ctx_nodes: bool = True,
) -> list[NodeRecord]:
    """Every retrievable node of one paper, in all text views.

    ``keep_ctx_nodes`` also emits definition/assumption/etc. records — but ONLY
    those actually cited as a neighbour by some query/doc node. Emitting every
    context-eligible node would roughly quadruple the corpus (equations alone are
    ~50% of all nodes, 8M at 100k scale) to embed vectors nothing ever reads.
    The ones we do keep are what makes the ctx-late view free: its neighbour
    vectors come straight out of this same store.
    """
    nodes = paper.nodes or []
    nodes_by_id = {_s(n.get("id")): n for n in nodes if _s(n.get("id"))}
    adjacency, concepts = _index_edges(paper.edges or [])
    qtypes = set(query_types)
    pid = paper.paper_id

    # Two canonicalization scopes, on purpose:
    #   node view  -> `canon_scope` (default 'local'): V1 = the first variable in
    #     THIS statement, which is what makes two isolated statements from two
    #     papers line up pairwise (the same choice src/embedding_sigma.py
    #     makes by preferring *_canonical_local).
    #   ctx view   -> `ctx_canon_scope` (default 'paper'): one numbering shared by
    #     the theorem and every definition quoted beneath it. With a local map per
    #     piece, the theorem's V1 and its definition's V1 are different variables
    #     and the assembled block is internally inconsistent — a confound that
    #     would make the canonical ctx-concat arm look worse for the wrong reason.
    # When the two scopes coincide the caches collapse and cost one pass, not two.
    need_paper_map = with_canon and "paper" in (canon_scope, ctx_canon_scope)
    paper_map = rename_map_for_paper(nodes) if need_paper_map else None

    # Cleaning and (especially) canonicalizing are the expensive operations —
    # ~240 nodes/s for canon, ~98% of this function's runtime. Neighbours are
    # shared between nodes, so compute each flavour at most once per paper.
    raw_body: dict[str, str] = {}
    canon_body: dict[tuple[str, str], str] = {}

    def _raw(nid: str) -> str:
        if nid not in raw_body:
            nb = nodes_by_id.get(nid)
            raw_body[nid] = "" if nb is None else _clean(_node_source_latex(nb))
        return raw_body[nid]

    def _canon_body(nid: str, scope: str) -> str:
        hit = canon_body.get((nid, scope))
        if hit is None:
            nb = nodes_by_id.get(nid)
            hit = "" if nb is None else _canon(_node_source_latex(nb), scope, paper_map)
            canon_body[(nid, scope)] = hit
        return hit

    main: list[NodeRecord] = []
    ctx_wanted: set[str] = set()

    for node in nodes:
        nid = _s(node.get("id"))
        ntype = _s(node.get("type")).lower()
        if not nid or not ntype:
            continue
        if role_of(ntype, qtypes) not in ("query", "doc"):
            continue
        role = role_of(ntype, qtypes)

        # Length gate on the BODY only. text_raw carries a "[theorem] Name" head,
        # and counting that would let shorter statements through here than
        # sweep_open.py admits — the two arms must retrieve over the same
        # population or the comparison measures the filter, not the matcher.
        if len(_raw(nid).split()) < min_words:
            continue
        text_raw = node_text(node, canonical=False)
        text_canon = node_text(node, canonical=True, scope=canon_scope,
                               paper_map=paper_map) if with_canon else ""

        nbrs = neighbours_of(nid, nodes_by_id, adjacency,
                             depth=ctx_depth, max_neighbours=max_neighbours)
        for nb in nbrs:
            nb.text = _raw(nb.key)
            ctx_wanted.add(nb.key)

        cnames = concept_names(nid, concepts)
        # A theorem's own grounding is sparse; the concepts of what it USES are
        # part of its meaning too, so fold in the neighbours' concepts.
        for nb in nbrs:
            for c in concept_names(nb.key, concepts, limit=3):
                if c not in cnames:
                    cnames.append(c)
        cnames = cnames[:10]

        ctx_raw = render_context(text_raw, nbrs, cnames, max_chars=max_ctx_chars)
        if with_canon:
            ctx_head = (text_canon if ctx_canon_scope == canon_scope
                        else node_text(node, canonical=True, scope=ctx_canon_scope,
                                       paper_map=paper_map))
            ctx_canon = render_context(
                ctx_head, nbrs, cnames, max_chars=max_ctx_chars,
                bodies={nb.key: _canon_body(nb.key, ctx_canon_scope) for nb in nbrs},
            )
        else:
            ctx_canon = ""

        main.append(NodeRecord(
            key=f"{pid}::{nid}", paper_id=pid, year=int(paper.year),
            yymm=yymm_of(pid, paper.year), category=paper.category or "",
            ntype=ntype, role=role,
            text_raw=text_raw, text_canon=text_canon,
            ctx_raw=ctx_raw, ctx_canon=ctx_canon,
            concepts="; ".join(cnames),
            ctx_keys=[f"{pid}::{nb.key}" for nb in nbrs],
            ctx_weights=[nb.weight for nb in nbrs],
            n_words=len(text_raw.split()),
            sha1=hashlib.sha1(text_raw.encode("utf-8")).hexdigest()[:16],
        ))

    if not keep_ctx_nodes:
        return main

    # Context-only nodes: node view only (nobody ever retrieves them, and nobody
    # builds context *for* them), and only the referenced ones.
    for nid in sorted(ctx_wanted):
        node = nodes_by_id.get(nid)
        if node is None:
            continue
        ntype = _s(node.get("type")).lower()
        if role_of(ntype, qtypes) != "ctx":
            continue  # a doc-type neighbour already has its own record above
        body = _raw(nid)
        if not body:
            continue
        # Same "[type] Name\nbody" shape as node_text, assembled from the cached
        # body so the expensive clean/canon is not repeated. ctx vectors are
        # averaged with doc vectors in the ctx-late view, so their surface form
        # has to match or the two live in slightly different distributions.
        head = " ".join(x for x in (f"[{ntype}]", _clean(_s(node.get("name")))) if x)
        text_raw = f"{head}\n{body}"
        main.append(NodeRecord(
            key=f"{pid}::{nid}", paper_id=pid, year=int(paper.year),
            yymm=yymm_of(pid, paper.year), category=paper.category or "",
            ntype=ntype, role="ctx",
            text_raw=text_raw,
            text_canon=(f"{head}\n{_canon_body(nid, canon_scope)}" if with_canon else ""),
            ctx_raw="", ctx_canon="",
            concepts="; ".join(concept_names(nid, concepts)),
            n_words=len(text_raw.split()),
            sha1=hashlib.sha1(text_raw.encode("utf-8")).hexdigest()[:16],
        ))
    return main


# ── view selection ───────────────────────────────────────────────────────────

#: Views that are produced by encoding a string. ``ctx-late`` is absent on
#: purpose — it is assembled from cached vectors at search time (see index.py).
TEXT_VIEWS = {
    "node": ("text_raw", "text_canon"),
    "ctx-concat": ("ctx_raw", "ctx_canon"),
    "concepts-only": ("concepts", "concepts"),   # canonicalization is a no-op here
}
VECTOR_VIEWS = ("ctx-late",)
ALL_VIEWS = tuple(TEXT_VIEWS) + VECTOR_VIEWS


def column_for(view: str, canon: bool) -> str:
    """Text-store column holding the string for (view, canon)."""
    if view in VECTOR_VIEWS:
        # ctx-late reuses the plain node vectors and combines them afterwards.
        view = "node"
    try:
        raw_col, canon_col = TEXT_VIEWS[view]
    except KeyError:
        raise ValueError(f"unknown view {view!r}; known: {', '.join(ALL_VIEWS)}") from None
    return canon_col if canon else raw_col
