"""Semantic Scholar citation graph with persistent sqlite cache.

Method E's K_structural / K_citation split needs to know whether the later
paper cites the earlier paper. We use Semantic Scholar (S2) as the canonical
citation source rather than parsing .bib / \\bibitem because:
  - papers cite journal/conference versions, not arxiv preprints; the .bib
    layer is noisy and partial.
  - S2 already has the resolved global citation graph and supports lookup
    via `ARXIV:<id>` external-ID prefix.

This module wraps the S2 paper endpoint behind a sqlite cache so repeat
queries are free and a partial run can be resumed.

Original fetch logic adapted from scripts/cross_paper_analysis.py::
fetch_citations_s2 (paper-level), generalized into a class with persistence
and a query API (cites/cited_by/references_of/authors_of/year_of) for use
by retrieve_pairs.py.

Schema:
    papers       (arxiv_id TEXT PK, s2_id TEXT, year INT, authors_json TEXT,
                  fetched_at TEXT)
    refs         (citer_arxiv_id TEXT, cited_arxiv_id TEXT,
                  PRIMARY KEY (citer_arxiv_id, cited_arxiv_id))
    -- indices on cited side too
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent
for _p in (_SRC, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from arxiv_id import normalize_arxiv_id  # noqa: E402

_S2_URL = ("https://api.semanticscholar.org/graph/v1/paper/arXiv:{aid}"
           "?fields=externalIds,year,authors.name,authors.authorId,"
           "references.externalIds,references.paperId,"
           "citations.externalIds,citations.paperId")
_UA = "Saranga/1.0 (academic research)"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id     TEXT PRIMARY KEY,
    s2_id        TEXT,
    year         INTEGER,
    authors_json TEXT,
    fetched_at   TEXT
);
CREATE TABLE IF NOT EXISTS refs (
    citer_arxiv_id TEXT NOT NULL DEFAULT '',
    cited_arxiv_id TEXT NOT NULL DEFAULT '',
    cited_s2_id    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (citer_arxiv_id, cited_arxiv_id, cited_s2_id)
);
CREATE INDEX IF NOT EXISTS idx_refs_cited ON refs (cited_arxiv_id);
CREATE INDEX IF NOT EXISTS idx_refs_cited_s2 ON refs (cited_s2_id);
"""


