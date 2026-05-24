"""SQLite-backed lazy text store for the split theorems index.

Background: the original Method E indexed format (`theorems.jsonl`)
stores both the signature (used for retrieval scoring) and the full
raw_latex / clean_text (used only at candidate-emission time) in the
same JSONL row. At v2 corpus scale (~1.24M theorems) the text fields
dominate file size (~1.5KB/row * 1.24M = 1.8GB), forcing the retrieve
phase onto a SLURM node with >= 64GB RAM just to hold the loaded rows
plus the inverted index.

This module enables a split-format alternative:

  theorems_sig.jsonl     — slim rows (signature + metadata only),
                           loaded fully into RAM at retrieve time.
                           ~250-450 bytes/row, total ~430MB.

  theorems_text.sqlite   — SQLite table keyed on (paper_id, node_id),
                           with the raw_latex and clean_text columns.
                           Random-access lookup, ~370MB on disk.
                           Loaded lazily: only the top-K per problem
                           are ever fetched. Negligible RAM cost.

Total retrieve RAM drops from ~2.1GB to ~750MB, gateway-runnable.

Public API:

  class TextStore:
      __init__(path: Path)              — open / create sqlite file
      put(paper_id, node_id, raw_latex, clean_text=None)
      put_many(rows: Iterable[(pid, nid, raw, clean)])  — bulk insert
      get(paper_id, node_id) -> (raw_latex, clean_text) | (None, None)
      close()

Use `put_many` for migrations / index builds (one txn). Use `get` at
candidate-emission time in retrieve_pairs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS theorem_text (
    paper_id   TEXT NOT NULL,
    node_id    TEXT NOT NULL,
    raw_latex  TEXT,
    clean_text TEXT,
    PRIMARY KEY (paper_id, node_id)
);
"""


class TextStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript(_SCHEMA)
        # Performance settings: we never read while writing, so WAL +
        # NORMAL syncing is safe and ~5x faster for bulk insert.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def put(self, paper_id: str, node_id: str,
            raw_latex: Optional[str], clean_text: Optional[str] = None):
        self.conn.execute(
            "INSERT OR REPLACE INTO theorem_text "
            "(paper_id, node_id, raw_latex, clean_text) VALUES (?, ?, ?, ?)",
            (paper_id, node_id, raw_latex or "", clean_text or ""))

    def put_many(self, rows: Iterable[tuple]):
        """rows is iterable of (paper_id, node_id, raw_latex, clean_text)."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO theorem_text "
            "(paper_id, node_id, raw_latex, clean_text) VALUES (?, ?, ?, ?)",
            rows)
        self.conn.commit()

    def get(self, paper_id: str, node_id: str) -> tuple[str, str]:
        cur = self.conn.execute(
            "SELECT raw_latex, clean_text FROM theorem_text "
            "WHERE paper_id = ? AND node_id = ?",
            (paper_id, node_id))
        row = cur.fetchone()
        if row is None:
            return ("", "")
        return (row[0] or "", row[1] or "")

    def get_many(self, keys: Iterable[tuple[str, str]]) -> dict:
        """Bulk fetch — returns {(paper_id, node_id): (raw_latex, clean_text)}."""
        out: dict = {}
        # SQLite parameter limit (~999) — batch
        batch: list = []
        for k in keys:
            batch.append(k)
            if len(batch) >= 500:
                self._fetch_batch(batch, out)
                batch = []
        if batch:
            self._fetch_batch(batch, out)
        return out

    def _fetch_batch(self, batch: list, out: dict):
        placeholders = ",".join(["(?, ?)"] * len(batch))
        flat = [v for pair in batch for v in pair]
        cur = self.conn.execute(
            f"SELECT paper_id, node_id, raw_latex, clean_text "
            f"FROM theorem_text WHERE (paper_id, node_id) IN ({placeholders})",
            flat)
        for pid, nid, raw, clean in cur.fetchall():
            out[(pid, nid)] = (raw or "", clean or "")

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM theorem_text").fetchone()[0]
