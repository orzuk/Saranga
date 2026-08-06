"""
LLMVersion/extract_arxiv_funcs.py — thin shim re-exporting src/extract_arxiv_funcs.py.

This file used to be a full 1715-line COPY of the module one directory up. Both
copies were actively maintained by different people and had drifted: 14 of 19
shared functions were still byte-identical, but the fix that taught
`normalize_arxiv_id` to parse pre-2007 arXiv IDs (`math/9410211`,
`quant-ph/0702094`) landed only in `src/`, so anything running through
LLMVersion raised ValueError on old-style IDs. Meanwhile `flatten_tex`, the
`use_paper_subdir` storage mode, and the `top_k`-before-metadata optimisation
existed only here. Both directions of that drift are now merged into
`src/extract_arxiv_funcs.py`, which is the single source of truth.

Why a shim and not a symlink: modules in this directory are run as scripts
(`python src/LLMVersion/parse_batch.py`), which puts THIS directory first on
sys.path, so `from extract_arxiv_funcs import ...` must keep resolving here.
A symlink would also deliver identical bytes, which was the original problem —
`src/config.py` yields `Path` values while `LLMVersion/config.py` yields `str`,
so one file had to be able to serve both. The merged module sidesteps that by
being type-agnostic (`Path(DATA_DIR) / ...` accepts either), which is why this
shim needs no conversion layer of its own — unlike `config.py`, which does.

Loaded via importlib under an alias so this module does not re-import itself.
"""

import importlib.util as _importlib_util
from pathlib import Path as _Path

_src_path = _Path(__file__).resolve().parent.parent / "extract_arxiv_funcs.py"
_spec = _importlib_util.spec_from_file_location("_src_extract_arxiv_funcs",
                                                str(_src_path))
_mod = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Re-export every public name, so `from extract_arxiv_funcs import X` and
# `extract_arxiv_funcs.X` both behave exactly as they did against the copy.
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

__all__ = [k for k in vars(_mod) if not k.startswith("_")]