def _connect(path: Path) -> sqlite3.Connection:
    """Connect, create schema if needed, and migrate existing DBs.

    Migration handles the case where an older sqlite (without cited_s2_id
    column) is opened by newer code. The ALTER TABLE is a no-op if the
    column already exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    # Schema migration: add cited_s2_id if missing on old DBs
    try:
        conn.execute("ALTER TABLE refs ADD COLUMN cited_s2_id TEXT DEFAULT ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_refs_cited_s2 ON refs (cited_s2_id)")
    except sqlite3.OperationalError:
        pass  # column already exists (sqlite raises "duplicate column name")
    conn.commit()
    return conn


class S2CitationGraph:
    """Persistent S2 citation cache + query API.

    Usage:
        g = S2CitationGraph(Path("s2_citations.sqlite"), api_key=os.environ.get("S2_KEY"))
        g.fetch_batch(["1805.11176", "2401.00367"])
        g.cites("2401.00367", "1805.11176")            # bool
        g.references_of("2401.00367")                  # set[str]
        g.cited_by("1805.11176")                       # set[str]
    """

    def __init__(self, sqlite_path: Path, api_key: Optional[str] = None,
                 delay: Optional[float] = None):
        self.sqlite_path = Path(sqlite_path)
        self.api_key = api_key
        # S2 unauthenticated rate limit is ~1 req/sec; with an API key it's
        # much higher. Use conservative pacing in both cases.
        self.delay = float(delay) if delay is not None else (0.15 if api_key else 2.0)
        self.conn = _connect(self.sqlite_path)

    def close(self):
        self.conn.close()

    # ── Reads ──────────────────────────────────────────────────────────────

    def has(self, arxiv_id: str) -> bool:
        a = normalize_arxiv_id(arxiv_id)
        cur = self.conn.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (a,))
        return cur.fetchone() is not None

    def year_of(self, arxiv_id: str) -> Optional[int]:
        a = normalize_arxiv_id(arxiv_id)
        cur = self.conn.execute("SELECT year FROM papers WHERE arxiv_id = ?", (a,))
        row = cur.fetchone()
        return row[0] if row else None

    def authors_of(self, arxiv_id: str) -> list[str]:
        a = normalize_arxiv_id(arxiv_id)
        cur = self.conn.execute("SELECT authors_json FROM papers WHERE arxiv_id = ?", (a,))
        row = cur.fetchone()
        if not row or not row[0]:
            return []
        try:
            return list(json.loads(row[0]))
        except Exception:
            return []

    def references_of(self, arxiv_id: str) -> set[str]:
        """ArXiv IDs that `arxiv_id` cites (out-edges)."""
        a = normalize_arxiv_id(arxiv_id)
        cur = self.conn.execute(
            "SELECT cited_arxiv_id FROM refs WHERE citer_arxiv_id = ?", (a,))
        return {r[0] for r in cur.fetchall()}

    def cited_by(self, arxiv_id: str) -> set[str]:
        """ArXiv IDs that cite `arxiv_id` (in-edges).

        Only complete to the extent that the *citers* have been fetched. For
        Method E we typically iterate problem→candidate pairs and ask
        `cites(candidate.paper, problem.paper)` — that requires the candidate
        paper to have been fetched, which it is whenever it appears in the
        theorem index."""
        a = normalize_arxiv_id(arxiv_id)
        cur = self.conn.execute(
            "SELECT citer_arxiv_id FROM refs WHERE cited_arxiv_id = ?", (a,))
        return {r[0] for r in cur.fetchall()}

    def s2_id_of(self, arxiv_id: str) -> str:
        """Return the S2 paperId for an arxiv_id (or empty string if unknown).

        Used by `cites()` to match cites that reference a paper by its
        S2/journal ID rather than its arXiv ID (e.g., a 2018 paper that
        cites a 2013 paper via the journal version's DOI — that reference
        has no ArXiv external ID but does have the same S2 paperId).
        """
        a = normalize_arxiv_id(arxiv_id)
        cur = self.conn.execute(
            "SELECT s2_id FROM papers WHERE arxiv_id = ?", (a,))
        row = cur.fetchone()
        return (row[0] or "") if row else ""

    def cites(self, citer: str, cited: str) -> bool:
        """Does `citer` cite `cited`? Checks both arxiv-id and S2-paperId paths.

        The arxiv-id path catches cites recorded with an explicit arXiv
        external ID. The S2-paperId path catches cites that referenced the
        journal / non-arXiv version of the same paper (S2 unifies versions
        under a single paperId). Brown→Dris was missed by arxiv-only
        matching until we added the s2_id fallback here.
        """
        c = normalize_arxiv_id(citer)
        d = normalize_arxiv_id(cited)
        # Cheap path: direct arxiv-to-arxiv match
        cur = self.conn.execute(
            "SELECT 1 FROM refs WHERE citer_arxiv_id = ? AND cited_arxiv_id = ?",
            (c, d))
        if cur.fetchone():
            return True
        # Fallback: look up cited's S2 paperId, check if citer's refs include it
        cited_s2 = self.s2_id_of(d)
        if not cited_s2:
            return False
        cur = self.conn.execute(
            "SELECT 1 FROM refs WHERE citer_arxiv_id = ? AND cited_s2_id = ?",
            (c, cited_s2))
        return cur.fetchone() is not None

    # ── Writes / fetch ────────────────────────────────────────────────────

    def _upsert_paper(self, arxiv_id: str, payload: dict) -> None:
        ext = (payload or {}).get("externalIds", {}) or {}
        s2_id = (payload or {}).get("paperId") or ext.get("CorpusId") or ""
        year = (payload or {}).get("year")
        authors = [(a or {}).get("name") for a in (payload.get("authors") or [])]
        authors = [a for a in authors if a]
        self.conn.execute(
            "INSERT OR REPLACE INTO papers "
            "(arxiv_id, s2_id, year, authors_json, fetched_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (arxiv_id, str(s2_id) if s2_id else "",
             int(year) if isinstance(year, int) else None,
             json.dumps(authors, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat()),
        )
        # References (out-edges of arxiv_id). Store both arxiv-id and
        # S2-paperId of each reference when available. A reference may
        # have only one (e.g. a paper cited via DOI only has paperId but
        # no arxiv id) — we still record the row so cites() can match
        # via the S2 path. Robust to pre-2007 / old-style arxiv IDs via
        # the canonical normalize_arxiv_id parser.
        for r in payload.get("references") or []:
            r = r or {}
            ext_r = r.get("externalIds") or {}
            arxiv_r = ""
            if ext_r.get("ArXiv"):
                try:
                    arxiv_r = normalize_arxiv_id(ext_r["ArXiv"])
                except ValueError:
                    arxiv_r = ""
            s2_r = (r.get("paperId") or "").strip()
            if arxiv_r or s2_r:
                self.conn.execute(
                    "INSERT OR IGNORE INTO refs "
                    "(citer_arxiv_id, cited_arxiv_id, cited_s2_id) "
                    "VALUES (?, ?, ?)",
                    (arxiv_id, arxiv_r, s2_r))
        # Citations (in-edges to arxiv_id). When we fetch O, the citations
        # field gives us the citers. We record each citer→arxiv_id edge.
        # The "cited" side here is arxiv_id (our paper), so we know its
        # arxiv id; we just need to identify the citer.
        for c in payload.get("citations") or []:
            c = c or {}
            ext_c = c.get("externalIds") or {}
            if ext_c.get("ArXiv"):
                try:
                    citer = normalize_arxiv_id(ext_c["ArXiv"])
                except ValueError:
                    continue
                self.conn.execute(
                    "INSERT OR IGNORE INTO refs "
                    "(citer_arxiv_id, cited_arxiv_id, cited_s2_id) "
                    "VALUES (?, ?, ?)",
                    (citer, arxiv_id, ""))

    def _fetch_one(self, arxiv_id: str, max_retries: int = 3) -> bool:
        """Fetch a single paper. Returns True on success/404 (cached either
        way), False on hard error."""
        url = _S2_URL.format(aid=arxiv_id)
        headers = {"User-Agent": _UA}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        backoff = self.delay
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    payload = json.loads(resp.read())
                self._upsert_paper(arxiv_id, payload)
                self.conn.commit()
                return True
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    backoff = min(backoff * 2, 120)
                    print(f"[s2] rate limited on {arxiv_id} attempt {attempt+1}; "
                          f"waiting {backoff:.0f}s", file=sys.stderr)
                    time.sleep(backoff)
                    continue
                if e.code == 404:
                    # Cache the absence so we don't refetch
                    self._upsert_paper(arxiv_id, {})
                    self.conn.commit()
                    return True
                print(f"[s2] HTTPError {e.code} on {arxiv_id}", file=sys.stderr)
                return False
            except Exception as e:
                print(f"[s2] error on {arxiv_id}: {e}", file=sys.stderr)
                return False
        return False

    def fetch_batch(self, arxiv_ids: Iterable[str],
                    *,
                    skip_existing: bool = True,
                    progress_every: int = 50) -> dict:
        """Fetch all listed papers. Returns {arxiv_id: bool} success map."""
        ids = [normalize_arxiv_id(a) for a in arxiv_ids]
        if skip_existing:
            ids = [a for a in ids if not self.has(a)]
        ok: dict[str, bool] = {}
        for i, aid in enumerate(ids, 1):
            ok[aid] = self._fetch_one(aid)
            if i % progress_every == 0:
                print(f"[s2] fetched {i}/{len(ids)}", file=sys.stderr)
            time.sleep(self.delay)
        return ok

    # ── Stats / introspection ────────────────────────────────────────────

    def stats(self) -> dict:
        p = self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        r = self.conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        return {"papers": p, "refs": r}


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Populate the cache for a list of arxiv IDs")
    f.add_argument("--cache", required=True, help="Sqlite path")
    f.add_argument("--ids-from", action="append", default=[],
                   help="JSONL file(s) with a 'paper_id' field per row; "
                        "all unique paper_id values are fetched.")
    f.add_argument("--ids", default=None,
                   help="Comma-separated arxiv IDs (alternative to --ids-from)")
    f.add_argument("--api-key", default=None,
                   help="S2 API key (or set S2_API_KEY env var)")
    f.add_argument("--delay", type=float, default=None,
                   help="Pacing between requests in seconds")

    s = sub.add_parser("stats", help="Show cache statistics")
    s.add_argument("--cache", required=True)

    args = ap.parse_args()

    if args.cmd == "stats":
        g = S2CitationGraph(Path(args.cache))
        print(g.stats())
        return

    import os
    api_key = args.api_key or os.environ.get("S2_API_KEY")
    g = S2CitationGraph(Path(args.cache), api_key=api_key, delay=args.delay)

    ids: list[str] = []
    if args.ids:
        ids.extend(a.strip() for a in args.ids.split(",") if a.strip())
    for path in args.ids_from:
        with open(path, encoding="utf-8") as fh:
            seen = set()
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                pid = row.get("paper_id")
                if pid and pid not in seen:
                    ids.append(pid)
                    seen.add(pid)
    if not ids:
        ap.error("No arxiv IDs supplied (--ids or --ids-from)")

    ok = g.fetch_batch(ids)
    print(f"\nFetched: {sum(ok.values())}/{len(ok)} successful.")
    print(f"Stats: {g.stats()}")


if __name__ == "__main__":
    main()
