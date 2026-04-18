#!/usr/bin/env python3
"""Embedding-based node similarity (σ) for cross-paper graph alignment.

Drop-in replacement for ``graph_alignment.jaccard_sim``.  Uses a
sentence-transformer model to embed the textual content of each node and
returns cosine similarity, weighted by the same type-compatibility matrix
used by the Jaccard baseline.

Canonicalization (scripts/canonicalize) is applied automatically: the
``*_canonical_local`` fields are preferred when present.

Usage with the benchmark runner::

    python scripts/run_alignment_benchmark.py \
        --config  .../benchmark_config.json \
        --sigma-import embedding_sigma.sigma \
        --sigma-label  bge-m3 \
        --output  results_embedding.csv

Or as a library::

    from embedding_sigma import sigma
    sim = sigma(node_a, node_b)   # float in [0, 1]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from functools import lru_cache
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Ensure repo root is importable (for graph_alignment.type_compat and
# scripts.canonicalize).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from graph_alignment import type_compat  # noqa: E402

# ---------------------------------------------------------------------------
# Model loading (lazy singleton)
# ---------------------------------------------------------------------------
_MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME, trust_remote_code=True)
        print(f"[embedding_sigma] Loaded model: {_MODEL_NAME}", flush=True)
    return _model


# ---------------------------------------------------------------------------
# Text extraction — prefers canonical_local fields when present
# ---------------------------------------------------------------------------

def _get_field(node: dict, field: str) -> str:
    """Return the best available version of *field*: canonical_local > canonical_paper > raw."""
    for suffix in ("_canonical_local", "_canonical_paper", ""):
        v = node.get(f"{field}{suffix}")
        if v:
            if isinstance(v, list):
                return " ".join(str(x) for x in v)
            return str(v)
    return ""


def node_text_for_embedding(node: dict) -> str:
    """Build a single text string for embedding from a node dict.

    Format:  "<type>: <name>. <statement> <assumptions> <conclusions>"
    Using canonical fields when available.
    """
    parts = []

    # Type prefix gives the model a hint about the node's role
    ntype = node.get("type") or node.get("kind") or ""
    if ntype:
        parts.append(f"[{ntype}]")

    name = _get_field(node, "name")
    if name:
        parts.append(name + ".")

    statement = _get_field(node, "statement")
    if statement:
        parts.append(statement)

    assumptions = _get_field(node, "assumptions")
    if assumptions:
        parts.append(f"Assumptions: {assumptions}")

    conclusions = _get_field(node, "conclusions")
    if conclusions:
        parts.append(f"Conclusions: {conclusions}")

    # proof_strategy for proof nodes
    proof = _get_field(node, "proof_strategy")
    if proof:
        parts.append(f"Proof strategy: {proof}")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Embedding with caching
# ---------------------------------------------------------------------------

@lru_cache(maxsize=20_000)
def _embed_cached(text: str) -> tuple:
    """Embed text and return as tuple (hashable for lru_cache)."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return tuple(vec.tolist())


def embed_node(node: dict) -> np.ndarray:
    """Return the L2-normalized embedding vector for a node."""
    text = node_text_for_embedding(node)
    return np.array(_embed_cached(text), dtype=np.float32)


# ---------------------------------------------------------------------------
# The σ function — the public API
# ---------------------------------------------------------------------------

def sigma(node_a: dict, node_b: dict) -> float:
    """Embedding cosine similarity × type compatibility.

    Returns float in [0, 1].
    """
    va = embed_node(node_a)
    vb = embed_node(node_b)
    cosine = float(va @ vb)
    # Cosine of normalized vectors is in [-1, 1]; clamp to [0, 1]
    cosine = max(0.0, cosine)
    # Apply type compatibility (same weighting as Jaccard baseline)
    tc = type_compat(
        (node_a.get("type") or node_a.get("kind") or ""),
        (node_b.get("type") or node_b.get("kind") or ""),
    )
    return cosine * tc


def sigma_no_type(node_a: dict, node_b: dict) -> float:
    """Embedding cosine similarity WITHOUT type compatibility.

    Useful for ablation / seeing raw semantic similarity.
    """
    va = embed_node(node_a)
    vb = embed_node(node_b)
    return max(0.0, float(va @ vb))


# ---------------------------------------------------------------------------
# Batch pre-embedding utility (for heatmaps / offline use)
# ---------------------------------------------------------------------------

def precompute_paper_embeddings(paper_json: dict) -> dict[str, np.ndarray]:
    """Return {node_id: embedding_vector} for all nodes in a paper JSON."""
    nodes = paper_json.get("nodes", [])
    if isinstance(nodes, dict):
        nodes = list(nodes.values())
    return {n["id"]: embed_node(n) for n in nodes}


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import argparse

    parser = argparse.ArgumentParser(description="Test embedding sigma on two paper JSONs")
    parser.add_argument("paper_a", help="Path to paper A JSON")
    parser.add_argument("paper_b", help="Path to paper B JSON")
    parser.add_argument("--top-k", type=int, default=10, help="Show top-k matches")
    args = parser.parse_args()

    with open(args.paper_a) as f:
        ga = json.load(f)
    with open(args.paper_b) as f:
        gb = json.load(f)

    nodes_a = ga.get("nodes", [])
    nodes_b = gb.get("nodes", [])
    if isinstance(nodes_a, dict):
        nodes_a = list(nodes_a.values())
    if isinstance(nodes_b, dict):
        nodes_b = list(nodes_b.values())

    print(f"Paper A: {len(nodes_a)} nodes")
    print(f"Paper B: {len(nodes_b)} nodes")

    # Compute all pairs
    pairs = []
    for a in nodes_a:
        for b in nodes_b:
            s = sigma(a, b)
            pairs.append((s, a, b))

    pairs.sort(key=lambda x: -x[0])
    print(f"\nTop-{args.top_k} matches (embedding σ):")
    for s, a, b in pairs[:args.top_k]:
        print(f"  {s:.3f}  {a['id']} ({a.get('type','')}) "
              f"↔ {b['id']} ({b.get('type','')})")
        print(f"         A: {a.get('name','')[:60]}")
        print(f"         B: {b.get('name','')[:60]}")
