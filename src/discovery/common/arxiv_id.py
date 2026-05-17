"""Arxiv ID helpers shared across discovery methods.

Re-exports `normalize_arxiv_id` from `src/extract_arxiv_funcs.py` and adds
`year_from_arxiv_id` based on the YYMM prefix used by all post-2007 arxiv IDs.
"""
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent  # .../Saranga/src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from extract_arxiv_funcs import normalize_arxiv_id  # noqa: E402,F401  (re-export)

_YYMM_RE = re.compile(r"^(\d{2})(\d{2})\.\d{4,5}")


def year_from_arxiv_id(arxiv_id: str) -> int:
    """Return submission year from `1805.11176` (any version) -> 2018.

    Only handles the post-2007 YYMM.NNNNN scheme. Raises ValueError otherwise.
    Pre-2007 arxiv IDs (`math/0501001`) are not in SARANGA's tier3 corpus.
    """
    base = normalize_arxiv_id(arxiv_id)
    m = _YYMM_RE.match(base)
    if not m:
        raise ValueError(f"Cannot extract year from arxiv ID: {arxiv_id!r}")
    return 2000 + int(m.group(1))
