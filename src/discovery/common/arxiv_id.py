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

_MODERN_YYMM_RE = re.compile(r"^(\d{2})(\d{2})\.\d{4,5}$")
_OLD_STYLE_YYMM_RE = re.compile(r"^[a-z]+(?:-[a-z]+)?(?:\.[A-Z]{2,3})?/(\d{2})(\d{2})\d{3}$")


def year_from_arxiv_id(arxiv_id: str) -> int:
    """Return submission year from a canonical arXiv ID.

    Modern format: `1805.11176` -> 2018 (from YYMM prefix).
    Old style:     `math/9410211` -> 1994
                   `cs/0008011`   -> 2000
                   `math.CO/0509050` -> 2005

    The pre-2007 ID convention: YY is 91-99 (= 1991-1999) or 00-06
    (= 2000-2006). The new YYMM.NNNNN format started April 2007.

    Raises ValueError on unparseable IDs.
    """
    base = normalize_arxiv_id(arxiv_id)
    m = _MODERN_YYMM_RE.match(base)
    if m:
        return 2000 + int(m.group(1))
    m = _OLD_STYLE_YYMM_RE.match(base)
    if m:
        yy = int(m.group(1))
        return (1900 + yy) if yy >= 91 else (2000 + yy)
    raise ValueError(f"Cannot extract year from arxiv ID: {arxiv_id!r}")
