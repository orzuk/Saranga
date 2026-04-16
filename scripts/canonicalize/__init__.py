"""
LaTeX canonicalization for cross-paper mathematical knowledge-graph alignment.

Public API:
    canonicalize_text(text, rename_map=None, prose_rewrites=False) -> str
    canonicalize_paper(paper_json, prose_rewrites=False) -> dict
    build_paper_rename_map(paper_json) -> dict
    build_local_rename_map(text) -> dict
"""
from .core import (
    canonicalize_text,
    canonicalize_paper,
    build_paper_rename_map,
    build_local_rename_map,
)

__all__ = [
    "canonicalize_text",
    "canonicalize_paper",
    "build_paper_rename_map",
    "build_local_rename_map",
]
